"""Shared time phases; activity rules choose explicit, behavior-preserving profiles.

The caller owns aging, yearly activity gains, arrival, and saving. This module
owns the world/erosion boundary and the order of elapsed-action settlement.
It neither loads nor saves and uses the caller's RNG throughout.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from .models import GameState
from .time_dependencies import ElapsedYearDependencies, TimeSettlementDependencies


@dataclass(frozen=True, slots=True)
class TimeSettlementPolicy:
    artifact_before_units: bool
    intelligence_per_unit: bool
    report_dependency_drain: bool
    market_clocks_per_unit: bool
    market_clocks_require_alive: bool


# These differences predate the common pipeline. Altering them changes gameplay,
# event/RNG order, or settlement after death, so do not silently merge profiles.
ACTION_TIME = TimeSettlementPolicy(
    artifact_before_units=True, intelligence_per_unit=True,
    report_dependency_drain=True, market_clocks_per_unit=True,
    market_clocks_require_alive=False,
)
TRAVEL_TIME = TimeSettlementPolicy(
    artifact_before_units=False, intelligence_per_unit=False,
    report_dependency_drain=False, market_clocks_per_unit=False,
    market_clocks_require_alive=True,
)


def advance_elapsed_year(
    deps: ElapsedYearDependencies, game: GameState, rng: random.Random,
    news: list[str], *, encounters: bool = True,
) -> bool:
    """Complete a year already aged by the caller, even if an event interrupts it.

World interruption does not cancel that year's erosion for a living player.
World death skips erosion; erosion death stops the next activity year.
"""
    if encounters:
        proceed = deps._advance_world_year(game, rng, news)
    else:
        proceed = deps._advance_world_year(game, rng, news, encounters=False)
    if game.player.alive:
        deps._advance_soul_erosion_time(game, 1)
    return bool(proceed and game.player.alive)


def completed_action_units(elapsed_years: int, unit_years: int) -> int:
    """Round a partial unit up; zero elapsed years produce no settlement."""
    if unit_years <= 0:
        raise ValueError("行动单位年数必须为正数")
    return max(0, (elapsed_years + unit_years - 1) // unit_years)


def settle_elapsed_time(
    deps: TimeSettlementDependencies, game: GameState, rng: random.Random, news: list[str],
    *, action: str, units: int, start_age: int, policy: TimeSettlementPolicy,
    after_units: Callable[[], None] | None = None,
    elapsed_years: int | None = None,
) -> None:
    """Settle artifact, unit systems, dependency, bounty, events, summary, clocks.

Callers decide whether settlement is entered after death. Once entered, pending
events and deaths inside unit hooks do not add new early returns: the established
batch still settles. Only the profile's market-clock guard is applied at the end.
The optional event hook runs once, after bounties and before summary/clocks.
"""
    if units <= 0:
        return
    if policy.intelligence_per_unit and deps._maybe_tianji_intelligence_event is None:
        raise RuntimeError("普通行动结算缺少神机情报回调")

    def artifact():
        result = deps._advance_natal_artifact(game, action, units)
        if result:
            news.append(result)

    if policy.artifact_before_units:
        artifact()
    for _ in range(units):
        news.extend(deps._advance_diplomacy_unit(game, rng))
        deps._advance_concubine_aftermath(game, rng)
        news.extend(deps._advance_heavenly_court_unit(game, rng))
        news.extend(deps._advance_intrigue_unit(game, rng))
        if policy.intelligence_per_unit:
            result = deps._maybe_tianji_intelligence_event(game, rng)
            if result:
                news.append(result)
    if not policy.artifact_before_units:
        artifact()
    drained = deps._advance_concubine_status(game, units)
    if policy.report_dependency_drain and drained:
        news.append(f"{game.player.age}岁：侍妾名分被抽走机缘 {drained:.1f}")
    deps._advance_player_bounties(game, rng)
    if after_units is not None:
        after_units()
    elapsed = game.player.age - start_age if elapsed_years is None else elapsed_years
    if elapsed >= 5:
        deps._record_era_summary(game, start_age, news)
    if not policy.market_clocks_require_alive or game.player.alive:
        for _ in range(units if policy.market_clocks_per_unit else 1):
            deps._advance_auction_clock(game, rng)
            deps._advance_exchange_clock(game, rng)
