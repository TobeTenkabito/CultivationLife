from __future__ import annotations

import copy

from ..content_registry import (
    ITEM_CATALOG, REALMS,
    TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
    MONSTER_BLOODLINE_SETTINGS,
)
from ..models import GameState, HistoryRecord
from ..rules import (
    assign_technique,
    learn_technique,
    max_mp,
    opportunity_required,
    realm,
    ensure_technique_set,
    divine_sense_level_threshold,
)


from ..runtime import decode_rng, encode_rng
from ..system.monster_bloodline_system import (
    bloodline_content_available,
    ensure_monster_bloodline_state,
)
from ..system.ghost_system import (
    ensure_ghost_cultivation_state, ghost_cultivation_active,
    grant_intrinsic_progression_if_new_highwater,
)
from ..system.possession_system import (
    migrate_possession_timeline,
)


class EnginePersistenceMixin:
    def _load(self, game_id: str) -> GameState:
        game = self.store.load(game_id)
        conversion_migrated = False
        monster_lifespan_migrated = False
        sense_baseline_migrated = False
        possession_timeline_migrated = migrate_possession_timeline(game.player)
        ghost_migrated = ensure_ghost_cultivation_state(game.player)
        if ghost_cultivation_active(game.player):
            old_intrinsic_state = (
                game.player.ghost_intrinsic_hp_reference,
                game.player.ghost_intrinsic_hp_current,
                game.player.ghost_intrinsic_mp_reference,
                game.player.ghost_intrinsic_mp_current,
                game.player.ghost_intrinsic_highwater_realm,
                game.player.ghost_intrinsic_highwater_layer,
            )
            grant_intrinsic_progression_if_new_highwater(game.player)
            ghost_migrated = ghost_migrated or old_intrinsic_state != (
                game.player.ghost_intrinsic_hp_reference,
                game.player.ghost_intrinsic_hp_current,
                game.player.ghost_intrinsic_mp_reference,
                game.player.ghost_intrinsic_mp_current,
                game.player.ghost_intrinsic_highwater_realm,
                game.player.ghost_intrinsic_highwater_layer,
            )
        ghost_floor = float(WORLD_SYSTEMS.get("ghost_cultivation", {}).get("soul_death_intrinsic_floor", 1.0))
        if (
            ghost_cultivation_active(game.player) and game.player.alive
            and (
                float(game.player.ghost_intrinsic_hp_current or 0.0) < ghost_floor
                or float(game.player.ghost_intrinsic_mp_current or 0.0) < ghost_floor
            )
        ):
            self._die(game, "本体魂基已经低于存在界限，魂魄彻底消散", "SYS_GHOST_SOUL_DISPERSAL")
            ghost_migrated = True
        if ghost_cultivation_active(game.player) and game.player.active_breakthrough_aids:
            valid_ghost_aids = [
                item_id for item_id in game.player.active_breakthrough_aids
                if item_id in ITEM_CATALOG
                and game.player.realm_index >= 4
                and (
                    not str(ITEM_CATALOG[item_id].breakthrough_scope or "").startswith("major:")
                    or game.player.realm_index >= 6
                )
            ]
            if valid_ghost_aids != game.player.active_breakthrough_aids:
                game.player.active_breakthrough_aids = valid_ghost_aids
                ghost_migrated = True
        if (
            game.player.path == "ghost" and not ghost_cultivation_active(game.player)
            and game.player.ghost_intrinsic_hp_reference is not None
            and game.player.lifespan is None and REALMS[game.player.realm_index].lifespan is not None
        ):
            game.player.lifespan = max(game.player.age + 1, int(REALMS[game.player.realm_index].lifespan[1]))
            ghost_migrated = True
        if game.player.path == "monster" and not game.player.monster_lifespan_scaled:
            if game.player.lifespan is not None:
                game.player.lifespan *= int(
                    WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3)
                )
            game.player.monster_lifespan_scaled = True
            monster_lifespan_migrated = True
        if game.player.world not in self.maps.worlds:
            game.player.world = "human"
            game.player.location_id = None
            self._clear_market(game)
            monster_lifespan_migrated = True
        if game.player.world == "celestial":
            if game.player.immortal_power_converted:
                if game.player.immortal_conversion_stage != 5:
                    game.player.immortal_conversion_stage = 5
                    conversion_migrated = True
            else:
                if game.player.immortal_conversion_last_age is None:
                    game.player.immortal_conversion_last_age = game.player.age
                    game.player.immortal_conversion_checked_units = 0
                    conversion_migrated = True
                cap = max_mp(game.player) * game.player.immortal_conversion_stage / 5
                if game.player.mp > cap:
                    game.player.mp = cap
                    conversion_migrated = True
                legacy_conversion_trial = bool(
                    game.active_trial and game.active_trial.get("kind") == "immortal_conversion"
                )
                if legacy_conversion_trial:
                    game.active_trial = None
                    conversion_migrated = True
                if legacy_conversion_trial and game.pending_event and str(game.pending_event.get("id", "")).startswith("EVT_IMMORTAL_CONVERSION_"):
                    game.pending_event = None
                    conversion_migrated = True
        normalized_location = self.maps.normalize_location(game.player.world, game.player.location_id)
        location_changed = normalized_location != game.player.location_id
        if location_changed:
            game.player.location_id = normalized_location
            self._clear_market(game)
        elif (
            game.market_location_id is None and game.market_world == game.player.world
            and game.market_offers
        ):
            game.market_location_id = normalized_location
            for offer in game.market_offers:
                offer.setdefault("location_id", normalized_location)
            location_changed = True
        before_known = tuple(technique.id for technique in game.player.known_techniques)
        before_manuals = tuple(
            (item.id, item.technique_level, item.technique_origin_realm_index, item.quantity)
            for item in game.player.inventory if item.technique_id
        )
        ensure_technique_set(game.player)
        after_manuals = tuple(
            (item.id, item.technique_level, item.technique_origin_realm_index, item.quantity)
            for item in game.player.inventory if item.technique_id
        )
        bloodline_changed = ensure_monster_bloodline_state(game.player)
        if game.player.path == "monster" and bloodline_content_available() and game.player.technique is None:
            starter_id = str(MONSTER_BLOODLINE_SETTINGS.get("starter_technique_id", ""))
            if starter_id in TECHNIQUE_CATALOG:
                starter = copy.deepcopy(TECHNIQUE_CATALOG[starter_id])
                learn_technique(game.player, starter)
                assign_technique(game.player, starter, "main")
                bloodline_changed = True
        version_changed = game.version < 5
        if version_changed:
            legacy_experience = max(0.0, game.player.divine_sense_experience)
            legacy_level = max(
                1 if game.player.path == "demonic" else 0,
                int((legacy_experience / max(1.0, float(WORLD_SYSTEMS["demonic_cultivation"]["divine_sense_experience_base"]))) ** 0.5),
            )
            game.player.divine_sense_rank = max(game.player.divine_sense_rank, legacy_level)
            game.player.divine_sense_experience = max(
                0.0, legacy_experience - divine_sense_level_threshold(legacy_level),
            )
            game.version = 5
        if game.player.path == "demonic" and game.player.divine_sense_technique is None:
            starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BLOOD_SOUL_SENSE"])
            learn_technique(game.player, starter)
            assign_technique(game.player, starter, "divine_sense")
            game.player.divine_sense_rank = max(game.player.divine_sense_rank, 1)
        if game.player.path == "demonic" and game.player.technique is None:
            starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_DEMON_BREATHING"])
            learn_technique(game.player, starter)
            assign_technique(game.player, starter, "main")
            version_changed = True
        true_cultivation = (
            game.player.cultivation_suppression
            or game.player.sealed_cultivation
            or {"realm_index": game.player.realm_index, "layer": game.player.layer}
        )
        natural_sense = self._cultivation_sense_requirement(
            int(true_cultivation.get("realm_index", game.player.realm_index)),
            int(true_cultivation.get("layer", game.player.layer)),
        )
        if game.player.divine_sense_rank < natural_sense:
            game.player.divine_sense_rank = natural_sense
            sense_baseline_migrated = True
        changed = (
            ghost_migrated or conversion_migrated or monster_lifespan_migrated
            or possession_timeline_migrated or version_changed or location_changed
            or sense_baseline_migrated
            or bloodline_changed or before_manuals != after_manuals
            or before_known != tuple(technique.id for technique in game.player.known_techniques)
        )
        if (
            game.player.body_technique and game.player.body_training < int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
            and game.player.body_progress >= self._body_progress_required(game.player)
            and not game.player.awaiting_body_breakthrough
        ):
            game.player.awaiting_body_breakthrough = True
            changed = True
        current_realm = realm(game.player)
        if (
            game.player.alive and self._manual_breakthrough_kind(game.player) == "major"
            and game.player.layer >= current_realm.layers
            and game.player.opportunity >= opportunity_required(game.player)
            and not game.player.awaiting_major_breakthrough
        ):
            game.player.awaiting_major_breakthrough = True
            changed = True
        if (
            game.player.alive and game.player.layer in self._manual_minor_layers(game.player)
            and game.player.opportunity >= opportunity_required(game.player)
            and not game.player.awaiting_minor_breakthrough
        ):
            game.player.awaiting_minor_breakthrough = True
            changed = True
        before_world_version = game.world_rules_version
        before_roster = {sect_id: tuple(npc.id for npc in sect.npcs) for sect_id, sect in game.sects.items()}
        before_world_npcs = tuple(game.world_npcs)
        self._ensure_sects(game)
        changed = self._ensure_world_npcs(game) or changed
        changed = self._enforce_world_realm_caps(game) or changed
        changed = self._ensure_npc_formations(game) or changed
        if self._ensure_sage_state(game):
            changed = True
        if self._ensure_guixu_state(game):
            changed = True
        self._refresh_sage_effects(game)
        changed = self._migrate_true_demon_races(game) or changed
        if game.player.faction_id in game.sects:
            sect_allegiance = game.sects[game.player.faction_id].allegiance_race
            if sect_allegiance and game.player.allegiance_race != sect_allegiance:
                game.player.allegiance_race = sect_allegiance
                changed = True
        elif not game.player.allegiance_race:
            game.player.allegiance_race = game.player.lineage_race or game.player.race
            changed = True
        changed = self._ensure_race_relations(game) or changed
        changed = self._ensure_sect_relations(game) or changed
        changed = self._ensure_wars(game) or changed
        changed = self._compact_world_history(game) or changed
        after_roster = {sect_id: tuple(npc.id for npc in sect.npcs) for sect_id, sect in game.sects.items()}
        changed = (
            changed or after_roster != before_roster or tuple(game.world_npcs) != before_world_npcs
            or game.world_rules_version != before_world_version
        )
        changed = self._sync_party_state(game) or changed
        changed = self._sync_relationship_records(game) or changed
        rng = decode_rng(game.seed, game.rng_state)
        if self._ensure_natal_artifact(game):
            changed = True
        if game.player.world == "celestial" and self._ensure_heavenly_court(game, rng):
            game.rng_state = encode_rng(rng)
            changed = True
        if self._ensure_market(game, rng):
            game.rng_state = encode_rng(rng)
            changed = True
        if changed:
            self.store.save(game)
        if game.pending_event:
            post_battle_possession = game.pending_event.get("id") == "SYS_POST_BATTLE_POSSESSION"
            event = self.events_by_id.get(game.pending_event.get("id"))
            is_mortal_event = bool(event and "mortal" in event.get("tags", []))
            saved_choices = {choice.get("id") for choice in game.pending_event.get("choices", [])}
            current_choices = {choice.get("id") for choice in event.get("choices", [])} if event else set()
            if event:
                tags = event.get("tags", [])
                if game.player.realm_index >= 4 and "faction" in tags and "duty" in tags and "war" not in tags:
                    current_choices.update({"__delegate_faction_task", "__decline_faction_task"})
            incompatible = not post_battle_possession and (
                event is None or ("all_realms" not in (event.get("tags", []) if event else []) and (game.player.realm_index == 0) != is_mortal_event)
                or not saved_choices <= current_choices
            )
            if incompatible:
                game.pending_event = None
                game.active_trial = None
                game.history.append(HistoryRecord(
                    "SYS_CONTENT_MIGRATION", 1, game.player.age, "命途校正", None, "migrated",
                    "旧版本中与当前境界不相容的待处理事件已移出事件池。", {}, ["system", "migration"],
                ))
                self.store.save(game)
        elif game.active_trial:
            game.active_trial = None
            game.history.append(HistoryRecord(
                "SYS_TRIAL_MIGRATION", 1, game.player.age, "劫数校正", None, "migrated",
                "旧存档中失去对应事件的突破或雷劫状态已经清理，可以继续行动。", {},
                ["system", "migration", "tribulation"],
            ))
            self.store.save(game)
        return game

