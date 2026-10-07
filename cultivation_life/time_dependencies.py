"""Named capabilities for independently executable game operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .models import GameState
from .ports import MapPort, SavePort


@dataclass(frozen=True, slots=True)
class WorldYearDependencies:
    _advance_buddhist_year: Callable[..., Any]
    _advance_ghost_phase_two_year: Callable[..., Any]
    _advance_guixu_calendar: Callable[..., Any]
    _advance_merchant_year: Callable[..., Any]
    _advance_monster_bloodline_year: Callable[..., Any]
    _advance_sage_year: Callable[..., Any]
    _annual_demonic_update: Callable[..., Any]
    _annual_sect_update: Callable[..., Any]
    _annual_spirit_field_update: Callable[..., Any]
    _annual_world_npc_update: Callable[..., Any]
    _check_tribulation: Callable[..., Any]
    _die: Callable[..., Any]
    _maybe_artifact_synthesis: Callable[..., Any]
    _maybe_mortal_root_completion: Callable[..., Any]
    _maybe_race_war_ambush: Callable[..., Any]
    _maybe_wanted_encounter: Callable[..., Any]
    _resolve_breakthroughs: Callable[..., Any]
    advance_researchers: Callable[..., Any] | None = None
    advance_caravans: Callable[..., Any] | None = None


@dataclass(frozen=True, slots=True)
class ElapsedYearDependencies:
    _advance_world_year: Callable[..., bool]
    _advance_soul_erosion_time: Callable[..., bool]


@dataclass(frozen=True, slots=True)
class MapTravelDependencies:
    year: ElapsedYearDependencies
    _clear_market: Callable[..., Any]
    _compact_world_history: Callable[..., Any]
    _die: Callable[..., Any]
    _ensure_market: Callable[..., Any]
    _finish_travel_time: Callable[..., Any]
    _load: Callable[[str], GameState]
    _monster_travel_multiplier: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class TeleportDependencies:
    _clear_market: Callable[..., Any]
    _ensure_market: Callable[..., Any]
    _instant_arrival: Callable[..., Any]
    _load: Callable[[str], GameState]
    _get_maps: Callable[[], MapPort]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class TimeSettlementDependencies:
    _advance_auction_clock: Callable[..., Any]
    _advance_concubine_aftermath: Callable[..., Any]
    _advance_concubine_status: Callable[..., Any]
    _advance_diplomacy_unit: Callable[..., Any]
    _advance_exchange_clock: Callable[..., Any]
    _advance_heavenly_court_unit: Callable[..., Any]
    _advance_intrigue_unit: Callable[..., Any]
    _advance_natal_artifact: Callable[..., Any]
    _advance_player_bounties: Callable[..., Any]
    _record_era_summary: Callable[..., Any]
    _maybe_tianji_intelligence_event: Callable[..., str | None] | None = None


@dataclass(frozen=True, slots=True)
class ElapsedTravelDependencies(TimeSettlementDependencies):
    """Existing travel settlement contract, now backed by common phases."""


@dataclass(frozen=True, slots=True)
class TimeDependencies:
    world_year: WorldYearDependencies
    elapsed_travel: ElapsedTravelDependencies
    travel: MapTravelDependencies
    teleport: TeleportDependencies
