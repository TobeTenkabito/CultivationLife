from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .domain.artifacts import NATAL, artifact_static_bonuses
from .domain.celestial import CELESTIAL_COURT
from .domain.combat import combat_snapshot
from .domain.definitions import GameDefinitions
from .domain.demonic import PUPPET
from .domain.factions import FACTION_PROFILE
from .domain.monster import MONSTER_BLOODLINE, monster_view
from .domain.world import LOCATION
from .kernel.model import WorldState


def load_achievement_definitions(
    content_root: Path,
    project_root: Path,
    definitions: GameDefinitions,
) -> tuple[dict[str, Any], ...]:
    documents: list[tuple[dict[str, Any], dict[str, str]]] = []
    base = json.loads((content_root / "achievements.json").read_text(encoding="utf-8"))
    documents.append((base, {"kind": "base", "id": "base", "name": "游戏本体"}))
    enabled = {
        extension.id: extension for extension in definitions.extensions
        if extension.enabled and extension.status == "loaded"
    }
    for kind, folder in (("dlc", "dlc"), ("mod", "mods")):
        for manifest_path in sorted((project_root / folder).glob("*/manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            package_id = str(manifest.get("id", ""))
            if package_id not in enabled:
                continue
            path = manifest_path.parent / "content" / "achievements.json"
            if not path.is_file():
                continue
            documents.append((
                json.loads(path.read_text(encoding="utf-8")),
                {
                    "kind": kind, "id": package_id,
                    "name": str(manifest.get("name", package_id)),
                },
            ))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for document, source in documents:
        if document.get("schema_version") != 1:
            raise ValueError("成就内容版本不受支持")
        for raw in document.get("achievements", []):
            row = copy.deepcopy(raw)
            achievement_id = str(row.get("id", ""))
            if not achievement_id or achievement_id in seen:
                raise ValueError("成就定义缺少或重复ID")
            if not isinstance(row.get("condition"), dict):
                raise ValueError(f"成就 {achievement_id} 缺少解锁条件")
            row["source"] = dict(row.get("source") or source)
            rows.append(row)
            seen.add(achievement_id)
    return tuple(rows)


def public_definition(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(definition[key])
        for key in ("id", "name", "description", "category", "source")
    }


def matching_achievement_ids(
    state: WorldState,
    definitions: GameDefinitions,
    achievements: tuple[dict[str, Any], ...],
) -> list[str]:
    actor_id = state.controlled_entity_id
    if actor_id is None:
        return []
    return [
        str(row["id"])
        for row in achievements
        if _matches(dict(row["condition"]), state, definitions, str(actor_id))
    ]


def _matches(
    condition: dict[str, Any],
    state: WorldState,
    definitions: GameDefinitions,
    actor_id: str,
) -> bool:
    if set(condition) == {"all"}:
        return all(
            _matches(dict(child), state, definitions, actor_id)
            for child in condition["all"]
        )
    if set(condition) == {"any"}:
        return any(
            _matches(dict(child), state, definitions, actor_id)
            for child in condition["any"]
        )
    cultivation = state.entities.require(actor_id, "cultivation.state")
    story = state.entities.get(actor_id, "story.state") or {}
    if "item" in condition:
        inventory = state.entities.get(actor_id, "economy.inventory") or {}
        return int(dict(inventory.get("items", {})).get(str(condition["item"]), 0)) > 0
    if "flag" in condition:
        return str(condition["flag"]) in set(map(str, story.get("flags", [])))
    if "born_rootless" in condition:
        born_root = str(cultivation.get(
            "born_spirit_root", cultivation.get("spirit_root", "")
        ))
        return (born_root == "none") == bool(condition["born_rootless"])
    if "path" in condition:
        return str(cultivation.get("path")) == str(condition["path"])
    if "realm_at_least" in condition:
        return definitions.realm_index(str(cultivation["realm_id"])) >= int(
            condition["realm_at_least"]
        )
    if "spirit_root" in condition:
        return str(cultivation.get("spirit_root")) == str(condition["spirit_root"])
    if "affinities" in condition:
        root = definitions.roots[str(cultivation["spirit_root"])]
        owned = set(root.elements) | set(map(str, cultivation.get("additional_roots", [])))
        return set(map(str, condition["affinities"])) <= owned
    if "techniques" in condition:
        practice = state.entities.require(actor_id, "cultivation.practice")
        return set(map(str, condition["techniques"])) <= set(map(
            str, practice.get("known_techniques", [])
        ))
    if "history" in condition:
        expected = dict(condition["history"])
        return any(
            (not expected.get("event_id") or row.get("event_id") == expected["event_id"])
            and (not expected.get("event_prefix") or str(row.get("event_id", "")).startswith(str(expected["event_prefix"])))
            and (not expected.get("choice_id") or row.get("choice_id") == expected["choice_id"])
            and (not expected.get("result") or row.get("result") == expected["result"])
            and row.get("result") not in expected.get("exclude_results", [])
            for row in story.get("history", [])
        )
    if "relationship" in condition:
        expected = dict(condition["relationship"])
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        if expected.get("player_realms") and realm_index not in expected["player_realms"]:
            return False
        kind = str(expected.get("kind", ""))
        relation_kind = {
            "companion": "dao_companion", "friend": "friend",
            "master": "master_disciple", "disciple": "master_disciple",
        }.get(kind)
        if relation_kind is None:
            return False
        edges = state.relations.involving(actor_id, kind=relation_kind)
        minimum = int(expected.get("minimum_realm", 0))
        for edge in edges:
            if kind == "master" and edge.target_id != actor_id:
                continue
            if kind == "disciple" and edge.source_id != actor_id:
                continue
            other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
            life = state.entities.get(other_id, "core.life") or {}
            other = state.entities.get(other_id, "cultivation.state") or {}
            if bool(life.get("alive")) and definitions.realm_index(
                str(other.get("realm_id", "mortal"))
            ) >= minimum:
                return True
        return False
    if "founded_faction" in condition:
        return any(
            state.entities.require(entity_id, FACTION_PROFILE).get("creator_id") == actor_id
            for entity_id in state.entities.with_component(FACTION_PROFILE)
        )
    if "ranking" in condition:
        location = state.entities.require(actor_id, LOCATION)
        world_id = str(location["world_id"])
        rows = []
        for entity_id in state.entities.with_component("core.identity"):
            other_location = state.entities.get(entity_id, LOCATION) or {}
            life = state.entities.get(entity_id, "core.life") or {}
            if other_location.get("world_id") == world_id and bool(life.get("alive")):
                rows.append((float(combat_snapshot(
                    state, definitions, entity_id
                )["power"]), entity_id))
        rows.sort(key=lambda row: (-row[0], row[1]))
        rank = next(
            (index for index, row in enumerate(rows, 1) if row[1] == actor_id),
            None,
        )
        return rank == int(condition["ranking"])
    if "puppet_count" in condition:
        expected = dict(condition["puppet_count"])
        puppet_kind = str(expected.get("type", ""))
        count = sum(
            1 for edge in state.relations.find(
                source_id=actor_id, kind="demonic.puppet_control"
            )
            for puppet in [state.entities.require(edge.target_id, PUPPET)]
            if (not puppet_kind or puppet.get("kind") == puppet_kind)
            and bool(puppet.get("active", True))
        )
        return count >= int(expected.get("minimum", 1))
    if "milestone_at_least" in condition:
        expected = dict(condition["milestone_at_least"])
        return int(dict(story.get("milestones", {})).get(str(expected["id"]), 0)) >= int(
            expected.get("value", 1)
        )
    if "wanted_target" in condition:
        court = state.entities.get(actor_id, CELESTIAL_COURT) or {}
        return bool(
            actor_id in court.get("wanted_ids", [])
            or int(dict(story.get("milestones", {})).get("became_wanted_target", 0))
        )
    if "natal_artifact" in condition:
        expected = dict(condition["natal_artifact"])
        artifact = dict((state.entities.get(actor_id, NATAL) or {}).get("artifact") or {})
        return bool(
            artifact.get("item_id") == expected.get("item_id")
            and float(artifact_static_bonuses(
                state, definitions, actor_id
            )["combat_power"]) >= float(expected.get("minimum_combat_bonus", 0))
        )
    if "heavenly_court_controls" in condition:
        court = state.entities.get(actor_id, CELESTIAL_COURT) or {}
        controlled = sum(
            1 for office in dict(court.get("offices", {})).values()
            if office and office.get("holder_id") == actor_id
        )
        return controlled >= int(condition["heavenly_court_controls"])
    bloodline = state.entities.get(actor_id, MONSTER_BLOODLINE) or {}
    if "monster_atavism_completed" in condition:
        return any(
            str(evolution_id).endswith("_NETHER_TRUE_4")
            for evolution_id in bloodline.get("evolution_history", [])
        )
    if "monster_custom_lineage" in condition:
        return isinstance(bloodline.get("custom_lineage"), dict)
    if "monster_bloodline_trait_count" in condition:
        view = monster_view(state, definitions, actor_id)
        current = dict(view.get("current") or {})
        custom = dict(view.get("custom_lineage") or {})
        traits = set(map(str, current.get("traits", [])))
        traits |= set(map(str, view.get("acquired_traits", [])))
        traits |= {
            str(row.get("id") or row.get("slot_id"))
            for row in custom.get("generated_traits", [])
            if row.get("id") or row.get("slot_id")
        }
        return len(traits) >= int(condition["monster_bloodline_trait_count"])
    return False
