from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope
from ..kernel.services import TimeService


IDENTITY = "core.identity"
LIFE = "character.life"
ACTIVITY = "character.activity"
TIMED_ACTION_COMPLETED = "character.timed_action.completed"


@dataclass(frozen=True, slots=True)
class BootstrapGame:
    name: str
    starting_age: int = 16


@dataclass(frozen=True, slots=True)
class PerformTimedAction:
    actor_id: str
    action: str
    years: int = 1


def _bootstrap_game(context: SimulationContext, command: object) -> None:
    if not isinstance(command, BootstrapGame):
        raise TypeError("命令类型错误")
    name = command.name.strip()
    if not name or len(name) > 40:
        raise ValueError("角色名必须为1至40个字符")
    if command.starting_age < 0 or command.starting_age > 1000:
        raise ValueError("初始年龄非法")
    if context.state.controlled_entity_id is not None:
        raise ValueError("游戏已经初始化")
    actor_id = context.state.entities.create("character")
    context.state.entities.put(actor_id, IDENTITY, {"name": name})
    context.state.entities.put(
        actor_id,
        LIFE,
        {"birth_year": context.state.clock.year - command.starting_age, "alive": True, "death_reason": None},
    )
    context.state.entities.put(
        actor_id,
        ACTIVITY,
        {"cultivation_progress": 0, "rest_years": 0, "actions_completed": 0},
    )
    context.state.controlled_entity_id = actor_id
    context.emit(
        "core.game.created",
        source="core",
        scope=EventScope.global_scope(),
        payload={"game_id": context.state.game_id},
    )
    context.emit(
        "character.created",
        source="character",
        scope=EventScope.entity(actor_id),
        payload={"entity_id": actor_id, "name": name, "starting_age": command.starting_age},
    )


def _perform_timed_action(context: SimulationContext, command: object) -> None:
    if not isinstance(command, PerformTimedAction):
        raise TypeError("命令类型错误")
    if command.actor_id != context.state.controlled_entity_id:
        raise ValueError("只能控制当前角色")
    life = context.state.entities.require(command.actor_id, LIFE)
    if not bool(life.get("alive")):
        raise ValueError("角色已经死亡")
    if command.action not in {"cultivate", "rest"}:
        raise ValueError("未知的V2耗时行动")
    if not isinstance(command.years, int) or isinstance(command.years, bool) or not 1 <= command.years <= 100:
        raise ValueError("单次行动必须耗时1至100年")

    gain = 0
    if command.action == "cultivate":
        gain = sum(context.rng.randint(1, 3) for _ in range(command.years))
    target_year = context.state.clock.year + command.years
    context.state.scheduler.schedule(
        due_year=target_year,
        event_type=TIMED_ACTION_COMPLETED,
        source="character",
        scope=EventScope.entity(command.actor_id),
        payload={
            "actor_id": command.actor_id,
            "action": command.action,
            "years": command.years,
            "cultivation_gain": gain,
        },
    )
    TimeService.advance(context, command.years, source=f"character.action.{command.action}")


def _apply_timed_action(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    activity = context.state.entities.require(actor_id, ACTIVITY)
    action = str(event.payload["action"])
    years = int(event.payload["years"])
    if action == "cultivate":
        activity["cultivation_progress"] = int(activity["cultivation_progress"]) + int(
            event.payload["cultivation_gain"]
        )
    elif action == "rest":
        activity["rest_years"] = int(activity["rest_years"]) + years
    else:
        raise ValueError("事件包含未知行动")
    activity["actions_completed"] = int(activity["actions_completed"]) + 1
    context.state.entities.put(actor_id, ACTIVITY, activity)


def register_character_domain(bus: CommandBus) -> None:
    bus.register(BootstrapGame, _bootstrap_game)
    bus.register(PerformTimedAction, _perform_timed_action)
    bus.event_bus.register(TIMED_ACTION_COMPLETED, _apply_timed_action)


def character_view(state: Any) -> dict[str, Any]:
    actor_id = state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    identity = state.entities.require(actor_id, IDENTITY)
    life = state.entities.require(actor_id, LIFE)
    activity = state.entities.require(actor_id, ACTIVITY)
    return {
        "id": actor_id,
        "name": str(identity["name"]),
        "age": state.clock.year - int(life["birth_year"]),
        "alive": bool(life["alive"]),
        "death_reason": life.get("death_reason"),
        "activity": activity,
    }
