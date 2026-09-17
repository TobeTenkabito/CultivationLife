from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .character import IDENTITY, LIFE, character_view
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions, RootDefinition, TechniqueDefinition
from .economy import inventory_quantity
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, RelationEdge, WorldState


SOCIAL_PROFILE = "relations.social_profile"
SOCIAL_KINDS = {"friend", "dao_companion", "master_disciple", "concubine"}
SYMMETRIC_KINDS = {"friend", "dao_companion"}
PENDING_DISCIPLE_REQUEST = "master_disciple_request"


@dataclass(frozen=True, slots=True)
class FormRelationship:
    source_id: str
    target_id: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EndRelationship:
    actor_id: str
    relation_id: str
    reason: str = "ended"


@dataclass(frozen=True, slots=True)
class ChangeAffinity:
    actor_id: str
    target_id: str
    amount: float
    reason: str = "interaction"


@dataclass(frozen=True, slots=True)
class ProposeDaoCompanion:
    actor_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class InteractDaoCompanion:
    actor_id: str
    action: str
    content_id: str = ""


@dataclass(frozen=True, slots=True)
class BefriendDaoist:
    actor_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class InteractDaoFriend:
    actor_id: str
    friend_id: str
    action: str


@dataclass(frozen=True, slots=True)
class RequestMentorship:
    actor_id: str
    target_id: str
    role: str


@dataclass(frozen=True, slots=True)
class OfferDiscipleRequest:
    requester_id: str
    master_id: str


@dataclass(frozen=True, slots=True)
class RespondDiscipleRequest:
    actor_id: str
    request_id: str
    accept: bool


@dataclass(frozen=True, slots=True)
class RequestFromMaster:
    actor_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class GiftDisciple:
    actor_id: str
    disciple_id: str
    kind: str
    content_id: str


def _default_profile() -> dict[str, Any]:
    return {"affinities": {}, "attempts": []}


def reconcile_relationship_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        profile = state.entities.get(entity_id, SOCIAL_PROFILE) or _default_profile()
        profile["affinities"] = {
            str(other_id): float(value)
            for other_id, value in dict(profile.get("affinities", {})).items()
            if state.entities.exists(str(other_id))
        }
        profile["attempts"] = list(dict.fromkeys(map(str, profile.get("attempts", []))))
        state.entities.put(entity_id, SOCIAL_PROFILE, profile)
    actor_id = state.controlled_entity_id
    if actor_id is not None:
        for edge in state.relations.involving(actor_id):
            if edge.kind not in SOCIAL_KINDS or "affinity" not in edge.metadata:
                continue
            other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
            profile = _profile(state, other_id)
            affinities = dict(profile.get("affinities", {}))
            if actor_id not in affinities:
                affinities[actor_id] = float(edge.metadata["affinity"])
                profile["affinities"] = affinities
                state.entities.put(other_id, SOCIAL_PROFILE, profile)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(str(event.payload["entity_id"]), SOCIAL_PROFILE, _default_profile())


def _profile(state: WorldState, entity_id: str) -> dict[str, Any]:
    profile = state.entities.get(entity_id, SOCIAL_PROFILE)
    if profile is None:
        if state.entities.get(entity_id, IDENTITY) is None:
            raise ValueError("关系人物不存在")
        profile = _default_profile()
        state.entities.put(entity_id, SOCIAL_PROFILE, profile)
    return profile


def _affinity(state: WorldState, observer_id: str, subject_id: str) -> float:
    return float(dict(_profile(state, observer_id).get("affinities", {})).get(subject_id, 0.0))


def _set_affinity(state: WorldState, observer_id: str, subject_id: str, value: float) -> float:
    profile = _profile(state, observer_id)
    affinities = dict(profile.get("affinities", {}))
    affinities[subject_id] = float(value)
    profile["affinities"] = affinities
    state.entities.put(observer_id, SOCIAL_PROFILE, profile)
    return float(value)


def _change_affinity(state: WorldState, observer_id: str, subject_id: str, amount: float) -> float:
    return _set_affinity(
        state, observer_id, subject_id, _affinity(state, observer_id, subject_id) + amount
    )


def _sync_edge_affinity(state: WorldState, edge: RelationEdge, actor_id: str) -> RelationEdge:
    other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
    metadata = dict(edge.metadata)
    metadata["affinity"] = _affinity(state, other_id, actor_id)
    return state.relations.replace_metadata(edge.relation_id, metadata)


def _same_pair(edge: RelationEdge, first: str, second: str) -> bool:
    return {edge.source_id, edge.target_id} == {first, second}


def _master_reaches(state: WorldState, start: str, target: str) -> bool:
    children: dict[str, list[str]] = {}
    for edge in state.relations.find(kind="master_disciple"):
        children.setdefault(edge.source_id, []).append(edge.target_id)
    stack, seen = [start], set()
    while stack:
        current = stack.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(children.get(current, []))
    return False


def _ensure_controlled_alive(context: SimulationContext, actor_id: str) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能进行人物互动")


def _ensure_available_pair(context: SimulationContext, actor_id: str, target_id: str) -> None:
    _ensure_controlled_alive(context, actor_id)
    if not context.state.entities.exists(target_id):
        raise ValueError("关系人物不存在")
    if not bool(context.state.entities.require(target_id, LIFE).get("alive")):
        raise ValueError("对方已经死亡")
    actor_location = context.state.entities.require(actor_id, LOCATION)
    target_location = context.state.entities.require(target_id, LOCATION)
    if actor_location["world_id"] != target_location["world_id"]:
        raise ValueError("人物不在同一世界")


def _active_edge(state: WorldState, actor_id: str, other_id: str, kind: str) -> RelationEdge | None:
    return next(
        (
            edge for edge in state.relations.involving(actor_id, kind=kind)
            if other_id in {edge.source_id, edge.target_id}
        ),
        None,
    )


def _single_edge(state: WorldState, actor_id: str, kind: str) -> RelationEdge | None:
    return next(iter(state.relations.involving(actor_id, kind=kind)), None)


def _add_relationship(context: SimulationContext, command: FormRelationship) -> RelationEdge:
    if command.kind not in SOCIAL_KINDS:
        raise ValueError("未知人物关系类型")
    if command.source_id == command.target_id:
        raise ValueError("不能与自己建立关系")
    for entity_id in (command.source_id, command.target_id):
        if not context.state.entities.exists(entity_id):
            raise ValueError("关系人物不存在")
        if not bool(context.state.entities.require(entity_id, LIFE).get("alive")):
            raise ValueError("不能与已死亡人物建立新关系")
    first_location = context.state.entities.require(command.source_id, LOCATION)
    second_location = context.state.entities.require(command.target_id, LOCATION)
    if first_location["world_id"] != second_location["world_id"]:
        raise ValueError("人物不在同一世界")

    existing_pair = [
        edge for edge in context.state.relations.find()
        if edge.kind in SOCIAL_KINDS and _same_pair(edge, command.source_id, command.target_id)
    ]
    if existing_pair:
        raise ValueError("两人已有其他有效人物关系；必须先结束或转换原关系")
    source_id, target_id = command.source_id, command.target_id
    if command.kind in SYMMETRIC_KINDS:
        source_id, target_id = sorted((source_id, target_id))
    if command.kind == "dao_companion":
        for entity_id in (source_id, target_id):
            if context.state.relations.involving(entity_id, kind="dao_companion"):
                raise ValueError("道侣关系具有唯一性")
    if command.kind == "concubine":
        if context.state.relations.find(target_id=target_id, kind="concubine"):
            raise ValueError("该人物已有侍奉对象")
    if command.kind == "master_disciple":
        if context.state.relations.find(target_id=target_id, kind="master_disciple"):
            raise ValueError("该弟子已有师父")
        if _master_reaches(context.state, target_id, source_id):
            raise ValueError("师徒关系不能形成循环")
    metadata = dict(command.metadata)
    metadata.setdefault(
        "affinity", _affinity(context.state, command.target_id, command.source_id)
    )
    controlled_id = context.state.controlled_entity_id
    if controlled_id in {command.source_id, command.target_id}:
        other_id = (
            command.target_id if command.source_id == controlled_id else command.source_id
        )
        _set_affinity(
            context.state, other_id, controlled_id, float(metadata.get("affinity", 0.0))
        )
    edge = context.state.relations.add(
        source_id=source_id,
        target_id=target_id,
        kind=command.kind,
        created_year=context.state.clock.year,
        metadata=metadata,
    )
    context.emit(
        "relationship.formed",
        source="relations",
        scope=EventScope.entity(command.source_id),
        payload=edge.to_dict(),
    )
    return edge


def _form_relationship(context: SimulationContext, command: object) -> None:
    if not isinstance(command, FormRelationship):
        raise TypeError("命令类型错误")
    _add_relationship(context, command)


def _end_relationship_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, EndRelationship):
            raise TypeError("命令类型错误")
        edge = context.state.relations.require(command.relation_id)
        if edge.kind not in SOCIAL_KINDS:
            raise ValueError("该关系不归人际关系领域管理")
        if command.actor_id not in {edge.source_id, edge.target_id}:
            raise ValueError("只能结束与自己有关的关系")
        _ensure_controlled_alive(context, command.actor_id)
        other_id = edge.target_id if edge.source_id == command.actor_id else edge.source_id
        if edge.kind == "dao_companion":
            penalty = float(
                _relationship_rules(definitions).get(
                    "companion_separation_heart_demon", 25.0
                )
            )
            context.emit(
                "relationship.cultivation.changed",
                source="relations",
                scope=EventScope.entity(command.actor_id),
                payload={"entity_id": command.actor_id, "heart_demon": penalty},
            )
        _set_affinity(context.state, other_id, command.actor_id, 0.0)
        ended = context.state.relations.end(command.relation_id, ended_year=context.state.clock.year)
        metadata = dict(ended.metadata)
        metadata.update({"end_reason": command.reason, "affinity": 0.0})
        ended = context.state.relations.replace_metadata(command.relation_id, metadata)
        context.emit(
            "relationship.ended",
            source="relations",
            scope=EventScope.entity(command.actor_id),
            payload=ended.to_dict(),
        )

    return handler


def _change_affinity_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, ChangeAffinity):
        raise TypeError("命令类型错误")
    _ensure_available_pair(context, command.actor_id, command.target_id)
    if not isinstance(command.amount, (int, float)) or isinstance(command.amount, bool):
        raise ValueError("好感变化必须是数字")
    after = _change_affinity(context.state, command.target_id, command.actor_id, float(command.amount))
    edge = next(
        (edge for edge in context.state.relations.involving(command.actor_id) if command.target_id in {edge.source_id, edge.target_id}),
        None,
    )
    if edge is not None and edge.kind in SOCIAL_KINDS:
        _sync_edge_affinity(context.state, edge, command.actor_id)
    context.emit(
        "relationship.affinity.changed",
        source="relations",
        scope=EventScope.entity(command.actor_id),
        payload={
            "actor_id": command.actor_id, "target_id": command.target_id,
            "amount": float(command.amount), "after": after, "reason": command.reason,
        },
    )


def _relationship_rules(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems.get("relationship", {}))


def _realm_rank(state: WorldState, definitions: GameDefinitions, entity_id: str) -> tuple[int, int]:
    cultivation = state.entities.require(entity_id, CULTIVATION)
    return definitions.realm_index(str(cultivation["realm_id"])), int(cultivation["layer"])


def _same_faction(state: WorldState, first_id: str, second_id: str) -> bool:
    def membership(entity_id: str) -> str | None:
        edge = next(iter(state.relations.find(source_id=entity_id, kind="faction_membership")), None)
        return edge.target_id if edge else None

    first, second = membership(first_id), membership(second_id)
    return first is not None and first == second


def _can_practice(root: RootDefinition, technique: TechniqueDefinition) -> bool:
    if technique.element in {"neutral", "sex"}:
        return True
    elements = set(root.elements)
    if technique.element == "five_elements":
        return {"metal", "wood", "water", "fire", "earth"} <= elements
    return technique.element in elements


def _available_goods(
    state: WorldState,
    definitions: GameDefinitions,
    *,
    recipient_id: str,
    giver_id: str,
    kind: str,
) -> list[str]:
    giver_rank, _ = _realm_rank(state, definitions, giver_id)
    world_id = str(state.entities.require(recipient_id, LOCATION)["world_id"])
    practice = state.entities.require(recipient_id, PRACTICE)
    cultivation = state.entities.require(recipient_id, CULTIVATION)
    root = definitions.roots[str(cultivation["spirit_root"])]
    known = set(map(str, practice.get("known_techniques", [])))
    result: list[str] = []
    for good in definitions.market_goods:
        if good.kind != kind or good.world_id != world_id or good.tier > max(1, giver_rank):
            continue
        if kind == "technique":
            technique = definitions.techniques[good.content_id]
            if good.content_id in known or not _can_practice(root, technique):
                continue
        if good.content_id not in result:
            result.append(good.content_id)
    return result


def _propose_companion_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ProposeDaoCompanion):
            raise TypeError("命令类型错误")
        _ensure_available_pair(context, command.actor_id, command.target_id)
        if _single_edge(context.state, command.actor_id, "dao_companion"):
            raise ValueError("你已经有道侣")
        if _active_edge(context.state, command.actor_id, command.target_id, "concubine"):
            raise ValueError("侍妾不是道侣，必须先解除侍妾名分")
        if _active_edge(context.state, command.actor_id, command.target_id, "master_disciple"):
            raise ValueError("已有师徒名分，不能再结为道侣")
        rules = _relationship_rules(definitions)
        affinity = _affinity(context.state, command.target_id, command.actor_id)
        realm_gap = abs(_realm_rank(context.state, definitions, command.target_id)[0] - _realm_rank(context.state, definitions, command.actor_id)[0])
        chance = max(0.05, min(0.9, float(rules.get("companion_proposal_base", 0.42)) + affinity / 180 - realm_gap * 0.12))
        accepted = context.rng.random() < chance
        if accepted:
            affinity = _change_affinity(context.state, command.target_id, command.actor_id, 12.0)
            edge = _add_relationship(context, FormRelationship(
                command.actor_id, command.target_id, "dao_companion",
                {"affinity": affinity, "last_interactions": {}},
            ))
        else:
            affinity = _change_affinity(context.state, command.target_id, command.actor_id, -3.0)
            edge = None
        context.emit(
            "relationship.dao_companion.proposed",
            source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "target_id": command.target_id,
                "accepted": accepted, "chance": chance, "affinity": affinity,
                "relation_id": edge.relation_id if edge else None,
            },
        )

    return handler


def _consume_item(context: SimulationContext, actor_id: str, item_id: str, reason: str) -> None:
    if inventory_quantity(context.state, actor_id, item_id, spendable=True) < 1:
        raise ValueError("物品栏中没有这件可用物品")
    context.emit(
        "economy.inventory.consume.requested",
        source="relations",
        scope=EventScope.entity(actor_id),
        payload={"entity_id": actor_id, "item_id": item_id, "quantity": 1, "reason": reason},
    )


def _grant_item(context: SimulationContext, actor_id: str, item_id: str, reason: str) -> None:
    context.emit(
        "story.effect.inventory.changed",
        source="relations",
        scope=EventScope.entity(actor_id),
        payload={"entity_id": actor_id, "item_id": item_id, "quantity": 1, "reason": reason},
    )


def _grant_technique(
    context: SimulationContext, actor_id: str, technique_id: str, *, equip_main: bool = False,
) -> None:
    context.emit(
        "relationship.technique.granted",
        source="relations",
        scope=EventScope.entity(actor_id),
        payload={"entity_id": actor_id, "technique_id": technique_id, "equip_main": equip_main},
    )


def _companion_interaction_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, InteractDaoCompanion):
            raise TypeError("命令类型错误")
        _ensure_controlled_alive(context, command.actor_id)
        edge = _single_edge(context.state, command.actor_id, "dao_companion")
        if edge is None:
            raise ValueError("你尚无道侣")
        other_id = edge.target_id if edge.source_id == command.actor_id else edge.source_id
        _ensure_available_pair(context, command.actor_id, other_id)
        metadata = dict(edge.metadata)
        last = dict(metadata.get("last_interactions", {}))
        cooldown_actions = {"intimacy", "entwine", "request_item", "request_technique"}
        rules = _relationship_rules(definitions)
        cooldown = int(rules.get("companion_interaction_cooldown_years", 1))
        if command.action in cooldown_actions and context.state.clock.year - int(last.get(command.action, -10**9)) < cooldown:
            raise ValueError("本年度已经进行过这项道侣互动")
        result: dict[str, Any] = {"action": command.action}
        if command.action in {"intimacy", "entwine"}:
            span_key = f"companion_heart_demon_{command.action}"
            low, high = rules.get(span_key, [1, 3] if command.action == "intimacy" else [3, 7])
            cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
            reduction = min(float(cultivation.get("heart_demon", 0.0)), float(context.rng.randint(int(low), int(high))))
            context.emit(
                "relationship.cultivation.changed", source="relations",
                scope=EventScope.entity(command.actor_id),
                payload={"entity_id": command.actor_id, "heart_demon": -reduction},
            )
            affinity_gain = 1.0 if command.action == "intimacy" else 2.0
            result["heart_demon_reduced"] = reduction
            if command.action == "entwine":
                result["conception_requested"] = True
                context.emit(
                    "family.conception.requested", source="relations",
                    scope=EventScope.entity(command.actor_id),
                    payload={"actor_id": command.actor_id, "partner_id": other_id},
                )
        elif command.action in {"request_item", "request_technique"}:
            kind = command.action.removeprefix("request_")
            candidates = _available_goods(
                context.state, definitions, recipient_id=command.actor_id,
                giver_id=other_id, kind=kind,
            )
            if not candidates:
                raise ValueError("道侣手中没有适合你的新物品或功法")
            affinity = _affinity(context.state, other_id, command.actor_id)
            chance = max(0.08, min(0.9, float(rules.get(f"companion_request_{kind}", 0.5)) + affinity / 250))
            accepted = context.rng.random() < chance
            result.update({"accepted": accepted, "chance": chance})
            affinity_gain = 0.0 if accepted else -1.0
            if accepted:
                content_id = context.rng.choice(candidates)
                result["content_id"] = content_id
                if kind == "item":
                    _grant_item(context, command.actor_id, content_id, "companion_gift")
                else:
                    _grant_technique(context, command.actor_id, content_id)
        elif command.action == "gift_item":
            if command.content_id not in definitions.items:
                raise ValueError("未知物品")
            _consume_item(context, command.actor_id, command.content_id, "companion_gift")
            affinity_gain = 3.0
            gifts = dict(metadata.get("items", {}))
            gifts[command.content_id] = int(gifts.get(command.content_id, 0)) + 1
            metadata["items"] = gifts
        elif command.action == "teach_technique":
            practice = context.state.entities.require(command.actor_id, PRACTICE)
            if command.content_id not in set(map(str, practice.get("known_techniques", []))):
                raise ValueError("你尚未掌握这部功法")
            technique = definitions.techniques[command.content_id]
            other_cultivation = context.state.entities.require(other_id, CULTIVATION)
            root = definitions.roots[str(other_cultivation["spirit_root"])]
            if not _can_practice(root, technique):
                raise ValueError("道侣的灵根无法修习这部功法")
            _grant_technique(context, other_id, command.content_id, equip_main=technique.category == "spiritual")
            affinity_gain = 2.0
        else:
            raise ValueError("未知道侣互动")
        if command.action in cooldown_actions:
            last[command.action] = context.state.clock.year
            metadata["last_interactions"] = last
        affinity = _change_affinity(context.state, other_id, command.actor_id, affinity_gain)
        metadata["affinity"] = affinity
        context.state.relations.replace_metadata(edge.relation_id, metadata)
        context.emit(
            "relationship.dao_companion.interacted", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={"actor_id": command.actor_id, "companion_id": other_id, **result, "affinity": affinity},
        )

    return handler


def _befriend_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BefriendDaoist):
            raise TypeError("命令类型错误")
        _ensure_available_pair(context, command.actor_id, command.target_id)
        if any(
            command.target_id in {edge.source_id, edge.target_id}
            for edge in context.state.relations.involving(command.actor_id)
            if edge.kind in SOCIAL_KINDS
        ):
            raise ValueError("你们已经有其他人际名分")
        rules = _relationship_rules(definitions)
        affinity = _affinity(context.state, command.target_id, command.actor_id)
        required = float(rules.get("friend_affinity_required", 15.0))
        if affinity < required:
            raise ValueError(f"对方好感至少达到 {required:g} 才愿与你结为道友")
        chance = min(0.95, float(rules.get("friend_invite_base", 0.58)) + affinity / 200)
        accepted = context.rng.random() < chance
        edge = _add_relationship(context, FormRelationship(
            command.actor_id, command.target_id, "friend",
            {"affinity": affinity, "last_interactions": {}},
        )) if accepted else None
        context.emit(
            "relationship.friend.proposed", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "target_id": command.target_id,
                "accepted": accepted, "chance": chance,
                "relation_id": edge.relation_id if edge else None,
            },
        )

    return handler


def _friend_interaction_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, InteractDaoFriend):
            raise TypeError("命令类型错误")
        _ensure_available_pair(context, command.actor_id, command.friend_id)
        edge = _active_edge(context.state, command.actor_id, command.friend_id, "friend")
        if edge is None:
            raise ValueError("此人并非你的道友")
        if command.action not in {"spar", "discuss"}:
            raise ValueError("未知道友互动")
        metadata = dict(edge.metadata)
        last = dict(metadata.get("last_interactions", {}))
        rules = _relationship_rules(definitions)
        cooldown = int(rules.get("friend_interaction_cooldown_years", 1))
        if context.state.clock.year - int(last.get(command.action, -10**9)) < cooldown:
            raise ValueError("本年度已经进行过这项道友互动")
        low, high = rules.get(
            "friend_spar_opportunity" if command.action == "spar" else "friend_discuss_opportunity",
            [5, 11] if command.action == "spar" else [6, 13],
        )
        gain = float(context.rng.randint(int(low), int(high)))
        context.emit(
            "relationship.cultivation.changed", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "opportunity": gain},
        )
        affinity = _change_affinity(
            context.state, command.friend_id, command.actor_id,
            1.0 if command.action == "spar" else 2.0,
        )
        last[command.action] = context.state.clock.year
        metadata.update({"last_interactions": last, "affinity": affinity})
        context.state.relations.replace_metadata(edge.relation_id, metadata)
        context.emit(
            "relationship.friend.interacted", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "friend_id": command.friend_id,
                "action": command.action, "opportunity": gain, "affinity": affinity,
            },
        )

    return handler


def _mentorship_request_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RequestMentorship):
            raise TypeError("命令类型错误")
        if command.role not in {"master", "disciple"}:
            raise ValueError("未知师徒关系类型")
        _ensure_available_pair(context, command.actor_id, command.target_id)
        if not _same_faction(context.state, command.actor_id, command.target_id):
            raise ValueError("只有同一宗门人物之间才能直接提出师徒请求")
        profile = _profile(context.state, command.actor_id)
        key = f"{command.role}:{command.target_id}"
        attempts = list(profile.get("attempts", []))
        if key in attempts:
            raise ValueError("你已经向此人提出过同类请求")
        actor_rank = _realm_rank(context.state, definitions, command.actor_id)
        target_rank = _realm_rank(context.state, definitions, command.target_id)
        max_disciples = int(_relationship_rules(definitions).get("max_disciples", 8))
        if command.role == "master":
            if context.state.relations.find(target_id=command.actor_id, kind="master_disciple"):
                raise ValueError("你已经拜有师承")
            if target_rank <= actor_rank:
                raise ValueError("只能拜修为严格高于自己的修士为师")
            master_id, disciple_id = command.target_id, command.actor_id
        else:
            if len(context.state.relations.find(source_id=command.actor_id, kind="master_disciple")) >= max_disciples:
                raise ValueError(f"当前最多记录{max_disciples}名弟子")
            if target_rank >= actor_rank:
                raise ValueError("只能收修为严格低于自己的修士为徒")
            master_id, disciple_id = command.actor_id, command.target_id
        attempts.append(key)
        profile["attempts"] = attempts
        context.state.entities.put(command.actor_id, SOCIAL_PROFILE, profile)
        realm_gap = abs(actor_rank[0] - target_rank[0])
        chance = min(0.82, (0.28 + realm_gap * 0.10) if command.role == "master" else (0.62 + realm_gap * 0.06))
        accepted = context.rng.random() < chance
        edge = _add_relationship(context, FormRelationship(
            master_id, disciple_id, "master_disciple",
            {"affinity": _affinity(context.state, command.target_id, command.actor_id), "last_requests": {}},
        )) if accepted else None
        context.emit(
            "relationship.mentorship.requested", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "target_id": command.target_id,
                "role": command.role, "accepted": accepted, "chance": chance,
                "relation_id": edge.relation_id if edge else None,
            },
        )

    return handler


def _offer_disciple_request_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, OfferDiscipleRequest):
            raise TypeError("命令类型错误")
        if command.master_id != context.state.controlled_entity_id:
            raise ValueError("拜师帖必须交给当前角色处理")
        _ensure_available_pair(context, command.master_id, command.requester_id)
        if _realm_rank(context.state, definitions, command.requester_id) >= _realm_rank(
            context.state, definitions, command.master_id
        ):
            raise ValueError("求道者修为必须严格低于拟拜师者")
        if _active_edge(context.state, command.master_id, command.requester_id, "master_disciple"):
            raise ValueError("双方已经存在师徒关系")
        if any(
            edge.source_id == command.requester_id and edge.target_id == command.master_id
            for edge in context.state.relations.find(kind=PENDING_DISCIPLE_REQUEST)
        ):
            raise ValueError("这份拜师帖已经存在")
        max_disciples = int(_relationship_rules(definitions).get("max_disciples", 8))
        active_count = len(context.state.relations.find(
            source_id=command.master_id, kind="master_disciple"
        ))
        pending_count = len(context.state.relations.find(
            target_id=command.master_id, kind=PENDING_DISCIPLE_REQUEST
        ))
        if active_count + pending_count >= max_disciples:
            raise ValueError(f"当前师徒系统最多记录{max_disciples}名弟子或待决拜师帖")
        edge = context.state.relations.add(
            source_id=command.requester_id, target_id=command.master_id,
            kind=PENDING_DISCIPLE_REQUEST, created_year=context.state.clock.year,
            metadata={"status": "pending"},
        )
        context.emit(
            "relationship.disciple_request.offered", source="relations",
            scope=EventScope.entity(command.master_id), payload=edge.to_dict(),
        )

    return handler


def _respond_disciple_request_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RespondDiscipleRequest):
            raise TypeError("命令类型错误")
        _ensure_controlled_alive(context, command.actor_id)
        request = context.state.relations.require(command.request_id)
        if request.kind != PENDING_DISCIPLE_REQUEST or request.target_id != command.actor_id or not request.active:
            raise ValueError("这份拜师帖已经不存在")
        requester_life = context.state.entities.require(request.source_id, LIFE)
        if command.accept and not bool(requester_life.get("alive")):
            raise ValueError("求道者已经陨落，无法再收入门下")
        max_disciples = int(_relationship_rules(definitions).get("max_disciples", 8))
        if command.accept and len(context.state.relations.find(source_id=command.actor_id, kind="master_disciple")) >= max_disciples:
            raise ValueError(f"当前最多记录{max_disciples}名弟子")
        closed = context.state.relations.end(request.relation_id, ended_year=context.state.clock.year)
        metadata = dict(closed.metadata)
        metadata["status"] = "accepted" if command.accept else "declined"
        context.state.relations.replace_metadata(closed.relation_id, metadata)
        edge = _add_relationship(context, FormRelationship(
            command.actor_id, request.source_id, "master_disciple",
            {"affinity": _affinity(context.state, request.source_id, command.actor_id), "last_requests": {}},
        )) if command.accept else None
        context.emit(
            "relationship.disciple_request.resolved", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={
                "request_id": request.relation_id, "requester_id": request.source_id,
                "accepted": command.accept, "relation_id": edge.relation_id if edge else None,
            },
        )

    return handler


def _request_from_master_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RequestFromMaster):
            raise TypeError("命令类型错误")
        _ensure_controlled_alive(context, command.actor_id)
        if command.kind not in {"item", "technique"}:
            raise ValueError("未知索取类型")
        edge = next(iter(context.state.relations.find(target_id=command.actor_id, kind="master_disciple")), None)
        if edge is None:
            raise ValueError("你尚无师承")
        _ensure_available_pair(context, command.actor_id, edge.source_id)
        metadata = dict(edge.metadata)
        last_requests = dict(metadata.get("last_requests", {}))
        if last_requests.get(command.kind) == context.state.clock.year:
            raise ValueError("本年度已经向师父提出过这类请求")
        candidates = _available_goods(
            context.state, definitions, recipient_id=command.actor_id,
            giver_id=edge.source_id, kind=command.kind,
        )
        if not candidates:
            raise ValueError("师父手中已无适合你的新物品或功法")
        chance = float(dict(_relationship_rules(definitions).get("master_request_acceptance", {})).get(command.kind, 0.5))
        accepted = context.rng.random() < chance
        content_id = context.rng.choice(candidates) if accepted else None
        if content_id:
            if command.kind == "item":
                _grant_item(context, command.actor_id, content_id, "master_gift")
            else:
                _grant_technique(context, command.actor_id, content_id)
        last_requests[command.kind] = context.state.clock.year
        metadata["last_requests"] = last_requests
        context.state.relations.replace_metadata(edge.relation_id, metadata)
        context.emit(
            "relationship.master.requested", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "master_id": edge.source_id,
                "kind": command.kind, "accepted": accepted,
                "chance": chance, "content_id": content_id,
            },
        )

    return handler


def _gift_disciple_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, GiftDisciple):
            raise TypeError("命令类型错误")
        _ensure_available_pair(context, command.actor_id, command.disciple_id)
        edge = next(
            (
                edge for edge in context.state.relations.find(
                    source_id=command.actor_id, kind="master_disciple"
                ) if edge.target_id == command.disciple_id
            ),
            None,
        )
        if edge is None:
            raise ValueError("此人并非你的弟子")
        metadata = dict(edge.metadata)
        if command.kind == "item":
            if command.content_id not in definitions.items:
                raise ValueError("未知物品")
            _consume_item(context, command.actor_id, command.content_id, "disciple_gift")
            gifts = dict(metadata.get("items", {}))
            gifts[command.content_id] = int(gifts.get(command.content_id, 0)) + 1
            metadata["items"] = gifts
            if "pill" in definitions.items[command.content_id].tags:
                demonic = dict(definitions.systems.get("demonic_cultivation", {}))
                metadata["breakthrough_bonus"] = min(
                    0.35,
                    float(metadata.get("breakthrough_bonus", 0.0))
                    + float(demonic.get("pill_breakthrough_bonus", 0.05)),
                )
        elif command.kind == "technique":
            practice = context.state.entities.require(command.actor_id, PRACTICE)
            if command.content_id not in set(map(str, practice.get("known_techniques", []))):
                raise ValueError("你尚未掌握这部功法")
            taught = list(map(str, metadata.get("techniques", [])))
            if command.content_id in taught:
                raise ValueError("这名弟子已经受过此法")
            technique = definitions.techniques[command.content_id]
            other_cultivation = context.state.entities.require(command.disciple_id, CULTIVATION)
            root = definitions.roots[str(other_cultivation["spirit_root"])]
            if not _can_practice(root, technique):
                raise ValueError("弟子的灵根无法修习这部功法")
            taught.append(command.content_id)
            metadata["techniques"] = taught
            _grant_technique(context, command.disciple_id, command.content_id)
        else:
            raise ValueError("未知赠予类型")
        context.state.relations.replace_metadata(edge.relation_id, metadata)
        context.emit(
            "relationship.disciple.gifted", source="relations",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "disciple_id": command.disciple_id,
                "kind": command.kind, "content_id": command.content_id,
            },
        )

    return handler


def _on_permanent_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    keep_ids = set(map(str, event.payload.get("keep_relationship_ids", [])))
    ended: list[str] = []
    for edge in list(context.state.relations.involving(actor_id)):
        if edge.kind not in SOCIAL_KINDS:
            continue
        other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
        if other_id in keep_ids and edge.kind in {"friend", "dao_companion"}:
            continue
        closed = context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
        metadata = dict(closed.metadata)
        metadata["end_reason"] = "permanent_world_transition"
        context.state.relations.replace_metadata(closed.relation_id, metadata)
        ended.append(edge.relation_id)
    for request in list(context.state.relations.involving(actor_id, kind=PENDING_DISCIPLE_REQUEST)):
        context.state.relations.end(request.relation_id, ended_year=context.state.clock.year)
    context.emit(
        "world.transition.acknowledged",
        source="relations",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": event.payload["transaction_id"],
            "actor_id": actor_id, "domain": "relations", "ended_ids": ended,
        },
    )


def _on_faction_relationship_invited(
    context: SimulationContext, event: EventEnvelope,
) -> None:
    actor_id = str(event.payload["actor_id"])
    character_id = str(event.payload["character_id"])
    affinity = _change_affinity(context.state, character_id, actor_id, 4.0)
    relation_id = str(event.payload["relationship_id"])
    edge = context.state.relations.require(relation_id)
    metadata = dict(edge.metadata)
    metadata["affinity"] = affinity
    context.state.relations.replace_metadata(relation_id, metadata)


def relationship_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    active = [edge for edge in state.relations.find() if edge.kind in SOCIAL_KINDS]
    seen_pair: set[tuple[str, str]] = set()
    companion_counts: dict[str, int] = {}
    disciple_counts: dict[str, int] = {}
    concubine_counts: dict[str, int] = {}
    for entity_id in state.entities.with_component(IDENTITY):
        profile = state.entities.get(entity_id, SOCIAL_PROFILE)
        if profile is None:
            errors.append(f"角色 {entity_id} 缺少关系档案")
            continue
        affinities = dict(profile.get("affinities", {}))
        if any(not state.entities.exists(str(other_id)) for other_id in affinities):
            errors.append(f"角色 {entity_id} 的好感档案引用未知人物")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in affinities.values()):
            errors.append(f"角色 {entity_id} 的好感数值非法")
        attempts = list(profile.get("attempts", []))
        if len(attempts) != len(set(attempts)):
            errors.append(f"角色 {entity_id} 的关系请求记录重复")
    for edge in active:
        if state.entities.get(edge.source_id, IDENTITY) is None or state.entities.get(edge.target_id, IDENTITY) is None:
            errors.append(f"人物关系端点不是角色：{edge.relation_id}")
        pair = tuple(sorted((edge.source_id, edge.target_id)))
        if pair in seen_pair:
            errors.append(f"同一人物对存在多个有效角色关系：{pair}")
        seen_pair.add(pair)
        if edge.kind in SYMMETRIC_KINDS and edge.source_id > edge.target_id:
            errors.append(f"对称关系端点未规范化：{edge.relation_id}")
        if edge.kind == "dao_companion":
            for entity_id in pair:
                companion_counts[entity_id] = companion_counts.get(entity_id, 0) + 1
        elif edge.kind == "master_disciple":
            disciple_counts[edge.target_id] = disciple_counts.get(edge.target_id, 0) + 1
        elif edge.kind == "concubine":
            concubine_counts[edge.target_id] = concubine_counts.get(edge.target_id, 0) + 1
    if any(count > 1 for count in companion_counts.values()):
        errors.append("人物拥有多个有效道侣")
    if any(count > 1 for count in disciple_counts.values()):
        errors.append("弟子拥有多个有效师父")
    if any(count > 1 for count in concubine_counts.values()):
        errors.append("侍妾拥有多个有效侍奉对象")
    for edge in (edge for edge in active if edge.kind == "master_disciple"):
        if _master_reaches(state, edge.target_id, edge.source_id):
            errors.append("师徒关系存在循环")
            break
    for edge in state.relations.find(kind=PENDING_DISCIPLE_REQUEST):
        if edge.metadata.get("status") != "pending":
            errors.append(f"有效拜师帖状态非法：{edge.relation_id}")
    return errors


def register_relationship_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(FormRelationship, _form_relationship)
    bus.register(EndRelationship, _end_relationship_handler(definitions))
    bus.register(ChangeAffinity, _change_affinity_handler)
    bus.register(ProposeDaoCompanion, _propose_companion_handler(definitions))
    bus.register(InteractDaoCompanion, _companion_interaction_handler(definitions))
    bus.register(BefriendDaoist, _befriend_handler(definitions))
    bus.register(InteractDaoFriend, _friend_interaction_handler(definitions))
    bus.register(RequestMentorship, _mentorship_request_handler(definitions))
    bus.register(OfferDiscipleRequest, _offer_disciple_request_handler(definitions))
    bus.register(RespondDiscipleRequest, _respond_disciple_request_handler(definitions))
    bus.register(RequestFromMaster, _request_from_master_handler(definitions))
    bus.register(GiftDisciple, _gift_disciple_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("faction.relationship.invited", _on_faction_relationship_invited)
    bus.event_bus.register("world.permanent_transition.requested", _on_permanent_world_transition)


def relationship_view(state: Any, entity_id: str | None = None) -> list[dict[str, Any]]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    rows = []
    for edge in (
        edge for edge in state.relations.involving(actor_id)
        if edge.kind in SOCIAL_KINDS
    ):
        other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
        other = character_view(state, other_id)
        metadata = dict(edge.metadata)
        metadata["affinity"] = _affinity(state, other_id, actor_id)
        rows.append({
            "relation_id": edge.relation_id,
            "kind": edge.kind,
            "direction": "source" if edge.source_id == actor_id else "target",
            "role": (
                "master" if edge.kind == "master_disciple" and edge.source_id == actor_id
                else "disciple" if edge.kind == "master_disciple"
                else edge.kind
            ),
            "other": {
                "id": other["id"], "name": other["name"], "gender": other["gender"],
                "age": other["age"], "lifespan": other["lifespan"],
                "alive": other["alive"], "death_reason": other["death_reason"],
            },
            "created_year": edge.created_year,
            "metadata": metadata,
        })
    return rows


def disciple_request_view(state: Any, entity_id: str | None = None) -> list[dict[str, Any]]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    return [
        {
            "request_id": edge.relation_id,
            "requester": character_view(state, edge.source_id),
            "created_year": edge.created_year,
        }
        for edge in state.relations.find(target_id=actor_id, kind=PENDING_DISCIPLE_REQUEST)
    ]
