"""Composition of time operations through explicit, late-bound ports."""
from ...time_dependencies import (
    ElapsedTravelDependencies,
    ElapsedYearDependencies,
    MapTravelDependencies,
    TeleportDependencies,
    TimeDependencies,
    TimeSettlementDependencies,
    WorldYearDependencies,
)


def bind_world_year(host) -> WorldYearDependencies:
    from ..world import regions, factions
    from ...system.monster_civilizations.core import advance_year
    from ...system.economy.caravans import advance_caravans
    from ...system.economy.organizations import advance_organizations
    from ...system.war.stationing import advance as advance_stationing
    return WorldYearDependencies(
        advance_regions=lambda game, news: regions.advance(host._dependencies.regions, game, news),
        advance_player_society=lambda game, rng: factions.annual_player_faction(host._dependencies.world_factions, game, rng),
        advance_civilizations=advance_year,
        advance_caravans=lambda game: advance_caravans(game, host.maps),
        advance_organizations=lambda game: advance_organizations(game, host.maps),
        advance_war_finance=advance_stationing,
        advance_strategic_wars=lambda game, rng: host._advance_strategic_wars(game, rng),
        _advance_buddhist_year=lambda game: host._advance_buddhist_year(game),
        _advance_ghost_phase_two_year=lambda game, rng: host._advance_ghost_phase_two_year(game, rng),
        _advance_guixu_calendar=lambda game, rng, news: host._advance_guixu_calendar(game, rng, news),
        _advance_merchant_year=lambda game: host._advance_merchant_year(game),
        _advance_monster_bloodline_year=lambda game: host._advance_monster_bloodline_year(game),
        _advance_sage_year=lambda game, rng: host._advance_sage_year(game, rng),
        _annual_demonic_update=lambda game, rng: host._annual_demonic_update(game, rng),
        _annual_sect_update=lambda game, rng, *, personal=True: (host._annual_sect_update(game, rng) if personal else host._annual_sect_update(game, rng, personal=False)),
        _annual_spirit_field_update=lambda player: host._annual_spirit_field_update(player),
        _annual_world_npc_update=lambda game, rng: host._annual_world_npc_update(game, rng),
        advance_researchers=lambda game: host._dependencies.heavens.advance_researchers(game),
        _check_tribulation=lambda game, rng: host._check_tribulation(game, rng),
        _die=lambda game, reason, event_id: host._die(game, reason, event_id),
        _maybe_artifact_synthesis=lambda game, rng: host._maybe_artifact_synthesis(game, rng),
        _maybe_mortal_root_completion=lambda game, rng: host._maybe_mortal_root_completion(game, rng),
        _maybe_race_war_ambush=lambda game, rng: host._maybe_race_war_ambush(game, rng),
        _maybe_wanted_encounter=lambda game, rng: host._maybe_wanted_encounter(game, rng),
        _resolve_breakthroughs=lambda game, rng: host._resolve_breakthroughs(game, rng),
    )


def bind_map_travel(host) -> MapTravelDependencies:
    return MapTravelDependencies(
        year=bind_elapsed_year(host),
        _clear_market=lambda game: host._clear_market(game),
        _compact_world_history=lambda game: host._compact_world_history(game),
        _die=lambda game, reason, event_id: host._die(game, reason, event_id),
        _ensure_market=lambda game, rng: host._ensure_market(game, rng),
        _finish_travel_time=lambda game, start_age, institution_world, institution_unit, news, rng, *, action_units=None: (
            host._finish_travel_time(game, start_age, institution_world, institution_unit, news, rng)
            if action_units is None else host._finish_travel_time(game, start_age, institution_world, institution_unit, news, rng, action_units=action_units)),
        _load=lambda game_id: host._load(game_id),
        _monster_travel_multiplier=lambda player, destination: host._monster_travel_multiplier(player, destination),
        _get_maps=lambda: host.maps,
        present=lambda game: host.present(game),
        _get_store=lambda: host.store,
    )


def bind_teleport(host) -> TeleportDependencies:
    return TeleportDependencies(
        _clear_market=lambda game: host._clear_market(game),
        _ensure_market=lambda game, rng: host._ensure_market(game, rng),
        _instant_arrival=lambda game, destination: host._instant_arrival(game, destination),
        _load=lambda game_id: host._load(game_id),
        _get_maps=lambda: host.maps,
        present=lambda game: host.present(game),
        _get_store=lambda: host.store,
    )


def bind_elapsed_year(host) -> ElapsedYearDependencies:
    return ElapsedYearDependencies(
        _advance_world_year=lambda game, rng, news, *, encounters=True: (host._advance_world_year(game, rng, news) if encounters else host._advance_world_year(game, rng, news, encounters=False)),
        _advance_soul_erosion_time=lambda game, elapsed_years: host._advance_soul_erosion_time(game, elapsed_years),
    )


def bind_settlement(host, *, travel: bool = False) -> TimeSettlementDependencies:
    contract = ElapsedTravelDependencies if travel else TimeSettlementDependencies
    return contract(
        _settle_territory_time=lambda game, rng: host._settle_territory_time(game, rng),
        _maybe_tianji_intelligence_event=(None if travel else
            lambda game, rng: host._maybe_tianji_intelligence_event(game, rng)),
        _advance_auction_clock=lambda game, rng: host._advance_auction_clock(game, rng),
        _advance_concubine_aftermath=lambda game, rng: host._advance_concubine_aftermath(game, rng),
        _advance_concubine_status=lambda game, units: host._advance_concubine_status(game, units),
        _advance_diplomacy_unit=lambda game, rng: host._advance_diplomacy_unit(game, rng),
        _advance_exchange_clock=lambda game, rng: host._advance_exchange_clock(game, rng),
        _advance_heavenly_court_unit=lambda game, rng: host._advance_heavenly_court_unit(game, rng),
        _advance_intrigue_unit=lambda game, rng: host._advance_intrigue_unit(game, rng),
        _advance_natal_artifact=lambda game, action, units: host._advance_natal_artifact(game, action, units),
        _advance_player_bounties=lambda game, rng: host._advance_player_bounties(game, rng),
        _record_era_summary=lambda game, start_age, news: host._record_era_summary(game, start_age, news),
    )


def bind_elapsed_travel(host) -> ElapsedTravelDependencies:
    return bind_settlement(host, travel=True)


def bind_time(host) -> TimeDependencies:
    return TimeDependencies(
        world_year=bind_world_year(host),
        elapsed_travel=bind_elapsed_travel(host),
        travel=bind_map_travel(host),
        teleport=bind_teleport(host),
    )
