from __future__ import annotations

from .bus import SimulationContext
from collections.abc import Callable

from .model import EventScope, WorldState


class InvariantViolation(RuntimeError):
    pass


InvariantValidator = Callable[[WorldState], list[str]]


class InvariantRegistry:
    def __init__(self) -> None:
        self._validators: dict[str, InvariantValidator] = {}

    def register(self, name: str, validator: InvariantValidator) -> None:
        if name in self._validators:
            raise ValueError(f"不变量检查器重复注册：{name}")
        self._validators[name] = validator

    def validate(self, state: WorldState) -> None:
        errors = validate_kernel_state(state)
        for name, validator in self._validators.items():
            errors.extend(f"{name}: {error}" for error in validator(state))
        if errors:
            raise InvariantViolation("；".join(errors))


class TimeService:
    """The only legal entry point for advancing simulation time."""

    @staticmethod
    def advance(context: SimulationContext, years: int, *, source: str) -> None:
        if not isinstance(years, int) or isinstance(years, bool) or years <= 0:
            raise ValueError("耗时必须是正整数年")
        TimeService.advance_to(
            context, context.state.clock.year + years, source=source,
        )

    @staticmethod
    def advance_to(context: SimulationContext, target_year: int, *, source: str) -> None:
        if not isinstance(target_year, int) or isinstance(target_year, bool):
            raise ValueError("目标年份必须是整数")
        start_year = context.state.clock.year
        if target_year < start_year:
            raise ValueError("模拟时钟不能倒退")
        cursor = start_year
        while not context.time_halted:
            scheduled = context.state.scheduler.next_due_through(target_year)
            if scheduled is None:
                break
            if scheduled.due_year < cursor:
                raise InvariantViolation("调度器中存在已经过期的事件")
            if scheduled.due_year > cursor:
                context.state.clock = context.state.clock.at(scheduled.due_year)
                context.emit(
                    "core.time.advanced",
                    source=source,
                    scope=EventScope.global_scope(),
                    payload={"from_year": cursor, "to_year": scheduled.due_year},
                )
                cursor = scheduled.due_year
                if context.time_halted:
                    break
            scheduled = context.state.scheduler.pop(scheduled.sequence)
            context.emit(
                scheduled.event_type,
                source=scheduled.source,
                scope=scheduled.scope,
                payload=scheduled.payload,
            )
        if not context.time_halted and cursor < target_year:
            context.state.clock = context.state.clock.at(target_year)
            context.emit(
                "core.time.advanced",
                source=source,
                scope=EventScope.global_scope(),
                payload={"from_year": cursor, "to_year": target_year},
            )


def validate_kernel_state(state: WorldState) -> list[str]:
    errors: list[str] = []
    if state.clock.year < 0:
        errors.append("世界时间小于零")
    if state.revision < 0:
        errors.append("存档修订号小于零")
    if state.next_event_sequence < 1:
        errors.append("事件序号非法")
    controlled = state.controlled_entity_id
    if controlled and not state.entities.exists(controlled):
        errors.append("受控角色实体不存在")
    scheduled_sequences = [event.sequence for event in state.scheduler.events]
    if len(scheduled_sequences) != len(set(scheduled_sequences)):
        errors.append("调度事件序号重复")
    # An interaction may halt time immediately after the clock reaches a year
    # but before all work scheduled for that year has run.  Such events are
    # resumable; only events strictly in the past are corrupt.
    if any(event.due_year < state.clock.year for event in state.scheduler.events):
        errors.append("存在未结算的过期调度事件")
    relation_ids = list(state.relations.edges)
    if len(relation_ids) != len(set(relation_ids)):
        errors.append("关系ID重复")
    for relation_id, edge in state.relations.edges.items():
        if relation_id != edge.relation_id:
            errors.append(f"关系索引不一致：{relation_id}")
        if not state.entities.exists(edge.source_id) or not state.entities.exists(edge.target_id):
            errors.append(f"关系引用不存在的实体：{relation_id}")
        if edge.ended_year is not None and edge.ended_year < edge.created_year:
            errors.append(f"关系时间非法：{relation_id}")
    return errors


def validate_world_state(state: WorldState) -> None:
    """Backward-compatible kernel-only validation entry point.

    Application code uses ``InvariantRegistry`` so each domain owns its own
    rules.  This function remains useful for storage and low-level tests.
    """
    errors = validate_kernel_state(state)
    if errors:
        raise InvariantViolation("；".join(errors))
