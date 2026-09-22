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
from ..npc_system import npc_breakthrough_chance, npc_combat_power, npc_team_combat_power
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
from ..monster_bloodline_system import (
    bloodline_content_available,
)
from ..concubine_system import gender_name
from .engine_constants import LEGACY_TRUE_DEMON_RACE_MAP


class EngineWorldRuntimeMixin:
    @staticmethod
    def _party_invitation_chance(player: Player, npc: SectNpc, global_hostility: float = 0.0) -> float:
        config = WORLD_SYSTEMS["party"]
        realm_gap = max(0, npc.realm_index - player.realm_index)
        confidence_bonus = 0.0
        if player.realm_index >= npc.realm_index:
            confidence_bonus = min(
                float(config.get("lower_realm_bonus_cap", 0.22)),
                float(config.get("same_or_lower_realm_bonus", 0.12))
                + max(0, player.realm_index - npc.realm_index) * float(config.get("lower_realm_bonus_per_gap", 0.04)),
            )
        return max(0.02, min(
            0.9,
            float(config["invite_base_chance"]) + confidence_bonus
            + float(npc.affinity or 0) / 200 - global_hostility / 120 - realm_gap * 0.12,
        ))

    def _party_crossing_candidate(self, game: GameState, npc_id: str) -> dict[str, Any] | None:
        player = game.player
        npc = self._find_npc(game, npc_id)
        relation = next((entry for entry in [player.dao_companion, *player.dao_friends] if entry and str(entry.get("id")) == npc_id), None)
        source = relation or (npc.to_dict() if npc else None)
        if not source or not source.get("alive", True) or source.get("world") != player.world:
            return None
        requirements = {
            "human": (5, lambda layer: layer <= 3),
            "demon": (5, lambda layer: layer >= 1),
            "spirit": (8, lambda layer: layer == REALMS[8].layers),
            "true_demon": (8, lambda layer: layer == REALMS[8].layers),
        }
        required = requirements.get(player.world)
        if (
            not required or player.realm_index != required[0]
            or not required[1](player.layer)
        ):
            return None
        if not required or int(source.get("realm_index", -1)) != required[0] or not required[1](int(source.get("layer", 99))):
            return None
        return {"id":npc_id, "name":str(source.get("name", "无名队友"))}

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
    def _ensure_race_relations(game: GameState) -> bool:
        changed = False
        diplomacy = RACE_SYSTEMS.get("diplomacy", {})
        for row in diplomacy.get("initial_relations", []):
            members = list(row.get("members", []))
            if len(members) != 2:
                continue
            key = race_pair(str(members[0]), str(members[1]))
            if key not in game.race_relations:
                game.race_relations[key] = {
                    "affinity": float(row.get("affinity", 0)),
                    "status": str(row.get("status", "neutral")),
                    "since_age": game.player.age,
                    "name": row.get("name"),
                }
                changed = True
        return changed

    @staticmethod
    def _actual_player_realm(player: Player) -> tuple[int, int]:
        if player.sealed_cultivation:
            return int(player.sealed_cultivation["realm_index"]), int(player.sealed_cultivation["layer"])
        return player.realm_index, player.layer

    @staticmethod
    def _governance_threshold(world: str) -> int:
        thresholds = WORLD_SYSTEMS["player_faction"]["governance_threshold"]
        # 新增界面按界面层级沿用人界/上界治理门槛，避免每开一个界面都
        # 必须复制一份纯数值配置。
        fallback = "human" if world == "human" else "spirit"
        return int(thresholds.get(world, thresholds[fallback]))

    @staticmethod
    def _world_supports(world: str, feature: str) -> bool:
        profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world, {})
        return feature in profile.get("supports", [])

    @staticmethod
    def _world_realm_cap(world: str) -> int:
        profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world, {})
        return max(0, min(len(REALMS) - 1, int(profile.get("npc_realm_cap", len(REALMS) - 1))))

    @staticmethod
    def _faction_meta(game: GameState, faction_id: str) -> dict[str, Any]:
        if faction_id in FACTION_DEFINITIONS:
            return dict(FACTION_DEFINITIONS[faction_id])
        sect = game.sects.get(faction_id)
        if not sect:
            return {"name": faction_id, "world": "human", "path": "dao", "description": "自立势力"}
        return {
            "name": sect.name, "world": sect.world, "path": sect.path,
            "description": sect.description or "由玩家开创的新宗门。",
            "allegiance_race": sect.allegiance_race or "human",
        }

    @staticmethod
    def _ensure_sect_relations(game: GameState) -> bool:
        changed = False
        active = [sect for sect in game.sects.values() if not sect.extinct]
        for index, first in enumerate(active):
            for second in active[index + 1:]:
                if first.world != second.world:
                    continue
                key = race_pair(first.id, second.id)
                if key not in game.sect_relations:
                    game.sect_relations[key] = {
                        "affinity": 0.0, "status": "neutral", "since_age": game.player.age,
                    }
                    changed = True
        return changed

    def _has_race_voice(self, game: GameState) -> bool:
        if self._intrigue_enabled():
            race_id = self._player_allegiance_race(game.player)
            return self._world_supports(game.player.world, "races") and self._intrigue_has_decision_authority(game, "race", race_id)
        realm_index, _ = self._actual_player_realm(game.player)
        required = int(WORLD_SYSTEMS["world_travel"]["required_realm"])
        return self._world_supports(game.player.world, "races") and self._player_allegiance_race(game.player) == "human" and realm_index >= required

    def _has_sect_voice(self, game: GameState) -> bool:
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if self._intrigue_enabled():
            return bool(sect and self._intrigue_has_decision_authority(game, "sect", sect.id))
        realm_index, _ = self._actual_player_realm(player)
        return bool(
            sect and not sect.extinct and sect.world == player.world
            and (sect.founded_by_player or realm_index >= self._governance_threshold(player.world))
        )

    def _has_family_voice(self, game: GameState) -> bool:
        family = game.family
        if self._intrigue_enabled():
            return bool(
                family and family.world == game.player.world
                and self._intrigue_has_decision_authority(game, "family", family.id)
            )
        return bool(
            family and not family.extinct and family.founded_by_player
            and family.world == game.player.world
        )

    @staticmethod
    def _select_npc_treasure(npc: SectNpc, rng: random.Random) -> str | None:
        tier = max(1, min(8, npc.realm_index))
        market_worlds = {str(row.get("world", "human")) for row in MARKET_GOODS}
        world = npc.world if npc.world in market_worlds else ("spirit" if npc.realm_index >= 6 else "human")
        candidates = [
            row for row in MARKET_GOODS
            if row["kind"] == "item" and row.get("world", "human") == world
            and int(row["tier"]) == tier
            and "currency" not in ITEM_CATALOG[row["content_id"]].tags
            and "root_manual" not in ITEM_CATALOG[row["content_id"]].tags
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda row: int(row["price"]), reverse=True)
        return str(rng.choice(candidates[: min(4, len(candidates))])["content_id"])

    def _npc_power(self, npc: SectNpc) -> float:
        treasure = ITEM_CATALOG.get(npc.treasure_item_id or "")
        return npc_combat_power(
            npc, expected_combat_power, self._npc_root_efficiency(npc.spirit_root), treasure
        ) * max(0.1, float(getattr(npc, "combat_factor", 1.0))) * max(0.35, 1 - int(getattr(npc, "wounds", 0)) * 0.15)

    def _npc_breakthrough_probability(self, npc: SectNpc) -> float:
        if npc.realm_index >= 9 or (npc.realm_index == 8 and npc.layer >= REALMS[8].layers):
            return 0.0
        return npc_breakthrough_chance(
            npc, FACTION_SYSTEMS["npc_cultivation"], self._npc_root_efficiency(npc.spirit_root)
        )

    @staticmethod
    def _hostility_key(kind: str, entity_id: str) -> str:
        return f"{kind}:{entity_id}"

    def _npc_faction_id(self, game: GameState, npc_id: str) -> str | None:
        npc = self._find_npc(game, npc_id)
        if npc and npc.faction_id and npc.faction_id in game.sects and not game.sects[npc.faction_id].extinct:
            return npc.faction_id
        return next(
            (sect_id for sect_id, sect in game.sects.items() if any(npc.id == npc_id for npc in sect.npcs)),
            None,
        )

    def _sect_members(self, game: GameState, sect: SectState) -> list[SectNpc]:
        members = {npc.id:npc for npc in sect.npcs}
        for npc in [*game.world_npcs.values(), *game.notable_npcs.values()]:
            if npc.faction_id == sect.id:
                members[npc.id] = npc
        return list(members.values())

    def _find_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        if npc_id in game.world_npcs:
            return game.world_npcs[npc_id]
        if npc_id in game.notable_npcs:
            return game.notable_npcs[npc_id]
        return next((npc for sect in game.sects.values() for npc in sect.npcs if npc.id == npc_id), None)

    def _persist_relationship_npc(self, game: GameState, relation: dict[str, Any], reason: str) -> SectNpc:
        existing = self._find_npc(game, str(relation.get("id", "")))
        if existing:
            return existing
        npc = SectNpc(
            id=str(relation.get("id") or f"relation_{uuid.uuid4().hex[:12]}"),
            name=str(relation.get("name", "无名修士")), title=reason,
            realm_index=int(relation.get("realm_index", 0)), layer=int(relation.get("layer", 1)),
            age=int(relation.get("age", 18)), lifespan=relation.get("lifespan"),
            spirit_root=str(relation.get("spirit_root", "none")),
            cultivation_progress=float(relation.get("cultivation_progress", 0)),
            path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
            world=str(relation.get("world", game.player.world)), alive=bool(relation.get("alive", True)),
            death_reason=relation.get("death_reason"), affinity=float(relation.get("affinity", 0)),
            gender=str(relation.get("gender", "")),
            treasure_item_id=next(iter(relation.get("items", {})), None),
            next_tribulation_age=relation.get("next_tribulation_age"),
            tribulation_count=int(relation.get("tribulation_count", 0)),
            tribulation_power=relation.get("tribulation_power"),
        )
        game.notable_npcs[npc.id] = npc
        relation["id"] = npc.id
        relation["source"] = "world"
        return npc

    def _adjust_person_affinity(self, game: GameState, npc_id: str, delta: float) -> float:
        npc = self._find_npc(game, npc_id)
        relation = next((entry for entry in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == npc_id), None)
        base = float(relation.get("affinity", 0)) if relation else float(npc.affinity or 0) if npc else 0.0
        value = base + self._sage_affinity_gain(game.player, delta)
        if npc:
            npc.affinity = value
        for relation in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]:
            if relation and str(relation.get("id")) == npc_id:
                relation["affinity"] = value
        return value

    def _set_person_affinity(self, game: GameState, npc_id: str, value: float) -> float:
        """Set, rather than add, affinity on both the persistent NPC and relation snapshot."""
        affinity = max(-100.0, min(100.0, float(value)))
        npc = self._find_npc(game, npc_id)
        if npc:
            npc.affinity = affinity
        for relation in [
            game.player.master, game.player.dao_companion,
            *game.player.dao_friends, *game.player.disciples,
        ]:
            if relation and str(relation.get("id")) == npc_id:
                relation["affinity"] = affinity
        return affinity

    @staticmethod
    def _revenge_cooldown_key(scope: str, family: str = "", adversary_id: str = "") -> str:
        suffix = ":".join(part for part in (family, adversary_id) if part)
        return f"revenge_cooldown:{scope}" + (f":{suffix}" if suffix else "")

    def _revenge_ready(self, game: GameState, family: str, adversary_id: str) -> bool:
        """All revenge sources share one global gate and also retain per-source gates."""
        global_next = int(game.governance_actions.get(self._revenge_cooldown_key("next"), -1))
        source_next = int(game.governance_actions.get(
            self._revenge_cooldown_key("next", family, adversary_id), -1,
        ))
        return game.diplomacy_unit >= max(global_next, source_next)

    def _record_revenge_trigger(self, game: GameState, family: str, adversary_id: str) -> int:
        """Start an escalating action-unit cooldown after a revenge event is opened."""
        rules = WORLD_SYSTEMS["relationship"]
        base = max(1, int(rules.get("revenge_cooldown_base_units", 3)))
        increment = max(0, int(rules.get("revenge_cooldown_increment_units", 2)))
        maximum = max(base, int(rules.get("revenge_cooldown_max_units", 15)))
        global_count_key = self._revenge_cooldown_key("count")
        source_count_key = self._revenge_cooldown_key("count", family, adversary_id)
        global_count = int(game.governance_actions.get(global_count_key, 0)) + 1
        source_count = int(game.governance_actions.get(source_count_key, 0)) + 1
        game.governance_actions[global_count_key] = global_count
        game.governance_actions[source_count_key] = source_count
        interval = min(maximum, base + (global_count - 1) * increment)
        next_unit = game.diplomacy_unit + interval
        game.governance_actions[self._revenge_cooldown_key("next")] = next_unit
        game.governance_actions[
            self._revenge_cooldown_key("next", family, adversary_id)
        ] = next_unit
        return interval

    @staticmethod
    def _random_npc_path(faction_id: str, rng: random.Random) -> str:
        weights = FACTION_SYSTEMS["npc_path_distribution"].get(
            faction_id, {"dao": 0.55, "confucian": 0.15, "buddhist": 0.10, "demonic": 0.10, "ghost": 0.05, "monster": 0.05},
        )
        roll = rng.random()
        selected = next(reversed(weights))
        for path, weight in weights.items():
            roll -= float(weight)
            if roll <= 0:
                selected = path
                break
        return selected

    @staticmethod
    def _random_npc_root(realm_index: int, rng: random.Random) -> str:
        """人界 NPC 只生成常规五行或变异灵根，且高境界自然筛去伪灵根。"""
        distributions = FACTION_SYSTEMS["npc_root_distribution"]
        weights = distributions.get(str(min(5, max(1, realm_index))), distributions["1"])
        families = list(weights)
        roll = rng.random() * sum(float(weights[name]) for name in families)
        family = families[-1]
        for name in families:
            weight = float(weights[name])
            if weight <= 0:
                continue
            roll -= weight
            if roll <= 0:
                family = name
                break
        pools = {
            "pseudo": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("pseudo_")],
            "heavenly": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("heavenly_")],
            "supreme": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("supreme_")],
            "mutated": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("mutated_")],
        }
        return rng.choice(pools[family])

    @staticmethod
    def _npc_root_name(root_id: str) -> str:
        return ROOT_DEFINITIONS.get(root_id, {"name": "灵根未明"})["name"]

    @staticmethod
    def _npc_root_efficiency(root_id: str) -> float:
        return float(ROOT_DEFINITIONS.get(root_id, {"efficiency": 1.0})["efficiency"])

    @staticmethod
    def _mortal_root_completion_chance(player: Player) -> float:
        if player.age < 35 or not player.born_rootless or player.spirit_root != "none":
            return 0.0
        if not any(item.id.startswith("jinque_") and item.quantity > 0 for item in player.inventory):
            return 0.0
        return min(1.0, (player.age - 34) * 0.01)

    def _maybe_mortal_root_completion(self, game: GameState, rng: random.Random) -> bool:
        chance = self._mortal_root_completion_chance(game.player)
        if chance <= 0 or rng.random() >= chance:
            return False
        event = self.events_by_id["EVT_MORTAL_ROOT_COMPLETE_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["body"] += f"（本年逆天改命机率 {chance:.0%}）"
        return True

    def _maybe_probability_story_event(self, game: GameState, rng: random.Random) -> bool:
        for event in self.events:
            if "probability_gate" not in event.get("tags", []) or event["id"] == "EVT_XIANG_NODE_001":
                continue
            world_tags = {tag for tag in event.get("tags", []) if tag.startswith("world:")}
            if world_tags and f"world:{game.player.world}" not in world_tags:
                continue
            event_id = event["id"]
            if any(record.event_id == event_id for record in game.history):
                continue
            if not self._condition(event.get("conditions", {}), game):
                continue
            if self._roll_escalating_event(game, event, rng):
                return True
        return False

    def _maybe_artifact_synthesis(self, game: GameState, rng: random.Random) -> bool:
        event = self.events_by_id["EVT_FIVE_POLES_CRAFT_001"]
        if has_item(game.player, "yuanhe_five_poles_mountain"):
            return False
        if any(record.event_id == event["id"] and record.age == game.player.age for record in game.history[-2:]):
            return False
        if not self._condition(event["conditions"], game):
            return False
        game.pending_event = self._instantiate_event(event, game, rng)
        return True

    def _maybe_xiang_node_event(self, game: GameState, rng: random.Random) -> bool:
        event = self.events_by_id["EVT_XIANG_NODE_001"]
        if any(record.event_id == event["id"] for record in game.history):
            return False
        if has_item(game.player, "spirit_node_info") or not self._condition(event["conditions"], game):
            return False
        return self._roll_escalating_event(game, event, rng)

    def _roll_escalating_event(self, game: GameState, event: dict[str, Any], rng: random.Random) -> bool:
        trigger = event["trigger"]
        milestone = str(trigger["milestone"])
        game.player.milestones.setdefault(milestone, game.player.age)
        attempts = int(game.story_trigger_attempts.get(milestone, 0))
        increment = float(trigger.get("unit_increment", trigger.get("annual_increment", 0)))
        chance = min(1.0, float(trigger["base_chance"]) + attempts * increment)
        if rng.random() >= chance:
            game.story_trigger_attempts[milestone] = attempts + 1
            return False
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["body"] += f"（本行动单位触发概率 {chance:.0%}）"
        return True

    def _maybe_faction_event(self, game: GameState, rng: random.Random) -> bool:
        faction_id = game.player.faction_id
        if (
            not faction_id
            or faction_id not in game.sects
            or game.sects[faction_id].extinct
            or self._faction_meta(game, faction_id).get("world", "human") != game.player.world
            or rng.random() >= 0.30
        ):
            return False
        candidates: list[tuple[dict[str, Any], float]] = []
        for event in self.events:
            tags = event.get("tags", [])
            world_tags = [tag for tag in tags if tag.startswith("world:")]
            if (
                int(WORLD_SYSTEMS.get("world_profiles", {}).get(game.player.world, {}).get("tier", 1)) >= 3
                and f"world:{game.player.world}" not in world_tags
            ):
                continue
            if world_tags and f"world:{game.player.world}" not in world_tags:
                continue
            if "faction" not in tags or "faction_join" in tags:
                continue
            if "revenge" in tags and not self._revenge_ready(game, "faction", str(event["id"])):
                continue
            if self._intrigue_enabled() and any(
                marker in f"{event.get('title', '')}{event.get('body', '')}"
                for marker in ("争位", "夺位", "排挤", "竞争")
            ) and not self._intrigue_pressure_position_occupied(game, faction_id):
                # With the DLC, political rivals must occupy a scarce office;
                # an empty seat never invents an imaginary competitor.
                continue
            if "faction_unique" in tags and f"faction:{faction_id}" not in tags:
                continue
            if not self._condition(event.get("conditions", {}), game):
                continue
            if event.get("repeat") == "once" and any(h.event_id == event["id"] for h in game.history):
                continue
            candidates.append((event, max(0.0, float(event.get("weight", 1)))))
        total = sum(weight for _, weight in candidates)
        if total <= 0:
            return False
        roll = rng.random() * total
        for event, weight in candidates:
            roll -= weight
            if roll <= 0:
                game.pending_event = self._instantiate_event(event, game, rng)
                if "revenge" in event.get("tags", []):
                    interval = self._record_revenge_trigger(game, "faction", str(event["id"]))
                    game.pending_event.setdefault("runtime", {})["revenge_cooldown_units"] = interval
                return True
        selected = candidates[-1][0]
        game.pending_event = self._instantiate_event(selected, game, rng)
        if "revenge" in selected.get("tags", []):
            interval = self._record_revenge_trigger(game, "faction", str(selected["id"]))
            game.pending_event.setdefault("runtime", {})["revenge_cooldown_units"] = interval
        return True

    def _maybe_wanted_encounter(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        coalition_threshold = float(
            config["demonic_coalition_fame_threshold"]
            if player.path == "demonic" else config["coalition_fame_threshold"]
        )
        key = self._hostility_key("world", player.world)
        subdued_flag = f"world_coalition_subdued:{player.world}"
        if subdued_flag in player.story_flags:
            # “全界”不是会重建组织结构的实体；一旦被玩家压服，本界不能
            # 仅因威名仍高就立即重发同一份围杀令。
            player.hostility[key] = 0.0
        else:
            amnesty_fame = self._world_coalition_amnesty_fame(player, player.world)
            issue_threshold = max(coalition_threshold, amnesty_fame)
            if player.fame > issue_threshold:
                player.hostility[key] = max(
                    player.hostility.get(key, 0),
                    player.fame - issue_threshold + float(config["wanted_threshold"]),
                )
        hostiles: list[tuple[str, float]] = []
        for key, value in list(player.hostility.items()):
            if value <= float(config["wanted_threshold"]):
                continue
            player.milestones["became_wanted_target"] = 1
            state = self._hostility_entity_state(game, key)
            if state["status"] == "inactive":
                continue
            if state["status"] == "friendly":
                player.hostility[key] = 0.0
                continue
            if state["status"] == "fallen":
                self._queue_wanted_settlement(game, key, state, rng, fallen=True)
                return True
            if (
                self._player_battle_power(game) >= float(state["power"])
                or int(state["max_realm"]) <= self._actual_player_realm(player)[0]
            ):
                self._queue_wanted_settlement(game, key, state, rng, fallen=False)
                return True
            if not self._revenge_ready(game, "wanted", key):
                continue
            hostiles.append((key, value))
        if not hostiles:
            return False
        chance = min(0.92, float(config["encounter_base_chance"]) + max(value for _, value in hostiles) * float(config["encounter_hostility_scale"]))
        if rng.random() >= chance:
            return False
        key, hostility = rng.choices(hostiles, weights=[value for _, value in hostiles], k=1)[0]
        kind, entity_id = key.split(":", 1)
        target = self._wanted_target(game, kind, entity_id, hostility, rng)
        self._cache_encounter_target(game, target, rng)
        event = self.events_by_id["EVT_WANTED_ENCOUNTER_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["runtime"] = {"hostility_key": key, "hostility": hostility, "target": target}
        game.pending_event["body"] = game.pending_event["body"].replace("{pursuer}", self._hostility_name(key, game))
        if len(target.get("members", [])) > 1:
            game.pending_event["body"] += f" 此次追兵共有{len(target['members'])}人，合计战斗力约{target['target_power']:.0f}。"
        interval = self._record_revenge_trigger(game, "wanted", key)
        game.pending_event["runtime"]["revenge_cooldown_units"] = interval
        return True

    @staticmethod
    def _world_coalition_amnesty_fame(player: Player, world: str) -> float:
        prefix = f"world_coalition_amnesty:{world}:"
        values = []
        for flag in player.story_flags:
            if not flag.startswith(prefix):
                continue
            try:
                values.append(float(flag[len(prefix):]))
            except ValueError:
                continue
        return max(values, default=0.0)

    @staticmethod
    def _record_world_coalition_amnesty(player: Player, world: str) -> None:
        prefix = f"world_coalition_amnesty:{world}:"
        player.story_flags = [flag for flag in player.story_flags if not flag.startswith(prefix)]
        player.story_flags.append(f"{prefix}{max(0.0, player.fame):.1f}")

    def _player_protected_npc_ids(self, game: GameState) -> set[str]:
        player = game.player
        protected = {
            str(row.get("id")) for row in [
                player.master, player.dao_companion, *player.dao_friends,
                *player.concubines, *player.disciples,
            ] if row and row.get("id")
        }
        own_sect = game.sects.get(player.faction_id or "")
        if own_sect and not own_sect.extinct:
            protected.update(npc.id for npc in self._sect_members(game, own_sect) if npc.alive)
        if game.family and not game.family.extinct:
            protected.update(npc.id for npc in game.family.npcs if npc.alive)
        protected.update(self._retaliatory_relationship_ids(game))
        return protected

    def _hostility_entity_members(self, game: GameState, kind: str, entity_id: str) -> list[SectNpc]:
        world = game.player.world
        if kind in {"sect", "family"}:
            entity = game.sects.get(entity_id)
            if entity is None and game.family and game.family.id == entity_id:
                entity = game.family
            return [
                npc for npc in self._sect_members(game, entity)
                if npc.alive and npc.world == world
            ] if entity else []
        people = list({npc.id:npc for npc in self._all_world_npcs(game)}.values())
        if kind == "race":
            return [npc for npc in people if npc.alive and npc.world == world and npc.race == entity_id]
        if kind == "world":
            return [npc for npc in people if npc.alive and npc.world == world]
        return []

    def _hostility_entity_state(self, game: GameState, key: str) -> dict[str, Any]:
        kind, entity_id = key.split(":", 1)
        player = game.player
        if kind == "world" and entity_id != player.world:
            return {"status":"inactive"}
        if kind == "race" and (
            not self._world_supports(player.world, "races")
            or player.world not in RACE_DEFINITIONS.get(entity_id, {}).get("worlds", [])
        ):
            return {"status":"inactive"}
        entity = None
        if kind in {"sect", "family"}:
            entity = game.sects.get(entity_id)
            if entity is None and game.family and game.family.id == entity_id:
                entity = game.family
            if entity and entity.world != player.world:
                return {"status":"inactive"}
        own_entity = (
            (kind == "sect" and entity_id == player.faction_id)
            or (kind == "family" and game.family and entity_id == game.family.id)
            or (kind == "race" and entity_id == self._player_allegiance_race(player))
        )
        if own_entity:
            return {"status":"friendly"}
        raw_members = self._hostility_entity_members(game, kind, entity_id)
        if (entity and entity.extinct) or not raw_members:
            return {"status":"fallen", "kind":kind, "entity_id":entity_id, "members":[]}
        members = [npc for npc in raw_members if npc.id not in self._player_protected_npc_ids(game)]
        if not members:
            return {"status":"friendly"}
        powers = sorted((self._npc_power(npc) for npc in members), reverse=True)[:5]
        return {
            "status":"active", "kind":kind, "entity_id":entity_id, "members":members,
            "power":sum(powers), "max_realm":max(npc.realm_index for npc in members),
        }

    def _queue_wanted_settlement(
        self, game: GameState, key: str, state: dict[str, Any], rng: random.Random, *, fallen: bool,
    ) -> None:
        event_id = "EVT_POWER_FALL_001" if fallen else "EVT_WANTED_NEGOTIATION_001"
        event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        name = self._hostility_name(key, game)
        event["body"] = event["body"].replace("{pursuer}", name)
        event["runtime"] = {
            "hostility_key":key, "kind":state.get("kind", key.split(":", 1)[0]),
            "entity_id":state.get("entity_id", key.split(":", 1)[1]), "entity_name":name,
            "member_ids":[npc.id for npc in state.get("members", [])],
            "power":round(float(state.get("power", 0)), 1),
        }
        if fallen:
            titles = {"sect":"宗门的陨落", "family":"家族的陨落", "race":"种族势力的陨落", "world":"围杀令的陨落"}
            event["title"] = titles.get(event["runtime"]["kind"], "势力的陨落")
            game.player.hostility[key] = 0.0
        else:
            kind = event["runtime"]["kind"]
            own_sect = game.sects.get(game.player.faction_id or "")
            for choice in event["choices"]:
                if choice["id"] == "dissolve" and kind not in {"sect", "family"}:
                    choice["enabled"] = False
                    choice["disabled_reason"] = "种族与全界势力不能以解散宗门的方式处置"
                if choice["id"] == "sect_vassal" and (not own_sect or kind not in {"sect", "family"}):
                    choice["enabled"] = False
                    choice["disabled_reason"] = "需要拥有当前宗门，且谈判对象必须是宗门或家族"
        game.pending_event = event

    def _resolve_wanted_settlement(
        self, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random,
    ) -> tuple[str, str]:
        runtime = pending.get("runtime", {})
        key = str(runtime.get("hostility_key", ""))
        if not key or ":" not in key:
            raise ValueError("议和对象已经不存在")
        kind = str(runtime.get("kind", key.split(":", 1)[0]))
        entity_id = str(runtime.get("entity_id", key.split(":", 1)[1]))
        name = str(runtime.get("entity_name", self._hostility_name(key, game)))
        game.player.hostility[key] = 0.0
        if kind == "world":
            subdued_flag = f"world_coalition_subdued:{entity_id}"
            if subdued_flag not in game.player.story_flags:
                game.player.story_flags.append(subdued_flag)
        if mode == "fallen":
            return "pursuit_ended", f"{name}已经覆灭，针对你的追杀与通缉至此自动终止。"

        members = self._hostility_entity_members(game, kind, entity_id)
        target = max(members, key=self._npc_power, default=None)
        if mode == "compensation":
            amount = max(500, int(max(1.0, float(runtime.get("power", 1))) ** 0.5) * 80)
            add_item(game.player, "spirit_stone", amount)
            return "compensated", f"{name}交出下品灵石 ×{amount}作为巨额赔偿，并撤销全部追杀令。"
        if mode == "dissolve":
            entity = game.sects.get(entity_id)
            if entity is None and game.family and game.family.id == entity_id:
                entity = game.family
            if not entity or kind not in {"sect", "family"}:
                raise ValueError("该类势力不能就地解散")
            entity.extinct = True
            game.player.milestones["became_wanted_target"] = 1
            game.player.milestones["dissolved_wanted_power"] = 1
            self._record_former_jailer_dissolved(game.player, kind, entity_id)
            for npc in members:
                npc.faction_id = None
                game.notable_npcs.setdefault(npc.id, npc)
            return "dissolved", f"你勒令{name}撤下门庭、解散传承；幸存者各自散去，旧通缉令失效。"
        if mode in {"personal_vassal", "sect_vassal"}:
            own_sect = game.sects.get(game.player.faction_id or "")
            if mode == "sect_vassal" and (not own_sect or kind not in {"sect", "family"}):
                raise ValueError("当前条件无法将对方纳为本宗附庸")
            if mode == "sect_vassal" and own_sect:
                relation = game.sect_relations.setdefault(
                    race_pair(own_sect.id, entity_id), {"affinity":0.0, "since_age":game.player.age},
                )
                relation.update(status="vassal", affinity=70.0, since_age=game.player.age,
                                overlord=own_sect.id, subject=entity_id)
                return "sect_vassal", f"{name}交出外交与征召权，成为{own_sect.name}的附庸。"
            flag = f"personal_vassal:{kind}:{entity_id}"
            if flag not in game.player.story_flags:
                game.player.story_flags.append(flag)
            return "personal_vassal", f"{name}向你本人奉上臣服契约，承诺不再追杀并听候你的号令。"
        if mode == "hostages":
            amount = max(200, int(max(1.0, float(runtime.get("power", 1))) ** 0.5) * 35)
            add_item(game.player, "spirit_stone", amount)
            if target:
                game.player.prisoners.append({
                    "id":target.id, "npc_id":target.id, "name":target.name,
                    "realm_index":target.realm_index, "layer":target.layer,
                    "realm_name":self._npc_realm_name(target), "path":target.path,
                    "path_name":PATH_NAMES.get(target.path, target.path), "race":target.race,
                    "affinity":-80.0, "combat_power":round(self._npc_power(target), 1),
                    "main_technique_id":self._default_npc_main_technique(target),
                    "captured_age":game.player.age, "source":f"settlement:{kind}",
                })
                target.alive = False
                target.death_reason = f"被{game.player.name}扣作议和人质"
                return "hostages", f"{name}交出灵石 ×{amount}，并将最强者{target.name}交给你作为人质。"
            return "hostages", f"{name}已无强者可交，只得献上灵石 ×{amount}并永远撤销追杀。"
        raise ValueError("未知议和条件")

    def _personal_npcs(self, game: GameState) -> list[SectNpc]:
        return list({
            npc.id:npc for npc in self._all_world_npcs(game)
            if npc.alive and npc.world == game.player.world and npc.id != "player"
        }.values())

    def _high_affinity_npcs(self, game: GameState, exclude_id: str = "") -> list[SectNpc]:
        threshold = float(WORLD_SYSTEMS["relationship"]["positive_affinity_threshold"])
        people = [npc for npc in self._personal_npcs(game) if npc.id != exclude_id and float(npc.affinity or 0) >= threshold]
        known = {npc.id for npc in people}
        for relation in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]:
            if not relation or str(relation.get("id")) in known or str(relation.get("id")) == exclude_id:
                continue
            if relation.get("alive", True) and relation.get("world") == game.player.world and float(relation.get("affinity", 0)) >= threshold:
                people.append(self._persist_relationship_npc(game, relation, "交好修士"))
        return people

    def _maybe_affinity_gift(self, game: GameState, rng: random.Random) -> bool:
        people = self._high_affinity_npcs(game)
        if not people:
            return False
        rules = WORLD_SYSTEMS["relationship"]
        chance = min(0.32, float(rules["positive_event_base_chance"]) + len(people) * float(rules["positive_event_per_person"]))
        if rng.random() >= chance:
            return False
        npc = rng.choices(people, weights=[max(1.0,float(person.affinity or 0)) for person in people], k=1)[0]
        event = self.events_by_id["EVT_PERSONAL_AFFINITY_GIFT_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        game.pending_event["runtime"] = {"npc_id":npc.id,"npc_name":npc.name,"npc_realm_index":npc.realm_index}
        game.pending_event["body"] = game.pending_event["body"].replace("{npc_name}",npc.name)
        return True

    def _maybe_personal_revenge(self, game: GameState, rng: random.Random) -> bool:
        rules = WORLD_SYSTEMS["relationship"]
        threshold = float(rules["hostile_affinity_threshold"])
        protected_ids = self._retaliatory_relationship_ids(game)
        enemies = [
            npc for npc in self._personal_npcs(game)
            if float(npc.affinity or 0) <= threshold and npc.id not in protected_ids
            and self._revenge_ready(game, "personal", npc.id)
        ]
        enemies = self._filter_personal_revenge_by_protection(game, enemies, rng)
        if not enemies:
            return False
        allies = self._high_affinity_npcs(game)
        protection = min(float(rules["ally_protection_cap"]), len(allies) * float(rules["ally_protection_per_person"]))
        severity = max(abs(float(npc.affinity or 0) - threshold) for npc in enemies)
        chance = min(0.75, float(rules["revenge_base_chance"]) + severity * float(rules["revenge_affinity_scale"])) * (1 - protection)
        if rng.random() >= chance:
            return False
        enemy = rng.choices(enemies, weights=[max(1.0,abs(float(npc.affinity or 0))) for npc in enemies], k=1)[0]
        race_definition = RACE_DEFINITIONS.get(enemy.race,RACE_DEFINITIONS["human"])
        target = {
            "target_name":enemy.name,"target_power":self._npc_power(enemy),"primary_power":self._npc_power(enemy),
            "target_realm_index":enemy.realm_index,"target_layer":enemy.layer,
            "target_realm_visible":enemy.realm_index <= game.player.realm_index + 1,
            "target_realm_display":self._npc_realm_name(enemy) if enemy.realm_index <= game.player.realm_index + 1 else "无法看清",
            "combat_type":"cultivator","race":enemy.race,"race_name":race_definition["name"],
            "race_description":race_definition["description"],"world":enemy.world,"npc_id":enemy.id,
            "faction_id":self._npc_faction_id(game,enemy.id),"treasure_item_id":enemy.treasure_item_id,
            "kill_karma":False,"action":"revenge",
        }
        event = self.events_by_id["EVT_PERSONAL_REVENGE_001"]
        game.pending_event = self._instantiate_event(event, game, rng)
        best_ally = max((npc for npc in allies if npc.id != enemy.id),key=self._npc_power,default=None)
        sect = game.sects.get(game.player.faction_id or "")
        sect_defenders = [npc for npc in self._sect_members(game,sect) if npc.alive and npc.id != enemy.id] if sect else []
        game.pending_event["runtime"] = {
            "target":target,"npc_id":enemy.id,
            "ally_id":best_ally.id if best_ally else None,"ally_name":best_ally.name if best_ally else None,
            "sect_support_power":max((self._npc_power(npc) for npc in sect_defenders),default=0.0),
            "chance":round(chance,3),"protection":round(protection,3),
        }
        game.pending_event["body"] = game.pending_event["body"].replace("{npc_name}",enemy.name).replace("{target_power}",f"{target['target_power']:.0f}")
        for choice in game.pending_event["choices"]:
            if choice["id"] == "ally":
                choice["enabled"] = best_ally is not None
                if best_ally is None: choice["disabled_reason"] = "当前没有愿意驰援的高好感修士"
                else: choice["text"] += f"（{best_ally.name}）"
            elif choice["id"] == "sect":
                choice["enabled"] = bool(sect_defenders)
                if not sect_defenders: choice["disabled_reason"] = "当前没有可接应你的宗门同道"
        interval = self._record_revenge_trigger(game, "personal", enemy.id)
        game.pending_event["runtime"]["revenge_cooldown_units"] = interval
        return True

    def _wanted_target(
        self, game: GameState, kind: str, entity_id: str, hostility: float, rng: random.Random,
    ) -> dict[str, Any]:
        player = game.player
        desired_realm = min(8, player.realm_index + max(0, int(hostility // 45)))
        candidates = [
            npc for npc in self._hostility_entity_members(game, kind, entity_id)
            if npc.id not in self._player_protected_npc_ids(game) and npc.realm_index >= player.realm_index
        ]
        if candidates:
            candidates.sort(key=lambda npc: (abs(npc.realm_index - desired_realm), -npc.realm_index, -npc.layer))
            npc = candidates[0]
            race_def = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
            target = {
                "target_name": npc.name, "target_power": self._npc_power(npc), "primary_power": self._npc_power(npc),
                "target_realm_index": npc.realm_index, "target_layer": npc.layer,
                "target_realm_visible": npc.realm_index <= player.realm_index + 1,
                "target_realm_display": self._npc_realm_name(npc) if npc.realm_index <= player.realm_index + 1 else "无法看清",
                "combat_type": "cultivator", "race": npc.race, "race_name": race_def["name"],
                "race_description": race_def["description"], "world": player.world,
                "npc_id": npc.id, "faction_id": self._npc_faction_id(game, npc.id),
                "treasure_item_id": npc.treasure_item_id, "path":npc.path,
            }
            return self._add_enemy_party(target, ACTIONS["slay"]["combat"], rng)
        race_id = entity_id if kind == "race" and entity_id in RACE_DEFINITIONS else "human"
        settings = dict(ACTIONS["slay"]["combat"])
        offset = desired_realm - player.realm_index
        settings["realm_offsets"] = [[offset, 1.0]]
        target = self._generate_cultivator_target(player, "追缉使", settings, rng, game=game, forced_race=race_id)
        target["race"] = race_id
        target["race_name"] = RACE_DEFINITIONS[race_id]["name"]
        target["race_description"] = RACE_DEFINITIONS[race_id]["description"]
        target["faction_id"] = entity_id if kind in {"sect", "family"} else None
        for member in target.get("members", []):
            member["race"] = race_id
            member["faction_id"] = target.get("faction_id")
        return target

    def _resolve_wanted_response(
        self, game: GameState, pending: dict[str, Any], response: str, rng: random.Random,
    ) -> tuple[str, str]:
        runtime = pending.get("runtime", {})
        key = str(runtime.get("hostility_key", "world:unknown"))
        target = runtime.get("target") or {}
        config = WORLD_SYSTEMS["faction_conflict"]
        if response == "fight":
            target["kill_karma"] = True
            target["non_story_combat"] = True
            result, summary = self._combat(game, target, True, rng)
            game.player.hostility[key] = game.player.hostility.get(key, 0) + float(config["fight_hostility_gain"])
            if result == "defeat" and game.player.alive:
                custody = self._imprison_or_execute(game, key, rng)
                summary += " " + custody
            return result, summary
        if response == "surrender":
            return "surrendered", self._imprison_or_execute(game, key, rng, surrendered=True)
        if response == "escape":
            own_power = self._player_battle_power(game)
            chance = max(0.08, min(0.8, 0.22 + own_power / max(1.0, float(target.get("target_power", own_power))) * 0.25))
            game.player.hostility[key] = game.player.hostility.get(key, 0) + float(config["escape_hostility_gain"])
            if rng.random() < chance:
                return "escaped", f"你付出代价甩脱追兵（成功率 {chance:.0%}），敌对值却进一步上升。"
            return "captured", f"突围失败（成功率 {chance:.0%}）。" + self._imprison_or_execute(game, key, rng)
        raise ValueError("未知通缉应对方式")

    def _imprison_or_execute(
        self, game: GameState, key: str, rng: random.Random, surrendered: bool = False,
    ) -> str:
        player = game.player
        config = WORLD_SYSTEMS["faction_conflict"]
        hostility = player.hostility.get(key, 0)
        execution_threshold = float(config["execution_threshold"])
        execution_chance = 0.0 if hostility < execution_threshold else min(0.9, 0.35 + (hostility - execution_threshold) / 100)
        if not surrendered:
            execution_chance = min(0.95, execution_chance + 0.12)
        if rng.random() < execution_chance:
            self._die(game, f"落入{self._hostility_name(key, game)}之手，被当场处决", "SYS_WANTED_EXECUTION")
            return f"敌对值 {hostility:.0f}，对方拒绝收押，将你当场处决。"
        low, high = config["prison_years"]
        years = rng.randint(int(low), int(high)) + min(8, int(hostility // 35))
        player.imprisonment = {
            "key": key, "name": self._hostility_name(key, game), "remaining_years": years,
            "captured_age": player.age, "hostility": round(hostility, 1),
            "sentence_years": years,
            "hostility_reduction_per_year": max(4.0, hostility / max(1, years)),
        }
        self._intrigue_record_player_prison(game, key, years)
        player.party = []
        return f"你被押入{self._hostility_name(key, game)}大牢，刑期 {years} 年。"

    def _hostility_name(self, key: str, game: GameState | None = None) -> str:
        kind, entity_id = key.split(":", 1)
        if kind in {"sect", "family"}:
            if game and entity_id in game.sects:
                return game.sects[entity_id].name
            if game and game.family and entity_id == game.family.id:
                return game.family.name
            return FACTION_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
        if kind == "race":
            return RACE_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
        return WORLD_SYSTEMS["world_names"].get(entity_id, entity_id) + "修仙界"

    def _try_conceive_child(self, game: GameState, rng: random.Random) -> str:
        player = game.player
        companion = player.dao_companion
        if not companion or not companion.get("alive", True):
            return ""
        player_realm, _ = self._actual_player_realm(player)
        # 生育难度取双方较高的生命层次；任一方达到化神，概率即归零。
        realm_index = max(player_realm, int(companion.get("realm_index", player_realm)))
        family_rules = WORLD_SYSTEMS["family"]
        natural_chance = float(family_rules["conception_chance_by_realm"].get(str(realm_index), 0.0))
        medicine_bonus = max(0.0, float(player.next_companion_conception_bonus))
        chance = min(0.95, natural_chance + medicine_bonus)
        # 药力只绑定一次有效的缠绵互动；即使本次未能诞下后代也会消耗。
        player.next_companion_conception_bonus = 0.0
        if chance <= 0 or rng.random() >= chance:
            if chance > 0:
                source = f"（自然 {natural_chance:.1%} + 丹药 {medicine_bonus:.1%}）" if medicine_bonus else ""
                return f" 本次孕育后代概率 {chance:.1%}{source}，未有血脉诞生。"
            return " 化神以后生命层次过高，已无法自然孕育后代；可借孕育丹药暂时提高下一次概率。"
        player_innate = player.spirit_root != "none" and not player.acquired_root
        companion_root = str(companion.get("spirit_root", "none"))
        companion_innate = companion_root != "none" and not companion.get("acquired_root", False)
        has_root = player_innate and companion_innate and rng.random() < float(family_rules["spirit_root_inheritance_chance"])
        child_root = rng.choice([player.spirit_root, companion_root]) if has_root else "none"
        surn = player.name[:1] if player.name else "韩"
        child = {
            "id":f"child_{game.id.replace('-', '')[:8]}_{len(player.offspring)}", "name":surn + rng.choice(["宁","安","澄","昭","遥","真","元","清"]),
            "age":0, "alive":True, "world":player.world, "spirit_root":child_root,
            "spirit_root_name":self._npc_root_name(child_root), "cultivation_started":False,
            "realm_index":0, "layer":1, "path":player.technique.path if player.technique else player.path,
            "lifespan":rng.randint(80, 100), "parents":[player.name, str(companion.get("name", "道侣"))],
            "gender":rng.choice(["male", "female"]),
        }
        lineage_text = ""
        inheritance = MONSTER_BLOODLINE_SETTINGS.get("inheritance", {})
        if player.path == "monster" and bloodline_content_available() and rng.random() < float(inheritance.get("species_chance", 1.0)):
            species = MONSTER_SPECIES.get(str(player.monster_species_id or ""), {})
            base_evolution_id = species.get("base_evolution_id")
            child.update(
                path="monster", monster_species_id=player.monster_species_id,
                monster_evolution_id=base_evolution_id,
                monster_evolution_history=[base_evolution_id] if base_evolution_id else [],
                monster_bloodline_imprints=[
                    imprint for imprint in player.monster_bloodline_imprints
                    if rng.random() < float(inheritance.get("imprint_chance", 0.45))
                ],
                monster_lineage_origin=player.monster_evolution_id,
            )
            child["lifespan"] *= int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))
            lineage_text = f"并继承了{species.get('name', '妖族')}本源血脉"
            lineage_candidates: list[dict[str, Any]] = []
            for parent in (player.to_dict(), companion):
                lineage = parent.get("monster_custom_lineage")
                lineage_id = parent.get("monster_custom_lineage_id") or (
                    lineage.get("id") if isinstance(lineage, dict) else None
                )
                if not isinstance(lineage, dict) or not lineage_id or not isinstance(lineage.get("rules"), list):
                    continue
                if any(row["id"] == str(lineage_id) for row in lineage_candidates):
                    continue
                lineage_candidates.append({"id": str(lineage_id), "lineage": lineage})
            if lineage_candidates:
                inherited = rng.choice(lineage_candidates)
                child["monster_custom_lineage_id"] = inherited["id"]
                child["monster_custom_lineage"] = copy.deepcopy(inherited["lineage"])
                child["monster_custom_lineage"]["id"] = inherited["id"]
                lineage_text += f"，并承袭了祖血【{child['monster_custom_lineage'].get('name', inherited['id'])}】的定型规则"
        player.offspring.append(child)
        player.children += 1
        return f" 你们诞下一名后代{child['name']}；其{'身具' + child['spirit_root_name'] if has_root else '没有显现灵根'}{lineage_text}。"

    def _annual_offspring_and_family_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        player = game.player
        family_ids = {npc.id for npc in game.family.npcs} if game.family else set()
        for child in player.offspring:
            if not child.get("alive", True) or child.get("id") in family_ids:
                continue
            child["age"] = int(child.get("age", 0)) + 1
            if child.get("lifespan") is not None and child["age"] >= int(child["lifespan"]):
                child["alive"] = False
                child["death_reason"] = "寿元耗尽"
                summary = f"后代{child['name']}寿元耗尽，安然辞世。"
                if child.get("world", player.world) == player.world:
                    news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_CHILD_FALL",1,player.age,"血脉凋零",child["id"],"child_fallen",summary,
                    {"child_id":child["id"],"alive":[True,False]},
                    ["system","family","offspring","world_news",f"world:{child.get('world',player.world)}"],
                ))
                continue
            if child.get("spirit_root", "none") != "none" and not child.get("cultivation_started") and child["age"] >= int(WORLD_SYSTEMS["family"]["cultivation_start_age"]):
                child.update(cultivation_started=True, realm_index=1, layer=1, lifespan=rng.randint(100, 120))
                summary = f"后代{child['name']}在{child['age']}岁正式引气入体，踏入练气一层。"
                news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_CHILD_CULTIVATION",1,player.age,"血脉问道",child["id"],"cultivator",summary,
                    {"child_id":child["id"],"realm_index":1},["system","family","offspring",f"world:{child.get('world',player.world)}"],
                ))
            if child.get("cultivation_started"):
                descendant = SectNpc(
                    str(child["id"]), str(child["name"]), "后代",
                    int(child.get("realm_index", 1)), int(child.get("layer", 1)),
                    int(child["age"]), child.get("lifespan"),
                    spirit_root=str(child.get("spirit_root", "none")),
                    cultivation_progress=float(child.get("cultivation_progress", 0)),
                    path=str(child.get("path", player.path)), race=player.race,
                    world=str(child.get("world", player.world)),
                    gender=str(child.get("gender") or self._stable_gender(str(child.get("id", "")))),
                    next_tribulation_age=child.get("next_tribulation_age"),
                    tribulation_count=int(child.get("tribulation_count", 0)),
                    tribulation_power=child.get("tribulation_power"),
                )
                tribulation = self._resolve_npc_periodic_tribulation(game, descendant, rng, "后代")
                result = None if not descendant.alive else self._advance_npc_cultivation(descendant, rng)
                child.update(
                    age=descendant.age, alive=descendant.alive, realm_index=descendant.realm_index,
                    layer=descendant.layer, lifespan=descendant.lifespan, world=descendant.world,
                    cultivation_progress=descendant.cultivation_progress,
                    next_tribulation_age=descendant.next_tribulation_age,
                    tribulation_count=descendant.tribulation_count,
                    tribulation_power=descendant.tribulation_power,
                    death_reason=descendant.death_reason,
                )
                if tribulation and child.get("world") == player.world:
                    news.append(f"{player.age}岁：{tribulation}")
                if result:
                    summary = f"后代{child['name']}由{result['old']}突破至{result['new']}。"
                    if child.get("world") == player.world:
                        news.append(f"{player.age}岁：{summary}")
                    game.history.append(HistoryRecord(
                        "SYS_CHILD_BREAKTHROUGH",1,player.age,"后辈破境",child["id"],result["type"],summary,
                        {"child_id":child["id"],"realm":[result["old"],result["new"]]},
                        ["system","family","offspring","world_news",f"world:{child.get('world',player.world)}"],
                    ))
        family = game.family
        if not family or family.extinct:
            return news
        for npc in family.npcs:
            if not npc.alive:
                continue
            child = next((row for row in player.offspring if row.get("id") == npc.id), None)
            npc.age += 1
            tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, family.name)
            if tribulation and family.world == player.world:
                news.append(f"{player.age}岁：{tribulation}")
            if not npc.alive:
                if child:
                    child.update(age=npc.age,alive=False,death_reason=npc.death_reason)
                continue
            if npc.lifespan is not None and npc.age >= npc.lifespan:
                npc.alive = False
                npc.death_reason = "寿元耗尽，族谱除名"
                if child:
                    child.update(age=npc.age,alive=False,death_reason=npc.death_reason)
                summary = f"{family.name}{npc.title}{npc.name}寿尽坐化。"
                news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_FAMILY_MEMBER_FALL",1,player.age,"家族讣告",npc.id,"npc_fallen",summary,
                    {"npc_id":npc.id},["system","family","npc","world_news",f"world:{family.world}"],
                ))
                continue
            result = self._advance_npc_cultivation(npc, rng)
            if child:
                child.update(
                    age=npc.age,alive=npc.alive,realm_index=npc.realm_index,layer=npc.layer,
                    lifespan=npc.lifespan,world=npc.world,cultivation_progress=npc.cultivation_progress,
                    next_tribulation_age=npc.next_tribulation_age,tribulation_count=npc.tribulation_count,
                    tribulation_power=npc.tribulation_power,death_reason=npc.death_reason,
                )
            if result:
                summary = f"{family.name}{npc.title}{npc.name}由{result['old']}突破至{result['new']}。"
                if family.world == player.world:
                    news.append(f"{player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_FAMILY_MEMBER_BREAKTHROUGH",1,player.age,"家族喜报",npc.id,result["type"],summary,
                    {"npc_id":npc.id,"realm":[result["old"],result["new"]]},
                    ["system","family","npc","world_news",f"world:{family.world}"],
                ))
        if not any(npc.alive for npc in family.npcs):
            family.extinct = True
            game.history.append(HistoryRecord(
                "SYS_FAMILY_EXTINCT",1,player.age,"家族断绝",family.id,"extinct",
                f"{family.name}最后一名在册修士陨落，修仙家族传承断绝。",
                {"family_id":family.id,"extinct":True},
                ["system","family","extinction","world_news",f"world:{family.world}"],
            ))
            return news
        family_rules = WORLD_SYSTEMS["family"]
        if (
            player.age % int(family_rules["recruitment_interval_years"]) == 0
            and len([npc for npc in family.npcs if npc.alive]) < int(family_rules["max_members"])
        ):
            newcomer = self._recruit_sect_npc(family, player.age, rng)
            newcomer.title = "外姓门人"
            summary = f"低阶散修{newcomer.name}请求依附{family.name}，列入外门。"
            game.history.append(HistoryRecord(
                "SYS_FAMILY_RECRUIT",1,player.age,"家族收录外姓",newcomer.id,"npc_joined",summary,
                {"npc_id":newcomer.id},["system","family","recruitment",f"world:{family.world}"],
            ))
        return news

    def _check_sect_extinction(self, game: GameState, sect: SectState) -> bool:
        if sect.extinct or any(npc.alive and npc.world == sect.world for npc in self._sect_members(game, sect)):
            return False
        sect.extinct = True
        summary = f"{sect.name}最后一盏 NPC 魂灯熄灭，传承断绝，宗门正式灭亡。"
        if game.player.faction_id == sect.id:
            game.player.faction_id = None
            game.player.faction_join_age = None
            game.player.faction_contribution = 0
            game.player.faction_reward_preference = None
        game.history.append(HistoryRecord(
            "SYS_SECT_EXTINCT",1,game.player.age,"宗门灭亡",sect.id,"extinct",summary,
            {"sect_id":sect.id,"extinct":True},["system","faction","extinction","world_news",f"world:{sect.world}"],
        ))
        return True

    def _dissolve_player_sect(self, game: GameState, sect: SectState, reason: str) -> None:
        """Disband a weak player sect without falsely killing every former member."""
        sect.extinct = True
        for npc in self._sect_members(game, sect):
            if npc.alive:
                npc.faction_id = None
                game.notable_npcs.setdefault(npc.id, npc)
        if game.player.faction_id == sect.id:
            game.player.faction_id = None
            game.player.faction_join_age = None
            game.player.faction_contribution = 0
            game.player.faction_reward_preference = None
        game.history.append(HistoryRecord(
            "SYS_PLAYER_SECT_DISSOLVED",1,game.player.age,"山门解散",sect.id,"dissolved",
            f"{sect.name}因{reason}而解散；幸存门人散入天下，并未凭空陨落。",
            {"sect_id":sect.id,"pressure":sect.pressure},
            ["system","faction","player_faction","extinction","world_news",f"world:{sect.world}"],
        ))

    def _maybe_founded_sect_pressure(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        sect = game.sects.get(player.faction_id or "")
        if not sect or sect.extinct or not sect.founded_by_player or sect.world != player.world:
            return False
        actual_realm, _ = self._actual_player_realm(player)
        governance_threshold = self._governance_threshold(player.world)
        qualified_members = [
            npc for npc in self._sect_members(game, sect)
            if npc.alive and npc.world == sect.world and npc.realm_index >= governance_threshold
        ]
        if actual_realm >= governance_threshold or qualified_members:
            # 排挤针对的是“无人坐镇”的弱小山门。只要玩家或任一正式门人
            # 达到本界治理门槛，旧的守山失败记录也应立即失效。
            sect.pressure = 0
            return False
        faction_rules = WORLD_SYSTEMS["player_faction"]
        if rng.random() >= float(faction_rules["pressure_chance_per_unit"]):
            return False
        event_id = f"EVT_PLAYER_SECT_DEFENSE_{min(3, sect.pressure + 1):03d}"
        game.pending_event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        threshold_realm = governance_threshold
        required_power = expected_combat_power(threshold_realm, 1) * (0.58 + sect.pressure * 0.12)
        game.pending_event["runtime"] = {
            "sect_id":sect.id, "required_power":round(required_power, 1),
            "failure_number":sect.pressure + 1,
        }
        game.pending_event["_history_tags"] = [
            tag for tag in self.events_by_id[event_id].get("tags", []) if not tag.startswith("world:")
        ] + [f"world:{player.world}"]
        game.pending_event["body"] += f"（正面守山建议战力 {required_power:.0f}；此前护山失败 {sect.pressure}/3 次。）"
        return True

    def _advance_player_bounties(self, game: GameState, rng: random.Random) -> None:
        active = [row for row in game.player_bounties if row.get("status") == "active" and row.get("world") == game.player.world]
        if not active:
            return
        bounty = active[0]
        bounty["attempts"] = int(bounty.get("attempts", 0)) + 1
        npc = self._find_npc(game, str(bounty.get("target_id", "")))
        if not npc or not npc.alive:
            bounty["status"] = "closed"
            return
        authority = str(bounty.get("authority", ""))
        available = {row["id"]:row for row in self._available_bounty_authorities(game)}
        if authority not in available:
            bounty["status"] = "suspended"
            return
        if authority == "race":
            allegiance_race = self._player_allegiance_race(game.player)
            members = [
                member for member in [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]
                if member.alive and member.world == game.player.world and member.race == allegiance_race
            ]
        elif authority == "sect":
            sect = game.sects.get(game.player.faction_id or "")
            members = [member for member in sect.npcs if member.alive] if sect else []
        else:
            members = [member for member in game.family.npcs if member.alive] if game.family else []
        # 同一 NPC 可能同时出现在宗门与世界人物集合中，只允许出战一次；
        # 发布者本人不自动参战，通缉令依靠玩家实际掌握的同僚执行。
        unique_members = {
            member.id: member for member in members
            if member.id != npc.id and member.alive and member.world == game.player.world
        }
        candidates = sorted(unique_members.values(), key=self._npc_power, reverse=True)
        if not candidates:
            game.history.append(HistoryRecord(
                "SYS_PLAYER_BOUNTY_NO_HUNTERS",1,game.player.age,"通缉无人可遣",npc.id,"delayed",
                f"{bounty.get('issuer_name','麾下势力')}暂时没有可跨界执行追杀的弟子或同僚，通缉令仍然有效。",
                {"bounty_id":bounty["id"],"attempts":bounty["attempts"]},["system","wanted","player_order",f"world:{npc.world}"],
            ))
            return

        # 每个行动单位派出一至三人。优先从最强的五人中抽调，兼顾势力会认真
        # 执行命令与同一位高层不会机械地永远出战两种表现。
        pool = candidates[: min(5, len(candidates))]
        team_size = min(len(pool), rng.randint(1, 3))
        hunters = rng.sample(pool, team_size)
        hunter_powers = {member.id: self._npc_power(member) for member in hunters}
        pursuit_power = npc_team_combat_power(hunter_powers.values())
        target_power = max(1.0, self._npc_power(npc))
        ratio = pursuit_power / target_power
        victory_chance = max(0.06, min(0.94, 0.18 + ratio * 0.34))
        hunter_names = "、".join(member.name for member in hunters)

        if rng.random() < victory_chance:
            target_threshold = float(REALMS[npc.realm_index].kill_threshold)
            can_kill = ratio >= target_threshold
            killed = can_kill and rng.random() < min(0.92, 0.55 + (ratio - target_threshold) * 0.12)
            if killed:
                npc.alive = False
                npc.death_reason = f"被{bounty.get('issuer_name','麾下势力')}通缉后伏诛"
                bounty["status"] = "completed"
                bounty["completed_age"] = game.player.age
                reward_text = "其身上并无可入眼的重宝"
                if npc.treasure_item_id and not npc.treasure_looted:
                    add_item(game.player, npc.treasure_item_id)
                    npc.treasure_looted = True
                    reward_text = f"其重宝《{ITEM_CATALOG[npc.treasure_item_id].name}》已交由你接收"
                for candidate_sect in game.sects.values():
                    if any(member.id == npc.id for member in candidate_sect.npcs):
                        self._check_sect_extinction(game, candidate_sect)
                game.history.append(HistoryRecord(
                    "SYS_PLAYER_BOUNTY_COMPLETE",1,game.player.age,"通缉伏诛",npc.id,"completed",
                    f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}），围杀{npc.name}（战力 {target_power:.0f}）；{reward_text}。",
                    {"bounty_id":bounty["id"],"target_id":npc.id,"hunter_ids":[row.id for row in hunters],"pursuit_power":pursuit_power,"target_power":target_power},
                    ["system","wanted","player_order",f"world:{npc.world}"],
                ))
                return
            npc.wounds = min(4, npc.wounds + (2 if ratio >= 1 else 1))
            for hunter in hunters:
                if ratio < 1.6 and rng.random() < 0.30:
                    hunter.wounds = min(4, hunter.wounds + 1)
            game.history.append(HistoryRecord(
                "SYS_PLAYER_BOUNTY_TARGET_WOUNDED",1,game.player.age,"通缉重创",npc.id,"target_wounded",
                f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}）重创了{npc.name}（战力 {target_power:.0f}），但未满足击杀条件；通缉令继续执行。",
                {"bounty_id":bounty["id"],"hunter_ids":[row.id for row in hunters],"target_wounds":npc.wounds},
                ["system","wanted","player_order",f"world:{npc.world}"],
            ))
            return

        outcomes: list[str] = []
        for hunter in hunters:
            hunter_power = max(1.0, hunter_powers[hunter.id])
            counter_ratio = target_power / hunter_power
            kill_threshold = float(REALMS[hunter.realm_index].kill_threshold)
            if counter_ratio >= kill_threshold and rng.random() < 0.55:
                hunter.alive = False
                hunter.death_reason = f"执行对{npc.name}的通缉令时反遭灭杀"
                outcomes.append(f"{hunter.name}阵亡")
                for candidate_sect in game.sects.values():
                    if any(member.id == hunter.id for member in candidate_sect.npcs):
                        self._check_sect_extinction(game, candidate_sect)
            elif rng.random() < min(0.85, 0.38 + max(0.0, counter_ratio - 1) * 0.18):
                hunter.wounds = min(4, hunter.wounds + 2)
                outcomes.append(f"{hunter.name}重伤遁回")
            else:
                outcomes.append(f"{hunter.name}及时脱身")
        if ratio >= 0.65:
            npc.wounds = min(4, npc.wounds + 1)
        game.history.append(HistoryRecord(
            "SYS_PLAYER_BOUNTY_COUNTERED",1,game.player.age,"通缉反噬",npc.id,"hunters_defeated",
            f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}）截住{npc.name}（战力 {target_power:.0f}），却被对方击退：{'、'.join(outcomes)}。通缉令仍然有效。",
            {"bounty_id":bounty["id"],"hunter_ids":[row.id for row in hunters],"outcomes":outcomes},
            ["system","wanted","player_order",f"world:{npc.world}"],
        ))

    def _annual_sect_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        player = game.player
        living_spirit_npcs = sum(
            npc.alive and npc.world == "human" and npc.realm_index == 5
            for sect in game.sects.values()
            for npc in sect.npcs
        ) + sum(npc.alive and npc.world == "human" and npc.realm_index == 5 for npc in game.world_npcs.values())
        for sect_id, sect in game.sects.items():
            if sect.extinct:
                continue
            for npc in sect.npcs:
                if not npc.alive or npc.world != sect.world:
                    continue
                npc.age += 1
                if self._intrigue_is_imprisoned(game, npc.id):
                    if npc.lifespan is not None and npc.age >= npc.lifespan:
                        npc.alive = False
                        npc.death_reason = "服刑期间寿元耗尽"
                    continue
                if npc.wounds > 0 and rng.random() < 0.35:
                    npc.wounds -= 1
                tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, sect.name)
                if tribulation:
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{tribulation}")
                    if not npc.alive:
                        continue
                death_reason: str | None = None
                if npc.lifespan is not None and npc.age >= npc.lifespan:
                    death_reason = "寿元耗尽，坐化于宗门祖庭"
                elif rng.random() < float(FACTION_SYSTEMS["npc_cultivation"]["accident_death_chance"]):
                    death_reason = rng.choice(["外出历练时失踪，魂灯熄灭", "冲关失败，道消身殒", 
                                               "遭逢旧敌伏杀，未能归山", "秘境陨落，身死道消", 
                                               "遭遇魔道，元神不测", "走火入魔，爆体而亡"])
                if death_reason:
                    npc.alive = False
                    npc.death_reason = death_reason
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{sect.name}{npc.name}{death_reason}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_NPC_FALL", 1, player.age, "宗门讣告", None, "npc_fallen",
                        f"{sect.name}{npc.title}{npc.name}{death_reason}。",
                        {"npc_id": npc.id, "alive": [True, False]},
                        ["system", "faction", "npc", "world_news", f"world:{sect.world}"],
                    ))
                    continue
                crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
                can_cross = not crossing_to_spirit or living_spirit_npcs < 1
                old_title = self._dynamic_sect_title(npc, sect)
                breakthrough = self._advance_npc_cultivation(npc, rng, can_cross)
                if breakthrough:
                    old_name, new_name = breakthrough["old"], breakthrough["new"]
                    new_title = self._dynamic_sect_title(npc, sect)
                    title_change = f"，职衔由{old_title}晋为{new_title}" if new_title != old_title else ""
                    if breakthrough["type"] == "breakthrough" and npc.world == "human" and npc.realm_index == 5:
                        living_spirit_npcs += 1
                    if breakthrough["type"] == "departure":
                        living_spirit_npcs = max(0, living_spirit_npcs - 1)
                        if sect.world == player.world:
                            news.append(f"{player.age}岁：{sect.name}{npc.name}{new_name}，人界魂灯熄灭")
                    else:
                        if sect.world == player.world:
                            news.append(f"{player.age}岁：{sect.name}{npc.name}由{old_name}突破至{new_name}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_NPC_DEPART" if breakthrough["type"] == "departure" else "SYS_SECT_NPC_BREAKTHROUGH",
                        1, player.age, "宗门魂灯" if breakthrough["type"] == "departure" else "宗门喜报", None,
                        "npc_departed" if breakthrough["type"] == "departure" else "npc_breakthrough",
                        f"{sect.name}{old_title}{npc.name}{new_name}。" if breakthrough["type"] == "departure" else f"{sect.name}{old_title}{npc.name}由{old_name}突破至{new_name}{title_change}。",
                        {"npc_id": npc.id, "realm": [old_name, new_name]},
                        ["system", "faction", "npc", "world_news", f"world:{sect.world}"],
                    ))
            if self._check_sect_extinction(game, sect):
                continue
            self._compact_sect_roster(game, sect)
            if (
                player.age % int(FACTION_SYSTEMS["recruitment_interval_years"]) == 0
                and len([npc for npc in self._sect_members(game, sect) if npc.alive])
                < int(FACTION_SYSTEMS.get("max_members", 36))
            ):
                newcomer = self._recruit_sect_npc(sect, player.age, rng)
                if newcomer.realm_index >= 3:
                    if sect.world == player.world:
                        news.append(f"{player.age}岁：{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}")
                    game.history.append(HistoryRecord(
                        "SYS_SECT_RECRUIT", 1, player.age, "宗门招新", None, "npc_joined",
                        f"{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}，列为{newcomer.title}。",
                        {"npc_id": newcomer.id, "realm_index": newcomer.realm_index},
                        ["system", "faction", "npc", "recruitment", "world_news", f"world:{sect.world}"],
                    ))
                elif player.faction_id == sect_id:
                    game.history.append(HistoryRecord(
                        "SYS_SECT_RECRUIT", 1, player.age, "宗门招新", None, "npc_joined",
                        f"{newcomer.name}以{self._npc_realm_name(newcomer)}修为加入{sect.name}，列为{newcomer.title}。",
                        {"npc_id": newcomer.id, "realm_index": newcomer.realm_index},
                        ["system", "faction", "npc", "recruitment"],
                    ))
                self._compact_sect_roster(game, sect)

        news.extend(self._annual_offspring_and_family_update(game, rng))
        self._annual_relationship_update(game, rng)
        faction_meta = self._faction_meta(game, player.faction_id or "")
        if (
            not player.faction_id
            or player.faction_id not in game.sects
            or game.sects[player.faction_id].extinct
            or faction_meta.get("world", "human") != player.world
        ):
            return news
        reward_id = (
            player.faction_reward_preference
            if player.realm_index >= 4 and player.faction_reward_preference in FACTION_REWARDS
            else rng.choice(sorted(FACTION_REWARDS))
        )
        reward_name = FACTION_REWARDS[reward_id]["name"]
        if reward_id == "opportunity":
            self._add_opportunity(player, 3)
            reward_text = "机缘 +3"
        elif reward_id == "vitality":
            player.faction_hp_bonus += 2
            player.hp = min(max_hp(player), player.hp + 2)
            reward_text = "HP 上限永久 +2"
        elif reward_id == "mana":
            player.faction_mp_bonus += 2
            player.mp = min(max_mp(player), player.mp + 2)
            reward_text = "MP 上限永久 +2"
        else:
            player.faction_combat_bonus += 3
            reward_text = "独立战斗力永久 +3"
        player.faction_contribution += 1
        sect_name = faction_meta["name"]
        game.history.append(HistoryRecord(
            "SYS_FACTION_WELFARE", 1, player.age, f"{sect_name}年度结算", reward_id, "rewarded",
            f"宗门发放{reward_name}：{reward_text}；年度履职记宗门贡献 +1。",
            {"reward": reward_id, "faction_contribution": player.faction_contribution},
            ["system", "faction", "annual"],
        ))
        return news

    def _annual_world_npc_update(self, game: GameState, rng: random.Random) -> list[str]:
        news: list[str] = []
        living_human_spirits = sum(
            npc.alive and npc.world == "human" and npc.realm_index == 5
            for npc in game.world_npcs.values()
        ) + sum(
            npc.alive and npc.world == "human" and npc.realm_index == 5
            for sect in game.sects.values() for npc in sect.npcs
        )
        simulated_npcs = [*game.world_npcs.values(), *game.notable_npcs.values()]
        for npc in simulated_npcs:
            if not npc.alive:
                continue
            npc.age += 1
            if self._intrigue_is_imprisoned(game, npc.id):
                if npc.lifespan is not None and npc.age >= npc.lifespan:
                    npc.alive = False
                    npc.death_reason = "服刑期间寿元耗尽"
                continue
            if npc.wounds > 0 and rng.random() < 0.35:
                npc.wounds -= 1
            tribulation = self._resolve_npc_periodic_tribulation(game, npc, rng, npc.title)
            if tribulation:
                if npc.world == game.player.world:
                    news.append(f"{game.player.age}岁：{tribulation}")
                if not npc.alive:
                    continue
            if npc.lifespan is not None and npc.age >= npc.lifespan:
                event_world = npc.world
                npc.alive = False
                npc.death_reason = "寿元耗尽，坐化于世间"
                summary = f"{npc.title}{npc.name}寿元耗尽，此后再无音讯。"
                if event_world == game.player.world:
                    news.append(f"{game.player.age}岁：{summary}")
                game.history.append(HistoryRecord(
                    "SYS_WORLD_NPC_FALL", 1, game.player.age, "天下讣闻", None, "npc_fallen", summary,
                    {"npc_id": npc.id, "alive": [True, False]},
                    ["system", "world_npc", "world_news", f"world:{event_world}"],
                ))
                continue
            crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
            event_world = npc.world
            result = self._advance_npc_cultivation(npc, rng, not crossing_to_spirit or living_human_spirits < 1)
            if not result:
                continue
            if result["type"] == "departure":
                living_human_spirits = max(0, living_human_spirits - 1)
                summary = f"{npc.title}{npc.name}{result['new']}；在人界看来，其魂灯已熄，等同陨落。"
                outcome = "npc_departed"
            else:
                if npc.realm_index == 5:
                    living_human_spirits += 1
                summary = f"{npc.title}{npc.name}由{result['old']}突破至{result['new']}。"
                outcome = "npc_breakthrough"
            if event_world == game.player.world:
                news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord(
                "SYS_WORLD_NPC_CHANGE", 1, game.player.age, "天下异动", None, outcome, summary,
                {"npc_id": npc.id, "realm": [result["old"], result["new"]]},
                ["system", "world_npc", "world_news", f"world:{event_world}"],
            ))
        self._maybe_notorious_npc_killing(game, rng, news)
        return news

    def _maybe_notorious_npc_killing(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        protected = {
            str(row.get("id")) for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]
            if row
        }
        villains = [
            npc for npc in game.world_npcs.values()
            if npc.alive and not npc.encountered_player and not self._intrigue_is_imprisoned(game, npc.id)
            and (npc.notorious or npc.path == "demonic")
            and rng.random() < (0.014 if npc.path == "demonic" else 0.004)
        ]
        for villain in villains:
            villain_faction = self._npc_faction_id(game, villain.id)
            victims = [
                npc for npc in self._all_world_npcs(game)
                if npc.alive and not npc.notorious and npc.world == villain.world
                and npc.id not in protected and npc.realm_index < villain.realm_index
                and not (
                    villain.path == "demonic" and villain_faction
                    and self._npc_faction_id(game, npc.id) == villain_faction
                )
            ]
            if not victims:
                continue
            victim = rng.choice(victims)
            victim.alive = False
            victim.death_reason = f"遭{villain.name}截杀"
            summary = f"臭名昭著的{villain.name}又造血案，{victim.name}（{self._npc_realm_name(victim)}）遭其截杀。"
            game.history.append(HistoryRecord(
                "SYS_NOTORIOUS_KILLING", 1, game.player.age, "凶名远播", villain.id, "npc_murdered", summary,
                {"villain_id":villain.id,"victim_id":victim.id},
                ["system","world_npc","notorious","world_news",f"world:{villain.world}"],
            ))
            if game.player.world == villain.world:
                news.append(f"{game.player.age}岁：{summary}")

    def _annual_race_diplomacy_update(self, game: GameState, rng: random.Random) -> list[str]:
        """Compatibility wrapper. Diplomacy now advances once per action unit, not once per year."""
        return self._advance_diplomacy_unit(game, rng)

    def _advance_diplomacy_unit(self, game: GameState, rng: random.Random) -> list[str]:
        self._ensure_race_relations(game)
        self._ensure_sect_relations(game)
        game.diplomacy_unit += 1
        news: list[str] = []
        config = RACE_SYSTEMS.get("diplomacy", {})

        for kind, relations in (("race", game.race_relations), ("sect", game.sect_relations)):
            for key, relation in relations.items():
                if relation.get("status") != "truce" or game.diplomacy_unit < int(relation.get("truce_until_unit", 0)):
                    continue
                first, second = split_race_pair(key)
                if kind == "race" and not all(
                    game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                    for side in (first, second)
                ):
                    continue
                relation.update(status="neutral", affinity=max(-10.0, float(relation.get("affinity", 0))), since_age=game.player.age)
                relation.pop("truce_until_unit", None)
                first_name, second_name = self._power_name(game, kind, first), self._power_name(game, kind, second)
                world = game.player.world if kind == "race" and self._world_supports(game.player.world, "races") else "spirit" if kind == "race" else game.sects.get(first, SectState(first, first)).world
                summary = f"{first_name}与{second_name}的停战期结束，双方暂时恢复中立。"
                game.history.append(HistoryRecord(
                    "SYS_TRUCE_EXPIRED", 1, game.player.age, "停战期届满", None, "neutral", summary,
                    {"kind":kind,"sides":[first,second]}, ["system","diplomacy","truce","world_news",f"world:{world}"],
                ))
                if game.player.world == world:
                    news.append(f"{game.player.age}岁：{summary}")

        news.extend(self._advance_wars_unit(game, rng))

        allied_race = any(
            relation.get("status") in {"alliance", "vassal"}
            and self._player_allegiance_race(game.player) in split_race_pair(key)
            and all(
                game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                for side in split_race_pair(key)
            )
            for key, relation in game.race_relations.items()
        )
        allied_sect = bool(game.player.faction_id) and any(
            relation.get("status") in {"alliance", "vassal"} and game.player.faction_id in split_race_pair(key)
            for key, relation in game.sect_relations.items()
        )
        if self._world_supports(game.player.world, "races") and allied_race:
            reward = float(config.get("alliance_opportunity_reward", 2))
            self._add_opportunity(game.player, reward)
            summary = f"盟族互市与情报共享为你带来机缘 +{reward:g}。"
            news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord("SYS_RACE_ALLIANCE_BENEFIT", 1, game.player.age, "盟族互惠", None, "rewarded", summary, {"opportunity":reward}, ["system","diplomacy","alliance","reward",f"world:{game.player.world}"]))
        if allied_sect:
            game.player.faction_contribution += 1
            summary = "盟宗协作使你的宗门贡献 +1。"
            news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord("SYS_SECT_ALLIANCE_BENEFIT", 1, game.player.age, "盟宗协作", None, "rewarded", summary, {"faction_contribution":1}, ["system","diplomacy","alliance","reward",f"world:{game.player.world}"]))

        if rng.random() < float(config.get("unit_event_chance", 0.08)):
            self._random_race_diplomacy_event(game, rng, news)
        if rng.random() < float(config.get("unit_event_chance", 0.08)):
            self._random_sect_diplomacy_event(game, rng, news)
        self._maybe_npc_found_power(game, rng, news)
        self._pressure_weak_npc_powers(game, rng, news)
        self._simulate_cultivator_duel(game, rng, news)
        return news

    def _random_race_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
        race_ids = [race_id for race_id, row in RACE_DEFINITIONS.items() if world in row.get("worlds", [])]
        first, second = rng.sample(race_ids, 2)
        key = race_pair(first, second)
        relation = game.race_relations.setdefault(key, {"affinity": 0.0, "status": "neutral", "since_age": game.player.age})
        old_status = str(relation.get("status", "neutral"))
        if game.diplomacy_unit < max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))):
            return
        if old_status == "war":
            return  # 战争由士气、厌战和和谈系统决定，不再被普通外交骰直接终止。
        elif old_status in {"alliance", "vassal"}:
            new_status, affinity, action = "neutral", rng.uniform(8, 34), "断盟" if old_status == "alliance" else "脱离依附"
        else:
            roll = rng.random()
            if roll < 0.44:
                new_status, affinity, action = "war", rng.uniform(-82, -56), "宣战"
            elif roll < 0.86:
                new_status, affinity, action = "alliance", rng.uniform(72, 90), "结盟"
            else:
                new_status, affinity, action = "vassal", rng.uniform(62, 84), "确立依附"
        self._set_diplomatic_relation(game, relation, new_status, first, second, "race", affinity)
        first_name, second_name = RACE_DEFINITIONS[first]["name"], RACE_DEFINITIONS[second]["name"]
        summary = f"{first_name}与{second_name}{action}，双方关系转为{RELATION_LABELS[new_status]}（好感 {affinity:.0f}）。"
        game.history.append(HistoryRecord(
            "SYS_RACE_DIPLOMACY", 1, game.player.age, f"{WORLD_SYSTEMS['world_names'][world]}族群大事", action, new_status, summary,
            {"races": [first, second], "status": [old_status, new_status], "affinity": round(affinity, 1)},
            ["system", "diplomacy", "race", "world_news", f"world:{world}"],
        ))
        if game.player.world == world:
            news.append(f"{game.player.age}岁：{summary}")

    def _random_sect_diplomacy_event(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        active = [sect for sect in game.sects.values() if not sect.extinct]
        worlds = [world for world in {sect.world for sect in active} if sum(sect.world == world for sect in active) >= 2]
        if not worlds:
            return
        world = rng.choice(worlds)
        first, second = rng.sample([sect for sect in active if sect.world == world], 2)
        key = race_pair(first.id, second.id)
        relation = game.sect_relations.setdefault(key, {"affinity":0.0,"status":"neutral","since_age":game.player.age})
        old_status = str(relation.get("status", "neutral"))
        if game.diplomacy_unit < max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))):
            return
        if old_status == "war":
            return
        elif old_status in {"alliance", "vassal"}:
            new_status, affinity, action = "neutral", rng.uniform(5, 30), "断绝盟约"
        else:
            roll = rng.random()
            if roll < 0.42:
                new_status, affinity, action = "war", rng.uniform(-82, -55), "正式宣战"
            elif roll < 0.86:
                new_status, affinity, action = "alliance", rng.uniform(68, 90), "缔结盟约"
            else:
                new_status, affinity, action = "vassal", rng.uniform(58, 82), "确立依附"
        self._set_diplomatic_relation(game, relation, new_status, first.id, second.id, "sect", affinity)
        summary = f"{first.name}与{second.name}{action}，宗门关系转为{RELATION_LABELS[new_status]}（好感 {affinity:.0f}）。"
        game.history.append(HistoryRecord(
            "SYS_SECT_DIPLOMACY",1,game.player.age,"宗门外交大事",action,new_status,summary,
            {"sects":[first.id,second.id],"status":[old_status,new_status],"affinity":round(affinity,1)},
            ["system","diplomacy","faction","world_news",f"world:{world}"],
        ))
        if game.player.world == world:
            news.append(f"{game.player.age}岁：{summary}")

    def _pressure_weak_npc_powers(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        rules = WORLD_SYSTEMS["player_faction"]
        for sect in game.sects.values():
            if sect.extinct or not sect.founded_by_npc:
                continue
            threshold = self._governance_threshold(sect.world)
            if any(npc.alive and npc.world == sect.world and npc.realm_index >= threshold for npc in self._sect_members(game, sect)):
                sect.pressure = max(0, sect.pressure - 1)
                continue
            if rng.random() >= float(rules["pressure_chance_per_unit"]):
                continue
            sect.pressure += 1
            if sect.pressure < int(rules["pressure_limit"]):
                continue
            sect.extinct = True
            for npc in self._sect_members(game, sect):
                if npc.alive:
                    npc.faction_id = None
                    game.notable_npcs.setdefault(npc.id, npc)
            summary = f"{sect.name}失去足够修为的坐镇者后，接连遭到排挤，山门很快烟消云散。"
            game.history.append(HistoryRecord(
                "SYS_NPC_POWER_DISSOLVED",1,game.player.age,"新势力消散",sect.id,"dissolved",summary,
                {"sect_id":sect.id},["system","faction","npc","extinction","world_news",f"world:{sect.world}"],
            ))
            if game.player.world == sect.world:
                news.append(f"{game.player.age}岁：{summary}")

    def _simulate_cultivator_duel(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        world = game.player.world
        people = list({npc.id:npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world}.values())
        if len(people) < 2:
            return
        demonic = [npc for npc in people if npc.path == "demonic"]
        if rng.random() >= min(0.42, 0.18 + len(demonic) * 0.025):
            return
        if demonic and rng.random() < 0.72:
            first = rng.choice(demonic)
            first_faction = self._npc_faction_id(game, first.id)
            opponents = [
                npc for npc in people if npc.id != first.id
                and not (first_faction and self._npc_faction_id(game, npc.id) == first_faction)
            ]
            if not opponents:
                return
            second = rng.choice(opponents)
        else:
            pairs = [
                (first, second) for index, first in enumerate(people) for second in people[index + 1:]
                if not (
                    (first.path == "demonic" or second.path == "demonic")
                    and self._npc_faction_id(game, first.id)
                    and self._npc_faction_id(game, first.id) == self._npc_faction_id(game, second.id)
                )
            ]
            if not pairs:
                return
            first, second = rng.choice(pairs)
        first_power, second_power = self._npc_power(first), self._npc_power(second)
        winner, loser = (first, second) if first_power * rng.uniform(0.85, 1.15) >= second_power else (second, first)
        ratio = max(first_power, second_power) / max(1.0, min(first_power, second_power))
        lethal_chance = self._npc_lethal_chance(world, loser.realm_index, "duel")
        lethal = ratio >= REALMS[loser.realm_index].kill_threshold and rng.random() < lethal_chance
        if lethal:
            loser.alive = False
            loser.death_reason = f"与{winner.name}斗法时陨落"
            outcome = f"{loser.name}未能脱身，当场陨落"
            transfer_summary = ""
        else:
            loser.wounds = min(4, loser.wounds + 1)
            outcome = f"{loser.name}负伤退走"
            transfer_summary = self._maybe_transfer_player_dependency(
                game, loser, winner, rng, context="cultivator_duel",
            )
        faction_ids = {self._npc_faction_id(game, first.id), self._npc_faction_id(game, second.id)} - {None}
        tags = ["system","world_npc","duel","world_news",f"world:{world}"]
        if game.player.faction_id in faction_ids:
            tags.append("faction")
        duel_ids = {first.id, second.id}
        if game.player.dao_companion and str(game.player.dao_companion.get("id")) in duel_ids:
            tags.extend(["relationship", "dao_companion"])
        if any(str(row.get("id")) in duel_ids for row in game.player.dao_friends):
            tags.extend(["relationship", "friend"])
        if (game.player.master and str(game.player.master.get("id")) in duel_ids) or any(
            str(row.get("id")) in duel_ids for row in game.player.disciples
        ):
            tags.extend(["relationship", "master"])
        cause = "由魔修主动挑衅引发斗法" if first.path == "demonic" else "因旧怨斗法"
        summary = (
            f"{first.name}（{self._npc_realm_name(first)}）与{second.name}（{self._npc_realm_name(second)}）"
            f"{cause}，{winner.name}占据上风，{outcome}。"
            + (f" {transfer_summary}" if transfer_summary else "")
        )
        game.history.append(HistoryRecord(
            "SYS_CULTIVATOR_DUEL",1,game.player.age,"修士斗法",winner.id,"fatal" if lethal else "injured",summary,
            {"npcs":[first.id,second.id],"winner":winner.id,"loser":loser.id},tags,
        ))
        news.append(f"{game.player.age}岁：{summary}")

    def _set_diplomatic_relation(
        self, game: GameState, relation: dict[str, Any], status: str,
        first: str, second: str, kind: str, affinity: float,
    ) -> None:
        if status == "war":
            self._start_war(game, kind, first, second)
        relation.update(status=status, affinity=round(float(affinity), 1), since_age=game.player.age)
        relation.pop("overlord", None)
        relation.pop("subject", None)
        relation.pop("truce_until_unit", None)
        if status == "truce":
            relation["truce_until_unit"] = game.diplomacy_unit + int(RACE_SYSTEMS.get("diplomacy", {}).get("truce_units", 3))
        elif status == "vassal":
            power = self._race_power if kind == "race" else self._sect_power
            first_power, second_power = power(game, first), power(game, second)
            relation["overlord"], relation["subject"] = ((first, second) if first_power >= second_power else (second, first))

    def _race_power(self, game: GameState, race_id: str) -> float:
        world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
        members = [npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world and npc.race == race_id]
        return sum(sorted((self._npc_power(npc) for npc in members), reverse=True)[:5])

    def _sect_power(self, game: GameState, sect_id: str) -> float:
        sect = game.sects.get(sect_id)
        return sum(sorted((self._npc_power(npc) for npc in self._sect_members(game, sect) if npc.alive), reverse=True)[:5]) if sect else 0.0

    @staticmethod
    def _all_world_npcs(game: GameState) -> list[SectNpc]:
        return [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]

    def _simulate_war_casualties(self, game: GameState, rng: random.Random, kind: str) -> list[str]:
        relations = game.race_relations if kind == "race" else game.sect_relations
        chance = float(RACE_SYSTEMS.get("diplomacy", {}).get("war_casualty_chance", 0.42))
        news: list[str] = []
        protected_ids = {
            str(row.get("id")) for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]
            if row
        }
        for key, relation in relations.items():
            if relation.get("status") != "war" or rng.random() >= chance:
                continue
            first, second = split_race_pair(key)
            if kind == "race" and not all(
                game.player.world in RACE_DEFINITIONS.get(side, {}).get("worlds", [])
                for side in (first, second)
            ):
                continue
            fallen: list[str] = []
            for side in (first, second):
                if kind == "race":
                    world = game.player.world if self._world_supports(game.player.world, "races") else "spirit"
                    candidates = [npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == world and npc.race == side]
                    side_name = RACE_DEFINITIONS.get(side, {"name": side})["name"]
                else:
                    sect = game.sects.get(side)
                    candidates = [npc for npc in (sect.npcs if sect else []) if npc.alive]
                    side_name = sect.name if sect else side
                    world = sect.world if sect else game.player.world
                candidates = [npc for npc in candidates if npc.id not in protected_ids]
                elite_realm = 4 if world == "human" else 6
                ordinary = [npc for npc in candidates if npc.realm_index < elite_realm]
                if not ordinary:
                    ordinary = candidates
                if not ordinary:
                    continue
                victim = rng.choices(ordinary, weights=[1 / max(1, npc.realm_index) for npc in ordinary], k=1)[0]
                if victim.realm_index >= elite_realm and rng.random() >= self._npc_lethal_chance(world, victim.realm_index, "war"):
                    continue
                victim.alive = False
                victim.death_reason = "势力大战中陨落"
                fallen.append(f"{side_name}{victim.name}（{self._npc_realm_name(victim)}）")
                for sect in game.sects.values():
                    if victim in sect.npcs:
                        self._check_sect_extinction(game, sect)
            if fallen:
                title = f"{WORLD_SYSTEMS['world_names'].get(world, world)}族战" if kind == "race" else "宗门大战"
                summary = f"{title}持续，本行动单位战报：" + "、".join(fallen) + "陨落。"
                tags = ["system", "diplomacy", kind, "war", "world_news", f"world:{world}"]
                game.history.append(HistoryRecord("SYS_POWER_WAR", 1, game.player.age, title, None, "casualties", summary, {"sides":[first, second]}, tags))
                if game.player.world == world:
                    news.append(f"{game.player.age}岁：{summary}")
        return news

    @staticmethod
    def _npc_lethal_chance(world: str, realm_index: int, context: str) -> float:
        config = WORLD_SYSTEMS.get("npc_mortality", {})
        if context == "duel":
            protected = config.get("protected_duel_chance", {}).get(world, {})
            if str(realm_index) in protected:
                return float(protected[str(realm_index)])
            return float(config.get("duel_lethal_chance", 0.16))
        table = config.get("elite_war_chance", {}).get(world, {})
        return float(table.get(str(realm_index), 0.02))

    @staticmethod
    def _npc_lifespan_multiplier(path: str) -> int:
        if path != "monster":
            return 1
        return int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))

    @classmethod
    def _scale_npc_lifespan(cls, lifespan: int | None, path: str, age: int = 0) -> int | None:
        if lifespan is None:
            return None
        return max(age + 1, int(lifespan) * cls._npc_lifespan_multiplier(path))

    def _maybe_npc_found_power(self, game: GameState, rng: random.Random, news: list[str]) -> None:
        if rng.random() >= 0.012 or sum(sect.founded_by_npc and not sect.extinct for sect in game.sects.values()) >= 8:
            return
        world = game.player.world
        realm_cap = self._world_realm_cap(world)
        realm_index = (
            (5 if rng.random() < 0.02 else 4)
            if realm_cap <= 5 else (8 if rng.random() < 0.10 else 7)
        )
        kind = rng.choice(["sect", "family"])
        serial = sum(sect.founded_by_npc for sect in game.sects.values()) + 1
        surname = rng.choice(["顾", "叶", "陆", "楚", "白", "谢", "云", "林"])
        founder_name = surname + rng.choice(["玄岳", "长风", "照夜", "问天", "清河"])
        power_name = (founder_name[0] + "氏仙族") if kind == "family" else rng.choice(["玄岳门", "长风谷", "照夜宫", "问天盟"]) + str(serial)
        sect_id = f"npc_{kind}_{game.diplomacy_unit}_{serial}"
        layer = rng.randint(1, REALMS[realm_index].layers)
        age = rng.randint(500, 1200) if realm_cap <= 5 else rng.randint(8000, 30000)
        founder = SectNpc(
            f"{sect_id}_founder", founder_name, "开山祖师" if kind == "sect" else "始祖",
            realm_index, layer, age, None if realm_index >= 6 else max(age + 1, REALMS[realm_index].lifespan[1]),
            spirit_root=self._random_npc_root(realm_index, rng), path=rng.choice(list(PATH_NAMES)),
            race="human", world=world, faction_id=sect_id, affinity=0,
        )
        founder.lifespan = self._scale_npc_lifespan(founder.lifespan, founder.path, founder.age)
        sect = SectState(
            sect_id, power_name, world, [founder], f"由{founder_name}自行建立的{'修仙家族' if kind == 'family' else '宗门'}。",
            path=founder.path, kind=kind, founded_by_npc=True, founder_npc_id=founder.id,
            allegiance_race=founder.race,
        )
        for _ in range(2):
            self._recruit_sect_npc(sect, game.player.age, rng)
        game.sects[sect_id] = sect
        self._ensure_sect_relations(game)
        summary = f"{founder_name}建立了{power_name}，一座新的{'修仙家族' if kind == 'family' else '宗门'}进入天下势力谱。"
        game.history.append(HistoryRecord("SYS_NPC_FOUND_POWER", 1, game.player.age, "新势力崛起", sect_id, "founded", summary, {"faction_id":sect_id,"kind":kind}, ["system","faction","founding","npc",f"world:{world}"]))
        news.append(f"{game.player.age}岁：{summary}")

    def _maybe_race_war_ambush(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if not self._world_supports(player.world, "races") or game.pending_event:
            return False
        enemies = []
        player_race = self._player_allegiance_race(player)
        for key, relation in game.race_relations.items():
            first, second = split_race_pair(key)
            if player_race not in {first, second} or relation.get("status") != "war":
                continue
            enemy = second if first == player_race else first
            if player.world not in RACE_DEFINITIONS.get(enemy, {}).get("worlds", []):
                continue
            if not self._revenge_ready(game, "race_war", enemy):
                continue
            enemies.append(enemy)
        chance = float(RACE_SYSTEMS.get("diplomacy", {}).get("war_ambush_chance", 0.08))
        if not enemies or rng.random() >= chance:
            return False
        enemy = rng.choice(enemies)
        target = self._generate_cultivator_target(player, "边境截杀者", ACTIONS["slay"]["combat"], rng, game=game, forced_race=enemy)
        target["kill_karma"] = True
        target["action"] = "slay"
        self._cache_encounter_target(game, target, rng)
        ambush = self._instantiate_event(self.events_by_id["EVT_ENCOUNTER_AMBUSH_001"], game, rng)
        ambush["title"] = f"{RACE_DEFINITIONS[enemy]['name']}边境截杀"
        ambush["runtime"] = target
        ambush["body"] = (
            f"两族正在交战，{RACE_DEFINITIONS[enemy]['name']}修士循踪截住了你。"
            f"来者修为{target['target_realm_display']}，战斗力约{target['target_power']:.0f}。你必须立即应对。"
        )
        interval = self._record_revenge_trigger(game, "race_war", enemy)
        ambush.setdefault("runtime", {})["revenge_cooldown_units"] = interval
        game.pending_event = ambush
        return True

    def _advance_npc_cultivation(
        self, npc: SectNpc, rng: random.Random, allow_spirit_crossing: bool = True,
        breakthrough_bonus: float = 0.0,
    ) -> dict[str, str] | None:
        if not npc.alive or npc.realm_index <= 0:
            return None
        if npc.realm_index >= len(REALMS):
            return None
        if npc.realm_index >= 9 or (npc.realm_index == 8 and npc.layer >= REALMS[8].layers):
            return None
        realm_cap = self._world_realm_cap(npc.world)
        if npc.realm_index > realm_cap or (
            npc.world != "human" and npc.realm_index == realm_cap and npc.layer >= REALMS[realm_cap].layers
        ):
            return None
        if npc.realm_index == len(REALMS) - 1 and npc.layer >= REALMS[-1].layers:
            return None
        settings = FACTION_SYSTEMS["npc_cultivation"]
        rate = float(settings["progress_per_year"][str(npc.realm_index)])
        root_efficiency = self._npc_root_efficiency(npc.spirit_root)
        npc.cultivation_progress += rate * root_efficiency * rng.uniform(0.82, 1.18)
        threshold = float(settings["threshold"]) * (1 + 0.06 * (npc.layer - 1))
        if npc.cultivation_progress < threshold:
            return None
        crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
        leaving_human_world = npc.world == "human" and npc.realm_index == 5 and npc.layer >= 3
        if crossing_to_spirit and not allow_spirit_crossing:
            npc.cultivation_progress = min(npc.cultivation_progress, threshold)
            return None
        success_chance = min(0.98, self._npc_breakthrough_probability(npc) + max(0.0, float(breakthrough_bonus)))
        if rng.random() >= success_chance:
            npc.cultivation_progress = threshold * float(settings["failed_progress_retained"])
            return None
        old_name = self._npc_realm_name(npc)
        npc.cultivation_progress = max(0.0, npc.cultivation_progress - threshold)
        if leaving_human_world:
            destination = self._ascension_destination(npc.path)
            npc.world = destination
            npc.departed_age = npc.age
            npc.departure_reason = f"飞升{WORLD_SYSTEMS['world_names'][destination]}"
            return {"type": "departure", "old": old_name, "new": npc.departure_reason}
        current = REALMS[npc.realm_index]
        if npc.layer < current.layers:
            npc.layer += 1
            stage = "middle" if npc.layer == 4 else "late" if npc.layer == 7 else None
            stage_ranges = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(current.id, {})
            if stage and stage in stage_ranges and npc.lifespan is not None:
                npc.lifespan += rng.randint(*stage_ranges[stage]) * self._npc_lifespan_multiplier(npc.path)
        else:
            npc.realm_index += 1
            npc.layer = 1
            span = REALMS[npc.realm_index].lifespan
            if span:
                rolled = rng.randint(*span) * self._npc_lifespan_multiplier(npc.path)
                npc.lifespan = max(npc.lifespan or 0, rolled, npc.age + 1)
            else:
                npc.lifespan = None
        return {"type": "breakthrough", "old": old_name, "new": self._npc_realm_name(npc)}

    def _resolve_npc_periodic_tribulation(
        self, game: GameState, npc: SectNpc, rng: random.Random, affiliation: str = "",
    ) -> str | None:
        """Resolve one NPC thunder tribulation; immortal lifespan does not mean immortal NPCs."""
        if not npc.alive or not self._world_supports(npc.world, "ranking") or npc.realm_index < 6:
            return None
        config = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
        if npc.next_tribulation_age is None:
            npc.next_tribulation_age = npc.age + int(config["interval_years"])
            npc.tribulation_power = float(config["base_power"]) * float(config["power_multiplier"]) ** npc.tribulation_count
            return None
        if npc.age < npc.next_tribulation_age:
            return None
        expected = expected_combat_power(npc.realm_index, npc.layer)
        own_power = self._npc_power(npc)
        uncapped_pressure = max(1.0, float(npc.tribulation_power or config["base_power"]))
        world_cap = self._tribulation_base_power_cap(npc.world)
        pressure = min(uncapped_pressure, world_cap) if world_cap is not None else uncapped_pressure
        preparedness = own_power / max(1.0, expected * 0.72 + pressure * 16)
        success_chance = max(0.48, min(0.985, 0.62 + preparedness * 0.24))
        old_count = npc.tribulation_count
        npc.tribulation_count += 1
        npc.next_tribulation_age += int(config["interval_years"])
        npc.tribulation_power = float(config["base_power"]) * float(config["power_multiplier"]) ** npc.tribulation_count
        prefix = f"{affiliation}{npc.name}" if affiliation else npc.name
        if rng.random() >= success_chance:
            npc.alive = False
            npc.death_reason = f"第{old_count + 1}次大天劫下灰飞烟灭"
            summary = f"{prefix}迎击第{old_count + 1}次大天劫失败，灰飞烟灭。"
            result = "npc_tribulation_fallen"
        else:
            summary = f"{prefix}扛过第{old_count + 1}次大天劫（渡过概率 {success_chance:.0%}），下一劫威力再增一倍。"
            if world_cap is not None and uncapped_pressure > world_cap:
                summary += f" 本界将实际基础雷威压制在 {world_cap:.0f}。"
            result = "npc_tribulation_survived"
        game.history.append(HistoryRecord(
            "SYS_NPC_TRIBULATION", 1, game.player.age,
            f"{WORLD_SYSTEMS['world_names'].get(npc.world, npc.world)}天劫", None, result, summary,
            {
                "npc_id": npc.id, "tribulation_count": npc.tribulation_count,
                "chance": round(success_chance, 3), "base_power": pressure,
                "uncapped_base_power": uncapped_pressure, "world_base_power_cap": world_cap,
            },
            ["system", "npc", "tribulation", "world_news", f"world:{npc.world}"],
        ))
        return summary

    @staticmethod
    def _ascension_destination(path: str) -> str:
        if path == "demonic":
            return "demon"
        if path == "ghost":
            return "hell"
        if path == "monster" and "monster_realm" in WORLD_SYSTEMS.get("world_profiles", {}):
            return "monster_realm"
        return "spirit"

    @staticmethod
    def _npc_realm_name(npc: SectNpc) -> str:
        definition = REALMS[npc.realm_index]
        if npc.world == "asura" and npc.realm_index >= 9:
            return WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
                str(npc.realm_index), definition.name,
            )
        if definition.layers == 1:
            return definition.name
        if npc.path == "demonic" and definition.id != "mortal":
            name = WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
                str(npc.realm_index), definition.name,
            )
            if definition.id == "qi":
                return f"{name}{npc.layer}层"
            stage = "初期" if npc.layer <= 3 else "中期" if npc.layer <= 6 else "后期"
            return f"{name}{stage}"
        if definition.id == "qi":
            return f"{definition.name}{npc.layer}层"
        if definition.id == "mortal":
            return definition.name
        stage = "初期" if npc.layer <= 3 else "中期" if npc.layer <= 6 else "后期"
        return f"{definition.name}{stage}"

    @staticmethod
    def _stable_secret_art_roll(identity: str) -> int:
        return sum((index + 1) * ord(character) for index, character in enumerate(identity))

    def _ensure_npc_concealment(self, npc: SectNpc) -> tuple[int, int] | None:
        if (
            npc.concealed_realm_index is not None
            and 0 <= int(npc.concealed_realm_index) < npc.realm_index
        ):
            realm_index = int(npc.concealed_realm_index)
            layer = max(1, min(int(npc.concealed_layer or 1), REALMS[realm_index].layers))
            npc.concealed_layer = layer
            return realm_index, layer
        npc.concealed_realm_index = None
        npc.concealed_layer = None
        if npc.realm_index < 2:
            return None
        rules = WORLD_SYSTEMS.get("secret_arts", {})
        roll = self._stable_secret_art_roll(f"{npc.id}|{npc.name}|收敛修为")
        chance = max(0.0, min(1.0, float(rules.get("npc_concealment_chance", 0.18))))
        if roll % 10_000 >= round(chance * 10_000):
            return None
        maximum_drop = min(
            npc.realm_index,
            max(1, int(rules.get("npc_max_realm_drop", 3))),
        )
        drop = 1 + (roll // 10_000) % maximum_drop
        realm_index = max(0, npc.realm_index - drop)
        layer = 1 + (roll // 100_000) % REALMS[realm_index].layers
        npc.concealed_realm_index = realm_index
        npc.concealed_layer = layer
        return realm_index, layer

    def _npc_cultivation_perception(
        self, game: GameState, npc: SectNpc, require_realm_visibility: bool = False,
    ) -> dict[str, Any]:
        concealed = self._ensure_npc_concealment(npc)
        actual_name = self._npc_realm_name(npc)
        if not concealed:
            visible = not require_realm_visibility or npc.realm_index <= game.player.realm_index + 1
            return {
                "realm_index": npc.realm_index,
                "layer": npc.layer,
                "realm_name": actual_name if visible else "无法看清",
                "concealed": False,
                "detected": False,
                "revealed": visible,
                "actual_realm_name": actual_name if visible else None,
                "display_power": self._npc_power(npc) if visible else None,
            }
        concealed_realm, concealed_layer = concealed
        shell = SectNpc(
            npc.id, npc.name, npc.title, concealed_realm, concealed_layer,
            npc.age, npc.lifespan, path=npc.path, world=npc.world,
        )
        concealed_name = self._npc_realm_name(shell)
        sense = divine_sense_level(game.player)
        detect_requirement = self._cultivation_sense_requirement(concealed_realm, concealed_layer)
        reveal_requirement = self._cultivation_sense_requirement(npc.realm_index, npc.layer)
        detected = sense >= detect_requirement
        revealed = sense >= reveal_requirement
        if revealed:
            realm_name = f"{concealed_name}（已识破：真实{actual_name}）"
            shown_realm, shown_layer = npc.realm_index, npc.layer
            display_power = self._npc_power(npc)
        else:
            realm_name = f"{concealed_name}（气机有异）" if detected else concealed_name
            shown_realm, shown_layer = concealed_realm, concealed_layer
            actual_expected = max(1.0, expected_combat_power(npc.realm_index, npc.layer))
            display_power = self._npc_power(npc) * (
                expected_combat_power(concealed_realm, concealed_layer) / actual_expected
            )
        return {
            "realm_index": shown_realm,
            "layer": shown_layer,
            "realm_name": realm_name,
            "concealed": True,
            "detected": detected,
            "revealed": revealed,
            "actual_realm_name": actual_name if revealed else None,
            "concealed_realm_name": concealed_name,
            "detect_requirement": detect_requirement,
            "reveal_requirement": reveal_requirement if revealed else None,
            "display_power": round(max(1.0, display_power), 1),
        }

    def _relationship_cultivation_perception(
        self, game: GameState, person: dict[str, Any], title: str = "故交",
    ) -> dict[str, Any]:
        """Apply the same secret-art visibility rules to compact relationship snapshots."""
        realm_index = int(person.get("realm_index", 0))
        layer = int(person.get("layer", 1))
        shell = SectNpc(
            str(person.get("id", person.get("name", "relationship"))),
            str(person.get("name", "无名修士")), title, realm_index, layer,
            int(person.get("age", 1)), person.get("lifespan"),
            path=str(person.get("path", "dao")), race=str(person.get("race", "human")),
            world=str(person.get("world", game.player.world)),
            combat_factor=float(person.get("combat_factor", 1.0)),
            concealed_realm_index=person.get("concealed_realm_index"),
            concealed_layer=person.get("concealed_layer"),
        )
        perception = self._npc_cultivation_perception(game, shell)
        # Persist a deterministic disguise into the relationship snapshot so
        # leaving and re-entering the panel cannot reroll the NPC's public face.
        person["concealed_realm_index"] = shell.concealed_realm_index
        person["concealed_layer"] = shell.concealed_layer
        if perception["display_power"] is not None and person.get("combat_power") is not None:
            actual = max(1.0, self._npc_power(shell))
            perception["display_power"] = round(
                float(person["combat_power"]) * float(perception["display_power"]) / actual, 1,
            )
        return perception

    @staticmethod
    def _dynamic_sect_title(npc: SectNpc, sect: SectState) -> str:
        """随修为投影宗门职位，同时保留掌门等唯一职衔。"""
        if any(marker in npc.title for marker in ("宗主","掌门","台主","住持","方丈","太上","宫主","山主","族长","祭酒","老祖","尊者")):
            return npc.title
        if sect.world == "human":
            return {0:"杂役",1:"外门弟子",2:"宗门执事",3:"结丹护法",4:"元婴长老",5:"供奉老祖"}.get(npc.realm_index,"门人")
        return {0:"杂役",1:"外门弟子",2:"内门弟子",3:"真传弟子",4:"宗门执事",5:"化神护法",6:"炼虚长老",7:"合体太上",8:"大乘老祖"}.get(npc.realm_index,"门人")

    def _relationship_snapshot(
        self, person_id: str, name: str, realm_index: int, layer: int, source: str,
        age: int, lifespan: int | None, alive: bool = True, death_reason: str | None = None,
        spirit_root: str = "", cultivation_progress: float = 0.0,
        path: str = "dao", race: str = "human", world: str = "human",
        main_technique_id: str | None = None, affinity: float = 20.0,
        gender: str = "",
    ) -> dict[str, Any]:
        shell = SectNpc(
            person_id, name, "", realm_index, layer, age, int(lifespan or age + 1),
            spirit_root=spirit_root, cultivation_progress=cultivation_progress,
            path=path, race=race, world=world, gender=gender,
        )
        return {
            "id": person_id, "name": name, "realm_index": realm_index, "layer": layer,
            "realm_name": self._npc_realm_name(shell), "source": source,
            "age": age, "lifespan": lifespan, "alive": alive, "death_reason": death_reason,
            "spirit_root": spirit_root, "spirit_root_name": self._npc_root_name(spirit_root),
            "cultivation_progress": cultivation_progress,
            "path": path, "path_name": PATH_NAMES.get(path, path), "race": race,
            "race_name": RACE_DEFINITIONS.get(race, {"name": race})["name"], "world": world,
            "items": {}, "techniques": [], "last_requests": {}, "last_interactions": {},
            "main_technique_id": main_technique_id, "affinity": affinity,
            "gender": shell.gender, "gender_name": gender_name(shell.gender),
            "next_tribulation_age": None, "tribulation_count": 0, "tribulation_power": None,
        }

    def _generated_relationship(self, player: Player, role: str, rng: random.Random) -> dict[str, Any]:
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林"]
        given = ["玄真", "清微", "问岳", "照霜", "长离", "守一", "青崖", "明河"]
        name = rng.choice(surnames) + rng.choice(given)
        if role == "master":
            realm_index = min(5, player.realm_index + 1)
            layer = rng.randint(1, 3)
        elif role == "companion":
            realm_index = player.realm_index
            layer = player.layer
        elif player.layer > 1:
            realm_index = player.realm_index
            layer = rng.randint(1, player.layer - 1)
        else:
            realm_index = max(0, player.realm_index - 1)
            layer = 1
        person_id = f"event_{role}_{player.age}_{rng.randrange(1_000_000)}"
        age_ranges = {
            0: (14, 55), 1: (18, 90), 2: (55, 190), 3: (180, 450),
            4: (450, 1200), 5: (1200, 2600), 6: (2800, 7000),
            7: (7000, 18000), 8: (18000, 80000),
        }
        age = rng.randint(*age_ranges[realm_index])
        span = REALMS[realm_index].lifespan
        lifespan = max(age + 1, rng.randint(*span)) if span else None
        spirit_root = self._random_npc_root(realm_index, rng) if realm_index > 0 else "none"
        path = (player.technique.path if player.technique else player.path) if role == "companion" else rng.choice(list(PATH_NAMES))
        lifespan = self._scale_npc_lifespan(lifespan, path, age)
        return self._relationship_snapshot(
            person_id, name, realm_index, layer, "event", age, lifespan,
            spirit_root=spirit_root, path=path, race="human", world=player.world,
            main_technique_id=player.technique.id if role == "companion" and player.technique else None,
            affinity=28.0 if role == "companion" else 20.0,
        )

    @staticmethod
    def _default_npc_main_technique(npc: SectNpc) -> str | None:
        candidates = [
            technique for technique in TECHNIQUE_CATALOG.values()
            if technique.path == npc.path and technique.grade <= max(1, npc.realm_index)
            and technique.element != "sex" and can_practice_technique(npc.spirit_root, technique.element)
            and technique.id not in GUIXU_EXCLUSIVE_TECHNIQUE_IDS
        ]
        if not candidates:
            candidates = [
                technique for technique in TECHNIQUE_CATALOG.values()
                if technique.element == "neutral"
                and technique.id not in GUIXU_EXCLUSIVE_TECHNIQUE_IDS
            ]
        return max(candidates, key=lambda technique: (technique.grade, technique.combat_bonus)).id if candidates else None

    def _sync_relationship_records(self, game: GameState) -> bool:
        """补齐旧存档字段，并让宗门师徒信息跟随真实 NPC。"""
        changed = False
        relations = [entry for entry in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.concubines, *game.player.disciples, *game.player.disciple_requests] if entry]
        for relation in relations:
            before = copy.deepcopy(relation)
            source = relation.get("source", "event")
            npc = self._find_npc(game, str(relation.get("npc_id") or relation.get("id")))
            if not npc and source not in {"world", "event", "captive", "relationship"}:
                npc = next((entry for entry in game.sects.get(source, SectState(source, "")).npcs if entry.id == relation.get("id")), None)
            if npc:
                relation.update(
                    realm_index=npc.realm_index, layer=npc.layer, realm_name=self._npc_realm_name(npc),
                    age=npc.age, lifespan=npc.lifespan, alive=npc.alive, death_reason=npc.death_reason,
                    spirit_root=npc.spirit_root, spirit_root_name=self._npc_root_name(npc.spirit_root),
                    cultivation_progress=npc.cultivation_progress,
                    path=npc.path, path_name=PATH_NAMES.get(npc.path, npc.path), race=npc.race,
                    race_name=RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"], world=npc.world,
                    affinity=npc.affinity if npc.affinity is not None else relation.get("affinity", 20.0),
                    next_tribulation_age=npc.next_tribulation_age,
                    tribulation_count=npc.tribulation_count,
                    tribulation_power=npc.tribulation_power,
                )
            else:
                realm_index = int(relation.get("realm_index", 0))
                age = int(relation.get("age", {0: 30, 1: 50, 2: 120, 3: 300, 4: 800, 5: 1800}.get(realm_index, 30)))
                span = REALMS[realm_index].lifespan
                relation.setdefault("age", age)
                relation.setdefault("lifespan", max(age + 1, span[1]) if span else None)
                relation.setdefault("alive", True)
                relation.setdefault("death_reason", None)
                relation.setdefault(
                    "spirit_root",
                    self._random_npc_root(realm_index, random.Random(f"relation:{relation.get('id', '')}"))
                    if realm_index > 0 else "none",
                )
                relation.setdefault("cultivation_progress", 0.0)
                relation.setdefault("path", "dao")
                relation.setdefault("race", "human")
                relation.setdefault("world", "human")
                shell = SectNpc(
                    str(relation.get("id", "relation")), str(relation.get("name", "无名")), "",
                    realm_index, int(relation.get("layer", 1)), age, int(relation.get("lifespan") or age + 1),
                    path=str(relation.get("path", "dao")),
                )
                relation["realm_name"] = self._npc_realm_name(shell)
                relation["spirit_root_name"] = self._npc_root_name(relation["spirit_root"])
                relation["path_name"] = PATH_NAMES.get(relation["path"], relation["path"])
                relation["race_name"] = RACE_DEFINITIONS.get(relation["race"], {"name": relation["race"]})["name"]
            relation.setdefault("items", {})
            relation.setdefault("techniques", [])
            relation.setdefault("last_requests", {})
            relation.setdefault("last_interactions", {})
            relation.setdefault("affinity", 20.0)
            relation.setdefault("main_technique_id", None)
            relation.setdefault("breakthrough_bonus", 0.0)
            relation.setdefault("next_tribulation_age", None)
            relation.setdefault("tribulation_count", 0)
            relation.setdefault("tribulation_power", None)
            changed = changed or relation != before
        return changed

    def _annual_relationship_update(self, game: GameState, rng: random.Random | None = None) -> None:
        self._sync_relationship_records(game)
        player = game.player
        rng = rng or random.Random(f"relationships:{game.seed}:{player.age}")
        event_relations = [
            entry for entry in [player.master, player.dao_companion, *player.dao_friends, *player.concubines, *player.disciples, *player.disciple_requests]
            if entry and not self._find_npc(game, str(entry.get("npc_id") or entry.get("id", "")))
        ]
        for relation in event_relations:
            if not relation.get("alive", True):
                continue
            relation["age"] = int(relation.get("age", 0)) + 1
            lifespan = relation.get("lifespan")
            if lifespan is not None and relation["age"] >= lifespan:
                relation["alive"] = False
                relation["death_reason"] = "寿元耗尽，坐化尘世"
                is_companion = relation is player.dao_companion
                is_friend = relation in player.dao_friends
                is_concubine = relation in player.concubines
                game.history.append(HistoryRecord(
                    "SYS_RELATION_FALL", 1, player.age, "道侣坐化" if is_companion else "道友坐化" if is_friend else "侍妾坐化" if is_concubine else "师门故人坐化", None, "relation_fallen",
                    f"{relation['name']}寿元已尽，这段尘缘只余旧忆。",
                    {"relation_id": relation["id"], "alive": [True, False]}, ["system", "relationship", "friend" if is_friend else "dao_companion" if is_companion else "concubine" if is_concubine else "master", "death"],
                ))
                continue
            shell = SectNpc(
                id=str(relation["id"]), name=str(relation["name"]), title="",
                realm_index=int(relation["realm_index"]), layer=int(relation["layer"]),
                age=int(relation["age"]), lifespan=relation.get("lifespan"),
                spirit_root=str(relation.get("spirit_root", "")),
                cultivation_progress=float(relation.get("cultivation_progress", 0.0)),
                path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
                world=str(relation.get("world", "human")),
                next_tribulation_age=relation.get("next_tribulation_age"),
                tribulation_count=int(relation.get("tribulation_count", 0)),
                tribulation_power=relation.get("tribulation_power"),
            )
            tribulation = self._resolve_npc_periodic_tribulation(game, shell, rng, "道侣" if relation is player.dao_companion else "")
            if tribulation and not shell.alive:
                relation.update(alive=False, death_reason=shell.death_reason)
                continue
            breakthrough = self._advance_npc_cultivation(
                shell, rng, allow_spirit_crossing=True,
                breakthrough_bonus=float(relation.get("breakthrough_bonus", 0)),
            )
            relation.update(
                realm_index=shell.realm_index, layer=shell.layer, realm_name=self._npc_realm_name(shell),
                lifespan=shell.lifespan, cultivation_progress=shell.cultivation_progress,
                spirit_root=shell.spirit_root, spirit_root_name=self._npc_root_name(shell.spirit_root),
                path=shell.path, path_name=PATH_NAMES.get(shell.path, shell.path), race=shell.race,
                race_name=RACE_DEFINITIONS.get(shell.race, {"name": shell.race})["name"], world=shell.world,
                next_tribulation_age=shell.next_tribulation_age,
                tribulation_count=shell.tribulation_count,
                tribulation_power=shell.tribulation_power,
            )
            if breakthrough:
                is_companion = relation is player.dao_companion
                is_friend = relation in player.dao_friends
                is_concubine = relation in player.concubines
                game.history.append(HistoryRecord(
                    "SYS_RELATION_BREAKTHROUGH", 1, player.age, "道侣破境" if is_companion else "道友破境" if is_friend else "侍妾破境" if is_concubine else "师门破境", None, "npc_breakthrough",
                    f"{relation['name']}凭借{relation['spirit_root_name']}由{breakthrough['old']}突破至{breakthrough['new']}。",
                    {"relation_id": relation["id"], "realm": [breakthrough["old"], breakthrough["new"]]}, ["system", "relationship", "friend" if is_friend else "dao_companion" if is_companion else "concubine" if is_concubine else "master", "npc"],
                ))
        expired = [entry for entry in player.disciple_requests if not entry.get("alive", True)]
        if expired:
            expired_ids = {entry["id"] for entry in expired}
            player.disciple_requests = [entry for entry in player.disciple_requests if entry["id"] not in expired_ids]
        self._sync_relationship_records(game)

    @staticmethod
    def _recruit_realm_index(roll: float, world: str = "human") -> int:
        distributions = FACTION_SYSTEMS.get("recruitment_distribution_by_world", {})
        rows = distributions.get(world, FACTION_SYSTEMS["recruitment_distribution"])
        for entry in rows:
            if roll < float(entry["upper"]):
                return int(entry["realm_index"])
        raise ValueError("宗门招募概率表未覆盖完整区间")

    @classmethod
    def _roll_recruit_age_lifespan(
        cls, realm_index: int, path: str, rng: random.Random, *, young: bool = False,
    ) -> tuple[int, int | None]:
        """Generate recruits with a meaningful amount of lifespan still remaining."""
        age_ranges = {
            0: (16, 36), 1: (18, 72), 2: (45, 150), 3: (120, 330),
            4: (280, 850), 5: (750, 2300), 6: (2200, 5800),
            7: (6000, 21000), 8: (14000, 80000), 9: (40000, 150000),
            10: (120000, 520000), 11: (420000, 1500000), 12: (1000000, 4200000),
        }
        low, high = age_ranges.get(realm_index, (18, 80))
        if young:
            high = low + max(6, (high - low) // 2)
        lifespan_range = REALMS[realm_index].lifespan
        if lifespan_range is None:
            return rng.randint(low, high), None
        lifespan = rng.randint(*lifespan_range) * cls._npc_lifespan_multiplier(path)
        minimum_remaining = max(12, int(lifespan * 0.25))
        safe_high = max(low, min(high, lifespan - minimum_remaining))
        safe_low = min(low, safe_high)
        age = rng.randint(safe_low, safe_high)
        return age, lifespan

    def _recruit_sect_npc(self, sect: SectState, world_age: int, rng: random.Random) -> SectNpc:
        realm_index = self._recruit_realm_index(rng.random(), sect.world)
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "江", "闻"]
        given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚"]
        name = rng.choice(surnames) + rng.choice(given)
        layer = rng.randint(1, REALMS[realm_index].layers)
        title = "仙宫供奉" if realm_index >= 9 else "跨域客卿" if realm_index >= 5 else "加盟客卿" if realm_index >= 3 else "新晋内门" if realm_index == 2 else "新入门弟子"
        path = self._random_npc_path(sect.id, rng)
        age, lifespan = self._roll_recruit_age_lifespan(realm_index, path, rng)
        race = "human"
        if self._world_supports(sect.world, "races"):
            race = rng.choice([
                race_id for race_id, definition in RACE_DEFINITIONS.items()
                if sect.world in definition.get("worlds", [])
            ])
        npc = SectNpc(
            id=f"{sect.id}_recruit_{world_age}_{len(sect.npcs)}", name=name, title=title,
            realm_index=realm_index, layer=layer, age=age, lifespan=lifespan,
            spirit_root=self._random_npc_root(realm_index, rng),
            path=path, race=race, world=sect.world,
        )
        npc.affinity = rng.uniform(-6, 10)
        npc.treasure_item_id = self._select_npc_treasure(npc, rng)
        sect.npcs.append(npc)
        return npc

