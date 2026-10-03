"""Named dependency builders for actions."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..dependencies import (
    CultivationActionDependencies,
    WorldTravelDependencies,
    FactionActionDependencies,
    EncounterActionDependencies,
    InventoryDependencies,
    RelationshipActionDependencies,
)

if TYPE_CHECKING:
    from .. import GameEngine


def bind_cultivation_actions(engine: GameEngine, *, bloodline_content_available: Callable[[], bool]) -> CultivationActionDependencies:
    return CultivationActionDependencies(
        _body_breakthrough_chance=lambda *args, **kwargs: engine._body_breakthrough_chance(*args, **kwargs),
        _body_pity_key=lambda *args, **kwargs: engine._body_pity_key(*args, **kwargs),
        _body_progress_required=lambda *args, **kwargs: engine._body_progress_required(*args, **kwargs),
        _body_tribulation_damage_reduction=lambda *args, **kwargs: engine._body_tribulation_damage_reduction(*args, **kwargs),
        _breakthrough_chance=lambda *args, **kwargs: engine._breakthrough_chance(*args, **kwargs),
        _clear_minor_pity=lambda *args, **kwargs: engine._clear_minor_pity(*args, **kwargs),
        _complete_major_breakthrough=lambda *args, **kwargs: engine._complete_major_breakthrough(*args, **kwargs),
        _complete_minor_breakthrough=lambda *args, **kwargs: engine._complete_minor_breakthrough(*args, **kwargs),
        _consume_breakthrough_aids=lambda *args, **kwargs: engine._consume_breakthrough_aids(*args, **kwargs),
        _cultivation_sense_requirement=lambda *args, **kwargs: engine._cultivation_sense_requirement(*args, **kwargs),
        _enforce_guixu_rank_boundary=lambda *args, **kwargs: engine._enforce_guixu_rank_boundary(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: engine._ensure_market(*args, **kwargs),
        _joint_companion_eligible=lambda *args, **kwargs: engine._joint_companion_eligible(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _major_breakthrough_requirement=lambda *args, **kwargs: engine._major_breakthrough_requirement(*args, **kwargs),
        _manual_breakthrough_kind=lambda *args, **kwargs: engine._manual_breakthrough_kind(*args, **kwargs),
        _minor_layer_target=lambda *args, **kwargs: engine._minor_layer_target(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _record_minor_pity_failure=lambda *args, **kwargs: engine._record_minor_pity_failure(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: engine._sage_scaled_gain(*args, **kwargs),
        _secret_art_realm_name=lambda *args, **kwargs: engine._secret_art_realm_name(*args, **kwargs),
        _start_breakthrough_trial=lambda *args, **kwargs: engine._start_breakthrough_trial(*args, **kwargs),
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
        bloodline_content_available=bloodline_content_available,
    )


def bind_world_travel_actions(engine: GameEngine) -> WorldTravelDependencies:
    return WorldTravelDependencies(
        _plan_world_transition=lambda *args, **kwargs: engine._plan_world_transition(*args, **kwargs),
        _apply_world_transition=lambda *args, **kwargs: engine._apply_world_transition(*args, **kwargs),
        _ascension_destination=lambda *args, **kwargs: engine._ascension_destination(*args, **kwargs),
        _cancel_auction_for_world_change=lambda *args, **kwargs: engine._cancel_auction_for_world_change(*args, **kwargs),
        _clear_market=lambda *args, **kwargs: engine._clear_market(*args, **kwargs),
        _complete_demonic_ascension=lambda *args, **kwargs: engine._complete_demonic_ascension(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: engine._ensure_market(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: engine._find_npc(*args, **kwargs),
        _handover_faction_for_ascension=lambda *args, **kwargs: engine._handover_faction_for_ascension(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _intrigue_key=lambda *args, **kwargs: engine._intrigue_key(*args, **kwargs),
        _intrigue_position_specs=lambda *args, **kwargs: engine._intrigue_position_specs(*args, **kwargs),
        _intrigue_state=lambda *args, **kwargs: engine._intrigue_state(*args, **kwargs),
        _intrigue_sync_player_prison=lambda *args, **kwargs: engine._intrigue_sync_player_prison(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _maybe_founder_return_event=lambda *args, **kwargs: engine._maybe_founder_return_event(*args, **kwargs),
        _party_crossing_candidate=lambda *args, **kwargs: engine._party_crossing_candidate(*args, **kwargs),
        _prepare_permanent_world_transition=lambda *args, **kwargs: engine._prepare_permanent_world_transition(*args, **kwargs),
        _resolve_selected_ascension_entourage=lambda *args, **kwargs: engine._resolve_selected_ascension_entourage(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: engine._sect_members(*args, **kwargs),
        _get_events_by_id=lambda: engine.events_by_id,
        _get_maps=lambda: engine.maps,
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
    )


def bind_faction_actions(engine: GameEngine) -> FactionActionDependencies:
    return FactionActionDependencies(
        _actual_player_realm=lambda *args, **kwargs: engine._actual_player_realm(*args, **kwargs),
        _check_sect_extinction=lambda *args, **kwargs: engine._check_sect_extinction(*args, **kwargs),
        _ensure_sect_relations=lambda *args, **kwargs: engine._ensure_sect_relations(*args, **kwargs),
        _governance_threshold=lambda *args, **kwargs: engine._governance_threshold(*args, **kwargs),
        _has_race_voice=lambda *args, **kwargs: engine._has_race_voice(*args, **kwargs),
        _has_sect_voice=lambda *args, **kwargs: engine._has_sect_voice(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: engine._intrigue_enabled(*args, **kwargs),
        _intrigue_state=lambda *args, **kwargs: engine._intrigue_state(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: engine._player_allegiance_race(*args, **kwargs),
        _power_name=lambda *args, **kwargs: engine._power_name(*args, **kwargs),
        _random_npc_root=lambda *args, **kwargs: engine._random_npc_root(*args, **kwargs),
        _roll_recruit_age_lifespan=lambda *args, **kwargs: engine._roll_recruit_age_lifespan(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: engine._sect_members(*args, **kwargs),
        _select_npc_treasure=lambda *args, **kwargs: engine._select_npc_treasure(*args, **kwargs),
        _set_diplomatic_relation=lambda *args, **kwargs: engine._set_diplomatic_relation(*args, **kwargs),
        _stable_gender=lambda *args, **kwargs: engine._stable_gender(*args, **kwargs),
        _sync_relationship_records=lambda *args, **kwargs: engine._sync_relationship_records(*args, **kwargs),
        _vote_probability=lambda *args, **kwargs: engine._vote_probability(*args, **kwargs),
        intrigue_propose_resolution=lambda *args, **kwargs: engine.intrigue_propose_resolution(*args, **kwargs),
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
    )


def bind_encounter_actions(engine: GameEngine) -> EncounterActionDependencies:
    return EncounterActionDependencies(
        _add_enemy_party=lambda *args, **kwargs: engine._add_enemy_party(*args, **kwargs),
        _add_opportunity=lambda *args, **kwargs: engine._add_opportunity(*args, **kwargs),
        _advance_concubine_status=lambda *args, **kwargs: engine._advance_concubine_status(*args, **kwargs),
        _advance_soul_erosion_time=lambda *args, **kwargs: engine._advance_soul_erosion_time(*args, **kwargs),
        _annual_sect_update=lambda *args, **kwargs: engine._annual_sect_update(*args, **kwargs),
        _annual_world_npc_update=lambda *args, **kwargs: engine._annual_world_npc_update(*args, **kwargs),
        _apply_combat_action_rewards=lambda *args, **kwargs: engine._apply_combat_action_rewards(*args, **kwargs),
        _available_bounty_authorities=lambda *args, **kwargs: engine._available_bounty_authorities(*args, **kwargs),
        _cache_encounter_target=lambda *args, **kwargs: engine._cache_encounter_target(*args, **kwargs),
        _check_tribulation=lambda *args, **kwargs: engine._check_tribulation(*args, **kwargs),
        _combat=lambda *args, **kwargs: engine._combat(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _generate_cultivator_target=lambda *args, **kwargs: engine._generate_cultivator_target(*args, **kwargs),
        _has_family_voice=lambda *args, **kwargs: engine._has_family_voice(*args, **kwargs),
        _has_race_voice=lambda *args, **kwargs: engine._has_race_voice(*args, **kwargs),
        _has_sect_voice=lambda *args, **kwargs: engine._has_sect_voice(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _intrigue_sync_player_prison=lambda *args, **kwargs: engine._intrigue_sync_player_prison(*args, **kwargs),
        _known_npc_encounter_target=lambda *args, **kwargs: engine._known_npc_encounter_target(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _npc_cultivation_perception=lambda *args, **kwargs: engine._npc_cultivation_perception(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: engine._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: engine._player_allegiance_race(*args, **kwargs),
        _player_battle_power=lambda *args, **kwargs: engine._player_battle_power(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: engine._player_intrinsic_combat_power(*args, **kwargs),
        _player_protected_npc_ids=lambda *args, **kwargs: engine._player_protected_npc_ids(*args, **kwargs),
        _promote_cached_npc=lambda *args, **kwargs: engine._promote_cached_npc(*args, **kwargs),
        _record_world_coalition_amnesty=lambda *args, **kwargs: engine._record_world_coalition_amnesty(*args, **kwargs),
        _remember_faction_prison_release=lambda *args, **kwargs: engine._remember_faction_prison_release(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: engine._sage_scaled_gain(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: engine._sect_members(*args, **kwargs),
        _tianji_observe_npc=lambda *args, **kwargs: engine._tianji_observe_npc(*args, **kwargs),
        _tianji_preview_npc_power=lambda *args, **kwargs: engine._tianji_preview_npc_power(*args, **kwargs),
        _world_supports=lambda *args, **kwargs: engine._world_supports(*args, **kwargs),
        _get_events_by_id=lambda: engine.events_by_id,
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
    )


def bind_inventory_actions(engine: GameEngine, *, bloodline_content_available: Callable[[], bool]) -> InventoryDependencies:
    return InventoryDependencies(
        _add_opportunity=lambda *args, **kwargs: engine._add_opportunity(*args, **kwargs),
        _base_affinities=lambda *args, **kwargs: engine._base_affinities(*args, **kwargs),
        _buy_crafting_material_offer=lambda *args, **kwargs: engine._buy_crafting_material_offer(*args, **kwargs),
        _buy_formation_material_offer=lambda *args, **kwargs: engine._buy_formation_material_offer(*args, **kwargs),
        _buy_formation_supply_offer=lambda *args, **kwargs: engine._buy_formation_supply_offer(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _manual_breakthrough_kind=lambda *args, **kwargs: engine._manual_breakthrough_kind(*args, **kwargs),
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
        bloodline_content_available=bloodline_content_available,
    )


def bind_relationship_actions(engine: GameEngine) -> RelationshipActionDependencies:
    return RelationshipActionDependencies(
        _add_opportunity=lambda *args, **kwargs: engine._add_opportunity(*args, **kwargs),
        _adjust_person_affinity=lambda *args, **kwargs: engine._adjust_person_affinity(*args, **kwargs),
        _default_npc_main_technique=lambda *args, **kwargs: engine._default_npc_main_technique(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: engine._find_npc(*args, **kwargs),
        _hostility_key=lambda *args, **kwargs: engine._hostility_key(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _market_tier=lambda *args, **kwargs: engine._market_tier(*args, **kwargs),
        _npc_faction_id=lambda *args, **kwargs: engine._npc_faction_id(*args, **kwargs),
        _party_crossing_candidate=lambda *args, **kwargs: engine._party_crossing_candidate(*args, **kwargs),
        _party_invitation_chance=lambda *args, **kwargs: engine._party_invitation_chance(*args, **kwargs),
        _persist_relationship_npc=lambda *args, **kwargs: engine._persist_relationship_npc(*args, **kwargs),
        _promote_cached_npc=lambda *args, **kwargs: engine._promote_cached_npc(*args, **kwargs),
        _relationship_snapshot=lambda *args, **kwargs: engine._relationship_snapshot(*args, **kwargs),
        _sage_affinity_gain=lambda *args, **kwargs: engine._sage_affinity_gain(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: engine._sage_scaled_gain(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: engine._sect_members(*args, **kwargs),
        _set_person_affinity=lambda *args, **kwargs: engine._set_person_affinity(*args, **kwargs),
        _tianji_npc_conversation_clue=lambda *args, **kwargs: engine._tianji_npc_conversation_clue(*args, **kwargs),
        _try_conceive_child=lambda *args, **kwargs: engine._try_conceive_child(*args, **kwargs),
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
    )
