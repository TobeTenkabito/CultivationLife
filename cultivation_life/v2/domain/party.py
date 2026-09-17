from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import ACTION_RUNTIME
from .character import IDENTITY, LIFE, character_view
from .combat import combat_snapshot
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .relations import relationship_affinity, set_relationship_affinity
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, RelationEdge, WorldState


PARTY_MEMBER = "combat.party_member"


@dataclass(frozen=True, slots=True)
class ManageParty:
    actor_id: str
    target_id: str
    action: str


def _action_unit(state: WorldState, actor_id: str) -> int:
    runtime = state.entities.require(actor_id, ACTION_RUNTIME)
    return max(0, int(runtime.get("next_sequence", 1)) - 1)


def _party_edges(state: WorldState, actor_id: str) -> list[RelationEdge]:
    return list(state.relations.find(source_id=actor_id, kind=PARTY_MEMBER))


def _party_edge(
    state: WorldState, actor_id: str, target_id: str,
) -> RelationEdge | None:
    return next(
        (
            edge for edge in _party_edges(state, actor_id)
            if edge.target_id == target_id
        ),
        None,
    )


def _social_kind(state: WorldState, actor_id: str, target_id: str) -> str | None:
    for edge in state.relations.involving(actor_id):
        other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
        if other_id == target_id and edge.kind in {"friend", "dao_companion"}:
            return edge.kind
    return None


def _ensure_available(
    context: SimulationContext, actor_id: str, target_id: str,
) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能调整当前角色的队伍")
    if context.state.relations.find(target_id=actor_id, kind="combat_prisoner"):
        raise ValueError("服刑期间不能调整队伍")
    if not context.state.entities.exists(target_id) or target_id == actor_id:
        raise ValueError("同行目标不存在")
    for entity_id in (actor_id, target_id):
        if not bool(context.state.entities.require(entity_id, LIFE).get("alive")):
            raise ValueError("死亡角色不能结伴同行")
    actor_world = context.state.entities.require(actor_id, LOCATION).get("world_id")
    target_world = context.state.entities.require(target_id, LOCATION).get("world_id")
    if actor_world != target_world:
        raise ValueError("只能邀请同一界面的角色同行")


def _rank(
    state: WorldState, definitions: GameDefinitions, entity_id: str,
) -> tuple[int, int]:
    cultivation = state.entities.require(entity_id, CULTIVATION)
    return definitions.realm_index(str(cultivation["realm_id"])), int(cultivation["layer"])


def _crossing_eligible(
    state: WorldState, definitions: GameDefinitions, actor_id: str, target_id: str,
) -> bool:
    if _social_kind(state, actor_id, target_id) is None:
        return False
    actor_location = state.entities.require(actor_id, LOCATION)
    target_location = state.entities.require(target_id, LOCATION)
    return (
        actor_location.get("world_id") == target_location.get("world_id")
        and bool(state.entities.require(target_id, LIFE).get("alive"))
        and _rank(state, definitions, target_id)[0] >= _rank(state, definitions, actor_id)[0]
    )


def _manage_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ManageParty):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id, command.target_id)
        edge = _party_edge(context.state, command.actor_id, command.target_id)
        rules = dict(definitions.systems.get("party", {}))
        if command.action == "invite":
            if edge is not None:
                raise ValueError("此人已经在队伍中")
            if len(_party_edges(context.state, command.actor_id)) >= int(
                rules.get("max_companions", 2)
            ):
                raise ValueError("当前队伍已经满员")
            social_kind = _social_kind(
                context.state, command.actor_id, command.target_id
            )
            accepted = social_kind == "dao_companion"
            chance = 1.0 if accepted else 0.0
            if not accepted:
                actor_realm = _rank(
                    context.state, definitions, command.actor_id
                )[0]
                target_realm = _rank(
                    context.state, definitions, command.target_id
                )[0]
                target_affinity = relationship_affinity(
                    context.state, command.target_id, command.actor_id
                )
                confidence = 0.0
                if actor_realm >= target_realm:
                    confidence = min(
                        float(rules.get("lower_realm_bonus_cap", 0.22)),
                        float(rules.get("same_or_lower_realm_bonus", 0.12))
                        + max(0, actor_realm - target_realm)
                        * float(rules.get("lower_realm_bonus_per_gap", 0.04)),
                    )
                chance = max(0.02, min(
                    0.90,
                    float(rules.get("invite_base_chance", 0.45))
                    + confidence + target_affinity / 200
                    - max(0, target_realm - actor_realm) * 0.12,
                ))
                accepted = social_kind == "friend" or context.rng.random() < chance
            if accepted:
                edge = context.state.relations.add(
                    source_id=command.actor_id,
                    target_id=command.target_id,
                    kind=PARTY_MEMBER,
                    created_year=context.state.clock.year,
                    metadata={
                        "joined_year": context.state.clock.year,
                        "source": social_kind or "world",
                        "last_interaction_unit": -1,
                        "crossing_selected": False,
                    },
                )
                affinity = set_relationship_affinity(
                    context.state,
                    command.target_id,
                    command.actor_id,
                    relationship_affinity(
                        context.state, command.target_id, command.actor_id
                    ) + (0 if social_kind else 4),
                )
            else:
                affinity = set_relationship_affinity(
                    context.state,
                    command.target_id,
                    command.actor_id,
                    relationship_affinity(
                        context.state, command.target_id, command.actor_id
                    ) - 2,
                )
            payload = {
                "result": "joined" if accepted else "rejected",
                "chance": chance,
                "affinity": affinity,
            }
        elif command.action == "leave":
            if edge is None:
                raise ValueError("此人不在队伍中")
            closed = context.state.relations.end(
                edge.relation_id, ended_year=context.state.clock.year
            )
            metadata = dict(closed.metadata)
            metadata["end_reason"] = "left_party"
            context.state.relations.replace_metadata(closed.relation_id, metadata)
            payload = {"result": "left"}
        elif command.action == "interact":
            if edge is None:
                raise ValueError("只有当前队友可以进行同行互动")
            metadata = dict(edge.metadata)
            unit = _action_unit(context.state, command.actor_id)
            if int(metadata.get("last_interaction_unit", -1)) == unit:
                raise ValueError("本行动单位已经与这位队友交流过")
            gain_range = list(rules.get("interaction_affinity", [4, 8]))
            gain = context.rng.randint(int(gain_range[0]), int(gain_range[1]))
            affinity = set_relationship_affinity(
                context.state,
                command.target_id,
                command.actor_id,
                relationship_affinity(
                    context.state, command.target_id, command.actor_id
                ) + gain,
            )
            metadata["last_interaction_unit"] = unit
            context.state.relations.replace_metadata(edge.relation_id, metadata)
            payload = {
                "result": "interacted", "gain": gain, "affinity": affinity,
            }
        elif command.action in {"crossing_add", "crossing_remove"}:
            if edge is None:
                raise ValueError("只有当前队友可以随行飞升")
            if not _crossing_eligible(
                context.state, definitions, command.actor_id, command.target_id
            ):
                raise ValueError("此队友尚未达到可共同飞升的境界")
            metadata = dict(edge.metadata)
            metadata["crossing_selected"] = command.action == "crossing_add"
            context.state.relations.replace_metadata(edge.relation_id, metadata)
            payload = {
                "result": (
                    "crossing_selected"
                    if command.action == "crossing_add" else "crossing_removed"
                ),
            }
        else:
            raise ValueError("未知队伍操作")
        context.emit(
            "combat.party.managed",
            source="party",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id,
                "target_id": command.target_id,
                "action": command.action,
                **payload,
            },
        )

    return handler


def party_member_ids(state: WorldState, actor_id: str) -> tuple[str, ...]:
    actor_world = state.entities.require(actor_id, LOCATION).get("world_id")
    return tuple(
        edge.target_id for edge in _party_edges(state, actor_id)
        if bool(state.entities.require(edge.target_id, LIFE).get("alive"))
        and state.entities.require(edge.target_id, LOCATION).get("world_id") == actor_world
    )


def party_crossing_ids(state: WorldState, actor_id: str) -> tuple[str, ...]:
    return tuple(
        edge.target_id for edge in _party_edges(state, actor_id)
        if bool(edge.metadata.get("crossing_selected"))
    )


def party_combat_snapshot(
    state: WorldState, definitions: GameDefinitions, leader_id: str,
) -> dict[str, Any]:
    leader = combat_snapshot(state, definitions, leader_id)
    members = [
        combat_snapshot(state, definitions, member_id)
        for member_id in party_member_ids(state, leader_id)
    ][:2]
    coefficient = 0.5 if len(members) == 1 else 0.25 if len(members) >= 2 else 0.0
    combined = float(leader["power"]) + sum(
        float(member["power"]) for member in members
    ) * coefficient
    scale = combined / max(1.0, float(leader["power"]))
    return {
        **leader,
        "leader_power": float(leader["power"]),
        "power": round(combined, 4),
        "stats": {
            key: round(float(value) * scale, 4)
            for key, value in dict(leader["stats"]).items()
        },
        "party_coefficient": coefficient,
        "party_members": members,
    }


def _close_party_edge(
    context: SimulationContext, edge: RelationEdge, reason: str,
) -> None:
    closed = context.state.relations.end(
        edge.relation_id, ended_year=context.state.clock.year
    )
    metadata = dict(closed.metadata)
    metadata["end_reason"] = reason
    context.state.relations.replace_metadata(closed.relation_id, metadata)


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    for edge in list(context.state.relations.involving(entity_id, kind=PARTY_MEMBER)):
        _close_party_edge(context, edge, "party_member_died")


def _on_permanent_transition(
    context: SimulationContext, event: EventEnvelope,
) -> None:
    actor_id = str(event.payload["actor_id"])
    keep = set(map(str, event.payload.get("keep_relationship_ids", [])))
    kept_targets = {
        other_id
        for relation_id in keep
        for edge in context.state.relations.involving(actor_id)
        if edge.relation_id == relation_id
        for other_id in [
            edge.target_id if edge.source_id == actor_id else edge.source_id
        ]
    }
    ended = []
    for edge in list(_party_edges(context.state, actor_id)):
        if edge.target_id in kept_targets:
            continue
        _close_party_edge(context, edge, "permanent_world_transition")
        ended.append(edge.relation_id)
    context.emit(
        "world.transition.acknowledged",
        source="party",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": event.payload["transaction_id"],
            "actor_id": actor_id,
            "domain": "party",
            "released_ids": ended,
        },
    )


def _on_temporary_transition(
    context: SimulationContext, event: EventEnvelope,
) -> None:
    actor_id = str(event.payload["actor_id"])
    for edge in list(_party_edges(context.state, actor_id)):
        _close_party_edge(context, edge, "temporary_world_transition")


def party_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    leaders: dict[str, int] = {}
    for edge in state.relations.find(kind=PARTY_MEMBER):
        leaders[edge.source_id] = leaders.get(edge.source_id, 0) + 1
        if edge.source_id == edge.target_id:
            errors.append(f"队伍关系不能指向自身：{edge.relation_id}")
        for entity_id in (edge.source_id, edge.target_id):
            if state.entities.get(entity_id, IDENTITY) is None:
                errors.append(f"队伍关系引用未知角色：{edge.relation_id}")
    for leader_id, count in leaders.items():
        if count > 2:
            errors.append(f"角色 {leader_id} 的同行队友超过上限")
    return errors


def party_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    rows = []
    unit = _action_unit(state, actor_id)
    for edge in _party_edges(state, actor_id):
        member = character_view(state, edge.target_id)
        cultivation = state.entities.require(edge.target_id, CULTIVATION)
        realm = definitions.realm(str(cultivation["realm_id"]))
        rows.append({
            **member,
            "realm_id": realm.id,
            "realm_name": realm.name,
            "layer": int(cultivation["layer"]),
            "combat_power": combat_snapshot(
                state, definitions, edge.target_id
            )["power"],
            "crossing_selected": bool(edge.metadata.get("crossing_selected")),
            "crossing_eligible": _crossing_eligible(
                state, definitions, actor_id, edge.target_id
            ),
            "can_interact": int(
                edge.metadata.get("last_interaction_unit", -1)
            ) != unit,
        })
    snapshot = party_combat_snapshot(state, definitions, actor_id)
    actor_world = state.entities.require(actor_id, LOCATION).get("world_id")
    member_ids = {edge.target_id for edge in _party_edges(state, actor_id)}
    candidates = []
    for candidate_id in state.entities.with_component(IDENTITY):
        if candidate_id == actor_id or candidate_id in member_ids:
            continue
        if not bool(state.entities.require(candidate_id, LIFE).get("alive")):
            continue
        if state.entities.require(candidate_id, LOCATION).get("world_id") != actor_world:
            continue
        social_kind = _social_kind(state, actor_id, candidate_id)
        candidate = character_view(state, candidate_id)
        cultivation = state.entities.require(candidate_id, CULTIVATION)
        realm = definitions.realm(str(cultivation["realm_id"]))
        candidates.append({
            **candidate,
            "realm_id": realm.id,
            "realm_name": realm.name,
            "layer": int(cultivation["layer"]),
            "relationship": social_kind,
            "combat_power": combat_snapshot(
                state, definitions, candidate_id
            )["power"],
        })
    candidates.sort(
        key=lambda row: (
            row["relationship"] not in {"dao_companion", "friend"},
            -float(row["combat_power"]),
            str(row["id"]),
        )
    )
    return {
        "members": rows,
        "candidates": candidates[:50],
        "capacity": int(definitions.systems.get("party", {}).get("max_companions", 2)),
        "combined_combat_power": snapshot["power"],
        "leader_combat_power": snapshot["leader_power"],
        "coefficient": snapshot["party_coefficient"],
    }


def register_party_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(ManageParty, _manage_handler(definitions))
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register(
        "world.permanent_transition.requested", _on_permanent_transition
    )
    bus.event_bus.register(
        "world.temporary_transition.committed", _on_temporary_transition
    )
