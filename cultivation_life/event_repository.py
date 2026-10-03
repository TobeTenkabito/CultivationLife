from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ContentError as ContentError
from .event_catalog import EventCatalog


@dataclass(frozen=True)
class EventRepository(EventCatalog):
    """Compatibility loader using the active registry when catalogs are omitted."""

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
        return super().from_documents(documents, allow_overrides=allow_overrides, catalogs=catalogs)
