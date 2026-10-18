"""Explicit operations for world time."""
from __future__ import annotations

import random

from ...content_registry import WORLD_SYSTEMS
from ...models import GameState
from ...system.possession_system import current_body_age
from ...system.semantic_events import emit
from ...time_dependencies import ElapsedTravelDependencies, WorldYearDependencies
from ...time_flow import TRAVEL_TIME, completed_action_units, settle_elapsed_time


def advance_spatial_year(deps: WorldYearDependencies, game, rng):
    """Isolated year: same personal breakthrough, thunder and lifespan order."""
    p = game.player
    from ...system.economy.state import advance_economy
    if deps.advance_regions:
        deps.advance_regions(game, [])
        deps._advance_merchant_year(game)
        if deps.advance_strategic_wars:
            deps.advance_strategic_wars(game, rng)
        if deps.advance_researchers:
            deps.advance_researchers(game)
    else:
        advance_economy(game)
    if deps.advance_war_finance:
        deps.advance_war_finance(game)
    if deps.advance_caravans and not deps.advance_regions:
        deps.advance_caravans(game)
    if deps.advance_organizations and not deps.advance_regions:
        deps.advance_organizations(game)
    emit(game, 'time.elapsed', years=1, unit_years=WORLD_SYSTEMS['time_units'][str(p.realm_index)])
    deps._advance_buddhist_year(game)
    deps._advance_sage_year(game, rng)
    deps._advance_monster_bloodline_year(game)
    deps._annual_demonic_update(game, rng)
    from ...system.economy.spirit_fields import advance_field_year
    advance_field_year(game)
    if deps.advance_civilizations and not deps.advance_regions:
        deps.advance_civilizations(game)
    if not p.alive or game.pending_event:
        return False
    deps._resolve_breakthroughs(game, rng)
    if not p.alive or game.pending_event:
        return False
    deps._check_tribulation(game, rng)
    if not p.alive or game.pending_event:
        return False
    if p.lifespan is not None and current_body_age(p) >= p.lifespan:
        deps._die(game, '寿元已尽', 'SYS_LIFESPAN')
        return False
    return True


def _advance_world_year(
    deps: WorldYearDependencies, game: GameState, rng: random.Random, era_news: list[str], *, encounters: bool = True,
) -> bool:
    player = game.player
    from ...system.economy.state import advance_economy
    if deps.advance_regions:
        deps.advance_regions(game, era_news)
    else:
        advance_economy(game)
    if deps.advance_war_finance:
        deps.advance_war_finance(game)
    if deps.advance_caravans and not deps.advance_regions:
        deps.advance_caravans(game)
    if deps.advance_organizations and not deps.advance_regions:
        deps.advance_organizations(game)
    emit(game, "time.elapsed", years=1, unit_years=WORLD_SYSTEMS["time_units"][str(player.realm_index)])
    deps._advance_buddhist_year(game)
    deps._advance_merchant_year(game)
    if deps.advance_regions:
        if deps.advance_strategic_wars:
            deps.advance_strategic_wars(game, rng)
        if deps.advance_researchers:
            deps.advance_researchers(game)
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
    if deps.advance_regions:
        from ...regional_context import calendar_scope
        with calendar_scope(game, player.world, player.age):
            era_news.extend(deps.advance_player_society(game, rng))
    else:
        era_news.extend(deps._annual_sect_update(game, rng))
        era_news.extend(deps._annual_world_npc_update(game, rng))
    if deps.advance_strategic_wars and not deps.advance_regions:
        deps.advance_strategic_wars(game, rng)
    if deps.advance_civilizations and not deps.advance_regions:
        deps.advance_civilizations(game)
    if deps.advance_researchers and not deps.advance_regions:
        deps.advance_researchers(game)
    deps._annual_demonic_update(game, rng)
    if not deps.advance_regions:
        from ...system.economy.spirit_fields import advance_field_year
        advance_field_year(game)
    if not player.alive:
        return False
    deps._resolve_breakthroughs(game, rng)
    if not player.alive or game.pending_event:
        return False
    if not deps.advance_regions and deps._advance_guixu_calendar(game, rng, era_news):
        return False
    if not encounters or game.settings.get("silent_events", False):
        return True
    return not (
        deps._maybe_wanted_encounter(game, rng)
        or deps._maybe_race_war_ambush(game, rng)
        or deps._maybe_artifact_synthesis(game, rng)
        or deps._maybe_mortal_root_completion(game, rng)
    )


def _finish_travel_time(deps: ElapsedTravelDependencies, game, start_age, institution_world, institution_unit, era_news, rng, *, action_units=None):
    player = game.player
    elapsed = player.age - start_age
    if player.world == institution_world:
        from ...system.upper_institutions import advance_time
        advance_time(game, elapsed, institution_unit)
    if elapsed:
        time_unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
        settle_elapsed_time(
            deps, game, rng, era_news, action="travel",
            units=completed_action_units(elapsed, time_unit) if action_units is None else action_units, start_age=start_age,
            policy=TRAVEL_TIME, elapsed_years=elapsed,
        )
