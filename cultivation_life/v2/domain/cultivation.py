from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import ACTIVITY, IDENTITY, LIFE, PerformTimedAction
from .definitions import GameDefinitions, QI_SOURCES, RootDefinition, TechniqueDefinition
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState
from ..kernel.services import TimeService


CULTIVATION = "cultivation.state"
PRACTICE = "cultivation.practice"
ACTION_TICK = "cultivation.action.tick"


@dataclass(frozen=True, slots=True)
class PerformActionUnits:
    actor_id: str
    action: str
    units: int = 1


@dataclass(frozen=True, slots=True)
class GrantTechnique:
    actor_id: str
    technique_id: str
    equip_main: bool = False


@dataclass(frozen=True, slots=True)
class EquipMainTechnique:
    actor_id: str
    technique_id: str


@dataclass(frozen=True, slots=True)
class AttemptBreakthrough:
    actor_id: str


def _initial_cultivation(event: EventEnvelope, definitions: GameDefinitions) -> tuple[dict[str, Any], dict[str, Any]]:
    path = str(event.payload["path"])
    root_id = str(event.payload["spirit_root"])
    realm_id = str(event.payload["realm_id"])
    cultivation = {
        "path": path,
        "spirit_root": root_id,
        "additional_roots": [],
        "realm_id": realm_id,
        "layer": int(event.payload["layer"]),
        "opportunity": 0.0,
        "heart_demon": 0.0,
        "bottleneck": None,
        "breakthrough_pity": {},
        "qi_experience": {source: 0.0 for source in QI_SOURCES},
    }
    starters = {
        "demonic": "TECH_DEMON_BREATHING",
        "ghost": "TECH_GHOST_BREATHING",
    }
    starter_id = starters.get(path)
    if starter_id and starter_id not in definitions.techniques:
        starter_id = None
    practice = {
        "known_techniques": [starter_id] if starter_id else [],
        "main_technique_id": starter_id,
    }
    return cultivation, practice


def _on_character_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        entity_id = str(event.payload["entity_id"])
        cultivation, practice = _initial_cultivation(event, definitions)
        context.state.entities.put(entity_id, CULTIVATION, cultivation)
        context.state.entities.put(entity_id, PRACTICE, practice)

    return handler


def _ensure_controllable_alive(context: SimulationContext, actor_id: str) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能执行修炼行动")


def _schedule_action(
    context: SimulationContext,
    *,
    actor_id: str,
    action: str,
    years: int,
) -> None:
    if action not in {"cultivate", "rest"}:
        raise ValueError("未知的V2耗时行动")
    if not isinstance(years, int) or isinstance(years, bool) or not 1 <= years <= 1_000:
        raise ValueError("单次行动必须耗时1至1000年")
    action_token = f"action:{context.state.next_event_sequence}:{actor_id}"
    start_year = context.state.clock.year
    for offset in range(1, years + 1):
        context.state.scheduler.schedule(
            due_year=start_year + offset,
            event_type=ACTION_TICK,
            source="cultivation",
            scope=EventScope.entity(actor_id),
            payload={
                "actor_id": actor_id,
                "action": action,
                "action_token": action_token,
                "elapsed": offset,
                "total_years": years,
                "final": offset == years,
            },
        )
    TimeService.advance(context, years, source=f"cultivation.action.{action}")


def _perform_timed_action_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, PerformTimedAction):
        raise TypeError("命令类型错误")
    _ensure_controllable_alive(context, command.actor_id)
    _schedule_action(context, actor_id=command.actor_id, action=command.action, years=command.years)


def _perform_units_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PerformActionUnits):
            raise TypeError("命令类型错误")
        _ensure_controllable_alive(context, command.actor_id)
        if not isinstance(command.units, int) or isinstance(command.units, bool) or not 1 <= command.units <= 10:
            raise ValueError("行动单位必须为1至10")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        years = definitions.action_time(str(cultivation["realm_id"]), command.units)
        _schedule_action(context, actor_id=command.actor_id, action=command.action, years=years)

    return handler


def _qi_environment_multiplier(concentration: float) -> float:
    return 0.25 + 1.5 * concentration / (concentration + 1)


def _can_practice(root: RootDefinition, technique: TechniqueDefinition) -> bool:
    if technique.element in {"neutral", "sex"}:
        return True
    elements = set(root.elements)
    if technique.element == "five_elements":
        return {"metal", "wood", "water", "fire", "earth"} <= elements
    return technique.element in elements


def _opportunity_required(definitions: GameDefinitions, cultivation: dict[str, Any]) -> int:
    realm = definitions.realm(str(cultivation["realm_id"]))
    return round(realm.opportunity_base * (1 + 0.12 * (int(cultivation["layer"]) - 1)))


def _root_probability_group(root: RootDefinition) -> str:
    if root.id.startswith("acquired_"):
        return "acquired"
    return {
        "伪灵根": "pseudo",
        "天灵根": "heavenly",
        "极品灵根": "supreme",
        "变异灵根": "mutated",
        "法则灵根": "law",
        "异世界灵根": "otherworld",
        "后天灵根": "acquired",
        "后天变异灵根": "acquired",
    }.get(root.tier, "acquired")


def _mark_bottleneck(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    cultivation: dict[str, Any],
) -> None:
    if str(cultivation["spirit_root"]) == "none":
        cultivation["opportunity"] = 0.0
        cultivation["bottleneck"] = None
        return
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    realm = definitions.realms[realm_index]
    safety = 0
    while float(cultivation["opportunity"]) >= _opportunity_required(definitions, cultivation) and safety < 32:
        safety += 1
        required = _opportunity_required(definitions, cultivation)
        layer = int(cultivation["layer"])
        if layer >= realm.layers:
            cultivation["opportunity"] = min(float(cultivation["opportunity"]), float(required))
            cultivation["bottleneck"] = "major"
            break
        if realm_index >= 2:
            cultivation["opportunity"] = min(float(cultivation["opportunity"]), float(required))
            cultivation["bottleneck"] = "minor"
            break
        cultivation["opportunity"] = max(0.0, float(cultivation["opportunity"]) - required)
        cultivation["layer"] = layer + 1
        context.emit(
            "cultivation.breakthrough.succeeded",
            source="cultivation",
            scope=EventScope.entity(actor_id),
            payload={
                "entity_id": actor_id,
                "kind": "minor",
                "realm_id": realm.id,
                "from_layer": layer,
                "to_layer": layer + 1,
                "automatic": True,
            },
        )


def _cultivation_gain(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    action: str,
) -> float:
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    practice = context.state.entities.require(actor_id, PRACTICE)
    root = definitions.roots[str(cultivation["spirit_root"])]
    main_id = practice.get("main_technique_id")
    if root.id == "none" or not main_id:
        return 0.0
    technique = definitions.techniques[str(main_id)]
    low, high = map(int, definitions.actions[action]["opportunity"])
    base = context.rng.randint(low, high)
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    world = definitions.worlds[world_id]
    environment = sum(
        weight * _qi_environment_multiplier(world.qi_concentrations[source])
        for source, weight in technique.sources.items()
    )
    inventory = context.state.entities.get(actor_id, "economy.inventory") or {"items": {}}
    item_bonus = sum(
        definitions.items[item_id].opportunity_bonus * int(quantity)
        for item_id, quantity in dict(inventory.get("items", {})).items()
        if item_id in definitions.items
    )
    multiplier = (
        root.efficiency
        * (1 + technique.opportunity_bonus * technique.scale)
        * max(0.0, 1 + item_bonus)
        * environment
    )
    if action == "cultivate" and cultivation["path"] == "demonic":
        multiplier *= 0.1
    return float(base) * multiplier


def _on_action_tick(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        life = context.state.entities.require(actor_id, LIFE)
        final = bool(event.payload["final"])
        if not bool(life.get("alive")):
            if final:
                context.emit(
                    "cultivation.action.interrupted",
                    source="cultivation",
                    scope=EventScope.entity(actor_id),
                    payload={
                        "actor_id": actor_id,
                        "action": event.payload["action"],
                        "reason": life.get("death_reason"),
                    },
                )
            return
        action = str(event.payload["action"])
        activity = context.state.entities.require(actor_id, ACTIVITY)
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        gain = _cultivation_gain(context, definitions, actor_id, action)
        cultivation["opportunity"] = max(0.0, float(cultivation["opportunity"]) + gain)
        if gain > 0:
            practice = context.state.entities.require(actor_id, PRACTICE)
            technique = definitions.techniques[str(practice["main_technique_id"])]
            location = context.state.entities.require(actor_id, LOCATION)
            world = definitions.worlds[str(location["world_id"])]
            local = world.locations[str(location["location_id"])]
            qi_experience = dict(cultivation["qi_experience"])
            for source, weight in technique.sources.items():
                qi_experience[source] = float(qi_experience.get(source, 0.0)) + (
                    gain * weight * local.qi_gain_efficiencies[source]
                )
            cultivation["qi_experience"] = qi_experience
        _mark_bottleneck(context, definitions, actor_id, cultivation)
        context.state.entities.put(actor_id, CULTIVATION, cultivation)
        if action == "rest":
            activity["rest_years"] = int(activity["rest_years"]) + 1
        if final:
            activity["actions_completed"] = int(activity["actions_completed"]) + 1
            context.emit(
                "cultivation.action.completed",
                source="cultivation",
                scope=EventScope.entity(actor_id),
                payload={
                    "actor_id": actor_id,
                    "action": action,
                    "years": int(event.payload["total_years"]),
                    "action_token": event.payload["action_token"],
                },
            )
        context.state.entities.put(actor_id, ACTIVITY, activity)

    return handler


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["entity_id"])
    cancelled = context.state.scheduler.cancel(
        lambda scheduled: (
            scheduled.event_type == ACTION_TICK
            and str(scheduled.payload.get("actor_id", "")) == actor_id
        )
    )
    tokens = sorted({str(scheduled.payload.get("action_token", "")) for scheduled in cancelled})
    for token in tokens:
        sample = next(
            scheduled for scheduled in cancelled
            if str(scheduled.payload.get("action_token", "")) == token
        )
        context.emit(
            "cultivation.action.interrupted",
            source="cultivation",
            scope=EventScope.entity(actor_id),
            payload={
                "actor_id": actor_id,
                "action": sample.payload.get("action"),
                "action_token": token,
                "reason": event.payload.get("reason"),
            },
        )


def _grant_technique_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, GrantTechnique):
            raise TypeError("命令类型错误")
        if not context.state.entities.exists(command.actor_id):
            raise ValueError("角色不存在")
        technique = definitions.techniques.get(command.technique_id)
        if technique is None:
            raise ValueError("未知功法")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        root = definitions.roots[str(cultivation["spirit_root"])]
        if not _can_practice(root, technique):
            raise ValueError("灵根属性与功法不合")
        practice = context.state.entities.require(command.actor_id, PRACTICE)
        known = list(practice["known_techniques"])
        if command.technique_id not in known:
            known.append(command.technique_id)
        practice["known_techniques"] = known
        if command.equip_main:
            if technique.category != "spiritual":
                raise ValueError("只有灵修功法可以配置为主修")
            practice["main_technique_id"] = command.technique_id
        context.state.entities.put(command.actor_id, PRACTICE, practice)
        context.emit(
            "cultivation.technique.learned",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "technique_id": command.technique_id},
        )

    return handler


def _equip_technique_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, EquipMainTechnique):
            raise TypeError("命令类型错误")
        practice = context.state.entities.require(command.actor_id, PRACTICE)
        if command.technique_id not in practice["known_techniques"]:
            raise ValueError("尚未学会该功法")
        technique = definitions.techniques[command.technique_id]
        if technique.category != "spiritual":
            raise ValueError("只有灵修功法可以配置为主修")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        if not _can_practice(definitions.roots[str(cultivation["spirit_root"])], technique):
            raise ValueError("灵根属性与功法不合")
        practice["main_technique_id"] = command.technique_id
        context.state.entities.put(command.actor_id, PRACTICE, practice)
        context.emit(
            "cultivation.technique.equipped",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "technique_id": command.technique_id},
        )

    return handler


def _on_technique_purchased(definitions: GameDefinitions):
    grant = _grant_technique_handler(definitions)

    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        grant(context, GrantTechnique(
            actor_id=str(event.payload["entity_id"]),
            technique_id=str(event.payload["technique_id"]),
            equip_main=False,
        ))

    return handler


def _breakthrough_chance(definitions: GameDefinitions, cultivation: dict[str, Any], major: bool) -> float:
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    if major and realm_index == 0:
        base = 1.0
    elif major:
        table = definitions.breakthrough["major_base"].get(str(realm_index))
        if table is None:
            raise ValueError("当前大境界突破需要尚未迁移的专属试炼")
        group = _root_probability_group(definitions.roots[str(cultivation["spirit_root"])])
        base = float(table.get(group, table.get("default", 0.01)))
    else:
        if realm_index >= 6:
            raise ValueError("当前小境界突破需要尚未迁移的专属试炼")
        base = float(definitions.breakthrough["minor_base"].get(str(realm_index), 1.0))
    penalty = min(
        float(definitions.breakthrough["heart_demon_penalty_cap"]),
        float(cultivation["heart_demon"])
        * float(definitions.breakthrough["heart_demon_penalty_per_point"]),
    )
    pity = 0.0
    if not major:
        key = f"minor:{realm_index}:{int(cultivation['layer'])}"
        failures = int(dict(cultivation["breakthrough_pity"]).get(key, 0))
        pity = min(
            float(definitions.breakthrough["minor_pity"]["max_bonus"]),
            failures * float(definitions.breakthrough["minor_pity"]["bonus_per_failure"]),
        )
    return max(0.005, min(0.98, base + pity - penalty))


def _attempt_breakthrough_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, AttemptBreakthrough):
            raise TypeError("命令类型错误")
        _ensure_controllable_alive(context, command.actor_id)
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        kind = cultivation.get("bottleneck")
        if kind not in {"minor", "major"}:
            raise ValueError("尚未抵达需要手动突破的瓶颈")
        major = kind == "major"
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        if major and realm_index >= len(definitions.realms) - 1:
            raise ValueError("已经达到当前境界体系终点")
        required = _opportunity_required(definitions, cultivation)
        if float(cultivation["opportunity"]) < required:
            raise ValueError("机缘尚未圆满")
        chance = _breakthrough_chance(definitions, cultivation, major)
        old_realm = str(cultivation["realm_id"])
        old_layer = int(cultivation["layer"])
        pity_key = f"minor:{realm_index}:{old_layer}"
        success = context.rng.random() < chance
        if not success:
            retention_key = "major_failure_retention" if major else "minor_failure_retention"
            demon_key = "major_failure_heart_demon" if major else "minor_failure_heart_demon"
            cultivation["opportunity"] = required * float(definitions.breakthrough[retention_key])
            cultivation["heart_demon"] = float(cultivation["heart_demon"]) + float(
                definitions.breakthrough[demon_key]
            )
            if not major:
                pity = dict(cultivation["breakthrough_pity"])
                pity[pity_key] = int(pity.get(pity_key, 0)) + 1
                cultivation["breakthrough_pity"] = pity
            cultivation["bottleneck"] = None
            context.state.entities.put(command.actor_id, CULTIVATION, cultivation)
            context.emit(
                "cultivation.breakthrough.failed",
                source="cultivation",
                scope=EventScope.entity(command.actor_id),
                payload={"entity_id": command.actor_id, "kind": kind, "chance": chance},
            )
            return

        cultivation["opportunity"] = max(0.0, float(cultivation["opportunity"]) - required)
        cultivation["heart_demon"] = max(
            0.0,
            float(cultivation["heart_demon"]) - (5.0 if major else 1.0),
        )
        pity = dict(cultivation["breakthrough_pity"])
        pity.pop(pity_key, None)
        cultivation["breakthrough_pity"] = pity
        life = context.state.entities.require(command.actor_id, LIFE)
        lifespan_gain = 0
        if major:
            target = definitions.realms[realm_index + 1]
            cultivation["realm_id"] = target.id
            cultivation["layer"] = 1
            if target.lifespan is None:
                life["lifespan"] = None
            elif life.get("lifespan") is not None:
                rolled = context.rng.randint(*target.lifespan)
                if cultivation["path"] == "monster":
                    rolled *= 3
                old_lifespan = int(life["lifespan"])
                life["lifespan"] = max(old_lifespan, rolled)
                lifespan_gain = int(life["lifespan"]) - old_lifespan
        else:
            cultivation["layer"] = old_layer + 1
            stage = "middle" if cultivation["layer"] == 4 else "late" if cultivation["layer"] == 7 else None
            span = definitions.stage_lifespan_bonus.get(old_realm, {}).get(stage or "")
            if span and life.get("lifespan") is not None:
                lifespan_gain = context.rng.randint(*span)
                if cultivation["path"] == "monster":
                    lifespan_gain *= 3
                life["lifespan"] = int(life["lifespan"]) + lifespan_gain
        cultivation["bottleneck"] = None
        context.state.entities.put(command.actor_id, LIFE, life)
        context.state.entities.put(command.actor_id, CULTIVATION, cultivation)
        context.emit(
            "character.lifespan.changed",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "lifespan": life.get("lifespan")},
        )
        context.emit(
            "cultivation.breakthrough.succeeded",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id,
                "kind": kind,
                "chance": chance,
                "from_realm_id": old_realm,
                "from_layer": old_layer,
                "to_realm_id": cultivation["realm_id"],
                "to_layer": cultivation["layer"],
                "lifespan_gain": lifespan_gain,
                "automatic": False,
            },
        )

    return handler


def cultivation_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for entity_id in state.entities.with_component(IDENTITY):
            cultivation = state.entities.get(entity_id, CULTIVATION)
            practice = state.entities.get(entity_id, PRACTICE)
            if cultivation is None or practice is None:
                errors.append(f"角色 {entity_id} 缺少修炼组件")
                continue
            realm_id = str(cultivation.get("realm_id", ""))
            root_id = str(cultivation.get("spirit_root", ""))
            if realm_id not in {realm.id for realm in definitions.realms}:
                errors.append(f"角色 {entity_id} 境界无效")
                continue
            realm = definitions.realm(realm_id)
            if not 1 <= int(cultivation.get("layer", 0)) <= realm.layers:
                errors.append(f"角色 {entity_id} 层数无效")
            if root_id not in definitions.roots:
                errors.append(f"角色 {entity_id} 灵根无效")
            if cultivation.get("path") not in definitions.paths:
                errors.append(f"角色 {entity_id} 修行道路无效")
            if float(cultivation.get("opportunity", -1)) < 0:
                errors.append(f"角色 {entity_id} 机缘为负")
            known = list(practice.get("known_techniques", []))
            if len(known) != len(set(known)) or set(known) - set(definitions.techniques):
                errors.append(f"角色 {entity_id} 功法列表无效")
            main_id = practice.get("main_technique_id")
            if main_id is not None and main_id not in known:
                errors.append(f"角色 {entity_id} 主修功法尚未学会")
        return errors

    return validate


def register_cultivation_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(PerformTimedAction, _perform_timed_action_handler)
    bus.register(PerformActionUnits, _perform_units_handler(definitions))
    bus.register(GrantTechnique, _grant_technique_handler(definitions))
    bus.register(EquipMainTechnique, _equip_technique_handler(definitions))
    bus.register(AttemptBreakthrough, _attempt_breakthrough_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created(definitions))
    bus.event_bus.register("economy.technique.purchased", _on_technique_purchased(definitions))
    bus.event_bus.register(ACTION_TICK, _on_action_tick(definitions))
    bus.event_bus.register("character.died", _on_character_died)


def cultivation_view(state: Any, definitions: GameDefinitions, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    cultivation = state.entities.require(actor_id, CULTIVATION)
    practice = state.entities.require(actor_id, PRACTICE)
    realm = definitions.realm(str(cultivation["realm_id"]))
    main_id = practice.get("main_technique_id")
    return {
        **cultivation,
        "realm_name": realm.name,
        "realm_index": definitions.realm_index(realm.id),
        "opportunity_required": _opportunity_required(definitions, cultivation),
        "spirit_root_name": definitions.roots[str(cultivation["spirit_root"])].name,
        "path_name": definitions.paths[str(cultivation["path"])],
        "known_techniques": [
            {"id": technique_id, "name": definitions.techniques[technique_id].name}
            for technique_id in practice["known_techniques"]
        ],
        "main_technique": (
            {"id": main_id, "name": definitions.techniques[str(main_id)].name}
            if main_id else None
        ),
    }
