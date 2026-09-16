from __future__ import annotations

from .bus import SimulationContext
from .model import EventScope, WorldState


class InvariantViolation(RuntimeError):
    pass


class TimeService:
    """The only legal V2 entry point for advancing simulation time."""

    @staticmethod
    def advance(context: SimulationContext, years: int, *, source: str) -> None:
        if not isinstance(years, int) or isinstance(years, bool) or years <= 0:
            raise ValueError("耗时必须是正整数年")
        start_year = context.state.clock.year
        target_year = start_year + years
        cursor = start_year
        for scheduled in context.state.scheduler.pop_due_through(target_year):
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
            context.emit(
                scheduled.event_type,
                source=scheduled.source,
                scope=scheduled.scope,
                payload=scheduled.payload,
            )
        if cursor < target_year:
            context.state.clock = context.state.clock.at(target_year)
            context.emit(
                "core.time.advanced",
                source=source,
                scope=EventScope.global_scope(),
                payload={"from_year": cursor, "to_year": target_year},
            )


def validate_world_state(state: WorldState) -> None:
    errors: list[str] = []
    if state.clock.year < 0:
        errors.append("世界时间小于零")
    if state.revision < 0:
        errors.append("存档修订号小于零")
    if state.next_event_sequence < 1:
        errors.append("事件序号非法")
    controlled = state.controlled_entity_id
    if not controlled:
        errors.append("没有受控角色")
    elif not state.entities.exists(controlled):
        errors.append("受控角色实体不存在")
    else:
        for component in ("core.identity", "character.life", "character.activity"):
            if state.entities.get(controlled, component) is None:
                errors.append(f"受控角色缺少组件：{component}")
        life = state.entities.get(controlled, "character.life")
        if life is not None and int(life.get("birth_year", 1)) > state.clock.year:
            errors.append("角色出生时间晚于当前世界时间")
    scheduled_sequences = [event.sequence for event in state.scheduler.events]
    if len(scheduled_sequences) != len(set(scheduled_sequences)):
        errors.append("调度事件序号重复")
    if any(event.due_year <= state.clock.year for event in state.scheduler.events):
        errors.append("存在未结算的过期调度事件")
    if errors:
        raise InvariantViolation("；".join(errors))
