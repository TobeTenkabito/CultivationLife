"""Explicit composition; callbacks and resources resolve on use."""

from typing import Any, Callable


from .dependencies import (
    IntrigueGovernanceDependencies,
    IntrigueGuestsDependencies,
    IntriguePresentationDependencies,
    IntrigueRecruitmentDependencies,
    IntrigueResolutionsDependencies,
    IntrigueRuntimeDependencies,
    IntrigueStateDependencies,
    IntrigueDependencies,
)


def bind_governance(
    host, *, _get_PLAYER_ID: Callable[[], Any], intrigue_rules: Callable[..., Any]
) -> IntrigueGovernanceDependencies:
    return IntrigueGovernanceDependencies(
        _get_PLAYER_ID=_get_PLAYER_ID,
        _actual_player_realm=lambda *args, **kwargs: host._actual_player_realm(
            *args, **kwargs
        ),
        _ensure_intrigue_faction=lambda *args, **kwargs: host._ensure_intrigue_faction(
            *args, **kwargs
        ),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_entity=lambda *args, **kwargs: host._intrigue_entity(*args, **kwargs),
        _intrigue_faction_name=lambda *args, **kwargs: host._intrigue_faction_name(
            *args, **kwargs
        ),
        _intrigue_find_npc=lambda *args, **kwargs: host._intrigue_find_npc(
            *args, **kwargs
        ),
        _intrigue_has_control=lambda *args, **kwargs: host._intrigue_has_control(
            *args, **kwargs
        ),
        _intrigue_is_imprisoned=lambda *args, **kwargs: host._intrigue_is_imprisoned(
            *args, **kwargs
        ),
        _intrigue_key=lambda *args, **kwargs: host._intrigue_key(*args, **kwargs),
        _intrigue_members=lambda *args, **kwargs: host._intrigue_members(
            *args, **kwargs
        ),
        _intrigue_player_faction_id=lambda *args,
        **kwargs: host._intrigue_player_faction_id(*args, **kwargs),
        _intrigue_position_specs=lambda *args, **kwargs: host._intrigue_position_specs(
            *args, **kwargs
        ),
        _intrigue_state=lambda *args, **kwargs: host._intrigue_state(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args,
        **kwargs: host._player_intrinsic_combat_power(*args, **kwargs),
        _sage_affinity_gain=lambda *args, **kwargs: host._sage_affinity_gain(
            *args, **kwargs
        ),
        intrigue_rules=intrigue_rules,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_guests(
    host, *, _get_PLAYER_ID: Callable[[], Any]
) -> IntrigueGuestsDependencies:
    return IntrigueGuestsDependencies(
        _get_PLAYER_ID=_get_PLAYER_ID,
        _coalition_ids=lambda *args, **kwargs: host._coalition_ids(*args, **kwargs),
        _ensure_intrigue_faction=lambda *args, **kwargs: host._ensure_intrigue_faction(
            *args, **kwargs
        ),
        _ensure_intrigue_personality=lambda *args,
        **kwargs: host._ensure_intrigue_personality(*args, **kwargs),
        _intrigue_can_invite_guest=lambda *args,
        **kwargs: host._intrigue_can_invite_guest(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_entity=lambda *args, **kwargs: host._intrigue_entity(*args, **kwargs),
        _intrigue_faction_name=lambda *args, **kwargs: host._intrigue_faction_name(
            *args, **kwargs
        ),
        _intrigue_find_npc=lambda *args, **kwargs: host._intrigue_find_npc(
            *args, **kwargs
        ),
        _intrigue_guest_npcs=lambda *args, **kwargs: host._intrigue_guest_npcs(
            *args, **kwargs
        ),
        _intrigue_has_control=lambda *args, **kwargs: host._intrigue_has_control(
            *args, **kwargs
        ),
        _intrigue_is_imprisoned=lambda *args, **kwargs: host._intrigue_is_imprisoned(
            *args, **kwargs
        ),
        _intrigue_key=lambda *args, **kwargs: host._intrigue_key(*args, **kwargs),
        _intrigue_members=lambda *args, **kwargs: host._intrigue_members(
            *args, **kwargs
        ),
        _intrigue_player_faction_id=lambda *args,
        **kwargs: host._intrigue_player_faction_id(*args, **kwargs),
        _intrigue_player_relation=lambda *args,
        **kwargs: host._intrigue_player_relation(*args, **kwargs),
        _intrigue_position_specs=lambda *args, **kwargs: host._intrigue_position_specs(
            *args, **kwargs
        ),
        _intrigue_state=lambda *args, **kwargs: host._intrigue_state(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _npc_faction_id=lambda *args, **kwargs: host._npc_faction_id(*args, **kwargs),
        _persist_relationship_npc=lambda *args,
        **kwargs: host._persist_relationship_npc(*args, **kwargs),
        _sage_affinity_gain=lambda *args, **kwargs: host._sage_affinity_gain(
            *args, **kwargs
        ),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_presentation(
    host,
    *,
    _get_PERSONALITY_LABELS: Callable[[], Any],
    _get_PLAYER_ID: Callable[[], Any],
    _get_RESOLUTION_LABELS: Callable[[], Any],
    _get_STYLE_LABELS: Callable[[], Any],
) -> IntriguePresentationDependencies:
    return IntriguePresentationDependencies(
        _get_PERSONALITY_LABELS=_get_PERSONALITY_LABELS,
        _get_PLAYER_ID=_get_PLAYER_ID,
        _get_RESOLUTION_LABELS=_get_RESOLUTION_LABELS,
        _get_STYLE_LABELS=_get_STYLE_LABELS,
        _actual_player_realm=lambda *args, **kwargs: host._actual_player_realm(
            *args, **kwargs
        ),
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _ensure_intrigue_faction=lambda *args, **kwargs: host._ensure_intrigue_faction(
            *args, **kwargs
        ),
        _ensure_intrigue_personality=lambda *args,
        **kwargs: host._ensure_intrigue_personality(*args, **kwargs),
        _intrigue_can_invite_guest=lambda *args,
        **kwargs: host._intrigue_can_invite_guest(*args, **kwargs),
        _intrigue_decision_threshold=lambda *args,
        **kwargs: host._intrigue_decision_threshold(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_entity=lambda *args, **kwargs: host._intrigue_entity(*args, **kwargs),
        _intrigue_faction_name=lambda *args, **kwargs: host._intrigue_faction_name(
            *args, **kwargs
        ),
        _intrigue_find_npc=lambda *args, **kwargs: host._intrigue_find_npc(
            *args, **kwargs
        ),
        _intrigue_has_control=lambda *args, **kwargs: host._intrigue_has_control(
            *args, **kwargs
        ),
        _intrigue_has_decision_authority=lambda *args,
        **kwargs: host._intrigue_has_decision_authority(*args, **kwargs),
        _intrigue_is_imprisoned=lambda *args, **kwargs: host._intrigue_is_imprisoned(
            *args, **kwargs
        ),
        _intrigue_members=lambda *args, **kwargs: host._intrigue_members(
            *args, **kwargs
        ),
        _intrigue_player_faction_id=lambda *args,
        **kwargs: host._intrigue_player_faction_id(*args, **kwargs),
        _intrigue_player_relation=lambda *args,
        **kwargs: host._intrigue_player_relation(*args, **kwargs),
        _intrigue_position_specs=lambda *args, **kwargs: host._intrigue_position_specs(
            *args, **kwargs
        ),
        _intrigue_public_member=lambda *args, **kwargs: host._intrigue_public_member(
            *args, **kwargs
        ),
        _intrigue_recruitment_config=lambda *args,
        **kwargs: host._intrigue_recruitment_config(*args, **kwargs),
        _intrigue_recruitment_realm_options=lambda *args,
        **kwargs: host._intrigue_recruitment_realm_options(*args, **kwargs),
        _intrigue_state=lambda *args, **kwargs: host._intrigue_state(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _npc_root_name=lambda *args, **kwargs: host._npc_root_name(*args, **kwargs),
        _public_guest_invitation=lambda *args, **kwargs: host._public_guest_invitation(
            *args, **kwargs
        ),
        _public_intrigue_recruitment=lambda *args,
        **kwargs: host._public_intrigue_recruitment(*args, **kwargs),
        _world_supports=lambda *args, **kwargs: host._world_supports(*args, **kwargs),
    )


def bind_recruitment(
    host, *, _get_PLAYER_ID: Callable[[], Any]
) -> IntrigueRecruitmentDependencies:
    return IntrigueRecruitmentDependencies(
        _get_PLAYER_ID=_get_PLAYER_ID,
        _ensure_intrigue_faction=lambda *args, **kwargs: host._ensure_intrigue_faction(
            *args, **kwargs
        ),
        _ensure_intrigue_personality=lambda *args,
        **kwargs: host._ensure_intrigue_personality(*args, **kwargs),
        _intrigue_decision_threshold=lambda *args,
        **kwargs: host._intrigue_decision_threshold(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_has_decision_authority=lambda *args,
        **kwargs: host._intrigue_has_decision_authority(*args, **kwargs),
        _intrigue_player_faction_id=lambda *args,
        **kwargs: host._intrigue_player_faction_id(*args, **kwargs),
        _intrigue_recruitment_config=lambda *args,
        **kwargs: host._intrigue_recruitment_config(*args, **kwargs),
        _intrigue_recruitment_filter_summary=lambda *args,
        **kwargs: host._intrigue_recruitment_filter_summary(*args, **kwargs),
        _intrigue_recruitment_realm_options=lambda *args,
        **kwargs: host._intrigue_recruitment_realm_options(*args, **kwargs),
        _intrigue_resolve=lambda *args, **kwargs: host._intrigue_resolve(
            *args, **kwargs
        ),
        _intrigue_state=lambda *args, **kwargs: host._intrigue_state(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _normalize_intrigue_recruitment_filters=lambda *args,
        **kwargs: host._normalize_intrigue_recruitment_filters(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _random_npc_path=lambda *args, **kwargs: host._random_npc_path(*args, **kwargs),
        _random_npc_root=lambda *args, **kwargs: host._random_npc_root(*args, **kwargs),
        _recruit_realm_index=lambda *args, **kwargs: host._recruit_realm_index(
            *args, **kwargs
        ),
        _roll_recruit_age_lifespan=lambda *args,
        **kwargs: host._roll_recruit_age_lifespan(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: host._sect_members(*args, **kwargs),
        _select_npc_treasure=lambda *args, **kwargs: host._select_npc_treasure(
            *args, **kwargs
        ),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_resolutions(
    host,
    *,
    _get_PERSONALITY_LABELS: Callable[[], Any],
    _get_PLAYER_ID: Callable[[], Any],
    _get_RESOLUTION_LABELS: Callable[[], Any],
    _get_STYLE_LABELS: Callable[[], Any],
) -> IntrigueResolutionsDependencies:
    return IntrigueResolutionsDependencies(
        _get_PERSONALITY_LABELS=_get_PERSONALITY_LABELS,
        _get_PLAYER_ID=_get_PLAYER_ID,
        _get_RESOLUTION_LABELS=_get_RESOLUTION_LABELS,
        _get_STYLE_LABELS=_get_STYLE_LABELS,
        _active_war=lambda *args, **kwargs: host._active_war(*args, **kwargs),
        _add_war_participant=lambda *args, **kwargs: host._add_war_participant(
            *args, **kwargs
        ),
        _append_war_log=lambda *args, **kwargs: host._append_war_log(*args, **kwargs),
        _ensure_intrigue_faction=lambda *args, **kwargs: host._ensure_intrigue_faction(
            *args, **kwargs
        ),
        _ensure_intrigue_personality=lambda *args,
        **kwargs: host._ensure_intrigue_personality(*args, **kwargs),
        _generate_intrigue_recruitment_session=lambda *args,
        **kwargs: host._generate_intrigue_recruitment_session(*args, **kwargs),
        _intrigue_apply_resolution=lambda *args,
        **kwargs: host._intrigue_apply_resolution(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_entity=lambda *args, **kwargs: host._intrigue_entity(*args, **kwargs),
        _intrigue_faction_name=lambda *args, **kwargs: host._intrigue_faction_name(
            *args, **kwargs
        ),
        _intrigue_governance_style=lambda *args,
        **kwargs: host._intrigue_governance_style(*args, **kwargs),
        _intrigue_guest_npcs=lambda *args, **kwargs: host._intrigue_guest_npcs(
            *args, **kwargs
        ),
        _intrigue_has_decision_authority=lambda *args,
        **kwargs: host._intrigue_has_decision_authority(*args, **kwargs),
        _intrigue_is_imprisoned=lambda *args, **kwargs: host._intrigue_is_imprisoned(
            *args, **kwargs
        ),
        _intrigue_members=lambda *args, **kwargs: host._intrigue_members(
            *args, **kwargs
        ),
        _intrigue_player_faction_id=lambda *args,
        **kwargs: host._intrigue_player_faction_id(*args, **kwargs),
        _intrigue_resolve=lambda *args, **kwargs: host._intrigue_resolve(
            *args, **kwargs
        ),
        _intrigue_state=lambda *args, **kwargs: host._intrigue_state(*args, **kwargs),
        _intrigue_vote_chance=lambda *args, **kwargs: host._intrigue_vote_chance(
            *args, **kwargs
        ),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _normalize_intrigue_recruitment_filters=lambda *args,
        **kwargs: host._normalize_intrigue_recruitment_filters(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _participant_side=lambda *args, **kwargs: host._participant_side(
            *args, **kwargs
        ),
        _set_diplomatic_relation=lambda *args, **kwargs: host._set_diplomatic_relation(
            *args, **kwargs
        ),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_runtime(
    host,
    *,
    _get_PLAYER_ID: Callable[[], Any],
    _get_RESOLUTION_LABELS: Callable[[], Any],
    _get_STYLE_LABELS: Callable[[], Any],
) -> IntrigueRuntimeDependencies:
    return IntrigueRuntimeDependencies(
        _get_PLAYER_ID=_get_PLAYER_ID,
        _get_RESOLUTION_LABELS=_get_RESOLUTION_LABELS,
        _get_STYLE_LABELS=_get_STYLE_LABELS,
        _actual_player_realm=lambda *args, **kwargs: host._actual_player_realm(
            *args, **kwargs
        ),
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _ensure_intrigue_faction=lambda *args, **kwargs: host._ensure_intrigue_faction(
            *args, **kwargs
        ),
        _intrigue_decision_threshold=lambda *args,
        **kwargs: host._intrigue_decision_threshold(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_find_npc=lambda *args, **kwargs: host._intrigue_find_npc(
            *args, **kwargs
        ),
        _intrigue_governance_style=lambda *args,
        **kwargs: host._intrigue_governance_style(*args, **kwargs),
        _intrigue_has_decision_authority=lambda *args,
        **kwargs: host._intrigue_has_decision_authority(*args, **kwargs),
        _intrigue_members=lambda *args, **kwargs: host._intrigue_members(
            *args, **kwargs
        ),
        _intrigue_player_faction_id=lambda *args,
        **kwargs: host._intrigue_player_faction_id(*args, **kwargs),
        _intrigue_resolve=lambda *args, **kwargs: host._intrigue_resolve(
            *args, **kwargs
        ),
        _intrigue_state=lambda *args, **kwargs: host._intrigue_state(*args, **kwargs),
        _intrigue_sync_player_prison=lambda *args,
        **kwargs: host._intrigue_sync_player_prison(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: host._player_allegiance_race(
            *args, **kwargs
        ),
        _sect_members=lambda *args, **kwargs: host._sect_members(*args, **kwargs),
        _war_relation=lambda *args, **kwargs: host._war_relation(*args, **kwargs),
        _world_supports=lambda *args, **kwargs: host._world_supports(*args, **kwargs),
    )


def bind_state(
    host,
    *,
    _get_PERSONALITY_LABELS: Callable[[], Any],
    _get_PLAYER_ID: Callable[[], Any],
    _get_STYLE_LABELS: Callable[[], Any],
    intrigue_rules: Callable[..., Any],
) -> IntrigueStateDependencies:
    return IntrigueStateDependencies(
        _get_PERSONALITY_LABELS=_get_PERSONALITY_LABELS,
        _get_PLAYER_ID=_get_PLAYER_ID,
        _get_STYLE_LABELS=_get_STYLE_LABELS,
        _actual_player_realm=lambda *args, **kwargs: host._actual_player_realm(
            *args, **kwargs
        ),
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _ensure_intrigue_personality=lambda *args,
        **kwargs: host._ensure_intrigue_personality(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _intrigue_auto_appoint_player=lambda *args,
        **kwargs: host._intrigue_auto_appoint_player(*args, **kwargs),
        _intrigue_entity=lambda *args, **kwargs: host._intrigue_entity(*args, **kwargs),
        _intrigue_governance_style=lambda *args,
        **kwargs: host._intrigue_governance_style(*args, **kwargs),
        _intrigue_key=lambda *args, **kwargs: host._intrigue_key(*args, **kwargs),
        _intrigue_members=lambda *args, **kwargs: host._intrigue_members(
            *args, **kwargs
        ),
        _intrigue_player_faction_id=lambda *args,
        **kwargs: host._intrigue_player_faction_id(*args, **kwargs),
        _intrigue_position_specs=lambda *args, **kwargs: host._intrigue_position_specs(
            *args, **kwargs
        ),
        _intrigue_state=lambda *args, **kwargs: host._intrigue_state(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: host._player_allegiance_race(
            *args, **kwargs
        ),
        _sect_members=lambda *args, **kwargs: host._sect_members(*args, **kwargs),
        intrigue_rules=intrigue_rules,
    )


def bind_intrigue(
    host,
    *,
    _get_PERSONALITY_LABELS: Callable[[], Any],
    _get_PLAYER_ID: Callable[[], Any],
    _get_RESOLUTION_LABELS: Callable[[], Any],
    _get_STYLE_LABELS: Callable[[], Any],
    intrigue_rules: Callable[..., Any],
) -> IntrigueDependencies:
    return IntrigueDependencies(
        governance=bind_governance(
            host, _get_PLAYER_ID=_get_PLAYER_ID, intrigue_rules=intrigue_rules
        ),
        guests=bind_guests(host, _get_PLAYER_ID=_get_PLAYER_ID),
        presentation=bind_presentation(
            host,
            _get_PERSONALITY_LABELS=_get_PERSONALITY_LABELS,
            _get_PLAYER_ID=_get_PLAYER_ID,
            _get_RESOLUTION_LABELS=_get_RESOLUTION_LABELS,
            _get_STYLE_LABELS=_get_STYLE_LABELS,
        ),
        recruitment=bind_recruitment(host, _get_PLAYER_ID=_get_PLAYER_ID),
        resolutions=bind_resolutions(
            host,
            _get_PERSONALITY_LABELS=_get_PERSONALITY_LABELS,
            _get_PLAYER_ID=_get_PLAYER_ID,
            _get_RESOLUTION_LABELS=_get_RESOLUTION_LABELS,
            _get_STYLE_LABELS=_get_STYLE_LABELS,
        ),
        runtime=bind_runtime(
            host,
            _get_PLAYER_ID=_get_PLAYER_ID,
            _get_RESOLUTION_LABELS=_get_RESOLUTION_LABELS,
            _get_STYLE_LABELS=_get_STYLE_LABELS,
        ),
        state=bind_state(
            host,
            _get_PERSONALITY_LABELS=_get_PERSONALITY_LABELS,
            _get_PLAYER_ID=_get_PLAYER_ID,
            _get_STYLE_LABELS=_get_STYLE_LABELS,
            intrigue_rules=intrigue_rules,
        ),
    )
