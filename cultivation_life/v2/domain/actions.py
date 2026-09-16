from __future__ import annotations

from typing import Any

from .character import IDENTITY, LIFE
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState
from ..kernel.services import TimeService


ACTION_RUNTIME = "core.action_runtime"


def reconcile_action_runtime(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        if state.entities.get(entity_id, ACTION_RUNTIME) is None:
            state.entities.put(
                entity_id,
                ACTION_RUNTIME,
                {"active": None, "next_sequence": 1, "last_completed": None},
            )


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(
        str(event.payload["entity_id"]),
        ACTION_RUNTIME,
        {"active": None, "next_sequence": 1, "last_completed": None},
    )


def begin_action(
    context: SimulationContext,
    *,
    actor_id: str,
    action: str,
    years: int,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能开始行动")
    if not action.strip() or not source.strip():
        raise ValueError("行动类型和来源不能为空")
    if not isinstance(years, int) or isinstance(years, bool) or years <= 0:
        raise ValueError("行动耗时必须是正整数年")
    runtime = context.state.entities.require(actor_id, ACTION_RUNTIME)
    if runtime.get("active") is not None:
        raise ValueError("当前行动尚未完成")
    sequence = int(runtime.get("next_sequence", 1))
    token = f"action:{sequence}:{actor_id}"
    runtime["next_sequence"] = sequence + 1
    runtime["active"] = {
        "token": token,
        "action": action,
        "source": source,
        "started_year": context.state.clock.year,
        "target_year": context.state.clock.year + years,
        "years": years,
        "metadata": dict(metadata or {}),
    }
    context.state.entities.put(actor_id, ACTION_RUNTIME, runtime)
    context.emit(
        "core.action.started",
        source="core.actions",
        scope=EventScope.entity(actor_id),
        payload={"actor_id": actor_id, **dict(runtime["active"])},
    )
    return token


def complete_action(
    context: SimulationContext,
    *,
    actor_id: str,
    token: str,
    result: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> None:
    runtime = context.state.entities.require(actor_id, ACTION_RUNTIME)
    active = runtime.get("active")
    if not isinstance(active, dict) or active.get("token") != token:
        raise ValueError("行动令牌与当前行动不一致")
    completed = {
        **dict(active),
        "completed_year": context.state.clock.year,
        "result": result,
        "result_metadata": dict(metadata or {}),
    }
    runtime["active"] = None
    runtime["last_completed"] = completed
    context.state.entities.put(actor_id, ACTION_RUNTIME, runtime)
    context.emit(
        "core.action.completed",
        source="core.actions",
        scope=EventScope.entity(actor_id),
        payload={"actor_id": actor_id, **completed},
    )


def interrupt_action(
    context: SimulationContext,
    *,
    actor_id: str,
    reason: str,
) -> None:
    runtime = context.state.entities.require(actor_id, ACTION_RUNTIME)
    active = runtime.get("active")
    if not isinstance(active, dict):
        return
    runtime["active"] = None
    runtime["last_completed"] = {
        **dict(active),
        "completed_year": context.state.clock.year,
        "result": "interrupted",
        "result_metadata": {"reason": reason},
    }
    context.state.entities.put(actor_id, ACTION_RUNTIME, runtime)
    context.emit(
        "core.action.interrupted",
        source="core.actions",
        scope=EventScope.entity(actor_id),
        payload={"actor_id": actor_id, **dict(active), "reason": reason},
    )


def resume_action(context: SimulationContext, actor_id: str) -> None:
    runtime = context.state.entities.require(actor_id, ACTION_RUNTIME)
    active = runtime.get("active")
    if not isinstance(active, dict):
        return
    target_year = int(active["target_year"])
    if target_year < context.state.clock.year:
        raise ValueError("暂停行动的目标时间已经过期")
    TimeService.advance_to(context, target_year, source=str(active["source"]))


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    interrupt_action(
        context,
        actor_id=str(event.payload["entity_id"]),
        reason=str(event.payload.get("reason") or "角色已经死亡"),
    )


def action_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    for entity_id in state.entities.with_component(IDENTITY):
        runtime = state.entities.get(entity_id, ACTION_RUNTIME)
        if runtime is None:
            errors.append(f"角色 {entity_id} 缺少行动运行时")
            continue
        if int(runtime.get("next_sequence", 0)) < 1:
            errors.append(f"角色 {entity_id} 行动序号非法")
        active = runtime.get("active")
        if active is not None:
            if not isinstance(active, dict) or not str(active.get("token", "")):
                errors.append(f"角色 {entity_id} 当前行动格式非法")
            elif int(active.get("target_year", -1)) < state.clock.year:
                errors.append(f"角色 {entity_id} 当前行动已经过期")
            elif not any(
                scheduled.scope.kind == "entity"
                and scheduled.scope.value == entity_id
                and str(
                    scheduled.payload.get(
                        "action_token", scheduled.payload.get("token", "")
                    )
                ) == str(active["token"])
                and scheduled.due_year <= int(active["target_year"])
                for scheduled in state.scheduler.events
            ):
                errors.append(f"角色 {entity_id} 当前行动没有可恢复的调度事件")
    return errors


def action_view(state: WorldState, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    return state.entities.require(actor_id, ACTION_RUNTIME)


def register_action_domain(bus: CommandBus) -> None:
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("character.died", _on_character_died)
