"""Resolve named collaborators at call time, preserving late overrides."""
from typing import Any, Callable
from .dependencies import (
    WarStateDependencies,
    WarDiplomacyDependencies,
    WarPowerDependencies,
    WarCombatDependencies,
    WarLifecycleDependencies,
    WarPeaceDependencies,
    WarActionsDependencies,
    WarPresentationDependencies,
    WarDependencies,
)


def bind_war_state(host) -> WarStateDependencies:
    return WarStateDependencies(
        _active_war=lambda *args, **kwargs: host._active_war(*args, **kwargs),
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _coalition_ids=lambda *args, **kwargs: host._coalition_ids(*args, **kwargs),
        _ensure_war_shape=lambda *args, **kwargs: host._ensure_war_shape(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _intrigue_is_imprisoned=lambda *args, **kwargs: host._intrigue_is_imprisoned(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _participant_side=lambda *args, **kwargs: host._participant_side(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: host._player_allegiance_race(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: host._sect_members(*args, **kwargs),
        _start_war=lambda *args, **kwargs: host._start_war(*args, **kwargs),
        _war_npc=lambda *args, **kwargs: host._war_npc(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_sect=lambda *args, **kwargs: host._war_sect(*args, **kwargs),
        _get_maps=lambda: host.maps,
    )


def bind_war_diplomacy(host) -> WarDiplomacyDependencies:
    return WarDiplomacyDependencies(
        _active_war=lambda *args, **kwargs: host._active_war(*args, **kwargs),
        _add_war_participant=lambda *args, **kwargs: host._add_war_participant(*args, **kwargs),
        _allied_powers=lambda *args, **kwargs: host._allied_powers(*args, **kwargs),
        _append_war_log=lambda *args, **kwargs: host._append_war_log(*args, **kwargs),
        _coalition_ids=lambda *args, **kwargs: host._coalition_ids(*args, **kwargs),
        _ensure_war_shape=lambda *args, **kwargs: host._ensure_war_shape(*args, **kwargs),
        _has_family_voice=lambda *args, **kwargs: host._has_family_voice(*args, **kwargs),
        _has_race_voice=lambda *args, **kwargs: host._has_race_voice(*args, **kwargs),
        _has_sect_voice=lambda *args, **kwargs: host._has_sect_voice(*args, **kwargs),
        _intrigue_defensive_guest_ids=lambda *args, **kwargs: host._intrigue_defensive_guest_ids(*args, **kwargs),
        _intrigue_player_guest_side=lambda *args, **kwargs: host._intrigue_player_guest_side(*args, **kwargs),
        _participant_side=lambda *args, **kwargs: host._participant_side(*args, **kwargs),
        _player_has_war_voice=lambda *args, **kwargs: host._player_has_war_voice(*args, **kwargs),
        _player_war_side=lambda *args, **kwargs: host._player_war_side(*args, **kwargs),
        _power_exists_in_world=lambda *args, **kwargs: host._power_exists_in_world(*args, **kwargs),
        _war_player_identity=lambda *args, **kwargs: host._war_player_identity(*args, **kwargs),
        _war_relation=lambda *args, **kwargs: host._war_relation(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_side_members=lambda *args, **kwargs: host._war_side_members(*args, **kwargs),
        _war_side_name=lambda *args, **kwargs: host._war_side_name(*args, **kwargs),
        _war_total_power=lambda *args, **kwargs: host._war_total_power(*args, **kwargs),
        _war_world=lambda *args, **kwargs: host._war_world(*args, **kwargs),
    )


def bind_war_power(host) -> WarPowerDependencies:
    return WarPowerDependencies(
        _available_warriors=lambda *args, **kwargs: host._available_warriors(*args, **kwargs),
        _coalition_ids=lambda *args, **kwargs: host._coalition_ids(*args, **kwargs),
        _ground_profile=lambda *args, **kwargs: host._ground_profile(*args, **kwargs),
        _npc_formation_power_multiplier=lambda *args, **kwargs: host._npc_formation_power_multiplier(*args, **kwargs),
        _npc_formation_profile=lambda *args, **kwargs: host._npc_formation_profile(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: host._player_intrinsic_combat_power(*args, **kwargs),
        _sect_guard_array=lambda *args, **kwargs: host._sect_guard_array(*args, **kwargs),
        _sect_guard_power=lambda *args, **kwargs: host._sect_guard_power(*args, **kwargs),
        _war_formation_metric_score=lambda *args, **kwargs: host._war_formation_metric_score(*args, **kwargs),
        _war_formation_modifier=lambda *args, **kwargs: host._war_formation_modifier(*args, **kwargs),
        _war_player_identity=lambda *args, **kwargs: host._war_player_identity(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_side_formation=lambda *args, **kwargs: host._war_side_formation(*args, **kwargs),
        _war_side_name=lambda *args, **kwargs: host._war_side_name(*args, **kwargs),
        _war_total_power=lambda *args, **kwargs: host._war_total_power(*args, **kwargs),
    )


def bind_war_combat(host) -> WarCombatDependencies:
    return WarCombatDependencies(
        _append_war_log=lambda *args, **kwargs: host._append_war_log(*args, **kwargs),
        _available_warriors=lambda *args, **kwargs: host._available_warriors(*args, **kwargs),
        _combat=lambda *args, **kwargs: host._combat(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _finish_war_by_morale=lambda *args, **kwargs: host._finish_war_by_morale(*args, **kwargs),
        _maybe_transfer_player_dependency=lambda *args, **kwargs: host._maybe_transfer_player_dependency(*args, **kwargs),
        _npc_faction_id=lambda *args, **kwargs: host._npc_faction_id(*args, **kwargs),
        _npc_formation_power_multiplier=lambda *args, **kwargs: host._npc_formation_power_multiplier(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _player_has_war_voice=lambda *args, **kwargs: host._player_has_war_voice(*args, **kwargs),
        _player_war_side=lambda *args, **kwargs: host._player_war_side(*args, **kwargs),
        _resolve_field_attack=lambda *args, **kwargs: host._resolve_field_attack(*args, **kwargs),
        _shift_war_morale=lambda *args, **kwargs: host._shift_war_morale(*args, **kwargs),
        _war_defeat_probabilities=lambda *args, **kwargs: host._war_defeat_probabilities(*args, **kwargs),
        _war_formation_contexts=lambda *args, **kwargs: host._war_formation_contexts(*args, **kwargs),
        _war_formation_text=lambda *args, **kwargs: host._war_formation_text(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_side_name=lambda *args, **kwargs: host._war_side_name(*args, **kwargs),
        _wear_war_guard_arrays=lambda *args, **kwargs: host._wear_war_guard_arrays(*args, **kwargs),
    )


def bind_war_lifecycle(host) -> WarLifecycleDependencies:
    return WarLifecycleDependencies(
        _append_war_log=lambda *args, **kwargs: host._append_war_log(*args, **kwargs),
        _available_warriors=lambda *args, **kwargs: host._available_warriors(*args, **kwargs),
        _call_war_allies=lambda *args, **kwargs: host._call_war_allies(*args, **kwargs),
        _conclude_war=lambda *args, **kwargs: host._conclude_war(*args, **kwargs),
        _conclude_war_bundle=lambda *args, **kwargs: host._conclude_war_bundle(*args, **kwargs),
        _ensure_war_shape=lambda *args, **kwargs: host._ensure_war_shape(*args, **kwargs),
        _finish_war_by_morale=lambda *args, **kwargs: host._finish_war_by_morale(*args, **kwargs),
        _generate_ai_peace_offer=lambda *args, **kwargs: host._generate_ai_peace_offer(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _player_has_war_voice=lambda *args, **kwargs: host._player_has_war_voice(*args, **kwargs),
        _player_war_side=lambda *args, **kwargs: host._player_war_side(*args, **kwargs),
        _resolve_abstract_defeat=lambda *args, **kwargs: host._resolve_abstract_defeat(*args, **kwargs),
        _resolve_field_attack=lambda *args, **kwargs: host._resolve_field_attack(*args, **kwargs),
        _shift_war_morale=lambda *args, **kwargs: host._shift_war_morale(*args, **kwargs),
        _war_formation_contexts=lambda *args, **kwargs: host._war_formation_contexts(*args, **kwargs),
        _war_formation_text=lambda *args, **kwargs: host._war_formation_text(*args, **kwargs),
        _war_power_profile=lambda *args, **kwargs: host._war_power_profile(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_side_name=lambda *args, **kwargs: host._war_side_name(*args, **kwargs),
        _wear_war_guard_arrays=lambda *args, **kwargs: host._wear_war_guard_arrays(*args, **kwargs),
    )


def bind_war_peace(host, *, _get_WAR_TERM_DEFS: Callable[..., Any], decode_rng: Callable[..., Any]) -> WarPeaceDependencies:
    return WarPeaceDependencies(
        _append_war_log=lambda *args, **kwargs: host._append_war_log(*args, **kwargs),
        _available_warriors=lambda *args, **kwargs: host._available_warriors(*args, **kwargs),
        _coalition_ids=lambda *args, **kwargs: host._coalition_ids(*args, **kwargs),
        _conclude_war=lambda *args, **kwargs: host._conclude_war(*args, **kwargs),
        _ensure_war_shape=lambda *args, **kwargs: host._ensure_war_shape(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(*args, **kwargs),
        _intrigue_resolve=lambda *args, **kwargs: host._intrigue_resolve(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _player_has_war_voice=lambda *args, **kwargs: host._player_has_war_voice(*args, **kwargs),
        _player_war_side=lambda *args, **kwargs: host._player_war_side(*args, **kwargs),
        _record_former_jailer_dissolved=lambda *args, **kwargs: host._record_former_jailer_dissolved(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: host._sect_members(*args, **kwargs),
        _set_diplomatic_relation=lambda *args, **kwargs: host._set_diplomatic_relation(*args, **kwargs),
        _war_entity_power=lambda *args, **kwargs: host._war_entity_power(*args, **kwargs),
        _war_player_identity=lambda *args, **kwargs: host._war_player_identity(*args, **kwargs),
        _war_relation=lambda *args, **kwargs: host._war_relation(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_sect=lambda *args, **kwargs: host._war_sect(*args, **kwargs),
        _war_side_name=lambda *args, **kwargs: host._war_side_name(*args, **kwargs),
        _war_total_power=lambda *args, **kwargs: host._war_total_power(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        decode_rng=decode_rng,
        _get_WAR_TERM_DEFS=_get_WAR_TERM_DEFS,
    )


def bind_war_actions(host, *, decode_rng: Callable[..., Any]) -> WarActionsDependencies:
    return WarActionsDependencies(
        _append_war_log=lambda *args, **kwargs: host._append_war_log(*args, **kwargs),
        _available_warriors=lambda *args, **kwargs: host._available_warriors(*args, **kwargs),
        _call_war_allies=lambda *args, **kwargs: host._call_war_allies(*args, **kwargs),
        _conclude_war_bundle=lambda *args, **kwargs: host._conclude_war_bundle(*args, **kwargs),
        _ensure_war_shape=lambda *args, **kwargs: host._ensure_war_shape(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _finish_war_by_morale=lambda *args, **kwargs: host._finish_war_by_morale(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _npc_faction_id=lambda *args, **kwargs: host._npc_faction_id(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: host._npc_realm_name(*args, **kwargs),
        _participant_side=lambda *args, **kwargs: host._participant_side(*args, **kwargs),
        _player_has_war_voice=lambda *args, **kwargs: host._player_has_war_voice(*args, **kwargs),
        _player_war_side=lambda *args, **kwargs: host._player_war_side(*args, **kwargs),
        _resolve_field_attack=lambda *args, **kwargs: host._resolve_field_attack(*args, **kwargs),
        _resolve_player_war_round=lambda *args, **kwargs: host._resolve_player_war_round(*args, **kwargs),
        _war_formation_contexts=lambda *args, **kwargs: host._war_formation_contexts(*args, **kwargs),
        _war_formation_text=lambda *args, **kwargs: host._war_formation_text(*args, **kwargs),
        _war_player_identity=lambda *args, **kwargs: host._war_player_identity(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_side_name=lambda *args, **kwargs: host._war_side_name(*args, **kwargs),
        _wear_war_guard_arrays=lambda *args, **kwargs: host._wear_war_guard_arrays(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
        _get_maps=lambda: host.maps,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        decode_rng=decode_rng,
    )


def bind_war_presentation(host, *, _get_WAR_TERM_DEFS: Callable[..., Any]) -> WarPresentationDependencies:
    return WarPresentationDependencies(
        _allied_powers=lambda *args, **kwargs: host._allied_powers(*args, **kwargs),
        _ensure_war_shape=lambda *args, **kwargs: host._ensure_war_shape(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: host._npc_realm_name(*args, **kwargs),
        _participant_side=lambda *args, **kwargs: host._participant_side(*args, **kwargs),
        _player_has_war_voice=lambda *args, **kwargs: host._player_has_war_voice(*args, **kwargs),
        _player_war_side=lambda *args, **kwargs: host._player_war_side(*args, **kwargs),
        _war_formation_contexts=lambda *args, **kwargs: host._war_formation_contexts(*args, **kwargs),
        _war_power_profile=lambda *args, **kwargs: host._war_power_profile(*args, **kwargs),
        _war_rules=lambda *args, **kwargs: host._war_rules(*args, **kwargs),
        _war_side_name=lambda *args, **kwargs: host._war_side_name(*args, **kwargs),
        _get_WAR_TERM_DEFS=_get_WAR_TERM_DEFS,
    )


def bind_war(host, *, _get_WAR_TERM_DEFS: Callable[..., Any], decode_rng: Callable[..., Any]) -> WarDependencies:
    return WarDependencies(
        state=bind_war_state(host),
        diplomacy=bind_war_diplomacy(host),
        power=bind_war_power(host),
        combat=bind_war_combat(host),
        lifecycle=bind_war_lifecycle(host),
        peace=bind_war_peace(host, _get_WAR_TERM_DEFS=_get_WAR_TERM_DEFS, decode_rng=decode_rng),
        actions=bind_war_actions(host, decode_rng=decode_rng),
        presentation=bind_war_presentation(host, _get_WAR_TERM_DEFS=_get_WAR_TERM_DEFS),
    )
