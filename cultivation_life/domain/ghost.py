from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from .actions import begin_action, complete_action
from .advanced_cultivation import DIVINE_SENSE
from .character import IDENTITY, LIFE, LIFESPAN_DUE
from .combat import CONDITION, combat_snapshot
from .cultivation import CULTIVATION
from .definitions import GameDefinitions, StoryEffectDefinition
from .demonic import DEMONIC_STATE, POSSESSION, possess_character, possession_limit
from .economy import INVENTORY
from .extensions import GHOST_DLC, GHOST_SOUL
from .story import (
    STORY_STATE,
    EffectOutcome,
    StoryEffectRegistry,
    queue_story_event,
)
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, RelationEdge, WorldState
from ..kernel.services import TimeService


GHOST_ECOLOGY = "dlc.ghost.ecology"
BOUND_SOUL = "dlc.ghost.bound_soul"
SOUL_CONTROL = "dlc.ghost.soul_control"

SOUL_SLOTS: dict[str, tuple[str, str]] = {
    "胎光": ("opportunity", "机缘效率"),
    "爽灵": ("external_mp", "外源 MP"),
    "幽精": ("external_hp", "外源 HP"),
    "尸狗": ("mobility", "身法"),
    "伏矢": ("might", "威能"),
    "雀阴": ("resolve", "定力"),
    "吞贼": ("guard", "护御"),
    "非毒": ("sense", "神识"),
    "除秽": ("breach", "破防"),
    "臭肺": ("sustain", "续战"),
}
THREE_SOUL_STATS = frozenset({"opportunity", "external_mp", "external_hp"})
SOUL_TRAITS = (
    ("寒魄", "失去先手时防护提高"),
    ("执念", "降低战意损失"),
    ("迅影", "前两轮身法提高"),
    ("噬灵", "攻势侵蚀敌方防护"),
    ("宿慧", "机缘获取额外提高"),
    ("不灭", "危局中恢复魂势"),
    ("凶魂", "对衰弱敌人增伤"),
    ("明识", "降低禁神识环境惩罚"),
)


@dataclass(frozen=True, slots=True)
class PrepareGhostReincarnation:
    actor_id: str


@dataclass(frozen=True, slots=True)
class ReincarnateGhost:
    actor_id: str


@dataclass(frozen=True, slots=True)
class GhostParadeAction:
    actor_id: str
    action: str
    soul_id: str = ""


@dataclass(frozen=True, slots=True)
class GhostSoulAction:
    actor_id: str
    soul_id: str
    action: str
    slot: str = ""


@dataclass(frozen=True, slots=True)
class GhostAttachmentAction:
    actor_id: str
    action: str
    item_id: str = ""


@dataclass(frozen=True, slots=True)
class GhostConstraintAction:
    actor_id: str
    action: str


@dataclass(frozen=True, slots=True)
class LeavePossessedBody:
    actor_id: str


def _loaded(definitions: GameDefinitions) -> bool:
    return any(
        row.id == GHOST_DLC and row.status == "loaded"
        for row in definitions.extensions
    )


def _phase_two(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(dict(definitions.systems.get("ghost_cultivation", {})).get("phase_two", {}))


def _attachment_quality(item: Any) -> float:
    return max(
        0.0,
        float(item.combat_bonus) + float(item.hp_bonus) + float(item.mp_bonus)
        + float(item.opportunity_bonus) * 100,
    )


def _is_attachable_item(item: Any) -> bool:
    vessel_words = ("器", "剑", "刀", "鼎", "炉", "珠", "灯", "匣", "舟")
    return (
        _attachment_quality(item) > 0
        or "ghost_vessel" in item.tags
        or any(word in item.name for word in vessel_words)
    )


def _default_ecology() -> dict[str, Any]:
    return {
        "slots": {},
        "parade": None,
        "attachment": None,
        "captor": None,
        "pending_capture_revive": False,
    }


def reconcile_ghost_state(state: WorldState, definitions: GameDefinitions) -> None:
    if not _loaded(definitions):
        return
    for entity_id in state.entities.with_component(GHOST_SOUL):
        current = state.entities.get(entity_id, GHOST_ECOLOGY) or _default_ecology()
        for key, value in _default_ecology().items():
            current.setdefault(key, copy.deepcopy(value))
        state.entities.put(entity_id, GHOST_ECOLOGY, current)


def _on_character_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        entity_id = str(event.payload["entity_id"])
        if _loaded(definitions) and str(event.payload.get("path")) == "ghost":
            context.state.entities.put(entity_id, GHOST_ECOLOGY, _default_ecology())

    return handler


def _ensure_actor(context: SimulationContext, actor_id: str, *, free: bool = False) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("此生已经结束")
    if context.state.entities.get(actor_id, GHOST_SOUL) is None:
        raise ValueError("当前角色没有鬼魂核心")
    story = context.state.entities.get(actor_id, STORY_STATE) or {}
    if story.get("pending") is not None:
        raise ValueError("请先处理当前事件")
    if free:
        ecology = context.state.entities.require(actor_id, GHOST_ECOLOGY)
        possession = context.state.entities.require(actor_id, POSSESSION)
        if ecology.get("captor"):
            raise ValueError("魂印受制于拘魂者，当前无法自由行动")
        if possession.get("host"):
            raise ValueError("夺舍期间鬼魂核心沉寂")


def _bound_edges(state: WorldState, actor_id: str) -> list[RelationEdge]:
    return list(state.relations.find(source_id=actor_id, kind=SOUL_CONTROL))


def _bound_ids(state: WorldState, actor_id: str) -> set[str]:
    return {edge.target_id for edge in _bound_edges(state, actor_id)}


def _end_edge(context: SimulationContext, edge: RelationEdge, reason: str) -> None:
    closed = context.state.relations.end(
        edge.relation_id, ended_year=context.state.clock.year
    )
    metadata = dict(closed.metadata)
    metadata["end_reason"] = reason
    context.state.relations.replace_metadata(closed.relation_id, metadata)


def ghost_soul_effects(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> dict[str, float]:
    result = {key: 0.0 for key in {
        "opportunity", "external_mp", "external_hp", "mobility", "might",
        "resolve", "guard", "sense", "breach", "sustain",
    }}
    ecology = state.entities.get(actor_id, GHOST_ECOLOGY)
    possession = state.entities.get(actor_id, POSSESSION) or {}
    if ecology is None or possession.get("host"):
        return result
    rules = dict(_phase_two(definitions).get("soul_slots", {}))
    seven_cap = max(0.0, float(rules.get("seven_effect_cap", 0.25)))
    coefficient = max(0.0, float(rules.get("three_soul_log_coefficient", 0.18)))
    scale = max(1.0, float(rules.get("power_scale", 2500.0)))
    bound = _bound_ids(state, actor_id)
    for slot, soul_id in dict(ecology.get("slots", {})).items():
        if slot not in SOUL_SLOTS or soul_id not in bound:
            continue
        soul = state.entities.get(str(soul_id), BOUND_SOUL)
        if soul is None:
            continue
        stat = SOUL_SLOTS[slot][0]
        power = max(0.0, float(soul.get("combat_power", 0.0)))
        value = (
            coefficient * math.log1p(power / scale)
            if stat in THREE_SOUL_STATS
            else seven_cap * (1.0 - math.exp(-power / scale))
        )
        result[stat] += value
        if stat == "opportunity" and soul.get("trait", {}).get("name") == "宿慧":
            result[stat] += value * 0.08
    return result


def ghost_soul_pressure(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> tuple[float, float]:
    ecology = state.entities.get(actor_id, GHOST_ECOLOGY)
    possession = state.entities.get(actor_id, POSSESSION) or {}
    if ecology is None or possession.get("host"):
        return 0.0, 0.0
    bound = _bound_ids(state, actor_id)
    pressure = 0.0
    for soul_id in dict(ecology.get("slots", {})).values():
        if soul_id not in bound:
            continue
        soul = state.entities.get(str(soul_id), BOUND_SOUL) or {}
        pressure += max(0.0, float(soul.get("soul_pressure", 0.0)))
    per_point = max(0.0, float(_phase_two(definitions).get("pressure_modifier_per_point", 0.01)))
    return pressure, pressure * per_point


def ghost_progression_multiplier(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> float:
    effects = ghost_soul_effects(state, definitions, actor_id)
    ecology = state.entities.get(actor_id, GHOST_ECOLOGY) or {}
    attachment = ecology.get("attachment") or {}
    return max(
        0.0,
        (1.0 + effects["opportunity"])
        * float(attachment.get("cultivation_efficiency_multiplier", 1.0)),
    )


def ghost_breakthrough_bonus(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> float:
    soul = state.entities.get(actor_id, GHOST_SOUL)
    if soul is None:
        return 0.0
    possession = state.entities.get(actor_id, POSSESSION) or {}
    if possession.get("host"):
        return 0.0
    cultivation = state.entities.require(actor_id, CULTIVATION)
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    marks = 0
    for realm_id, count in dict(soul.get("reincarnation_imprints", {})).items():
        if realm_id in {realm.id for realm in definitions.realms}:
            source_index = definitions.realm_index(str(realm_id))
        else:
            try:
                source_index = int(realm_id)
            except (TypeError, ValueError):
                continue
        if source_index >= realm_index:
            marks += max(0, int(count))
    config = dict(definitions.systems.get("ghost_cultivation", {}))
    return marks * max(0.0, float(config.get("reincarnation_bonus_per_mark", 0.05)))


def ghost_combat_modifiers(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> dict[str, Any]:
    effects = ghost_soul_effects(state, definitions, actor_id)
    soul = state.entities.get(actor_id, GHOST_SOUL) or {}
    hp_reference = max(1.0, float(soul.get("intrinsic_hp_reference", soul.get("intrinsic_hp", 100.0))))
    mp_reference = max(1.0, float(soul.get("intrinsic_mp_reference", soul.get("intrinsic_mp", 100.0))))
    hp_current = max(0.0, float(soul.get("intrinsic_hp", hp_reference)))
    mp_current = max(0.0, float(soul.get("intrinsic_mp", mp_reference)))
    stat_factors = {
        key: 1.0 + effects[key]
        for key in ("might", "guard", "mobility", "sense", "sustain", "breach")
    }
    # V2 has no separate morale-resolve axis. Preserve the soul-slot meaning
    # by splitting resolve between defence and staying power.
    stat_factors["guard"] *= 1.0 + effects["resolve"] * 0.5
    stat_factors["sustain"] *= 1.0 + effects["resolve"] * 0.5
    ecology = state.entities.get(actor_id, GHOST_ECOLOGY) or {}
    bound = _bound_ids(state, actor_id)
    trait_factors = {
        "寒魄": ("guard", 0.12),
        "执念": ("sustain", 0.10),
        "迅影": ("mobility", 0.12),
        "噬灵": ("breach", 0.12),
        "不灭": ("sustain", 0.08),
        "凶魂": ("might", 0.15),
        "明识": ("sense", 0.08),
    }
    for soul_id in dict(ecology.get("slots", {})).values():
        if soul_id not in bound:
            continue
        bound_soul = state.entities.get(str(soul_id), BOUND_SOUL) or {}
        trait_name = str(dict(bound_soul.get("trait", {})).get("name", ""))
        if trait_name in trait_factors:
            stat, bonus = trait_factors[trait_name]
            stat_factors[stat] *= 1.0 + bonus
    return {
        "hp_multiplier": min(1.0, hp_current / hp_reference),
        "mp_multiplier": min(1.0, mp_current / mp_reference),
        "external_hp": hp_reference * effects["external_hp"],
        "external_mp": mp_reference * effects["external_mp"],
        "stats": stat_factors,
    }


def _can_reincarnate(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> bool:
    cultivation = state.entities.require(actor_id, CULTIVATION)
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    realm = definitions.realms[realm_index]
    return bool(
        realm_index >= 1
        and int(cultivation["layer"]) >= realm.layers
        and cultivation.get("bottleneck") == "major"
        and state.entities.get(actor_id, GHOST_SOUL) is not None
        and not (state.entities.get(actor_id, POSSESSION) or {}).get("host")
    )


def _perform_reincarnation(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> dict[str, Any]:
    if not _can_reincarnate(context.state, definitions, actor_id):
        raise ValueError("只有抵达大境界最终瓶颈并将机缘修至圆满，方可入轮回")
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    soul = context.state.entities.require(actor_id, GHOST_SOUL)
    source_realm = str(cultivation["realm_id"])
    source_layer = int(cultivation["layer"])
    imprints = dict(soul.get("reincarnation_imprints", {}))
    imprints[source_realm] = int(imprints.get(source_realm, 0)) + 1
    lost_wangsheng = int(soul.get("wangsheng", 0))
    soul["reincarnation_imprints"] = imprints
    soul["last_reincarnation"] = {
        "realm_id": source_realm,
        "layer": source_layer,
        "year": context.state.clock.year,
    }
    if bool(dict(definitions.systems.get("ghost_cultivation", {})).get(
        "clear_wangsheng_on_reincarnation", True
    )):
        soul["wangsheng"] = 0
    cultivation.update(
        realm_id=definitions.realms[1].id,
        layer=1,
        opportunity=0.0,
        bottleneck=None,
        breakthrough_pity={},
        active_breakthrough_aids=[],
    )
    sense = context.state.entities.require(actor_id, DIVINE_SENSE)
    sense.update(rank=1, experience=0.0)
    life = context.state.entities.require(actor_id, LIFE)
    life["lifespan"] = None
    context.state.scheduler.cancel(
        lambda row: row.event_type == LIFESPAN_DUE
        and str(row.payload.get("entity_id", "")) == actor_id
    )
    context.state.entities.put(actor_id, CULTIVATION, cultivation)
    context.state.entities.put(actor_id, GHOST_SOUL, soul)
    context.state.entities.put(actor_id, DIVINE_SENSE, sense)
    context.state.entities.put(actor_id, LIFE, life)
    context.emit(
        "dlc.ghost.reincarnated",
        source=GHOST_DLC,
        scope=EventScope.entity(actor_id),
        payload={
            "actor_id": actor_id,
            "source_realm_id": source_realm,
            "source_layer": source_layer,
            "imprint_count": imprints[source_realm],
            "wangsheng_lost": lost_wangsheng - int(soul.get("wangsheng", 0)),
        },
    )
    return {
        "result": "reincarnated",
        "source_realm_id": source_realm,
        "source_layer": source_layer,
    }


def _prepare_reincarnation_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PrepareGhostReincarnation):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id, free=True)
        if not _can_reincarnate(context.state, definitions, command.actor_id):
            raise ValueError("只有抵达大境界最终瓶颈并将机缘修至圆满，方可入轮回")
        if context.state.relations.find(target_id=command.actor_id, kind="combat_prisoner"):
            raise ValueError("受制期间无法进入轮回")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        soul = context.state.entities.require(command.actor_id, GHOST_SOUL)
        queue_story_event(
            context,
            definitions,
            command.actor_id,
            "SYS_GHOST_REINCARNATION",
            reason="ghost_reincarnation",
            runtime={
                "source_realm": definitions.realm(str(cultivation["realm_id"])).name,
                "source_layer": int(cultivation["layer"]),
                "wangsheng": int(soul.get("wangsheng", 0)),
            },
        )

    return handler


def _reincarnate_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ReincarnateGhost):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id, free=True)
        if context.state.relations.find(target_id=command.actor_id, kind="combat_prisoner"):
            raise ValueError("受制期间无法进入轮回")
        _perform_reincarnation(context, definitions, command.actor_id)

    return handler


def register_ghost_story_effects(
    registry: StoryEffectRegistry, definitions: GameDefinitions,
) -> None:
    def reincarnate(
        context: SimulationContext,
        actor_id: str,
        effect: StoryEffectDefinition,
        pending: dict[str, Any],
    ) -> EffectOutcome:
        del effect, pending
        _perform_reincarnation(context, definitions, actor_id)
        return EffectOutcome("reincarnated", "你舍去此世修为，携轮回印记重归练气一层。")

    registry.register("ghost_reincarnate", reincarnate)


def _schedule_parade(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> None:
    ecology = context.state.entities.require(actor_id, GHOST_ECOLOGY)
    if ecology.get("parade"):
        return
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    unit = definitions.action_time(str(cultivation["realm_id"]), 1)
    rules = dict(_phase_two(definitions).get("parade", {}))
    gap = context.rng.randint(
        max(3, int(rules.get("min_interval_units", 5))),
        max(3, int(rules.get("max_interval_units", 9))),
    )
    location = context.state.entities.require(actor_id, LOCATION)
    world = definitions.worlds[str(location["world_id"])]
    locations = sorted(world.locations)
    start = context.state.clock.year + gap * unit
    ecology["parade"] = {
        "status": "scheduled",
        "world_id": world.id,
        "location_id": context.rng.choice(locations),
        "start_year": start,
        "end_year": start + max(1, int(rules.get("duration_units", 2))) * unit,
        "announced": False,
        "participated": False,
        "soul_ids": [],
    }
    context.state.entities.put(actor_id, GHOST_ECOLOGY, ecology)


def _spawn_parade_souls(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> list[str]:
    ecology = context.state.entities.require(actor_id, GHOST_ECOLOGY)
    parade = dict(ecology["parade"])
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    current_index = definitions.realm_index(str(cultivation["realm_id"]))
    count = max(3, int(dict(_phase_two(definitions).get("parade", {})).get("soul_count", 6)))
    surnames = "沈顾谢陆萧楚苏宁白叶"
    given = ("无咎", "照夜", "忘川", "玄衣", "引灯", "归尘", "青冥", "幽篁")
    soul_ids: list[str] = []
    for index in range(count):
        realm_index = max(0, min(len(definitions.realms) - 1, current_index + context.rng.choice((-1, 0, 0, 1))))
        realm = definitions.realms[realm_index]
        layer = context.rng.randint(1, realm.layers)
        name = f"{context.rng.choice(surnames)}{context.rng.choice(given)}"
        soul_id = context.state.entities.create("ghost_soul")
        power = float(
            realm.base_power * (1.0 + 0.12 * (layer - 1))
            * context.rng.uniform(0.72, 1.18)
        )
        pressure_rules = dict(_phase_two(definitions).get("soul_pressure", {}))
        pressure = float(pressure_rules.get("base", 0.5)) + float(
            pressure_rules.get("power_cap", 2.0)
        ) * (1.0 - math.exp(-power / max(1.0, float(pressure_rules.get("power_scale", 5000.0)))))
        trait_name, trait_description = context.rng.choice(SOUL_TRAITS)
        context.state.entities.put(soul_id, BOUND_SOUL, {
            "name": name,
            "origin": "ghost_parade",
            "status": "roaming",
            "combat_power": power,
            "soul_pressure": round(pressure, 4),
            "affinity": context.rng.randint(-15, 25),
            "defeated": False,
            "befriended": False,
            "trait": {"name": trait_name, "description": trait_description},
            "original_identity": f"{realm.name}遗魂",
            "realm_id": realm.id,
            "layer": layer,
            "world_id": str(parade["world_id"]),
            "location_id": str(parade["location_id"]),
            "parade_year": context.state.clock.year,
            "sequence": index,
        })
        soul_ids.append(soul_id)
    return soul_ids


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        if not _loaded(definitions) or not bool(_phase_two(definitions).get("enabled", False)):
            return
        actor_id = context.state.controlled_entity_id
        if actor_id is None or context.state.entities.get(actor_id, GHOST_ECOLOGY) is None:
            return
        _schedule_parade(context, definitions, actor_id)
        ecology = context.state.entities.require(actor_id, GHOST_ECOLOGY)
        parade = dict(ecology.get("parade") or {})
        if not parade:
            return
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        unit = definitions.action_time(str(cultivation["realm_id"]), 1)
        to_year = int(event.payload["to_year"])
        if not parade.get("announced") and to_year >= int(parade["start_year"]) - 2 * unit:
            parade["announced"] = True
            parade["status"] = "announced"
            context.emit(
                "dlc.ghost.parade.announced",
                source=GHOST_DLC,
                scope=EventScope("world", str(parade["world_id"])),
                payload={"actor_id": actor_id, **parade},
            )
        if to_year >= int(parade["start_year"]) and not parade.get("soul_ids"):
            parade["status"] = "active"
            ecology["parade"] = parade
            context.state.entities.put(actor_id, GHOST_ECOLOGY, ecology)
            parade["soul_ids"] = _spawn_parade_souls(context, definitions, actor_id)
            context.emit(
                "dlc.ghost.parade.started",
                source=GHOST_DLC,
                scope=EventScope("world", str(parade["world_id"])),
                payload={"actor_id": actor_id, "soul_ids": list(parade["soul_ids"])},
            )
        if to_year >= int(parade["end_year"]):
            for soul_id in list(parade.get("soul_ids", [])):
                if soul_id in _bound_ids(context.state, actor_id):
                    continue
                soul = context.state.entities.get(soul_id, BOUND_SOUL)
                if soul:
                    soul["status"] = "departed"
                    context.state.entities.put(soul_id, BOUND_SOUL, soul)
            context.emit(
                "dlc.ghost.parade.ended",
                source=GHOST_DLC,
                scope=EventScope("world", str(parade["world_id"])),
                payload={"actor_id": actor_id, "escaped": len(parade.get("soul_ids", []))},
            )
            ecology["parade"] = None
            context.state.entities.put(actor_id, GHOST_ECOLOGY, ecology)
            _schedule_parade(context, definitions, actor_id)
            ecology = context.state.entities.require(actor_id, GHOST_ECOLOGY)
            parade = dict(ecology.get("parade") or {})
        ecology["parade"] = parade
        captor = dict(ecology.get("captor") or {})
        if captor:
            elapsed = max(
                0, int(event.payload["to_year"]) - int(event.payload["from_year"])
            )
            captor_id = str(captor.get("entity_id") or "")
            for _ in range(elapsed):
                captor["followed_years"] = int(captor.get("followed_years", 0)) + 1
                if context.rng.random() < 0.18:
                    actor_location = context.state.entities.require(actor_id, LOCATION)
                    world = definitions.worlds[str(actor_location["world_id"])]
                    destination = context.rng.choice(sorted(world.locations))
                    actor_location["location_id"] = destination
                    context.state.entities.put(actor_id, LOCATION, actor_location)
                    if (
                        captor_id
                        and context.state.entities.exists(captor_id)
                        and context.state.entities.get(captor_id, LOCATION) is not None
                    ):
                        captor_location = context.state.entities.require(captor_id, LOCATION)
                        captor_location.update(
                            world_id=actor_location["world_id"],
                            location_id=destination,
                        )
                        context.state.entities.put(captor_id, LOCATION, captor_location)
                    captor["location_id"] = destination
                if context.rng.random() < 0.12:
                    own_power = float(combat_snapshot(
                        context.state, definitions, actor_id
                    )["power"])
                    captor_power = max(1.0, float(captor.get("combat_power", 1.0)))
                    won = context.rng.random() < max(
                        0.10, min(0.90, (captor_power + own_power * 0.45) / (
                            captor_power + own_power * 0.45 + captor_power * 0.9
                        ))
                    )
                    if not won:
                        condition = context.state.entities.require(actor_id, CONDITION)
                        condition["hp_ratio"] = max(
                            0.05, float(condition.get("hp_ratio", 1.0)) - 0.12
                        )
                        context.state.entities.put(actor_id, CONDITION, condition)
                    context.emit(
                        "dlc.ghost.captor.battle",
                        source=GHOST_DLC,
                        scope=EventScope.entity(actor_id),
                        payload={
                            "actor_id": actor_id,
                            "captor_id": captor_id or None,
                            "outcome": "victory" if won else "defeat",
                            "ghost_contribution": own_power,
                        },
                    )
            ecology["captor"] = captor
        context.state.entities.put(actor_id, GHOST_ECOLOGY, ecology)

    return handler


def _bind_soul(context: SimulationContext, actor_id: str, soul_id: str) -> None:
    if soul_id in _bound_ids(context.state, actor_id):
        return
    context.state.relations.add(
        source_id=actor_id,
        target_id=soul_id,
        kind=SOUL_CONTROL,
        created_year=context.state.clock.year,
        metadata={"status": "bound", "source": "ghost_parade"},
    )
    soul = context.state.entities.require(soul_id, BOUND_SOUL)
    soul["status"] = "bound"
    context.state.entities.put(soul_id, BOUND_SOUL, soul)
    ecology = context.state.entities.require(actor_id, GHOST_ECOLOGY)
    parade = dict(ecology.get("parade") or {})
    parade["soul_ids"] = [value for value in parade.get("soul_ids", []) if value != soul_id]
    ecology["parade"] = parade
    context.state.entities.put(actor_id, GHOST_ECOLOGY, ecology)
    context.emit(
        "dlc.ghost.soul.bound",
        source=GHOST_DLC,
        scope=EventScope.entity(actor_id),
        payload={"actor_id": actor_id, "soul_id": soul_id},
    )


def _parade_action_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, GhostParadeAction):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id, free=True)
        ecology = context.state.entities.require(command.actor_id, GHOST_ECOLOGY)
        parade = dict(ecology.get("parade") or {})
        location = context.state.entities.require(command.actor_id, LOCATION)
        if (
            parade.get("status") != "active"
            or parade.get("world_id") != location.get("world_id")
            or parade.get("location_id") != location.get("location_id")
        ):
            raise ValueError("当前所在地没有正在发生的百鬼夜行")
        if command.action == "participate":
            if parade.get("participated"):
                raise ValueError("本次百鬼夜行已经参悟过")
            parade["participated"] = True
            soul = context.state.entities.require(command.actor_id, GHOST_SOUL)
            reduction = max(0.0, float(dict(_phase_two(definitions).get("parade", {})).get(
                "participate_reduction_pp", 0.005
            )))
            soul["erosion_rate_pp"] = max(0.0, float(soul["erosion_rate_pp"]) - reduction)
            context.state.entities.put(command.actor_id, GHOST_SOUL, soul)
        else:
            if command.soul_id not in set(map(str, parade.get("soul_ids", []))):
                raise ValueError("这道游魂已经离开夜行")
            soul = context.state.entities.require(command.soul_id, BOUND_SOUL)
            if command.action == "befriend":
                if soul.get("befriended"):
                    raise ValueError("已经与这道游魂结交过")
                soul["befriended"] = True
                soul["affinity"] = min(100, float(soul.get("affinity", 0)) + context.rng.randint(8, 18))
                context.state.entities.put(command.soul_id, BOUND_SOUL, soul)
                chance = max(0.05, min(0.75, 0.18 + float(soul["affinity"]) / 200))
                if context.rng.random() < chance:
                    ghost = context.state.entities.require(command.actor_id, GHOST_SOUL)
                    reduction = max(0.0, float(dict(
                        _phase_two(definitions).get("parade", {})
                    ).get("befriend_reduction_pp", 0.002)))
                    ghost["erosion_rate_pp"] = max(
                        0.0, float(ghost.get("erosion_rate_pp", 0.0)) - reduction
                    )
                    context.state.entities.put(command.actor_id, GHOST_SOUL, ghost)
            elif command.action in {"fight", "capture"}:
                own_power = float(combat_snapshot(
                    context.state, definitions, command.actor_id
                )["power"])
                target_power = max(1.0, float(soul.get("combat_power", 1.0)))
                chance = max(0.08, min(0.95, own_power / (own_power + target_power)))
                outcome = "victory" if context.rng.random() < chance else "defeat"
                condition = context.state.entities.require(command.actor_id, CONDITION)
                condition["hp_ratio"] = max(
                    0.10,
                    float(condition.get("hp_ratio", 1.0))
                    - context.rng.uniform(0.04, 0.14)
                    * (1.0 if outcome == "victory" else 2.0),
                )
                condition["mp_ratio"] = max(
                    0.0, float(condition.get("mp_ratio", 1.0))
                    - context.rng.uniform(0.03, 0.12)
                )
                context.state.entities.put(command.actor_id, CONDITION, condition)
                context.emit(
                    "dlc.ghost.parade.combat.resolved",
                    source=GHOST_DLC,
                    scope=EventScope.entity(command.actor_id),
                    payload={
                        "actor_id": command.actor_id,
                        "soul_id": command.soul_id,
                        "outcome": outcome,
                        "chance": chance,
                    },
                )
                if outcome == "victory":
                    soul["defeated"] = True
                    context.state.entities.put(command.soul_id, BOUND_SOUL, soul)
                    if command.action == "capture":
                        _bind_soul(context, command.actor_id, command.soul_id)
            elif command.action == "bind":
                if not soul.get("defeated"):
                    raise ValueError("必须先在交锋中击溃这道游魂")
                _bind_soul(context, command.actor_id, command.soul_id)
            else:
                raise ValueError("未知的百鬼夜行行动")
        ecology = context.state.entities.require(command.actor_id, GHOST_ECOLOGY)
        if ecology.get("parade"):
            current = dict(ecology["parade"])
            current["participated"] = bool(parade.get("participated"))
            ecology["parade"] = current
            context.state.entities.put(command.actor_id, GHOST_ECOLOGY, ecology)
        context.emit(
            "dlc.ghost.parade.action",
            source=GHOST_DLC,
            scope=EventScope.entity(command.actor_id),
            payload={"actor_id": command.actor_id, "action": command.action, "soul_id": command.soul_id},
        )

    return handler


def _soul_action_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, GhostSoulAction):
        raise TypeError("命令类型错误")
    _ensure_actor(context, command.actor_id)
    ecology = context.state.entities.require(command.actor_id, GHOST_ECOLOGY)
    possession = context.state.entities.require(command.actor_id, POSSESSION)
    bound = _bound_ids(context.state, command.actor_id)
    if command.action == "equip":
        if possession.get("host"):
            raise ValueError("夺舍期间十魂全部沉寂，不能更换")
        if command.soul_id not in bound or command.slot not in SOUL_SLOTS:
            raise ValueError("魂魄或魂位不存在")
        slots = {
            key: value for key, value in dict(ecology.get("slots", {})).items()
            if value != command.soul_id
        }
        slots[command.slot] = command.soul_id
        ecology["slots"] = slots
    elif command.action == "unequip":
        slots = dict(ecology.get("slots", {}))
        target = command.slot or next(
            (key for key, value in slots.items() if value == command.soul_id), ""
        )
        if target not in slots:
            raise ValueError("该魂魄没有入驻魂位")
        slots.pop(target)
        ecology["slots"] = slots
    elif command.action == "release":
        edge = next(
            (row for row in _bound_edges(context.state, command.actor_id) if row.target_id == command.soul_id),
            None,
        )
        if edge is None:
            raise ValueError("魂册中没有这道魂魄")
        _end_edge(context, edge, "released")
        ecology["slots"] = {
            key: value for key, value in dict(ecology.get("slots", {})).items()
            if value != command.soul_id
        }
        soul = context.state.entities.require(command.soul_id, BOUND_SOUL)
        soul["status"] = "released"
        context.state.entities.put(command.soul_id, BOUND_SOUL, soul)
    else:
        raise ValueError("未知魂魄操作")
    context.state.entities.put(command.actor_id, GHOST_ECOLOGY, ecology)
    context.emit(
        "dlc.ghost.soul.action",
        source=GHOST_DLC,
        scope=EventScope.entity(command.actor_id),
        payload={"actor_id": command.actor_id, "soul_id": command.soul_id, "action": command.action, "slot": command.slot},
    )


def _attachment_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, GhostAttachmentAction):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id, free=True)
        ecology = context.state.entities.require(command.actor_id, GHOST_ECOLOGY)
        if command.action == "leave":
            if not ecology.get("attachment"):
                raise ValueError("当前没有附着任何器物")
            ecology["attachment"] = None
        elif command.action == "attach":
            inventory = context.state.entities.require(command.actor_id, INVENTORY)
            if int(dict(inventory.get("items", {})).get(command.item_id, 0)) <= 0:
                raise ValueError("行囊中没有该器物")
            item = definitions.items.get(command.item_id)
            if item is None:
                raise ValueError("未知器物")
            quality = _attachment_quality(item)
            if not _is_attachable_item(item):
                raise ValueError("只能附着兵器、法器或魂器")
            ecology["attachment"] = {
                "item_id": item.id,
                "name": item.name,
                "spirit_name": (
                    f"{item.name}器灵·"
                    f"{context.state.entities.require(command.actor_id, IDENTITY)['name']}"
                ),
                "erosion_growth_multiplier": max(0.45, 0.92 - min(0.47, quality / 5000)),
                "cultivation_efficiency_multiplier": max(0.68, 0.94 - min(0.26, quality / 10000)),
            }
        else:
            raise ValueError("未知附灵操作")
        context.state.entities.put(command.actor_id, GHOST_ECOLOGY, ecology)
        context.emit(
            "dlc.ghost.attachment.changed",
            source=GHOST_DLC,
            scope=EventScope.entity(command.actor_id),
            payload={"actor_id": command.actor_id, "action": command.action, "item_id": command.item_id},
        )

    return handler


def _on_combat_resolved(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload.get("attacker_id", ""))
        if (
            actor_id != context.state.controlled_entity_id
            or event.payload.get("objective") != "kill"
            or event.payload.get("outcome") != "defeat"
            or context.state.entities.get(actor_id, GHOST_ECOLOGY) is None
            or (context.state.entities.get(actor_id, POSSESSION) or {}).get("host")
        ):
            return
        ecology = context.state.entities.require(actor_id, GHOST_ECOLOGY)
        if ecology.get("captor"):
            return
        target_id = str(event.payload.get("target_id", ""))
        target_identity = context.state.entities.get(target_id, IDENTITY)
        target_cultivation = context.state.entities.get(target_id, CULTIVATION)
        if target_identity is None or target_cultivation is None:
            return
        chance = max(0.05, min(0.90, float(_phase_two(definitions).get("defeat_capture_chance", 0.45))))
        if context.rng.random() >= chance:
            return
        ecology["attachment"] = None
        ecology["captor"] = {
            "entity_id": target_id,
            "name": str(target_identity["name"]),
            "realm_id": str(target_cultivation["realm_id"]),
            "layer": int(target_cultivation["layer"]),
            "location_id": context.state.entities.require(target_id, LOCATION)["location_id"],
            "combat_power": float(combat_snapshot(context.state, definitions, target_id)["power"]),
            "followed_years": 0,
            "controlled_form": context.rng.choice(("拘魂", "法器器灵", "魂幡附庸")),
            "capture_chance": chance,
        }
        ecology["pending_capture_revive"] = True
        context.state.entities.put(actor_id, GHOST_ECOLOGY, ecology)
        demonic = context.state.entities.require(actor_id, DEMONIC_STATE)
        demonic["pending_post_battle_possession"] = None
        context.state.entities.put(actor_id, DEMONIC_STATE, demonic)

    return handler


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload.get("entity_id", ""))
    ecology = context.state.entities.get(actor_id, GHOST_ECOLOGY)
    if not ecology or not ecology.get("pending_capture_revive"):
        return
    ecology["pending_capture_revive"] = False
    context.state.entities.put(actor_id, GHOST_ECOLOGY, ecology)
    life = context.state.entities.require(actor_id, LIFE)
    life.update(alive=True, death_reason=None)
    context.state.entities.put(actor_id, LIFE, life)
    condition = context.state.entities.require(actor_id, CONDITION)
    condition["hp_ratio"] = max(0.01, float(condition.get("hp_ratio", 0.0)))
    context.state.entities.put(actor_id, CONDITION, condition)
    context.emit(
        "dlc.ghost.captured",
        source=GHOST_DLC,
        scope=EventScope.entity(actor_id),
        payload={"actor_id": actor_id, "captor": copy.deepcopy(ecology["captor"])},
    )


def _on_breakthrough_succeeded(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload.get("entity_id", ""))
        soul = context.state.entities.get(actor_id, GHOST_SOUL)
        if soul is None or (context.state.entities.get(actor_id, POSSESSION) or {}).get("host"):
            return
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        current = (
            definitions.realm_index(str(cultivation["realm_id"])),
            int(cultivation["layer"]),
        )
        peak = dict(soul.get("historical_peak", {}))
        try:
            previous = (
                definitions.realm_index(str(peak.get("realm_id", definitions.realms[0].id))),
                int(peak.get("layer", 1)),
            )
        except (KeyError, ValueError):
            previous = (0, 1)
        if current > previous:
            old_score = previous[0] * 12 + previous[1]
            new_score = current[0] * 12 + current[1]
            steps = max(1, new_score - old_score)
            soul["intrinsic_hp_reference"] = float(
                soul.get("intrinsic_hp_reference", soul.get("intrinsic_hp", 100.0))
            ) + steps * 8.0
            soul["intrinsic_mp_reference"] = float(
                soul.get("intrinsic_mp_reference", soul.get("intrinsic_mp", 100.0))
            ) + steps * 11.0
            soul["intrinsic_hp"] = float(soul.get("intrinsic_hp", 100.0)) + steps * 8.0
            soul["intrinsic_mp"] = float(soul.get("intrinsic_mp", 100.0)) + steps * 11.0
            soul["historical_peak"] = {
                "realm_id": cultivation["realm_id"], "layer": cultivation["layer"]
            }
        config = dict(definitions.systems.get("ghost_cultivation", {}))
        soul["wangsheng"] = int(soul.get("wangsheng", 0)) + max(
            0, int(config.get("wangsheng_per_layer", 1))
        )
        context.state.entities.put(actor_id, GHOST_SOUL, soul)
        life = context.state.entities.require(actor_id, LIFE)
        if life.get("lifespan") is not None:
            life["lifespan"] = None
            context.state.entities.put(actor_id, LIFE, life)
            context.state.scheduler.cancel(
                lambda row: row.event_type == LIFESPAN_DUE
                and str(row.payload.get("entity_id", "")) == actor_id
            )

    return handler


def _constraint_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, GhostConstraintAction):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        ecology = context.state.entities.require(command.actor_id, GHOST_ECOLOGY)
        captor = dict(ecology.get("captor") or {})
        if not captor:
            raise ValueError("当前并未受制于拘魂者")
        target_id = str(captor.get("entity_id", ""))
        own = float(combat_snapshot(context.state, definitions, command.actor_id)["power"])
        target = max(1.0, float(captor.get("combat_power", 1.0)))
        chance = max(0.05, min(0.90, own / (own + target)))
        if command.action == "wait":
            token = begin_action(
                context,
                actor_id=command.actor_id,
                action="ghost_constraint_wait",
                years=1,
                source=GHOST_DLC,
            )
            TimeService.advance(context, 1, source=GHOST_DLC)
            if bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
                complete_action(
                    context,
                    actor_id=command.actor_id,
                    token=token,
                    metadata={"captor_id": target_id},
                )
            result = "waited"
        elif command.action == "resist":
            if context.rng.random() < chance:
                ecology["captor"] = None
                context.state.entities.put(command.actor_id, GHOST_ECOLOGY, ecology)
                result = "escaped"
            else:
                context.emit(
                    "character.lethal_hazard",
                    source=GHOST_DLC,
                    scope=EventScope.entity(command.actor_id),
                    payload={"entity_id": command.actor_id, "reason": "反抗拘魂者失败，魂飞魄散"},
                )
                result = "dead"
        elif command.action == "possess":
            if not context.state.entities.exists(target_id):
                raise ValueError("拘魂者实体已经不存在")
            if context.rng.random() < chance:
                ecology["captor"] = None
                context.state.entities.put(command.actor_id, GHOST_ECOLOGY, ecology)
                possess_character(
                    context,
                    definitions,
                    command.actor_id,
                    target_id,
                    post_battle=True,
                )
                result = "possessed"
            else:
                context.emit(
                    "character.lethal_hazard",
                    source=GHOST_DLC,
                    scope=EventScope.entity(command.actor_id),
                    payload={"entity_id": command.actor_id, "reason": "夺舍拘魂者失败，神魂反噬而灭"},
                )
                result = "dead"
        else:
            raise ValueError("未知受制行动")
        context.emit(
            "dlc.ghost.constraint.action",
            source=GHOST_DLC,
            scope=EventScope.entity(command.actor_id),
            payload={"actor_id": command.actor_id, "action": command.action, "result": result, "chance": chance},
        )

    return handler


def _leave_possession_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, LeavePossessedBody):
        raise TypeError("命令类型错误")
    _ensure_actor(context, command.actor_id)
    from .demonic import leave_possessed_body

    host = leave_possessed_body(context, command.actor_id)
    context.emit(
        "dlc.ghost.possession.left",
        source=GHOST_DLC,
        scope=EventScope.entity(command.actor_id),
        payload={"actor_id": command.actor_id, "host_id": host.get("entity_id")},
    )


def _controlled_guard(state: WorldState, command: object) -> None:
    actor_id = state.controlled_entity_id
    if actor_id is None or getattr(command, "actor_id", None) != actor_id:
        return
    ecology = state.entities.get(actor_id, GHOST_ECOLOGY) or {}
    if not ecology.get("captor"):
        return
    allowed = {
        "GhostConstraintAction", "GhostSoulAction", "ResolveStoryChoice",
        "RepairPendingStoryEvent", "UseItem", "UpdateSetting",
        "SetWorldNewsDebug",
    }
    if type(command).__name__ not in allowed:
        raise ValueError("魂印受制于拘魂者，当前功能要求自由行动主体，因而不可使用")


def ghost_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    valid_slots = set(SOUL_SLOTS)
    for actor_id in state.entities.with_component(GHOST_ECOLOGY):
        ecology = state.entities.require(actor_id, GHOST_ECOLOGY)
        if state.entities.get(actor_id, GHOST_SOUL) is None:
            errors.append(f"鬼魂生态状态缺少魂核：{actor_id}")
        slots = dict(ecology.get("slots", {}))
        if set(slots) - valid_slots or len(slots.values()) != len(set(slots.values())):
            errors.append(f"十魂槽位非法：{actor_id}")
        bound = _bound_ids(state, actor_id)
        if set(map(str, slots.values())) - bound:
            errors.append(f"十魂槽位引用未拘束魂魄：{actor_id}")
        if ecology.get("captor") and (state.entities.get(actor_id, POSSESSION) or {}).get("host"):
            errors.append(f"受制与夺舍状态互斥：{actor_id}")
        if ecology.get("captor") and ecology.get("attachment"):
            errors.append(f"受制与自主附灵状态互斥：{actor_id}")
    for soul_id in state.entities.with_component(BOUND_SOUL):
        soul = state.entities.require(soul_id, BOUND_SOUL)
        if float(soul.get("combat_power", -1)) < 0 or float(soul.get("soul_pressure", -1)) < 0:
            errors.append(f"拘魂数值非法：{soul_id}")
    return errors


def _public_soul(
    state: WorldState, definitions: GameDefinitions, soul_id: str,
) -> dict[str, Any]:
    soul = state.entities.require(soul_id, BOUND_SOUL)
    identity = state.entities.get(soul_id, IDENTITY) or {"name": soul.get("name", "无名游魂")}
    cultivation = state.entities.get(soul_id, CULTIVATION) or {}
    realm_id = str(cultivation.get("realm_id", "mortal"))
    layer = int(cultivation.get("layer", 1))
    realm = definitions.realm(realm_id)
    result = {
        "id": soul_id,
        "name": identity.get("name", soul.get("name", "无名游魂")),
        "realm_id": realm_id,
        "realm_index": definitions.realm_index(realm_id),
        "realm_name": realm.name if realm.id == "mortal" else f"{realm.name}·{layer}层",
        "layer": layer,
        **copy.deepcopy(soul),
    }
    result["soul_trait"] = copy.deepcopy(
        soul.get("soul_trait") or soul.get("trait") or {}
    )
    return result


def ghost_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    soul = state.entities.get(actor_id, GHOST_SOUL)
    if soul is None:
        return {"available": False, "name": "百鬼夜行:轮回往生"}
    ecology = state.entities.get(actor_id, GHOST_ECOLOGY) or _default_ecology()
    effects = ghost_soul_effects(state, definitions, actor_id)
    pressure, pressure_modifier = ghost_soul_pressure(state, definitions, actor_id)
    bound_ids = sorted(_bound_ids(state, actor_id))
    slots = [
        {
            "id": slot,
            "stat": stat,
            "stat_name": label,
            "soul_id": dict(ecology.get("slots", {})).get(slot),
            "effect": round(effects[stat], 6),
            "curve": (
                "unbounded_diminishing" if stat in THREE_SOUL_STATS
                else "bounded"
            ),
        }
        for slot, (stat, label) in SOUL_SLOTS.items()
    ]
    parade = copy.deepcopy(ecology.get("parade"))
    if parade and not parade.get("announced"):
        parade = {"status": "dormant", "announced": False}
    elif parade:
        parade["souls"] = [
            _public_soul(state, definitions, soul_id)
            for soul_id in parade.get("soul_ids", [])
            if state.entities.get(soul_id, BOUND_SOUL) is not None
        ]
        location = state.entities.require(actor_id, LOCATION)
        parade["at_location"] = bool(
            parade.get("world_id") == location.get("world_id")
            and parade.get("location_id") == location.get("location_id")
        )
    cultivation = state.entities.require(actor_id, CULTIVATION)
    can_reincarnate = _can_reincarnate(state, definitions, actor_id)
    possession = state.entities.require(actor_id, POSSESSION)
    state_name = (
        "possessed" if possession.get("host")
        else "controlled" if ecology.get("captor")
        else "attached" if ecology.get("attachment")
        else "free"
    )
    state_labels = {
        "free": "自由魂体",
        "attached": "附灵器魂",
        "controlled": "受制拘魂",
        "possessed": "夺舍寄身",
    }
    inventory = state.entities.require(actor_id, INVENTORY)
    attachable_items = []
    for item_id, quantity in dict(inventory.get("items", {})).items():
        item = definitions.items.get(str(item_id))
        if int(quantity) <= 0 or item is None or not _is_attachable_item(item):
            continue
        attachable_items.append({
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "quantity": int(quantity),
        })
    attachment = copy.deepcopy(ecology.get("attachment"))
    if isinstance(attachment, dict):
        attachment.setdefault(
            "spirit_name",
            f"{attachment.get('name', '无名器物')}器灵·"
            f"{state.entities.require(actor_id, IDENTITY)['name']}",
        )
    return {
        "available": True,
        "name": "百鬼夜行:轮回往生",
        "state": state_name,
        "state_name": state_labels[state_name],
        "suspended": bool(possession.get("host")),
        "souls_suspended": bool(possession.get("host")),
        "soul": copy.deepcopy(soul),
        "can_reincarnate": can_reincarnate,
        "reincarnation_preview": {
            "source_realm_id": cultivation["realm_id"],
            "source_layer": cultivation["layer"],
            "destination_realm_id": definitions.realms[1].id,
            "next_imprint_count": int(dict(soul.get("reincarnation_imprints", {})).get(
                str(cultivation["realm_id"]), 0
            )) + 1,
        } if can_reincarnate else None,
        "breakthrough_bonus": ghost_breakthrough_bonus(state, definitions, actor_id),
        "slots": slots,
        "bound_souls": [
            _public_soul(state, definitions, soul_id) for soul_id in bound_ids
        ],
        "effects": {key: round(value, 6) for key, value in effects.items()},
        "pressure": round(pressure, 4),
        "pressure_modifier": round(pressure_modifier, 6),
        "parade": parade,
        "attachment": attachment,
        "attachable_items": attachable_items,
        "captor": copy.deepcopy(ecology.get("captor")),
        "host": copy.deepcopy(possession.get("host")),
        "possession_count": int(possession.get("count", 0)),
        "possession_limit": possession_limit(
            state, definitions, actor_id
        ),
    }


def register_ghost_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(PrepareGhostReincarnation, _prepare_reincarnation_handler(definitions))
    bus.register(ReincarnateGhost, _reincarnate_handler(definitions))
    bus.register(GhostParadeAction, _parade_action_handler(definitions))
    bus.register(GhostSoulAction, _soul_action_handler)
    bus.register(GhostAttachmentAction, _attachment_handler(definitions))
    bus.register(GhostConstraintAction, _constraint_handler(definitions))
    bus.register(LeavePossessedBody, _leave_possession_handler)
    bus.add_guard(_controlled_guard)
    bus.event_bus.register("character.created", _on_character_created(definitions))
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))
    bus.event_bus.register("combat.resolved", _on_combat_resolved(definitions))
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register(
        "cultivation.breakthrough.succeeded",
        _on_breakthrough_succeeded(definitions),
    )
