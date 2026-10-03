"""Explicit operations for world time."""
from __future__ import annotations

import random

from ...content_registry import WORLD_SYSTEMS
from ...models import GameState
from ...system.possession_system import current_body_age
from ...system.semantic_events import emit
from ...time_dependencies import ElapsedTravelDependencies, WorldYearDependencies


def _advance_world_year(
    deps: WorldYearDependencies, game: GameState, rng: random.Random, era_news: list[str], *, encounters: bool = True,
) -> bool:
    player = game.player
    emit(game, "time.elapsed", years=1, unit_years=WORLD_SYSTEMS["time_units"][str(player.realm_index)])
    deps._advance_buddhist_year(game)
    deps._advance_merchant_year(game)
    era_news.extend(deps._advance_sage_year(game, rng))
    deps._advance_ghost_phase_two_year(game, rng)
    deps._advance_monster_bloodline_year(game)
    deps._resolve_breakthroughs(game, rng)
    if not player.alive or game.pending_event:
        return False
    deps._check_tribulation(game, rng)
    if not player.alive or game.pending_event:
        return False
    if player.lifespan is not None and current_body_age(player) >= player.lifespan:
        deps._die(game, "寿元已尽", "SYS_LIFESPAN")
        return False
    era_news.extend(deps._annual_sect_update(game, rng))
    era_news.extend(deps._annual_world_npc_update(game, rng))
    deps._annual_demonic_update(game, rng)
    deps._annual_spirit_field_update(player)
    if not player.alive:
        return False
    deps._resolve_breakthroughs(game, rng)
    if not player.alive or game.pending_event:
        return False
    if deps._advance_guixu_calendar(game, rng, era_news):
        return False
    if not encounters or game.settings.get("silent_events", False):
        return True
    return not (
        deps._maybe_wanted_encounter(game, rng)
        or deps._maybe_race_war_ambush(game, rng)
        or deps._maybe_artifact_synthesis(game, rng)
        or deps._maybe_mortal_root_completion(game, rng)
    )


def _finish_travel_time(deps: ElapsedTravelDependencies, game, start_age, institution_world, institution_unit, era_news, rng):
    player = game.player
    elapsed = player.age - start_age
    if player.world == institution_world:
        from ...system.upper_institutions import advance_time
        advance_time(game, elapsed, institution_unit)
    if elapsed:
        time_unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
        completed_units = max(1, (elapsed + time_unit - 1) // time_unit)
        for _ in range(completed_units):
            era_news.extend(deps._advance_diplomacy_unit(game, rng))
            deps._advance_concubine_aftermath(game, rng)
            era_news.extend(deps._advance_heavenly_court_unit(game, rng))
            era_news.extend(deps._advance_intrigue_unit(game, rng))
        artifact_news = deps._advance_natal_artifact(game, "travel", completed_units)
        if artifact_news:
            era_news.append(artifact_news)
        deps._advance_concubine_status(game, completed_units)
        deps._advance_player_bounties(game, rng)
        if elapsed >= 5:
            deps._record_era_summary(game, start_age, era_news)
        if player.alive:
            deps._advance_auction_clock(game, rng)
            deps._advance_exchange_clock(game, rng)

