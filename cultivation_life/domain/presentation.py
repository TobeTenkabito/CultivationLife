from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .character import IDENTITY
from .cultivation import CULTIVATION
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
    allow_during_interaction: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class SetWorldNewsDebug:
    actor_id: str
    enabled: bool
    allow_during_interaction: ClassVar[bool] = True


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


def _append_news(
    context: SimulationContext,
    *,
    world_id: str,
    title: str,
    summary: str,
    tags: tuple[str, ...] = (),
) -> None:
    """Project a simulation fact into the controlled character's chronology."""
    actor_id = context.state.controlled_entity_id
    if actor_id is None or not title.strip() or not summary.strip():
        return
    row = {
        "year": context.state.clock.year,
        "world_id": world_id,
        "title": title.strip(),
        "summary": summary.strip(),
        "tags": list(dict.fromkeys(map(str, tags))),
    }
    runtime = context.state.entities.get(actor_id, "core.action_runtime") or {}
    if isinstance(runtime.get("active"), dict):
        context.transient.setdefault("presentation.news", []).append(row)
        return
    _commit_news_rows(context, actor_id, [row])


def _commit_news_rows(
    context: SimulationContext, actor_id: str, rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    feed = context.state.entities.get(actor_id, NEWS_FEED)
    if feed is None:
        return
    sequence = int(feed.get("next_sequence", 1))
    entries = list(feed.get("entries", []))
    for raw in rows:
        entries.append({"id": f"news:{sequence}", **dict(raw)})
        sequence += 1
    feed["next_sequence"] = sequence
    feed["entries"] = entries[-200:]
    context.state.entities.put(actor_id, NEWS_FEED, feed)


def _flush_news_buffer(context: SimulationContext, event: EventEnvelope) -> None:
    del event
    actor_id = context.state.controlled_entity_id
    if actor_id is None:
        return
    rows = list(context.transient.pop("presentation.news", []))
    _commit_news_rows(context, actor_id, rows)


def _entity_name(context: SimulationContext, entity_id: str) -> str:
    identity = context.state.entities.get(entity_id, IDENTITY) or {}
    return str(identity.get("name") or "无名修士")


def _entity_world(context: SimulationContext, entity_id: str) -> str:
    location = context.state.entities.get(entity_id, LOCATION) or {}
    return str(location.get("world_id") or "global")


def _scope_world(context: SimulationContext, event: EventEnvelope) -> str:
    if event.scope.kind == "world" and event.scope.value:
        return str(event.scope.value)
    if event.scope.kind == "entity" and event.scope.value:
        return _entity_world(context, str(event.scope.value))
    if event.scope.kind == "faction" and event.scope.value:
        profile = (
            context.state.entities.get(str(event.scope.value), "faction.profile")
            or context.state.entities.get(str(event.scope.value), "family.profile")
            or {}
        )
        return str(profile.get("world_id") or "global")
    return "global"


def _realm_name(
    context: SimulationContext, definitions: GameDefinitions, entity_id: str
) -> str:
    cultivation = context.state.entities.get(entity_id, CULTIVATION) or {}
    realm_id = str(cultivation.get("realm_id", "mortal"))
    realm = definitions.realm(realm_id)
    layer = int(cultivation.get("layer", 1))
    if realm.layers == 1 or realm.id == "mortal":
        return realm.name
    if realm.id == "qi":
        return f"{realm.name}{layer}层"
    return f"{realm.name}{'初期' if layer <= 3 else '中期' if layer <= 6 else '后期'}"


def _realm_tuple_name(
    definitions: GameDefinitions, realm_and_layer: object
) -> str:
    """Format the realm at the instant a batched breakthrough happened.

    A long action may contain several breakthroughs for the same cultivator.
    Reading the entity's final cultivation component would label every row as
    the last realm reached, losing the chronology that V1 exposed.
    """
    if not isinstance(realm_and_layer, (list, tuple)) or len(realm_and_layer) != 2:
        return "未知境界"
    realm_id, raw_layer = realm_and_layer
    realm = definitions.realm(str(realm_id))
    layer = int(raw_layer)
    if realm.layers == 1 or realm.id == "mortal":
        return realm.name
    if realm.id == "qi":
        return f"{realm.name}{layer}层"
    return f"{realm.name}{'初期' if layer <= 3 else '中期' if layer <= 6 else '后期'}"


def _project_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload.get("entity_id", ""))
    if not entity_id or entity_id == context.state.controlled_entity_id:
        return
    name = _entity_name(context, entity_id)
    reason = str(event.payload.get("reason") or "不幸陨落")
    title = "天下讣闻"
    tags = ["system", "npc", "death"]
    faction = context.state.relations.find(
        source_id=entity_id, kind="faction_membership", active_only=False
    )
    family = context.state.relations.find(
        source_id=entity_id, kind="family_membership", active_only=False
    )
    social = [
        edge for edge in context.state.relations.involving(
            str(context.state.controlled_entity_id), active_only=False
        )
        if entity_id in {edge.source_id, edge.target_id}
    ]
    if family:
        title = "家族讣告"
        tags.append("family")
    elif faction:
        title = "宗门讣告"
        tags.append("faction")
    elif social:
        title = "故人陨落"
        tags.append("relationship")
    _append_news(
        context,
        world_id=_entity_world(context, entity_id),
        title=title,
        summary=f"{name}{reason if reason.startswith(('因', '于', '遭')) else '因' + reason}。",
        tags=tuple(tags),
    )


def _project_simulation_event(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        payload = event.payload
        event_type = event.event_type
        if event_type == "npc.breakthrough.batch":
            for raw in payload.get("entries", []):
                row = dict(raw)
                character_id = str(row.get("character_id", ""))
                _append_news(
                    context,
                    world_id=str(row.get("world_id") or _entity_world(
                        context, character_id
                    )),
                    title="修士破境",
                    summary=(
                        f"{_entity_name(context, character_id)}突破至"
                        f"{_realm_tuple_name(definitions, row.get('after'))}。"
                    ),
                    tags=("system", "npc", "breakthrough"),
                )
            return
        world_id = str(payload.get("world_id") or _scope_world(context, event))
        character_id = str(payload.get("character_id", ""))
        name = _entity_name(context, character_id) if character_id else ""
        title = ""
        summary = ""
        tags: tuple[str, ...] = ("system",)
        if event_type in {
            "npc.breakthrough", "faction.member.breakthrough",
            "family.member.breakthrough",
        }:
            # The canonical lifecycle also emits compatibility events for the
            # faction and family domains.  Project only its generic fact.
            if event_type != "npc.breakthrough" and event.source == "npc_lifecycle":
                return
            title = "修士破境"
            summary = f"{name}突破至{_realm_name(context, definitions, character_id)}。"
            tags = ("system", "npc", "breakthrough")
        elif event_type == "npc.departed":
            destination = str(payload.get("destination_world_id", ""))
            destination_name = definitions.worlds[destination].name
            world_id = str(payload.get("origin_world_id") or world_id)
            title = "飞升离界"
            summary = f"{name}飞升{destination_name}；自此在本界再无踪迹。"
            tags = ("system", "npc", "ascension")
        elif event_type == "npc.tribulation.resolved":
            survived = bool(payload.get("survived"))
            title = "天劫异动"
            summary = (
                f"{name}渡过第{int(payload.get('count', 1))}次大天劫。"
                if survived else
                f"{name}渡第{int(payload.get('count', 1))}次大天劫失败，灰飞烟灭。"
            )
            tags = ("system", "npc", "tribulation")
        elif event_type == "family.child.cultivation_started":
            child_id = str(payload.get("child_id", ""))
            title = "血脉问道"
            summary = f"后代{_entity_name(context, child_id)}正式引气入体，踏入仙途。"
            world_id = _entity_world(context, child_id)
            tags = ("system", "family", "offspring")
        elif event_type in {"family.member.recruited", "faction.member.recruited"}:
            title = "新秀入门"
            summary = f"{name or _entity_name(context, str(payload.get('source_id', '')))}加入了新的传承。"
            tags = ("system", "recruitment")
        elif event_type == "family.extinct":
            family = context.state.entities.get(
                str(payload.get("family_id", "")), "family.profile"
            ) or {}
            title = "家族断绝"
            summary = f"{family.get('name', '一支修仙家族')}最后一名在册修士陨落，传承断绝。"
            tags = ("system", "family", "extinction")
        elif event_type == "faction.dissolved":
            profile = context.state.entities.get(
                str(payload.get("faction_id", "")), "faction.profile"
            ) or {}
            title = "山门解散"
            summary = f"{profile.get('name', '一方宗门')}因{payload.get('reason', '变故')}而解散。"
            tags = ("system", "faction", "extinction")
        elif event_type == "faction.npc_founded":
            profile = context.state.entities.get(
                str(payload.get("faction_id", "")), "faction.profile"
            ) or {}
            founder = _entity_name(
                context, str(payload.get("founder_id", ""))
            )
            title = "新势力崛起"
            summary = (
                f"{founder}建立了{profile.get('name', '新势力')}，"
                f"一座新的"
                f"{'修仙家族' if payload.get('kind') == 'family' else '宗门'}"
                "进入天下势力谱。"
            )
            tags = ("system", "faction", "founding", "npc")
        elif event_type == "npc.notorious.killing":
            villain = _entity_name(
                context, str(payload.get("villain_id", ""))
            )
            victim = _entity_name(
                context, str(payload.get("victim_id", ""))
            )
            title = "凶名远播"
            summary = f"臭名昭著的{villain}又造血案，{victim}遭其截杀。"
            tags = ("system", "npc", "notorious", "death")
        elif event_type == "war.declared":
            title = "战端开启"
            summary = "两方势力正式宣战，烽火已经燃起。"
            tags = ("system", "war", "diplomacy")
        elif event_type == "war.peace.concluded":
            title = "战争落幕"
            summary = f"持续的战争以“{payload.get('term', '议和')}”告终。"
            tags = ("system", "war", "peace")
        elif event_type == "governance.diplomacy.voted" and bool(payload.get("passed")):
            relation = dict(payload.get("relation", {}))
            title = "外交异动"
            summary = f"两方势力关系转为{relation.get('status', '中立')}。"
            tags = ("system", "diplomacy")
        elif event_type == "governance.diplomacy.changed":
            relation = dict(payload.get("relation", {}))
            title = "外交异动"
            summary = f"两方势力关系转为{relation.get('status', '中立')}。"
            tags = ("system", "diplomacy")
        elif event_type == "npc.duel.resolved":
            winner = _entity_name(context, str(payload.get("winner_id", "")))
            loser = _entity_name(context, str(payload.get("loser_id", "")))
            title = "修士斗法"
            summary = (
                f"{winner}在斗法中击杀{loser}。"
                if bool(payload.get("lethal")) else
                f"{winner}在斗法中击败{loser}，双方各自退去。"
            )
            tags = ("system", "npc", "duel")
        elif event_type == "dlc.monster.adaptation.unlocked":
            title = "生命适应"
            summary = f"{name or '一名妖修'}在漫长栖居中获得了新的环境适应。"
            tags = ("system", "monster", "adaptation")
        else:
            return
        _append_news(
            context, world_id=world_id, title=title, summary=summary, tags=tags
        )

    return handler


def _project_era_summary(context: SimulationContext, event: EventEnvelope) -> None:
    years = int(event.payload.get("years", 0))
    if years < 5:
        return
    actor_id = str(event.payload.get("actor_id", ""))
    feed = context.state.entities.get(actor_id, NEWS_FEED)
    if feed is None:
        return
    started = int(event.payload.get("started_year", context.state.clock.year - years))
    rows = [
        row for row in feed.get("entries", [])
        if started < int(row.get("year", -1)) <= context.state.clock.year
        and "era_summary" not in row.get("tags", [])
    ]
    distinct = list(dict.fromkeys(str(row.get("summary", "")) for row in rows if row.get("summary")))
    if distinct:
        shown = distinct[:12]
        summary = "；".join(shown)
        if len(distinct) > len(shown):
            summary += f"；另有 {len(distinct) - len(shown)} 项人事变动记入各年档案"
    else:
        summary = "本期未发生足以传遍各地的突破、陨落或大事件。"
    _append_news(
        context,
        world_id=_entity_world(context, actor_id),
        title=f"{years}年纪要",
        summary=summary,
        tags=("system", "era_summary", "world_news"),
    )


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
    bus.event_bus.register("character.died", _project_character_died)
    projector = _project_simulation_event(definitions)
    for event_type in (
        "npc.breakthrough",
        "npc.breakthrough.batch",
        "npc.departed",
        "npc.tribulation.resolved",
        "faction.member.breakthrough",
        "family.member.breakthrough",
        "family.child.cultivation_started",
        "family.member.recruited",
        "faction.member.recruited",
        "family.extinct",
        "faction.dissolved",
        "faction.npc_founded",
        "npc.notorious.killing",
        "war.declared",
        "war.peace.concluded",
        "governance.diplomacy.voted",
        "governance.diplomacy.changed",
        "npc.duel.resolved",
        "dlc.monster.adaptation.unlocked",
    ):
        bus.event_bus.register(event_type, projector)
    # Scheduler events at the target year run after the final time slice.
    # Flush once more after the action runtime closes so deaths or other facts
    # due exactly that year are not stranded in the transient buffer.
    bus.event_bus.register("core.action.completed", _flush_news_buffer)
    bus.event_bus.register("core.action.completed", _project_era_summary)
    # TimeService may emit thousands of facts during one immortal action.
    # Commit each time slice as one component update instead of copying the
    # bounded news feed once per fact.
    bus.event_bus.register("core.time.advanced", _flush_news_buffer)
    bus.event_bus.register("core.action.interrupted", _flush_news_buffer)


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
