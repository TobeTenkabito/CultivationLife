from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from ..kernel.model import V2_FORMAT_ID, V2_SCHEMA_VERSION


SnapshotMigration = Callable[[dict[str, Any]], dict[str, Any]]


def _schema_1_to_2(source: dict[str, Any]) -> dict[str, Any]:
    """Upgrade the experimental step-3 save into the first domain model."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    controlled = value.get("controlled_entity_id")
    if controlled and controlled in entities:
        components = entities[controlled]
        identity = dict(components.get("core.identity", {}))
        life = dict(components.get("character.life", {}))
        activity = dict(components.get("character.activity", {}))
        identity.setdefault("gender", "male")
        identity.setdefault("race", "human")
        current_age = int(dict(value.get("clock", {})).get("year", 0)) - int(life.get("birth_year", -16))
        life.setdefault("lifespan", max(90, current_age + 1))
        components["core.identity"] = identity
        components["character.life"] = life
        components.setdefault(
            "cultivation.state",
            {
                "path": "dao",
                "spirit_root": "supreme_wood",
                "additional_roots": [],
                "realm_id": "mortal",
                "layer": 1,
                "opportunity": float(activity.get("cultivation_progress", 0)),
                "heart_demon": 0.0,
                "bottleneck": None,
                "breakthrough_pity": {},
                "qi_experience": {"spirit": 0.0, "demon": 0.0, "monster": 0.0, "yin": 0.0},
            },
        )
        components.setdefault(
            "cultivation.practice",
            {"known_techniques": [], "main_technique_id": None},
        )
        components.setdefault(
            "world.location",
            {"world_id": "human", "location_id": "wudi_plain"},
        )
        if life.get("lifespan") is not None:
            scheduler = value.setdefault("scheduler", {"next_sequence": 1, "events": []})
            sequence = int(scheduler.get("next_sequence", 1))
            scheduler.setdefault("events", []).append({
                "due_year": int(life["birth_year"]) + int(life["lifespan"]),
                "sequence": sequence,
                "event_type": "character.lifespan.due",
                "source": "character",
                "scope": {"kind": "entity", "value": controlled},
                "payload": {"entity_id": controlled},
            })
            scheduler["next_sequence"] = sequence + 1
    value.setdefault("relations", {"next_sequence": 1, "edges": {}})
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "core": 2,
        "character": 2,
        "cultivation": 1,
        "world": 1,
        "relations": 1,
        "factions": 1,
    }
    value["schema_version"] = 2
    return value


def _schema_2_to_3(source: dict[str, Any]) -> dict[str, Any]:
    """Add economy and combat components without importing domain code."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault("economy.inventory", {"items": {}, "reserved": {}})
        components.setdefault("economy.market", {"revision": 0, "offers": []})
        components.setdefault("combat.condition", {"hp_ratio": 1.0, "mp_ratio": 1.0})
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "core": 2,
        "character": 2,
        "cultivation": 1,
        "world": 1,
        "relations": 1,
        "factions": 1,
        "economy": 1,
        "combat": 1,
        "extensions": 1,
    }
    value.setdefault("content_packages", {})
    value["schema_version"] = 3
    return value


def _schema_3_to_4(source: dict[str, Any]) -> dict[str, Any]:
    """Add persisted presentation preferences and the scoped news feed."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault(
            "presentation.preferences",
            {
                "combat_popup": True,
                "achievement_popup": True,
                "auto_advance_player_wars": False,
                "debug_world_news": False,
            },
        )
        components.setdefault(
            "presentation.world_news",
            {"next_sequence": 1, "entries": []},
        )
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "presentation": 1,
    }
    value["schema_version"] = 4
    return value


def _schema_4_to_5(source: dict[str, Any]) -> dict[str, Any]:
    """Persist the unified action state and interactive story queue."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault(
            "core.action_runtime",
            {"active": None, "next_sequence": 1, "last_completed": None},
        )
        components.setdefault(
            "story.state",
            {
                "pending": None,
                "queue": [],
                "history": [],
                "flags": [],
                "milestones": {},
                "attributes": {"karma": 0.0, "fame": 0.0, "sha_qi": 0.0},
            },
        )
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "actions": 1,
        "story": 1,
    }
    value["schema_version"] = 5
    return value


def _schema_5_to_6(source: dict[str, Any]) -> dict[str, Any]:
    """Add independent body, divine-sense and transformation components."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault("cultivation.body", {
            "technique_id": None, "layer": 0, "progress": 0.0,
            "ready": False, "breakthrough_pity": {}, "intrinsic_hp_bonus": 0.0,
        })
        components.setdefault("cultivation.divine_sense", {
            "technique_id": None, "rank": 0, "experience": 0.0,
        })
        components.setdefault("cultivation.transformations", {
            "technique_id": None, "mastery": {}, "loadouts": {},
        })
        components.setdefault("world.transition", {
            "sealed_cultivation": None, "last_transaction": None, "history": [],
        })
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "advanced_cultivation": 1, "world": 2,
    }
    value["schema_version"] = 6
    return value


def _schema_6_to_7(source: dict[str, Any]) -> dict[str, Any]:
    """Persist interactive breakthrough and ascension trial state."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault("cultivation.trial", {"active": None, "history": []})
    value["module_versions"] = {
        **dict(value.get("module_versions", {})), "trials": 1,
    }
    value["schema_version"] = 7
    return value


MIGRATIONS: dict[int, SnapshotMigration] = {
    1: _schema_1_to_2,
    2: _schema_2_to_3,
    3: _schema_3_to_4,
    4: _schema_4_to_5,
    5: _schema_5_to_6,
    6: _schema_6_to_7,
}


def migrate_snapshot(source: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(source)
    if value.get("format") != V2_FORMAT_ID:
        raise ValueError("不是V2存档")
    version = int(value.get("schema_version", 0))
    if version < 1 or version > V2_SCHEMA_VERSION:
        raise ValueError("不支持的V2存档版本")
    while version < V2_SCHEMA_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"缺少V2存档迁移：{version} → {version + 1}")
        value = migration(value)
        next_version = int(value.get("schema_version", 0))
        if next_version != version + 1:
            raise ValueError(f"V2存档迁移未正确推进版本：{version}")
        version = next_version
    return value
