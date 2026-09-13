from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .content_registry import ContentError


@dataclass(frozen=True)
class EventRepository:
    events: tuple[dict[str, Any], ...]
    by_id: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, content_root: Path) -> "EventRepository":
        paths = [content_root / "events.json", *sorted(content_root.glob("*_events.json"))]
        documents: list[tuple[str, dict[str, Any]]] = []
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ContentError(f"事件文件 {path.name} 无法加载：{error}") from error
            if document.get("schema_version") != 1 or not isinstance(document.get("events"), list):
                raise ContentError(f"事件文件 {path.name} 格式不合法")
            documents.append((path.name, document))
        return cls.from_documents(documents)

    @classmethod
    def from_documents(
        cls, documents: list[tuple[str, dict[str, Any]]], *, allow_overrides: bool = False,
        catalogs: dict[str, Any] | None = None,
    ) -> "EventRepository":
        if catalogs is None:
            from .content_registry import (
                FACTION_DEFINITIONS, ITEM_CATALOG, MONSTER_BLOODLINE_SETTINGS,
                TECHNIQUE_CATALOG, WORLD_NPC_TEMPLATES,
            )

            catalogs = {
                "items": ITEM_CATALOG, "techniques": TECHNIQUE_CATALOG,
                "factions": FACTION_DEFINITIONS, "world_npcs": WORLD_NPC_TEMPLATES,
                "monster_imprints": MONSTER_BLOODLINE_SETTINGS.get("imprints", {}),
            }
        events: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}
        positions: dict[str, int] = {}
        for source_name, document in documents:
            if document.get("schema_version") != 1 or not isinstance(document.get("events"), list):
                raise ContentError(f"事件文件 {source_name} 格式不合法")
            document_world = document.get("world")
            for source_event in document["events"]:
                event = dict(source_event)
                if document_world:
                    event["tags"] = list(dict.fromkeys([*event.get("tags", []), f"world:{document_world}"]))
                event_id = event.get("id")
                if not event_id or (event_id in by_id and not allow_overrides):
                    raise ContentError(f"事件 ID 缺失或重复：{event_id}")
                cls._validate_event(event, catalogs)
                if event_id in positions:
                    events[positions[event_id]] = event
                else:
                    positions[event_id] = len(events)
                    events.append(event)
                by_id[event_id] = event
        for event in events:
            for choice in event.get("choices", []):
                for effect in choice.get("effects", []):
                    if effect.get("type") == "queue_event" and effect.get("event_id") not in by_id:
                        raise ContentError(f"事件 {event['id']} 排入不存在的后续事件：{effect.get('event_id')}")
        return cls(tuple(events), by_id)

    @classmethod
    def _validate_event(cls, event: dict[str, Any], catalogs: dict[str, Any]) -> None:
        if not event.get("title") or not isinstance(event.get("choices"), list) or not event["choices"]:
            raise ContentError(f"事件 {event.get('id')} 缺少标题或选项")
        choice_ids: set[str] = set()
        cls._validate_condition(event.get("conditions", {}), event["id"], catalogs)
        combat = event.get("combat")
        if combat:
            offsets = combat.get("realm_offsets", [])
            bounds = combat.get("power_bounds", [])
            valid_offsets = (
                isinstance(offsets, list) and bool(offsets)
                and all(isinstance(entry, list) and len(entry) == 2 and entry[1] >= 0 for entry in offsets)
                and sum(entry[1] for entry in offsets) > 0
            )
            if (
                not combat.get("target_name") or not valid_offsets
                or not isinstance(combat.get("power_sigma"), (int, float)) or combat["power_sigma"] <= 0
                or len(bounds) != 2 or bounds[0] <= 0 or bounds[0] > bounds[1]
            ):
                raise ContentError(f"事件 {event['id']} 的修士战斗分布不合法")
        for choice in event["choices"]:
            choice_id = choice.get("id")
            if not choice_id or choice_id in choice_ids:
                raise ContentError(f"事件 {event['id']} 的选项 ID 缺失或重复")
            choice_ids.add(choice_id)
            cls._validate_condition(choice.get("conditions", {}), event["id"], catalogs)
            for effect in choice.get("effects", []):
                kind = effect.get("type")
                if kind in {"add_item", "remove_item"} and effect.get("item_id") not in catalogs["items"]:
                    raise ContentError(f"事件 {event['id']} 引用不存在的物品：{effect.get('item_id')}")
                if kind in {"equip_technique", "learn_technique"} and effect.get("technique_id") not in catalogs["techniques"]:
                    raise ContentError(f"事件 {event['id']} 引用不存在的功法：{effect.get('technique_id')}")
                if kind == "join_faction" and effect.get("faction_id") not in catalogs["factions"]:
                    raise ContentError(f"事件 {event['id']} 引用不存在的宗门：{effect.get('faction_id')}")
                if kind == "grant_monster_imprint" and effect.get("imprint_id") not in catalogs.get("monster_imprints", {}):
                    raise ContentError(f"事件 {event['id']} 引用不存在的血脉印记：{effect.get('imprint_id')}")
                if kind == "attribute_check":
                    for check in effect.get("checks", []):
                        if check.get("stat") == "has_item" and check.get("item_id") not in catalogs["items"]:
                            raise ContentError(f"事件 {event['id']} 的判定引用不存在的物品：{check.get('item_id')}")
                        if check.get("stat") not in {
                            "has_item", "hp", "mp", "combat_power", "hp_ratio", "mp_ratio",
                            "combat_ratio", "karma", "sha_qi", "heart_demon", "fame",
                        }:
                            raise ContentError(f"事件 {event['id']} 使用未知属性判定：{check.get('stat')}")

    @classmethod
    def _validate_condition(cls, condition: dict[str, Any], event_id: str, catalogs: dict[str, Any]) -> None:
        if not condition:
            return
        for group in ("all", "any"):
            if group in condition:
                for child in condition[group]:
                    cls._validate_condition(child, event_id, catalogs)
        if "not" in condition:
            cls._validate_condition(condition["not"], event_id, catalogs)
        if "has_item" in condition and condition["has_item"] not in catalogs["items"]:
            raise ContentError(f"事件 {event_id} 的条件引用不存在的物品：{condition['has_item']}")
        if "knows_technique" in condition and condition["knows_technique"] not in catalogs["techniques"]:
            raise ContentError(f"事件 {event_id} 的条件引用不存在的功法：{condition['knows_technique']}")
        if "world_npc" in condition and condition["world_npc"].get("id") not in catalogs["world_npcs"]:
            raise ContentError(f"事件 {event_id} 的条件引用不存在的世界 NPC：{condition['world_npc'].get('id')}")
