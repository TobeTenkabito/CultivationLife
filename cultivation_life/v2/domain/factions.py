from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY
from .definitions import GameDefinitions
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


FACTION_PROFILE = "faction.profile"
FACTION_GOVERNANCE = "faction.governance"
MEMBERSHIP = "faction_membership"


@dataclass(frozen=True, slots=True)
class FoundFaction:
    founder_id: str
    name: str


@dataclass(frozen=True, slots=True)
class JoinFaction:
    character_id: str
    faction_id: str
    role: str = "member"


@dataclass(frozen=True, slots=True)
class LeaveFaction:
    character_id: str
    reason: str = "left"


@dataclass(frozen=True, slots=True)
class ChangeContribution:
    character_id: str
    faction_id: str
    amount: int
    reason: str


@dataclass(frozen=True, slots=True)
class TransferFactionControl:
    actor_id: str
    faction_id: str
    successor_id: str


def _create_faction_entity(
    context: SimulationContext,
    *,
    name: str,
    world_id: str,
    external_id: str | None,
    creator_id: str | None,
    path: str,
    allegiance_race: str,
    description: str,
    color: str,
) -> str:
    faction_id = context.state.entities.create("faction")
    context.state.entities.put(
        faction_id,
        FACTION_PROFILE,
        {
            "external_id": external_id,
            "name": name,
            "world_id": world_id,
            "path": path,
            "allegiance_race": allegiance_race,
            "description": description,
            "color": color,
            "active": True,
        },
    )
    context.state.entities.put(
        faction_id,
        FACTION_GOVERNANCE,
        {
            "creator_id": creator_id,
            "controller_id": creator_id,
            "designated_successor_id": None,
        },
    )
    return faction_id


def _on_game_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        for definition in definitions.factions.values():
            faction_id = _create_faction_entity(
                context,
                name=definition.name,
                world_id=definition.world_id,
                external_id=definition.id,
                creator_id=None,
                path=definition.path,
                allegiance_race=definition.allegiance_race,
                description=definition.description,
                color=definition.color,
            )
            context.emit(
                "faction.registered",
                source="factions",
                scope=EventScope("world", definition.world_id),
                payload={"faction_id": faction_id, "external_id": definition.id},
            )

    return handler


def _active_membership(state: WorldState, character_id: str):
    memberships = state.relations.find(source_id=character_id, kind=MEMBERSHIP)
    if len(memberships) > 1:
        raise ValueError("角色同时拥有多个有效势力身份")
    return memberships[0] if memberships else None


def _add_membership(
    context: SimulationContext,
    *,
    character_id: str,
    faction_id: str,
    role: str,
) -> str:
    if role not in {"member", "guest", "leader", "founder"}:
        raise ValueError("未知势力身份")
    if _active_membership(context.state, character_id):
        raise ValueError("角色已经拥有有效势力身份")
    character_location = context.state.entities.require(character_id, LOCATION)
    profile = context.state.entities.require(faction_id, FACTION_PROFILE)
    if not bool(profile.get("active")):
        raise ValueError("目标势力已经不存在")
    if character_location["world_id"] != profile["world_id"]:
        raise ValueError("角色与势力不在同一世界")
    edge = context.state.relations.add(
        source_id=character_id,
        target_id=faction_id,
        kind=MEMBERSHIP,
        created_year=context.state.clock.year,
        metadata={"role": role, "contribution": 0},
    )
    context.emit(
        "faction.member.joined",
        source="factions",
        scope=EventScope("faction", faction_id),
        payload=edge.to_dict(),
    )
    return edge.relation_id


def _found_faction(context: SimulationContext, command: object) -> None:
    if not isinstance(command, FoundFaction):
        raise TypeError("命令类型错误")
    if command.founder_id != context.state.controlled_entity_id:
        raise ValueError("只能由当前角色创建势力")
    if _active_membership(context.state, command.founder_id):
        raise ValueError("必须先退出当前势力")
    name = command.name.strip()
    if not name or len(name) > 30:
        raise ValueError("势力名称必须为1至30个字符")
    if any(
        str(context.state.entities.require(entity_id, FACTION_PROFILE)["name"]) == name
        for entity_id in context.state.entities.with_component(FACTION_PROFILE)
    ):
        raise ValueError("势力名称已经存在")
    identity = context.state.entities.require(command.founder_id, IDENTITY)
    world_id = str(context.state.entities.require(command.founder_id, LOCATION)["world_id"])
    faction_id = _create_faction_entity(
        context,
        name=name,
        world_id=world_id,
        external_id=None,
        creator_id=command.founder_id,
        path="player_created",
        allegiance_race=str(identity["race"]),
        description="由玩家创建的势力",
        color="#6f7b88",
    )
    _add_membership(
        context,
        character_id=command.founder_id,
        faction_id=faction_id,
        role="founder",
    )
    context.emit(
        "faction.founded",
        source="factions",
        scope=EventScope("faction", faction_id),
        payload={"faction_id": faction_id, "founder_id": command.founder_id, "name": name},
    )


def _join_faction(context: SimulationContext, command: object) -> None:
    if not isinstance(command, JoinFaction):
        raise TypeError("命令类型错误")
    if not context.state.entities.exists(command.character_id):
        raise ValueError("角色不存在")
    if not context.state.entities.exists(command.faction_id):
        raise ValueError("势力不存在")
    _add_membership(
        context,
        character_id=command.character_id,
        faction_id=command.faction_id,
        role=command.role,
    )


def _leave_faction(context: SimulationContext, command: object) -> None:
    if not isinstance(command, LeaveFaction):
        raise TypeError("命令类型错误")
    membership = _active_membership(context.state, command.character_id)
    if membership is None:
        raise ValueError("角色当前没有势力身份")
    governance = context.state.entities.require(membership.target_id, FACTION_GOVERNANCE)
    if governance.get("controller_id") == command.character_id:
        governance["controller_id"] = None
        context.state.entities.put(membership.target_id, FACTION_GOVERNANCE, governance)
    ended = context.state.relations.end(membership.relation_id, ended_year=context.state.clock.year)
    metadata = dict(ended.metadata)
    metadata["end_reason"] = command.reason
    context.state.relations.replace_metadata(ended.relation_id, metadata)
    context.emit(
        "faction.member.left",
        source="factions",
        scope=EventScope("faction", membership.target_id),
        payload={
            "character_id": command.character_id,
            "faction_id": membership.target_id,
            "reason": command.reason,
        },
    )


def _change_contribution(context: SimulationContext, command: object) -> None:
    if not isinstance(command, ChangeContribution):
        raise TypeError("命令类型错误")
    membership = _active_membership(context.state, command.character_id)
    if membership is None or membership.target_id != command.faction_id:
        raise ValueError("角色不属于该势力")
    metadata = dict(membership.metadata)
    before = int(metadata.get("contribution", 0))
    after = before + command.amount
    if after < 0:
        raise ValueError("势力贡献不足")
    metadata["contribution"] = after
    context.state.relations.replace_metadata(membership.relation_id, metadata)
    context.emit(
        "faction.contribution.changed",
        source="factions",
        scope=EventScope("faction", command.faction_id),
        payload={
            "character_id": command.character_id,
            "faction_id": command.faction_id,
            "before": before,
            "after": after,
            "amount": command.amount,
            "reason": command.reason,
        },
    )


def _transfer_control(context: SimulationContext, command: object) -> None:
    if not isinstance(command, TransferFactionControl):
        raise TypeError("命令类型错误")
    governance = context.state.entities.require(command.faction_id, FACTION_GOVERNANCE)
    if governance.get("controller_id") != command.actor_id:
        raise ValueError("当前角色没有该势力控制权")
    successor = _active_membership(context.state, command.successor_id)
    if successor is None or successor.target_id != command.faction_id:
        raise ValueError("继任者不是该势力成员")
    governance["controller_id"] = command.successor_id
    governance["designated_successor_id"] = command.successor_id
    context.state.entities.put(command.faction_id, FACTION_GOVERNANCE, governance)
    context.emit(
        "faction.control.transferred",
        source="factions",
        scope=EventScope("faction", command.faction_id),
        payload={
            "faction_id": command.faction_id,
            "from_id": command.actor_id,
            "to_id": command.successor_id,
        },
    )


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    character_id = str(event.payload["entity_id"])
    membership = _active_membership(context.state, character_id)
    if membership is None:
        return
    governance = context.state.entities.require(membership.target_id, FACTION_GOVERNANCE)
    if governance.get("controller_id") != character_id:
        return
    governance["controller_id"] = None
    context.state.entities.put(membership.target_id, FACTION_GOVERNANCE, governance)
    context.emit(
        "faction.control.vacant",
        source="factions",
        scope=EventScope("faction", membership.target_id),
        payload={"faction_id": membership.target_id, "former_controller_id": character_id},
    )


def faction_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        membership_counts: dict[str, int] = {}
        for faction_id in state.entities.with_component(FACTION_PROFILE):
            profile = state.entities.require(faction_id, FACTION_PROFILE)
            governance = state.entities.get(faction_id, FACTION_GOVERNANCE)
            if governance is None:
                errors.append(f"势力 {faction_id} 缺少治理组件")
                continue
            if profile.get("world_id") not in definitions.worlds:
                errors.append(f"势力 {faction_id} 所属世界无效")
            controller_id = governance.get("controller_id")
            if controller_id is not None:
                memberships = state.relations.find(
                    source_id=str(controller_id), kind=MEMBERSHIP
                )
                if not any(edge.target_id == faction_id for edge in memberships):
                    errors.append(f"势力 {faction_id} 控制者不是本势力成员")
        for edge in state.relations.find(kind=MEMBERSHIP):
            membership_counts[edge.source_id] = membership_counts.get(edge.source_id, 0) + 1
            if state.entities.get(edge.source_id, IDENTITY) is None:
                errors.append(f"势力成员不是角色：{edge.relation_id}")
            if state.entities.get(edge.target_id, FACTION_PROFILE) is None:
                errors.append(f"成员关系指向非势力实体：{edge.relation_id}")
            if int(edge.metadata.get("contribution", -1)) < 0:
                errors.append(f"势力贡献非法：{edge.relation_id}")
        if any(count > 1 for count in membership_counts.values()):
            errors.append("角色同时拥有多个有效势力身份")
        return errors

    return validate


def register_faction_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(FoundFaction, _found_faction)
    bus.register(JoinFaction, _join_faction)
    bus.register(LeaveFaction, _leave_faction)
    bus.register(ChangeContribution, _change_contribution)
    bus.register(TransferFactionControl, _transfer_control)
    bus.event_bus.register("core.game.created", _on_game_created(definitions))
    bus.event_bus.register("character.died", _on_character_died)


def faction_view(state: Any, entity_id: str | None = None) -> dict[str, Any] | None:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    membership = _active_membership(state, actor_id)
    if membership is None:
        return None
    profile = state.entities.require(membership.target_id, FACTION_PROFILE)
    governance = state.entities.require(membership.target_id, FACTION_GOVERNANCE)
    return {
        "id": membership.target_id,
        "external_id": profile.get("external_id"),
        "name": profile["name"],
        "world_id": profile["world_id"],
        "role": membership.metadata["role"],
        "contribution": int(membership.metadata["contribution"]),
        "controller_id": governance.get("controller_id"),
        "controlled_by_player": governance.get("controller_id") == actor_id,
    }


def faction_catalog_view(state: Any, world_id: str) -> list[dict[str, Any]]:
    result = []
    for faction_id in state.entities.with_component(FACTION_PROFILE):
        profile = state.entities.require(faction_id, FACTION_PROFILE)
        if profile.get("world_id") != world_id or not bool(profile.get("active")):
            continue
        result.append({
            "id": faction_id,
            "external_id": profile.get("external_id"),
            "name": profile["name"],
            "path": profile["path"],
            "description": profile["description"],
            "color": profile["color"],
        })
    return result
