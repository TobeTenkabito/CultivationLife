from __future__ import annotations

import ast
import copy
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

from .model import EventEnvelope, EventScope, WorldState


CommandHandler = Callable[["SimulationContext", object], None]
EventHandler = Callable[["SimulationContext", EventEnvelope], None]
CommandGuard = Callable[[WorldState, object], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def register(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            raise ValueError(f"事件处理器重复注册：{event_type}")
        self._handlers[event_type].append(handler)

    def handlers_for(self, event_type: str) -> tuple[EventHandler, ...]:
        return tuple(self._handlers.get(event_type, ()))


@dataclass(slots=True)
class SimulationContext:
    state: WorldState
    event_bus: EventBus
    emitted_events: list[EventEnvelope] = field(default_factory=list)
    _pending_events: deque[EventEnvelope] = field(default_factory=deque)
    _dispatching: bool = False
    time_halted: bool = False
    time_halt_reason: str | None = None
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.state.seed)
        if self.state.rng_state:
            self._rng.setstate(ast.literal_eval(self.state.rng_state))

    @property
    def rng(self) -> random.Random:
        return self._rng

    def persist_rng(self) -> None:
        self.state.rng_state = repr(self._rng.getstate())

    def halt_time(self, reason: str) -> None:
        self.time_halted = True
        self.time_halt_reason = reason

    def emit(
        self,
        event_type: str,
        *,
        source: str,
        scope: EventScope,
        payload: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        sequence = self.state.next_event_sequence
        self.state.next_event_sequence += 1
        event = EventEnvelope(
            sequence=sequence,
            event_id=f"evt:{sequence:010d}",
            event_type=event_type,
            occurred_at=self.state.clock.year,
            source=source,
            scope=scope,
            payload=copy.deepcopy(payload or {}),
        )
        self.emitted_events.append(event)
        self._pending_events.append(event)
        self._drain_events()
        return event

    def _drain_events(self) -> None:
        if self._dispatching:
            return
        self._dispatching = True
        try:
            while self._pending_events:
                event = self._pending_events.popleft()
                for handler in self.event_bus.handlers_for(event.event_type):
                    handler(self, event)
        finally:
            self._dispatching = False


class CommandBus:
    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus or EventBus()
        self._handlers: dict[type[object], CommandHandler] = {}
        self._guards: list[CommandGuard] = []

    def add_guard(self, guard: CommandGuard) -> None:
        if guard in self._guards:
            raise ValueError("命令守卫重复注册")
        self._guards.append(guard)

    def register(self, command_type: type[object], handler: CommandHandler) -> None:
        if command_type in self._handlers:
            raise ValueError(f"命令处理器重复注册：{command_type.__name__}")
        self._handlers[command_type] = handler

    def execute(self, state: WorldState, command: object) -> list[EventEnvelope]:
        handler = self._handlers.get(type(command))
        if handler is None:
            raise ValueError(f"未注册的游戏命令：{type(command).__name__}")
        for guard in self._guards:
            guard(state, command)
        context = SimulationContext(state=state, event_bus=self.event_bus)
        handler(context, command)
        context.persist_rng()
        return context.emitted_events
