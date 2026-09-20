from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import ACTION_RUNTIME
from .character import IDENTITY, LIFE, character_view
from .combat import combat_snapshot
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions, RootDefinition, TechniqueDefinition
from .relations import (
    SOCIAL_KINDS,
    relationship_affinity,
    set_relationship_affinity,
)
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, RelationEdge, WorldState


CONCUBINE_STATE = "relations.concubine_state"


@dataclass(frozen=True, slots=True)
class ManageConcubine:
    actor_id: str
    target_id: str
    action: str


@dataclass(frozen=True, slots=True)
class EnterConcubineStatus:
    actor_id: str
    owner_id: str
    forced: bool = False


@dataclass(frozen=True, slots=True)
class ManageConcubineStatus:
    actor_id: str
    action: str
    method: str = ""


def _default_state() -> dict[str, Any]:
    return {
        "cauldron_breakthrough_bonus": 0.0,
        "escape_reputation": 0,
        "rejection_aftermath": [],
        "revenge_cooldown": {
            "global_count": 0,
            "next_unit": -1,
            "sources": {},
        },
    }


def reconcile_concubine_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        component = state.entities.get(entity_id, CONCUBINE_STATE) or _default_state()
        component["cauldron_breakthrough_bonus"] = max(
            0.0, min(0.02, float(component.get("cauldron_breakthrough_bonus", 0.0)))
        )
        component["escape_reputation"] = max(
            0, int(component.get("escape_reputation", 0))
        )
        aftermath = []
        for raw in component.get("rejection_aftermath", []):
            if not isinstance(raw, dict) or not str(raw.get("owner_id", "")):
                continue
            row = dict(raw)
            declined = max(0, int(row.get("declined_unit", 0)))
            row["declined_unit"] = declined
            row["expires_unit"] = max(
                declined, int(row.get("expires_unit", declined + 2))
            )
            row["last_checked_unit"] = min(
                row["expires_unit"],
                max(declined, int(row.get("last_checked_unit", declined))),
            )
            aftermath.append(row)
        component["rejection_aftermath"] = aftermath
        cooldown = dict(component.get("revenge_cooldown", {}))
        cooldown["global_count"] = max(0, int(cooldown.get("global_count", 0)))
        cooldown["next_unit"] = int(cooldown.get("next_unit", -1))
        cooldown["sources"] = {
            str(key): {
                "count": max(0, int(dict(value).get("count", 0))),
                "next_unit": int(dict(value).get("next_unit", -1)),
            }
            for key, value in dict(cooldown.get("sources", {})).items()
            if isinstance(value, dict)
        }
        component["revenge_cooldown"] = cooldown
        state.entities.put(entity_id, CONCUBINE_STATE, component)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(
        str(event.payload["entity_id"]), CONCUBINE_STATE, _default_state()
    )


def _rank(
    state: WorldState, definitions: GameDefinitions, entity_id: str,
) -> tuple[int, int]:
    cultivation = state.entities.require(entity_id, CULTIVATION)
    return definitions.realm_index(str(cultivation["realm_id"])), int(cultivation["layer"])


def _action_unit(state: WorldState, actor_id: str) -> int:
    runtime = state.entities.require(actor_id, ACTION_RUNTIME)
    return max(0, int(runtime.get("next_sequence", 1)) - 1)


def _ensure_pair(
    context: SimulationContext,
    actor_id: str,
    target_id: str,
    *,
    require_available: bool = True,
) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    story = context.state.entities.get(actor_id, "story.state") or {}
    if story.get("pending") is not None:
        raise ValueError("请先处理当前事件")
    if context.state.relations.find(target_id=actor_id, kind="combat_prisoner"):
        raise ValueError("身陷牢狱时无法处理侍妾事务")
    for entity_id in (actor_id, target_id):
        if not context.state.entities.exists(entity_id):
            raise ValueError("人物不存在")
        if (entity_id == actor_id or require_available) and not bool(
            context.state.entities.require(entity_id, LIFE).get("alive")
        ):
            raise ValueError("死亡人物不能处理侍妾事务")
    actor_location = context.state.entities.require(actor_id, LOCATION)
    target_location = context.state.entities.require(target_id, LOCATION)
    if require_available and actor_location.get("world_id") != target_location.get("world_id"):
        raise ValueError("人物不在同一世界")


def _edge_for(
    state: WorldState, owner_id: str, concubine_id: str,
) -> RelationEdge | None:
    return next(
        (
            edge for edge in state.relations.find(
                source_id=owner_id, kind="concubine"
            ) if edge.target_id == concubine_id
        ),
        None,
    )


def _close_pair_relationships(
    context: SimulationContext, first_id: str, second_id: str,
) -> None:
    for edge in list(context.state.relations.involving(first_id)):
        if edge.kind not in SOCIAL_KINDS or second_id not in {edge.source_id, edge.target_id}:
            continue
        closed = context.state.relations.end(
            edge.relation_id, ended_year=context.state.clock.year
        )
        metadata = dict(closed.metadata)
        metadata["end_reason"] = "converted_to_concubine"
        context.state.relations.replace_metadata(closed.relation_id, metadata)


def _set_concubine_status(
    context: SimulationContext,
    actor_id: str,
    owner_id: str,
    *,
    forced: bool,
) -> RelationEdge:
    _close_pair_relationships(context, actor_id, owner_id)
    component = context.state.entities.get(actor_id, CONCUBINE_STATE)
    if component is not None:
        component["rejection_aftermath"] = []
        context.state.entities.put(actor_id, CONCUBINE_STATE, component)
    return context.state.relations.add(
        source_id=owner_id,
        target_id=actor_id,
        kind="concubine",
        created_year=context.state.clock.year,
        metadata={
            "joined_year": context.state.clock.year,
            "turns": 0,
            "last_drain": 0.0,
            "dependent": False,
            "forced": forced,
            "failed_escape_count": 0,
            "last_requests": {},
            "angered_until_unit": -1,
        },
    )


def _manage_concubine_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ManageConcubine):
            raise TypeError("命令类型错误")
        _ensure_pair(
            context,
            command.actor_id,
            command.target_id,
            require_available=command.action != "dismiss",
        )
        edge = _edge_for(context.state, command.actor_id, command.target_id)
        if command.action == "recruit":
            if edge is not None:
                raise ValueError("此人已经在侍妾名册中")
            identity = context.state.entities.require(command.target_id, IDENTITY)
            if identity.get("gender") != "female":
                raise ValueError("侍妾名分只可向女性修士提出")
            actor_rank = _rank(context.state, definitions, command.actor_id)
            target_rank = _rank(context.state, definitions, command.target_id)
            if target_rank > actor_rank:
                raise ValueError("修为高于你的修士必定拒绝侍妾之请")
            realm_gap = actor_rank[0] - target_rank[0]
            layer_gap = actor_rank[1] - target_rank[1] if realm_gap == 0 else 0
            affinity = relationship_affinity(
                context.state, command.target_id, command.actor_id
            )
            chance = max(
                0.12,
                min(0.96, 0.34 + realm_gap * 0.14 + layer_gap * 0.025 + affinity / 300),
            )
            accepted = context.rng.random() < chance
            if accepted:
                _close_pair_relationships(
                    context, command.actor_id, command.target_id
                )
                edge = context.state.relations.add(
                    source_id=command.actor_id,
                    target_id=command.target_id,
                    kind="concubine",
                    created_year=context.state.clock.year,
                    metadata={
                        "joined_year": context.state.clock.year,
                        "last_cauldron_unit": None,
                        "cauldron_uses": 0,
                        "affinity": affinity,
                        "source": "world",
                    },
                )
            else:
                affinity = set_relationship_affinity(
                    context.state, command.target_id, command.actor_id, affinity - 6
                )
            context.emit(
                "relationship.concubine.recruited",
                source="concubines",
                scope=EventScope.entity(command.actor_id),
                payload={
                    "actor_id": command.actor_id,
                    "target_id": command.target_id,
                    "accepted": accepted,
                    "chance": chance,
                    "relation_id": edge.relation_id if accepted and edge else None,
                    "affinity": affinity,
                },
            )
            return
        if edge is None:
            raise ValueError("侍妾名册中没有此人")
        if command.action == "cauldron":
            metadata = dict(edge.metadata)
            unit = _action_unit(context.state, command.actor_id)
            if metadata.get("last_cauldron_unit") == unit:
                raise ValueError("本行动单位已经以此人作过炉鼎")
            actor_cultivation = context.state.entities.require(
                command.actor_id, CULTIVATION
            )
            target_rank = _rank(context.state, definitions, command.target_id)[0]
            realm = definitions.realm(str(actor_cultivation["realm_id"]))
            required = round(
                realm.opportunity_base
                * (1 + 0.12 * (int(actor_cultivation["layer"]) - 1))
            )
            dependent = bool(context.state.relations.find(
                target_id=command.actor_id, kind="concubine"
            ))
            gain = round(
                required * (0.018 + target_rank * 0.003) * (0.8 if dependent else 1.0),
                1,
            )
            context.emit(
                "relationship.cultivation.changed",
                source="concubines",
                scope=EventScope.entity(command.actor_id),
                payload={"entity_id": command.actor_id, "opportunity": gain},
            )
            for kind in ("restore_hp", "restore_mp"):
                context.emit(
                    "story.effect.combat_condition.changed",
                    source="concubines",
                    scope=EventScope.entity(command.actor_id),
                    payload={"entity_id": command.actor_id, "kind": kind, "amount": 0.24},
                )
            metadata["last_cauldron_unit"] = unit
            metadata["cauldron_uses"] = int(metadata.get("cauldron_uses", 0)) + 1
            affinity = set_relationship_affinity(
                context.state,
                command.target_id,
                command.actor_id,
                relationship_affinity(context.state, command.target_id, command.actor_id) - 8,
            )
            metadata["affinity"] = affinity
            practice = context.state.entities.require(command.actor_id, PRACTICE)
            main_id = practice.get("main_technique_id")
            if main_id and definitions.techniques[str(main_id)].element == "sex":
                state = context.state.entities.require(
                    command.actor_id, CONCUBINE_STATE
                )
                state["cauldron_breakthrough_bonus"] = min(
                    0.02, float(state.get("cauldron_breakthrough_bonus", 0.0)) + 0.01
                )
                context.state.entities.put(command.actor_id, CONCUBINE_STATE, state)
            context.state.relations.replace_metadata(edge.relation_id, metadata)
            context.emit(
                "relationship.concubine.cauldron_used",
                source="concubines",
                scope=EventScope.entity(command.actor_id),
                payload={
                    "actor_id": command.actor_id,
                    "target_id": command.target_id,
                    "opportunity": gain,
                    "affinity": affinity,
                },
            )
        elif command.action == "dismiss":
            closed = context.state.relations.end(
                edge.relation_id, ended_year=context.state.clock.year
            )
            metadata = dict(closed.metadata)
            metadata["end_reason"] = "dismissed"
            metadata["affinity"] = 0.0
            context.state.relations.replace_metadata(closed.relation_id, metadata)
            set_relationship_affinity(
                context.state, command.target_id, command.actor_id, 0.0
            )
            context.emit(
                "relationship.concubine.dismissed",
                source="concubines",
                scope=EventScope.entity(command.actor_id),
                payload={"actor_id": command.actor_id, "target_id": command.target_id},
            )
        elif command.action == "corpse":
            from .demonic import convert_relationship_to_corpse

            result = convert_relationship_to_corpse(
                context, definitions, command.actor_id, command.target_id
            )
            context.emit(
                "relationship.concubine.corpse_conversion",
                source="concubines",
                scope=EventScope.entity(command.actor_id),
                payload={
                    "actor_id": command.actor_id,
                    "target_id": command.target_id,
                    **result,
                },
            )
        else:
            raise ValueError("未知侍妾操作")

    return handler


def _enter_status_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, EnterConcubineStatus):
            raise TypeError("命令类型错误")
        _ensure_pair(context, command.actor_id, command.owner_id)
        identity = context.state.entities.require(command.actor_id, IDENTITY)
        if identity.get("gender") != "female":
            raise ValueError("只有女性角色会进入他人的侍妾处境")
        if context.state.relations.find(target_id=command.actor_id, kind="concubine"):
            raise ValueError("当前角色已经有正主")
        if _rank(context.state, definitions, command.owner_id) <= _rank(
            context.state, definitions, command.actor_id
        ) and not command.forced:
            raise ValueError("修为不高于你的修士无法迫使你成为侍妾")
        edge = _set_concubine_status(
            context,
            command.actor_id,
            command.owner_id,
            forced=bool(command.forced),
        )
        context.emit(
            "relationship.concubine.status_entered",
            source="concubines",
            scope=EventScope.entity(command.actor_id),
            payload=edge.to_dict(),
        )

    return handler


def _can_practice(root: RootDefinition, technique: TechniqueDefinition) -> bool:
    if technique.element in {"neutral", "sex"}:
        return True
    elements = set(root.elements)
    if technique.element == "five_elements":
        return {"metal", "wood", "water", "fire", "earth"} <= elements
    return technique.element in elements


def _status_edge(state: WorldState, actor_id: str) -> RelationEdge | None:
    return next(iter(state.relations.find(target_id=actor_id, kind="concubine")), None)


def _manage_status_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ManageConcubineStatus):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能控制当前角色")
        edge = _status_edge(context.state, command.actor_id)
        if edge is None:
            raise ValueError("你当前并非他人的侍妾")
        owner_life = context.state.entities.require(edge.source_id, LIFE)
        owner_world = context.state.entities.require(edge.source_id, LOCATION).get(
            "world_id"
        )
        actor_world = context.state.entities.require(command.actor_id, LOCATION).get(
            "world_id"
        )
        if not bool(owner_life.get("alive")) or owner_world != actor_world:
            closed = context.state.relations.end(
                edge.relation_id, ended_year=context.state.clock.year
            )
            metadata = dict(closed.metadata)
            metadata["end_reason"] = "owner_unavailable"
            context.state.relations.replace_metadata(closed.relation_id, metadata)
            context.emit(
                "relationship.concubine.status_released",
                source="concubines",
                scope=EventScope.entity(command.actor_id),
                payload={"actor_id": command.actor_id, "owner_id": edge.source_id},
            )
            return
        _ensure_pair(context, command.actor_id, edge.source_id)
        metadata = dict(edge.metadata)
        owner_id = edge.source_id
        if command.action == "depend":
            if metadata.get("dependent"):
                raise ValueError("你已经选择依附正主")
            metadata["dependent"] = True
            affinity = relationship_affinity(
                context.state, owner_id, command.actor_id
            ) + 10
            set_relationship_affinity(context.state, owner_id, command.actor_id, affinity)
            context.state.relations.replace_metadata(edge.relation_id, metadata)
            payload = {"result": "dependent", "affinity": affinity}
        elif command.action == "escape":
            method = command.method
            if not method:
                from .story import queue_story_event

                queue_story_event(
                    context,
                    definitions,
                    command.actor_id,
                    "SYS_CONCUBINE_ESCAPE",
                    reason="concubine_escape",
                    runtime=_owner_runtime(
                        context.state, definitions, owner_id
                    ),
                )
                payload = {"result": "escape_planned", "chance": None}
                context.emit(
                    "relationship.concubine.status_managed",
                    source="concubines",
                    scope=EventScope.entity(command.actor_id),
                    payload={
                        "actor_id": command.actor_id,
                        "owner_id": owner_id,
                        "action": command.action,
                        **payload,
                    },
                )
                return
            if method == "abandon":
                payload = {"result": "abandoned", "chance": None}
            elif method in {"covert", "plead"}:
                owner_rank = _rank(context.state, definitions, owner_id)
                actor_rank = _rank(context.state, definitions, command.actor_id)
                gap = max(0, owner_rank[0] - actor_rank[0])
                chance = 0.18 if method == "plead" else 0.28
                chance += 0.10 if metadata.get("dependent") and method == "plead" else 0.0
                chance -= gap * 0.04
                chance += min(0.12, int(metadata.get("turns", 0)) * 0.015)
                chance = max(0.05, min(0.78, chance))
                escaped = context.rng.random() < chance
                if escaped:
                    closed = context.state.relations.end(
                        edge.relation_id, ended_year=context.state.clock.year
                    )
                    closed_meta = dict(closed.metadata)
                    closed_meta["end_reason"] = "escaped"
                    context.state.relations.replace_metadata(
                        closed.relation_id, closed_meta
                    )
                    set_relationship_affinity(
                        context.state, owner_id, command.actor_id, 0.0
                    )
                    state = context.state.entities.require(
                        command.actor_id, CONCUBINE_STATE
                    )
                    state["escape_reputation"] = int(
                        state.get("escape_reputation", 0)
                    ) + 1
                    context.state.entities.put(
                        command.actor_id, CONCUBINE_STATE, state
                    )
                else:
                    metadata["failed_escape_count"] = int(
                        metadata.get("failed_escape_count", 0)
                    ) + 1
                    metadata["angered_until_unit"] = _action_unit(
                        context.state, command.actor_id
                    ) + 2
                    context.state.relations.replace_metadata(
                        edge.relation_id, metadata
                    )
                    set_relationship_affinity(
                        context.state,
                        owner_id,
                        command.actor_id,
                        relationship_affinity(
                            context.state, owner_id, command.actor_id
                        ) - 18,
                    )
                payload = {"result": "escaped" if escaped else "escape_failed", "chance": chance}
            else:
                raise ValueError("未知的脱身方式")
        elif command.action in {"request_technique", "request_stones", "request_equipment"}:
            kind = command.action.removeprefix("request_")
            unit = _action_unit(context.state, command.actor_id)
            last = dict(metadata.get("last_requests", {}))
            if int(last.get(kind, -1)) == unit:
                raise ValueError("本行动单位已经索要过这类资源")
            owner_realm = _rank(context.state, definitions, owner_id)[0]
            candidates: list[str] = []
            if kind == "technique":
                cultivation = context.state.entities.require(
                    command.actor_id, CULTIVATION
                )
                root = definitions.roots[str(cultivation["spirit_root"])]
                known = set(context.state.entities.require(
                    command.actor_id, PRACTICE
                ).get("known_techniques", []))
                candidates = [
                    technique_id for technique_id, technique in definitions.techniques.items()
                    if technique.grade <= max(1, owner_realm + 1)
                    and technique_id not in known and _can_practice(root, technique)
                ]
            elif kind == "equipment":
                candidates = list(dict.fromkeys(
                    good.content_id for good in definitions.market_goods
                    if good.kind == "item" and good.tier <= max(1, owner_realm + 1)
                    and definitions.items[good.content_id].combat_bonus > 0
                ))
            if kind in {"technique", "equipment"} and not candidates:
                raise ValueError("正主手中没有适合你的新资源")
            affinity = relationship_affinity(context.state, owner_id, command.actor_id)
            base = {"technique": 0.27, "stones": 0.55, "equipment": 0.34}[kind]
            chance = max(0.08, min(0.92, base + affinity / 350 + (0.22 if metadata.get("dependent") else 0.0)))
            accepted = context.rng.random() < chance
            content_id = None
            quantity = 0
            if accepted and kind == "technique":
                content_id = context.rng.choice(candidates)
                context.emit(
                    "relationship.technique.granted", source="concubines",
                    scope=EventScope.entity(command.actor_id),
                    payload={"entity_id": command.actor_id, "technique_id": content_id},
                )
            elif accepted and kind == "equipment":
                content_id = context.rng.choice(candidates)
                context.emit(
                    "story.effect.inventory.changed", source="concubines",
                    scope=EventScope.entity(command.actor_id),
                    payload={"entity_id": command.actor_id, "item_id": content_id, "quantity": 1, "reason": "concubine_owner_gift"},
                )
            elif accepted:
                quantity = max(
                    3,
                    int(
                        4
                        * max(1, owner_realm) ** 2
                        * context.rng.uniform(0.8, 1.25)
                    ),
                )
                context.emit(
                    "story.effect.inventory.changed", source="concubines",
                    scope=EventScope.entity(command.actor_id),
                    payload={"entity_id": command.actor_id, "item_id": "spirit_stone", "quantity": quantity, "reason": "concubine_owner_gift"},
                )
            else:
                set_relationship_affinity(
                    context.state, owner_id, command.actor_id, affinity - 3
                )
            last[kind] = unit
            metadata["last_requests"] = last
            context.state.relations.replace_metadata(edge.relation_id, metadata)
            payload = {
                "result": "given" if accepted else "request_refused",
                "kind": kind,
                "chance": chance,
                "content_id": content_id,
                "quantity": quantity,
            }
        else:
            raise ValueError("未知侍妾处境操作")
        context.emit(
            "relationship.concubine.status_managed",
            source="concubines",
            scope=EventScope.entity(command.actor_id),
            payload={"actor_id": command.actor_id, "owner_id": owner_id, "action": command.action, **payload},
        )

    return handler


def _owner_runtime(
    state: WorldState, definitions: GameDefinitions, owner_id: str,
) -> dict[str, Any]:
    identity = state.entities.require(owner_id, IDENTITY)
    cultivation = state.entities.require(owner_id, CULTIVATION)
    realm = definitions.realm(str(cultivation["realm_id"]))
    return {
        "owner_id": owner_id,
        "owner_name": str(identity["name"]),
        "owner_realm_index": definitions.realm_index(realm.id),
        "owner_layer": int(cultivation["layer"]),
        "owner_realm": realm.name,
        "owner_realm_name": realm.name,
        "owner_world": str(state.entities.require(owner_id, LOCATION)["world_id"]),
    }


def _revenge_ready(component: dict[str, Any], owner_id: str, unit: int) -> bool:
    cooldown = dict(component.get("revenge_cooldown", {}))
    source = dict(dict(cooldown.get("sources", {})).get(owner_id, {}))
    return unit >= max(
        int(cooldown.get("next_unit", -1)), int(source.get("next_unit", -1))
    )


def _record_revenge_trigger(
    component: dict[str, Any], definitions: GameDefinitions, owner_id: str, unit: int,
) -> int:
    rules = dict(definitions.systems.get("relationship", {}))
    base = max(1, int(rules.get("revenge_cooldown_base_units", 3)))
    increment = max(0, int(rules.get("revenge_cooldown_increment_units", 2)))
    maximum = max(base, int(rules.get("revenge_cooldown_max_units", 15)))
    cooldown = dict(component.get("revenge_cooldown", {}))
    global_count = max(0, int(cooldown.get("global_count", 0))) + 1
    sources = dict(cooldown.get("sources", {}))
    source = dict(sources.get(owner_id, {}))
    source["count"] = max(0, int(source.get("count", 0))) + 1
    interval = min(maximum, base + (global_count - 1) * increment)
    next_unit = unit + interval
    source["next_unit"] = next_unit
    sources[owner_id] = source
    cooldown.update(
        global_count=global_count, next_unit=next_unit, sources=sources
    )
    component["revenge_cooldown"] = cooldown
    return interval


def _advance_rejection_aftermath(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    component: dict[str, Any],
) -> bool:
    from .story import queue_story_event

    current_unit = _action_unit(context.state, actor_id)
    kept: list[dict[str, Any]] = []
    triggered: dict[str, Any] | None = None
    for raw in component.get("rejection_aftermath", []):
        record = dict(raw)
        declined = int(record.get("declined_unit", current_unit))
        expires = int(record.get("expires_unit", declined + 2))
        if current_unit <= int(record.get("last_checked_unit", declined)):
            kept.append(record)
            continue
        owner_id = str(record.get("owner_id", ""))
        if (
            not context.state.entities.exists(owner_id)
            or not bool(context.state.entities.require(owner_id, LIFE).get("alive"))
            or context.state.entities.require(owner_id, LOCATION).get("world_id")
            != context.state.entities.require(actor_id, LOCATION).get("world_id")
            or current_unit > expires
        ):
            continue
        record["last_checked_unit"] = current_unit
        if (
            triggered is None
            and _revenge_ready(component, owner_id, current_unit)
            and context.rng.random() < 0.30
        ):
            record["revenge_cooldown_units"] = _record_revenge_trigger(
                component, definitions, owner_id, current_unit
            )
            triggered = record
            continue
        if current_unit < expires:
            kept.append(record)
    component["rejection_aftermath"] = kept
    context.state.entities.put(actor_id, CONCUBINE_STATE, component)
    if triggered is None:
        return False
    queue_story_event(
        context,
        definitions,
        actor_id,
        "SYS_CONCUBINE_REVENGE",
        reason="concubine_rejection_revenge",
        runtime=triggered,
    )
    return True


def _maybe_queue_proposal(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    component: dict[str, Any],
) -> bool:
    from .story import queue_story_event

    identity = context.state.entities.require(actor_id, IDENTITY)
    if (
        identity.get("gender") != "female"
        or _status_edge(context.state, actor_id) is not None
        or component.get("rejection_aftermath")
    ):
        return False
    actor_realm, actor_layer = _rank(context.state, definitions, actor_id)
    world_id = str(context.state.entities.require(actor_id, LOCATION)["world_id"])
    world = definitions.worlds[world_id]
    realm_cap = min(len(definitions.realms) - 1, world.npc_realm_cap)
    if actor_realm >= realm_cap - 1:
        return False
    candidates = [
        entity_id
        for entity_id in context.state.entities.with_component(IDENTITY)
        if entity_id != actor_id
        and context.state.entities.get(entity_id, "world.npc_profile") is None
        and context.state.entities.require(entity_id, IDENTITY).get("gender") == "male"
        and bool(context.state.entities.require(entity_id, LIFE).get("alive"))
        and context.state.entities.require(entity_id, LOCATION).get("world_id") == world_id
        and _rank(context.state, definitions, entity_id) > (actor_realm, actor_layer)
    ]
    if not candidates:
        return False
    candidates.sort(
        key=lambda entity_id: _rank(context.state, definitions, entity_id),
        reverse=True,
    )
    owner_id = context.rng.choice(candidates[: min(8, len(candidates))])
    gap = max(1, _rank(context.state, definitions, owner_id)[0] - actor_realm)
    reputation_multiplier = max(
        0.01, 0.20 ** int(component.get("escape_reputation", 0))
    )
    chance = min(0.32, 0.05 + gap * 0.035) * reputation_multiplier
    if context.rng.random() >= chance:
        return False
    queue_story_event(
        context,
        definitions,
        actor_id,
        "SYS_CONCUBINE_PROPOSAL",
        reason="concubine_proposal",
        runtime=_owner_runtime(context.state, definitions, owner_id),
    )
    return True


def _on_action_completed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        if actor_id != context.state.controlled_entity_id:
            return
        story = context.state.entities.require(actor_id, "story.state")
        if story.get("pending") is not None or story.get("queue"):
            return
        component = context.state.entities.require(actor_id, CONCUBINE_STATE)
        if _advance_rejection_aftermath(
            context, definitions, actor_id, component
        ):
            return
        _maybe_queue_proposal(context, definitions, actor_id, component)

    return handler


def register_concubine_story_effects(
    registry: Any, definitions: GameDefinitions,
) -> None:
    from .story import EffectOutcome

    def proposal(
        context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any],
    ) -> EffectOutcome:
        runtime = dict(pending.get("runtime", {}))
        owner_id = str(runtime.get("owner_id", ""))
        name = str(runtime.get("owner_name", "一位高阶修士"))
        if (
            not context.state.entities.exists(owner_id)
            or not bool(context.state.entities.require(owner_id, LIFE).get("alive"))
            or context.state.entities.require(owner_id, LOCATION).get("world_id")
            != context.state.entities.require(actor_id, LOCATION).get("world_id")
        ):
            return EffectOutcome(
                "owner_absent", "提议者已经离开当前界面，这桩拉拢自然作罢。"
            )
        component = context.state.entities.require(actor_id, CONCUBINE_STATE)
        if bool(effect.payload.get("accept", False)):
            if _status_edge(context.state, actor_id) is not None:
                return EffectOutcome("already_bound", "你已有正主，这桩拉拢无法再继续。")
            _set_concubine_status(context, actor_id, owner_id, forced=False)
            component["rejection_aftermath"] = []
            context.state.entities.put(actor_id, CONCUBINE_STATE, component)
            return EffectOutcome(
                "accepted",
                f"你接受{name}的拉拢，成为其侍妾；此后机缘获取效率降至八成。",
            )
        set_relationship_affinity(
            context.state,
            owner_id,
            actor_id,
            relationship_affinity(context.state, owner_id, actor_id) - 8,
        )
        unit = _action_unit(context.state, actor_id)
        aftermath = [
            dict(row)
            for row in component.get("rejection_aftermath", [])
            if str(row.get("owner_id", "")) != owner_id
        ]
        aftermath.append({
            **runtime,
            "declined_unit": unit,
            "expires_unit": unit + 2,
            "last_checked_unit": unit,
        })
        component["rejection_aftermath"] = aftermath
        context.state.entities.put(actor_id, CONCUBINE_STATE, component)
        return EffectOutcome(
            "refused",
            f"你拒绝成为{name}的侍妾；若其意图报复，只会在接下来的两个行动单位内发作。",
        )

    def revenge(
        context: SimulationContext, actor_id: str, effect: Any, pending: dict[str, Any],
    ) -> EffectOutcome:
        runtime = dict(pending.get("runtime", {}))
        owner_id = str(runtime.get("owner_id", ""))
        name = str(runtime.get("owner_name", "一位高阶修士"))
        if (
            not context.state.entities.exists(owner_id)
            or not bool(context.state.entities.require(owner_id, LIFE).get("alive"))
            or context.state.entities.require(owner_id, LOCATION).get("world_id")
            != context.state.entities.require(actor_id, LOCATION).get("world_id")
        ):
            return EffectOutcome(
                "owner_absent", "追来之人已经离开当前界面，这场逼迫不了了之。"
            )
        rules = dict(definitions.systems.get("relationship", {}))
        relief = float(rules.get("sanction_affinity_relief", 8))
        set_relationship_affinity(
            context.state,
            owner_id,
            actor_id,
            relationship_affinity(context.state, owner_id, actor_id) + relief,
        )
        method = str(effect.payload.get("method", ""))
        if method == "submit":
            _set_concubine_status(context, actor_id, owner_id, forced=True)
            return EffectOutcome(
                "submitted", f"你暂时向{name}低头，被强行带回府中。"
            )
        if method != "resist":
            raise ValueError("未知的逼迫应对方式")
        player_power = max(
            1.0, float(combat_snapshot(context.state, definitions, actor_id)["power"])
        )
        owner_power = max(
            1.0, float(combat_snapshot(context.state, definitions, owner_id)["power"])
        )
        chance = max(
            0.08,
            min(0.75, 0.16 + 0.42 * player_power / (player_power + owner_power)),
        )
        if context.rng.random() < chance:
            component = context.state.entities.require(actor_id, CONCUBINE_STATE)
            component["escape_reputation"] = int(
                component.get("escape_reputation", 0)
            ) + 1
            context.state.entities.put(actor_id, CONCUBINE_STATE, component)
            return EffectOutcome(
                "escaped_revenge",
                f"你拼死突破{name}的围堵，保住自由（成功率 {chance:.0%}）。",
            )
        context.emit(
            "combat.condition.drain.requested",
            source="concubines",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "hp_ratio": 0.22, "mp_ratio": 0.0},
        )
        edge = _set_concubine_status(context, actor_id, owner_id, forced=True)
        metadata = dict(edge.metadata)
        metadata["angered_until_unit"] = _action_unit(context.state, actor_id) + 2
        context.state.relations.replace_metadata(edge.relation_id, metadata)
        return EffectOutcome(
            "captured", f"反抗失败，你负伤后被{name}强行带走。"
        )

    registry.register("concubine_proposal", proposal)
    registry.register("concubine_revenge", revenge)


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = context.state.controlled_entity_id
        if actor_id is None:
            return
        edge = _status_edge(context.state, actor_id)
        if edge is None:
            return
        owner_life = context.state.entities.require(edge.source_id, LIFE)
        owner_location = context.state.entities.require(edge.source_id, LOCATION)
        actor_location = context.state.entities.require(actor_id, LOCATION)
        if not bool(owner_life.get("alive")) or owner_location.get("world_id") != actor_location.get("world_id"):
            context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
            return
        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        if elapsed <= 0:
            return
        metadata = dict(edge.metadata)
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        realm = definitions.realm(str(cultivation["realm_id"]))
        required = round(realm.opportunity_base * (1 + 0.12 * (int(cultivation["layer"]) - 1)))
        angered = int(metadata.get("angered_until_unit", -1)) >= _action_unit(
            context.state, actor_id
        )
        drain = min(
            float(cultivation.get("opportunity", 0.0)),
            required * (0.03 if angered else 0.02) * elapsed,
        )
        cultivation["opportunity"] = max(
            0.0, float(cultivation.get("opportunity", 0.0)) - drain
        )
        metadata["last_drain"] = round(drain, 1)
        metadata["turns"] = int(metadata.get("turns", 0)) + elapsed
        context.state.entities.put(actor_id, CULTIVATION, cultivation)
        context.state.relations.replace_metadata(edge.relation_id, metadata)

    return handler


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    for edge in list(context.state.relations.involving(entity_id, kind="concubine")):
        if edge.source_id == entity_id and edge.target_id == context.state.controlled_entity_id:
            closed = context.state.relations.end(
                edge.relation_id, ended_year=context.state.clock.year
            )
            metadata = dict(closed.metadata)
            metadata["end_reason"] = "owner_died"
            context.state.relations.replace_metadata(closed.relation_id, metadata)


def concubine_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    for entity_id in state.entities.with_component(IDENTITY):
        component = state.entities.get(entity_id, CONCUBINE_STATE)
        if component is None:
            errors.append(f"角色 {entity_id} 缺少侍妾状态组件")
            continue
        bonus = float(component.get("cauldron_breakthrough_bonus", -1))
        if not 0 <= bonus <= 0.02:
            errors.append(f"角色 {entity_id} 的炉鼎突破加成非法")
        for row in component.get("rejection_aftermath", []):
            owner_id = str(row.get("owner_id", ""))
            if state.entities.get(owner_id, IDENTITY) is None:
                errors.append(f"角色 {entity_id} 的拒婚后续引用未知人物")
            declined = int(row.get("declined_unit", -1))
            expires = int(row.get("expires_unit", -1))
            checked = int(row.get("last_checked_unit", -1))
            if declined < 0 or not declined <= checked <= expires:
                errors.append(f"角色 {entity_id} 的拒婚后续行动单位非法")
    return errors


def register_concubine_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(ManageConcubine, _manage_concubine_handler(definitions))
    bus.register(EnterConcubineStatus, _enter_status_handler(definitions))
    bus.register(ManageConcubineStatus, _manage_status_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions))
    bus.event_bus.register("character.died", _on_character_died)


def concubine_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    actor_world = state.entities.require(actor_id, LOCATION)["world_id"]
    unit = _action_unit(state, actor_id)
    rows = []
    for edge in state.relations.find(source_id=actor_id, kind="concubine"):
        other = character_view(state, edge.target_id)
        cultivation = state.entities.require(edge.target_id, CULTIVATION)
        practice = state.entities.require(edge.target_id, PRACTICE)
        realm = definitions.realm(str(cultivation["realm_id"]))
        world_id = state.entities.require(edge.target_id, LOCATION)["world_id"]
        metadata = dict(edge.metadata)
        rows.append({
            **other,
            "world_id": world_id,
            "realm_id": realm.id,
            "realm_name": realm.name,
            "realm_index": definitions.realm_index(realm.id),
            "layer": int(cultivation["layer"]),
            "spirit_root": cultivation["spirit_root"],
            "path": cultivation["path"],
            "main_technique_id": practice.get("main_technique_id"),
            "same_world": world_id == actor_world,
            "metadata": metadata,
            "can_use_cauldron": bool(
                other["alive"] and world_id == actor_world
                and metadata.get("last_cauldron_unit") != unit
            ),
        })
    status_edge = _status_edge(state, actor_id)
    status = None
    if status_edge is not None:
        owner = character_view(state, status_edge.source_id)
        owner_cultivation = state.entities.require(status_edge.source_id, CULTIVATION)
        owner_realm = definitions.realm(str(owner_cultivation["realm_id"]))
        actor_cultivation = state.entities.require(actor_id, CULTIVATION)
        actor_rank = (
            definitions.realm_index(str(actor_cultivation["realm_id"])),
            int(actor_cultivation["layer"]),
        )
        owner_rank = (
            definitions.realm_index(owner_realm.id),
            int(owner_cultivation["layer"]),
        )
        status_metadata = dict(status_edge.metadata)
        status = {
            "relation_id": status_edge.relation_id,
            "owner": {
                **owner,
                "world_id": state.entities.require(
                    status_edge.source_id, LOCATION
                )["world_id"],
                "realm_id": owner_realm.id,
                "realm_name": owner_realm.name,
                "realm_index": definitions.realm_index(owner_realm.id),
                "layer": int(owner_cultivation["layer"]),
                "spirit_root": owner_cultivation["spirit_root"],
                "path": owner_cultivation["path"],
                "main_technique_id": state.entities.require(
                    status_edge.source_id, PRACTICE
                ).get("main_technique_id"),
            },
            **status_metadata,
            "breakthrough_bonus_active": actor_rank < owner_rank,
            "angered": int(status_metadata.get("angered_until_unit", -1)) >= unit,
            "request_available": {
                kind: int(dict(status_metadata.get("last_requests", {})).get(kind, -1)) != unit
                for kind in ("technique", "stones", "equipment")
            },
        }
    component = state.entities.require(actor_id, CONCUBINE_STATE)
    return {
        "concubines": rows,
        "status": status,
        "cauldron_breakthrough_bonus": round(
            float(component["cauldron_breakthrough_bonus"]), 4
        ),
        "opportunity_efficiency_multiplier": 0.8 if status else 1.0,
        "escape_reputation": component["escape_reputation"],
        "future_proposal_multiplier": round(
            max(0.01, 0.20 ** int(component["escape_reputation"])), 4
        ),
        "rejection_aftermath": [
            dict(row) for row in component.get("rejection_aftermath", [])
        ],
    }
