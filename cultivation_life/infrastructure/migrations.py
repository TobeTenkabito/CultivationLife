from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from ..kernel.model import SAVE_FORMAT_ID, SAVE_SCHEMA_VERSION


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


def _schema_7_to_8(source: dict[str, Any]) -> dict[str, Any]:
    """Add instance assets, durable reservations and spirit-field production."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault(
            "economy.asset_ledger",
            {"next_sequence": 1, "instances": {}, "reservations": {}},
        )
        components.setdefault(
            "economy.spirit_field",
            {
                "reclaimed_qing": 0,
                "next_plot_sequence": 1,
                "plots": [],
                "art_experience": {
                    "alchemy": 0.0,
                    "refining": 0.0,
                    "formation": 0.0,
                    "talisman": 0.0,
                    "spirit_control": 0.0,
                },
            },
        )
        cultivation = dict(components.get("cultivation.state", {}))
        cultivation.setdefault("active_breakthrough_aids", [])
        cultivation.setdefault("intrinsic_hp_bonus", 0.0)
        cultivation.setdefault("intrinsic_mp_bonus", 0.0)
        cultivation.setdefault("next_thunder_damage_reduction", 0.0)
        if cultivation:
            components["cultivation.state"] = cultivation
    value["module_versions"] = {
        **dict(value.get("module_versions", {})), "assets": 1, "production": 1,
    }
    value["schema_version"] = 8
    return value


def _schema_8_to_9(source: dict[str, Any]) -> dict[str, Any]:
    """Add the auction/black-market state machine over the shared asset ledger."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" in components:
            components.setdefault(
                "economy.auction", {"next_sequence": 1, "session": None}
            )
    value["module_versions"] = {
        **dict(value.get("module_versions", {})), "auction": 1,
    }
    value["schema_version"] = 9
    return value


def _schema_9_to_10(source: dict[str, Any]) -> dict[str, Any]:
    """Add crafted artifacts, nine-palace formations and natal artifacts."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault(
            "crafting.artifacts", {"next_blueprint_sequence": 1, "blueprints": []}
        )
        components.setdefault(
            "formation.nine_palace", {
                "next_sequence": 1, "next_ground_sequence": 1,
                "loadouts": [], "active": None, "ground_arrays": [],
            },
        )
        components.setdefault("artifact.natal", {"artifact": None})
    value["module_versions"] = {
        **dict(value.get("module_versions", {})), "artifacts": 1,
    }
    value["schema_version"] = 10
    return value


def _schema_10_to_11(source: dict[str, Any]) -> dict[str, Any]:
    """Add canonical per-character affinity and relationship-attempt profiles."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" in components:
            components.setdefault(
                "relations.social_profile", {"affinities": {}, "attempts": []}
            )
    value["module_versions"] = {
        **dict(value.get("module_versions", {})), "relations": 2,
    }
    value["schema_version"] = 11
    return value


def _schema_11_to_12(source: dict[str, Any]) -> dict[str, Any]:
    """Add canonical lineage and concubine lifecycle state."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" in components:
            components.setdefault(
                "family.lineage",
                {
                    "child_ids": [],
                    "family_id": None,
                    "next_conception_bonus": 0.0,
                    "conceptions_attempted": 0,
                },
            )
            components.setdefault(
                "relations.concubine_state",
                {"cauldron_breakthrough_bonus": 0.0, "escape_reputation": 0},
            )
    value["module_versions"] = {
        **dict(value.get("module_versions", {})), "family": 1, "relations": 3,
    }
    value["schema_version"] = 12
    return value


def _schema_12_to_13(source: dict[str, Any]) -> dict[str, Any]:
    """Add governance runtime state without duplicating canonical characters."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" in components:
            components.setdefault("governance.diplomacy", {"relations": {}})
            concubine = components.get("relations.concubine_state")
            if isinstance(concubine, dict):
                concubine.setdefault("rejection_aftermath", [])
                concubine.setdefault(
                    "revenge_cooldown",
                    {"global_count": 0, "next_unit": -1, "sources": {}},
                )
        profile = components.get("faction.profile")
        if isinstance(profile, dict):
            profile.setdefault("roster_seeded", False)
        governance = components.get("faction.governance")
        if isinstance(governance, dict):
            governance.setdefault("designated_successor_id", None)
            governance.setdefault("last_ascension_handover", None)
        family = components.get("family.profile")
        if isinstance(family, dict):
            family.setdefault("last_recruitment_year", None)
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "relations": 4, "family": 2, "factions": 2,
    }
    value["schema_version"] = 13
    return value


def _schema_13_to_14(source: dict[str, Any]) -> dict[str, Any]:
    """Add canonical party-combat and war/bounty aggregate state."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" in components:
            components.setdefault(
                "governance.bounties", {"next_sequence": 1, "orders": []}
            )
    value["module_versions"] = {
        **dict(value.get("module_versions", {})), "combat": 2, "war": 1,
    }
    value["schema_version"] = 14
    return value


def _schema_14_to_15(source: dict[str, Any]) -> dict[str, Any]:
    """Add canonical imprisonment, puppet/soul and possession aggregate state."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        if "core.identity" not in components:
            continue
        components.setdefault("demonic.state", {
            "devouring_breakthrough_bonus": 0.0,
            "pending_post_battle_possession": None,
        })
        components.setdefault("demonic.imprisonment", {
            "active": None, "last_result": None,
        })
        components.setdefault("demonic.possession", {
            "host": None, "count": 0, "core": None,
        })
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "combat": 3,
        "demonic": 1,
    }
    value["schema_version"] = 15
    return value


def _schema_15_to_16(source: dict[str, Any]) -> dict[str, Any]:
    """Add canonical ghost ecology, reincarnation and possession body state."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        ghost = components.get("dlc.ghost.soul")
        if not isinstance(ghost, dict):
            continue
        ghost.setdefault("intrinsic_hp_reference", float(ghost.get("intrinsic_hp", 100.0)))
        ghost.setdefault("intrinsic_mp_reference", float(ghost.get("intrinsic_mp", 100.0)))
        ghost.setdefault("erosion_thresholds_seen", [])
        ghost.setdefault("last_reincarnation", None)
        components.setdefault("dlc.ghost.ecology", {
            "slots": {},
            "parade": None,
            "attachment": None,
            "captor": None,
            "pending_capture_revive": False,
        })
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "ghost": 1,
        "demonic": 2,
    }
    value["schema_version"] = 16
    return value


def _schema_16_to_17(source: dict[str, Any]) -> dict[str, Any]:
    """Add resumable monster evolution and custom-lineage state."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        bloodline = components.get("dlc.monster.bloodline")
        if not isinstance(bloodline, dict):
            continue
        bloodline.setdefault("generated_traits", [])
        bloodline.setdefault("lineage_deeds", {})
        bloodline.setdefault("custom_lineage_id", None)
        bloodline.setdefault("custom_lineage", None)
        bloodline.setdefault("pending_lineage_editor", None)
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "monster": 1,
    }
    value["schema_version"] = 17
    return value


def _schema_17_to_18(source: dict[str, Any]) -> dict[str, Any]:
    """Declare the persistent celestial-court aggregate module."""
    value = copy.deepcopy(source)
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "celestial": 1,
    }
    value["schema_version"] = 18
    return value


def _schema_18_to_19(source: dict[str, Any]) -> dict[str, Any]:
    """Expand intrigue governance into personnel and prison authority state."""
    value = copy.deepcopy(source)
    entities = dict(value.setdefault("entities", {}).setdefault("entities", {}))
    value["entities"]["entities"] = entities
    for components in entities.values():
        intrigue = components.get("dlc.intrigue.governance")
        if not isinstance(intrigue, dict):
            continue
        intrigue.setdefault("member_contribution", {})
        intrigue.setdefault("unrest", 0.0)
        intrigue.setdefault("fear", 0.0)
        intrigue.setdefault("time_progress", 0.0)
        intrigue.setdefault("personnel_history", [])
    value["module_versions"] = {
        **dict(value.get("module_versions", {})),
        "intrigue": 2,
    }
    value["schema_version"] = 19
    return value


MIGRATIONS: dict[int, SnapshotMigration] = {
    1: _schema_1_to_2,
    2: _schema_2_to_3,
    3: _schema_3_to_4,
    4: _schema_4_to_5,
    5: _schema_5_to_6,
    6: _schema_6_to_7,
    7: _schema_7_to_8,
    8: _schema_8_to_9,
    9: _schema_9_to_10,
    10: _schema_10_to_11,
    11: _schema_11_to_12,
    12: _schema_12_to_13,
    13: _schema_13_to_14,
    14: _schema_14_to_15,
    15: _schema_15_to_16,
    16: _schema_16_to_17,
    17: _schema_17_to_18,
    18: _schema_18_to_19,
}


def migrate_snapshot(source: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(source)
    if value.get("format") != SAVE_FORMAT_ID:
        raise ValueError("不是受支持的游戏存档")
    version = int(value.get("schema_version", 0))
    if version < 1 or version > SAVE_SCHEMA_VERSION:
        raise ValueError("不支持的存档版本")
    while version < SAVE_SCHEMA_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"缺少存档迁移：{version} → {version + 1}")
        value = migration(value)
        next_version = int(value.get("schema_version", 0))
        if next_version != version + 1:
            raise ValueError(f"存档迁移未正确推进版本：{version}")
        version = next_version
    return value
