"""Late-bound regional capabilities, resolved only at the composition root."""
from ...regional_dependencies import RegionalDependencies
from ...system.ghost import calendar as ghost_calendar
from ...system.intrigue import runtime as intrigue_runtime
from ...system.war import lifecycle as war_lifecycle


def bind_regions(host) -> RegionalDependencies:
    return RegionalDependencies(
        get_maps=lambda: host.maps,
        ensure_merchant=lambda game: host._ensure_merchant(game),
        advance_sects=lambda game, rng, *, personal=True: host._annual_sect_update(game, rng, personal=personal),
        advance_npcs=lambda game, rng: host._annual_world_npc_update(game, rng),
        advance_family=lambda game, rng: host._annual_offspring_and_family_update(game, rng),
        advance_relationships=lambda game, rng: host._annual_relationship_update(game, rng),
        advance_buddhist_society=lambda game: host._advance_buddhist_society_year(game),
        advance_sage_society=lambda game, rng: host._advance_sage_society_year(game, rng),
        advance_parade=lambda game, rng: ghost_calendar.advance_parade_year(host._dependencies.ghost_flows.calendar, game, rng),
        advance_guixu=lambda game, rng, news: host._advance_guixu_calendar(game, rng, news),
        advance_strategic_wars=lambda game, rng: host._advance_strategic_wars(game, rng),
        advance_researchers=lambda game: host._dependencies.heavens.advance_researchers(game),
        advance_wars_unit=lambda game, rng, campaigns: war_lifecycle._advance_wars_unit(
            host._dependencies.war.lifecycle, game, rng, campaigns=campaigns),
        pressure_npc_powers=lambda game, rng, news: host._pressure_weak_npc_powers(game, rng, news),
        advance_npc_faction=lambda game, rng, identity, news: intrigue_runtime.advance_npc_faction(
            host._dependencies.intrigue.runtime, game, rng, identity, news),
    )
