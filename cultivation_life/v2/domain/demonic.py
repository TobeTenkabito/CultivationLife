from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .actions import ACTION_RUNTIME, begin_action, complete_action
from .advanced_cultivation import DIVINE_SENSE
from .character import IDENTITY, LIFE, LIFESPAN_DUE, character_view
from .combat import CONDITION, PRISONER, combat_snapshot
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions
from .economy import change_inventory_item, inventory_quantity
from .extensions import GHOST_SOUL
from .party import PARTY_MEMBER
from .production import SPIRIT_FIELD
from .relations import relationship_affinity, set_relationship_affinity
from .story import STORY_STATE, ResolveStoryChoice
from .world import LOCATION, AscendWorld
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, RelationEdge, WorldState
from ..kernel.services import TimeService


DEMONIC_STATE = "demonic.state"
IMPRISONMENT = "demonic.imprisonment"
PUPPET = "demonic.puppet"
PUPPET_CONTROL = "demonic.puppet_control"
FOREIGN_SOUL = "demonic.foreign_soul"
SOUL_CONTROL = "demonic.soul_control"
POSSESSION = "demonic.possession"
SOUL_SECLUSION_TICK = "demonic.soul_seclusion.tick"
PUPPET_NAMES = {"corpse": "炼尸", "living": "活傀", "mechanical": "机关傀儡"}


@dataclass(frozen=True, slots=True)
class EnterImprisonment:
    actor_id: str
    captor_id: str
    years: int
    name: str = "势力大牢"
    facility: str = "world_prison"
    hostility: float = 0.0


@dataclass(frozen=True, slots=True)
class PrisonAction:
    actor_id: str
    action: str


@dataclass(frozen=True, slots=True)
class CaptiveAction:
    actor_id: str
    target_id: str
    action: str


@dataclass(frozen=True, slots=True)
class CraftMechanicalPuppet:
    actor_id: str


@dataclass(frozen=True, slots=True)
class PuppetAction:
    actor_id: str
    puppet_id: str
    action: str
    content_id: str = ""


@dataclass(frozen=True, slots=True)
class RefineForeignSoul:
    actor_id: str
    secluded: bool = False


@dataclass(frozen=True, slots=True)
class PostBattlePossession:
    actor_id: str
    target_id: str


def _default_state() -> dict[str, Any]:
    return {
        "devouring_breakthrough_bonus": 0.0,
        "pending_post_battle_possession": None,
    }


def _default_prison() -> dict[str, Any]:
    return {"active": None, "last_result": None}


def _default_possession() -> dict[str, Any]:
    return {"host": None, "count": 0, "core": None}


def _rules(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems["demonic_cultivation"])


def _action_unit(state: WorldState, actor_id: str) -> int:
    runtime = state.entities.require(actor_id, ACTION_RUNTIME)
    return max(0, int(runtime.get("next_sequence", 1)) - 1)


def _pending_story(state: WorldState, actor_id: str) -> bool:
    story = state.entities.get(actor_id, STORY_STATE) or {}
    return story.get("pending") is not None


def _imprisonment_guard(state: WorldState, command: object) -> None:
    actor_id = state.controlled_entity_id
    if actor_id is None or getattr(command, "actor_id", None) != actor_id:
        return
    prison = state.entities.get(actor_id, IMPRISONMENT) or {}
    if not prison.get("active"):
        return
    if isinstance(command, (PrisonAction, ResolveStoryChoice, AscendWorld)):
        return
    raise ValueError("身陷大牢时只能服刑、处理当前事件或尝试飞升偷渡")


def _ensure_actor(context: SimulationContext, actor_id: str) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能执行该操作")
    if _pending_story(context.state, actor_id):
        raise ValueError("请先处理当前事件")
    if (context.state.entities.get(actor_id, IMPRISONMENT) or {}).get("active"):
        raise ValueError("身陷大牢时不能执行该操作")


def _is_demonic(state: WorldState, actor_id: str) -> bool:
    return state.entities.require(actor_id, CULTIVATION).get("path") == "demonic"


def puppet_capacity(state: WorldState, actor_id: str) -> int:
    sense = state.entities.require(actor_id, DIVINE_SENSE)
    return max(1, (int(sense.get("rank", 0)) + 2) // 3)


def _puppet_edges(state: WorldState, actor_id: str) -> list[RelationEdge]:
    return list(state.relations.find(source_id=actor_id, kind=PUPPET_CONTROL))


def _soul_edges(state: WorldState, actor_id: str) -> list[RelationEdge]:
    return list(state.relations.find(source_id=actor_id, kind=SOUL_CONTROL))


def _puppet_edge(
    state: WorldState, actor_id: str, puppet_id: str,
) -> RelationEdge | None:
    return next(
        (edge for edge in _puppet_edges(state, actor_id) if edge.target_id == puppet_id),
        None,
    )


def _end_edge(
    context: SimulationContext, edge: RelationEdge, reason: str,
) -> None:
    closed = context.state.relations.end(
        edge.relation_id, ended_year=context.state.clock.year
    )
    metadata = dict(closed.metadata)
    metadata["end_reason"] = reason
    context.state.relations.replace_metadata(closed.relation_id, metadata)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    context.state.entities.put(entity_id, DEMONIC_STATE, _default_state())
    context.state.entities.put(entity_id, IMPRISONMENT, _default_prison())
    context.state.entities.put(entity_id, POSSESSION, _default_possession())


def reconcile_demonic_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        state.entities.put(
            entity_id,
            DEMONIC_STATE,
            state.entities.get(entity_id, DEMONIC_STATE) or _default_state(),
        )
        state.entities.put(
            entity_id,
            IMPRISONMENT,
            state.entities.get(entity_id, IMPRISONMENT) or _default_prison(),
        )
        state.entities.put(
            entity_id,
            POSSESSION,
            state.entities.get(entity_id, POSSESSION) or _default_possession(),
        )


def _enter_prison_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, EnterImprisonment):
        raise TypeError("命令类型错误")
    if command.actor_id != context.state.controlled_entity_id:
        raise ValueError("只能关押当前角色")
    if (
        not context.state.entities.exists(command.captor_id)
        or context.state.entities.get(command.captor_id, IDENTITY) is None
    ):
        raise ValueError("收押者不存在")
    if not 1 <= command.years <= 1000:
        raise ValueError("刑期必须为1至1000年")
    prison = context.state.entities.require(command.actor_id, IMPRISONMENT)
    if prison.get("active"):
        raise ValueError("当前角色已经被关押")
    existing = context.state.relations.find(
        target_id=command.actor_id, kind=PRISONER
    )
    if existing:
        raise ValueError("当前角色已经受他人拘押")
    edge = context.state.relations.add(
        source_id=command.captor_id,
        target_id=command.actor_id,
        kind=PRISONER,
        created_year=context.state.clock.year,
        metadata={"status": "imprisoned", "facility": command.facility},
    )
    prison["active"] = {
        "captor_id": command.captor_id,
        "relation_id": edge.relation_id,
        "name": command.name[:60] or "势力大牢",
        "facility": command.facility,
        "remaining_years": command.years,
        "sentence_years": command.years,
        "captured_year": context.state.clock.year,
        "hostility": max(0.0, float(command.hostility)),
        "hostility_reduction_per_year": max(
            4.0, max(0.0, float(command.hostility)) / command.years
        ),
    }
    context.state.entities.put(command.actor_id, IMPRISONMENT, prison)
    for party_edge in list(context.state.relations.find(
        source_id=command.actor_id, kind=PARTY_MEMBER
    )):
        _end_edge(context, party_edge, "leader_imprisoned")
    context.emit(
        "demonic.prison.entered",
        source="demonic",
        scope=EventScope.entity(command.actor_id),
        payload={"actor_id": command.actor_id, **dict(prison["active"])},
    )


def _release_prison(
    context: SimulationContext, actor_id: str, reason: str,
) -> None:
    component = context.state.entities.require(actor_id, IMPRISONMENT)
    active = dict(component.get("active") or {})
    relation_id = str(active.get("relation_id", ""))
    edge = context.state.relations.edges.get(relation_id)
    if edge is not None and edge.active:
        _end_edge(context, edge, reason)
    component["active"] = None
    context.state.entities.put(actor_id, IMPRISONMENT, component)
    context.emit(
        "demonic.prison.released",
        source="demonic",
        scope=EventScope.entity(actor_id),
        payload={"actor_id": actor_id, "reason": reason},
    )


def _prison_action_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PrisonAction):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能控制当前角色")
        if _pending_story(context.state, command.actor_id):
            raise ValueError("请先处理当前事件")
        component = context.state.entities.require(command.actor_id, IMPRISONMENT)
        active = dict(component.get("active") or {})
        if not active:
            raise ValueError("你当前并未被关押")
        if command.action == "escape":
            if active.get("facility") == "faction_prison":
                raise ValueError("势力监狱暂不开放越狱")
            own = float(combat_snapshot(
                context.state, definitions, command.actor_id
            )["power"])
            cultivation = context.state.entities.require(
                command.actor_id, CULTIVATION
            )
            realm = definitions.realm(str(cultivation["realm_id"]))
            guard = realm.base_power * (
                1 + float(active.get("hostility", 0.0)) / 160
            )
            chance = max(0.05, min(0.78, 0.18 + own / max(1.0, guard) * 0.28))
            active["hostility"] = float(active.get("hostility", 0.0)) + 12.0
            if context.rng.random() < chance:
                _release_prison(context, command.actor_id, "escaped")
                result = "escaped"
            else:
                condition = context.state.entities.require(
                    command.actor_id, CONDITION
                )
                condition["hp_ratio"] = max(
                    0.0,
                    float(condition["hp_ratio"])
                    - context.rng.uniform(0.25, 0.45),
                )
                context.state.entities.put(
                    command.actor_id, CONDITION, condition
                )
                if condition["hp_ratio"] <= 0:
                    context.emit(
                        "character.lethal_hazard",
                        source="demonic",
                        scope=EventScope.entity(command.actor_id),
                        payload={
                            "entity_id": command.actor_id,
                            "reason": "越狱失败，被狱卒当场格杀",
                        },
                    )
                    result = "dead"
                else:
                    component["active"] = active
                    context.state.entities.put(
                        command.actor_id, IMPRISONMENT, component
                    )
                    result = "failed"
            component = context.state.entities.require(
                command.actor_id, IMPRISONMENT
            )
            component["last_result"] = {
                "action": command.action, "result": result, "chance": chance,
                "year": context.state.clock.year,
            }
            context.state.entities.put(
                command.actor_id, IMPRISONMENT, component
            )
            return
        if command.action not in {"endure", "wait", "cultivate"}:
            raise ValueError("未知牢狱行动")
        if (
            command.action in {"wait", "cultivate"}
            and active.get("facility") != "faction_prison"
        ):
            raise ValueError("当前牢狱不允许此项行动")
        token = begin_action(
            context,
            actor_id=command.actor_id,
            action=f"prison_{command.action}",
            years=1,
            source="demonic.prison",
        )
        TimeService.advance(context, 1, source="demonic.prison")
        life = context.state.entities.require(command.actor_id, LIFE)
        if not bool(life.get("alive")):
            return
        component = context.state.entities.require(command.actor_id, IMPRISONMENT)
        active = dict(component.get("active") or {})
        condition = context.state.entities.require(command.actor_id, CONDITION)
        degraded = False
        gain = 0.0
        if command.action == "endure":
            condition["hp_ratio"] = max(
                0.01,
                float(condition["hp_ratio"]) - context.rng.uniform(0.08, 0.18),
            )
            condition["mp_ratio"] = max(
                0.0,
                float(condition["mp_ratio"]) - context.rng.uniform(0.06, 0.14),
            )
            cultivation = context.state.entities.require(
                command.actor_id, CULTIVATION
            )
            if (
                definitions.realm_index(str(cultivation["realm_id"])) < 9
                and context.rng.random()
                < float(definitions.systems["faction_conflict"].get(
                    "prison_breakthrough_loss_chance", 0.08
                ))
            ):
                realm_index = definitions.realm_index(str(cultivation["realm_id"]))
                if int(cultivation["layer"]) > 1:
                    cultivation["layer"] = int(cultivation["layer"]) - 1
                elif realm_index > 1:
                    cultivation["realm_id"] = definitions.realms[realm_index - 1].id
                    cultivation["layer"] = definitions.realms[realm_index - 1].layers
                cultivation["opportunity"] = 0.0
                context.state.entities.put(
                    command.actor_id, CULTIVATION, cultivation
                )
                degraded = True
        elif command.action == "cultivate":
            cultivation = context.state.entities.require(
                command.actor_id, CULTIVATION
            )
            realm = definitions.realm(str(cultivation["realm_id"]))
            gain = max(0.2, realm.opportunity_base * 0.01)
            cultivation["opportunity"] = float(
                cultivation.get("opportunity", 0.0)
            ) + gain
            condition["mp_ratio"] = max(
                0.0, float(condition["mp_ratio"]) - 0.04
            )
            context.state.entities.put(
                command.actor_id, CULTIVATION, cultivation
            )
        context.state.entities.put(command.actor_id, CONDITION, condition)
        active["remaining_years"] = max(
            0, int(active.get("remaining_years", 1)) - 1
        )
        active["hostility"] = max(
            0.0,
            float(active.get("hostility", 0.0))
            - float(active.get("hostility_reduction_per_year", 4.0)),
        )
        released = active["remaining_years"] <= 0
        component["active"] = active
        result = (
            "released" if released else "degraded" if degraded
            else "cultivated" if command.action == "cultivate" else command.action
        )
        component["last_result"] = {
            "action": command.action, "result": result, "gain": gain,
            "year": context.state.clock.year,
        }
        context.state.entities.put(command.actor_id, IMPRISONMENT, component)
        if released:
            _release_prison(context, command.actor_id, "sentence_completed")
        complete_action(
            context, actor_id=command.actor_id, token=token,
            result=result, metadata={"opportunity_gain": gain},
        )

    return handler


def _close_incompatible_relations(
    context: SimulationContext, target_id: str, reason: str,
) -> None:
    for edge in list(context.state.relations.involving(target_id)):
        if edge.kind in {PUPPET_CONTROL, SOUL_CONTROL}:
            continue
        _end_edge(context, edge, reason)


def _create_puppet(
    context: SimulationContext,
    definitions: GameDefinitions,
    owner_id: str,
    *,
    kind: str,
    target_id: str | None = None,
    name: str = "玄铁机关傀儡",
) -> str:
    if len(_puppet_edges(context.state, owner_id)) >= puppet_capacity(
        context.state, owner_id
    ):
        raise ValueError("神识可控傀儡数量已经达到上限")
    if kind not in PUPPET_NAMES:
        raise ValueError("未知傀儡类型")
    if target_id is None:
        puppet_id = context.state.entities.create("puppet")
        owner_cultivation = context.state.entities.require(owner_id, CULTIVATION)
        owner_snapshot = combat_snapshot(context.state, definitions, owner_id)
        realm_index = max(
            1,
            definitions.realm_index(str(owner_cultivation["realm_id"])) - 1,
        )
        layer = 1
        original_power = max(20.0, float(owner_snapshot["power"]) * 0.35)
        technique_id = None
    else:
        puppet_id = target_id
        target_cultivation = context.state.entities.require(target_id, CULTIVATION)
        realm_index = definitions.realm_index(str(target_cultivation["realm_id"]))
        layer = int(target_cultivation["layer"])
        original_power = float(
            combat_snapshot(context.state, definitions, target_id)["power"]
        )
        target_practice = context.state.entities.require(target_id, PRACTICE)
        technique_id = target_practice.get("main_technique_id")
        name = str(context.state.entities.require(target_id, IDENTITY)["name"])
    inherited = float(
        _rules(definitions).get(
            "corpse_power_inheritance" if kind == "corpse"
            else "living_power_inheritance", 1.0,
        )
    ) if kind != "mechanical" else 1.0
    component = {
        "name": name,
        "kind": kind,
        "realm_index": realm_index,
        "layer": layer,
        "combat_power": round(original_power * inherited, 4),
        "original_power": round(original_power, 4),
        "main_technique_id": technique_id,
        "control": 100.0 if kind != "living" else 55.0,
        "cultivation_progress": 0.0,
        "breakthrough_bonus": 0.0,
        "created_year": context.state.clock.year,
        "last_infusion_unit": -1,
        "durability": 100.0,
        "corpse_integrity": 100.0,
        "active": True,
        "source_character_id": target_id,
    }
    context.state.entities.put(puppet_id, PUPPET, component)
    context.state.relations.add(
        source_id=owner_id,
        target_id=puppet_id,
        kind=PUPPET_CONTROL,
        created_year=context.state.clock.year,
        metadata={"kind": kind},
    )
    return puppet_id


def _convert_captive(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    target_id: str,
    kind: str,
) -> dict[str, Any]:
    if not _is_demonic(context.state, actor_id):
        raise ValueError("只有魔修能够炼尸或种下活傀标记")
    edge = next(iter(context.state.relations.find(
        source_id=actor_id, target_id=target_id, kind=PRISONER
    )), None)
    if edge is None:
        raise ValueError("目标不是你的俘虏")
    own = combat_snapshot(context.state, definitions, actor_id)
    target = combat_snapshot(context.state, definitions, target_id)
    realm_gap = int(own["realm_index"]) - int(target["realm_index"])
    ratio = float(own["power"]) / max(1.0, float(target["power"]))
    affinity = relationship_affinity(context.state, target_id, actor_id)
    base = float(_rules(definitions)[
        "corpse_success_base" if kind == "corpse" else "living_success_base"
    ])
    chance = base + realm_gap * (0.07 if kind == "corpse" else 0.06)
    chance += math.log2(max(0.25, ratio)) * (0.06 if kind == "corpse" else 0.05)
    if kind == "living":
        chance += affinity / 300
    chance = max(0.05, min(0.95, chance))
    if context.rng.random() >= chance:
        set_relationship_affinity(context.state, target_id, actor_id, affinity - 15)
        if kind == "corpse":
            _end_edge(context, edge, "corpse_refining_failed")
            context.emit(
                "character.lethal_hazard",
                source="demonic",
                scope=EventScope.entity(target_id),
                payload={"entity_id": target_id, "reason": "炼尸失败，形神俱灭"},
            )
            return {"result": "destroyed", "chance": chance}
        return {"result": "resisted", "chance": chance}
    _end_edge(context, edge, f"converted_to_{kind}_puppet")
    _close_incompatible_relations(context, target_id, f"converted_to_{kind}_puppet")
    if kind == "corpse":
        context.emit(
            "character.lethal_hazard",
            source="demonic",
            scope=EventScope.entity(target_id),
            payload={"entity_id": target_id, "reason": "被炼为炼尸"},
        )
    puppet_id = _create_puppet(
        context, definitions, actor_id, kind=kind, target_id=target_id
    )
    return {"result": "created", "chance": chance, "puppet_id": puppet_id}


def convert_relationship_to_corpse(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    target_id: str,
) -> dict[str, Any]:
    if not context.state.relations.find(
        source_id=actor_id, target_id=target_id, kind="concubine"
    ):
        raise ValueError("目标不是你的侍妾")
    if len(_puppet_edges(context.state, actor_id)) >= puppet_capacity(
        context.state, actor_id
    ):
        raise ValueError("神识可控傀儡数量已经达到上限")
    captive = context.state.relations.add(
        source_id=actor_id,
        target_id=target_id,
        kind=PRISONER,
        created_year=context.state.clock.year,
        metadata={"status": "conversion", "source": "concubine"},
    )
    try:
        return _convert_captive(
            context, definitions, actor_id, target_id, "corpse"
        )
    except Exception:
        if captive.active:
            current = context.state.relations.edges.get(captive.relation_id)
            if current and current.active:
                _end_edge(context, current, "conversion_rolled_back")
        raise


def _possess(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    target_id: str,
    *,
    post_battle: bool,
) -> dict[str, Any]:
    ghost = context.state.entities.get(actor_id, GHOST_SOUL)
    possession = context.state.entities.require(actor_id, POSSESSION)
    if ghost is None or possession.get("host") is not None:
        raise ValueError("只有未寄身的鬼修可以夺舍")
    actor_cultivation = context.state.entities.require(actor_id, CULTIVATION)
    target_cultivation = context.state.entities.require(target_id, CULTIVATION)
    actor_rank = definitions.realm_index(str(actor_cultivation["realm_id"]))
    target_rank = definitions.realm_index(str(target_cultivation["realm_id"]))
    if target_rank > actor_rank:
        raise ValueError("不能夺舍境界高于自身的目标")
    identity = context.state.entities.require(target_id, IDENTITY)
    if str(identity.get("race", "human")) not in {"human", "demon", "immortal"}:
        raise ValueError("目标并非可夺舍的人形生灵")
    if int(possession.get("count", 0)) >= 1:
        raise ValueError("本魂最多成功夺舍一次")
    target_power = float(combat_snapshot(
        context.state, definitions, target_id
    )["power"])
    actor_power = float(combat_snapshot(
        context.state, definitions, actor_id
    )["power"])
    chance = 1.0 if post_battle else max(
        0.10,
        min(0.95, 0.55 + (actor_power - target_power) / (
            actor_power + target_power
        ) * 0.35),
    )
    if not post_battle and context.rng.random() >= chance:
        context.emit(
            "character.lethal_hazard",
            source="demonic",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "reason": "夺舍失败，神魂反噬而灭"},
        )
        return {"result": "dead", "chance": chance}
    actor_identity = context.state.entities.require(actor_id, IDENTITY)
    actor_life = context.state.entities.require(actor_id, LIFE)
    actor_practice = context.state.entities.require(actor_id, PRACTICE)
    possession["core"] = {
        "identity": actor_identity,
        "life": actor_life,
        "cultivation": actor_cultivation,
        "practice": actor_practice,
    }
    target_life = context.state.entities.require(target_id, LIFE)
    target_practice = context.state.entities.require(target_id, PRACTICE)
    target_age = context.state.clock.year - int(target_life["birth_year"])
    original_name = str(actor_identity["name"])
    actor_identity.update(
        name=f"{identity['name']}（{original_name}）",
        gender=identity["gender"],
        race=identity["race"],
    )
    actor_life.update(
        alive=True,
        death_reason=None,
        birth_year=context.state.clock.year - target_age,
        lifespan=target_life.get("lifespan"),
    )
    possession["host"] = {
        "entity_id": target_id,
        "name": identity["name"],
        "entered_year": context.state.clock.year,
        "body_age": target_age,
        "lifespan": target_life.get("lifespan"),
    }
    possession["count"] = int(possession.get("count", 0)) + 1
    context.state.entities.put(actor_id, IDENTITY, actor_identity)
    context.state.entities.put(actor_id, LIFE, actor_life)
    context.state.entities.put(actor_id, CULTIVATION, target_cultivation)
    context.state.entities.put(actor_id, PRACTICE, target_practice)
    context.state.entities.put(actor_id, POSSESSION, possession)
    context.state.entities.put(
        actor_id, CONDITION, {"hp_ratio": 0.7, "mp_ratio": 0.7}
    )
    context.state.scheduler.cancel(
        lambda row: row.event_type == LIFESPAN_DUE
        and str(row.payload.get("entity_id", "")) == actor_id
    )
    if actor_life.get("lifespan") is not None:
        context.emit(
            "character.lifespan.changed",
            source="demonic",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id},
        )
    edge = next(iter(context.state.relations.find(
        source_id=actor_id, target_id=target_id, kind=PRISONER
    )), None)
    if edge:
        _end_edge(context, edge, "possessed")
    context.emit(
        "character.lethal_hazard",
        source="demonic",
        scope=EventScope.entity(target_id),
        payload={"entity_id": target_id, "reason": "被鬼修夺舍，原神魂消散"},
    )
    state = context.state.entities.require(actor_id, DEMONIC_STATE)
    state["pending_post_battle_possession"] = None
    context.state.entities.put(actor_id, DEMONIC_STATE, state)
    return {"result": "possessed", "chance": chance, "host_id": target_id}


def _captive_action_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, CaptiveAction):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        edge = next(iter(context.state.relations.find(
            source_id=command.actor_id,
            target_id=command.target_id,
            kind=PRISONER,
        )), None)
        if edge is None:
            raise ValueError("目标俘虏不存在")
        if command.action == "release":
            _end_edge(context, edge, "released")
            result = {"result": "released"}
        elif command.action == "torture":
            affinity = set_relationship_affinity(
                context.state,
                command.target_id,
                command.actor_id,
                relationship_affinity(
                    context.state, command.target_id, command.actor_id
                ) - 12,
            )
            story = context.state.entities.require(command.actor_id, STORY_STATE)
            attributes = dict(story.get("attributes", {}))
            attributes["fame"] = float(attributes.get("fame", 0.0)) + 2
            story["attributes"] = attributes
            context.state.entities.put(command.actor_id, STORY_STATE, story)
            result = {"result": "tortured", "affinity": affinity}
        elif command.action in {"corpse", "living"}:
            result = _convert_captive(
                context, definitions, command.actor_id,
                command.target_id, command.action,
            )
        elif command.action == "possess":
            result = _possess(
                context, definitions, command.actor_id,
                command.target_id, post_battle=False,
            )
        else:
            raise ValueError("未知俘虏处置方式")
        context.emit(
            "demonic.captive.resolved",
            source="demonic",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id,
                "target_id": command.target_id,
                "action": command.action,
                **result,
            },
        )

    return handler


def _grant_art_experience(
    state: WorldState, actor_id: str, art_id: str, amount: float,
) -> None:
    field = state.entities.require(actor_id, SPIRIT_FIELD)
    experience = dict(field.get("art_experience", {}))
    experience[art_id] = float(experience.get(art_id, 0.0)) + amount
    field["art_experience"] = experience
    state.entities.put(actor_id, SPIRIT_FIELD, field)


def _craft_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, CraftMechanicalPuppet):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        recipe = dict(_rules(definitions)["mechanical_recipe"])
        if any(
            inventory_quantity(
                context.state, command.actor_id, item_id, spendable=True
            ) < int(quantity)
            for item_id, quantity in recipe.items()
        ):
            raise ValueError("机关傀儡需要下品灵石 ×25 与青锋灵剑 ×1")
        if len(_puppet_edges(context.state, command.actor_id)) >= puppet_capacity(
            context.state, command.actor_id
        ):
            raise ValueError("神识可控傀儡数量已经达到上限")
        for item_id, quantity in recipe.items():
            change_inventory_item(
                context, definitions, command.actor_id,
                item_id, -int(quantity), "craft_mechanical_puppet",
            )
        puppet_id = _create_puppet(
            context, definitions, command.actor_id, kind="mechanical"
        )
        _grant_art_experience(
            context.state, command.actor_id, "refining", 20
        )
        _grant_art_experience(
            context.state, command.actor_id, "formation", 8
        )
        _grant_art_experience(
            context.state, command.actor_id, "spirit_control", 10
        )
        context.emit(
            "demonic.puppet.crafted",
            source="demonic",
            scope=EventScope.entity(command.actor_id),
            payload={"actor_id": command.actor_id, "puppet_id": puppet_id},
        )

    return handler


def _try_puppet_breakthrough(
    context: SimulationContext,
    definitions: GameDefinitions,
    component: dict[str, Any],
) -> str:
    kind = str(component["kind"])
    realm_index = int(component["realm_index"])
    if kind == "mechanical" or realm_index >= len(definitions.realms) - 1:
        return "none"
    required = definitions.realms[realm_index].opportunity_base * 0.35
    if float(component.get("cultivation_progress", 0.0)) < required:
        return "none"
    chance = min(
        0.90,
        float(_rules(definitions)["puppet_breakthrough_base"][kind])
        + float(component.get("breakthrough_bonus", 0.0)),
    )
    component["breakthrough_bonus"] = 0.0
    if context.rng.random() >= chance:
        component["cultivation_progress"] = required * 0.5
        return "failed"
    component["cultivation_progress"] = 0.0
    if int(component["layer"]) >= definitions.realms[realm_index].layers:
        component["realm_index"] = realm_index + 1
        component["layer"] = 1
    else:
        component["layer"] = int(component["layer"]) + 1
    component["combat_power"] = float(component["combat_power"]) * 1.18
    if kind == "living":
        component["control"] = max(0.0, float(component["control"]) - 8)
    return "succeeded"


def _create_foreign_soul(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    puppet_id: str,
    component: dict[str, Any],
) -> str:
    kind = str(component["kind"])
    per_realm = float(_rules(definitions)["devour_bonus_per_realm"][kind])
    actor_power = float(combat_snapshot(
        context.state, definitions, actor_id
    )["power"])
    potential = per_realm * max(1, int(component["realm_index"])) * (
        1 + min(
            1.0,
            float(component["combat_power"]) / max(1.0, actor_power),
        ) * 0.3
    ) + float(_rules(definitions).get("devour_bonus_flat_increase", 0.05))
    immediate = potential * 0.4
    state = context.state.entities.require(actor_id, DEMONIC_STATE)
    state["devouring_breakthrough_bonus"] = min(
        float(_rules(definitions)["max_devour_bonus"]),
        float(state.get("devouring_breakthrough_bonus", 0.0)) + immediate,
    )
    context.state.entities.put(actor_id, DEMONIC_STATE, state)
    soul_id = context.state.entities.create("soul")
    context.state.entities.put(soul_id, FOREIGN_SOUL, {
        "name": component["name"],
        "origin_puppet_id": puppet_id,
        "realm_index": int(component["realm_index"]),
        "strength": round(max(0.5, potential * 30), 4),
        "combat_power": float(component["combat_power"]),
        "progress": 0.0,
        "required": 100.0,
        "remaining_bonus": max(0.0, potential - immediate),
        "refined": False,
        "last_refine_unit": -1,
    })
    context.state.relations.add(
        source_id=actor_id,
        target_id=soul_id,
        kind=SOUL_CONTROL,
        created_year=context.state.clock.year,
        metadata={},
    )
    return soul_id


def _puppet_action_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PuppetAction):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        edge = _puppet_edge(context.state, command.actor_id, command.puppet_id)
        if edge is None:
            raise ValueError("目标傀儡不存在")
        component = context.state.entities.require(command.puppet_id, PUPPET)
        if not bool(component.get("active", True)):
            raise ValueError("目标傀儡已经失效")
        result: dict[str, Any]
        if command.action == "infuse":
            if component["kind"] == "mechanical":
                raise ValueError("机关傀儡不能通过灌注气修炼")
            unit = _action_unit(context.state, command.actor_id)
            if int(component.get("last_infusion_unit", -1)) == unit:
                raise ValueError("本行动单位已经为该傀儡灌注过气")
            condition = context.state.entities.require(
                command.actor_id, CONDITION
            )
            cost = float(_rules(definitions)["infusion_mp_ratio"])
            if float(condition["mp_ratio"]) < cost:
                raise ValueError("当前 MP 不足以完成灌注")
            technique_id = component.get("main_technique_id")
            if not technique_id:
                practice = context.state.entities.require(
                    command.actor_id, PRACTICE
                )
                technique_id = practice.get("main_technique_id")
            technique = definitions.techniques.get(str(technique_id or ""))
            if technique is None:
                raise ValueError("该傀儡没有可承载灌注的主修功法")
            location = context.state.entities.require(command.actor_id, LOCATION)
            local = definitions.worlds[str(location["world_id"])].locations[
                str(location["location_id"])
            ]
            efficiency = sum(
                float(weight) * float(local.qi_gain_efficiencies.get(source, 0))
                for source, weight in technique.sources.items()
            )
            gain = float(_rules(definitions)["infusion_base"]) * efficiency * (
                1 + technique.grade * 0.08
            )
            condition["mp_ratio"] = float(condition["mp_ratio"]) - cost
            component["cultivation_progress"] = float(
                component.get("cultivation_progress", 0.0)
            ) + gain
            component["combat_power"] = float(component["combat_power"]) * (
                1 + min(0.08, gain / 1200)
            )
            component["last_infusion_unit"] = unit
            context.state.entities.put(command.actor_id, CONDITION, condition)
            result = {
                "result": "infused", "gain": gain,
                "breakthrough": _try_puppet_breakthrough(
                    context, definitions, component
                ),
            }
        elif command.action == "pill":
            item = definitions.items.get(command.content_id)
            if (
                item is None or "pill" not in item.tags
                or inventory_quantity(
                    context.state, command.actor_id,
                    command.content_id, spendable=True,
                ) < 1
            ):
                raise ValueError("需要选择并持有一枚丹药")
            change_inventory_item(
                context, definitions, command.actor_id,
                command.content_id, -1, "feed_puppet_pill",
            )
            gain = float(_rules(definitions)["pill_breakthrough_bonus"])
            component["breakthrough_bonus"] = min(
                0.35,
                float(component.get("breakthrough_bonus", 0.0)) + gain,
            )
            result = {"result": "pill_fed", "gain": gain}
        elif command.action == "technique":
            if component["kind"] != "living":
                raise ValueError("只有活傀能够更换功法")
            practice = context.state.entities.require(
                command.actor_id, PRACTICE
            )
            technique = definitions.techniques.get(command.content_id)
            if (
                technique is None or technique.category != "spiritual"
                or command.content_id not in practice.get("known_techniques", [])
            ):
                raise ValueError("需要选择已掌握的修仙功法")
            component["main_technique_id"] = command.content_id
            component["combat_power"] = float(
                component["combat_power"]
            ) + technique.combat_bonus * 0.10
            result = {"result": "technique_changed"}
        elif command.action == "reinforce_control":
            if not _is_demonic(context.state, command.actor_id) or component["kind"] != "living":
                raise ValueError("只有魔修能够加固活傀印记")
            condition = context.state.entities.require(
                command.actor_id, CONDITION
            )
            cost = float(_rules(definitions)["control_reinforce_mp_ratio"])
            if float(condition["mp_ratio"]) < cost:
                raise ValueError("当前 MP 不足以加固活傀印记")
            before = float(component.get("control", 0.0))
            rank = int(context.state.entities.require(
                command.actor_id, DIVINE_SENSE
            ).get("rank", 0))
            gain = float(_rules(definitions)["control_reinforce_base"]) * (
                1 + max(0, rank - 1) * 0.03
            )
            component["control"] = min(100.0, before + gain)
            condition["mp_ratio"] = float(condition["mp_ratio"]) - cost
            context.state.entities.put(command.actor_id, CONDITION, condition)
            _grant_art_experience(
                context.state, command.actor_id, "spirit_control", 8
            )
            result = {
                "result": "control_reinforced",
                "gain": float(component["control"]) - before,
            }
        elif command.action == "devour":
            if not _is_demonic(context.state, command.actor_id) or component["kind"] == "mechanical":
                raise ValueError("只有魔修能够吞噬炼尸或活傀")
            soul_id = _create_foreign_soul(
                context, definitions, command.actor_id,
                command.puppet_id, component,
            )
            _end_edge(context, edge, "devoured")
            component["active"] = False
            result = {"result": "devoured", "soul_id": soul_id}
        elif command.action == "dismiss":
            _end_edge(context, edge, "dismissed")
            component["active"] = False
            result = {"result": "dismissed"}
        else:
            raise ValueError("未知傀儡操作")
        context.state.entities.put(command.puppet_id, PUPPET, component)
        context.emit(
            "demonic.puppet.managed",
            source="demonic",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id,
                "puppet_id": command.puppet_id,
                "action": command.action,
                **result,
            },
        )

    return handler


def _soul_refine_gain(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> float:
    sense = state.entities.require(actor_id, DIVINE_SENSE)
    technique = definitions.techniques.get(str(sense.get("technique_id") or ""))
    location = state.entities.require(actor_id, LOCATION)
    local = definitions.worlds[str(location["world_id"])].locations[
        str(location["location_id"])
    ]
    multiplier = 0.5
    if technique:
        environment = sum(
            float(weight) * float(local.qi_gain_efficiencies.get(source, 0.0))
            for source, weight in technique.sources.items()
        )
        multiplier = (1 + technique.divine_sense_bonus * technique.scale) * environment
    return float(_rules(definitions)["soul_refine_progress"]) * multiplier


def _complete_soul(
    state: WorldState,
    definitions: GameDefinitions,
    actor_id: str,
    soul: dict[str, Any],
) -> None:
    if soul.get("refined"):
        return
    soul["progress"] = float(soul.get("required", 100.0))
    soul["refined"] = True
    component = state.entities.require(actor_id, DEMONIC_STATE)
    component["devouring_breakthrough_bonus"] = min(
        float(_rules(definitions)["max_devour_bonus"]),
        float(component.get("devouring_breakthrough_bonus", 0.0))
        + float(soul.get("remaining_bonus", 0.0)),
    )
    state.entities.put(actor_id, DEMONIC_STATE, component)


def _unrefined_souls(
    state: WorldState, actor_id: str,
) -> list[tuple[RelationEdge, dict[str, Any]]]:
    rows = []
    for edge in _soul_edges(state, actor_id):
        soul = state.entities.require(edge.target_id, FOREIGN_SOUL)
        if not bool(soul.get("refined")):
            rows.append((edge, soul))
    return rows


def _refine_soul_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RefineForeignSoul):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        if not _is_demonic(context.state, command.actor_id):
            raise ValueError("只有魔修能够炼化外来元神")
        souls = _unrefined_souls(context.state, command.actor_id)
        if not souls:
            raise ValueError("当前没有尚未炼化的外来元神")
        gain = _soul_refine_gain(context.state, definitions, command.actor_id)
        if command.secluded:
            remaining = sum(
                max(0.0, float(soul["required"]) - float(soul["progress"]))
                for _, soul in souls
            )
            multiplier = float(
                _rules(definitions).get("soul_seclusion_time_multiplier", 1.2)
            )
            years = max(1, math.ceil(remaining * multiplier / max(0.01, gain)))
            token = begin_action(
                context, actor_id=command.actor_id,
                action="secluded_refine_souls", years=years,
                source="demonic.soul_seclusion",
            )
            start_year = context.state.clock.year
            yearly_progress = gain / multiplier
            for offset in range(1, years + 1):
                context.state.scheduler.schedule(
                    due_year=start_year + offset,
                    event_type=SOUL_SECLUSION_TICK,
                    source="demonic",
                    scope=EventScope.entity(command.actor_id),
                    payload={
                        "actor_id": command.actor_id,
                        "action_token": token,
                        "yearly_progress": yearly_progress,
                        "final": offset == years,
                    },
                )
            TimeService.advance(
                context, years, source="demonic.soul_seclusion"
            )
            return
        edge, soul = souls[0]
        unit = _action_unit(context.state, command.actor_id)
        if int(soul.get("last_refine_unit", -1)) == unit:
            raise ValueError("本行动单位已经炼化过该元神")
        cultivation = context.state.entities.require(
            command.actor_id, CULTIVATION
        )
        realm = definitions.realm(str(cultivation["realm_id"]))
        cost = max(1.0, realm.opportunity_base * 0.04)
        condition = context.state.entities.require(command.actor_id, CONDITION)
        if (
            float(cultivation.get("opportunity", 0.0)) < cost
            or float(condition["mp_ratio"]) < 0.10
        ):
            raise ValueError("炼化元神需要足够机缘与 MP")
        cultivation["opportunity"] = float(cultivation["opportunity"]) - cost
        condition["mp_ratio"] = float(condition["mp_ratio"]) - 0.10
        soul["progress"] = min(
            float(soul["required"]), float(soul["progress"]) + gain
        )
        soul["last_refine_unit"] = unit
        if soul["progress"] >= float(soul["required"]):
            _complete_soul(
                context.state, definitions, command.actor_id, soul
            )
        context.state.entities.put(command.actor_id, CULTIVATION, cultivation)
        context.state.entities.put(command.actor_id, CONDITION, condition)
        context.state.entities.put(edge.target_id, FOREIGN_SOUL, soul)
        context.emit(
            "demonic.soul.refined",
            source="demonic",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id,
                "soul_id": edge.target_id,
                "progress": soul["progress"],
                "completed": soul["refined"],
            },
        )

    return handler


def _on_soul_seclusion_tick(
    definitions: GameDefinitions,
):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        runtime = context.state.entities.require(actor_id, ACTION_RUNTIME)
        active = runtime.get("active")
        token = str(event.payload["action_token"])
        if not isinstance(active, dict) or active.get("token") != token:
            return
        if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
            return
        budget = max(0.0, float(event.payload["yearly_progress"]))
        completed = 0
        for edge, soul in _unrefined_souls(context.state, actor_id):
            if budget <= 0:
                break
            applied = min(
                max(0.0, float(soul["required"]) - float(soul["progress"])),
                budget,
            )
            soul["progress"] = float(soul["progress"]) + applied
            soul["last_refine_unit"] = _action_unit(context.state, actor_id)
            budget -= applied
            if soul["progress"] >= float(soul["required"]):
                _complete_soul(context.state, definitions, actor_id, soul)
                completed += 1
            context.state.entities.put(edge.target_id, FOREIGN_SOUL, soul)
        context.emit(
            "demonic.soul.seclusion.progressed",
            source="demonic",
            scope=EventScope.entity(actor_id),
            payload={
                "actor_id": actor_id,
                "action_token": token,
                "souls_completed": completed,
            },
        )
        if bool(event.payload.get("final")):
            total_refined = sum(
                1
                for edge in _soul_edges(context.state, actor_id)
                if bool(context.state.entities.require(
                    edge.target_id, FOREIGN_SOUL
                ).get("refined"))
            )
            complete_action(
                context,
                actor_id=actor_id,
                token=token,
                metadata={"souls_refined": total_refined},
            )

    return handler


def _post_battle_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PostBattlePossession):
            raise TypeError("命令类型错误")
        state = context.state.entities.require(command.actor_id, DEMONIC_STATE)
        pending = dict(state.get("pending_post_battle_possession") or {})
        if bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("当前没有可结算的战陨夺舍")
        if command.target_id not in set(map(str, pending.get("candidate_ids", []))):
            raise ValueError("该俘虏不在本次战陨夺舍候选中")
        _possess(
            context, definitions, command.actor_id,
            command.target_id, post_battle=True,
        )

    return handler


def _on_combat_resolved(
    definitions: GameDefinitions,
):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload.get("attacker_id", ""))
        if (
            actor_id != context.state.controlled_entity_id
            or event.payload.get("objective") != "kill"
            or event.payload.get("outcome") != "defeat"
            or context.state.entities.get(actor_id, GHOST_SOUL) is None
        ):
            return
        possession = context.state.entities.require(actor_id, POSSESSION)
        if possession.get("host") is not None or int(possession.get("count", 0)) >= 1:
            return
        actor_cultivation = context.state.entities.require(actor_id, CULTIVATION)
        actor_rank = definitions.realm_index(str(actor_cultivation["realm_id"]))
        candidates = []
        for edge in context.state.relations.find(
            source_id=actor_id, kind=PRISONER
        ):
            identity = context.state.entities.require(edge.target_id, IDENTITY)
            cultivation = context.state.entities.require(edge.target_id, CULTIVATION)
            if (
                str(identity.get("race", "human")) in {"human", "demon", "immortal"}
                and definitions.realm_index(str(cultivation["realm_id"])) <= actor_rank
                and bool(context.state.entities.require(edge.target_id, LIFE).get("alive"))
            ):
                candidates.append(edge.target_id)
        if candidates:
            state = context.state.entities.require(actor_id, DEMONIC_STATE)
            state["pending_post_battle_possession"] = {
                "candidate_ids": candidates,
                "report_id": event.payload.get("report_id"),
                "year": context.state.clock.year,
            }
            context.state.entities.put(actor_id, DEMONIC_STATE, state)

    return handler


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        if elapsed <= 0:
            return
        actor_id = context.state.controlled_entity_id
        if actor_id is None or not bool(context.state.entities.require(
            actor_id, LIFE
        ).get("alive")):
            return
        rules = _rules(definitions)
        for _ in range(elapsed):
            cultivation = context.state.entities.require(actor_id, CULTIVATION)
            for edge in list(_puppet_edges(context.state, actor_id)):
                puppet = context.state.entities.require(edge.target_id, PUPPET)
                if not bool(puppet.get("active", True)):
                    continue
                kind = str(puppet["kind"])
                if kind in {"corpse", "living"}:
                    cultivation["opportunity"] = float(
                        cultivation.get("opportunity", 0.0)
                    ) + max(
                        0.1,
                        int(puppet["realm_index"])
                        * (0.16 if kind == "corpse" else 0.34),
                    )
                if kind != "living":
                    continue
                growth = 1 + int(puppet["realm_index"]) * 0.12
                puppet["control"] = max(
                    0.0,
                    float(puppet.get("control", 100.0))
                    - float(rules["living_control_loss_per_year"]) * growth,
                )
                if float(puppet["control"]) < 25:
                    chance = (25 - float(puppet["control"])) / 100 * 0.18
                    if context.rng.random() < chance:
                        _end_edge(context, edge, "living_puppet_revolt")
                        puppet["active"] = False
                        ratio = float(puppet["combat_power"]) / max(
                            1.0,
                            float(combat_snapshot(
                                context.state, definitions, actor_id
                            )["power"]),
                        )
                        if ratio > 1.15 and context.rng.random() < min(
                            0.85, 0.35 + (ratio - 1) * 0.25
                        ):
                            condition = context.state.entities.require(
                                actor_id, CONDITION
                            )
                            condition["hp_ratio"] = max(
                                0.0,
                                float(condition["hp_ratio"])
                                - min(0.9, 0.35 + ratio * 0.12),
                            )
                            context.state.entities.put(
                                actor_id, CONDITION, condition
                            )
                            if condition["hp_ratio"] <= 0:
                                context.emit(
                                    "character.lethal_hazard",
                                    source="demonic",
                                    scope=EventScope.entity(actor_id),
                                    payload={
                                        "entity_id": actor_id,
                                        "reason": "活傀挣脱控制后反杀主人",
                                    },
                                )
                        context.state.entities.put(edge.target_id, PUPPET, puppet)
                context.state.entities.put(edge.target_id, PUPPET, puppet)
            context.state.entities.put(actor_id, CULTIVATION, cultivation)
            souls = _unrefined_souls(context.state, actor_id)
            if souls:
                burden = sum(float(soul.get("strength", 1.0)) for _, soul in souls)
                if context.rng.random() < min(
                    0.65, float(rules["soul_backlash_base"]) * burden
                ):
                    condition = context.state.entities.require(actor_id, CONDITION)
                    condition["hp_ratio"] = max(
                        0.0,
                        float(condition["hp_ratio"])
                        - min(0.6, 0.06 + burden * 0.018),
                    )
                    cultivation = context.state.entities.require(
                        actor_id, CULTIVATION
                    )
                    cultivation["heart_demon"] = float(
                        cultivation.get("heart_demon", 0.0)
                    ) + burden * 0.5
                    context.state.entities.put(actor_id, CONDITION, condition)
                    context.state.entities.put(actor_id, CULTIVATION, cultivation)
                    if condition["hp_ratio"] <= 0:
                        context.emit(
                            "character.lethal_hazard",
                            source="demonic",
                            scope=EventScope.entity(actor_id),
                            payload={
                                "entity_id": actor_id,
                                "reason": "外来元神反客为主，撕碎识海",
                            },
                        )
            if context.time_halted:
                break

    return handler


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    if entity_id != context.state.controlled_entity_id:
        return
    state = context.state.entities.get(entity_id, DEMONIC_STATE) or {}
    if state.get("pending_post_battle_possession"):
        return
    context.state.scheduler.cancel(
        lambda scheduled: scheduled.event_type == SOUL_SECLUSION_TICK
        and str(scheduled.payload.get("actor_id", "")) == entity_id
    )
    prison = context.state.entities.get(entity_id, IMPRISONMENT) or {}
    if prison.get("active"):
        _release_prison(context, entity_id, "prisoner_died")


def _on_permanent_transition(
    context: SimulationContext, event: EventEnvelope,
) -> None:
    actor_id = str(event.payload["actor_id"])
    removed = []
    for edge in list(_puppet_edges(context.state, actor_id)):
        _end_edge(context, edge, "permanent_world_transition")
        puppet = context.state.entities.require(edge.target_id, PUPPET)
        puppet["active"] = False
        context.state.entities.put(edge.target_id, PUPPET, puppet)
        removed.append(edge.target_id)
    for edge in list(_soul_edges(context.state, actor_id)):
        _end_edge(context, edge, "permanent_world_transition")
        removed.append(edge.target_id)
    prison = context.state.entities.require(actor_id, IMPRISONMENT)
    if prison.get("active"):
        _release_prison(context, actor_id, "permanent_world_transition")
    context.emit(
        "world.transition.acknowledged",
        source="demonic",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": event.payload["transaction_id"],
            "actor_id": actor_id,
            "domain": "demonic",
            "released_ids": removed,
        },
    )


def demonic_combat_contributions(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> dict[str, Any]:
    intrinsic = 0.0
    living = []
    weights = _rules(definitions)["puppet_combat_contribution"]
    for edge in _puppet_edges(state, actor_id):
        puppet = state.entities.require(edge.target_id, PUPPET)
        if not bool(puppet.get("active", True)):
            continue
        kind = str(puppet["kind"])
        condition = (
            max(0.0, min(1.0, float(puppet.get("durability", 100.0)) / 100))
            if kind == "mechanical" else
            max(0.0, min(1.0, float(puppet.get("corpse_integrity", 100.0)) / 100))
            if kind == "corpse" else
            max(0.2, min(1.0, float(puppet.get("control", 100.0)) / 100))
        )
        contribution = float(puppet["combat_power"]) * float(weights[kind]) * condition
        if kind == "living":
            living.append({
                "entity_id": edge.target_id,
                "name": puppet["name"],
                "power": round(contribution, 4),
                "kind": kind,
            })
        else:
            intrinsic += contribution
    return {"intrinsic": round(intrinsic, 4), "living": living}


def consume_puppet_for_sale(
    context: SimulationContext, actor_id: str, puppet_id: str,
) -> dict[str, Any]:
    edge = _puppet_edge(context.state, actor_id, puppet_id)
    if edge is None:
        raise ValueError("黑市傀儡资产不存在")
    puppet = context.state.entities.require(puppet_id, PUPPET)
    if puppet.get("kind") == "living" or not bool(puppet.get("active", True)):
        raise ValueError("黑市只接收机关傀儡与炼尸，不接收活傀")
    _end_edge(context, edge, "sold_on_black_market")
    puppet["active"] = False
    context.state.entities.put(puppet_id, PUPPET, puppet)
    return {
        "id": puppet_id,
        "name": str(puppet["name"]),
        "kind": str(puppet["kind"]),
        "combat_power": float(puppet["combat_power"]),
    }


def demonic_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    owners: dict[str, int] = {}
    for edge in state.relations.find(kind=PUPPET_CONTROL):
        owners[edge.target_id] = owners.get(edge.target_id, 0) + 1
        puppet = state.entities.get(edge.target_id, PUPPET)
        if puppet is None or puppet.get("kind") not in PUPPET_NAMES:
            errors.append(f"傀儡关系引用非法傀儡：{edge.relation_id}")
    if any(count > 1 for count in owners.values()):
        errors.append("同一傀儡同时受多人控制")
    for edge in state.relations.find(kind=SOUL_CONTROL):
        if state.entities.get(edge.target_id, FOREIGN_SOUL) is None:
            errors.append(f"元神关系引用非法元神：{edge.relation_id}")
    for entity_id in state.entities.with_component(IDENTITY):
        prison = state.entities.get(entity_id, IMPRISONMENT)
        if prison is None:
            errors.append(f"角色 {entity_id} 缺少监禁组件")
        elif prison.get("active") and int(prison["active"].get("remaining_years", 0)) <= 0:
            errors.append(f"角色 {entity_id} 的有效刑期非法")
        elif prison.get("active"):
            relation_id = str(prison["active"].get("relation_id", ""))
            edge = state.relations.edges.get(relation_id)
            if (
                edge is None or not edge.active or edge.kind != PRISONER
                or edge.target_id != entity_id
            ):
                errors.append(f"角色 {entity_id} 的监禁关系缺失")
    return errors


def demonic_view(
    state: WorldState, definitions: GameDefinitions, actor_id: str | None = None,
) -> dict[str, Any]:
    actor_id = actor_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    puppets = []
    for edge in _puppet_edges(state, actor_id):
        puppet = state.entities.require(edge.target_id, PUPPET)
        if not bool(puppet.get("active", True)):
            continue
        kind = str(puppet["kind"])
        ratio = float(_rules(definitions)["puppet_combat_contribution"][kind])
        puppets.append({
            "id": edge.target_id,
            **dict(puppet),
            "type": kind,
            "type_name": PUPPET_NAMES[kind],
            "realm_name": definitions.realms[int(puppet["realm_index"])].name,
            "battle_contribution": round(
                float(puppet["combat_power"]) * ratio, 4
            ),
            "black_market_sellable": kind in {"mechanical", "corpse"},
        })
    prisoners = []
    for edge in state.relations.find(source_id=actor_id, kind=PRISONER):
        if state.entities.get(edge.target_id, IDENTITY) is None:
            continue
        cultivation = state.entities.require(edge.target_id, CULTIVATION)
        prisoners.append({
            **character_view(state, edge.target_id),
            "realm_id": cultivation["realm_id"],
            "realm_name": definitions.realm(str(cultivation["realm_id"])).name,
            "layer": cultivation["layer"],
            "combat_power": combat_snapshot(
                state, definitions, edge.target_id
            )["power"],
            "can_possess": state.entities.get(actor_id, GHOST_SOUL) is not None,
        })
    souls = []
    for edge in _soul_edges(state, actor_id):
        souls.append({"id": edge.target_id, **state.entities.require(
            edge.target_id, FOREIGN_SOUL
        )})
    demonic = state.entities.require(actor_id, DEMONIC_STATE)
    prison = state.entities.require(actor_id, IMPRISONMENT)
    return {
        "is_demonic": _is_demonic(state, actor_id),
        "capacity": puppet_capacity(state, actor_id),
        "used": len(puppets),
        "prisoners": prisoners,
        "puppets": puppets,
        "foreign_souls": souls,
        "breakthrough_bonus": float(
            demonic.get("devouring_breakthrough_bonus", 0.0)
        ),
        "imprisonment": prison.get("active"),
        "prison_last_result": prison.get("last_result"),
        "pending_post_battle_possession": demonic.get(
            "pending_post_battle_possession"
        ),
        "possession": state.entities.require(actor_id, POSSESSION),
        "mechanical_recipe": dict(_rules(definitions)["mechanical_recipe"]),
    }


def register_demonic_domain(
    bus: CommandBus, definitions: GameDefinitions,
) -> None:
    bus.register(EnterImprisonment, _enter_prison_handler)
    bus.register(PrisonAction, _prison_action_handler(definitions))
    bus.register(CaptiveAction, _captive_action_handler(definitions))
    bus.register(CraftMechanicalPuppet, _craft_handler(definitions))
    bus.register(PuppetAction, _puppet_action_handler(definitions))
    bus.register(RefineForeignSoul, _refine_soul_handler(definitions))
    bus.register(PostBattlePossession, _post_battle_handler(definitions))
    bus.add_guard(_imprisonment_guard)
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register(
        "combat.resolved", _on_combat_resolved(definitions)
    )
    bus.event_bus.register(
        "core.time.advanced", _on_time_advanced(definitions)
    )
    bus.event_bus.register(
        SOUL_SECLUSION_TICK, _on_soul_seclusion_tick(definitions)
    )
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register(
        "world.permanent_transition.requested", _on_permanent_transition
    )
