"""Resolve named collaborators at call time, preserving late overrides."""

from typing import Any, Callable
from .dependencies import (
    FormationMarketDependencies,
    FormationLoadoutsDependencies,
    FormationGroundDependencies,
    FormationNpcsDependencies,
    FormationPresentationDependencies,
    FormationDependencies,
)


def bind_formation_market(
    host,
    *,
    _get_NATURE_NAMES: Callable[..., Any],
    make_formation_material_instance: Callable[..., Any],
) -> FormationMarketDependencies:
    return FormationMarketDependencies(
        _formation_maintenance_defs=lambda *args,
        **kwargs: host._formation_maintenance_defs(*args, **kwargs),
        _formation_material_defs=lambda *args, **kwargs: host._formation_material_defs(
            *args, **kwargs
        ),
        _formation_rules=lambda *args, **kwargs: host._formation_rules(*args, **kwargs),
        make_formation_material_instance=make_formation_material_instance,
        _get_NATURE_NAMES=_get_NATURE_NAMES,
    )


def bind_formation_loadouts(
    host,
    *,
    _profile_from_bindings: Callable[..., Any],
    active_formation_profile: Callable[..., Any],
    calculate_formation_profile: Callable[..., Any],
    ensure_formation_state: Callable[..., Any],
    formation_alpha: Callable[..., Any],
    formation_shared_definitions: Callable[..., Any],
) -> FormationLoadoutsDependencies:
    return FormationLoadoutsDependencies(
        _activate_loadout=lambda *args, **kwargs: host._activate_loadout(
            *args, **kwargs
        ),
        _extract_candidate=lambda *args, **kwargs: host._extract_candidate(
            *args, **kwargs
        ),
        _formation_candidate=lambda *args, **kwargs: host._formation_candidate(
            *args, **kwargs
        ),
        _formation_candidates=lambda *args, **kwargs: host._formation_candidates(
            *args, **kwargs
        ),
        _formation_material_defs=lambda *args, **kwargs: host._formation_material_defs(
            *args, **kwargs
        ),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _nodes_from_candidate_ids=lambda *args,
        **kwargs: host._nodes_from_candidate_ids(*args, **kwargs),
        _release_active_formation=lambda *args,
        **kwargs: host._release_active_formation(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        _profile_from_bindings=_profile_from_bindings,
        active_formation_profile=active_formation_profile,
        calculate_formation_profile=calculate_formation_profile,
        ensure_formation_state=ensure_formation_state,
        formation_alpha=formation_alpha,
        formation_shared_definitions=formation_shared_definitions,
    )


def bind_formation_ground(
    host,
    *,
    active_formation_profile: Callable[..., Any],
    ensure_formation_state: Callable[..., Any],
    ground_formation_power: Callable[..., Any],
) -> FormationGroundDependencies:
    return FormationGroundDependencies(
        _coalition_ids=lambda *args, **kwargs: host._coalition_ids(*args, **kwargs),
        _formation_maintenance_defs=lambda *args,
        **kwargs: host._formation_maintenance_defs(*args, **kwargs),
        _formation_rules=lambda *args, **kwargs: host._formation_rules(*args, **kwargs),
        _ground_array_public=lambda *args, **kwargs: host._ground_array_public(
            *args, **kwargs
        ),
        _ground_profile=lambda *args, **kwargs: host._ground_profile(*args, **kwargs),
        _has_sect_voice=lambda *args, **kwargs: host._has_sect_voice(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_has_control=lambda *args, **kwargs: host._intrigue_has_control(
            *args, **kwargs
        ),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _release_bindings=lambda *args, **kwargs: host._release_bindings(
            *args, **kwargs
        ),
        _require_ground_array_access=lambda *args,
        **kwargs: host._require_ground_array_access(*args, **kwargs),
        _sect_guard_array=lambda *args, **kwargs: host._sect_guard_array(
            *args, **kwargs
        ),
        _get_maps=lambda: host.maps,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        active_formation_profile=active_formation_profile,
        ensure_formation_state=ensure_formation_state,
        ground_formation_power=ground_formation_power,
    )


def bind_formation_npcs(
    host,
    *,
    _cached_npc_formation_profile: Callable[..., Any],
    _get_NATURE_NAMES: Callable[..., Any],
    empty_formation_profile: Callable[..., Any],
) -> FormationNpcsDependencies:
    return FormationNpcsDependencies(
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _formation_material_defs=lambda *args, **kwargs: host._formation_material_defs(
            *args, **kwargs
        ),
        _formation_rules=lambda *args, **kwargs: host._formation_rules(*args, **kwargs),
        _npc_formation_profile=lambda *args, **kwargs: host._npc_formation_profile(
            *args, **kwargs
        ),
        _cached_npc_formation_profile=_cached_npc_formation_profile,
        empty_formation_profile=empty_formation_profile,
        _get_NATURE_NAMES=_get_NATURE_NAMES,
    )


def bind_formation_presentation(
    host,
    *,
    active_formation_profile: Callable[..., Any],
    ensure_formation_state: Callable[..., Any],
    formation_alpha: Callable[..., Any],
    formation_config: Callable[..., Any],
    formation_level: Callable[..., Any],
) -> FormationPresentationDependencies:
    return FormationPresentationDependencies(
        _formation_candidates=lambda *args, **kwargs: host._formation_candidates(
            *args, **kwargs
        ),
        _formation_maintenance_defs=lambda *args,
        **kwargs: host._formation_maintenance_defs(*args, **kwargs),
        _ground_array_public=lambda *args, **kwargs: host._ground_array_public(
            *args, **kwargs
        ),
        _has_sect_voice=lambda *args, **kwargs: host._has_sect_voice(*args, **kwargs),
        _intrigue_enabled=lambda *args, **kwargs: host._intrigue_enabled(
            *args, **kwargs
        ),
        _intrigue_has_control=lambda *args, **kwargs: host._intrigue_has_control(
            *args, **kwargs
        ),
        _get_maps=lambda: host.maps,
        active_formation_profile=active_formation_profile,
        ensure_formation_state=ensure_formation_state,
        formation_alpha=formation_alpha,
        formation_config=formation_config,
        formation_level=formation_level,
    )


def bind_formation(
    host,
    *,
    _cached_npc_formation_profile: Callable[..., Any],
    _get_NATURE_NAMES: Callable[..., Any],
    _profile_from_bindings: Callable[..., Any],
    active_formation_profile: Callable[..., Any],
    calculate_formation_profile: Callable[..., Any],
    empty_formation_profile: Callable[..., Any],
    ensure_formation_state: Callable[..., Any],
    formation_alpha: Callable[..., Any],
    formation_config: Callable[..., Any],
    formation_level: Callable[..., Any],
    formation_shared_definitions: Callable[..., Any],
    ground_formation_power: Callable[..., Any],
    make_formation_material_instance: Callable[..., Any],
) -> FormationDependencies:
    return FormationDependencies(
        market=bind_formation_market(
            host,
            _get_NATURE_NAMES=_get_NATURE_NAMES,
            make_formation_material_instance=make_formation_material_instance,
        ),
        loadouts=bind_formation_loadouts(
            host,
            _profile_from_bindings=_profile_from_bindings,
            active_formation_profile=active_formation_profile,
            calculate_formation_profile=calculate_formation_profile,
            ensure_formation_state=ensure_formation_state,
            formation_alpha=formation_alpha,
            formation_shared_definitions=formation_shared_definitions,
        ),
        ground=bind_formation_ground(
            host,
            active_formation_profile=active_formation_profile,
            ensure_formation_state=ensure_formation_state,
            ground_formation_power=ground_formation_power,
        ),
        npcs=bind_formation_npcs(
            host,
            _cached_npc_formation_profile=_cached_npc_formation_profile,
            _get_NATURE_NAMES=_get_NATURE_NAMES,
            empty_formation_profile=empty_formation_profile,
        ),
        presentation=bind_formation_presentation(
            host,
            active_formation_profile=active_formation_profile,
            ensure_formation_state=ensure_formation_state,
            formation_alpha=formation_alpha,
            formation_config=formation_config,
            formation_level=formation_level,
        ),
    )
