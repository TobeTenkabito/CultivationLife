from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE
from .combat import CONDITION, combat_snapshot
from .cultivation import CULTIVATION
from .definitions import GameDefinitions, StoryEffectDefinition
from .story import EffectOutcome, StoryEffectRegistry, STORY_STATE, queue_story_event
from .world import LOCATION, WORLD_TRANSITION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


TRIAL = "cultivation.trial"


@dataclass(frozen=True, slots=True)
class BeginAscensionTrial:
    actor_id: str
    destination_world_id: str
    invited_ids: tuple[str, ...] = ()


def _new_trial_state() -> dict[str, Any]:
    return {"active": None, "history": []}


def reconcile_trial_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        if state.entities.get(entity_id, TRIAL) is None:
            state.entities.put(entity_id, TRIAL, _new_trial_state())


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(str(event.payload["entity_id"]), TRIAL, _new_trial_state())


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    state = context.state.entities.get(entity_id, TRIAL)
    if state is None or state.get("active") is None:
        return
    active = dict(state["active"])
    history = list(state.get("history", []))
    history.append({
        "trial_id": active.get("id"),
        "kind": active.get("kind"),
        "result": "interrupted_by_death",
        "step": None,
        "year": context.state.clock.year,
    })
    state["history"] = history[-50:]
    state["active"] = None
    context.state.entities.put(entity_id, TRIAL, state)


def _required_opportunity(definitions: GameDefinitions, cultivation: dict[str, Any]) -> int:
    realm = definitions.realm(str(cultivation["realm_id"]))
    return round(realm.opportunity_base * (1 + 0.12 * (int(cultivation["layer"]) - 1)))


def _event_ids(kind: str) -> list[str]:
    return {
        "traditional": [
            "EVT_BREAKTHROUGH_TRADITIONAL_001",
            "EVT_BREAKTHROUGH_TRADITIONAL_002",
            "EVT_BREAKTHROUGH_TRADITIONAL_003",
        ],
        "heavenly": [
            "EVT_BREAKTHROUGH_HEAVENLY_001",
            "EVT_BREAKTHROUGH_HEAVENLY_002",
            "EVT_BREAKTHROUGH_HEAVENLY_003",
            "EVT_BREAKTHROUGH_HEAVENLY_004",
            "EVT_BREAKTHROUGH_HEAVENLY_005",
        ],
        "heavenly_demon": ["EVT_HEAVENLY_DEMON_TRIBULATION_001"] * 5,
        "celestial_ascension": [
            f"EVT_CELESTIAL_ASCENSION_{index:03d}" for index in range(1, 10)
        ],
        "asura_ascension": [
            f"EVT_ASURA_ASCENSION_{index:03d}" for index in range(1, 10)
        ],
    }[kind]


def _start_trial(
    context: SimulationContext,
    definitions: GameDefinitions,
    *,
    actor_id: str,
    kind: str,
    source_realm_index: int,
    source_layer: int,
    target_realm_index: int,
    target_layer: int,
    major: bool,
    lethal: bool,
    invited_ids: tuple[str, ...] = (),
    destination_world_id: str | None = None,
    joint_companion_id: str | None = None,
) -> None:
    state = context.state.entities.require(actor_id, TRIAL)
    if state.get("active") is not None:
        raise ValueError("已有试炼正在进行")
    event_ids = _event_ids(kind)
    trial_id = f"trial:{context.state.next_event_sequence:010d}"
    state["active"] = {
        "id": trial_id,
        "kind": kind,
        "status": "active",
        "source_realm_index": source_realm_index,
        "source_layer": source_layer,
        "target_realm_index": target_realm_index,
        "target_layer": target_layer,
        "major": major,
        "lethal": lethal,
        "step_index": 0,
        "event_ids": event_ids,
        "invited_ids": list(invited_ids),
        "destination_world_id": destination_world_id,
        "joint_companion_id": joint_companion_id,
        "started_year": context.state.clock.year,
    }
    context.state.entities.put(actor_id, TRIAL, state)
    queue_story_event(
        context, definitions, actor_id, event_ids[0], reason=f"trial:{trial_id}"
    )
    context.emit(
        "cultivation.trial.started",
        source="trials",
        scope=EventScope.entity(actor_id),
        payload={"entity_id": actor_id, "trial_id": trial_id, "kind": kind},
    )


def _on_breakthrough_trial_requested(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        _start_trial(
            context,
            definitions,
            actor_id=str(event.payload["entity_id"]),
            kind=str(event.payload["kind"]),
            source_realm_index=int(event.payload["source_realm_index"]),
            source_layer=int(event.payload["source_layer"]),
            target_realm_index=int(event.payload["target_realm_index"]),
            target_layer=int(event.payload["target_layer"]),
            major=bool(event.payload["major"]),
            lethal=bool(event.payload["lethal"]),
            joint_companion_id=(
                str(event.payload["joint_companion_id"])
                if event.payload.get("joint_companion_id") else None
            ),
        )

    return handler


def _begin_ascension(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BeginAscensionTrial):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能控制当前角色飞升")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("死亡角色不能飞升")
        if context.state.relations.find(target_id=command.actor_id, kind="combat_prisoner"):
            raise ValueError("身陷牢狱时无法渡劫飞升")
        transition = context.state.entities.require(command.actor_id, WORLD_TRANSITION)
        if transition.get("sealed_cultivation") is not None:
            raise ValueError("下界封印状态不能渡劫飞升")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        location = context.state.entities.require(command.actor_id, LOCATION)
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        path = str(cultivation["path"])
        destination = command.destination_world_id
        if destination == "celestial":
            valid = (
                location["world_id"] == "spirit"
                and realm_index == 8 and int(cultivation["layer"]) == 9
                and path in {"dao", "buddhist", "confucian"}
            )
            kind = "celestial_ascension"
        elif destination == "asura":
            valid = (
                location["world_id"] == "true_demon"
                and realm_index == 8 and int(cultivation["layer"]) == 9
                and path == "demonic"
            )
            kind = "asura_ascension"
        else:
            raise ValueError("目标界面没有九重飞升试炼")
        if not valid:
            raise ValueError("当前道统、境界或界面不满足九重飞升条件")
        required = _required_opportunity(definitions, cultivation)
        if float(cultivation["opportunity"]) < required:
            raise ValueError("当前境界机缘尚未圆满")
        if len(set(command.invited_ids)) != len(command.invited_ids):
            raise ValueError("同行邀请不能重复")
        _start_trial(
            context,
            definitions,
            actor_id=command.actor_id,
            kind=kind,
            source_realm_index=8,
            source_layer=9,
            target_realm_index=9,
            target_layer=1,
            major=True,
            lethal=True,
            invited_ids=command.invited_ids,
            destination_world_id=destination,
        )

    return handler


def _expected_power(definitions: GameDefinitions, realm_index: int, layer: int) -> float:
    realm = definitions.realms[realm_index]
    return float(realm.base_power) * (1 + 0.12 * (layer - 1))


def _story_attributes(context: SimulationContext, actor_id: str) -> dict[str, float]:
    story = context.state.entities.require(actor_id, STORY_STATE)
    return {
        key: float(dict(story.get("attributes", {})).get(key, 0))
        for key in ("karma", "fame", "sha_qi")
    }


def _body_thunder_reduction(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> float:
    body = context.state.entities.get(actor_id, "cultivation.body") or {}
    layer = int(body.get("layer", 0))
    config = dict(definitions.systems["body_cultivation"])
    start = int(config["tribulation_reduction_start"])
    if layer < start:
        return 0.0
    steps = 1 + (layer - start) // int(config["tribulation_reduction_step_layers"])
    return min(0.75, steps * float(config["tribulation_reduction_per_step"]))


def _evaluate_step(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    trial: dict[str, Any],
    step: str,
) -> tuple[bool, str, tuple[float, float], bool]:
    snapshot = combat_snapshot(context.state, definitions, actor_id)
    hp_ratio, mp_ratio = float(snapshot["hp_ratio"]), float(snapshot["mp_ratio"])
    power = float(snapshot["power"])
    attributes = _story_attributes(context, actor_id)
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    heart = float(cultivation.get("heart_demon", 0))
    source = int(trial["source_realm_index"])
    target = int(trial["target_realm_index"])
    thunder = "thunder" in step
    if step == "vitality":
        passed, detail, drain = hp_ratio >= 0.62 and mp_ratio >= 0.62, f"HP {hp_ratio:.0%}、MP {mp_ratio:.0%}", (0.08, 0.10)
    elif step == "karma":
        limit = float(definitions.breakthrough["traditional"]["karma_limits"].get(str(target), 60))
        passed, detail, drain = attributes["karma"] <= limit, f"因果 {attributes['karma']:.1f}/{limit:.0f}", (0.07, 0.09)
    elif step == "heart_demon":
        limit = float(definitions.breakthrough["traditional"]["heart_demon_limits"].get(str(target), 25))
        passed, detail, drain = heart <= limit, f"心魔 {heart:.1f}/{limit:.0f}", (0.07, 0.09)
    elif step == "heaven_vitality":
        passed, detail, drain = hp_ratio >= 0.78 and mp_ratio >= 0.78, f"HP {hp_ratio:.0%}、MP {mp_ratio:.0%}", (0.11, 0.13)
    elif step == "heaven_combat":
        need = _expected_power(definitions, target, 1) * float(definitions.breakthrough["heavenly"]["combat_ratio"])
        passed, detail, drain = power >= need, f"战力 {power:.0f}/{need:.0f}", (0.10, 0.12)
    elif step == "heaven_karma":
        limit = float(definitions.breakthrough["heavenly"]["karma_limit"])
        passed, detail, drain = attributes["karma"] <= limit, f"因果 {attributes['karma']:.1f}/{limit:.0f}", (0.10, 0.12)
    elif step == "heaven_sha":
        limit = float(definitions.breakthrough["heavenly"]["sha_qi_limit"])
        passed = cultivation["path"] in {"demonic", "ghost"} or attributes["sha_qi"] <= limit
        detail, drain = f"煞气 {attributes['sha_qi']:.1f}/{limit:.0f}", (0.10, 0.12)
    elif step == "heaven_heart":
        limit = float(definitions.breakthrough["heavenly"]["heart_demon_limit"])
        passed, detail, drain = heart <= limit, f"心魔 {heart:.1f}/{limit:.0f}", (0.10, 0.12)
    elif step == "heavenly_demon_combat":
        ratios = list(definitions.systems["demonic_cultivation"]["heavenly_demon_tribulation"]["outer_demon_power_ratios"])
        ratio = float(ratios[min(int(trial["step_index"]), len(ratios) - 1)])
        need = _expected_power(definitions, target, 1) * ratio
        passed, detail, drain = power >= need, f"战力 {power:.0f}/{need:.0f}", (0.09, 0.11)
    elif step == "ascension_body":
        passed, detail, drain = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.05, 0.03)
    elif step == "ascension_space":
        passed, detail, drain = mp_ratio >= 0.68, f"MP {mp_ratio:.0%}/68%", (0.04, 0.07)
    elif step.startswith("ascension_thunder_"):
        index = int(step.rsplit("_", 1)[1]) - 1
        hp_need, mp_need = (0.58, 0.48, 0.38)[index], (0.52, 0.42, 0.32)[index]
        passed = hp_ratio >= hp_need and mp_ratio >= mp_need
        detail, drain, thunder = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}", (0.10 + 0.02 * index, 0.08 + 0.02 * index), True
    elif step == "ascension_karma":
        passed, detail, drain = attributes["karma"] <= 120, f"因果 {attributes['karma']:.1f}/120", (0.03, 0.04)
    elif step in {"ascension_demon", "ascension_law"}:
        ratio = 0.75 if step == "ascension_demon" else 0.80
        need = _expected_power(definitions, 8, 9) * ratio
        passed = power >= need and (heart <= 50 if step == "ascension_demon" else True)
        detail, drain = f"战力 {power:.0f}/{need:.0f}，心魔 {heart:.1f}", (0.07, 0.08)
    elif step == "ascension_heart":
        passed, detail, drain = heart <= 45, f"心魔 {heart:.1f}/45", (0.04, 0.06)
    elif step == "asura_body":
        passed, detail, drain = hp_ratio >= 0.75, f"HP {hp_ratio:.0%}/75%", (0.06, 0.03)
    elif step == "asura_boundary":
        config = definitions.systems["demonic_cultivation"]["asura_ascension"]
        level = int((float(cultivation["qi_experience"].get("demon", 0)) / 25.0) ** 0.5)
        required = int(config["required_demon_qi_level"])
        passed = mp_ratio >= 0.68 and level >= required
        detail, drain = f"MP {mp_ratio:.0%}/68%，魔气 {level}/{required}", (0.04, 0.08)
    elif step.startswith("asura_thunder_"):
        index = int(step.rsplit("_", 1)[1]) - 1
        hp_need, mp_need = (0.60, 0.50, 0.40)[index], (0.54, 0.44, 0.34)[index]
        passed = hp_ratio >= hp_need and mp_ratio >= mp_need
        detail, drain, thunder = f"HP {hp_ratio:.0%}/{hp_need:.0%}，MP {mp_ratio:.0%}/{mp_need:.0%}", (0.11 + 0.02 * index, 0.09 + 0.02 * index), True
    elif step == "asura_karma":
        limit = float(definitions.systems["demonic_cultivation"]["asura_ascension"]["karma_limit"])
        passed, detail, drain = attributes["karma"] <= limit, f"因果 {attributes['karma']:.1f}/{limit:.0f}", (0.04, 0.05)
    elif step == "asura_demon":
        config = definitions.systems["demonic_cultivation"]["asura_ascension"]
        need = _expected_power(definitions, 8, 9) * float(config["combat_ratio"])
        limit = float(config["heart_demon_limit"])
        passed = power >= need and heart <= limit
        detail, drain = f"战力 {power:.0f}/{need:.0f}，心魔 {heart:.1f}/{limit:.0f}", (0.08, 0.09)
    elif step == "asura_sha":
        minimum = float(definitions.systems["demonic_cultivation"]["asura_ascension"]["sha_qi_min"])
        passed, detail, drain = attributes["sha_qi"] >= minimum, f"煞气 {attributes['sha_qi']:.1f}/{minimum:.0f}", (0.06, 0.07)
    elif step == "asura_heart":
        limit = float(definitions.systems["demonic_cultivation"]["asura_ascension"]["heart_demon_limit"])
        passed, detail, drain = heart <= limit, f"心魔 {heart:.1f}/{limit:.0f}", (0.04, 0.06)
    else:
        raise ValueError(f"未知试炼关隘：{step}")
    return passed, detail, drain, thunder


def _trial_step_handler(definitions: GameDefinitions):
    def handler(
        context: SimulationContext,
        actor_id: str,
        effect: StoryEffectDefinition,
        pending: dict[str, Any],
    ) -> EffectOutcome:
        state = context.state.entities.require(actor_id, TRIAL)
        active = state.get("active")
        if not isinstance(active, dict) or active.get("status") != "active":
            raise ValueError("当前没有进行中的试炼")
        index = int(active["step_index"])
        if index >= len(active["event_ids"]) or pending.get("id") != active["event_ids"][index]:
            raise ValueError("试炼事件与当前关隘不一致")
        step = str(effect.payload["step"])
        passed, detail, drain, thunder = _evaluate_step(
            context, definitions, actor_id, active, step
        )
        if not passed:
            active["status"] = "failed"
            state["active"] = None
            history = list(state.get("history", []))
            history.append({
                "trial_id": active["id"], "kind": active["kind"],
                "result": "failed", "step": step, "year": context.state.clock.year,
            })
            state["history"] = history[-50:]
            context.state.entities.put(actor_id, TRIAL, state)
            context.emit(
                "cultivation.trial.failed",
                source="trials",
                scope=EventScope.entity(actor_id),
                payload={
                    "entity_id": actor_id, "trial": active, "step": step,
                    "detail": detail,
                },
            )
            if bool(active["lethal"]):
                context.emit(
                    "character.lethal_hazard",
                    source="trials",
                    scope=EventScope.entity(actor_id),
                    payload={"entity_id": actor_id, "reason": f"试炼{step}失败：{detail}"},
                )
                return EffectOutcome("dead", f"判定失败（{detail}），角色陨落。")
            return EffectOutcome("trial_failed", f"判定失败（{detail}），试炼中止。")

        hp_drain, mp_drain = drain
        if thunder:
            reduction = min(
                0.90,
                _body_thunder_reduction(context, definitions, actor_id)
                + float(combat_snapshot(
                    context.state, definitions, actor_id
                ).get("tribulation_reduction", 0)),
            )
            hp_drain *= 1 - reduction
            mp_drain *= 1 - reduction
        context.emit(
            "combat.condition.drain.requested",
            source="trials",
            scope=EventScope.entity(actor_id),
            payload={
                "entity_id": actor_id, "hp_ratio": hp_drain,
                "mp_ratio": mp_drain, "reason": f"trial:{step}",
            },
        )
        active["step_index"] = index + 1
        if int(active["step_index"]) < len(active["event_ids"]):
            state["active"] = active
            context.state.entities.put(actor_id, TRIAL, state)
            queue_story_event(
                context, definitions, actor_id,
                str(active["event_ids"][int(active["step_index"])]),
                reason=f"trial:{active['id']}",
            )
            return EffectOutcome(
                "trial_step_success",
                f"第 {active['step_index']}/{len(active['event_ids'])} 关通过（{detail}）。",
            )

        if active["kind"] in {"celestial_ascension", "asura_ascension"}:
            context.emit(
                "world.ascension.commit.requested",
                source="trials",
                scope=EventScope.entity(actor_id),
                payload={
                    "actor_id": actor_id,
                    "destination_world_id": active["destination_world_id"],
                    "invited_ids": list(active.get("invited_ids", [])),
                    "trial_id": active["id"],
                },
            )
            context.emit(
                "cultivation.ascension.completed",
                source="trials",
                scope=EventScope.entity(actor_id),
                payload={"entity_id": actor_id, "trial": active},
            )
        else:
            context.emit(
                "cultivation.trial.completed",
                source="trials",
                scope=EventScope.entity(actor_id),
                payload={"entity_id": actor_id, "trial": active},
            )
        active["status"] = "completed"
        history = list(state.get("history", []))
        history.append({
            "trial_id": active["id"], "kind": active["kind"],
            "result": "completed", "year": context.state.clock.year,
        })
        state["history"] = history[-50:]
        state["active"] = None
        context.state.entities.put(actor_id, TRIAL, state)
        return EffectOutcome(
            "trial_completed",
            f"第 {len(active['event_ids'])}/{len(active['event_ids'])} 关通过（{detail}），试炼完成。",
        )

    return handler


def trial_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for entity_id in state.entities.with_component(IDENTITY):
            component = state.entities.get(entity_id, TRIAL)
            if component is None:
                errors.append(f"角色 {entity_id} 缺少试炼组件")
                continue
            active = component.get("active")
            if active is None:
                continue
            try:
                event_ids = list(active["event_ids"])
                index = int(active["step_index"])
                if active.get("status") != "active" or not event_ids or not 0 <= index < len(event_ids):
                    errors.append(f"角色 {entity_id} 的试炼进度无效")
                if any(event_id not in definitions.story_events for event_id in event_ids):
                    errors.append(f"角色 {entity_id} 的试炼引用未知事件")
                life = state.entities.require(entity_id, LIFE)
                if not bool(life.get("alive")):
                    errors.append(f"死亡角色 {entity_id} 仍有进行中的试炼")
                story = state.entities.get(entity_id, STORY_STATE) or {}
                pending = story.get("pending")
                if not isinstance(pending, dict) or pending.get("id") != event_ids[index]:
                    errors.append(f"角色 {entity_id} 的试炼与待处理事件不一致")
            except (KeyError, TypeError, ValueError):
                errors.append(f"角色 {entity_id} 的试炼结构无效")
        return errors

    return validate


def register_trial_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(BeginAscensionTrial, _begin_ascension(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register(
        "cultivation.trial.start.requested", _on_breakthrough_trial_requested(definitions)
    )


def register_trial_story_effects(
    registry: StoryEffectRegistry, definitions: GameDefinitions,
) -> None:
    registry.register("trial_step", _trial_step_handler(definitions))


def trial_view(state: WorldState, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    return state.entities.require(actor_id, TRIAL)
