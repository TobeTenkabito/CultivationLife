"""Named dependency builders for events."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..dependencies import (
    EventDependencies,
    ChoiceDependencies,
    EncounterDependencies,
    EffectDependencies,
)

if TYPE_CHECKING:
    from .. import GameEngine


def bind_event_runtime(engine: GameEngine) -> EventDependencies:
    return EventDependencies(
        _base_affinities=lambda *args, **kwargs: engine._base_affinities(*args, **kwargs),
        _cache_encounter_target=lambda *args, **kwargs: engine._cache_encounter_target(*args, **kwargs),
        _combat=lambda *args, **kwargs: engine._combat(*args, **kwargs),
        _condition=lambda *args, **kwargs: engine._condition(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _event_weight=lambda *args, **kwargs: engine._event_weight(*args, **kwargs),
        _generate_cultivator_target=lambda *args, **kwargs: engine._generate_cultivator_target(*args, **kwargs),
        _path=lambda *args, **kwargs: engine._path(*args, **kwargs),
        _record_revenge_trigger=lambda *args, **kwargs: engine._record_revenge_trigger(*args, **kwargs),
        _revenge_ready=lambda *args, **kwargs: engine._revenge_ready(*args, **kwargs),
        _story_unit_full_power=lambda *args, **kwargs: engine._story_unit_full_power(*args, **kwargs),
        _world_supports=lambda *args, **kwargs: engine._world_supports(*args, **kwargs),
        _get_events=lambda: engine.events,
        _get_events_by_id=lambda: engine.events_by_id,
    )


def bind_choices(engine: GameEngine) -> ChoiceDependencies:
    return ChoiceDependencies(
        _condition=lambda *args, **kwargs: engine._condition(*args, **kwargs),
        _diff=lambda *args, **kwargs: engine._diff(*args, **kwargs),
        _effect=lambda *args, **kwargs: engine._effect(*args, **kwargs),
        _enforce_guixu_rank_boundary=lambda *args, **kwargs: engine._enforce_guixu_rank_boundary(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: engine._ensure_market(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _maybe_artifact_synthesis=lambda *args, **kwargs: engine._maybe_artifact_synthesis(*args, **kwargs),
        _queue_followup_event=lambda *args, **kwargs: engine._queue_followup_event(*args, **kwargs),
        _resolve_breakthroughs=lambda *args, **kwargs: engine._resolve_breakthroughs(*args, **kwargs),
        _snapshot=lambda *args, **kwargs: engine._snapshot(*args, **kwargs),
        _get_events_by_id=lambda: engine.events_by_id,
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
    )


def bind_encounters(engine: GameEngine) -> EncounterDependencies:
    return EncounterDependencies(
        _add_enemy_party=lambda *args, **kwargs: engine._add_enemy_party(*args, **kwargs),
        _condition=lambda *args, **kwargs: engine._condition(*args, **kwargs),
        _encounter_person_name=lambda *args, **kwargs: engine._encounter_person_name(*args, **kwargs),
        _faction_meta=lambda *args, **kwargs: engine._faction_meta(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: engine._intrigue_enabled(*args, **kwargs),
        _intrigue_pressure_position_occupied=lambda *args, **kwargs: engine._intrigue_pressure_position_occupied(*args, **kwargs),
        _npc_cultivation_perception=lambda *args, **kwargs: engine._npc_cultivation_perception(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: engine._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: engine._player_allegiance_race(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: engine._player_intrinsic_combat_power(*args, **kwargs),
        _promote_cached_npc=lambda *args, **kwargs: engine._promote_cached_npc(*args, **kwargs),
        _random_npc_root=lambda *args, **kwargs: engine._random_npc_root(*args, **kwargs),
        _record_revenge_trigger=lambda *args, **kwargs: engine._record_revenge_trigger(*args, **kwargs),
        _revenge_ready=lambda *args, **kwargs: engine._revenge_ready(*args, **kwargs),
        _roll_escalating_event=lambda *args, **kwargs: engine._roll_escalating_event(*args, **kwargs),
        _scale_npc_lifespan=lambda *args, **kwargs: engine._scale_npc_lifespan(*args, **kwargs),
        _select_npc_treasure=lambda *args, **kwargs: engine._select_npc_treasure(*args, **kwargs),
        _world_realm_cap=lambda *args, **kwargs: engine._world_realm_cap(*args, **kwargs),
        _world_supports=lambda *args, **kwargs: engine._world_supports(*args, **kwargs),
        _would_enter_spirit_ranking=lambda *args, **kwargs: engine._would_enter_spirit_ranking(*args, **kwargs),
        _get_events=lambda: engine.events,
        _get_events_by_id=lambda: engine.events_by_id,
    )


def bind_effects(engine: GameEngine) -> EffectDependencies:
    return EffectDependencies(
        _plan_world_transition=lambda *args, **kwargs: engine._plan_world_transition(*args, **kwargs),
        _apply_world_transition=lambda *args, **kwargs: engine._apply_world_transition(*args, **kwargs),
        _add_court_merit=lambda *args, **kwargs: engine._add_court_merit(*args, **kwargs),
        _add_opportunity=lambda *args, **kwargs: engine._add_opportunity(*args, **kwargs),
        _adjust_person_affinity=lambda *args, **kwargs: engine._adjust_person_affinity(*args, **kwargs),
        _apply_combat_action_rewards=lambda *args, **kwargs: engine._apply_combat_action_rewards(*args, **kwargs),
        _ascension_destination=lambda *args, **kwargs: engine._ascension_destination(*args, **kwargs),
        _body_progress_required=lambda *args, **kwargs: engine._body_progress_required(*args, **kwargs),
        _cache_encounter_target=lambda *args, **kwargs: engine._cache_encounter_target(*args, **kwargs),
        _claim_treasure_reward=lambda *args, **kwargs: engine._claim_treasure_reward(*args, **kwargs),
        _clear_market=lambda *args, **kwargs: engine._clear_market(*args, **kwargs),
        _combat=lambda *args, **kwargs: engine._combat(*args, **kwargs),
        _complete_ghost_reincarnation=lambda *args, **kwargs: engine._complete_ghost_reincarnation(*args, **kwargs),
        _complete_immortal_conversion_stage=lambda *args, **kwargs: engine._complete_immortal_conversion_stage(*args, **kwargs),
        _court_law_active=lambda *args, **kwargs: engine._court_law_active(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _dissolve_player_sect=lambda *args, **kwargs: engine._dissolve_player_sect(*args, **kwargs),
        _ensure_intrigue_faction=lambda *args, **kwargs: engine._ensure_intrigue_faction(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: engine._find_npc(*args, **kwargs),
        _formation_rules=lambda *args, **kwargs: engine._formation_rules(*args, **kwargs),
        _generate_cultivator_target=lambda *args, **kwargs: engine._generate_cultivator_target(*args, **kwargs),
        _generated_relationship=lambda *args, **kwargs: engine._generated_relationship(*args, **kwargs),
        _grant_art_experience=lambda *args, **kwargs: engine._grant_art_experience(*args, **kwargs),
        _ground_profile=lambda *args, **kwargs: engine._ground_profile(*args, **kwargs),
        _hostility_key=lambda *args, **kwargs: engine._hostility_key(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _intrigue_position_specs=lambda *args, **kwargs: engine._intrigue_position_specs(*args, **kwargs),
        _intrigue_state=lambda *args, **kwargs: engine._intrigue_state(*args, **kwargs),
        _is_story_combat_check=lambda *args, **kwargs: engine._is_story_combat_check(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: engine._npc_power(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: engine._player_intrinsic_combat_power(*args, **kwargs),
        _prepare_permanent_world_transition=lambda *args, **kwargs: engine._prepare_permanent_world_transition(*args, **kwargs),
        _relationship_capture_step=lambda *args, **kwargs: engine._relationship_capture_step(*args, **kwargs),
        _resolve_concubine_escape=lambda *args, **kwargs: engine._resolve_concubine_escape(*args, **kwargs),
        _resolve_concubine_proposal=lambda *args, **kwargs: engine._resolve_concubine_proposal(*args, **kwargs),
        _resolve_concubine_revenge=lambda *args, **kwargs: engine._resolve_concubine_revenge(*args, **kwargs),
        _resolve_relationship_sanction=lambda *args, **kwargs: engine._resolve_relationship_sanction(*args, **kwargs),
        _resolve_story_combat_check=lambda *args, **kwargs: engine._resolve_story_combat_check(*args, **kwargs),
        _resolve_trial_step=lambda *args, **kwargs: engine._resolve_trial_step(*args, **kwargs),
        _resolve_wanted_response=lambda *args, **kwargs: engine._resolve_wanted_response(*args, **kwargs),
        _resolve_wanted_settlement=lambda *args, **kwargs: engine._resolve_wanted_settlement(*args, **kwargs),
        _resolve_war_vanguard=lambda *args, **kwargs: engine._resolve_war_vanguard(*args, **kwargs),
        _sage_affinity_gain=lambda *args, **kwargs: engine._sage_affinity_gain(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: engine._sage_scaled_gain(*args, **kwargs),
        _sect_guard_array=lambda *args, **kwargs: engine._sect_guard_array(*args, **kwargs),
        _sect_guard_power=lambda *args, **kwargs: engine._sect_guard_power(*args, **kwargs),
        _get_events_by_id=lambda: engine.events_by_id,
        grant_monster_imprint=lambda *args, **kwargs: engine.grant_monster_imprint(*args, **kwargs),
        _get_maps=lambda: engine.maps,
    )
