from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY
from .definitions import GameDefinitions
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


PREFERENCES = "presentation.preferences"
NEWS_FEED = "presentation.world_news"

SETTING_DEFAULTS = {
    "combat_popup": True,
    "achievement_popup": True,
    "auto_advance_player_wars": False,
}


def reconcile_presentation_state(state: WorldState) -> None:
    """Backfill components for entities materialized by import adapters.

    Runtime character creation uses the domain event.  Importers are allowed
    to materialize a normalized graph directly, so reconciliation is the one
    explicit boundary that brings those entities to the current module shape.
    """
    for entity_id in state.entities.with_component(IDENTITY):
        preferences = state.entities.get(entity_id, PREFERENCES)
        if preferences is None:
            preferences = {**SETTING_DEFAULTS, "debug_world_news": False}
        else:
            for key, default in SETTING_DEFAULTS.items():
                preferences.setdefault(key, default)
            preferences.setdefault("debug_world_news", False)
        state.entities.put(entity_id, PREFERENCES, preferences)
        if state.entities.get(entity_id, NEWS_FEED) is None:
            state.entities.put(entity_id, NEWS_FEED, {"next_sequence": 1, "entries": []})


@dataclass(frozen=True, slots=True)
class UpdateSetting:
    actor_id: str
    setting: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class SetWorldNewsDebug:
    actor_id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class RecordWorldNews:
    """Internal/publication command used by simulations and integration tests.

    News is simulated and stored regardless of whether its world is currently
    visible.  Visibility is a projection concern controlled by the debug flag.
    """

    actor_id: str
    world_id: str
    title: str
    summary: str
    tags: tuple[str, ...] = ()


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    context.state.entities.put(
        entity_id,
        PREFERENCES,
        {**SETTING_DEFAULTS, "debug_world_news": False},
    )
    context.state.entities.put(entity_id, NEWS_FEED, {"next_sequence": 1, "entries": []})


def _require_controlled(context: SimulationContext, actor_id: str) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能修改当前角色的界面设置")


def _update_setting(context: SimulationContext, command: object) -> None:
    if not isinstance(command, UpdateSetting):
        raise TypeError("命令类型错误")
    _require_controlled(context, command.actor_id)
    if command.setting not in SETTING_DEFAULTS:
        raise ValueError("未知设置项")
    preferences = context.state.entities.require(command.actor_id, PREFERENCES)
    preferences[command.setting] = bool(command.enabled)
    context.state.entities.put(command.actor_id, PREFERENCES, preferences)
    context.emit(
        "presentation.setting.changed",
        source="presentation",
        scope=EventScope("private", command.actor_id),
        payload={"setting": command.setting, "enabled": bool(command.enabled)},
    )


def _set_world_news_debug(context: SimulationContext, command: object) -> None:
    if not isinstance(command, SetWorldNewsDebug):
        raise TypeError("命令类型错误")
    _require_controlled(context, command.actor_id)
    preferences = context.state.entities.require(command.actor_id, PREFERENCES)
    preferences["debug_world_news"] = bool(command.enabled)
    context.state.entities.put(command.actor_id, PREFERENCES, preferences)
    context.emit(
        "presentation.world_news_debug.changed",
        source="presentation",
        scope=EventScope("private", command.actor_id),
        payload={"enabled": bool(command.enabled)},
    )


def _record_world_news(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RecordWorldNews):
            raise TypeError("命令类型错误")
        if not context.state.entities.exists(command.actor_id):
            raise ValueError("消息接收者不存在")
        if command.world_id not in {*definitions.worlds, "global"}:
            raise ValueError("世界消息所属世界无效")
        if not command.title.strip() or not command.summary.strip():
            raise ValueError("世界消息缺少必要字段")
        feed = context.state.entities.require(command.actor_id, NEWS_FEED)
        sequence = int(feed.get("next_sequence", 1))
        entries = [dict(row) for row in feed.get("entries", [])]
        entries.append({
            "id": f"news:{sequence}",
            "year": context.state.clock.year,
            "world_id": command.world_id,
            "title": command.title.strip(),
            "summary": command.summary.strip(),
            "tags": list(dict.fromkeys(map(str, command.tags))),
        })
        # The UI only needs a bounded chronology; simulation facts continue to
        # be represented by the append-only event journal.
        feed["next_sequence"] = sequence + 1
        feed["entries"] = entries[-200:]
        context.state.entities.put(command.actor_id, NEWS_FEED, feed)
        context.emit(
            "presentation.world_news.recorded",
            source="presentation",
            scope=(
                EventScope.global_scope()
                if command.world_id == "global"
                else EventScope("world", command.world_id)
            ),
            payload={"news_id": f"news:{sequence}", "title": command.title.strip()},
        )

    return handler


def presentation_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for entity_id in state.entities.with_component(IDENTITY):
            preferences = state.entities.get(entity_id, PREFERENCES)
            feed = state.entities.get(entity_id, NEWS_FEED)
            if preferences is None or feed is None:
                errors.append(f"角色 {entity_id} 缺少界面组件")
                continue
            for setting in (*SETTING_DEFAULTS, "debug_world_news"):
                if not isinstance(preferences.get(setting), bool):
                    errors.append(f"角色 {entity_id} 的界面设置非法：{setting}")
            seen: set[str] = set()
            for row in feed.get("entries", []):
                news_id = str(row.get("id", ""))
                world_id = str(row.get("world_id", ""))
                if (
                    not news_id or news_id in seen
                    or world_id not in {*definitions.worlds, "global"}
                ):
                    errors.append(f"角色 {entity_id} 的世界消息非法")
                seen.add(news_id)
        return errors

    return validate


def register_presentation_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(UpdateSetting, _update_setting)
    bus.register(SetWorldNewsDebug, _set_world_news_debug)
    bus.register(RecordWorldNews, _record_world_news(definitions))
    bus.event_bus.register("character.created", _on_character_created)


def presentation_view(state: Any, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    preferences = state.entities.require(actor_id, PREFERENCES)
    feed = state.entities.require(actor_id, NEWS_FEED)
    location = state.entities.require(actor_id, LOCATION)
    debug = bool(preferences["debug_world_news"])
    current_world = str(location["world_id"])
    visible = [
        dict(row)
        for row in feed.get("entries", [])
        if debug or str(row.get("world_id")) in {current_world, "global"}
    ]
    return {
        "settings": {key: bool(preferences[key]) for key in SETTING_DEFAULTS},
        "debug_world_news": debug,
        "world_news": list(reversed(visible[-80:])),
    }
