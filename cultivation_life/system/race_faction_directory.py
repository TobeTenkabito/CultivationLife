"""Stable local sect names. Only actual founding or mobilization creates a roster."""
from ..definition_data import definition as _content_definition
import random
from functools import lru_cache

from ..content_registry import RACE_DEFINITIONS, RACE_SYSTEMS


FACTION_SUFFIXES = _content_definition(__name__, "FACTION_SUFFIXES")


@lru_cache(maxsize=512)
def _names(seed, world, race, roots):
    rng = random.Random(f'race-sects-v1:{seed}:{world}:{race}')
    endings = FACTION_SUFFIXES
    prefixes = rng.sample(roots, 2) if len(roots) >= 2 else (roots[0], roots[0])
    return tuple(prefix + ending for prefix, ending in zip(prefixes, rng.sample(endings, 2)))


def unformed_factions(game, world, race, *, include_presets=True):
    definition = RACE_DEFINITIONS.get(race, {})
    if world not in definition.get('worlds', ()):
        return
    # The original record takes precedence even after extinction, a change of
    # allegiance, or the transfer of a family out of game.sects.
    def available(identity):
        return (identity not in game.sects and not (game.family and game.family.id == identity)
                and identity not in game.strategic_war_state.get('materialized', {}))

    support = game.strategic_war_state.get('directory_support', {}).get(world, {})
    if include_presets:
        for row in RACE_SYSTEMS.get('faction_presets', {}).get(race, ()):
            if row['world'] == world and available(row['id']):
                yield {**row, 'origin': 'preset', 'allegiance': support.get(row['id'], race)}

    roots = RACE_SYSTEMS.get('faction_name_roots', {}).get(race) or (definition['name'],)
    for slot, name in enumerate(_names(game.seed, world, race, tuple(roots)), 1):
        identity = f'race_sect_{world}_{race}_{slot}'
        if available(identity):
            yield {'id': identity, 'name': name, 'world': world, 'origin': 'seeded', 'allegiance': support.get(identity, race)}


def local_sects(game, world):
    rows = {}
    for race, definition in RACE_DEFINITIONS.items():
        if world in definition.get('worlds', ()):
            for entry in unformed_factions(game, world, race):
                rows[entry['id']] = dict(entry, active=False, home_race=race)
    for sect in game.sects.values():
        if sect.kind == 'sect' and sect.world == world and not sect.extinct:
            rows[sect.id] = dict(id=sect.id, name=sect.name, allegiance=sect.allegiance_race or 'human', active=True)
    return rows


def adopt_support(game, sect):
    overrides = game.strategic_war_state.get('directory_support', {}).get(sect.world, {})
    sect.allegiance_race = overrides.pop(sect.id, sect.allegiance_race)
