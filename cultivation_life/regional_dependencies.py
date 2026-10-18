"""Capabilities of regional settlement: original state, no loading or saving."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from random import Random
from typing import Any, Protocol

from .models import GameState
from .ports import MapPort
from .regional_context import CalendarGame


class SectYearPort(Protocol):
    def __call__(
        self, game: GameState | CalendarGame, rng: Random, *, personal: bool = True,
    ) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class RegionalDependencies:
    get_maps: Callable[[], MapPort]
    ensure_merchant: Callable[[GameState], bool]
    advance_sects: SectYearPort
    advance_npcs: Callable[[CalendarGame, Random], list[str]]
    advance_family: Callable[[CalendarGame, Random], list[str]]
    advance_relationships: Callable[[CalendarGame, Random], None]
    advance_buddhist_society: Callable[[CalendarGame], None]
    advance_sage_society: Callable[[CalendarGame, Random], None]
    advance_parade: Callable[[CalendarGame, Random], None]
    advance_guixu: Callable[[CalendarGame, Random, list[str]], bool]
    advance_strategic_wars: Callable[[CalendarGame, Random], None]
    advance_researchers: Callable[[CalendarGame], None]
    advance_wars_unit: Callable[[CalendarGame, Random, list[dict[str, Any]]], list[str]]
    pressure_npc_powers: Callable[[CalendarGame, Random, list[str]], None]
    advance_npc_faction: Callable[[CalendarGame, Random, str, list[str]], None]

    @property
    def maps(self) -> MapPort:
        return self.get_maps()
