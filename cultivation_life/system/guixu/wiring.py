"""Resolve named collaborators at call time, preserving late overrides."""
from typing import Any, Callable
from .dependencies import (
    GuixuStateDependencies,
    GuixuCalendarDependencies,
    GuixuNpcsDependencies,
    GuixuRewardsDependencies,
    GuixuEncountersDependencies,
    GuixuActionsDependencies,
    GuixuPresentationDependencies,
    GuixuDependencies,
)


def bind_guixu_state(host, *, guixu_content_available: Callable[..., Any]) -> GuixuStateDependencies:
    return GuixuStateDependencies(
        _guixu_definitions=lambda *args, **kwargs: host._guixu_definitions(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _next_guixu_open=lambda *args, **kwargs: host._next_guixu_open(*args, **kwargs),
        guixu_content_available=guixu_content_available,
    )


def bind_guixu_calendar(host) -> GuixuCalendarDependencies:
    return GuixuCalendarDependencies(
        _announce_guixu_cycle=lambda *args, **kwargs: host._announce_guixu_cycle(*args, **kwargs),
        _assign_due_guixu_entries=lambda *args, **kwargs: host._assign_due_guixu_entries(*args, **kwargs),
        _close_guixu_cycle=lambda *args, **kwargs: host._close_guixu_cycle(*args, **kwargs),
        _ensure_guixu_state=lambda *args, **kwargs: host._ensure_guixu_state(*args, **kwargs),
        _form_guixu_npc_teams=lambda *args, **kwargs: host._form_guixu_npc_teams(*args, **kwargs),
        _generate_guixu_roster=lambda *args, **kwargs: host._generate_guixu_roster(*args, **kwargs),
        _guixu_definitions=lambda *args, **kwargs: host._guixu_definitions(*args, **kwargs),
        _guixu_elapsed_days=lambda *args, **kwargs: host._guixu_elapsed_days(*args, **kwargs),
        _guixu_entry_definition=lambda *args, **kwargs: host._guixu_entry_definition(*args, **kwargs),
        _guixu_settings=lambda *args, **kwargs: host._guixu_settings(*args, **kwargs),
        _guixu_weighted_key=lambda *args, **kwargs: host._guixu_weighted_key(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _open_guixu_cycle=lambda *args, **kwargs: host._open_guixu_cycle(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
        _get_maps=lambda: host.maps,
    )


def bind_guixu_npcs(host) -> GuixuNpcsDependencies:
    return GuixuNpcsDependencies(
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _dissolve_guixu_npc_team=lambda *args, **kwargs: host._dissolve_guixu_npc_team(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _form_guixu_npc_teams=lambda *args, **kwargs: host._form_guixu_npc_teams(*args, **kwargs),
        _guixu_entry_definition=lambda *args, **kwargs: host._guixu_entry_definition(*args, **kwargs),
        _guixu_npc_claim_entry=lambda *args, **kwargs: host._guixu_npc_claim_entry(*args, **kwargs),
        _guixu_relation_ids=lambda *args, **kwargs: host._guixu_relation_ids(*args, **kwargs),
        _guixu_settings=lambda *args, **kwargs: host._guixu_settings(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _resolve_guixu_npc_kill=lambda *args, **kwargs: host._resolve_guixu_npc_kill(*args, **kwargs),
        _simulate_guixu_npc_conflict=lambda *args, **kwargs: host._simulate_guixu_npc_conflict(*args, **kwargs),
    )


def bind_guixu_rewards(host) -> GuixuRewardsDependencies:
    return GuixuRewardsDependencies(
        _dissolve_guixu_npc_team=lambda *args, **kwargs: host._dissolve_guixu_npc_team(*args, **kwargs),
        _guixu_entry_definition=lambda *args, **kwargs: host._guixu_entry_definition(*args, **kwargs),
    )


def bind_guixu_encounters(host) -> GuixuEncountersDependencies:
    return GuixuEncountersDependencies(
        _break_guixu_relationship=lambda *args, **kwargs: host._break_guixu_relationship(*args, **kwargs),
        _combat=lambda *args, **kwargs: host._combat(*args, **kwargs),
        _consume_guixu_days=lambda *args, **kwargs: host._consume_guixu_days(*args, **kwargs),
        _dissolve_guixu_npc_team=lambda *args, **kwargs: host._dissolve_guixu_npc_team(*args, **kwargs),
        _guixu_active_team=lambda *args, **kwargs: host._guixu_active_team(*args, **kwargs),
        _guixu_fight=lambda *args, **kwargs: host._guixu_fight(*args, **kwargs),
        _guixu_grant_entry=lambda *args, **kwargs: host._guixu_grant_entry(*args, **kwargs),
        _guixu_relationship_role=lambda *args, **kwargs: host._guixu_relationship_role(*args, **kwargs),
        _guixu_settings=lambda *args, **kwargs: host._guixu_settings(*args, **kwargs),
        _guixu_transferable_player_entries=lambda *args, **kwargs: host._guixu_transferable_player_entries(*args, **kwargs),
    )


def bind_guixu_actions(host, *, _get_MOVE_COSTS: Callable[..., Any], decode_rng: Callable[..., Any], guixu_content_available: Callable[..., Any]) -> GuixuActionsDependencies:
    return GuixuActionsDependencies(
        _add_opportunity=lambda *args, **kwargs: host._add_opportunity(*args, **kwargs),
        _advance_soul_erosion_time=lambda *args, **kwargs: host._advance_soul_erosion_time(*args, **kwargs),
        _advance_world_year=lambda *args, **kwargs: host._advance_world_year(*args, **kwargs),
        _apply_action_resources=lambda *args, **kwargs: host._apply_action_resources(*args, **kwargs),
        _body_progress_required=lambda *args, **kwargs: host._body_progress_required(*args, **kwargs),
        _body_training_step=lambda *args, **kwargs: host._body_training_step(*args, **kwargs),
        _consume_guixu_days=lambda *args, **kwargs: host._consume_guixu_days(*args, **kwargs),
        _dissolve_guixu_npc_team=lambda *args, **kwargs: host._dissolve_guixu_npc_team(*args, **kwargs),
        _ensure_guixu_state=lambda *args, **kwargs: host._ensure_guixu_state(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _guixu_actor=lambda *args, **kwargs: host._guixu_actor(*args, **kwargs),
        _guixu_cycle_and_definition=lambda *args, **kwargs: host._guixu_cycle_and_definition(*args, **kwargs),
        _guixu_elapsed_days=lambda *args, **kwargs: host._guixu_elapsed_days(*args, **kwargs),
        _guixu_entry_definition=lambda *args, **kwargs: host._guixu_entry_definition(*args, **kwargs),
        _guixu_fight=lambda *args, **kwargs: host._guixu_fight(*args, **kwargs),
        _guixu_grant_entry=lambda *args, **kwargs: host._guixu_grant_entry(*args, **kwargs),
        _guixu_offer_team=lambda *args, **kwargs: host._guixu_offer_team(*args, **kwargs),
        _guixu_relationship_role=lambda *args, **kwargs: host._guixu_relationship_role(*args, **kwargs),
        _guixu_return_days=lambda *args, **kwargs: host._guixu_return_days(*args, **kwargs),
        _guixu_settings=lambda *args, **kwargs: host._guixu_settings(*args, **kwargs),
        _guixu_team_tick=lambda *args, **kwargs: host._guixu_team_tick(*args, **kwargs),
        _guixu_transferable_player_entries=lambda *args, **kwargs: host._guixu_transferable_player_entries(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _maybe_guixu_npc_threat=lambda *args, **kwargs: host._maybe_guixu_npc_threat(*args, **kwargs),
        _sense_training_step=lambda *args, **kwargs: host._sense_training_step(*args, **kwargs),
        _surrender_guixu_treasure=lambda *args, **kwargs: host._surrender_guixu_treasure(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        decode_rng=decode_rng,
        guixu_content_available=guixu_content_available,
        _get_MOVE_COSTS=_get_MOVE_COSTS,
    )


def bind_guixu_presentation(host, *, guixu_content_available: Callable[..., Any]) -> GuixuPresentationDependencies:
    return GuixuPresentationDependencies(
        _ensure_guixu_state=lambda *args, **kwargs: host._ensure_guixu_state(*args, **kwargs),
        _guixu_cycle_and_definition=lambda *args, **kwargs: host._guixu_cycle_and_definition(*args, **kwargs),
        _guixu_definitions=lambda *args, **kwargs: host._guixu_definitions(*args, **kwargs),
        _guixu_entry_definition=lambda *args, **kwargs: host._guixu_entry_definition(*args, **kwargs),
        _guixu_return_days=lambda *args, **kwargs: host._guixu_return_days(*args, **kwargs),
        _guixu_transferable_player_entries=lambda *args, **kwargs: host._guixu_transferable_player_entries(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: host._npc_realm_name(*args, **kwargs),
        _get_maps=lambda: host.maps,
        guixu_content_available=guixu_content_available,
    )


def bind_guixu(host, *, _get_MOVE_COSTS: Callable[..., Any], decode_rng: Callable[..., Any], guixu_content_available: Callable[..., Any]) -> GuixuDependencies:
    return GuixuDependencies(
        state=bind_guixu_state(host, guixu_content_available=guixu_content_available),
        calendar=bind_guixu_calendar(host),
        npcs=bind_guixu_npcs(host),
        rewards=bind_guixu_rewards(host),
        encounters=bind_guixu_encounters(host),
        actions=bind_guixu_actions(host, _get_MOVE_COSTS=_get_MOVE_COSTS, decode_rng=decode_rng, guixu_content_available=guixu_content_available),
        presentation=bind_guixu_presentation(host, guixu_content_available=guixu_content_available),
    )
