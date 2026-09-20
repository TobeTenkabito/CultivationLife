from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .character import IDENTITY, LIFE, character_view, create_character
from .combat import combat_snapshot, resolve_combat
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


FACTION_PROFILE = "faction.profile"
FACTION_GOVERNANCE = "faction.governance"
MEMBERSHIP = "faction_membership"
FACTION_NPC = "faction.npc_profile"
DIPLOMACY_STATE = "governance.diplomacy"
RACE_SUPPORT = "governance.race_support"


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


@dataclass(frozen=True, slots=True)
class InviteRelationshipToFaction:
    actor_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class SetFactionRewardPreference:
    actor_id: str
    reward_id: str


@dataclass(frozen=True, slots=True)
class ArrangeFactionSuccession:
    actor_id: str


@dataclass(frozen=True, slots=True)
class DispatchFactionMember:
    actor_id: str
    target: str


@dataclass(frozen=True, slots=True)
class InterceptFactionMember:
    actor_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class ProposeDiplomacy:
    actor_id: str
    kind: str
    target_id: str
    status: str


@dataclass(frozen=True, slots=True)
class TransferVassalPersonnel:
    actor_id: str
    kind: str
    target_id: str
    character_id: str


@dataclass(frozen=True, slots=True)
class EnsureFactionRosters:
    """Idempotently materialize definition rosters in migrated V2 saves."""

    allow_during_interaction: ClassVar[bool] = True
    allow_during_court_election: ClassVar[bool] = True


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
            "roster_seeded": False,
            "last_recruitment_year": context.state.clock.year,
        },
    )
    context.state.entities.put(
        faction_id,
        FACTION_GOVERNANCE,
        {
            "creator_id": creator_id,
            "controller_id": creator_id,
            "designated_successor_id": None,
            "last_ascension_handover": None,
            "pressure": 0,
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
            # V1 factions existed as living powers from the first year.  A
            # lazy roster made every faction the player had not joined an
            # empty shell, so there was nobody to cultivate, die or fight.
            _seed_definition_roster(context, definitions, faction_id)

    return handler


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(
        str(event.payload["entity_id"]), DIPLOMACY_STATE, {"relations": {}}
    )


def _definition_for_faction(
    state: WorldState, definitions: GameDefinitions, faction_id: str,
):
    profile = state.entities.require(faction_id, FACTION_PROFILE)
    external_id = profile.get("external_id")
    return definitions.factions.get(str(external_id)) if external_id else None


def _seed_definition_roster(
    context: SimulationContext, definitions: GameDefinitions, faction_id: str,
) -> list[str]:
    profile = context.state.entities.require(faction_id, FACTION_PROFILE)
    if bool(profile.get("roster_seeded")):
        return []
    # Mark first because each membership emits faction.member.joined.
    profile["roster_seeded"] = True
    context.state.entities.put(faction_id, FACTION_PROFILE, profile)
    definition = _definition_for_faction(context.state, definitions, faction_id)
    if definition is None:
        return []
    created: list[str] = []
    for row in definition.npcs:
        realm_index = max(0, min(len(definitions.realms) - 1, int(row["realm_index"])))
        character_id = create_character(
            context,
            name=str(row["name"]),
            age=int(row.get("age", 16)),
            # Definition rosters are world state, not a player roll.  Keep
            # their missing gender deterministic without consuming the
            # gameplay RNG merely because eager world simulation is enabled.
            gender=str(row.get("gender") or (
                "female"
                if sum(str(row.get("id", row["name"])).encode("utf-8")) % 2
                else "male"
            )),
            race=str(row.get("race", definition.allegiance_race)),
            spirit_root=str(row.get("spirit_root", "none")),
            path=str(row.get("path", "dao")),
            realm_id=definitions.realms[realm_index].id,
            layer=int(row.get("layer", 1)),
            world_id=str(row.get("world", definition.world_id)),
            lifespan=(None if row.get("lifespan") is None else int(row["lifespan"])),
        )
        context.state.entities.put(character_id, FACTION_NPC, {
            "external_id": str(row.get("id", "")),
            "title": str(row.get("title", "门人")),
            "cultivation_progress": 0.0,
            "last_dispatch_year": None,
        })
        _add_membership(
            context, character_id=character_id, faction_id=faction_id, role="member"
        )
        created.append(character_id)
    return created


def _seed_player_followers(
    context: SimulationContext, definitions: GameDefinitions,
    faction_id: str, founder_id: str,
) -> None:
    profile = context.state.entities.require(faction_id, FACTION_PROFILE)
    if bool(profile.get("roster_seeded")):
        return
    profile["roster_seeded"] = True
    context.state.entities.put(faction_id, FACTION_PROFILE, profile)
    founder = context.state.entities.require(founder_id, IDENTITY)
    cultivation = context.state.entities.require(founder_id, CULTIVATION)
    founder_realm = definitions.realm_index(str(cultivation["realm_id"]))
    realm_index = 0 if founder_realm == 0 else max(1, founder_realm - 1)
    for index, name in enumerate(("沈砚", "叶舟")):
        realm = definitions.realms[realm_index]
        layer = 1 if realm_index == 0 else context.rng.randint(1, min(3, realm.layers))
        age = max(16, context.rng.randint(18, 40) + realm_index * 25)
        lifespan = None
        if realm.lifespan is not None:
            lifespan = max(age + 1, context.rng.randint(*realm.lifespan))
        character_id = create_character(
            context, name=name, age=age,
            gender="male" if index == 0 else "female",
            race=str(founder["race"]),
            spirit_root="none" if realm_index == 0 else "supreme_wood",
            path=str(cultivation["path"]), realm_id=realm.id, layer=layer,
            world_id=str(profile["world_id"]), lifespan=lifespan,
        )
        context.state.entities.put(character_id, FACTION_NPC, {
            "external_id": f"founder_follower_{index}", "title": "开山门人",
            "cultivation_progress": 0.0, "last_dispatch_year": None,
        })
        _add_membership(
            context, character_id=character_id, faction_id=faction_id, role="member"
        )


def _ensure_faction_rosters_handler(
    definitions: GameDefinitions,
):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, EnsureFactionRosters):
            raise TypeError("命令类型错误")
        for faction_id in context.state.entities.with_component(FACTION_PROFILE):
            profile = context.state.entities.require(faction_id, FACTION_PROFILE)
            if bool(profile.get("active")) and profile.get("external_id"):
                _seed_definition_roster(context, definitions, faction_id)

    return handler


def _active_membership(state: WorldState, character_id: str):
    memberships = state.relations.find(source_id=character_id, kind=MEMBERSHIP)
    if len(memberships) > 1:
        raise ValueError("角色同时拥有多个有效势力身份")
    return memberships[0] if memberships else None


def _allegiance_race(state: WorldState, character_id: str) -> str:
    membership = _active_membership(state, character_id)
    if membership is not None:
        profile = state.entities.get(membership.target_id, FACTION_PROFILE)
        if profile and profile.get("allegiance_race"):
            return str(profile["allegiance_race"])
    return str(state.entities.require(character_id, IDENTITY)["race"])


def _add_membership(
    context: SimulationContext,
    *,
    character_id: str,
    faction_id: str,
    role: str,
) -> str:
    if role not in {"member", "guest", "leader", "founder"}:
        raise ValueError("未知势力身份")
    if not bool(context.state.entities.require(character_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能加入势力")
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


def _found_faction_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
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
            context, name=name, world_id=world_id, external_id=None,
            creator_id=command.founder_id, path="player_created",
            allegiance_race=str(identity["race"]), description="由玩家创建的势力",
            color="#6f7b88",
        )
        _add_membership(
            context, character_id=command.founder_id,
            faction_id=faction_id, role="founder",
        )
        _seed_player_followers(context, definitions, faction_id, command.founder_id)
        context.emit(
            "faction.founded", source="factions",
            scope=EventScope("faction", faction_id),
            payload={"faction_id": faction_id, "founder_id": command.founder_id, "name": name},
        )

    return handler


def _join_faction_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, JoinFaction):
            raise TypeError("命令类型错误")
        if not context.state.entities.exists(command.character_id):
            raise ValueError("角色不存在")
        if not context.state.entities.exists(command.faction_id):
            raise ValueError("势力不存在")
        _seed_definition_roster(context, definitions, command.faction_id)
        _add_membership(
            context, character_id=command.character_id,
            faction_id=command.faction_id, role=command.role,
        )

    return handler


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


def _on_story_contribution_changed(context: SimulationContext, event: EventEnvelope) -> None:
    character_id = str(event.payload["entity_id"])
    membership = _active_membership(context.state, character_id)
    if membership is None:
        raise ValueError("当前没有可结算贡献的势力身份")
    _change_contribution(context, ChangeContribution(
        character_id=character_id,
        faction_id=membership.target_id,
        amount=int(event.payload["amount"]),
        reason="story",
    ))


def _transfer_control(context: SimulationContext, command: object) -> None:
    if not isinstance(command, TransferFactionControl):
        raise TypeError("命令类型错误")
    governance = context.state.entities.require(command.faction_id, FACTION_GOVERNANCE)
    if governance.get("controller_id") != command.actor_id:
        raise ValueError("当前角色没有该势力控制权")
    profile = context.state.entities.require(command.faction_id, FACTION_PROFILE)
    actor_location = context.state.entities.require(command.actor_id, LOCATION)
    if actor_location.get("world_id") != profile.get("world_id"):
        raise ValueError("身处其他世界时不能控制该势力")
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


def _invite_relationship(context: SimulationContext, command: object) -> None:
    if not isinstance(command, InviteRelationshipToFaction):
        raise TypeError("命令类型错误")
    if command.actor_id != context.state.controlled_entity_id:
        raise ValueError("只能由当前角色引荐入宗")
    membership = _active_membership(context.state, command.actor_id)
    if membership is None:
        raise ValueError("当前角色没有可以引荐他人的势力")
    profile = context.state.entities.require(membership.target_id, FACTION_PROFILE)
    actor_location = context.state.entities.require(command.actor_id, LOCATION)
    if actor_location.get("world_id") != profile.get("world_id"):
        raise ValueError("当前世界没有可以引荐他人的势力")
    eligible = None
    for edge in context.state.relations.involving(command.actor_id):
        other_id = edge.target_id if edge.source_id == command.actor_id else edge.source_id
        if other_id != command.target_id:
            continue
        if edge.kind in {"friend", "dao_companion"}:
            eligible = edge
            break
        # V1 permits inviting one's master, but not one's disciples.
        if (
            edge.kind == "master_disciple"
            and edge.source_id == command.target_id
            and edge.target_id == command.actor_id
        ):
            eligible = edge
            break
    if eligible is None:
        raise ValueError("只能邀请当前世界中存活的师父、道侣或道友")
    metadata = dict(eligible.metadata)
    metadata["affinity"] = float(metadata.get("affinity", 0.0)) + 4.0
    context.state.relations.replace_metadata(eligible.relation_id, metadata)
    relation_id = _add_membership(
        context,
        character_id=command.target_id,
        faction_id=membership.target_id,
        role="member",
    )
    context.emit(
        "faction.relationship.invited",
        source="factions",
        scope=EventScope("faction", membership.target_id),
        payload={
            "actor_id": command.actor_id,
            "character_id": command.target_id,
            "faction_id": membership.target_id,
            "membership_id": relation_id,
            "relationship_id": eligible.relation_id,
        },
    )


def _set_reward_preference(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SetFactionRewardPreference):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能设置当前角色的宗门奖励")
        membership = _active_membership(context.state, command.actor_id)
        if membership is None:
            raise ValueError("当前角色没有宗门身份")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        if definitions.realm_index(str(cultivation["realm_id"])) < 4:
            raise ValueError("进入元婴初期后方可固定年度奖励")
        if command.reward_id not in definitions.faction_rewards:
            raise ValueError("未知宗门奖励")
        metadata = dict(membership.metadata)
        metadata["reward_preference"] = command.reward_id
        context.state.relations.replace_metadata(membership.relation_id, metadata)
        context.emit(
            "faction.reward.preference.changed",
            source="factions",
            scope=EventScope("faction", membership.target_id),
            payload={
                "character_id": command.actor_id,
                "faction_id": membership.target_id,
                "reward_id": command.reward_id,
            },
        )

    return handler


def _same_world_faction(context: SimulationContext, actor_id: str):
    membership = _active_membership(context.state, actor_id)
    if membership is None:
        raise ValueError("当前角色没有宗门身份")
    profile = context.state.entities.require(membership.target_id, FACTION_PROFILE)
    location = context.state.entities.require(actor_id, LOCATION)
    if profile.get("world_id") != location.get("world_id") or not bool(profile.get("active")):
        raise ValueError("身处其他世界时不能处理该宗门事务")
    return membership, profile


def _arrange_succession_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ArrangeFactionSuccession):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能安排当前角色的宗门后事")
        membership, profile = _same_world_faction(context, command.actor_id)
        governance = context.state.entities.require(membership.target_id, FACTION_GOVERNANCE)
        if governance.get("creator_id") != command.actor_id or governance.get("controller_id") != command.actor_id:
            raise ValueError("只有仍在执掌亲手创建宗门时才能安排让权")
        if not bool(profile.get("roster_seeded")):
            _seed_player_followers(
                context, definitions, membership.target_id, command.actor_id
            )
        candidates: list[tuple[int, int, int, str]] = []
        for edge in context.state.relations.find(target_id=membership.target_id, kind=MEMBERSHIP):
            if edge.source_id == command.actor_id:
                continue
            life = context.state.entities.require(edge.source_id, LIFE)
            location = context.state.entities.require(edge.source_id, LOCATION)
            if not bool(life.get("alive")) or location.get("world_id") != profile.get("world_id"):
                continue
            cultivation = context.state.entities.require(edge.source_id, CULTIVATION)
            candidates.append((
                definitions.realm_index(str(cultivation["realm_id"])),
                int(cultivation["layer"]),
                -(context.state.clock.year - int(life["birth_year"])),
                edge.source_id,
            ))
        if not candidates:
            raise ValueError("宗门中没有能够承接权柄的在世门人")
        successor_id = max(candidates)[3]
        governance["designated_successor_id"] = successor_id
        governance["succession_arranged_year"] = context.state.clock.year
        context.state.entities.put(membership.target_id, FACTION_GOVERNANCE, governance)
        context.emit(
            "faction.succession.arranged", source="factions",
            scope=EventScope("faction", membership.target_id),
            payload={"faction_id": membership.target_id, "founder_id": command.actor_id, "successor_id": successor_id},
        )

    return handler


def _market_tier(definitions: GameDefinitions, actor_id: str, state: WorldState) -> int:
    cultivation = state.entities.require(actor_id, CULTIVATION)
    world_id = str(state.entities.require(actor_id, LOCATION)["world_id"])
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    if realm_index == 0:
        return 0
    if world_id == "celestial":
        return max(9, min(12, realm_index))
    if definitions.worlds[world_id].tier == 2:
        return max(5, min(8, realm_index))
    return min(5, max(1, realm_index))


def _dispatch_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, DispatchFactionMember):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色派遣门人")
        if command.target not in {"item", "technique"}:
            raise ValueError("未知派遣目标")
        membership, profile = _same_world_faction(context, command.actor_id)
        _seed_definition_roster(context, definitions, membership.target_id)
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        if definitions.realm_index(str(cultivation["realm_id"])) < 4:
            raise ValueError("成为元婴期宗门股东后方可派遣弟子")
        metadata = dict(membership.metadata)
        if metadata.get("last_dispatch_year") == context.state.clock.year:
            raise ValueError("本年度已经派遣过弟子")
        rules = dict(definitions.systems.get("factions", {}))
        cost = int(rules.get("disciple_dispatch_cost", 2))
        if int(metadata.get("contribution", 0)) < cost:
            raise ValueError(f"派遣弟子需要 {cost} 点宗门贡献")
        metadata["contribution"] = int(metadata.get("contribution", 0)) - cost
        metadata["last_dispatch_year"] = context.state.clock.year
        context.state.relations.replace_metadata(membership.relation_id, metadata)
        world_id = str(profile["world_id"])
        tier = _market_tier(definitions, command.actor_id, context.state)
        pool = [
            good for good in definitions.market_goods
            if good.world_id == world_id and good.tier == tier and good.kind == command.target
        ]
        if command.target == "technique":
            known = set(map(str, context.state.entities.require(command.actor_id, "cultivation.practice").get("known_techniques", [])))
            root = definitions.roots[str(cultivation["spirit_root"])]
            def compatible(content_id: str) -> bool:
                technique = definitions.techniques[content_id]
                if technique.element in {"neutral", "sex"}:
                    return True
                if technique.element == "five_elements":
                    return {"metal", "wood", "water", "fire", "earth"} <= set(root.elements)
                return technique.element in set(root.elements)
            pool = [
                good for good in pool
                if good.content_id not in known and compatible(good.content_id)
            ]
        success = bool(pool) and context.rng.random() < float(rules.get("disciple_dispatch_success", 0.72))
        content_id = context.rng.choice(pool).content_id if success else None
        if content_id is not None:
            event_type = "story.effect.inventory.changed" if command.target == "item" else "relationship.technique.granted"
            payload = {"entity_id": command.actor_id}
            if command.target == "item":
                payload.update(item_id=content_id, quantity=1, reason="faction_dispatch")
            else:
                payload.update(technique_id=content_id, equip_main=False)
            context.emit(event_type, source="factions", scope=EventScope.entity(command.actor_id), payload=payload)
        context.emit(
            "faction.member.dispatched", source="factions",
            scope=EventScope("faction", membership.target_id),
            payload={
                "actor_id": command.actor_id, "faction_id": membership.target_id,
                "target": command.target, "cost": cost, "success": success,
                "content_id": content_id,
            },
        )

    return handler


def _intercept_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, InterceptFactionMember):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色发起截杀")
        membership, profile = _same_world_faction(context, command.actor_id)
        target_membership = _active_membership(context.state, command.target_id)
        if target_membership is None or target_membership.target_id != membership.target_id:
            raise ValueError("目标已不在当前宗门名册中")
        target_location = context.state.entities.require(command.target_id, LOCATION)
        target_life = context.state.entities.require(command.target_id, LIFE)
        if target_location.get("world_id") != profile.get("world_id") or not bool(target_life.get("alive")):
            raise ValueError("目标已不在当前宗门名册中")
        from .intrigue import is_intrigue_imprisoned

        if is_intrigue_imprisoned(context.state, command.target_id):
            raise ValueError("目标正在势力监狱服刑")
        context.state.entities.put(
            command.target_id,
            LOCATION,
            dict(context.state.entities.require(command.actor_id, LOCATION)),
        )
        resolve_combat(
            context, definitions, attacker_id=command.actor_id,
            target_id=command.target_id, objective="kill",
        )
        context.emit(
            "faction.member.intercepted", source="factions",
            scope=EventScope("faction", membership.target_id),
            payload={"actor_id": command.actor_id, "target_id": command.target_id, "faction_id": membership.target_id},
        )

    return handler


def _resolve_faction_id(state: WorldState, value: str) -> str | None:
    if state.entities.get(value, FACTION_PROFILE) is not None:
        return value
    return next((
        faction_id for faction_id in state.entities.with_component(FACTION_PROFILE)
        if str(state.entities.require(faction_id, FACTION_PROFILE).get("external_id")) == value
    ), None)


def _governance_threshold(definitions: GameDefinitions, world_id: str) -> int:
    return int(dict(definitions.systems.get("player_faction", {})).get(
        "governance_threshold", {}
    ).get(world_id, 4))


def _has_faction_voice(
    state: WorldState, definitions: GameDefinitions, actor_id: str, faction_id: str,
) -> bool:
    profile = state.entities.require(faction_id, FACTION_PROFILE)
    governance = state.entities.require(faction_id, FACTION_GOVERNANCE)
    if state.entities.require(actor_id, LOCATION).get("world_id") != profile.get("world_id"):
        return False
    cultivation = state.entities.require(actor_id, CULTIVATION)
    return bool(
        governance.get("controller_id") == actor_id
        or definitions.realm_index(str(cultivation["realm_id"]))
        >= _governance_threshold(definitions, str(profile["world_id"]))
    )


def _diplomacy_key(kind: str, first_id: str, second_id: str) -> str:
    first, second = sorted((first_id, second_id))
    return f"{kind}:{first}:{second}"


def _vote_probability(affinity: float, status: str, voter_affinity: float = 0.0) -> float:
    if status == "war":
        base = 0.48 - affinity / 220
    elif status in {"alliance", "vassal"}:
        base = 0.48 + affinity / 220
    elif status == "truce":
        base = 0.68 if affinity < 0 else 0.48
    else:
        base = 0.56
    return max(0.08, min(0.92, base + voter_affinity / 500))


def _propose_diplomacy_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        from .intrigue import is_intrigue_imprisoned

        if not isinstance(command, ProposeDiplomacy):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色提出外交决议")
        if command.kind not in {"race", "faction"}:
            raise ValueError("未知势力类型")
        if command.status not in {"war", "alliance", "truce", "neutral", "vassal"}:
            raise ValueError("未知外交决议")
        if command.kind == "faction":
            membership, own_profile = _same_world_faction(context, command.actor_id)
            world_id = str(own_profile["world_id"])
            own_id = membership.target_id
            target_id = _resolve_faction_id(context.state, command.target_id)
            if target_id is None or target_id == own_id:
                raise ValueError("目标宗门无效")
            target_profile = context.state.entities.require(target_id, FACTION_PROFILE)
            if not bool(target_profile.get("active")) or target_profile.get("world_id") != world_id:
                raise ValueError("目标宗门无效")
            if not _has_faction_voice(context.state, definitions, command.actor_id, own_id):
                raise ValueError("你尚未取得当前宗门的外交话语权")
            _seed_definition_roster(context, definitions, own_id)
            _seed_definition_roster(context, definitions, target_id)
            voter_ids = [
                edge.source_id for edge in context.state.relations.find(target_id=own_id, kind=MEMBERSHIP)
                if edge.source_id != command.actor_id
                and bool(context.state.entities.require(edge.source_id, LIFE).get("alive"))
                and not is_intrigue_imprisoned(context.state, edge.source_id)
                and definitions.realm_index(str(context.state.entities.require(edge.source_id, CULTIVATION)["realm_id"]))
                >= _governance_threshold(definitions, world_id)
            ]
        else:
            world_id = str(context.state.entities.require(
                command.actor_id, LOCATION
            )["world_id"])
            own_id = _allegiance_race(context.state, command.actor_id)
            target_id = command.target_id
            cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
            required = int(definitions.systems["world_travel"]["required_realm"])
            known_races = {
                str(context.state.entities.require(entity_id, IDENTITY)["race"])
                for entity_id in context.state.entities.with_component(IDENTITY)
                if context.state.entities.require(entity_id, LOCATION).get("world_id") == world_id
            } | {
                str(profile.get("allegiance_race"))
                for faction_id in context.state.entities.with_component(FACTION_PROFILE)
                for profile in [context.state.entities.require(faction_id, FACTION_PROFILE)]
                if profile.get("world_id") == world_id
            }
            if definitions.worlds[world_id].tier < 2 or own_id != "human" or definitions.realm_index(str(cultivation["realm_id"])) < required:
                raise ValueError("只有身处种族上界的人族大乘才能发起种族外交表决")
            if target_id == own_id or target_id not in known_races:
                raise ValueError("目标种族无效")
            voter_ids = [
                entity_id for entity_id in context.state.entities.with_component(IDENTITY)
                if entity_id != command.actor_id
                and context.state.entities.get(entity_id, "world.npc_profile") is None
                and context.state.entities.require(entity_id, IDENTITY).get("race") == own_id
                and context.state.entities.require(entity_id, LOCATION).get("world_id") == world_id
                and bool(context.state.entities.require(entity_id, LIFE).get("alive"))
                and not is_intrigue_imprisoned(context.state, entity_id)
                and definitions.realm_index(str(context.state.entities.require(entity_id, CULTIVATION)["realm_id"])) >= required
            ]
        state = context.state.entities.require(command.actor_id, DIPLOMACY_STATE)
        relations = dict(state.get("relations", {}))
        key = _diplomacy_key(command.kind, own_id, target_id)
        relation = dict(relations.get(key, {
            "kind": command.kind, "first_id": min(own_id, target_id),
            "second_id": max(own_id, target_id), "status": "neutral",
            "affinity": 0.0, "since_year": context.state.clock.year,
        }))
        if relation.get("status") == "war" and command.status != "war":
            raise ValueError("战争已经进入征伐阶段，请在战争事务中依据战果和谈")
        ballots = [{"entity_id": command.actor_id, "vote": True, "player": True}]
        for voter_id in sorted(set(voter_ids)):
            social = context.state.entities.get(voter_id, "relations.social_profile") or {}
            voter_affinity = float(dict(social.get("affinities", {})).get(command.actor_id, 0.0))
            chance = _vote_probability(float(relation.get("affinity", 0.0)), command.status, voter_affinity)
            ballots.append({"entity_id": voter_id, "vote": context.rng.random() < chance, "chance": round(chance, 3), "player": False})
        yes = sum(bool(row["vote"]) for row in ballots)
        passed = yes > len(ballots) / 2
        if passed:
            relation.update(
                status=command.status,
                affinity=float({"war": -75, "alliance": 80, "truce": -5, "neutral": 0, "vassal": 65}[command.status]),
                since_year=context.state.clock.year,
                overlord=own_id if command.status == "vassal" else None,
                subject=target_id if command.status == "vassal" else None,
            )
        relation["last_vote"] = {
            "year": context.state.clock.year, "proposal": command.status,
            "yes": yes, "total": len(ballots), "passed": passed, "ballots": ballots,
        }
        relations[key] = relation
        state["relations"] = relations
        context.state.entities.put(command.actor_id, DIPLOMACY_STATE, state)
        context.emit(
            "governance.diplomacy.voted", source="factions",
            scope=EventScope("world", world_id),
            payload={"actor_id": command.actor_id, "key": key, "passed": passed, "relation": relation},
        )

    return handler


def _transfer_vassal_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, TransferVassalPersonnel):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能由当前角色调动人事")
        if command.kind not in {"race", "faction"}:
            raise ValueError("未知势力类型")
        if command.kind == "faction":
            membership, own_profile = _same_world_faction(context, command.actor_id)
            own_id = membership.target_id
            destination_world = str(own_profile["world_id"])
        else:
            membership = None
            own_id = _allegiance_race(context.state, command.actor_id)
            destination_world = str(context.state.entities.require(
                command.actor_id, LOCATION
            )["world_id"])
        target_id = command.target_id
        if command.kind == "faction":
            resolved = _resolve_faction_id(context.state, target_id)
            if resolved is None:
                raise ValueError("附庸宗门不存在")
            target_id = resolved
        state = context.state.entities.require(command.actor_id, DIPLOMACY_STATE)
        relation = dict(dict(state.get("relations", {})).get(
            _diplomacy_key(command.kind, own_id, target_id), {}
        ))
        if relation.get("status") != "vassal" or relation.get("overlord") != own_id or relation.get("subject") != target_id:
            raise ValueError("只有被依附方可以从附庸势力调动同级以下人事")
        candidate = _active_membership(context.state, command.character_id)
        identity = context.state.entities.require(command.character_id, IDENTITY)
        if command.kind == "faction":
            if candidate is None or candidate.target_id != target_id:
                raise ValueError("目标不是附庸宗门成员")
        elif identity.get("race") != target_id:
            raise ValueError("目标不属于该附庸种族")
        location = context.state.entities.require(command.character_id, LOCATION)
        life = context.state.entities.require(command.character_id, LIFE)
        actor_cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        target_cultivation = context.state.entities.require(command.character_id, CULTIVATION)
        from .intrigue import is_intrigue_imprisoned

        if (
            location.get("world_id") != destination_world
            or not bool(life.get("alive"))
            or is_intrigue_imprisoned(context.state, command.character_id)
            or (
                definitions.realm_index(str(target_cultivation["realm_id"])), int(target_cultivation["layer"])
            ) > (
                definitions.realm_index(str(actor_cultivation["realm_id"])), int(actor_cultivation["layer"])
            )
        ):
            raise ValueError("只能调动当前界面内、修为不高于你的附庸修士")
        if candidate is not None:
            ended = context.state.relations.end(candidate.relation_id, ended_year=context.state.clock.year)
            metadata = dict(ended.metadata)
            metadata["end_reason"] = "vassal_transfer"
            context.state.relations.replace_metadata(ended.relation_id, metadata)
        npc_profile = context.state.entities.get(command.character_id, FACTION_NPC) or {}
        npc_profile["title"] = "附庸外援"
        context.state.entities.put(command.character_id, FACTION_NPC, npc_profile)
        if command.kind == "faction":
            assert membership is not None
            _add_membership(
                context, character_id=command.character_id,
                faction_id=membership.target_id, role="guest",
            )
            scope = EventScope("faction", membership.target_id)
        else:
            context.state.relations.add(
                source_id=command.actor_id, target_id=command.character_id,
                kind=RACE_SUPPORT, created_year=context.state.clock.year,
                metadata={"race_id": own_id, "source_race_id": target_id},
            )
            scope = EventScope("world", destination_world)
        context.emit(
            "governance.vassal_personnel.transferred", source="factions",
            scope=scope,
            payload={"actor_id": command.actor_id, "character_id": command.character_id, "kind": command.kind, "subject_id": target_id},
        )

    return handler


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = context.state.controlled_entity_id
        if actor_id is None:
            return
        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        membership = _active_membership(context.state, actor_id)
        if elapsed <= 0 or membership is None:
            return
        life = context.state.entities.require(actor_id, LIFE)
        if not bool(life.get("alive")):
            return
        profile = context.state.entities.require(membership.target_id, FACTION_PROFILE)
        if not bool(profile.get("roster_seeded")):
            governance = context.state.entities.require(
                membership.target_id, FACTION_GOVERNANCE
            )
            if governance.get("creator_id") == actor_id:
                _seed_player_followers(
                    context, definitions, membership.target_id, actor_id
                )
            else:
                _seed_definition_roster(
                    context, definitions, membership.target_id
                )
            profile = context.state.entities.require(
                membership.target_id, FACTION_PROFILE
            )
        location = context.state.entities.require(actor_id, LOCATION)
        if not bool(profile.get("active")) or profile.get("world_id") != location.get("world_id"):
            return
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        metadata = dict(membership.metadata)
        benefits = dict(metadata.get("permanent_benefits", {}))
        rewards = sorted(definitions.faction_rewards)
        for offset in range(1, elapsed + 1):
            preferred = str(metadata.get("reward_preference", ""))
            reward_id = preferred if realm_index >= 4 and preferred in definitions.faction_rewards else context.rng.choice(rewards)
            effect = dict(definitions.faction_rewards[reward_id]["effect"])
            opportunity = float(effect.get("opportunity", 0))
            if opportunity:
                cultivation["opportunity"] = max(
                    0.0, float(cultivation.get("opportunity", 0.0)) + opportunity
                )
            for key in ("hp", "mp", "combat"):
                amount = float(effect.get(key, 0))
                if amount:
                    benefits[key] = float(benefits.get(key, 0.0)) + amount
            metadata["contribution"] = int(metadata.get("contribution", 0)) + 1
            context.emit(
                "faction.reward.granted",
                source="factions",
                scope=EventScope("faction", membership.target_id),
                payload={
                    "character_id": actor_id,
                    "faction_id": membership.target_id,
                    "reward_id": reward_id,
                    "year": int(event.payload["from_year"]) + offset,
                },
            )
        metadata["permanent_benefits"] = benefits
        context.state.entities.put(actor_id, CULTIVATION, cultivation)
        context.state.relations.replace_metadata(membership.relation_id, metadata)

    return handler


def _dissolve_faction(
    context: SimulationContext, faction_id: str, *, reason: str,
) -> None:
    profile = context.state.entities.require(faction_id, FACTION_PROFILE)
    profile["active"] = False
    context.state.entities.put(faction_id, FACTION_PROFILE, profile)
    governance = context.state.entities.require(faction_id, FACTION_GOVERNANCE)
    governance["controller_id"] = None
    governance["positions"] = {}
    governance["prisoner_ids"] = []
    context.state.entities.put(faction_id, FACTION_GOVERNANCE, governance)
    intrigue = context.state.entities.get(
        faction_id, "dlc.intrigue.governance"
    )
    if intrigue is not None:
        intrigue["positions"] = {}
        intrigue["prisoner_ids"] = []
        context.state.entities.put(
            faction_id, "dlc.intrigue.governance", intrigue
        )
    for edge in list(context.state.relations.find(
        source_id=faction_id, kind="dlc.intrigue.prisoner"
    )):
        context.state.relations.end(
            edge.relation_id, ended_year=context.state.clock.year
        )
    for edge in list(context.state.relations.find(
        target_id=faction_id, kind=MEMBERSHIP
    )):
        ended = context.state.relations.end(
            edge.relation_id, ended_year=context.state.clock.year
        )
        metadata = dict(ended.metadata)
        metadata["end_reason"] = "faction_dissolved"
        context.state.relations.replace_metadata(ended.relation_id, metadata)
    context.emit(
        "faction.dissolved", source="factions",
        scope=EventScope("faction", faction_id),
        payload={"faction_id": faction_id, "reason": reason},
    )


def _maybe_player_faction_pressure(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = context.state.controlled_entity_id
        if actor_id is None or int(event.payload["to_year"]) <= int(
            event.payload["from_year"]
        ):
            return
        membership = _active_membership(context.state, actor_id)
        if membership is None:
            return
        faction_id = membership.target_id
        profile = context.state.entities.require(faction_id, FACTION_PROFILE)
        governance = context.state.entities.require(faction_id, FACTION_GOVERNANCE)
        if (
            not bool(profile.get("active"))
            or governance.get("creator_id") != actor_id
            or profile.get("world_id")
            != context.state.entities.require(actor_id, LOCATION).get("world_id")
        ):
            return
        rules = dict(definitions.systems.get("player_faction", {}))
        threshold = _governance_threshold(definitions, str(profile["world_id"]))
        actor_cultivation = context.state.entities.require(actor_id, CULTIVATION)
        qualified = definitions.realm_index(
            str(actor_cultivation["realm_id"])
        ) >= threshold
        if not qualified:
            qualified = any(
                edge.source_id != actor_id
                and bool(context.state.entities.require(
                    edge.source_id, LIFE
                ).get("alive"))
                and context.state.entities.require(
                    edge.source_id, LOCATION
                ).get("world_id") == profile.get("world_id")
                and definitions.realm_index(str(context.state.entities.require(
                    edge.source_id, CULTIVATION
                )["realm_id"])) >= threshold
                for edge in context.state.relations.find(
                    target_id=faction_id, kind=MEMBERSHIP
                )
            )
        if qualified:
            if int(governance.get("pressure", 0)):
                governance["pressure"] = 0
                context.state.entities.put(
                    faction_id, FACTION_GOVERNANCE, governance
                )
            return
        from .story import STORY_STATE, queue_story_event

        story = context.state.entities.require(actor_id, STORY_STATE)
        if story.get("pending") is not None or story.get("queue"):
            return
        if context.rng.random() >= float(
            rules.get("pressure_chance_per_unit", 0.35)
        ):
            return
        pressure = int(governance.get("pressure", 0))
        event_id = f"EVT_PLAYER_SECT_DEFENSE_{min(3, pressure + 1):03d}"
        queue_story_event(
            context, definitions, actor_id, event_id,
            reason="player_faction_pressure",
            runtime={
                "faction_id": faction_id,
                "failure_number": pressure + 1,
                "threshold_realm": threshold,
            },
        )

    return handler


def _advance_faction_npcs(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        from .intrigue import is_intrigue_imprisoned

        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        if elapsed <= 0:
            return
        rules = dict(definitions.systems.get("factions", {}))
        cultivation_rules = dict(rules.get("npc_cultivation", {}))
        rates = dict(cultivation_rules.get("progress_per_year", {}))
        threshold = float(cultivation_rules.get("threshold", 100.0))
        base_success = float(cultivation_rules.get("base_success", 0.64))
        retention = float(cultivation_rules.get("failed_progress_retained", 0.55))
        accident = float(cultivation_rules.get("accident_death_chance", 0.0005))
        for character_id in list(context.state.entities.with_component(FACTION_NPC)):
            # Schema 3 gives every NPC one canonical lifecycle.  Keep this
            # legacy loop only as a fallback for snapshots not yet reconciled;
            # otherwise family/faction overlap would advance a person twice.
            if context.state.entities.get(
                character_id, "simulation.npc_lifecycle"
            ) is not None:
                continue
            life = context.state.entities.require(character_id, LIFE)
            if not bool(life.get("alive")) or is_intrigue_imprisoned(
                context.state, character_id
            ):
                continue
            cultivation = context.state.entities.require(character_id, CULTIVATION)
            npc = context.state.entities.require(character_id, FACTION_NPC)
            for _ in range(elapsed):
                if context.rng.random() < accident:
                    context.emit(
                        "character.lethal_hazard", source="factions",
                        scope=EventScope.entity(character_id),
                        payload={"entity_id": character_id, "reason": "宗门修行意外陨落"},
                    )
                    break
                realm_index = definitions.realm_index(str(cultivation["realm_id"]))
                if realm_index == 0 or realm_index >= len(definitions.realms) - 1:
                    continue
                progress = float(npc.get("cultivation_progress", 0.0))
                progress += float(rates.get(str(realm_index), 0.0))
                if progress < threshold:
                    npc["cultivation_progress"] = progress
                    continue
                root = definitions.roots.get(str(cultivation.get("spirit_root", "none")))
                chance = base_success
                if root is not None:
                    chance += (float(root.efficiency) - 1.0) * float(
                        cultivation_rules.get("root_success_scale", 0.20)
                    )
                if context.rng.random() >= max(0.05, min(0.95, chance)):
                    npc["cultivation_progress"] = threshold * retention
                    continue
                realm = definitions.realms[realm_index]
                before = (str(cultivation["realm_id"]), int(cultivation["layer"]))
                if int(cultivation["layer"]) < realm.layers:
                    cultivation["layer"] = int(cultivation["layer"]) + 1
                else:
                    cultivation["realm_id"] = definitions.realms[realm_index + 1].id
                    cultivation["layer"] = 1
                    span = definitions.realms[realm_index + 1].lifespan
                    if span is not None:
                        age = context.state.clock.year - int(life["birth_year"])
                        life["lifespan"] = max(
                            int(life.get("lifespan") or 0), age + 1,
                            context.rng.randint(*span),
                        )
                        context.state.entities.put(character_id, LIFE, life)
                        context.emit(
                            "character.lifespan.changed", source="factions",
                            scope=EventScope.entity(character_id),
                            payload={"entity_id": character_id},
                        )
                npc["cultivation_progress"] = 0.0
                membership = _active_membership(context.state, character_id)
                context.emit(
                    "faction.member.breakthrough", source="factions",
                    scope=(
                        EventScope("faction", membership.target_id)
                        if membership else EventScope.entity(character_id)
                    ),
                    payload={
                        "character_id": character_id,
                        "before": before,
                        "after": (str(cultivation["realm_id"]), int(cultivation["layer"])),
                    },
                )
            context.state.entities.put(character_id, CULTIVATION, cultivation)
            context.state.entities.put(character_id, FACTION_NPC, npc)

    return handler


def _recruit_faction_npc(
    context: SimulationContext,
    definitions: GameDefinitions,
    faction_id: str,
) -> str:
    profile = context.state.entities.require(faction_id, FACTION_PROFILE)
    rules = dict(definitions.systems.get("factions", {}))
    distributions = dict(rules.get("recruitment_distribution_by_world", {}))
    distribution = list(
        distributions.get(str(profile["world_id"]))
        or rules.get("recruitment_distribution", [{"upper": 1.0, "realm_index": 1}])
    )
    roll = context.rng.random()
    realm_index = int(distribution[-1]["realm_index"])
    for row in distribution:
        if roll <= float(row["upper"]):
            realm_index = int(row["realm_index"])
            break
    realm_index = max(0, min(len(definitions.realms) - 1, realm_index))
    realm = definitions.realms[realm_index]
    age_ranges = {
        0: (16, 36), 1: (18, 72), 2: (45, 150), 3: (120, 330),
        4: (280, 850), 5: (750, 2300), 6: (2200, 5800),
        7: (6000, 21000), 8: (14000, 80000),
    }
    low, high = age_ranges.get(realm_index, (18, 80))
    lifespan = None
    if realm.lifespan is not None:
        lifespan = context.rng.randint(*realm.lifespan)
        high = max(low, min(high, lifespan - max(12, int(lifespan * 0.25))))
    age = context.rng.randint(low, high)
    existing = [
        edge.source_id for edge in context.state.relations.find(
            target_id=faction_id, kind=MEMBERSHIP
        )
    ]
    paths = [
        str(context.state.entities.require(entity_id, CULTIVATION)["path"])
        for entity_id in existing
        if context.state.entities.get(entity_id, CULTIVATION) is not None
    ]
    path = context.rng.choice(paths) if paths else "dao"
    if path == "monster" and lifespan is not None:
        lifespan *= 3
    roots = [
        root_id for root_id, root in definitions.roots.items()
        if root_id != "none" and root.creation
    ]
    surname = context.rng.choice(["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "江", "闻"])
    given = context.rng.choice(["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚"])
    character_id = create_character(
        context,
        name=surname + given,
        age=age,
        gender=context.rng.choice(("male", "female")),
        race=str(profile.get("allegiance_race", "human")),
        spirit_root=context.rng.choice(roots),
        path=path,
        realm_id=realm.id,
        layer=1 if realm_index == 0 else context.rng.randint(1, realm.layers),
        world_id=str(profile["world_id"]),
        lifespan=lifespan,
    )
    context.state.entities.put(character_id, FACTION_NPC, {
        "external_id": "",
        "title": (
            "跨域客卿" if realm_index >= 5 else
            "加盟客卿" if realm_index >= 3 else
            "新晋内门" if realm_index == 2 else "新入门弟子"
        ),
        "cultivation_progress": 0.0,
        "last_dispatch_year": None,
    })
    _add_membership(
        context, character_id=character_id, faction_id=faction_id, role="member"
    )
    context.emit(
        "faction.member.recruited", source="factions",
        scope=EventScope("faction", faction_id),
        payload={"faction_id": faction_id, "character_id": character_id},
    )
    return character_id


def _maintain_faction_rosters(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        start = int(event.payload["from_year"])
        end = int(event.payload["to_year"])
        if end <= start:
            return
        player_rng_state = context.rng.getstate()
        rules = dict(definitions.systems.get("factions", {}))
        interval = max(1, int(rules.get("recruitment_interval_years", 5)))
        maximum = max(1, int(rules.get("max_members", 36)))
        actor_id = context.state.controlled_entity_id
        active_world = (
            str(context.state.entities.require(actor_id, LOCATION)["world_id"])
            if actor_id else ""
        )
        for faction_id in list(context.state.entities.with_component(FACTION_PROFILE)):
            profile = context.state.entities.require(faction_id, FACTION_PROFILE)
            if (
                not bool(profile.get("active"))
                or not bool(profile.get("roster_seeded"))
                or str(profile.get("world_id")) != active_world
            ):
                continue
            last = int(profile.get("last_recruitment_year", start))
            due = max(0, end // interval - max(last, start) // interval)
            for _ in range(due):
                living = sum(
                    bool(context.state.entities.require(edge.source_id, LIFE).get("alive"))
                    for edge in context.state.relations.find(
                        target_id=faction_id, kind=MEMBERSHIP
                    )
                )
                if living >= maximum:
                    break
                _recruit_faction_npc(context, definitions, faction_id)
            if due:
                profile = context.state.entities.require(faction_id, FACTION_PROFILE)
                profile["last_recruitment_year"] = end
                context.state.entities.put(faction_id, FACTION_PROFILE, profile)
        context.rng.setstate(player_rng_state)

    return handler


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    character_id = str(event.payload["entity_id"])
    membership = _active_membership(context.state, character_id)
    if membership is None:
        return
    governance = context.state.entities.require(membership.target_id, FACTION_GOVERNANCE)
    if governance.get("controller_id") == character_id:
        governance["controller_id"] = None
        context.state.entities.put(membership.target_id, FACTION_GOVERNANCE, governance)
        context.emit(
            "faction.control.vacant",
            source="factions",
            scope=EventScope("faction", membership.target_id),
            payload={"faction_id": membership.target_id, "former_controller_id": character_id},
        )
    ended = context.state.relations.end(
        membership.relation_id, ended_year=context.state.clock.year
    )
    metadata = dict(ended.metadata)
    metadata["end_reason"] = "member_died"
    context.state.relations.replace_metadata(ended.relation_id, metadata)
    living = [
        edge for edge in context.state.relations.find(
            target_id=membership.target_id, kind=MEMBERSHIP
        )
        if bool(context.state.entities.require(edge.source_id, LIFE).get("alive"))
    ]
    profile = context.state.entities.require(membership.target_id, FACTION_PROFILE)
    if not living and bool(profile.get("active")):
        _dissolve_faction(
            context, membership.target_id, reason="last_member_fallen"
        )


def _on_same_faction_combat(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload.get("attacker_id", ""))
        target_id = str(event.payload.get("target_id", ""))
        if (
            actor_id != context.state.controlled_entity_id
            or event.payload.get("objective") != "kill"
            or event.payload.get("outcome") != "victory"
        ):
            return
        actor_membership = _active_membership(context.state, actor_id)
        target_membership = _active_membership(context.state, target_id)
        if (
            actor_membership is None
            or target_membership is None
            or actor_membership.target_id != target_membership.target_id
        ):
            return
        faction_id = actor_membership.target_id
        profile = context.state.entities.require(faction_id, FACTION_PROFILE)
        world_id = str(profile["world_id"])
        conflict = dict(definitions.systems.get("faction_conflict", {}))
        thresholds = dict(conflict.get("control_realm", {}))
        control_realm = int(thresholds.get(
            world_id,
            max(1, definitions.worlds[world_id].npc_realm_cap),
        ))
        actor_cultivation = context.state.entities.require(actor_id, CULTIVATION)
        actor_rank = (
            definitions.realm_index(str(actor_cultivation["realm_id"])),
            int(actor_cultivation["layer"]),
        )
        living_ranks = []
        for membership in context.state.relations.find(
            target_id=faction_id, kind=MEMBERSHIP
        ):
            if not bool(context.state.entities.require(
                membership.source_id, LIFE
            ).get("alive")):
                continue
            cultivation = context.state.entities.require(
                membership.source_id, CULTIVATION
            )
            living_ranks.append((
                definitions.realm_index(str(cultivation["realm_id"])),
                int(cultivation["layer"]),
            ))
        is_first = not living_ranks or actor_rank >= max(living_ranks)
        governance = context.state.entities.require(
            faction_id, FACTION_GOVERNANCE
        )
        warnings = list(map(str, governance.get("same_sect_kill_warnings", [])))
        warning_key = f"same_sect_kill:{actor_id}"
        result = "suppressed"
        summary = "你位列宗门顺位第一，无人敢当面追究这次同门血案。"

        def expel(reason: str, minimum: float, gain: float) -> None:
            closed = context.state.relations.end(
                actor_membership.relation_id,
                ended_year=context.state.clock.year,
            )
            metadata = dict(closed.metadata)
            metadata["end_reason"] = reason
            context.state.relations.replace_metadata(
                closed.relation_id, metadata
            )
            from .war import WANTED_STATE, _change_hostility

            key = f"sect:{faction_id}"
            wanted = context.state.entities.require(actor_id, WANTED_STATE)
            current = float(dict(wanted.get("hostility", {})).get(key, 0.0))
            _change_hostility(
                context, actor_id, key, max(gain, minimum - current)
            )

        if actor_rank[0] < control_realm:
            expel("same_faction_kill", 60.0, 45.0)
            result = "expelled"
            summary = "你残杀同门，被当场逐出宗门并列入全宗通缉。"
        elif not is_first and warning_key not in warnings:
            warnings.append(warning_key)
            governance["same_sect_kill_warnings"] = warnings
            context.state.entities.put(
                faction_id, FACTION_GOVERNANCE, governance
            )
            story = context.state.entities.require(actor_id, "story.state")
            if story.get("pending") is None and not story.get("queue"):
                from .story import queue_story_event

                queue_story_event(
                    context, definitions, actor_id,
                    "EVT_SECT_FIRST_WARNING_001",
                    reason="same_faction_kill_warning",
                    runtime={"faction_id": faction_id},
                )
            result = "warned"
            summary = "宗门顺位第一的强者降下法旨，警告你下不为例。"
        elif not is_first:
            expel("repeated_same_faction_kill", 90.0, 55.0)
            result = "hunted"
            summary = "你无视警告再杀同门，宗门上下奉诛杀令追索你的性命。"
        story = context.state.entities.require(actor_id, "story.state")
        history = list(story.get("system_history", []))
        history.append({
            "kind": "same_faction_kill", "faction_id": faction_id,
            "target_id": target_id, "result": result,
            "summary": summary, "year": context.state.clock.year,
        })
        story["system_history"] = history[-80:]
        context.state.entities.put(actor_id, "story.state", story)

    return handler


def _on_permanent_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    membership = _active_membership(context.state, actor_id)
    handover: dict[str, Any] | None = None
    if membership is not None:
        faction_id = membership.target_id
        governance = context.state.entities.require(faction_id, FACTION_GOVERNANCE)
        successor_id = governance.get("designated_successor_id")
        successor = _active_membership(context.state, str(successor_id)) if successor_id else None
        arranged = bool(successor and successor.target_id == faction_id)
        controlled = governance.get("controller_id") == actor_id
        if controlled:
            governance["controller_id"] = str(successor_id) if arranged else None
        governance["last_ascension_handover"] = {
            "founder_id": actor_id if governance.get("creator_id") == actor_id else None,
            "successor_id": str(successor_id) if arranged else None,
            "arranged": arranged,
            "return_eligible": bool(
                controlled and arranged and governance.get("creator_id") == actor_id
            ),
            "origin_world_id": event.payload["origin_world_id"],
            "year": context.state.clock.year,
        }
        context.state.entities.put(faction_id, FACTION_GOVERNANCE, governance)
        closed = context.state.relations.end(membership.relation_id, ended_year=context.state.clock.year)
        metadata = dict(closed.metadata)
        metadata["end_reason"] = "ascension"
        context.state.relations.replace_metadata(closed.relation_id, metadata)
        handover = {
            "faction_id": faction_id, "controlled": controlled,
            "arranged": arranged, "successor_id": successor_id if arranged else None,
        }
    context.emit(
        "world.transition.acknowledged",
        source="factions",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": event.payload["transaction_id"],
            "actor_id": actor_id, "domain": "factions", "handover": handover,
        },
    )


def _on_temporary_world_transition(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        if _active_membership(context.state, actor_id) is not None:
            return
        destination = str(event.payload["destination_world_id"])
        candidate: tuple[str, dict[str, Any]] | None = None
        for faction_id in context.state.entities.with_component(FACTION_GOVERNANCE):
            governance = context.state.entities.require(faction_id, FACTION_GOVERNANCE)
            handover = governance.get("last_ascension_handover")
            profile = context.state.entities.require(faction_id, FACTION_PROFILE)
            if (
                isinstance(handover, dict)
                and handover.get("founder_id") == actor_id
                and bool(handover.get("return_eligible"))
                and bool(profile.get("active"))
                and profile.get("world_id") == destination
            ):
                candidate = faction_id, governance
                break
        if candidate is None or context.rng.random() >= 0.5:
            return
        faction_id, _ = candidate
        from .story import STORY_STATE, queue_story_event
        profile = context.state.entities.require(faction_id, FACTION_PROFILE)
        queue_story_event(
            context, definitions, actor_id, "EVT_FOUNDER_RETURN_001",
            reason="founder_return",
            runtime={
                "faction_id": faction_id,
                "sect_name": str(profile["name"]),
            },
        )
        story = context.state.entities.require(actor_id, STORY_STATE)
        pending = story.get("pending")
        if isinstance(pending, dict) and pending.get("id") == "EVT_FOUNDER_RETURN_001":
            pending = dict(pending)
            story["pending"] = pending
            context.state.entities.put(actor_id, STORY_STATE, story)

    return handler


def register_faction_story_effects(
    registry: Any, definitions: GameDefinitions,
) -> None:
    from .story import EffectOutcome

    def join(
        context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any],
    ) -> EffectOutcome:
        del pending
        external_id = str(effect.payload["faction_id"])
        faction_id = _resolve_faction_id(context.state, external_id)
        if faction_id is None:
            raise ValueError("剧情目标宗门不存在")
        _join_faction_handler(registry.definitions)(
            context, JoinFaction(actor_id, faction_id)
        )
        profile = context.state.entities.require(faction_id, FACTION_PROFILE)
        return EffectOutcome("faction_joined", f"你加入了{profile['name']}。")

    def restore(
        context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any],
    ) -> EffectOutcome:
        faction_id = str(dict(pending.get("runtime", {})).get("faction_id", ""))
        profile = context.state.entities.get(faction_id, FACTION_PROFILE)
        governance = context.state.entities.get(faction_id, FACTION_GOVERNANCE)
        handover = governance.get("last_ascension_handover") if governance else None
        same_world = profile and context.state.entities.require(actor_id, LOCATION).get("world_id") == profile.get("world_id")
        if not profile or not governance or not isinstance(handover, dict) or not bool(handover.get("return_eligible")) or not bool(profile.get("active")) or not same_world:
            return EffectOutcome("faction_return_expired", "旧宗已经不复存在，祖师之约就此作罢。")
        handover["return_eligible"] = False
        governance["last_ascension_handover"] = handover
        if not bool(effect.payload.get("accept", False)):
            context.state.entities.put(faction_id, FACTION_GOVERNANCE, governance)
            return EffectOutcome("faction_return_declined", f"你谢绝了{profile['name']}门人的迎请，让后辈继续执掌宗门。")
        if _active_membership(context.state, actor_id) is not None:
            raise ValueError("已有宗门归属，不能重新接掌旧宗")
        _add_membership(context, character_id=actor_id, faction_id=faction_id, role="founder")
        governance["controller_id"] = actor_id
        context.state.entities.put(faction_id, FACTION_GOVERNANCE, governance)
        context.emit(
            "faction.control.restored", source="factions",
            scope=EventScope("faction", faction_id),
            payload={"faction_id": faction_id, "controller_id": actor_id},
        )
        return EffectOutcome("faction_control_restored", f"你重返{profile['name']}祖庭，门人奉还印玺，你重新执掌宗门大权。")

    def defend_sect(
        context: SimulationContext, actor_id: str, effect: Any,
        pending: dict[str, Any],
    ) -> EffectOutcome:
        runtime = dict(pending.get("runtime", {}))
        membership = _active_membership(context.state, actor_id)
        faction_id = str(runtime.get(
            "faction_id", membership.target_id if membership else ""
        ))
        profile = context.state.entities.get(faction_id, FACTION_PROFILE)
        governance = context.state.entities.get(faction_id, FACTION_GOVERNANCE)
        if (
            membership is None or membership.target_id != faction_id
            or profile is None or governance is None
            or not bool(profile.get("active"))
        ):
            return EffectOutcome("sect_absent", "山门已经不复存在。")
        mode = str(effect.payload.get("mode", "fight"))
        success = False
        detail = ""
        if mode == "fight":
            threshold = int(runtime.get(
                "threshold_realm",
                _governance_threshold(definitions, str(profile["world_id"])),
            ))
            enemy_realm_index = max(0, threshold - 1)
            enemy_realm = definitions.realms[enemy_realm_index]
            enemy_id = create_character(
                context, name="来犯山门的敌修", age=max(18, threshold * 60),
                gender="male", race=str(profile.get(
                    "allegiance_race", "human"
                )), spirit_root=(
                    "none" if enemy_realm_index == 0 else "supreme_fire"
                ), path="dao", realm_id=enemy_realm.id,
                layer=enemy_realm.layers, world_id=str(profile["world_id"]),
                lifespan=None,
            )
            context.state.entities.put(
                enemy_id,
                LOCATION,
                dict(context.state.entities.require(actor_id, LOCATION)),
            )
            before = set(context.state.entities.with_component("combat.report"))
            resolve_combat(
                context, definitions, attacker_id=actor_id,
                target_id=enemy_id, objective="duel",
            )
            report_id = next(iter(
                set(context.state.entities.with_component("combat.report")) - before
            ))
            report = context.state.entities.require(report_id, "combat.report")
            success = report["outcome"] == "victory"
            detail = "你在山门前击退来犯修士" if success else "你未能正面压退来犯修士"
            enemy_life = context.state.entities.require(enemy_id, LIFE)
            enemy_life["alive"] = False
            enemy_life["death_year"] = context.state.clock.year
            enemy_life["death_reason"] = "护山战后离场"
            context.state.entities.put(enemy_id, LIFE, enemy_life)
        elif mode == "formation":
            from .artifacts import FORMATION
            from .combat import combat_snapshot

            formation = context.state.entities.require(actor_id, FORMATION)
            location = context.state.entities.require(actor_id, LOCATION)
            arrays = [dict(row) for row in formation.get("ground_arrays", [])]
            index = next((
                index for index, row in enumerate(arrays)
                if row.get("owner_kind") == "sect"
                and row.get("world_id") == location.get("world_id")
                and row.get("location_id") == location.get("location_id")
                and float(row.get("durability", 0)) > 0
            ), None)
            if index is not None:
                ground = arrays[index]
                metrics = dict(dict(ground.get("profile", {})).get("metrics", {}))
                formation_factor = 0.65 + sum(
                    float(metrics.get(key, 0))
                    for key in ("growth", "kill", "focus", "balance", "cycle", "change")
                ) / 3
                defense_power = float(combat_snapshot(
                    context.state, definitions, actor_id
                )["power"]) * formation_factor * float(
                    ground.get("durability", 0)
                ) / 100
                threshold = int(runtime.get(
                    "threshold_realm",
                    _governance_threshold(definitions, str(profile["world_id"])),
                ))
                target_realm = definitions.realms[max(0, threshold - 1)]
                target_id = create_character(
                    context, name="阵外试压傀儡", age=18, gender="male",
                    race="human", spirit_root=(
                        "none" if threshold <= 1 else "supreme_fire"
                    ), path="dao", realm_id=target_realm.id,
                    layer=target_realm.layers,
                    world_id=str(profile["world_id"]),
                    lifespan=None,
                )
                required_power = float(combat_snapshot(
                    context.state, definitions, target_id
                )["power"]) * (0.72 + int(governance.get("pressure", 0)) * 0.12)
                success = defense_power >= required_power
                wear = min(25.0, 7.0 if success else 15.0)
                ground["durability"] = round(max(
                    0.0, float(ground.get("durability", 0)) - wear
                ), 4)
                arrays[index] = ground
                formation["ground_arrays"] = arrays
                context.state.entities.put(actor_id, FORMATION, formation)
                target_life = context.state.entities.require(target_id, LIFE)
                target_life["alive"] = False
                context.state.entities.put(target_id, LIFE, target_life)
                detail = (
                    f"镇宗大阵以 {defense_power:.0f} 阵力抵御"
                    f" {required_power:.0f} 来犯战力，完整度降至"
                    f" {ground['durability']:.1f}%"
                )
            else:
                detail = "此地没有以真实阵材布下的镇宗大阵"
        elif mode == "appease":
            from .economy import change_inventory_item, inventory_quantity

            cost = 80 if str(profile["world_id"]) == "human" else 800
            if inventory_quantity(
                context.state, actor_id, "spirit_stone", spendable=True
            ) >= cost:
                change_inventory_item(
                    context, definitions, actor_id, "spirit_stone", -cost,
                    "faction_defense_appeasement",
                )
                success = True
                detail = f"你支付了 {cost} 灵石请人调停"
            else:
                detail = f"可用灵石不足 {cost}"
        elif mode == "abandon":
            _dissolve_faction(context, faction_id, reason="founder_abandoned")
            return EffectOutcome(
                "sect_dissolved", "你撤下山门匾额，幸存门人各寻出路。"
            )
        else:
            raise ValueError("未知护山方式")
        if success:
            metadata = dict(membership.metadata)
            metadata["contribution"] = int(metadata.get("contribution", 0)) + 5
            context.state.relations.replace_metadata(
                membership.relation_id, metadata
            )
            return EffectOutcome(
                "defended", f"{detail}；山门守住，宗门贡献 +5"
            )
        pressure = int(governance.get("pressure", 0)) + 1
        governance["pressure"] = pressure
        context.state.entities.put(faction_id, FACTION_GOVERNANCE, governance)
        limit = int(dict(definitions.systems.get(
            "player_faction", {}
        )).get("pressure_limit", 3))
        if pressure >= limit:
            _dissolve_faction(
                context, faction_id, reason="three_failed_defenses"
            )
            return EffectOutcome(
                "sect_dissolved",
                f"{detail}；这是第 {pressure} 次护山失败，宗门就此解散",
            )
        return EffectOutcome(
            "defense_failed",
            f"{detail}；护山失败累计 {pressure}/{limit}",
        )

    registry.register("join_faction", join)
    registry.register("restore_faction_control", restore)
    registry.register("sect_defense", defend_sect)


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
            preference = edge.metadata.get("reward_preference")
            if preference is not None and preference not in definitions.faction_rewards:
                errors.append(f"势力奖励偏好非法：{edge.relation_id}")
            benefits = dict(edge.metadata.get("permanent_benefits", {}))
            if set(benefits) - {"hp", "mp", "combat"} or any(
                not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
                for value in benefits.values()
            ):
                errors.append(f"势力永久奖励非法：{edge.relation_id}")
        if any(count > 1 for count in membership_counts.values()):
            errors.append("角色同时拥有多个有效势力身份")
        support_counts: dict[str, int] = {}
        for edge in state.relations.find(kind=RACE_SUPPORT):
            if state.entities.get(edge.source_id, IDENTITY) is None or state.entities.get(edge.target_id, IDENTITY) is None:
                errors.append(f"种族外援关系端点不是角色：{edge.relation_id}")
            support_counts[edge.target_id] = support_counts.get(edge.target_id, 0) + 1
        if any(count > 1 for count in support_counts.values()):
            errors.append("同一角色同时成为多个种族外援")
        return errors

    return validate


def register_faction_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(FoundFaction, _found_faction_handler(definitions))
    bus.register(JoinFaction, _join_faction_handler(definitions))
    bus.register(LeaveFaction, _leave_faction)
    bus.register(ChangeContribution, _change_contribution)
    bus.register(TransferFactionControl, _transfer_control)
    bus.register(InviteRelationshipToFaction, _invite_relationship)
    bus.register(SetFactionRewardPreference, _set_reward_preference(definitions))
    bus.register(ArrangeFactionSuccession, _arrange_succession_handler(definitions))
    bus.register(DispatchFactionMember, _dispatch_handler(definitions))
    bus.register(InterceptFactionMember, _intercept_handler(definitions))
    bus.register(ProposeDiplomacy, _propose_diplomacy_handler(definitions))
    bus.register(TransferVassalPersonnel, _transfer_vassal_handler(definitions))
    bus.register(EnsureFactionRosters, _ensure_faction_rosters_handler(definitions))
    bus.event_bus.register("core.game.created", _on_game_created(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register("combat.resolved", _on_same_faction_combat(definitions))
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))
    bus.event_bus.register(
        "core.time.advanced", _maintain_faction_rosters(definitions)
    )
    bus.event_bus.register(
        "core.time.advanced", _maybe_player_faction_pressure(definitions)
    )
    bus.event_bus.register(
        "story.effect.faction_contribution.changed", _on_story_contribution_changed
    )
    bus.event_bus.register("world.permanent_transition.requested", _on_permanent_world_transition)
    bus.event_bus.register(
        "world.temporary_transition.committed", _on_temporary_world_transition(definitions)
    )


def faction_view(
    state: Any, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any] | None:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    membership = _active_membership(state, actor_id)
    if membership is None:
        return None
    profile = state.entities.require(membership.target_id, FACTION_PROFILE)
    location = state.entities.require(actor_id, LOCATION)
    if location.get("world_id") != profile.get("world_id"):
        return None
    governance = state.entities.require(membership.target_id, FACTION_GOVERNANCE)
    permanent_benefits = {"hp": 0.0, "mp": 0.0, "combat": 0.0}
    for historical in state.relations.find(
        source_id=actor_id, kind=MEMBERSHIP, active_only=False
    ):
        for key, value in dict(historical.metadata.get("permanent_benefits", {})).items():
            if key in permanent_benefits:
                permanent_benefits[key] += float(value)
    roster = []
    for edge in state.relations.find(target_id=membership.target_id, kind=MEMBERSHIP):
        member_location = state.entities.require(edge.source_id, LOCATION)
        if member_location.get("world_id") != profile.get("world_id"):
            continue
        member = character_view(state, edge.source_id)
        cultivation = state.entities.require(edge.source_id, CULTIVATION)
        npc_profile = state.entities.get(edge.source_id, FACTION_NPC) or {}
        roster.append({
            **member,
            "role": edge.metadata.get("role", "member"),
            "title": npc_profile.get("title", "门人"),
            "realm_id": cultivation["realm_id"],
            "realm_index": definitions.realm_index(str(cultivation["realm_id"])),
            "layer": int(cultivation["layer"]),
            "path": cultivation["path"],
        })
    diplomacy = state.entities.get(actor_id, DIPLOMACY_STATE) or {"relations": {}}
    relations = dict(diplomacy.get("relations", {}))
    actor_cultivation = state.entities.require(actor_id, CULTIVATION)
    actor_rank = (
        definitions.realm_index(str(actor_cultivation["realm_id"])),
        int(actor_cultivation["layer"]),
    )
    runtime = state.entities.get(actor_id, "core.action_runtime") or {}
    current_unit = max(0, int(runtime.get("next_sequence", 1)) - 1)
    status_names = {
        "neutral": "中立", "war": "战争", "alliance": "同盟",
        "truce": "停战", "vassal": "依附",
    }
    diplomacy_rows = []
    for other_id in state.entities.with_component(FACTION_PROFILE):
        if other_id == membership.target_id:
            continue
        other_profile = state.entities.require(other_id, FACTION_PROFILE)
        if (
            not bool(other_profile.get("active"))
            or other_profile.get("world_id") != profile.get("world_id")
        ):
            continue
        relation = dict(relations.get(
            _diplomacy_key("faction", membership.target_id, other_id),
            {},
        ))
        status = str(relation.get("status", "neutral"))
        members = []
        for other_edge in state.relations.find(
            target_id=other_id, kind=MEMBERSHIP
        ):
            member_id = other_edge.source_id
            member_life = state.entities.require(member_id, LIFE)
            member_location = state.entities.require(member_id, LOCATION)
            if (
                not bool(member_life.get("alive"))
                or member_location.get("world_id") != profile.get("world_id")
            ):
                continue
            member_cultivation = state.entities.require(member_id, CULTIVATION)
            member_realm = definitions.realm(
                str(member_cultivation["realm_id"])
            )
            snapshot = combat_snapshot(state, definitions, member_id)
            members.append({
                "id": member_id,
                "name": state.entities.require(member_id, IDENTITY)["name"],
                "realm_name": (
                    member_realm.name
                    if member_realm.id == "mortal"
                    else f"{member_realm.name}·{int(member_cultivation['layer'])}层"
                ),
                "rank": (
                    definitions.realm_index(member_realm.id),
                    int(member_cultivation["layer"]),
                ),
                "combat_power": float(snapshot["power"]),
            })
        members.sort(
            key=lambda row: (-row["combat_power"], -row["rank"][0], row["name"])
        )
        transferable = bool(
            status == "vassal"
            and relation.get("overlord") == membership.target_id
            and relation.get("subject") == other_id
        )
        diplomacy_rows.append({
            "target_id": other_id,
            "target_name": other_profile["name"],
            "status": status,
            "status_name": status_names.get(status, status),
            "affinity": round(float(relation.get("affinity", 0.0)), 1),
            "overlord": relation.get("overlord"),
            "subject": relation.get("subject"),
            "since_age": relation.get("since_year"),
            "last_vote": relation.get("last_vote"),
            "truce_units_remaining": max(
                0,
                max(
                    int(relation.get("truce_until_unit", 0)),
                    int(relation.get("war_truce_until_unit", 0)),
                ) - current_unit,
            ),
            "living_count": len(members),
            "combined_power": round(sum(
                row["combat_power"] for row in members
            ), 1),
            "leaders": [
                f"{row['name']}（{row['realm_name']}）" for row in members[:3]
            ],
            "recent_events": [],
            "transfer_candidates": [
                {
                    "id": row["id"], "name": row["name"],
                    "realm_name": row["realm_name"],
                }
                for row in members if transferable and row["rank"] <= actor_rank
            ],
        })
    return {
        "id": membership.target_id,
        "external_id": profile.get("external_id"),
        "name": profile["name"],
        "world_id": profile["world_id"],
        "allegiance_race": profile.get("allegiance_race"),
        "role": membership.metadata["role"],
        "contribution": int(membership.metadata["contribution"]),
        "controller_id": governance.get("controller_id"),
        "controlled_by_player": governance.get("controller_id") == actor_id,
        "has_voice": _has_faction_voice(
            state, definitions, actor_id, membership.target_id
        ),
        "designated_successor_id": governance.get("designated_successor_id"),
        "last_ascension_handover": governance.get("last_ascension_handover"),
        "roster": roster,
        "diplomacy": diplomacy_rows,
        "reward_preference": membership.metadata.get("reward_preference"),
        "reward_options": {
            reward_id: {
                "name": reward["name"],
                "description": reward.get("description", ""),
            }
            for reward_id, reward in definitions.faction_rewards.items()
        },
        "permanent_benefits": permanent_benefits,
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


def governance_view(
    state: WorldState, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    component = state.entities.get(actor_id, DIPLOMACY_STATE) or {"relations": {}}
    world_id = str(state.entities.require(actor_id, LOCATION)["world_id"])
    preferences = state.entities.get(actor_id, "presentation.preferences") or {}
    debug = bool(preferences.get("debug_world_news", False))
    visible_relations = [
        dict(row) for row in dict(component.get("relations", {})).values()
        if debug or not row.get("world_id") or row.get("world_id") == world_id
    ]
    support = []
    for edge in state.relations.find(source_id=actor_id, kind=RACE_SUPPORT):
        location = state.entities.require(edge.target_id, LOCATION)
        if location.get("world_id") != world_id:
            continue
        support.append({
            "character": character_view(state, edge.target_id),
            "race_id": edge.metadata.get("race_id"),
            "source_race_id": edge.metadata.get("source_race_id"),
        })
    return {
        "relations": visible_relations,
        "race_support": support,
        "diplomacy_statuses": {
            "neutral": "中立",
            "alliance": "同盟",
            "war": "战争",
            "truce": "停战",
            "vassal": "依附",
        },
    }
