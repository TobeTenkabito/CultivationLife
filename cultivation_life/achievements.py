from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from .models import GameState
from .runtime import now_iso


FIVE_ELEMENTS = {"metal", "wood", "water", "fire", "earth"}
ALLOWED_SOURCE_KINDS = {"base", "dlc", "mod"}
ALLOWED_CATEGORIES = {"story", "cultivation"}


def load_achievement_definitions(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Validate and freeze the data-driven achievement catalog."""
    if document.get("schema_version") != 1 or not isinstance(document.get("achievements"), list):
        raise ValueError("achievements.json 须声明 schema_version=1 与 achievements 数组")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in document["achievements"]:
        if not isinstance(row, dict):
            raise ValueError("成就定义必须是对象")
        achievement_id = str(row.get("id", ""))
        source = row.get("source", {})
        if not achievement_id or achievement_id in seen:
            raise ValueError("成就定义存在缺失或重复 ID")
        if not row.get("name") or not row.get("description") or row.get("category") not in ALLOWED_CATEGORIES:
            raise ValueError(f"成就 {achievement_id} 缺少名称、条件说明或合法分类")
        if not isinstance(source, dict) or source.get("kind") not in ALLOWED_SOURCE_KINDS:
            raise ValueError(f"成就 {achievement_id} 必须声明本体、DLC 或 MOD 来源")
        if not source.get("id") or not source.get("name") or not isinstance(row.get("condition"), dict):
            raise ValueError(f"成就 {achievement_id} 的来源或解锁条件不完整")
        seen.add(achievement_id)
        result.append(copy.deepcopy(row))
    return tuple(result)


class GlobalMetadataStore:
    """Cross-save metadata stored beside normal saves, never inside a character save."""

    filename = "global_metadata.json"

    def __init__(self, save_directory: Path):
        self.path = save_directory / self.filename
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"schema_version": 1, "achievements": {}}

    def ensure_exists(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._write(self._empty())

    def read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return self._empty()
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return self._empty()
            if data.get("schema_version") != 1 or not isinstance(data.get("achievements"), dict):
                return self._empty()
            return data

    def unlock(self, definitions: list[dict[str, Any]], game: GameState) -> list[dict[str, Any]]:
        if not definitions:
            return []
        with self._lock:
            data = self.read()
            unlocked = data["achievements"]
            fresh: list[dict[str, Any]] = []
            for definition in definitions:
                achievement_id = definition["id"]
                if achievement_id in unlocked:
                    continue
                record = {
                    "unlocked_at": now_iso(),
                    "game_id": game.id,
                    "player_name": game.player.name,
                }
                unlocked[achievement_id] = record
                fresh.append({**public_definition(definition), **record, "unlocked": True})
            if fresh:
                self._write(data)
            return fresh

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


class AchievementSystem:
    def __init__(self, definitions: tuple[dict[str, Any], ...], save_directory: Path):
        self.definitions = definitions
        self.metadata = GlobalMetadataStore(save_directory)

    def ensure_global_metadata(self) -> None:
        self.metadata.ensure_exists()

    def evaluate(self, game: GameState, *, player_rank: int | None = None) -> list[dict[str, Any]]:
        completed = [
            definition for definition in self.definitions
            if self._matches(definition["condition"], game, player_rank=player_rank)
        ]
        return self.metadata.unlock(completed, game)

    def public_catalog(self) -> dict[str, Any]:
        records = self.metadata.read()["achievements"]
        rows: list[dict[str, Any]] = []
        for definition in self.definitions:
            record = records.get(definition["id"])
            rows.append({
                **public_definition(definition),
                "unlocked": record is not None,
                "unlocked_at": record.get("unlocked_at") if record else None,
                "player_name": record.get("player_name") if record else None,
            })
        unlocked = sum(1 for row in rows if row["unlocked"])
        return {"achievements": rows, "unlocked": unlocked, "total": len(rows)}

    def _matches(self, condition: dict[str, Any], game: GameState, *, player_rank: int | None) -> bool:
        player = game.player
        if set(condition) == {"all"}:
            return all(self._matches(child, game, player_rank=player_rank) for child in condition["all"])
        if set(condition) == {"any"}:
            return any(self._matches(child, game, player_rank=player_rank) for child in condition["any"])
        if "item" in condition:
            return any(item.id == condition["item"] and item.quantity > 0 for item in player.inventory)
        if "flag" in condition:
            return condition["flag"] in player.story_flags
        if "born_rootless" in condition:
            return player.born_rootless == bool(condition["born_rootless"])
        if "path" in condition:
            return player.path == str(condition["path"])
        if "realm_at_least" in condition:
            return player.realm_index >= int(condition["realm_at_least"])
        if "spirit_root" in condition:
            return player.spirit_root == condition["spirit_root"]
        if "affinities" in condition:
            from .rules import root_elements

            owned = set(root_elements(player.spirit_root)) | set(player.additional_roots)
            return set(map(str, condition["affinities"])) <= owned
        if "techniques" in condition:
            known = {
                technique.id for technique in [
                    player.technique, player.support_technique, player.body_technique,
                    player.divine_sense_technique, player.transformation_technique,
                    *player.combat_techniques, *player.known_techniques,
                ] if technique
            }
            return set(map(str, condition["techniques"])) <= known
        if "history" in condition:
            expected = condition["history"]
            return any(
                (not expected.get("event_id") or record.event_id == expected["event_id"])
                and (not expected.get("event_prefix") or record.event_id.startswith(expected["event_prefix"]))
                and (not expected.get("choice_id") or record.choice_id == expected["choice_id"])
                and (not expected.get("result") or record.result == expected["result"])
                and record.result not in expected.get("exclude_results", [])
                for record in game.history
            )
        if "relationship" in condition:
            expected = condition["relationship"]
            if expected.get("player_realms") and player.realm_index not in expected["player_realms"]:
                return False
            kind = expected.get("kind")
            if kind == "companion":
                relations = [player.dao_companion] if player.dao_companion else []
            elif kind == "master":
                relations = [player.master] if player.master else []
            elif kind == "disciple":
                relations = player.disciples
            elif kind == "friend":
                relations = player.dao_friends
            else:
                return False
            minimum_realm = int(expected.get("minimum_realm", 0))
            return any(
                relation and relation.get("alive", True)
                and int(relation.get("realm_index", 0)) >= minimum_realm
                for relation in relations
            )
        if "founded_faction" in condition:
            return any(
                faction.founded_by_player and faction.founder_player_id == game.id
                for faction in game.sects.values()
            )
        if "ranking" in condition:
            return player_rank == int(condition["ranking"])
        if "puppet_count" in condition:
            expected = condition["puppet_count"]
            kind = str(expected.get("type", ""))
            count = sum(
                1 for puppet in player.puppets
                if puppet.get("alive", True) and (not kind or puppet.get("type") == kind)
            )
            return count >= int(expected.get("minimum", 1))
        if "milestone_at_least" in condition:
            expected = condition["milestone_at_least"]
            return int(player.milestones.get(str(expected["id"]), 0)) >= int(expected.get("value", 1))
        if "wanted_target" in condition:
            threshold = 100.0
            try:
                from .content_registry import WORLD_SYSTEMS

                threshold = float(WORLD_SYSTEMS["faction_conflict"]["wanted_threshold"])
            except (ImportError, KeyError, TypeError, ValueError):
                pass
            return bool(
                int(player.milestones.get("became_wanted_target", 0))
                or any(float(value) > threshold for value in player.hostility.values())
                or (game.heavenly_court and "player" in game.heavenly_court.get("wanted_ids", []))
            )
        if "natal_artifact" in condition:
            expected = condition["natal_artifact"]
            return bool(
                game.natal_artifact
                and game.natal_artifact.get("item_id") == expected.get("item_id")
                and float(player.natal_artifact_combat_bonus) >= float(expected.get("minimum_combat_bonus", 0))
            )
        if "heavenly_court_controls" in condition:
            offices = game.heavenly_court.get("offices", {}) if game.heavenly_court else {}
            controlled = sum(
                1 for office in offices.values()
                if office and office.get("holder_id") == "player"
            )
            return controlled >= int(condition["heavenly_court_controls"])
        if "monster_evolution_realm_at_least" in condition:
            try:
                from .content_registry import MONSTER_EVOLUTIONS

                return any(
                    int(MONSTER_EVOLUTIONS.get(evolution_id, {}).get("realm_index", -1))
                    >= int(condition["monster_evolution_realm_at_least"])
                    for evolution_id in player.monster_evolution_history
                )
            except ImportError:
                return False
        if "monster_atavism_completed" in condition:
            return any(
                evolution_id.endswith("_NETHER_TRUE_4")
                for evolution_id in player.monster_evolution_history
            )
        if "monster_custom_lineage" in condition:
            return bool(player.monster_custom_lineage_id and player.monster_custom_lineage)
        if "monster_bloodline_trait_count" in condition:
            try:
                from .monster_bloodline_system import active_bloodline_profile

                profile = active_bloodline_profile(player)
                fixed = set(map(str, profile.get("traits", [])))
                generated = {
                    str(row.get("id") or row.get("slot_id"))
                    for row in profile.get("generated_traits", []) if row.get("id") or row.get("slot_id")
                }
                return len(fixed | generated) >= int(condition["monster_bloodline_trait_count"])
            except ImportError:
                return False
        return False


def public_definition(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": definition["id"],
        "name": definition["name"],
        "description": definition["description"],
        "category": definition["category"],
        "source": copy.deepcopy(definition["source"]),
    }
