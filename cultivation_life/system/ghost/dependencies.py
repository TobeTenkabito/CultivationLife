"""Named ports for ghost workflows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...models import GameState
from ...ports import MapPort, SavePort


@dataclass(frozen=True, slots=True)
class GhostIdentityDependencies:
    _advance_soul_erosion_time: Callable[..., Any]
    _advance_world_year: Callable[..., Any]
    _die: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _load: Callable[[str], GameState]
    _post_battle_possession_candidates: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class GhostCalendarDependencies:
    _all_world_npcs: Callable[..., Any]
    _ensure_ghost_parade: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _generate_parade_souls: Callable[..., Any]
    _maybe_transfer_player_dependency: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class GhostErosionDependencies:
    _apply_soul_erosion_units: Callable[..., Any]
    _die: Callable[..., Any]
    _load: Callable[[str], GameState]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class GhostReincarnationDependencies:
    _complete_ghost_reincarnation: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _load: Callable[[str], GameState]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class GhostFlowDependencies:
    identity: GhostIdentityDependencies
    calendar: GhostCalendarDependencies
    erosion: GhostErosionDependencies
    reincarnation: GhostReincarnationDependencies

