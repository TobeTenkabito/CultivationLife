from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any


V2_FORMAT_ID = "cultivation-life-v2"
V2_SCHEMA_VERSION = 1


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

    def to_dict(self) -> dict[str, Any]:
        return {"next_sequence": self.next_sequence, "entities": copy.deepcopy(self.entities)}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EntityStore:
        return cls(
            entities=copy.deepcopy(dict(value.get("entities", {}))),
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
    scheduler: Scheduler = field(default_factory=Scheduler)
    module_versions: dict[str, int] = field(default_factory=lambda: {"core": 1, "character": 1})
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
            scheduler=Scheduler.from_dict(dict(value["scheduler"])),
            module_versions={str(key): int(version) for key, version in dict(value["module_versions"]).items()},
            next_event_sequence=int(value.get("next_event_sequence", 1)),
        )
