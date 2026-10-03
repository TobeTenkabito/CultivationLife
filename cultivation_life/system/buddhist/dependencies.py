"""Named ports for buddhist workflows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...models import GameState
from ...ports import MapPort, SavePort


@dataclass(frozen=True, slots=True)
class BuddhistActionDependencies:
    _buddhist_burden: Callable[..., Any]
    _buddhist_permissions: Callable[..., Any]
    _buddhist_record: Callable[..., Any]
    _continue_buddhist_assembly: Callable[..., Any]
    _ensure_buddhist_state: Callable[..., Any]
    _ensure_market: Callable[..., Any]
    _finish_buddhist_assembly: Callable[..., Any]
    _load: Callable[[str], GameState]
    _public_buddhist: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    nirvana: NirvanaDependencies
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class BuddhistAssemblyDependencies:
    _advance_soul_erosion_time: Callable[..., Any]
    _advance_world_year: Callable[..., Any]
    _buddhist_permissions: Callable[..., Any]
    _buddhist_record: Callable[..., Any]
    _combat: Callable[..., Any]
    _finish_buddhist_assembly: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class NirvanaDependencies:
    _buddhist_record: Callable[..., Any]
    _complete_minor_breakthrough: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class BuddhistFlowDependencies:
    actions: BuddhistActionDependencies
    assembly: BuddhistAssemblyDependencies
    nirvana: NirvanaDependencies

