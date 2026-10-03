"""Compose ghost flows; collaborators resolve at call time."""
from ...system.ghost.dependencies import (
    GhostCalendarDependencies,
    GhostErosionDependencies,
    GhostFlowDependencies,
    GhostIdentityDependencies,
    GhostReincarnationDependencies,
)


def bind_identity(host) -> GhostIdentityDependencies:
    return GhostIdentityDependencies(
        _advance_soul_erosion_time=lambda *args, **kwargs: host._advance_soul_erosion_time(*args, **kwargs),
        _advance_world_year=lambda *args, **kwargs: host._advance_world_year(*args, **kwargs),
        _die=lambda *args, **kwargs: host._die(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _post_battle_possession_candidates=lambda *args, **kwargs: host._post_battle_possession_candidates(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_calendar(host) -> GhostCalendarDependencies:
    return GhostCalendarDependencies(
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _ensure_ghost_parade=lambda *args, **kwargs: host._ensure_ghost_parade(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _generate_parade_souls=lambda *args, **kwargs: host._generate_parade_souls(*args, **kwargs),
        _maybe_transfer_player_dependency=lambda *args, **kwargs: host._maybe_transfer_player_dependency(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: host._npc_power(*args, **kwargs),
        _get_maps=lambda: host.maps,
    )


def bind_erosion(host) -> GhostErosionDependencies:
    return GhostErosionDependencies(
        _apply_soul_erosion_units=lambda *args, **kwargs: host._apply_soul_erosion_units(*args, **kwargs),
        _die=lambda *args, **kwargs: host._die(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_reincarnation(host) -> GhostReincarnationDependencies:
    return GhostReincarnationDependencies(
        _complete_ghost_reincarnation=lambda *args, **kwargs: host._complete_ghost_reincarnation(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_ghost_flows(host) -> GhostFlowDependencies:
    return GhostFlowDependencies(
        identity=bind_identity(host),
        calendar=bind_calendar(host),
        erosion=bind_erosion(host),
        reincarnation=bind_reincarnation(host),
    )
