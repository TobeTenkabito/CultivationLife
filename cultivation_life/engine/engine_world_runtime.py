from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from ..content_registry import (
    ACTIONS, FACTION_DEFINITIONS, FACTION_NPC_TEMPLATES, FACTION_REWARDS, FACTION_SYSTEMS,
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS, ITEM_CATALOG, MARKET_GOODS,
    PATH_NAMES, REALMS,
    RACE_DEFINITIONS, RACE_SYSTEMS, ROOT_DEFINITIONS, TECHNIQUE_CATALOG,
    WORLD_NPC_TEMPLATES, WORLD_SYSTEMS,
    MONSTER_BLOODLINE_SETTINGS, MONSTER_SPECIES,
)
from ..models import GameState, HistoryRecord, Player, SectNpc, SectState
from ..system.npc_system import npc_breakthrough_chance, npc_combat_power, npc_team_combat_power
from ..rules import (
    add_item,
    can_practice_technique,
    expected_combat_power,
    has_item,
    max_hp,
    max_mp,
    divine_sense_level,
)


from ..world_state import (
    RELATION_LABELS, race_pair, split_race_pair,
)
from ..system.monster_bloodline_system import (
    bloodline_content_available,
)
from ..system.concubine_system import gender_name
from .engine_constants import LEGACY_TRUE_DEMON_RACE_MAP


class EngineWorldRuntimeMixin:
    @staticmethod
    def _new_sects() -> dict[str, SectState]:
        sects = {
            sect_id: SectState(
                id=sect_id,
                name=FACTION_DEFINITIONS[sect_id]["name"],
                world=FACTION_DEFINITIONS[sect_id].get("world", "human"),
                npcs=[SectNpc(**copy.deepcopy(npc)) for npc in templates],
                description=FACTION_DEFINITIONS[sect_id].get("description", ""),
                path=FACTION_DEFINITIONS[sect_id].get("path", "dao"),
                allegiance_race=FACTION_DEFINITIONS[sect_id].get("allegiance_race"),
            )
            for sect_id, templates in FACTION_NPC_TEMPLATES.items()
        }
        for sect_id, sect in sects.items():
            for npc in sect.npcs:
                npc.faction_id = sect_id
                npc.world = sect.world
        return sects

    def _ensure_sects(self, game: GameState) -> None:
        fresh = self._new_sects()
        if game.world_rules_version < 2:
            game.sects = fresh
            game.world_rules_version = 6
        for sect_id, new_sect in fresh.items():
            if sect_id not in game.sects:
                game.sects[sect_id] = new_sect
                continue
            game.sects[sect_id].world = new_sect.world
            game.sects[sect_id].allegiance_race = new_sect.allegiance_race
            known_ids = {npc.id for npc in game.sects[sect_id].npcs}
            game.sects[sect_id].npcs.extend(npc for npc in new_sect.npcs if npc.id not in known_ids)
            templates = {npc.id: npc for npc in new_sect.npcs}
            for npc in game.sects[sect_id].npcs:
                if not npc.faction_id:
                    npc.faction_id = sect_id
                template = templates.get(npc.id)
                if not npc.spirit_root:
                    npc.spirit_root = (
                        template.spirit_root if template and template.spirit_root
                        else self._random_npc_root(npc.realm_index, random.Random(f"{game.seed}:{npc.id}"))
                    )
                if game.world_rules_version < 4 and template:
                    npc.path = template.path
                elif not npc.path or npc.path not in PATH_NAMES:
                    npc.path = template.path if template else self._random_npc_path(sect_id, random.Random(f"path:{game.seed}:{npc.id}"))
                npc.world = getattr(npc, "world", new_sect.world) or new_sect.world
                npc.race = getattr(npc, "race", "human") or "human"
                if not npc.treasure_item_id and not npc.treasure_looted:
                    npc.treasure_item_id = self._select_npc_treasure(
                        npc, random.Random(f"treasure:{game.seed}:{npc.id}")
                    )
                if npc.affinity is None:
                    npc.affinity = random.Random(f"affinity:{game.seed}:{npc.id}").uniform(-8, 12)
            self._compact_sect_roster(game, game.sects[sect_id])
        game.world_rules_version = max(game.world_rules_version, 7)

    def _compact_sect_roster(self, game: GameState, sect: SectState) -> bool:
        """Discard only stale dead recruit records once a sect's simulation roster is full."""
        cap = int(FACTION_SYSTEMS.get("max_roster_records", 48))
        if len(sect.npcs) <= cap:
            return False
        protected = {str(npc.get("id")) for npc in FACTION_NPC_TEMPLATES.get(sect.id, [])}
        protected.update(str(row.get("id")) for row in [
            game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples,
        ] if row and row.get("id"))
        for war in game.wars:
            if war.get("status") in {"active", "peace_ready"}:
                protected.update(war.get("roster", {}).get("attacker", []))
                protected.update(war.get("roster", {}).get("defender", []))
        removable = [npc for npc in sect.npcs if not npc.alive and npc.id not in protected]
        remove_ids = {npc.id for npc in removable[:max(0, len(sect.npcs) - cap)]}
        if not remove_ids:
            return False
        sect.npcs = [npc for npc in sect.npcs if npc.id not in remove_ids]
        return True

    @staticmethod
    def _compact_world_history(game: GameState) -> bool:
        """Bound old ambient world news while preserving the player's personal chronicle."""
        cap = int(WORLD_SYSTEMS.get("performance", {}).get("max_world_history_records", 6000))
        world_news = [record for record in game.history if "world_news" in record.tags]
        excess = len(world_news) - cap
        if excess <= 0:
            return False
        discard = {id(record) for record in world_news[:excess]}
        game.history = [record for record in game.history if id(record) not in discard]
        return True

    @staticmethod
    def _new_world_npcs() -> dict[str, SectNpc]:
        return {npc_id: copy.deepcopy(npc) for npc_id, npc in WORLD_NPC_TEMPLATES.items()}

    def _ensure_world_npcs(self, game: GameState) -> bool:
        fresh = self._new_world_npcs()
        changed = False
        # V6 以前没有保存固定 NPC 的模板基准。这里只记录真正发生过
        # 变更的旧基准；其后的 JSON 年龄调整均可通过存档里的基准通用迁移。
        legacy_initial_ages = {"xiang_zhili": 2810}
        for npc_id, npc in fresh.items():
            if npc_id not in game.world_npcs:
                game.world_npcs[npc_id] = npc
                changed = True
            current = game.world_npcs[npc_id]
            template_age = int(npc.age)
            recorded_age = game.world_npc_template_ages.get(npc_id)
            if recorded_age is None:
                legacy_age = legacy_initial_ages.get(npc_id)
                if legacy_age is not None and current.age >= legacy_age and template_age != legacy_age:
                    elapsed = max(0, int(current.age) - legacy_age)
                    current.age = template_age + elapsed
                    changed = True
                game.world_npc_template_ages[npc_id] = template_age
                changed = True
            elif recorded_age != template_age:
                elapsed = max(0, int(current.age) - int(recorded_age))
                current.age = template_age + elapsed
                game.world_npc_template_ages[npc_id] = template_age
                changed = True
            if not current.treasure_item_id and not current.treasure_looted:
                current.treasure_item_id = self._select_npc_treasure(
                    current, random.Random(f"treasure:{game.seed}:{current.id}")
                )
                changed = True
            if current.affinity is None:
                current.affinity = random.Random(f"affinity:{game.seed}:{current.id}").uniform(-12, 8)
                changed = True
        if game.world_rules_version < 7:
            game.world_rules_version = 7
            changed = True
        return changed

    def _enforce_world_realm_caps(self, game: GameState) -> bool:
        """Migrate pre-V8 saves so lower worlds cannot retain upper-world NPCs."""
        if game.world_rules_version >= 8:
            return False
        changed = False
        migrated_names: list[str] = []

        # This NPC used to have an invalid world id and a lower placeholder realm.
        # Preserve elapsed age and mutable state while applying the new fixed identity.
        template = WORLD_NPC_TEMPLATES.get("wu_xingyun")
        current = game.world_npcs.get("wu_xingyun")
        if template and current and (current.world != template.world or current.realm_index != template.realm_index):
            elapsed_age = max(0, current.age - 1210)
            for field_name in (
                "name", "title", "realm_index", "layer", "lifespan", "spirit_root",
                "cultivation_progress", "path", "race", "world",
            ):
                setattr(current, field_name, copy.deepcopy(getattr(template, field_name)))
            current.age = template.age + elapsed_age
            game.world_npc_template_ages[current.id] = template.age
            changed = True
            migrated_names.append(current.name)

        demon_cap = self._world_realm_cap("demon")
        for sect in game.sects.values():
            if sect.world != "demon":
                continue
            upper_members = [npc for npc in sect.npcs if npc.realm_index > demon_cap]
            if not upper_members:
                continue
            if sect.founded_by_npc:
                sect.world = "true_demon"
                for npc in sect.npcs:
                    npc.world = "true_demon"
                migrated_names.append(sect.name)
            else:
                upper_ids = {npc.id for npc in upper_members}
                sect.npcs = [npc for npc in sect.npcs if npc.id not in upper_ids]
                for npc in upper_members:
                    npc.world = "true_demon"
                    npc.faction_id = None
                    npc.departed_age = npc.departed_age or npc.age
                    npc.departure_reason = npc.departure_reason or "飞升真魔界"
                    game.notable_npcs.setdefault(npc.id, npc)
                    migrated_names.append(npc.name)
            changed = True

        for collection in (game.world_npcs.values(), game.notable_npcs.values()):
            for npc in collection:
                if npc.world == "demon" and npc.realm_index > demon_cap:
                    npc.world = "true_demon"
                    npc.departed_age = npc.departed_age or npc.age
                    npc.departure_reason = npc.departure_reason or "飞升真魔界"
                    migrated_names.append(npc.name)
                    changed = True

        related_people = [
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples, *game.player.disciple_requests,
        ]
        for person in related_people:
            if person and person.get("world") == "demon" and int(person.get("realm_index", 0)) > demon_cap:
                person["world"] = "true_demon"
                migrated_names.append(str(person.get("name", "无名修士")))
                changed = True
        for cached in game.encounter_npc_cache:
            cached_npc = cached.get("npc") if isinstance(cached.get("npc"), dict) else cached
            if cached_npc.get("world") == "demon" and int(cached_npc.get("realm_index", 0)) > demon_cap:
                cached_npc["world"] = "true_demon"
                changed = True

        game.world_rules_version = 8
        if migrated_names:
            names = "、".join(dict.fromkeys(migrated_names))
            game.history.append(HistoryRecord(
                "SYS_WORLD_REALM_CAP_MIGRATION", 1, game.player.age, "界面境界校正", None,
                "migrated", f"旧存档中超出魔界境界上限的{names}已迁入真魔界。",
                {"destination": "true_demon", "npc_count": len(set(migrated_names))},
                ["system", "migration", "ascension", "world:true_demon"],
            ))
        return changed or bool(migrated_names)

    def _migrate_true_demon_races(self, game: GameState) -> bool:
        """Move pre-V9 true-demon residents off the former shared spirit race table."""
        if game.world_rules_version >= 9:
            return False
        true_demon_races = {
            race_id for race_id, definition in RACE_DEFINITIONS.items()
            if "true_demon" in definition.get("worlds", [])
        }
        migrated = 0

        def migrate_record(record: Any) -> None:
            nonlocal migrated
            if isinstance(record, SectNpc):
                if record.world != "true_demon" or record.race in true_demon_races:
                    return
                record.race = LEGACY_TRUE_DEMON_RACE_MAP.get(record.race, "human")
                migrated += 1
                return
            if not isinstance(record, dict) or record.get("world") != "true_demon":
                return
            old_race = str(record.get("race", "human"))
            if old_race not in true_demon_races:
                record["race"] = LEGACY_TRUE_DEMON_RACE_MAP.get(old_race, "human")
                migrated += 1

        # Fixed sect characters adopt their redesigned canonical race while all
        # mutable cultivation, affinity and survival state remains untouched.
        fixed_races = {
            str(template["id"]): str(template.get("race", "human"))
            for sect_id, templates in FACTION_NPC_TEMPLATES.items()
            if FACTION_DEFINITIONS[sect_id].get("world") == "true_demon"
            for template in templates
        }
        for sect in game.sects.values():
            if sect.world != "true_demon":
                continue
            old_allegiance = str(sect.allegiance_race or "human")
            if old_allegiance not in true_demon_races:
                sect.allegiance_race = LEGACY_TRUE_DEMON_RACE_MAP.get(old_allegiance, "human")
                migrated += 1
            for npc in sect.npcs:
                canonical_race = fixed_races.get(npc.id)
                if canonical_race and npc.race != canonical_race:
                    npc.race = canonical_race
                    migrated += 1
                else:
                    migrate_record(npc)

        for collection in (game.world_npcs.values(), game.notable_npcs.values()):
            for npc in collection:
                migrate_record(npc)
        for cached in game.encounter_npc_cache:
            migrate_record(cached.get("npc") if isinstance(cached.get("npc"), dict) else cached)
        for person in (
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples, *game.player.disciple_requests,
            *game.player.offspring, *game.player.prisoners, *game.player.puppets,
        ):
            if person:
                migrate_record(person)
        if game.family and game.family.world == "true_demon":
            old_allegiance = str(game.family.allegiance_race or "human")
            if old_allegiance not in true_demon_races:
                game.family.allegiance_race = LEGACY_TRUE_DEMON_RACE_MAP.get(old_allegiance, "human")
                migrated += 1
            for npc in game.family.npcs:
                migrate_record(npc)

        player = game.player
        if player.world == "true_demon":
            for field_name in ("race", "lineage_race", "allegiance_race"):
                old_race = str(getattr(player, field_name) or player.race)
                if old_race not in true_demon_races:
                    setattr(player, field_name, LEGACY_TRUE_DEMON_RACE_MAP.get(old_race, "human"))
                    migrated += 1

        game.world_rules_version = 9
        if migrated:
            game.history.append(HistoryRecord(
                "SYS_TRUE_DEMON_RACE_MIGRATION", 1, player.age, "真魔诸族重订", None,
                "migrated", f"真魔界族谱已独立重订，旧存档中的 {migrated} 项族属记录完成迁移。",
                {"migrated_records": migrated},
                ["system", "migration", "race", "world_news", "world:true_demon"],
            ))
        return True

    @staticmethod
    def _actual_player_realm(player: Player) -> tuple[int, int]:
        if player.sealed_cultivation:
            return int(player.sealed_cultivation["realm_index"]), int(player.sealed_cultivation["layer"])
        return player.realm_index, player.layer

    @staticmethod
    def _world_supports(world: str, feature: str) -> bool:
        profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world, {})
        return feature in profile.get("supports", [])

    @staticmethod
    def _world_realm_cap(world: str) -> int:
        profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world, {})
        return max(0, min(len(REALMS) - 1, int(profile.get("npc_realm_cap", len(REALMS) - 1))))
