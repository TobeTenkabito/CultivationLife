from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any


V2_FORMAT_ID = "cultivation-life-v2"
V2_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class GameClock:
    """Canonical simulation clock.

    One tick is one in-game year for the first V2 milestone.  Finer-grained
    units can be introduced behind this type without allowing domains to edit
    character ages directly.
    """

    year: int = 0

    def at(self, year: int) -> GameClock:
        if year < self.year:
            raise ValueError("模拟时钟不能倒退")
        return GameClock(year=year)


@dataclass(frozen=True, slots=True)
class EventScope:
    kind: str
    value: str | None = None

    def __post_init__(self) -> None:
        allowed = {"global", "entity", "world", "faction", "private"}
        if self.kind not in allowed:
            raise ValueError(f"未知事件作用域：{self.kind}")
        if self.kind == "global" and self.value is not None:
            raise ValueError("全局事件不能携带作用域ID")
        if self.kind != "global" and not self.value:
            raise ValueError(f"{self.kind}事件必须携带作用域ID")

    @classmethod
    def global_scope(cls) -> EventScope:
        return cls("global")

    @classmethod
    def entity(cls, entity_id: str) -> EventScope:
        return cls("entity", entity_id)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EventScope:
        return cls(kind=str(value["kind"]), value=value.get("value"))


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    sequence: int
    event_id: str
    event_type: str
    occurred_at: int
    source: str
    scope: EventScope
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "source": self.source,
            "scope": self.scope.to_dict(),
            "payload": copy.deepcopy(self.payload),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EventEnvelope:
        return cls(
            sequence=int(value["sequence"]),
            event_id=str(value["event_id"]),
            event_type=str(value["event_type"]),
            occurred_at=int(value["occurred_at"]),
            source=str(value["source"]),
            scope=EventScope.from_dict(dict(value["scope"])),
            payload=copy.deepcopy(dict(value.get("payload", {}))),
        )


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    due_year: int
    sequence: int
    event_type: str
    source: str
    scope: EventScope
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "due_year": self.due_year,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "source": self.source,
            "scope": self.scope.to_dict(),
            "payload": copy.deepcopy(self.payload),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ScheduledEvent:
        return cls(
            due_year=int(value["due_year"]),
            sequence=int(value["sequence"]),
            event_type=str(value["event_type"]),
            source=str(value["source"]),
            scope=EventScope.from_dict(dict(value["scope"])),
            payload=copy.deepcopy(dict(value.get("payload", {}))),
        )


@dataclass(slots=True)
class Scheduler:
    events: list[ScheduledEvent] = field(default_factory=list)
    next_sequence: int = 1

    def schedule(
        self,
        *,
        due_year: int,
        event_type: str,
        source: str,
        scope: EventScope,
        payload: dict[str, Any] | None = None,
    ) -> ScheduledEvent:
        event = ScheduledEvent(
            due_year=due_year,
            sequence=self.next_sequence,
            event_type=event_type,
            source=source,
            scope=scope,
            payload=copy.deepcopy(payload or {}),
        )
        self.next_sequence += 1
        self.events.append(event)
        return event

    def pop_due_through(self, year: int) -> list[ScheduledEvent]:
        due = sorted(
            (event for event in self.events if event.due_year <= year),
            key=lambda event: (event.due_year, event.sequence),
        )
        due_sequences = {event.sequence for event in due}
        self.events = [event for event in self.events if event.sequence not in due_sequences]
        return due

    def next_due_through(self, year: int) -> ScheduledEvent | None:
        eligible = [event for event in self.events if event.due_year <= year]
        return min(eligible, key=lambda event: (event.due_year, event.sequence), default=None)

    def pop(self, sequence: int) -> ScheduledEvent:
        for index, event in enumerate(self.events):
            if event.sequence == sequence:
                return self.events.pop(index)
        raise KeyError(f"调度事件不存在：{sequence}")

    def cancel(self, predicate: Callable[[ScheduledEvent], bool]) -> tuple[ScheduledEvent, ...]:
        cancelled = tuple(event for event in self.events if predicate(event))
        cancelled_sequences = {event.sequence for event in cancelled}
        self.events = [event for event in self.events if event.sequence not in cancelled_sequences]
        return cancelled

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_sequence": self.next_sequence,
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Scheduler:
        return cls(
            events=[ScheduledEvent.from_dict(dict(row)) for row in value.get("events", [])],
            next_sequence=int(value.get("next_sequence", 1)),
        )


@dataclass(slots=True)
class EntityStore:
    """Normalized entity/component storage.

    Component payloads are copied on both read and write.  A domain therefore
    cannot retain a mutable alias and silently change state outside a command.
    """

    entities: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    next_sequence: int = 1

    def create(self, namespace: str) -> str:
        if not namespace or not namespace.replace("_", "").isalnum():
            raise ValueError("非法实体命名空间")
        entity_id = f"{namespace}:{self.next_sequence}"
        self.next_sequence += 1
        self.entities[entity_id] = {}
        return entity_id

    def exists(self, entity_id: str) -> bool:
        return entity_id in self.entities

    def put(self, entity_id: str, component: str, payload: dict[str, Any]) -> None:
        if entity_id not in self.entities:
            raise KeyError(f"实体不存在：{entity_id}")
        if not component:
            raise ValueError("组件名不能为空")
        self.entities[entity_id][component] = copy.deepcopy(payload)

    def get(self, entity_id: str, component: str) -> dict[str, Any] | None:
        payload = self.entities.get(entity_id, {}).get(component)
        return copy.deepcopy(payload) if payload is not None else None

    def require(self, entity_id: str, component: str) -> dict[str, Any]:
        payload = self.get(entity_id, component)
        if payload is None:
            raise KeyError(f"实体 {entity_id} 缺少组件 {component}")
        return payload

    def with_component(self, component: str) -> tuple[str, ...]:
        return tuple(
            entity_id for entity_id, components in self.entities.items()
            if component in components
        )

    def to_dict(self) -> dict[str, Any]:
        return {"next_sequence": self.next_sequence, "entities": copy.deepcopy(self.entities)}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EntityStore:
        return cls(
            entities=copy.deepcopy(dict(value.get("entities", {}))),
            next_sequence=int(value.get("next_sequence", 1)),
        )


@dataclass(frozen=True, slots=True)
class RelationEdge:
    relation_id: str
    source_id: str
    target_id: str
    kind: str
    created_year: int
    metadata: dict[str, Any]
    ended_year: int | None = None

    @property
    def active(self) -> bool:
        return self.ended_year is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "kind": self.kind,
            "created_year": self.created_year,
            "metadata": copy.deepcopy(self.metadata),
            "ended_year": self.ended_year,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RelationEdge:
        ended = value.get("ended_year")
        return cls(
            relation_id=str(value["relation_id"]),
            source_id=str(value["source_id"]),
            target_id=str(value["target_id"]),
            kind=str(value["kind"]),
            created_year=int(value["created_year"]),
            metadata=copy.deepcopy(dict(value.get("metadata", {}))),
            ended_year=int(ended) if ended is not None else None,
        )


@dataclass(slots=True)
class RelationStore:
    """Typed edges between canonical entities; never embeds entity snapshots."""

    edges: dict[str, RelationEdge] = field(default_factory=dict)
    next_sequence: int = 1

    def add(
        self,
        *,
        source_id: str,
        target_id: str,
        kind: str,
        created_year: int,
        metadata: dict[str, Any] | None = None,
    ) -> RelationEdge:
        if source_id == target_id:
            raise ValueError("实体不能与自身建立关系")
        if not kind:
            raise ValueError("关系类型不能为空")
        relation_id = f"relation:{self.next_sequence}"
        self.next_sequence += 1
        edge = RelationEdge(
            relation_id=relation_id,
            source_id=source_id,
            target_id=target_id,
            kind=kind,
            created_year=created_year,
            metadata=copy.deepcopy(metadata or {}),
        )
        self.edges[relation_id] = edge
        return edge

    def get(self, relation_id: str) -> RelationEdge | None:
        edge = self.edges.get(relation_id)
        return RelationEdge.from_dict(edge.to_dict()) if edge is not None else None

    def require(self, relation_id: str) -> RelationEdge:
        edge = self.get(relation_id)
        if edge is None:
            raise KeyError(f"关系不存在：{relation_id}")
        return edge

    def find(
        self,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        kind: str | None = None,
        active_only: bool = True,
    ) -> tuple[RelationEdge, ...]:
        result = []
        for edge in self.edges.values():
            if active_only and not edge.active:
                continue
            if source_id is not None and edge.source_id != source_id:
                continue
            if target_id is not None and edge.target_id != target_id:
                continue
            if kind is not None and edge.kind != kind:
                continue
            result.append(RelationEdge.from_dict(edge.to_dict()))
        return tuple(sorted(result, key=lambda edge: int(edge.relation_id.rsplit(":", 1)[-1])))

    def involving(
        self, entity_id: str, *, kind: str | None = None, active_only: bool = True,
    ) -> tuple[RelationEdge, ...]:
        return tuple(
            edge for edge in self.find(kind=kind, active_only=active_only)
            if entity_id in {edge.source_id, edge.target_id}
        )

    def replace_metadata(self, relation_id: str, metadata: dict[str, Any]) -> RelationEdge:
        edge = self.require(relation_id)
        updated = RelationEdge(
            relation_id=edge.relation_id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            kind=edge.kind,
            created_year=edge.created_year,
            metadata=copy.deepcopy(metadata),
            ended_year=edge.ended_year,
        )
        self.edges[relation_id] = updated
        return updated

    def end(self, relation_id: str, *, ended_year: int) -> RelationEdge:
        edge = self.require(relation_id)
        if not edge.active:
            raise ValueError("关系已经结束")
        if ended_year < edge.created_year:
            raise ValueError("关系结束时间不能早于建立时间")
        updated = RelationEdge(
            relation_id=edge.relation_id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            kind=edge.kind,
            created_year=edge.created_year,
            metadata=edge.metadata,
            ended_year=ended_year,
        )
        self.edges[relation_id] = updated
        return updated

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_sequence": self.next_sequence,
            "edges": {relation_id: edge.to_dict() for relation_id, edge in self.edges.items()},
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RelationStore:
        return cls(
            edges={
                str(relation_id): RelationEdge.from_dict(dict(edge))
                for relation_id, edge in dict(value.get("edges", {})).items()
            },
            next_sequence=int(value.get("next_sequence", 1)),
        )


@dataclass(slots=True)
class WorldState:
    game_id: str
    seed: int
    created_at: str
    updated_at: str
    revision: int = 0
    schema_version: int = V2_SCHEMA_VERSION
    clock: GameClock = field(default_factory=GameClock)
    rng_state: str = ""
    controlled_entity_id: str | None = None
    entities: EntityStore = field(default_factory=EntityStore)
    relations: RelationStore = field(default_factory=RelationStore)
    scheduler: Scheduler = field(default_factory=Scheduler)
    module_versions: dict[str, int] = field(default_factory=lambda: {
        "core": 2,
        "character": 2,
        "cultivation": 1,
        "world": 1,
        "relations": 1,
        "factions": 1,
    })
    next_event_sequence: int = 1

    @classmethod
    def new(cls, *, seed: int, created_at: str, game_id: str | None = None) -> WorldState:
        return cls(
            game_id=game_id or uuid.uuid4().hex,
            seed=seed,
            created_at=created_at,
            updated_at=created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": V2_FORMAT_ID,
            "schema_version": self.schema_version,
            "game_id": self.game_id,
            "seed": self.seed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
            "clock": {"year": self.clock.year},
            "rng_state": self.rng_state,
            "controlled_entity_id": self.controlled_entity_id,
            "entities": self.entities.to_dict(),
            "relations": self.relations.to_dict(),
            "scheduler": self.scheduler.to_dict(),
            "module_versions": dict(self.module_versions),
            "next_event_sequence": self.next_event_sequence,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> WorldState:
        if value.get("format") != V2_FORMAT_ID:
            raise ValueError("不是V2存档")
        if int(value.get("schema_version", 0)) != V2_SCHEMA_VERSION:
            raise ValueError("不支持的V2存档版本")
        return cls(
            game_id=str(value["game_id"]),
            seed=int(value["seed"]),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            revision=int(value.get("revision", 0)),
            schema_version=int(value["schema_version"]),
            clock=GameClock(year=int(dict(value["clock"])["year"])),
            rng_state=str(value.get("rng_state", "")),
            controlled_entity_id=value.get("controlled_entity_id"),
            entities=EntityStore.from_dict(dict(value["entities"])),
            relations=RelationStore.from_dict(dict(value.get("relations", {}))),
            scheduler=Scheduler.from_dict(dict(value["scheduler"])),
            module_versions={str(key): int(version) for key, version in dict(value["module_versions"]).items()},
            next_event_sequence=int(value.get("next_event_sequence", 1)),
        )
