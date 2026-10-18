"""Named capabilities for independently executable game operations."""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any, Callable, Protocol

from .models import GameState, Player
from .ports import MapPort, SavePort


class WorldYearPort(Protocol):
    def __call__(
        self, game: GameState, rng: Random, news: list[str], *, encounters: bool = True,
    ) -> bool: ...


class SectYearPort(Protocol):
    def __call__(
        self, game: GameState, rng: Random, *, personal: bool = True,
    ) -> list[str]: ...


class TravelSettlementPort(Protocol):
    def __call__(
        self, game: GameState, start_age: int, institution_world: str,
        institution_unit: int, news: list[str], rng: Random, *, action_units: int | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class WorldYearDependencies:
    _advance_buddhist_year: Callable[[GameState], list[str]]
    _advance_ghost_phase_two_year: Callable[[GameState, Random], None]
    _advance_guixu_calendar: Callable[[GameState, Random, list[str]], bool]
    _advance_merchant_year: Callable[[GameState], None]
    _advance_monster_bloodline_year: Callable[[GameState], None]
    _advance_sage_year: Callable[[GameState, Random], list[str]]
    _annual_demonic_update: Callable[[GameState, Random], None]
    _annual_sect_update: SectYearPort
    _annual_spirit_field_update: Callable[[Player], None]
    _annual_world_npc_update: Callable[[GameState, Random], list[str]]
    _check_tribulation: Callable[[GameState, Random], None]
    _die: Callable[[GameState, str, str], None]
    _maybe_artifact_synthesis: Callable[[GameState, Random], bool]
    _maybe_mortal_root_completion: Callable[[GameState, Random], bool]
    _maybe_race_war_ambush: Callable[[GameState, Random], bool]
    _maybe_wanted_encounter: Callable[[GameState, Random], bool]
    _resolve_breakthroughs: Callable[[GameState, Random], None]
    advance_researchers: Callable[[GameState], None] | None = None
    advance_caravans: Callable[[GameState], None] | None = None
    advance_organizations: Callable[[GameState], None] | None = None
    advance_war_finance: Callable[[GameState], None] | None = None
    advance_civilizations: Callable[[GameState], None] | None = None
    advance_strategic_wars: Callable[[GameState, Random], None] | None = None
    advance_regions: Callable[[GameState, list[str]], None] | None = None
    advance_player_society: Callable[[GameState, Random], list[str]] | None = None


@dataclass(frozen=True, slots=True)
class ElapsedYearDependencies:
    _advance_world_year: WorldYearPort
    _advance_soul_erosion_time: Callable[[GameState, int], bool]


@dataclass(frozen=True, slots=True)
class MapTravelDependencies:
    year: ElapsedYearDependencies
    _clear_market: Callable[[GameState], None]
    _compact_world_history: Callable[[GameState], bool]
    _die: Callable[[GameState, str, str], None]
    _ensure_market: Callable[[GameState, Random], bool]
    _finish_travel_time: TravelSettlementPort
    _load: Callable[[str], GameState]
    _monster_travel_multiplier: Callable[[Player, str], float]
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
    _clear_market: Callable[[GameState], None]
    _ensure_market: Callable[[GameState, Random], bool]
    _instant_arrival: Callable[[GameState, str], None]
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
    _advance_auction_clock: Callable[[GameState, Random], None]
    _advance_concubine_aftermath: Callable[[GameState, Random], None]
    _advance_concubine_status: Callable[[GameState, int], float]
    _advance_diplomacy_unit: Callable[[GameState, Random], list[str]]
    _advance_exchange_clock: Callable[[GameState, Random], None]
    _advance_heavenly_court_unit: Callable[[GameState, Random], list[str]]
    _advance_intrigue_unit: Callable[[GameState, Random], list[str]]
    _advance_natal_artifact: Callable[[GameState, str, int], str | None]
    _advance_player_bounties: Callable[[GameState, Random], None]
    _record_era_summary: Callable[[GameState, int, list[str]], None]
    _maybe_tianji_intelligence_event: Callable[[GameState, Random], str | None] | None = None
    _settle_territory_time: Callable[[GameState, Random], None] | None = None


@dataclass(frozen=True, slots=True)
class ElapsedTravelDependencies(TimeSettlementDependencies):
    """Existing travel settlement contract, now backed by common phases."""


@dataclass(frozen=True, slots=True)
class TimeDependencies:
    world_year: WorldYearDependencies
    elapsed_travel: ElapsedTravelDependencies
    travel: MapTravelDependencies
    teleport: TeleportDependencies
