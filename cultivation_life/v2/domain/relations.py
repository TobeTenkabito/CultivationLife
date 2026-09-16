from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE, character_view
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventScope, RelationEdge, WorldState


SOCIAL_KINDS = {"friend", "dao_companion", "master_disciple", "concubine"}
SYMMETRIC_KINDS = {"friend", "dao_companion"}


@dataclass(frozen=True, slots=True)
class FormRelationship:
    source_id: str
    target_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class EndRelationship:
    actor_id: str
    relation_id: str
    reason: str = "ended"


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


def _form_relationship(context: SimulationContext, command: object) -> None:
    if not isinstance(command, FormRelationship):
        raise TypeError("命令类型错误")
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
    edge = context.state.relations.add(
        source_id=source_id,
        target_id=target_id,
        kind=command.kind,
        created_year=context.state.clock.year,
    )
    context.emit(
        "relationship.formed",
        source="relations",
        scope=EventScope.entity(command.source_id),
        payload=edge.to_dict(),
    )


def _end_relationship(context: SimulationContext, command: object) -> None:
    if not isinstance(command, EndRelationship):
        raise TypeError("命令类型错误")
    edge = context.state.relations.require(command.relation_id)
    if edge.kind not in SOCIAL_KINDS:
        raise ValueError("该关系不归人际关系领域管理")
    if command.actor_id not in {edge.source_id, edge.target_id}:
        raise ValueError("只能结束与自己有关的关系")
    ended = context.state.relations.end(command.relation_id, ended_year=context.state.clock.year)
    metadata = dict(ended.metadata)
    metadata["end_reason"] = command.reason
    ended = context.state.relations.replace_metadata(command.relation_id, metadata)
    context.emit(
        "relationship.ended",
        source="relations",
        scope=EventScope.entity(command.actor_id),
        payload=ended.to_dict(),
    )


def relationship_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    active = [edge for edge in state.relations.find() if edge.kind in SOCIAL_KINDS]
    seen_pair: set[tuple[str, str]] = set()
    companion_counts: dict[str, int] = {}
    disciple_counts: dict[str, int] = {}
    concubine_counts: dict[str, int] = {}
    for edge in active:
        if edge.kind not in SOCIAL_KINDS:
            errors.append(f"未知人物关系：{edge.relation_id}")
            continue
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
    return errors


def register_relationship_domain(bus: CommandBus) -> None:
    bus.register(FormRelationship, _form_relationship)
    bus.register(EndRelationship, _end_relationship)


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
        rows.append({
            "relation_id": edge.relation_id,
            "kind": edge.kind,
            "direction": "source" if edge.source_id == actor_id else "target",
            "other": {
                "id": other["id"],
                "name": other["name"],
                "age": other["age"],
                "alive": other["alive"],
                "death_reason": other["death_reason"],
            },
            "created_year": edge.created_year,
            "metadata": edge.metadata,
        })
    return rows
