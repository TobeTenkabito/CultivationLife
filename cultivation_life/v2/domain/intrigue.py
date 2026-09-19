from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE, character_view, create_character
from .combat import combat_snapshot
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .extensions import INTRIGUE_DLC, INTRIGUE_GOVERNANCE
from .factions import (
    DIPLOMACY_STATE,
    FACTION_GOVERNANCE,
    FACTION_PROFILE,
    MEMBERSHIP,
    _add_membership,
    _diplomacy_key,
)
from .family import FAMILY_MEMBERSHIP, FAMILY_PROFILE, LINEAGE
from .presentation import PREFERENCES
from .relations import relationship_affinity, set_relationship_affinity
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


INTRIGUE_PRISONER = "dlc.intrigue.prisoner"
INTRIGUE_GUEST = "dlc.intrigue.guest"

PERSONALITY_LABELS = {
    "paranoid": "偏执", "fanatical": "狂热", "cautious": "谨慎",
    "smooth": "圆滑", "forceful": "强硬", "generous": "宽厚",
    "suspicious": "多疑", "greedy": "贪婪", "restrained": "克制",
    "warlike": "好战", "conservative": "保守", "open": "开放",
}
STYLE_LABELS = {
    "balance": "平衡型", "internal": "内政型",
    "diplomacy": "外交型", "military": "军事型",
}
RESOLUTION_LABELS = {
    "declare_war": "宣战", "make_peace": "停战",
    "form_alliance": "缔结联盟", "break_alliance": "解除联盟",
    "intervene_war": "介入战争", "mass_recruitment": "大规模招收成员",
    "relocate": "迁移主要驻地", "investment": "重大资源投资",
    "policy": "长期政策", "disciple_recruitment": "扩招徒弟",
}


@dataclass(frozen=True, slots=True)
class IntriguePersonnelAction:
    actor_id: str
    kind: str
    action: str
    member_id: str
    position_id: str = ""
    years: int = 1
    reason: str = ""


@dataclass(frozen=True, slots=True)
class IntrigueGuestAction:
    actor_id: str
    kind: str
    action: str
    target_id: str = ""


@dataclass(frozen=True, slots=True)
class IntrigueResolutionAction:
    actor_id: str
    kind: str
    resolution_type: str
    target_id: str = ""
    player_vote: bool = True


@dataclass(frozen=True, slots=True)
class IntrigueRecruitmentAction:
    actor_id: str
    action: str
    filters: dict[str, Any] | None = None
    candidate_ids: tuple[str, ...] = ()
    player_vote: bool = True


def _loaded(definitions: GameDefinitions) -> bool:
    return any(
        extension.id == INTRIGUE_DLC and extension.status == "loaded"
        for extension in definitions.extensions
    )


def _defaults() -> dict[str, Any]:
    return {
        "positions": {},
        "pending_decisions": [],
        "decision_history": [],
        "prisoner_ids": [],
        "member_contribution": {},
        "unrest": 0.0,
        "fear": 0.0,
        "time_progress": 0.0,
        "personnel_history": [],
        "resources": 0,
        "policy": "balance",
        "resolutions": [],
        "next_resolution_sequence": 1,
        "pending_recruitment": None,
        "next_recruitment_sequence": 1,
        "pending_guest_invitation": None,
    }


def _power_kind(state: WorldState, power_id: str) -> str | None:
    if state.entities.get(power_id, FACTION_PROFILE) is not None:
        return "sect"
    if state.entities.get(power_id, FAMILY_PROFILE) is not None:
        return "family"
    return None


def _profile(state: WorldState, kind: str, power_id: str) -> dict[str, Any]:
    return state.entities.require(
        power_id, FACTION_PROFILE if kind == "sect" else FAMILY_PROFILE
    )


def _controller_id(state: WorldState, kind: str, power_id: str) -> str | None:
    component = FACTION_GOVERNANCE if kind == "sect" else FAMILY_PROFILE
    return state.entities.require(power_id, component).get("controller_id")


def _membership_kind(kind: str) -> str:
    return MEMBERSHIP if kind == "sect" else FAMILY_MEMBERSHIP


def _membership(state: WorldState, kind: str, member_id: str, power_id: str):
    rows = state.relations.find(
        source_id=member_id,
        target_id=power_id,
        kind=_membership_kind(kind),
    )
    return rows[0] if rows else None


def _actor_power(state: WorldState, actor_id: str, kind: str) -> str | None:
    if kind == "sect":
        rows = state.relations.find(source_id=actor_id, kind=MEMBERSHIP)
        return rows[0].target_id if rows else None
    if kind == "family":
        lineage = state.entities.get(actor_id, LINEAGE) or {}
        family_id = lineage.get("family_id")
        if family_id and state.entities.get(str(family_id), FAMILY_PROFILE) is not None:
            return str(family_id)
        return next((
            family_id for family_id in state.entities.with_component(FAMILY_PROFILE)
            if state.entities.require(family_id, FAMILY_PROFILE).get("controller_id") == actor_id
        ), None)
    return None


def _positions(definitions: GameDefinitions, kind: str) -> dict[str, dict[str, Any]]:
    config = dict(definitions.systems.get("intrigue_dlc", {}))
    return {
        str(position_id): dict(spec)
        for position_id, spec in dict(config.get("positions", {})).get(kind, {}).items()
    }


def _leader_position(kind: str) -> str:
    return "leader" if kind == "sect" else "family_head"


def _normalize_governance(
    state: WorldState, definitions: GameDefinitions, power_id: str,
) -> None:
    kind = _power_kind(state, power_id)
    if kind is None:
        return
    current = state.entities.get(power_id, INTRIGUE_GOVERNANCE) or {}
    defaults = _defaults()
    for key, value in defaults.items():
        current.setdefault(key, value.copy() if isinstance(value, (dict, list)) else value)
    current["unrest"] = max(0.0, min(100.0, float(current.get("unrest", 0))))
    current["fear"] = max(0.0, min(100.0, float(current.get("fear", 0))))
    controller_id = _controller_id(state, kind, power_id)
    leader = _leader_position(kind)
    if controller_id and leader in _positions(definitions, kind):
        current["positions"][leader] = str(controller_id)
    else:
        current["positions"].pop(leader, None)
    state.entities.put(power_id, INTRIGUE_GOVERNANCE, current)


def reconcile_intrigue_state(state: WorldState, definitions: GameDefinitions) -> None:
    state.module_versions["intrigue"] = 2
    if not _loaded(definitions):
        return
    for component in (FACTION_PROFILE, FAMILY_PROFILE):
        for power_id in state.entities.with_component(component):
            _normalize_governance(state, definitions, power_id)


def is_intrigue_imprisoned(state: WorldState, character_id: str) -> bool:
    return bool(state.relations.find(target_id=character_id, kind=INTRIGUE_PRISONER))


def intrigue_guest_ids(
    state: WorldState, power_id: str, *, defensive: bool = True,
) -> list[str]:
    result = []
    for edge in state.relations.find(source_id=power_id, kind=INTRIGUE_GUEST):
        if defensive and not bool(edge.metadata.get("defense_required", True)):
            continue
        life = state.entities.get(edge.target_id, LIFE) or {}
        if bool(life.get("alive")) and not is_intrigue_imprisoned(state, edge.target_id):
            result.append(edge.target_id)
    return list(dict.fromkeys(result))


def _remove_guest_from_active_wars(
    state: WorldState, power_id: str, character_id: str,
) -> None:
    from .war import WAR_PROFILE

    for war_id in state.entities.with_component(WAR_PROFILE):
        war = state.entities.require(war_id, WAR_PROFILE)
        if war.get("status") not in {"active", "peace_ready"}:
            continue
        owners = dict(war.get("roster_owner", {}))
        if owners.get(character_id) != power_id:
            continue
        roster = dict(war.get("roster", {}))
        for side in ("attacker", "defender"):
            roster[side] = [
                value for value in map(str, roster.get(side, []))
                if value != character_id
            ]
        owners.pop(character_id, None)
        war["roster"] = roster
        war["roster_owner"] = owners
        state.entities.put(war_id, WAR_PROFILE, war)


def _decision_threshold(definitions: GameDefinitions, kind: str) -> int:
    config = dict(definitions.systems.get("intrigue_dlc", {}))
    return int(dict(config.get("decision_thresholds", {})).get(
        kind, {"sect": 4, "family": 3, "race": 8}.get(kind, 99)
    ))


def _decision_authority(
    state: WorldState,
    definitions: GameDefinitions,
    kind: str,
    power_id: str,
    character_id: str,
) -> bool:
    life = state.entities.get(character_id, LIFE) or {}
    cultivation = state.entities.get(character_id, CULTIVATION) or {}
    location = state.entities.get(character_id, LOCATION) or {}
    if not bool(life.get("alive")) or is_intrigue_imprisoned(state, character_id):
        return False
    if definitions.realm_index(str(cultivation.get("realm_id", "mortal"))) < _decision_threshold(
        definitions, kind
    ):
        return False
    if kind == "race":
        identity = state.entities.get(character_id, IDENTITY) or {}
        actor_world = location.get("world_id")
        return identity.get("race") == power_id and actor_world is not None
    profile = _profile(state, kind, power_id)
    return (
        profile.get("world_id") == location.get("world_id")
        and (
            character_id == _controller_id(state, kind, power_id)
            or _membership(state, kind, character_id, power_id) is not None
            or bool(state.relations.find(
                source_id=power_id,
                target_id=character_id,
                kind=INTRIGUE_GUEST,
            ))
        )
    )


def _power_members_for_decision(
    state: WorldState, kind: str, power_id: str, world_id: str,
) -> list[str]:
    if kind == "race":
        return [
            entity_id for entity_id in state.entities.with_component(IDENTITY)
            if state.entities.require(entity_id, IDENTITY).get("race") == power_id
            and state.entities.require(entity_id, LOCATION).get("world_id") == world_id
        ]
    members = [
        edge.source_id for edge in state.relations.find(
            target_id=power_id, kind=_membership_kind(kind)
        )
    ]
    return list(dict.fromkeys([*members, *intrigue_guest_ids(state, power_id)]))


def _guest_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, IntrigueGuestAction):
            raise TypeError("命令类型错误")
        if not _loaded(definitions):
            raise ValueError("势力内政DLC未启用")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色处理客卿事务")
        if command.kind not in {"sect", "family"}:
            raise ValueError("客卿事务只适用于宗门或家族")

        if command.action in {"accept_invitation", "decline_invitation"}:
            found: tuple[str, dict[str, Any]] | None = None
            for power_id in context.state.entities.with_component(INTRIGUE_GOVERNANCE):
                governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
                invitation = governance.get("pending_guest_invitation")
                if isinstance(invitation, dict) and invitation.get("target_id") == command.actor_id:
                    found = power_id, invitation
                    break
            if found is None:
                raise ValueError("当前没有待回应的客卿邀请")
            power_id, invitation = found
            kind = _power_kind(context.state, power_id)
            if kind is None or kind != command.kind:
                raise ValueError("客卿邀请所属势力无效")
            profile = _profile(context.state, kind, power_id)
            actor_world = context.state.entities.require(command.actor_id, LOCATION)["world_id"]
            if profile.get("world_id") != actor_world or not bool(profile.get("active", True)):
                raise ValueError("这份客卿邀请已经失效")
            governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
            governance["pending_guest_invitation"] = None
            context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
            if command.action == "accept_invitation" and not context.state.relations.find(
                source_id=power_id, target_id=command.actor_id, kind=INTRIGUE_GUEST
            ):
                context.state.relations.add(
                    source_id=power_id,
                    target_id=command.actor_id,
                    kind=INTRIGUE_GUEST,
                    created_year=context.state.clock.year,
                    metadata={
                        "defense_required": True,
                        "offense_opt_in": False,
                        "invited_by": invitation.get("invited_by"),
                    },
                )
            power_for_event = power_id
        elif command.action == "resign":
            power_id = command.target_id
            rows = context.state.relations.find(
                source_id=power_id, target_id=command.actor_id, kind=INTRIGUE_GUEST
            )
            if not rows:
                raise ValueError("你并非该势力客卿")
            for edge in rows:
                context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
            _remove_guest_from_active_wars(context.state, power_id, command.actor_id)
            power_for_event = power_id
        else:
            power_id = _actor_power(context.state, command.actor_id, command.kind)
            if power_id is None or _controller_id(
                context.state, command.kind, power_id
            ) != command.actor_id:
                raise ValueError("你没有该势力的客卿任免权")
            profile = _profile(context.state, command.kind, power_id)
            if profile.get("world_id") != context.state.entities.require(
                command.actor_id, LOCATION
            ).get("world_id"):
                raise ValueError("身处其他世界时不能处理客卿事务")
            target_id = command.target_id
            life = context.state.entities.get(target_id, LIFE)
            location = context.state.entities.get(target_id, LOCATION)
            if life is None or not bool(life.get("alive")) or location is None:
                raise ValueError("目标人物已经失联")
            if location.get("world_id") != profile.get("world_id"):
                raise ValueError("目标不在当前世界")
            rows = context.state.relations.find(
                source_id=power_id, target_id=target_id, kind=INTRIGUE_GUEST
            )
            if command.action == "invite":
                if rows or _membership(context.state, command.kind, target_id, power_id):
                    raise ValueError("目标已经属于该势力")
                affinity = relationship_affinity(context.state, target_id, command.actor_id)
                is_friend = any(
                    target_id in {edge.source_id, edge.target_id}
                    for edge in context.state.relations.involving(
                        command.actor_id, kind="friend"
                    )
                )
                if affinity < 30 and not is_friend:
                    raise ValueError("目标不是高好感人物或道友")
                chance = max(0.12, min(0.95, 0.48 + affinity / 180))
                if context.rng.random() >= chance:
                    _set_affinity_delta(context.state, target_id, command.actor_id, -2)
                else:
                    context.state.relations.add(
                        source_id=power_id,
                        target_id=target_id,
                        kind=INTRIGUE_GUEST,
                        created_year=context.state.clock.year,
                        metadata={
                            "defense_required": True,
                            "offense_opt_in": False,
                            "invited_by": command.actor_id,
                        },
                    )
                    _set_affinity_delta(context.state, target_id, command.actor_id, 4)
            elif command.action == "remove":
                if not rows:
                    raise ValueError("目标不是本势力客卿")
                for edge in rows:
                    context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
                _remove_guest_from_active_wars(context.state, power_id, target_id)
                _set_affinity_delta(context.state, target_id, command.actor_id, -10)
            elif command.action == "regularize":
                if not rows:
                    raise ValueError("目标不是本势力客卿")
                actor_membership = next(iter(context.state.relations.find(
                    source_id=command.actor_id, kind=MEMBERSHIP
                )), None)
                if actor_membership is None or int(actor_membership.metadata.get("contribution", 0)) < 30:
                    raise ValueError("转正需要消耗30点势力贡献")
                governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
                positions = dict(governance.get("positions", {}))
                realm = definitions.realm_index(str(context.state.entities.require(
                    target_id, CULTIVATION
                )["realm_id"]))
                vacancy = next((
                    position_id for position_id, spec in _positions(definitions, command.kind).items()
                    if position_id != _leader_position(command.kind)
                    and position_id not in positions
                    and realm >= int(spec.get("minimum_realm", 0))
                ), None)
                if vacancy is None:
                    raise ValueError("没有符合其修为的正式职位空缺")
                metadata = dict(actor_membership.metadata)
                metadata["contribution"] = int(metadata.get("contribution", 0)) - 30
                context.state.relations.replace_metadata(actor_membership.relation_id, metadata)
                for edge in rows:
                    context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
                if command.kind == "sect":
                    _add_membership(
                        context, character_id=target_id, faction_id=power_id, role="guest_regularized"
                    )
                else:
                    context.state.relations.add(
                        source_id=target_id,
                        target_id=power_id,
                        kind=FAMILY_MEMBERSHIP,
                        created_year=context.state.clock.year,
                        metadata={"role": "guest_regularized", "cultivation_progress": 0.0},
                    )
                positions[vacancy] = target_id
                governance["positions"] = positions
                context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
            else:
                raise ValueError("未知客卿操作")
            power_for_event = power_id
        context.emit(
            "dlc.intrigue.guest.resolved",
            source=INTRIGUE_DLC,
            scope=EventScope("faction", power_for_event),
            payload={
                "power_id": power_for_event,
                "actor_id": command.actor_id,
                "target_id": command.target_id,
                "action": command.action,
            },
        )
    return handler


def _resolution_store(
    state: WorldState, kind: str, power_id: str, actor_id: str,
) -> tuple[dict[str, Any], str]:
    if kind == "race":
        component = state.entities.require(actor_id, DIPLOMACY_STATE)
        component.setdefault("intrigue_resolutions", [])
        component.setdefault("next_intrigue_resolution_sequence", 1)
        return component, actor_id
    return state.entities.require(power_id, INTRIGUE_GOVERNANCE), power_id


def _record_resolution(
    state: WorldState,
    kind: str,
    power_id: str,
    actor_id: str,
    resolution: dict[str, Any],
) -> None:
    component, owner_id = _resolution_store(state, kind, power_id, actor_id)
    key = "intrigue_resolutions" if kind == "race" else "resolutions"
    rows = list(component.get(key, []))
    rows.append(resolution)
    component[key] = rows[-80:]
    state.entities.put(
        owner_id,
        DIPLOMACY_STATE if kind == "race" else INTRIGUE_GOVERNANCE,
        component,
    )


def _next_resolution_id(
    state: WorldState, kind: str, power_id: str, actor_id: str,
) -> str:
    component, owner_id = _resolution_store(state, kind, power_id, actor_id)
    key = (
        "next_intrigue_resolution_sequence"
        if kind == "race" else "next_resolution_sequence"
    )
    sequence = max(1, int(component.get(key, 1)))
    component[key] = sequence + 1
    state.entities.put(
        owner_id,
        DIPLOMACY_STATE if kind == "race" else INTRIGUE_GOVERNANCE,
        component,
    )
    return f"resolution:{kind}:{sequence}"


def _create_recruit(
    context: SimulationContext,
    definitions: GameDefinitions,
    *,
    world_id: str,
    path: str,
    race: str,
    realm_id: str,
    layer: int,
    name: str,
    gender: str,
    spirit_root: str,
) -> str:
    realm = definitions.realm(realm_id)
    age = context.rng.randint(16, 36)
    lifespan = (
        None if realm.lifespan is None
        else max(age + 1, context.rng.randint(*realm.lifespan))
    )
    return create_character(
        context,
        name=name,
        age=age,
        gender=gender,
        race=race,
        spirit_root=spirit_root,
        path=path,
        realm_id=realm_id,
        layer=layer,
        world_id=world_id,
        lifespan=lifespan,
    )


def _apply_resolution(
    context: SimulationContext,
    definitions: GameDefinitions,
    command: IntrigueResolutionAction,
    power_id: str,
) -> None:
    resolution_type = command.resolution_type
    kind = command.kind
    if resolution_type in {
        "declare_war", "make_peace", "form_alliance", "break_alliance",
    }:
        diplomacy_kind = "faction" if kind == "sect" else kind
        if diplomacy_kind not in {"faction", "race"} or not command.target_id:
            raise ValueError("该势力不能执行这项外交决议")
        own_id = power_id
        target_id = command.target_id
        if diplomacy_kind == "faction":
            target_profile = context.state.entities.get(target_id, FACTION_PROFILE)
            if target_profile is None:
                raise ValueError("目标宗门无效")
        elif target_id not in definitions.races:
            raise ValueError("目标种族无效")
        if target_id == own_id:
            raise ValueError("不能以自身为外交目标")
        diplomacy = context.state.entities.require(command.actor_id, DIPLOMACY_STATE)
        relations = dict(diplomacy.get("relations", {}))
        key = _diplomacy_key(diplomacy_kind, own_id, target_id)
        status = {
            "declare_war": "war", "make_peace": "truce",
            "form_alliance": "alliance", "break_alliance": "neutral",
        }[resolution_type]
        relation = dict(relations.get(key, {
            "kind": diplomacy_kind,
            "first_id": min(own_id, target_id),
            "second_id": max(own_id, target_id),
            "since_year": context.state.clock.year,
        }))
        if relation.get("status") == "war" and status != "war":
            raise ValueError("战争已经进入征伐阶段，请在战争事务中提交和约")
        relation.update(
            status=status,
            affinity=float({
                "war": -75, "truce": -5, "alliance": 80, "neutral": 0,
            }[status]),
            since_year=context.state.clock.year,
            overlord=None,
            subject=None,
        )
        relations[key] = relation
        diplomacy["relations"] = relations
        context.state.entities.put(command.actor_id, DIPLOMACY_STATE, diplomacy)
        context.emit(
            "governance.diplomacy.voted",
            source=INTRIGUE_DLC,
            scope=EventScope("world", context.state.entities.require(
                command.actor_id, LOCATION
            )["world_id"]),
            payload={
                "actor_id": command.actor_id,
                "key": key,
                "passed": True,
                "relation": relation,
            },
        )
        return
    if kind not in {"sect", "family"}:
        raise ValueError("该种族决议类型尚无有效对象")
    governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
    profile = _profile(context.state, kind, power_id)
    if resolution_type == "mass_recruitment":
        recruit_path = str(profile.get("path", ""))
        if recruit_path not in definitions.paths:
            recruit_path = str(context.state.entities.require(
                command.actor_id, CULTIVATION
            )["path"])
        for index in range(context.rng.randint(2, 4)):
            realm_id = context.rng.choice(["mortal", "qi", "foundation"])
            member_id = _create_recruit(
                context,
                definitions,
                world_id=str(profile["world_id"]),
                path=recruit_path,
                race=str(profile.get("allegiance_race", "human")),
                realm_id=realm_id,
                layer=1,
                name=context.rng.choice(["宁川", "苏砚", "沈禾", "顾霜", "陆迟", "叶青"])
                + (str(index + 1) if index else ""),
                gender=context.rng.choice(["male", "female"]),
                spirit_root="none" if realm_id == "mortal" else "supreme_water",
            )
            if kind == "sect":
                _add_membership(
                    context, character_id=member_id, faction_id=power_id, role="recruit"
                )
            else:
                context.state.relations.add(
                    source_id=member_id,
                    target_id=power_id,
                    kind=FAMILY_MEMBERSHIP,
                    created_year=context.state.clock.year,
                    metadata={"role": "recruit", "cultivation_progress": 0.0},
                )
        governance["unrest"] = max(0.0, float(governance.get("unrest", 0)) - 2)
    elif resolution_type == "investment":
        governance["resources"] = int(governance.get("resources", 0)) + 25
        governance["unrest"] = max(0.0, float(governance.get("unrest", 0)) - 4)
    elif resolution_type == "relocate":
        if command.target_id not in definitions.worlds or not definitions.worlds[
            command.target_id
        ].enabled:
            raise ValueError("目标世界无效")
        profile["world_id"] = command.target_id
        context.state.entities.put(
            power_id,
            FACTION_PROFILE if kind == "sect" else FAMILY_PROFILE,
            profile,
        )
        for member_id in _power_members_for_decision(
            context.state, kind, power_id, str(profile["world_id"])
        ):
            location = context.state.entities.require(member_id, LOCATION)
            location["world_id"] = command.target_id
            location["location_id"] = definitions.worlds[command.target_id].default_location_id
            context.state.entities.put(member_id, LOCATION, location)
    elif resolution_type == "policy":
        if command.target_id not in STYLE_LABELS:
            raise ValueError("未知长期政策")
        governance["policy"] = command.target_id
    elif resolution_type == "intervene_war":
        from .war import WAR_PROFILE

        war = context.state.entities.get(command.target_id, WAR_PROFILE)
        if war is None or war.get("status") not in {"active", "peace_ready"}:
            raise ValueError("目标战争不存在")
        if war.get("kind") != "faction" or power_id in {
            war.get("attacker_id"), war.get("defender_id")
        }:
            raise ValueError("当前势力不能介入这场战争")
        coalitions = dict(war.get("coalitions", {}))
        defenders = list(map(str, coalitions.get("defender", [])))
        if power_id not in defenders:
            defenders.append(power_id)
        coalitions["defender"] = defenders
        war["coalitions"] = coalitions
        roster = dict(war.get("roster", {}))
        defender_roster = list(map(str, roster.get("defender", [])))
        additions = _power_members_for_decision(
            context.state, kind, power_id, str(war["world_id"])
        )
        defender_roster = list(dict.fromkeys([*defender_roster, *additions]))
        roster["defender"] = defender_roster
        war["roster"] = roster
        owners = dict(war.get("roster_owner", {}))
        owners.update({member_id: power_id for member_id in additions})
        war["roster_owner"] = owners
        context.state.entities.put(command.target_id, WAR_PROFILE, war)
        governance["intervention_target"] = command.target_id
    elif resolution_type == "disciple_recruitment":
        raise ValueError("扩招徒弟需要先设置筛选条件")
    else:
        raise ValueError("未知重大决议")
    context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)


def _resolution_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, IntrigueResolutionAction):
            raise TypeError("命令类型错误")
        if not _loaded(definitions):
            raise ValueError("势力内政DLC未启用")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色提出势力决议")
        if command.kind not in {"sect", "family", "race"}:
            raise ValueError("未知势力类型")
        if command.resolution_type not in RESOLUTION_LABELS:
            raise ValueError("未知重大决议")
        if command.resolution_type == "disciple_recruitment":
            raise ValueError("扩招徒弟需要先设置筛选条件")
        if command.kind == "race":
            power_id = str(context.state.entities.require(command.actor_id, IDENTITY)["race"])
            world_id = str(context.state.entities.require(command.actor_id, LOCATION)["world_id"])
        else:
            power_id = _actor_power(context.state, command.actor_id, command.kind) or ""
            if not power_id:
                raise ValueError("当前角色不属于该势力")
            world_id = str(_profile(context.state, command.kind, power_id)["world_id"])
        if not _decision_authority(
            context.state, definitions, command.kind, power_id, command.actor_id
        ):
            raise ValueError("你没有该势力的决策权")
        voter_ids = _power_members_for_decision(
            context.state, command.kind, power_id, world_id
        )
        ballots = [{
            "id": command.actor_id,
            "vote": bool(command.player_vote),
            "player": True,
            "chance": 1.0 if command.player_vote else 0.0,
        }]
        policy = "balance"
        if command.kind != "race":
            policy = str(context.state.entities.require(
                power_id, INTRIGUE_GOVERNANCE
            ).get("policy", "balance"))
        biases = {
            "balance": {"investment": .08, "make_peace": .14, "declare_war": -.10},
            "internal": {"mass_recruitment": .18, "investment": .16, "declare_war": -.12},
            "diplomacy": {"form_alliance": .20, "make_peace": .18, "declare_war": -.18},
            "military": {"declare_war": .22, "intervene_war": .16, "make_peace": -.10},
        }
        for voter_id in sorted(set(voter_ids)):
            if voter_id == command.actor_id or not _decision_authority(
                context.state, definitions, command.kind, power_id, voter_id
            ):
                continue
            affinity = relationship_affinity(context.state, voter_id, command.actor_id)
            chance = max(0.05, min(
                0.95,
                0.5 + biases.get(policy, {}).get(command.resolution_type, 0)
                + (0.08 if affinity > 40 else 0),
            ))
            ballots.append({
                "id": voter_id,
                "vote": context.rng.random() < chance,
                "player": False,
                "chance": round(chance, 3),
            })
        yes = sum(bool(row["vote"]) for row in ballots)
        passed = yes > len(ballots) / 2
        resolution = {
            "id": _next_resolution_id(
                context.state, command.kind, power_id, command.actor_id
            ),
            "kind": command.kind,
            "faction_id": power_id,
            "type": command.resolution_type,
            "type_name": RESOLUTION_LABELS[command.resolution_type],
            "target_id": command.target_id,
            "proposer_id": command.actor_id,
            "votes": ballots,
            "yes": yes,
            "total": len(ballots),
            "result": "passed" if passed else "rejected",
            "year": context.state.clock.year,
        }
        if passed:
            _apply_resolution(context, definitions, command, power_id)
        _record_resolution(
            context.state, command.kind, power_id, command.actor_id, resolution
        )
        context.emit(
            "dlc.intrigue.resolution.completed",
            source=INTRIGUE_DLC,
            scope=EventScope("world", world_id),
            payload=resolution,
        )
    return handler


def _normalize_recruitment_filters(
    definitions: GameDefinitions, filters: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = dict(filters or {})
    root = str(raw.get("spirit_root", "any"))
    if root not in {"any", "heavenly"}:
        raise ValueError("灵根筛选只能选择不筛选或天灵根")
    realm = raw.get("realm_index", "any")
    realm_id = None
    if realm not in {None, "", "any"}:
        if isinstance(realm, int) or str(realm).isdigit():
            index = int(realm)
            if not 0 <= index < len(definitions.realms):
                raise ValueError("修为筛选无效")
            realm_id = definitions.realms[index].id
        elif str(realm) in {row.id for row in definitions.realms}:
            realm_id = str(realm)
        else:
            raise ValueError("修为筛选无效")
    path = str(raw.get("path", "any"))
    if path not in {"any", "dao", "demonic", "ghost", "monster"}:
        raise ValueError("修炼路线筛选无效")
    combat = str(raw.get("combat", "any"))
    config = dict(definitions.systems.get("intrigue_dlc", {}))
    if combat not in dict(config.get("disciple_recruitment", {})).get(
        "combat_filters", {}
    ):
        raise ValueError("战斗力筛选无效")
    gender = str(raw.get("gender", "any"))
    if gender not in {"any", "male", "female"}:
        raise ValueError("性别筛选无效")
    return {
        "spirit_root": root,
        "realm_id": realm_id,
        "path": path,
        "combat": combat,
        "gender": gender,
    }


def _recruitment_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, IntrigueRecruitmentAction):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色处理宗门扩招")
        power_id = _actor_power(context.state, command.actor_id, "sect")
        if power_id is None or not _decision_authority(
            context.state, definitions, "sect", power_id, command.actor_id
        ):
            raise ValueError("你没有当前宗门的决策权")
        governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
        profile = context.state.entities.require(power_id, FACTION_PROFILE)
        if command.action == "propose":
            if governance.get("pending_recruitment"):
                raise ValueError("请先处理上一轮扩招候选人")
            filters = _normalize_recruitment_filters(definitions, command.filters)
            voter_ids = _power_members_for_decision(
                context.state, "sect", power_id, str(profile["world_id"])
            )
            votes = [bool(command.player_vote)]
            for voter_id in voter_ids:
                if voter_id != command.actor_id and _decision_authority(
                    context.state, definitions, "sect", power_id, voter_id
                ):
                    votes.append(context.rng.random() < 0.68)
            passed = sum(votes) > len(votes) / 2
            record = {
                "id": _next_resolution_id(context.state, "sect", power_id, command.actor_id),
                "kind": "sect",
                "faction_id": power_id,
                "type": "disciple_recruitment",
                "type_name": RESOLUTION_LABELS["disciple_recruitment"],
                "votes": votes,
                "yes": sum(votes),
                "total": len(votes),
                "result": "passed" if passed else "rejected",
                "year": context.state.clock.year,
            }
            if passed:
                config = dict(definitions.systems.get("intrigue_dlc", {}))
                recruitment = dict(config.get("disciple_recruitment", {}))
                low, high = map(int, recruitment.get("applicant_pool", [6, 12]))
                maximum = max(1, min(5, int(recruitment.get("max_candidates", 5))))
                candidates: list[str] = []
                combat_ratios: dict[str, float] = {}
                surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "江", "苏", "沈"]
                given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "砚", "青", "禾"]
                threshold = _decision_threshold(definitions, "sect")
                for _ in range(context.rng.randint(low, max(low, high))):
                    realm_id = filters["realm_id"] or context.rng.choice(
                        [row.id for row in definitions.realms[:max(1, threshold)]]
                    )
                    if definitions.realm_index(realm_id) >= threshold:
                        continue
                    path = (
                        filters["path"] if filters["path"] != "any"
                        else str(
                            profile.get("path")
                            or context.state.entities.require(
                                command.actor_id, CULTIVATION
                            )["path"]
                        )
                    )
                    if path not in definitions.paths:
                        path = str(context.state.entities.require(
                            command.actor_id, CULTIVATION
                        )["path"])
                    gender = filters["gender"] if filters["gender"] != "any" else context.rng.choice(
                        ["male", "female"]
                    )
                    roots = [root for root in definitions.roots.values() if root.id != "none"]
                    if filters["spirit_root"] == "heavenly":
                        roots = [root for root in roots if root.tier == "天灵根"]
                    root = context.rng.choice(roots).id if realm_id != "mortal" and roots else "none"
                    candidate_id = _create_recruit(
                        context,
                        definitions,
                        world_id=str(profile["world_id"]),
                        path=path,
                        race=str(profile.get("allegiance_race", "human")),
                        realm_id=realm_id,
                        layer=1,
                        name=context.rng.choice(surnames) + context.rng.choice(given),
                        gender=gender,
                        spirit_root=root,
                    )
                    baseline = max(1.0, float(combat_snapshot(
                        context.state, definitions, candidate_id
                    )["power"]))
                    minimum_ratio = float(dict(
                        recruitment.get("combat_filters", {})
                    ).get(filters["combat"], {}).get("minimum_ratio", 0.0))
                    ratio = 1.0
                    candidate_cultivation = context.state.entities.require(
                        candidate_id, CULTIVATION
                    )
                    for candidate_layer in range(1, definitions.realm(realm_id).layers + 1):
                        candidate_cultivation["layer"] = candidate_layer
                        context.state.entities.put(
                            candidate_id, CULTIVATION, candidate_cultivation
                        )
                        ratio = float(combat_snapshot(
                            context.state, definitions, candidate_id
                        )["power"]) / baseline
                        if ratio + 1e-9 >= minimum_ratio:
                            break
                    if ratio + 1e-9 < minimum_ratio:
                        continue
                    candidates.append(candidate_id)
                    combat_ratios[candidate_id] = round(ratio, 4)
                    if len(candidates) >= maximum:
                        break
                governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
                sequence = max(1, int(governance.get("next_recruitment_sequence", 1)))
                governance["next_recruitment_sequence"] = sequence + 1
                governance["pending_recruitment"] = {
                    "id": f"recruitment:{sequence}",
                    "filters": filters,
                    "candidate_ids": candidates,
                    "combat_ratios": combat_ratios,
                    "created_year": context.state.clock.year,
                }
                governance["unrest"] = max(0.0, float(governance.get("unrest", 0)) - 1)
                context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
                record["candidate_count"] = len(candidates)
            _record_resolution(context.state, "sect", power_id, command.actor_id, record)
        elif command.action == "confirm":
            pending = governance.get("pending_recruitment")
            if not isinstance(pending, dict):
                raise ValueError("当前没有待选择的扩招候选人")
            available = set(map(str, pending.get("candidate_ids", [])))
            requested = list(dict.fromkeys(map(str, command.candidate_ids)))
            if any(candidate_id not in available for candidate_id in requested):
                raise ValueError("所选候选人不属于本轮扩招名单")
            maximum = int(dict(dict(definitions.systems.get(
                "intrigue_dlc", {}
            )).get("disciple_recruitment", {})).get("max_candidates", 5))
            if len(requested) > maximum:
                raise ValueError(f"每轮最多录取{maximum}名弟子")
            current = len(context.state.relations.find(
                target_id=power_id, kind=MEMBERSHIP
            ))
            capacity = max(0, int(definitions.systems.get("factions", {}).get(
                "max_members", 36
            )) - current)
            if len(requested) > capacity:
                raise ValueError(f"宗门名册仅余{capacity}个空位")
            for candidate_id in requested:
                _add_membership(
                    context,
                    character_id=candidate_id,
                    faction_id=power_id,
                    role="disciple_recruitment",
                )
            governance["pending_recruitment"] = None
            context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
            context.emit(
                "dlc.intrigue.recruitment.completed",
                source=INTRIGUE_DLC,
                scope=EventScope("faction", power_id),
                payload={
                    "faction_id": power_id,
                    "candidate_ids": requested,
                    "recruited": len(requested),
                },
            )
        else:
            raise ValueError("未知的宗门扩招操作")
    return handler


def _set_affinity_delta(
    state: WorldState, member_id: str, actor_id: str, delta: float,
) -> float:
    return set_relationship_affinity(
        state,
        member_id,
        actor_id,
        max(-100.0, min(100.0, relationship_affinity(state, member_id, actor_id) + delta)),
    )


def _clear_personnel_reference(
    context: SimulationContext,
    definitions: GameDefinitions,
    power_id: str,
    member_id: str,
    *,
    reason: str,
) -> None:
    governance = context.state.entities.get(power_id, INTRIGUE_GOVERNANCE)
    if governance is None:
        return
    positions = dict(governance.get("positions", {}))
    removed = [position_id for position_id, holder in positions.items() if holder == member_id]
    for position_id in removed:
        positions.pop(position_id, None)
    governance["positions"] = positions
    governance["prisoner_ids"] = [
        value for value in map(str, governance.get("prisoner_ids", []))
        if value != member_id
    ]
    context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
    _normalize_governance(context.state, definitions, power_id)
    for edge in context.state.relations.find(
        source_id=power_id, target_id=member_id, kind=INTRIGUE_PRISONER
    ):
        ended = context.state.relations.end(
            edge.relation_id, ended_year=context.state.clock.year
        )
        metadata = dict(ended.metadata)
        metadata["end_reason"] = reason
        context.state.relations.replace_metadata(ended.relation_id, metadata)
    if removed:
        context.emit(
            "dlc.intrigue.positions.vacated",
            source=INTRIGUE_DLC,
            scope=EventScope("faction", power_id),
            payload={
                "power_id": power_id,
                "member_id": member_id,
                "position_ids": removed,
                "reason": reason,
            },
        )


def _personnel_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, IntriguePersonnelAction):
            raise TypeError("命令类型错误")
        if not _loaded(definitions):
            raise ValueError("势力内政DLC未启用")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色处理势力人事")
        if command.kind not in {"sect", "family"}:
            raise ValueError("未知势力类型")
        power_id = _actor_power(context.state, command.actor_id, command.kind)
        if power_id is None or _controller_id(context.state, command.kind, power_id) != command.actor_id:
            raise ValueError("你没有该势力的控制权")
        profile = _profile(context.state, command.kind, power_id)
        actor_world = context.state.entities.require(command.actor_id, LOCATION)["world_id"]
        if profile.get("world_id") != actor_world or not bool(profile.get("active", True)):
            raise ValueError("身处其他世界时不能处理该势力人事")
        if command.member_id == command.actor_id:
            raise ValueError("不能对当前控制者执行此操作")
        membership = _membership(
            context.state, command.kind, command.member_id, power_id
        )
        life = context.state.entities.get(command.member_id, LIFE)
        if membership is None or life is None or not bool(life.get("alive")):
            raise ValueError("目标不是在册的存活成员")
        _normalize_governance(context.state, definitions, power_id)
        governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
        positions = dict(governance.get("positions", {}))
        specs = _positions(definitions, command.kind)
        result: dict[str, Any] = {}

        if command.action == "appoint":
            position = specs.get(command.position_id)
            if position is None or command.position_id == _leader_position(command.kind):
                raise ValueError("该职位不可由此处任命")
            cultivation = context.state.entities.require(command.member_id, CULTIVATION)
            if definitions.realm_index(str(cultivation["realm_id"])) < int(position.get("minimum_realm", 0)):
                raise ValueError("目标修为尚未达到职位要求")
            if is_intrigue_imprisoned(context.state, command.member_id):
                raise ValueError("囚犯不能担任职位")
            former = positions.get(command.position_id)
            positions = {
                position_id: holder_id
                for position_id, holder_id in positions.items()
                if holder_id != command.member_id and position_id != command.position_id
            }
            if former and former != command.member_id and context.state.entities.exists(str(former)):
                _set_affinity_delta(context.state, str(former), command.actor_id, -8)
                governance["unrest"] = min(100.0, float(governance["unrest"]) + 3)
            positions[command.position_id] = command.member_id
            _set_affinity_delta(context.state, command.member_id, command.actor_id, 5)
            result = {"position_id": command.position_id, "former_holder_id": former}
        elif command.action == "dismiss":
            held = next((position_id for position_id, holder in positions.items() if holder == command.member_id), None)
            if held is None or held == _leader_position(command.kind):
                raise ValueError("目标当前没有可以撤除的正式职位")
            positions.pop(held, None)
            _set_affinity_delta(context.state, command.member_id, command.actor_id, -12)
            governance["unrest"] = min(100.0, float(governance["unrest"]) + 5)
            result = {"position_id": held}
        elif command.action == "expel":
            positions = {
                position_id: holder_id for position_id, holder_id in positions.items()
                if holder_id != command.member_id
            }
            ended = context.state.relations.end(
                membership.relation_id, ended_year=context.state.clock.year
            )
            metadata = dict(ended.metadata)
            metadata["end_reason"] = "intrigue_expelled"
            context.state.relations.replace_metadata(ended.relation_id, metadata)
            _set_affinity_delta(context.state, command.member_id, command.actor_id, -30)
            governance["unrest"] = min(100.0, float(governance["unrest"]) + 12)
            for edge in context.state.relations.find(
                source_id=power_id, target_id=command.member_id, kind=INTRIGUE_PRISONER
            ):
                context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
            governance["prisoner_ids"] = [
                value for value in map(str, governance.get("prisoner_ids", []))
                if value != command.member_id
            ]
        elif command.action == "imprison":
            if is_intrigue_imprisoned(context.state, command.member_id):
                raise ValueError("目标已经被关押")
            years = max(1, min(1000, int(command.years)))
            reason = command.reason.strip()[:40] or "违抗势力法令"
            edge = context.state.relations.add(
                source_id=power_id,
                target_id=command.member_id,
                kind=INTRIGUE_PRISONER,
                created_year=context.state.clock.year,
                metadata={
                    "sentence_remaining": years,
                    "sentence_units": years,
                    "reason": reason,
                    "imprisoned_by": command.actor_id,
                },
            )
            governance["prisoner_ids"] = list(dict.fromkeys([
                *map(str, governance.get("prisoner_ids", [])), command.member_id,
            ]))
            _set_affinity_delta(context.state, command.member_id, command.actor_id, -25)
            governance["fear"] = min(100.0, float(governance["fear"]) + 12)
            governance["unrest"] = min(100.0, float(governance["unrest"]) + 7)
            result = {"sentence_units": years, "reason": reason, "relation_id": edge.relation_id}
        elif command.action == "release":
            prison = context.state.relations.find(
                source_id=power_id,
                target_id=command.member_id,
                kind=INTRIGUE_PRISONER,
            )
            if not prison:
                raise ValueError("目标不在本势力监狱")
            for edge in prison:
                ended = context.state.relations.end(
                    edge.relation_id, ended_year=context.state.clock.year
                )
                metadata = dict(ended.metadata)
                metadata["end_reason"] = "released"
                context.state.relations.replace_metadata(ended.relation_id, metadata)
            governance["prisoner_ids"] = [
                value for value in map(str, governance.get("prisoner_ids", []))
                if value != command.member_id
            ]
            governance["fear"] = max(0.0, float(governance["fear"]) - 3)
        elif command.action in {"reward", "punish"}:
            contribution = dict(governance.get("member_contribution", {}))
            delta = 10 if command.action == "reward" else -10
            contribution[command.member_id] = int(contribution.get(command.member_id, 0)) + delta
            governance["member_contribution"] = contribution
            _set_affinity_delta(
                context.state,
                command.member_id,
                command.actor_id,
                6 if command.action == "reward" else -8,
            )
            if command.action == "punish":
                governance["fear"] = min(100.0, float(governance["fear"]) + 3)
            result = {"contribution_delta": delta}
        else:
            raise ValueError("未知人事操作")

        governance["positions"] = positions
        history = list(governance.get("personnel_history", []))
        history.append({
            "year": context.state.clock.year,
            "actor_id": command.actor_id,
            "member_id": command.member_id,
            "action": command.action,
            **result,
        })
        governance["personnel_history"] = history[-100:]
        context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
        context.emit(
            "dlc.intrigue.personnel.resolved",
            source=INTRIGUE_DLC,
            scope=EventScope("faction", power_id),
            payload={
                "power_id": power_id,
                "kind": command.kind,
                "actor_id": command.actor_id,
                "member_id": command.member_id,
                "action": command.action,
                **result,
            },
        )

    return handler


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        if not _loaded(definitions):
            return
        actor_id = context.state.controlled_entity_id
        if actor_id is None:
            return
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        unit_years = definitions.action_time(str(cultivation["realm_id"]), 1)
        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        if elapsed <= 0:
            return
        completed_any = False
        for power_id in context.state.entities.with_component(INTRIGUE_GOVERNANCE):
            governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
            total = float(governance.get("time_progress", 0.0)) + elapsed / unit_years
            completed = int(total + 1e-12)
            governance["time_progress"] = total - completed
            if completed:
                completed_any = True
                active_ids: list[str] = []
                for edge in list(context.state.relations.find(
                    source_id=power_id, kind=INTRIGUE_PRISONER
                )):
                    metadata = dict(edge.metadata)
                    remaining = max(0, int(metadata.get("sentence_remaining", 0)) - completed)
                    metadata["sentence_remaining"] = remaining
                    if remaining:
                        context.state.relations.replace_metadata(edge.relation_id, metadata)
                        active_ids.append(edge.target_id)
                    else:
                        ended = context.state.relations.end(
                            edge.relation_id, ended_year=context.state.clock.year
                        )
                        metadata = dict(ended.metadata)
                        metadata["sentence_remaining"] = 0
                        metadata["end_reason"] = "sentence_completed"
                        context.state.relations.replace_metadata(edge.relation_id, metadata)
                        context.emit(
                            "dlc.intrigue.prisoner.released",
                            source=INTRIGUE_DLC,
                            scope=EventScope("faction", power_id),
                            payload={
                                "power_id": power_id,
                                "character_id": edge.target_id,
                                "reason": "sentence_completed",
                            },
                        )
                governance["prisoner_ids"] = list(dict.fromkeys(active_ids))
            context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
        if completed_any:
            _maybe_offer_player_guest_invitation(context, definitions, actor_id)

    return handler


def _maybe_offer_player_guest_invitation(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
) -> None:
    if definitions.realm_index(str(context.state.entities.require(
        actor_id, CULTIVATION
    )["realm_id"])) < _decision_threshold(definitions, "sect"):
        return
    if any(
        isinstance(context.state.entities.require(power_id, INTRIGUE_GOVERNANCE).get(
            "pending_guest_invitation"
        ), dict)
        and context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)[
            "pending_guest_invitation"
        ].get("target_id") == actor_id
        for power_id in context.state.entities.with_component(INTRIGUE_GOVERNANCE)
    ):
        return
    if context.rng.random() >= 0.08:
        return
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    candidates = []
    for power_id in context.state.entities.with_component(FACTION_PROFILE):
        profile = context.state.entities.require(power_id, FACTION_PROFILE)
        if (
            bool(profile.get("active", True))
            and profile.get("world_id") == world_id
            and _membership(context.state, "sect", actor_id, power_id) is None
            and not context.state.relations.find(
                source_id=power_id, target_id=actor_id, kind=INTRIGUE_GUEST
            )
        ):
            candidates.append(power_id)
    if not candidates:
        return
    power_id = context.rng.choice(sorted(candidates))
    governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
    governance["pending_guest_invitation"] = {
        "target_id": actor_id,
        "invited_by": _controller_id(context.state, "sect", power_id),
        "title": "客卿长老",
        "world_id": world_id,
    }
    context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
    context.emit(
        "dlc.intrigue.guest.invited",
        source=INTRIGUE_DLC,
        scope=EventScope.entity(actor_id),
        payload={"power_id": power_id, "target_id": actor_id},
    )


def _on_character_unavailable(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        member_id = str(
            event.payload.get("entity_id") or event.payload.get("character_id") or ""
        )
        if not member_id:
            return
        for power_id in context.state.entities.with_component(INTRIGUE_GOVERNANCE):
            _clear_personnel_reference(
                context, definitions, power_id, member_id, reason=event.event_type
            )
            for edge in context.state.relations.find(
                source_id=power_id, target_id=member_id, kind=INTRIGUE_GUEST
            ):
                context.state.relations.end(
                    edge.relation_id, ended_year=context.state.clock.year
                )
                _remove_guest_from_active_wars(context.state, power_id, member_id)
            governance = context.state.entities.require(power_id, INTRIGUE_GOVERNANCE)
            pending = governance.get("pending_recruitment")
            if isinstance(pending, dict):
                pending["candidate_ids"] = [
                    value for value in map(str, pending.get("candidate_ids", []))
                    if value != member_id
                ]
                governance["pending_recruitment"] = pending
            invitation = governance.get("pending_guest_invitation")
            if isinstance(invitation, dict) and invitation.get("target_id") == member_id:
                governance["pending_guest_invitation"] = None
            context.state.entities.put(power_id, INTRIGUE_GOVERNANCE, governance)
    return handler


def _on_faction_member_left(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        member_id = str(event.payload.get("character_id", ""))
        power_id = str(event.payload.get("faction_id", ""))
        if member_id and power_id:
            _clear_personnel_reference(
                context,
                definitions,
                power_id,
                member_id,
                reason="faction_member_left",
            )
    return handler


def _on_faction_control_changed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        power_id = str(event.payload.get("faction_id", ""))
        if power_id and context.state.entities.get(power_id, INTRIGUE_GOVERNANCE):
            _normalize_governance(context.state, definitions, power_id)
    return handler


def _on_world_transition_acknowledged(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        if event.payload.get("domain") != "factions":
            return
        handover = event.payload.get("handover")
        if not isinstance(handover, dict):
            return
        power_id = str(handover.get("faction_id", ""))
        if power_id and context.state.entities.get(power_id, INTRIGUE_GOVERNANCE):
            _normalize_governance(context.state, definitions, power_id)
    return handler


def _on_power_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        power_id = str(event.payload.get("faction_id") or event.payload.get("family_id") or "")
        if power_id and _loaded(definitions):
            _normalize_governance(context.state, definitions, power_id)
    return handler


def intrigue_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        position_tables = {
            kind: set(_positions(definitions, kind)) for kind in ("sect", "family")
        }
        prisoner_targets: set[str] = set()
        for power_id in state.entities.with_component(INTRIGUE_GOVERNANCE):
            kind = _power_kind(state, power_id)
            if kind is None:
                errors.append(f"内政聚合 {power_id} 不属于宗门或家族")
                continue
            governance = state.entities.require(power_id, INTRIGUE_GOVERNANCE)
            positions = dict(governance.get("positions", {}))
            if set(positions) - position_tables[kind]:
                errors.append(f"势力 {power_id} 引用了未知职位")
            holders = [str(value) for value in positions.values() if value]
            if len(holders) != len(set(holders)):
                errors.append(f"势力 {power_id} 同一人物兼任多个正式职位")
            controller_id = _controller_id(state, kind, power_id)
            leader_id = _leader_position(kind)
            for position_id, holder in positions.items():
                if not holder:
                    continue
                holder_id = str(holder)
                controller_exception = (
                    position_id == leader_id and holder_id == controller_id
                )
                if not controller_exception and _membership(state, kind, holder_id, power_id) is None:
                    errors.append(f"势力 {power_id} 职位指向非成员")
                elif not bool((state.entities.get(holder_id, LIFE) or {}).get("alive")):
                    errors.append(f"势力 {power_id} 职位指向死亡成员")
            if not 0 <= float(governance.get("unrest", -1)) <= 100:
                errors.append(f"势力 {power_id} 动荡度非法")
            if not 0 <= float(governance.get("fear", -1)) <= 100:
                errors.append(f"势力 {power_id} 威慑度非法")
            active = {
                edge.target_id for edge in state.relations.find(
                    source_id=power_id, kind=INTRIGUE_PRISONER
                )
            }
            if set(map(str, governance.get("prisoner_ids", []))) != active:
                errors.append(f"势力 {power_id} 监狱索引与关系边不一致")
            prisoner_targets.update(active)
            guests = state.relations.find(source_id=power_id, kind=INTRIGUE_GUEST)
            for edge in guests:
                if not state.entities.exists(edge.target_id):
                    errors.append(f"势力 {power_id} 客卿指向不存在的人物")
                elif not bool(state.entities.require(edge.target_id, LIFE).get("alive")):
                    errors.append(f"势力 {power_id} 保留死亡客卿")
                if _membership(state, kind, edge.target_id, power_id) is not None:
                    errors.append(f"势力 {power_id} 的客卿同时是正式成员")
            pending = governance.get("pending_recruitment")
            if isinstance(pending, dict):
                candidates = list(map(str, pending.get("candidate_ids", [])))
                if len(candidates) != len(set(candidates)):
                    errors.append(f"势力 {power_id} 扩招候选人重复")
                if any(not state.entities.exists(value) for value in candidates):
                    errors.append(f"势力 {power_id} 扩招候选人不存在")
        for edge in state.relations.find(kind=INTRIGUE_PRISONER):
            kind = _power_kind(state, edge.source_id)
            if kind is None or _membership(state, kind, edge.target_id, edge.source_id) is None:
                errors.append(f"内政监狱关系 {edge.relation_id} 不属于有效成员")
            if int(edge.metadata.get("sentence_remaining", 0)) <= 0:
                errors.append(f"内政监狱关系 {edge.relation_id} 刑期非法")
        if len(prisoner_targets) != sum(
            len(state.relations.find(target_id=target_id, kind=INTRIGUE_PRISONER))
            for target_id in prisoner_targets
        ):
            errors.append("同一人物被多个势力内政监狱同时关押")
        return errors
    return validate


def intrigue_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    if not _loaded(definitions):
        return {"enabled": False, "name": "明争暗斗：合纵连横", "sections": []}
    actor_world = str(state.entities.require(actor_id, LOCATION)["world_id"])
    preferences = state.entities.get(actor_id, PREFERENCES) or {}
    debug = bool(preferences.get("debug_world_news"))
    sections: list[dict[str, Any]] = []
    pending_invitation = None
    for power_id in state.entities.with_component(INTRIGUE_GOVERNANCE):
        invitation = state.entities.require(
            power_id, INTRIGUE_GOVERNANCE
        ).get("pending_guest_invitation")
        if not isinstance(invitation, dict) or invitation.get("target_id") != actor_id:
            continue
        kind = _power_kind(state, power_id)
        if kind is None:
            continue
        profile = _profile(state, kind, power_id)
        if profile.get("world_id") != actor_world and not debug:
            continue
        pending_invitation = {
            **invitation, "power_id": power_id, "kind": kind,
            "power_name": profile.get("name", power_id),
        }
        break
    for kind in ("sect", "family"):
        power_id = _actor_power(state, actor_id, kind)
        if power_id is None:
            continue
        profile = _profile(state, kind, power_id)
        same_world = profile.get("world_id") == actor_world
        if not same_world and not debug:
            continue
        governance = state.entities.require(power_id, INTRIGUE_GOVERNANCE)
        positions = dict(governance.get("positions", {}))
        member_rows = state.relations.find(
            target_id=power_id, kind=_membership_kind(kind)
        )
        members = []
        for edge in member_rows:
            if not state.entities.exists(edge.source_id):
                continue
            cultivation = state.entities.require(edge.source_id, CULTIVATION)
            held = next((key for key, value in positions.items() if value == edge.source_id), None)
            members.append({
                **character_view(state, edge.source_id),
                "realm_id": cultivation["realm_id"],
                "realm_index": definitions.realm_index(str(cultivation["realm_id"])),
                "layer": int(cultivation["layer"]),
                "position_id": held,
                "position": _positions(definitions, kind).get(held or "", {}).get("name"),
                "imprisoned": is_intrigue_imprisoned(state, edge.source_id),
                "contribution": int(dict(governance.get("member_contribution", {})).get(edge.source_id, 0)),
                "affinity": relationship_affinity(state, edge.source_id, actor_id),
            })
        prison = []
        for edge in state.relations.find(source_id=power_id, kind=INTRIGUE_PRISONER):
            prisoner = character_view(state, edge.target_id)
            prison.append({
                "relation_id": edge.relation_id,
                "prisoner_id": edge.target_id,
                "name": prisoner["name"],
                **dict(edge.metadata),
            })
        guests = []
        for edge in state.relations.find(source_id=power_id, kind=INTRIGUE_GUEST):
            if not state.entities.exists(edge.target_id):
                continue
            guests.append({
                **character_view(state, edge.target_id),
                "guest_id": edge.target_id,
                "defense_required": bool(edge.metadata.get("defense_required", True)),
                "offense_opt_in": bool(edge.metadata.get("offense_opt_in", False)),
                "affinity": relationship_affinity(state, edge.target_id, actor_id),
            })
        pending = governance.get("pending_recruitment")
        pending_public = None
        if isinstance(pending, dict):
            pending_public = {
                **pending,
                "candidates": [
                    {
                        **character_view(state, candidate_id),
                        "cultivation": dict(state.entities.require(candidate_id, CULTIVATION)),
                        "combat_ratio": float(dict(pending.get(
                            "combat_ratios", {}
                        )).get(candidate_id, 1.0)),
                    }
                    for candidate_id in map(str, pending.get("candidate_ids", []))
                    if state.entities.exists(candidate_id)
                ],
            }
        specs = _positions(definitions, kind)
        sections.append({
            "kind": kind,
            "id": power_id,
            "name": profile["name"],
            "same_world": same_world,
            "control_authority": same_world and _controller_id(state, kind, power_id) == actor_id,
            "unrest": round(float(governance.get("unrest", 0)), 2),
            "fear": round(float(governance.get("fear", 0)), 2),
            "resources": int(governance.get("resources", 0)),
            "policy": str(governance.get("policy", "balance")),
            "decision_threshold": _decision_threshold(definitions, kind),
            "decision_authority": same_world and _decision_authority(
                state, definitions, kind, power_id, actor_id
            ),
            "positions": [
                {
                    "id": position_id,
                    **spec,
                    "holder_id": positions.get(position_id),
                    "holder": (
                        character_view(state, str(positions[position_id]))
                        if positions.get(position_id) and state.entities.exists(str(positions[position_id]))
                        else None
                    ),
                }
                for position_id, spec in specs.items()
            ],
            "members": members,
            "prison": prison,
            "guests": guests,
            "resolutions": list(governance.get("resolutions", []))[-20:],
            "pending_recruitment": pending_public,
            "personnel_history": list(governance.get("personnel_history", []))[-20:],
        })
    identity = state.entities.require(actor_id, IDENTITY)
    race_id = str(identity.get("race", "human"))
    race_diplomacy = state.entities.require(actor_id, DIPLOMACY_STATE)
    sections.append({
        "kind": "race",
        "id": race_id,
        "name": dict(definitions.races.get(race_id, {})).get("name", race_id),
        "same_world": True,
        "decision_threshold": _decision_threshold(definitions, "race"),
        "decision_authority": _decision_authority(
            state, definitions, "race", race_id, actor_id
        ),
        "resolutions": list(race_diplomacy.get("intrigue_resolutions", []))[-20:],
    })
    return {
        "enabled": True,
        "name": "明争暗斗：合纵连横",
        "sections": sections,
        "resolution_types": dict(RESOLUTION_LABELS),
        "policy_types": dict(STYLE_LABELS),
        "pending_guest_invitation": pending_invitation,
    }


def register_intrigue_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(IntriguePersonnelAction, _personnel_handler(definitions))
    bus.register(IntrigueGuestAction, _guest_handler(definitions))
    bus.register(IntrigueResolutionAction, _resolution_handler(definitions))
    bus.register(IntrigueRecruitmentAction, _recruitment_handler(definitions))
    bus.event_bus.register("faction.registered", _on_power_created(definitions))
    bus.event_bus.register("faction.founded", _on_power_created(definitions))
    bus.event_bus.register("family.founded", _on_power_created(definitions))
    bus.event_bus.register(
        "faction.member.left", _on_faction_member_left(definitions)
    )
    bus.event_bus.register(
        "character.died", _on_character_unavailable(definitions)
    )
    bus.event_bus.register(
        "faction.control.transferred", _on_faction_control_changed(definitions)
    )
    bus.event_bus.register(
        "faction.control.restored", _on_faction_control_changed(definitions)
    )
    bus.event_bus.register(
        "faction.control.vacant", _on_faction_control_changed(definitions)
    )
    bus.event_bus.register(
        "world.transition.acknowledged",
        _on_world_transition_acknowledged(definitions),
    )
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))
