from __future__ import annotations
from ...models import GameState
from ...content_registry import ITEM_CATALOG
from ...content_registry import MONSTER_BLOODLINE_SETTINGS
from ...content_registry import REALMS
from ...content_registry import TECHNIQUE_CATALOG
from ...content_registry import WORLD_SYSTEMS
from ...rules import assign_technique
from ...rules import breakthrough_opportunity_required
import copy
from ...system.monster_bloodline_system import ensure_monster_bloodline_state
from ...rules import ensure_technique_set
from ...system.ghost_system import ghost_cultivation_active
from ...rules import learn_technique
from ...rules import max_mp
from ...rules import realm
from .dependencies import CharacterPreparationDependencies


def prepare_character(deps: CharacterPreparationDependencies, game: GameState) -> bool:
    ghost_migrated = conversion_migrated = monster_lifespan_migrated = sense_baseline_migrated = False
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
    if game.player.world not in deps.maps.worlds:
        game.player.world = "human"
        game.player.location_id = None
        deps._clear_market(game)
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
    normalized_location = deps.maps.normalize_location(game.player.world, game.player.location_id)
    location_changed = normalized_location != game.player.location_id
    if location_changed:
        game.player.location_id = normalized_location
        deps._clear_market(game)
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
    if game.player.path == "monster" and deps.bloodline_content_available() and game.player.technique is None:
        starter_id = str(MONSTER_BLOODLINE_SETTINGS.get("starter_technique_id", ""))
        if starter_id in TECHNIQUE_CATALOG:
            starter = copy.deepcopy(TECHNIQUE_CATALOG[starter_id])
            learn_technique(game.player, starter)
            assign_technique(game.player, starter, "main")
            bloodline_changed = True
    starter_changed = False
    if game.player.path == "demonic" and game.player.divine_sense_technique is None:
        starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BLOOD_SOUL_SENSE"])
        learn_technique(game.player, starter)
        assign_technique(game.player, starter, "divine_sense")
        game.player.divine_sense_rank = max(game.player.divine_sense_rank, 1)
        starter_changed = True
    if game.player.path == "demonic" and game.player.technique is None:
        starter = copy.deepcopy(TECHNIQUE_CATALOG["TECH_DEMON_BREATHING"])
        learn_technique(game.player, starter)
        assign_technique(game.player, starter, "main")
        starter_changed = True
    true_cultivation = (
        game.player.cultivation_suppression
        or game.player.sealed_cultivation
        or {"realm_index": game.player.realm_index, "layer": game.player.layer}
    )
    natural_sense = deps._cultivation_sense_requirement(
        int(true_cultivation.get("realm_index", game.player.realm_index)),
        int(true_cultivation.get("layer", game.player.layer)),
    )
    if game.player.divine_sense_rank < natural_sense:
        game.player.divine_sense_rank = natural_sense
        sense_baseline_migrated = True
    changed = (
        ghost_migrated or conversion_migrated or monster_lifespan_migrated
        or starter_changed or location_changed
        or sense_baseline_migrated
        or bloodline_changed or before_manuals != after_manuals
        or before_known != tuple(technique.id for technique in game.player.known_techniques)
    )
    if (
        game.player.body_technique and game.player.body_training < int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
        and game.player.body_progress >= deps._body_progress_required(game.player)
        and not game.player.awaiting_body_breakthrough
    ):
        game.player.awaiting_body_breakthrough = True
        changed = True
    current_realm = realm(game.player)
    if game.player.realm_index >= 9 and game.player.world == "celestial":
        changed = changed or game.player.awaiting_minor_breakthrough or game.player.awaiting_major_breakthrough
        game.player.awaiting_minor_breakthrough = False
        game.player.awaiting_major_breakthrough = False
    if (
        game.player.alive and deps._manual_breakthrough_kind(game.player) == "major"
        and game.player.layer >= current_realm.layers
        and game.player.opportunity >= breakthrough_opportunity_required(game.player)
        and not game.player.awaiting_major_breakthrough
    ):
        game.player.awaiting_major_breakthrough = True
        changed = True
    if (
        game.player.alive and game.player.layer in deps._manual_minor_layers(game.player)
        and game.player.opportunity >= breakthrough_opportunity_required(game.player)
        and not game.player.awaiting_minor_breakthrough
    ):
        game.player.awaiting_minor_breakthrough = True
        changed = True
    return bool(changed)
