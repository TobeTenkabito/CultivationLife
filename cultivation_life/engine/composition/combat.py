"""Named dependency builders for combat."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..dependencies import (
    ImmortalTrialDependencies,
    CombatDependencies,
    BreakthroughDependencies,
    TrialDependencies,
)

if TYPE_CHECKING:
    from .. import GameEngine


def bind_immortal_trials(engine: GameEngine) -> ImmortalTrialDependencies:
    return ImmortalTrialDependencies(
        _get_events_by_id=lambda: engine.events_by_id,
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _complete_major_breakthrough=lambda *args, **kwargs: engine._complete_major_breakthrough(*args, **kwargs),
    )


def bind_combat_runtime(engine: GameEngine) -> CombatDependencies:
    return CombatDependencies(
        _apply_cultivator_kill=lambda *args, **kwargs: engine._apply_cultivator_kill(*args, **kwargs),
        _apply_support_damage=lambda *args, **kwargs: engine._apply_support_damage(*args, **kwargs),
        _capture_cultivator=lambda *args, **kwargs: engine._capture_cultivator(*args, **kwargs),
        _capture_defeated_ghost=lambda *args, **kwargs: engine._capture_defeated_ghost(*args, **kwargs),
        _check_sect_extinction=lambda *args, **kwargs: engine._check_sect_extinction(*args, **kwargs),
        _combat_battlefield_tags=lambda *args, **kwargs: engine._combat_battlefield_tags(*args, **kwargs),
        _combat_report_lead=lambda *args, **kwargs: engine._combat_report_lead(*args, **kwargs),
        _court_law_active=lambda *args, **kwargs: engine._court_law_active(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _ensure_war_shape=lambda *args, **kwargs: engine._ensure_war_shape(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: engine._find_npc(*args, **kwargs),
        _formation_rules=lambda *args, **kwargs: engine._formation_rules(*args, **kwargs),
        _grant_art_experience=lambda *args, **kwargs: engine._grant_art_experience(*args, **kwargs),
        _grant_demonic_kill_opportunity=lambda *args, **kwargs: engine._grant_demonic_kill_opportunity(*args, **kwargs),
        _ground_profile=lambda *args, **kwargs: engine._ground_profile(*args, **kwargs),
        _handle_same_sect_kill=lambda *args, **kwargs: engine._handle_same_sect_kill(*args, **kwargs),
        _hostility_key=lambda *args, **kwargs: engine._hostility_key(*args, **kwargs),
        _inject_tianji_npc_artifacts=lambda *args, **kwargs: engine._inject_tianji_npc_artifacts(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _is_wartime_opponent=lambda *args, **kwargs: engine._is_wartime_opponent(*args, **kwargs),
        _kill_generates_hostility=lambda *args, **kwargs: engine._kill_generates_hostility(*args, **kwargs),
        _local_ground_formation=lambda *args, **kwargs: engine._local_ground_formation(*args, **kwargs),
        _natal_artifact_combat_effects=lambda *args, **kwargs: engine._natal_artifact_combat_effects(*args, **kwargs),
        _npc_formation_power_multiplier=lambda *args, **kwargs: engine._npc_formation_power_multiplier(*args, **kwargs),
        _npc_formation_profile=lambda *args, **kwargs: engine._npc_formation_profile(*args, **kwargs),
        _participant_side=lambda *args, **kwargs: engine._participant_side(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: engine._player_allegiance_race(*args, **kwargs),
        _player_combat_units=lambda *args, **kwargs: engine._player_combat_units(*args, **kwargs),
        _post_battle_possession_candidates=lambda *args, **kwargs: engine._post_battle_possession_candidates(*args, **kwargs),
        _prepare_post_battle_possession=lambda *args, **kwargs: engine._prepare_post_battle_possession(*args, **kwargs),
        _public_party=lambda *args, **kwargs: engine._public_party(*args, **kwargs),
        _race_alliance=lambda *args, **kwargs: engine._race_alliance(*args, **kwargs),
        _record_player_combat=lambda *args, **kwargs: engine._record_player_combat(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: engine._sage_scaled_gain(*args, **kwargs),
        _story_unit_full_power=lambda *args, **kwargs: engine._story_unit_full_power(*args, **kwargs),
        _tianji_handle_npc_kill=lambda *args, **kwargs: engine._tianji_handle_npc_kill(*args, **kwargs),
        _world_supports=lambda *args, **kwargs: engine._world_supports(*args, **kwargs),
        _get_events_by_id=lambda: engine.events_by_id,
        _get_maps=lambda: engine.maps,
    )


def bind_breakthroughs(engine: GameEngine, *, bloodline_content_available: Callable[[], bool]) -> BreakthroughDependencies:
    return BreakthroughDependencies(
        _add_opportunity=lambda *args, **kwargs: engine._add_opportunity(*args, **kwargs),
        _breakthrough_chance=lambda *args, **kwargs: engine._breakthrough_chance(*args, **kwargs),
        _combat=lambda *args, **kwargs: engine._combat(*args, **kwargs),
        _complete_joint_companion_breakthrough=lambda *args, **kwargs: engine._complete_joint_companion_breakthrough(*args, **kwargs),
        _complete_major_breakthrough=lambda *args, **kwargs: engine._complete_major_breakthrough(*args, **kwargs),
        _complete_minor_breakthrough=lambda *args, **kwargs: engine._complete_minor_breakthrough(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: engine._find_npc(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _joint_companion_eligible=lambda *args, **kwargs: engine._joint_companion_eligible(*args, **kwargs),
        _manual_minor_layers=lambda *args, **kwargs: engine._manual_minor_layers(*args, **kwargs),
        _minor_layer_target=lambda *args, **kwargs: engine._minor_layer_target(*args, **kwargs),
        _minor_pity_bonus=lambda *args, **kwargs: engine._minor_pity_bonus(*args, **kwargs),
        _minor_pity_key=lambda *args, **kwargs: engine._minor_pity_key(*args, **kwargs),
        _npc_lifespan_multiplier=lambda *args, **kwargs: engine._npc_lifespan_multiplier(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _player_battle_power=lambda *args, **kwargs: engine._player_battle_power(*args, **kwargs),
        _queue_heavenly_demon_battle=lambda *args, **kwargs: engine._queue_heavenly_demon_battle(*args, **kwargs),
        _raise_divine_sense_one_level=lambda *args, **kwargs: engine._raise_divine_sense_one_level(*args, **kwargs),
        _root_probability_group=lambda *args, **kwargs: engine._root_probability_group(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: engine._sage_scaled_gain(*args, **kwargs),
        _start_breakthrough_trial=lambda *args, **kwargs: engine._start_breakthrough_trial(*args, **kwargs),
        _get_events_by_id=lambda: engine.events_by_id,
        bloodline_content_available=bloodline_content_available,
    )


def bind_trials(engine: GameEngine) -> TrialDependencies:
    return TrialDependencies(
        _plan_world_transition=lambda *args, **kwargs: engine._plan_world_transition(*args, **kwargs),
        _apply_world_transition=lambda *args, **kwargs: engine._apply_world_transition(*args, **kwargs),
        _body_tribulation_damage_reduction=lambda *args, **kwargs: engine._body_tribulation_damage_reduction(*args, **kwargs),
        _clear_market=lambda *args, **kwargs: engine._clear_market(*args, **kwargs),
        _complete_major_breakthrough=lambda *args, **kwargs: engine._complete_major_breakthrough(*args, **kwargs),
        _complete_minor_breakthrough=lambda *args, **kwargs: engine._complete_minor_breakthrough(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _ensure_heavenly_court=lambda *args, **kwargs: engine._ensure_heavenly_court(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: engine._ensure_market(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: engine._player_intrinsic_combat_power(*args, **kwargs),
        _prepare_permanent_world_transition=lambda *args, **kwargs: engine._prepare_permanent_world_transition(*args, **kwargs),
        _resolve_asura_ascension_step=lambda *args, **kwargs: engine._resolve_asura_ascension_step(*args, **kwargs),
        _resolve_celestial_ascension_step=lambda *args, **kwargs: engine._resolve_celestial_ascension_step(*args, **kwargs),
        _resolve_heavenly_demon_battle=lambda *args, **kwargs: engine._resolve_heavenly_demon_battle(*args, **kwargs),
        _resolve_selected_ascension_entourage=lambda *args, **kwargs: engine._resolve_selected_ascension_entourage(*args, **kwargs),
        _sage_scaled_gain=lambda *args, **kwargs: engine._sage_scaled_gain(*args, **kwargs),
        _tribulation_base_power_cap=lambda *args, **kwargs: engine._tribulation_base_power_cap(*args, **kwargs),
        _tribulation_damage_reduction=lambda *args, **kwargs: engine._tribulation_damage_reduction(*args, **kwargs),
        _get_events_by_id=lambda: engine.events_by_id,
        _get_maps=lambda: engine.maps,
    )
