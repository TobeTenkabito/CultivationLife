from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import complete_action
from .character import ACTIVITY, IDENTITY, LIFE
from .cultivation import ACTION_TICK, CULTIVATION, PRACTICE
from .definitions import GameDefinitions, TransformationDefinition
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


BODY = "cultivation.body"
DIVINE_SENSE = "cultivation.divine_sense"
TRANSFORMATIONS = "cultivation.transformations"
TRANSFORMATION_STATS = ("might", "guard", "mobility", "sense", "sustain", "breach")


@dataclass(frozen=True, slots=True)
class EquipSpecialTechnique:
    actor_id: str
    technique_id: str
    slot: str


@dataclass(frozen=True, slots=True)
class AttemptBodyBreakthrough:
    actor_id: str


@dataclass(frozen=True, slots=True)
class AttemptDivineSenseBreakthrough:
    actor_id: str


@dataclass(frozen=True, slots=True)
class AbsorbTransformationMaterial:
    actor_id: str
    item_id: str
    mode: str = "direct"
    stat_id: str = ""
    batch: bool = False


@dataclass(frozen=True, slots=True)
class ManageTransformation:
    actor_id: str
    form_id: str
    action: str


def _new_body() -> dict[str, Any]:
    return {
        "technique_id": None,
        "layer": 0,
        "progress": 0.0,
        "ready": False,
        "breakthrough_pity": {},
        "intrinsic_hp_bonus": 0.0,
    }


def _new_sense() -> dict[str, Any]:
    return {"technique_id": None, "rank": 0, "experience": 0.0}


def _new_transformations() -> dict[str, Any]:
    return {"technique_id": None, "mastery": {}, "loadouts": {}}


def reconcile_advanced_cultivation(state: WorldState, definitions: GameDefinitions) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        if state.entities.get(entity_id, BODY) is None:
            state.entities.put(entity_id, BODY, _new_body())
        if state.entities.get(entity_id, DIVINE_SENSE) is None:
            state.entities.put(entity_id, DIVINE_SENSE, _new_sense())
        if state.entities.get(entity_id, TRANSFORMATIONS) is None:
            state.entities.put(entity_id, TRANSFORMATIONS, _new_transformations())


def _on_character_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        entity_id = str(event.payload["entity_id"])
        context.state.entities.put(entity_id, BODY, _new_body())
        sense = _new_sense()
        path = str(event.payload.get("path", "dao"))
        starter = {
            "demonic": "TECH_BLOOD_SOUL_SENSE",
            "ghost": "TECH_SOUL_ECHO_SENSE",
        }.get(path)
        if starter in definitions.techniques:
            practice = context.state.entities.require(entity_id, PRACTICE)
            known = list(practice.get("known_techniques", []))
            if starter not in known:
                known.append(starter)
            practice["known_techniques"] = known
            context.state.entities.put(entity_id, PRACTICE, practice)
            sense.update(technique_id=starter, rank=1)
        context.state.entities.put(entity_id, DIVINE_SENSE, sense)
        context.state.entities.put(entity_id, TRANSFORMATIONS, _new_transformations())

    return handler


def _ensure_actor(context: SimulationContext, actor_id: str) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能修炼")
    transition = context.state.entities.get(actor_id, "world.transition") or {}
    if transition.get("sealed_cultivation") is not None:
        raise ValueError("当前修为受下界法则压制，不能修炼")
    if context.state.relations.find(target_id=actor_id, kind="combat_prisoner"):
        raise ValueError("身陷牢狱时无法修炼")


def _technique_environment(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str, technique_id: str,
) -> float:
    technique = definitions.techniques[technique_id]
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    world = definitions.worlds[world_id]
    return sum(
        weight * (0.25 + 1.5 * world.qi_concentrations[source] / (world.qi_concentrations[source] + 1))
        for source, weight in technique.sources.items()
    )


def _body_required(definitions: GameDefinitions, layer: int) -> float:
    config = dict(definitions.systems["body_cultivation"])
    return float(config["progress_base"]) + layer * float(config["progress_per_layer"])


def _sense_cost(definitions: GameDefinitions, rank: int) -> float:
    base = float(definitions.systems["demonic_cultivation"]["divine_sense_experience_base"])
    return base * ((rank + 1) ** 2 - rank**2)


def _equip_special(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, EquipSpecialTechnique):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        if command.slot not in {"body", "divine_sense", "transformation"}:
            raise ValueError("未知功法槽位")
        technique = definitions.techniques.get(command.technique_id)
        if technique is None or technique.category != command.slot:
            raise ValueError("功法类型与槽位不符")
        practice = context.state.entities.require(command.actor_id, PRACTICE)
        if command.technique_id not in practice.get("known_techniques", []):
            raise ValueError("尚未学会该功法")
        component_name = {
            "body": BODY, "divine_sense": DIVINE_SENSE,
            "transformation": TRANSFORMATIONS,
        }[command.slot]
        component = context.state.entities.require(command.actor_id, component_name)
        component["technique_id"] = command.technique_id
        if command.slot == "transformation":
            component.setdefault("loadouts", {}).setdefault(
                command.technique_id, {"stored": [], "active": []}
            )
        context.state.entities.put(command.actor_id, component_name, component)
        context.emit(
            "cultivation.special_technique.equipped",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id,
                "technique_id": command.technique_id,
                "slot": command.slot,
            },
        )

    return handler


def _on_action_tick(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        action = str(event.payload.get("action", ""))
        if action not in {"body_train", "sense_train"}:
            return
        actor_id = str(event.payload["actor_id"])
        life = context.state.entities.require(actor_id, LIFE)
        if not bool(life.get("alive")):
            return
        gain = 0.0
        if action == "body_train":
            body = context.state.entities.require(actor_id, BODY)
            technique_id = str(body.get("technique_id") or "")
            technique = definitions.techniques[technique_id]
            config = dict(definitions.systems["body_cultivation"])
            gain = float(context.rng.randint(*map(int, config["progress_per_year"])))
            gain *= 1 + 0.04 * max(0, technique.grade - 1)
            gain *= _technique_environment(context, definitions, actor_id, technique_id)
            cultivation = context.state.entities.require(actor_id, CULTIVATION)
            if cultivation.get("path") == "monster":
                gain *= float(definitions.systems.get("monster_cultivation", {}).get(
                    "body_training_multiplier", 1.5
                ))
            required = _body_required(definitions, int(body["layer"]))
            body["progress"] = min(required, float(body["progress"]) + gain)
            body["ready"] = body["progress"] >= required
            context.state.entities.put(actor_id, BODY, body)
        else:
            sense = context.state.entities.require(actor_id, DIVINE_SENSE)
            technique_id = str(sense.get("technique_id") or "")
            technique = definitions.techniques[technique_id]
            gain = float(definitions.systems["demonic_cultivation"]["divine_sense_training_base"])
            gain *= 1 + technique.divine_sense_bonus * technique.scale
            gain *= _technique_environment(context, definitions, actor_id, technique_id)
            sense["experience"] = float(sense["experience"]) + gain
            context.state.entities.put(actor_id, DIVINE_SENSE, sense)
        context.emit(
            "cultivation.special_training.progressed",
            source="cultivation",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "action": action, "gain": gain},
        )
        if bool(event.payload.get("final")):
            action_spec = dict(definitions.actions[action])
            context.emit(
                "combat.condition.drain.requested",
                source="cultivation",
                scope=EventScope.entity(actor_id),
                payload={
                    "entity_id": actor_id,
                    "hp_ratio": max(0.0, -float(action_spec.get("hp", 0))),
                    "mp_ratio": max(0.0, -float(action_spec.get("mp", 0))),
                    "reason": f"action:{action}",
                },
            )
            activity = context.state.entities.require(actor_id, ACTIVITY)
            activity["actions_completed"] = int(activity["actions_completed"]) + 1
            context.state.entities.put(actor_id, ACTIVITY, activity)
            complete_action(
                context,
                actor_id=actor_id,
                token=str(event.payload["action_token"]),
                metadata={"training_gain": gain},
            )

    return handler


def _body_chance(definitions: GameDefinitions, body: dict[str, Any]) -> dict[str, float]:
    config = dict(definitions.systems["body_cultivation"])
    target = int(body["layer"]) + 1
    base = next(
        float(value) for span, value in dict(config["base_chance"]).items()
        if int(span.split("-", 1)[0]) <= target <= int(span.split("-", 1)[1])
    )
    technique = definitions.techniques[str(body["technique_id"])]
    technique_bonus = (
        technique.body_breakthrough_bonus
        if target <= technique.body_bonus_max_layer else 0.0
    )
    failures = int(dict(body.get("breakthrough_pity", {})).get(f"body:{target}", 0))
    pity = 0.0
    if target >= int(config["pity_start_target"]):
        pity = min(
            float(config["pity_max_bonus"]),
            failures * float(config["pity_bonus_per_failure"]),
        )
    return {
        "base": base, "technique_bonus": technique_bonus,
        "pity_bonus": pity, "failures": failures,
        "final": min(0.98, base + technique_bonus + pity),
    }


def _attempt_body(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, AttemptBodyBreakthrough):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        body = context.state.entities.require(command.actor_id, BODY)
        config = dict(definitions.systems["body_cultivation"])
        maximum = int(config["max_layer"])
        if not body.get("technique_id"):
            raise ValueError("必须先配置一部炼体功法")
        if int(body["layer"]) >= maximum:
            raise ValueError("炼体已经达到一百层极限")
        required = _body_required(definitions, int(body["layer"]))
        if not bool(body.get("ready")) or float(body["progress"]) < required:
            raise ValueError("炼体积累尚未圆满")
        target = int(body["layer"]) + 1
        key = f"body:{target}"
        chance = _body_chance(definitions, body)
        success = context.rng.random() < chance["final"]
        if success:
            body["layer"] = target
            body["progress"] = 0.0
            body["ready"] = False
            body["intrinsic_hp_bonus"] = float(body.get("intrinsic_hp_bonus", 0)) + 12.0
            pity = dict(body.get("breakthrough_pity", {}))
            pity.pop(key, None)
            body["breakthrough_pity"] = pity
        else:
            body["progress"] = required * float(config["failure_retention"])
            body["ready"] = False
            if target >= int(config["pity_start_target"]):
                pity = dict(body.get("breakthrough_pity", {}))
                pity[key] = int(pity.get(key, 0)) + 1
                body["breakthrough_pity"] = pity
        context.state.entities.put(command.actor_id, BODY, body)
        context.emit(
            f"cultivation.body.breakthrough.{'succeeded' if success else 'failed'}",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "target_layer": target,
                "chance": chance, "success": success,
            },
        )

    return handler


def _attempt_sense(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, AttemptDivineSenseBreakthrough):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        sense = context.state.entities.require(command.actor_id, DIVINE_SENSE)
        if not sense.get("technique_id"):
            raise ValueError("必须先配置一部神识功法")
        old_rank = int(sense["rank"])
        cost = _sense_cost(definitions, old_rank)
        if float(sense["experience"]) < cost:
            raise ValueError("神识经验尚未达到手动突破要求")
        sense["experience"] = float(sense["experience"]) - cost
        sense["rank"] = old_rank + 1
        context.state.entities.put(command.actor_id, DIVINE_SENSE, sense)
        context.emit(
            "cultivation.divine_sense.breakthrough.succeeded",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "from_rank": old_rank,
                "to_rank": old_rank + 1, "experience_cost": cost,
            },
        )

    return handler


def _form_progress(state: dict[str, Any], form_id: str) -> dict[str, float]:
    mastery = dict(state.get("mastery", {})).get(form_id, {})
    legacy = max(0.0, min(1.0, float(mastery.get("purity", 0))))
    saved = dict(mastery.get("stats", {}))
    return {key: max(0.0, min(1.0, float(saved.get(key, legacy)))) for key in TRANSFORMATION_STATS}


def _purified_purity(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1 - (1 - value) ** 2


def _absorption_gain(value: float, purified: bool) -> float:
    effective = _purified_purity(value) if purified else max(0.0, min(1.0, value))
    return min(1.0, effective * (0.92 if purified else 0.45))


def _absorb_material(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, AbsorbTransformationMaterial):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        if cultivation.get("path") == "monster":
            raise ValueError("妖修依靠血脉进化，不能使用变化术")
        if command.mode not in {"direct", "purified"}:
            raise ValueError("未知炼化方式")
        item = definitions.items.get(command.item_id)
        if item is None or item.transformation_form_id not in definitions.transformations:
            raise ValueError("该物品不是真灵素材")
        inventory = context.state.entities.require(command.actor_id, "economy.inventory")
        available = int(dict(inventory.get("items", {})).get(command.item_id, 0)) - int(
            dict(inventory.get("reserved", {})).get(command.item_id, 0)
        )
        unit_cost = 2 if command.mode == "purified" else 1
        if available < unit_cost:
            raise ValueError("真灵素材数量不足")
        transformations = context.state.entities.require(command.actor_id, TRANSFORMATIONS)
        form_id = str(item.transformation_form_id)
        progress = _form_progress(transformations, form_id)
        stat_id = command.stat_id if command.stat_id in progress else min(progress, key=progress.get)
        if progress[stat_id] >= 1 - 1e-9:
            raise ValueError("所选变化属性已经圆满")
        remaining = available if command.batch else unit_cost
        consumed = 0
        improved = progress[stat_id]
        direct_gain = _absorption_gain(item.transformation_purity, False)
        pair_gain = _absorption_gain(item.transformation_purity, True)
        if command.batch and command.mode == "purified" and available > 2:
            pair_gain *= 1.30
        while remaining >= unit_cost and improved < 1 - 1e-9:
            improved = min(1.0, improved + (pair_gain if command.mode == "purified" else direct_gain))
            remaining -= unit_cost
            consumed += unit_cost
        if consumed <= 0:
            raise ValueError("没有可炼化的素材")
        context.emit(
            "economy.inventory.consume.requested",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "item_id": command.item_id,
                "quantity": consumed, "reason": "transformation",
            },
        )
        progress[stat_id] = improved
        mastery = dict(transformations.get("mastery", {}))
        mastery[form_id] = {
            "stats": progress,
            "purity": sum(progress.values()) / len(progress),
            "material_id": command.item_id,
            "source_type": item.transformation_source,
        }
        transformations["mastery"] = mastery
        context.state.entities.put(command.actor_id, TRANSFORMATIONS, transformations)
        context.emit(
            "cultivation.transformation.absorbed",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "form_id": form_id,
                "stat_id": stat_id, "new_progress": improved,
                "quantity": consumed, "mode": command.mode,
            },
        )

    return handler


def _incompatible(definitions: GameDefinitions, first: str, second: str) -> bool:
    return (
        second in definitions.transformations[first].incompatible_with
        or first in definitions.transformations[second].incompatible_with
    )


def _manage_transformation(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ManageTransformation):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        state = context.state.entities.require(command.actor_id, TRANSFORMATIONS)
        technique_id = str(state.get("technique_id") or "")
        if not technique_id:
            raise ValueError("请先配置一部变化功法")
        if command.form_id not in definitions.transformations or command.form_id not in state.get("mastery", {}):
            raise ValueError("尚未掌握这种变化")
        technique = definitions.techniques[technique_id]
        loadouts = dict(state.get("loadouts", {}))
        loadout = dict(loadouts.setdefault(technique_id, {"stored": [], "active": []}))
        stored, active = list(loadout.get("stored", [])), list(loadout.get("active", []))
        if command.action == "store":
            if command.form_id in stored:
                raise ValueError("该变化已经存入功法")
            if len(stored) >= technique.transformation_capacity:
                raise ValueError("该功法的变化容量已满")
            stored.append(command.form_id)
        elif command.action == "remove":
            if command.form_id not in stored:
                raise ValueError("该变化不在功法中")
            stored.remove(command.form_id)
            active = [value for value in active if value != command.form_id]
        elif command.action == "activate":
            if command.form_id not in stored:
                raise ValueError("需要先将变化存入功法")
            if command.form_id in active:
                raise ValueError("该变化已经启用")
            if len(active) >= technique.transformation_space:
                raise ValueError("该功法的变化空间已满")
            if any(_incompatible(definitions, command.form_id, other) for other in active):
                raise ValueError("该变化与当前已启用形态互斥")
            active.append(command.form_id)
        elif command.action == "deactivate":
            if command.form_id not in active:
                raise ValueError("该变化当前没有启用")
            active.remove(command.form_id)
        elif command.action in {"promote", "demote"}:
            if command.form_id not in active:
                raise ValueError("只有已启用的变化可以调整顺序")
            index = active.index(command.form_id)
            target = index - 1 if command.action == "promote" else index + 1
            if not 0 <= target < len(active):
                raise ValueError("该变化已经位于顺序边界")
            active[index], active[target] = active[target], active[index]
        else:
            raise ValueError("未知变化管理操作")
        loadout.update(stored=stored, active=active)
        loadouts[technique_id] = loadout
        state["loadouts"] = loadouts
        context.state.entities.put(command.actor_id, TRANSFORMATIONS, state)
        context.emit(
            "cultivation.transformation.loadout.changed",
            source="cultivation",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "form_id": command.form_id,
                "action": command.action, "technique_id": technique_id,
            },
        )

    return handler


def advanced_cultivation_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        maximum = int(definitions.systems["body_cultivation"]["max_layer"])
        for entity_id in state.entities.with_component(IDENTITY):
            body = state.entities.get(entity_id, BODY)
            sense = state.entities.get(entity_id, DIVINE_SENSE)
            transformations = state.entities.get(entity_id, TRANSFORMATIONS)
            if body is None or sense is None or transformations is None:
                errors.append(f"角色 {entity_id} 缺少高级修炼组件")
                continue
            if not 0 <= int(body.get("layer", -1)) <= maximum or float(body.get("progress", -1)) < 0:
                errors.append(f"角色 {entity_id} 炼体状态无效")
            if int(sense.get("rank", -1)) < 0 or float(sense.get("experience", -1)) < 0:
                errors.append(f"角色 {entity_id} 神识状态无效")
            for component, category in ((body, "body"), (sense, "divine_sense"), (transformations, "transformation")):
                technique_id = component.get("technique_id")
                if technique_id is not None and (
                    technique_id not in definitions.techniques
                    or definitions.techniques[str(technique_id)].category != category
                ):
                    errors.append(f"角色 {entity_id} {category}功法无效")
            mastery = dict(transformations.get("mastery", {}))
            if set(mastery) - set(definitions.transformations):
                errors.append(f"角色 {entity_id} 掌握未知变化")
            for form_id in mastery:
                values = _form_progress(transformations, form_id)
                if any(not 0 <= value <= 1 for value in values.values()):
                    errors.append(f"角色 {entity_id} 变化圆满度无效")
        return errors

    return validate


def register_advanced_cultivation_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(EquipSpecialTechnique, _equip_special(definitions))
    bus.register(AttemptBodyBreakthrough, _attempt_body(definitions))
    bus.register(AttemptDivineSenseBreakthrough, _attempt_sense(definitions))
    bus.register(AbsorbTransformationMaterial, _absorb_material(definitions))
    bus.register(ManageTransformation, _manage_transformation(definitions))
    bus.event_bus.register("character.created", _on_character_created(definitions))
    bus.event_bus.register(ACTION_TICK, _on_action_tick(definitions))


def _form_view(
    definition: TransformationDefinition, mastery: dict[str, Any], *, active: bool,
) -> dict[str, Any]:
    stats = {
        key: max(0.0, min(1.0, float(dict(mastery.get("stats", {})).get(key, mastery.get("purity", 0)))))
        for key in TRANSFORMATION_STATS
    }
    purity = sum(stats.values()) / len(stats)
    return {
        "id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "purity": purity,
        "stats": stats,
        "active": active,
        "traits": [
            {"id": trait, "description": description, "required_purity": required, "unlocked": purity >= required}
            for trait, description, required in zip(
                definition.traits, definition.trait_descriptions,
                definition.trait_purity_requirements,
            )
        ],
    }


def advanced_cultivation_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    body = dict(state.entities.require(actor_id, BODY))
    body["required"] = _body_required(definitions, int(body["layer"]))
    body["chance"] = _body_chance(definitions, body) if body.get("technique_id") and int(body["layer"]) < 100 else None
    sense = dict(state.entities.require(actor_id, DIVINE_SENSE))
    sense["breakthrough_cost"] = _sense_cost(definitions, int(sense["rank"]))
    transformations = state.entities.require(actor_id, TRANSFORMATIONS)
    technique_id = transformations.get("technique_id")
    loadout = dict(transformations.get("loadouts", {})).get(str(technique_id), {}) if technique_id else {}
    active = list(loadout.get("active", []))
    mastery = dict(transformations.get("mastery", {}))
    return {
        "body": body,
        "divine_sense": sense,
        "transformations": {
            "technique_id": technique_id,
            "capacity": definitions.techniques[str(technique_id)].transformation_capacity if technique_id else 0,
            "space": definitions.techniques[str(technique_id)].transformation_space if technique_id else 0,
            "stored": list(loadout.get("stored", [])),
            "active": active,
            "forms": [
                _form_view(definitions.transformations[form_id], value, active=form_id in active)
                for form_id, value in mastery.items() if form_id in definitions.transformations
            ],
        },
    }
