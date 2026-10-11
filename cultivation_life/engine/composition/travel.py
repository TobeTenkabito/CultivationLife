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
    from ...system.monster_civilizations.core import advance_year
    from ...system.economy.caravans import advance_caravans
    from ...system.economy.organizations import advance_organizations
    from ...system.war.stationing import advance as advance_stationing
    return WorldYearDependencies(
        advance_civilizations=advance_year,
        advance_caravans=lambda game: advance_caravans(game, host.maps),
        advance_organizations=lambda game: advance_organizations(game, host.maps),
        advance_war_finance=advance_stationing,
        _advance_buddhist_year=lambda *args, **kwargs: host._advance_buddhist_year(*args, **kwargs),
        _advance_ghost_phase_two_year=lambda *args, **kwargs: host._advance_ghost_phase_two_year(*args, **kwargs),
        _advance_guixu_calendar=lambda *args, **kwargs: host._advance_guixu_calendar(*args, **kwargs),
        _advance_merchant_year=lambda *args, **kwargs: host._advance_merchant_year(*args, **kwargs),
        _advance_monster_bloodline_year=lambda *args, **kwargs: host._advance_monster_bloodline_year(*args, **kwargs),
        _advance_sage_year=lambda *args, **kwargs: host._advance_sage_year(*args, **kwargs),
        _annual_demonic_update=lambda *args, **kwargs: host._annual_demonic_update(*args, **kwargs),
        _annual_sect_update=lambda *args, **kwargs: host._annual_sect_update(*args, **kwargs),
        _annual_spirit_field_update=lambda *args, **kwargs: host._annual_spirit_field_update(*args, **kwargs),
        _annual_world_npc_update=lambda *args, **kwargs: host._annual_world_npc_update(*args, **kwargs),
        advance_researchers=lambda game: host._dependencies.heavens.advance_researchers(game),
        _check_tribulation=lambda *args, **kwargs: host._check_tribulation(*args, **kwargs),
        _die=lambda *args, **kwargs: host._die(*args, **kwargs),
        _maybe_artifact_synthesis=lambda *args, **kwargs: host._maybe_artifact_synthesis(*args, **kwargs),
        _maybe_mortal_root_completion=lambda *args, **kwargs: host._maybe_mortal_root_completion(*args, **kwargs),
        _maybe_race_war_ambush=lambda *args, **kwargs: host._maybe_race_war_ambush(*args, **kwargs),
        _maybe_wanted_encounter=lambda *args, **kwargs: host._maybe_wanted_encounter(*args, **kwargs),
        _resolve_breakthroughs=lambda *args, **kwargs: host._resolve_breakthroughs(*args, **kwargs),
    )


def bind_map_travel(host) -> MapTravelDependencies:
    return MapTravelDependencies(
        year=bind_elapsed_year(host),
        _clear_market=lambda *args, **kwargs: host._clear_market(*args, **kwargs),
        _compact_world_history=lambda *args, **kwargs: host._compact_world_history(*args, **kwargs),
        _die=lambda *args, **kwargs: host._die(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: host._ensure_market(*args, **kwargs),
        _finish_travel_time=lambda *args, **kwargs: host._finish_travel_time(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _monster_travel_multiplier=lambda *args, **kwargs: host._monster_travel_multiplier(*args, **kwargs),
        _get_maps=lambda: host.maps,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_teleport(host) -> TeleportDependencies:
    return TeleportDependencies(
        _clear_market=lambda *args, **kwargs: host._clear_market(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: host._ensure_market(*args, **kwargs),
        _instant_arrival=lambda *args, **kwargs: host._instant_arrival(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _get_maps=lambda: host.maps,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_elapsed_year(host) -> ElapsedYearDependencies:
    return ElapsedYearDependencies(
        _advance_world_year=lambda *args, **kwargs: host._advance_world_year(*args, **kwargs),
        _advance_soul_erosion_time=lambda *args, **kwargs: host._advance_soul_erosion_time(*args, **kwargs),
    )


def bind_settlement(host, *, travel: bool = False) -> TimeSettlementDependencies:
    contract = ElapsedTravelDependencies if travel else TimeSettlementDependencies
    return contract(
        _maybe_tianji_intelligence_event=(None if travel else
            lambda *args, **kwargs: host._maybe_tianji_intelligence_event(*args, **kwargs)),
        _advance_auction_clock=lambda *args, **kwargs: host._advance_auction_clock(*args, **kwargs),
        _advance_concubine_aftermath=lambda *args, **kwargs: host._advance_concubine_aftermath(*args, **kwargs),
        _advance_concubine_status=lambda *args, **kwargs: host._advance_concubine_status(*args, **kwargs),
        _advance_diplomacy_unit=lambda *args, **kwargs: host._advance_diplomacy_unit(*args, **kwargs),
        _advance_exchange_clock=lambda *args, **kwargs: host._advance_exchange_clock(*args, **kwargs),
        _advance_heavenly_court_unit=lambda *args, **kwargs: host._advance_heavenly_court_unit(*args, **kwargs),
        _advance_intrigue_unit=lambda *args, **kwargs: host._advance_intrigue_unit(*args, **kwargs),
        _advance_natal_artifact=lambda *args, **kwargs: host._advance_natal_artifact(*args, **kwargs),
        _advance_player_bounties=lambda *args, **kwargs: host._advance_player_bounties(*args, **kwargs),
        _record_era_summary=lambda *args, **kwargs: host._record_era_summary(*args, **kwargs),
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
