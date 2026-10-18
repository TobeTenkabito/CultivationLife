"""One parade per ordinary world; archived rows are references, never copies."""
from ...regional_context import region
from ...content_registry import WORLD_SYSTEMS


def get(game, world=None):
    world = world or region(game) or game.player.world
    if world in {'lost', 'rift'}:
        return {}
    if game.ghost_parade.get('world') == world:
        return game.ghost_parade
    return game.world_simulation.get('ghost_parades', {}).get(world, {})


def put(game, world, parade):
    if world == game.player.world or game.ghost_parade.get('world') == world:
        previous = game.ghost_parade
        if previous and previous.get('world') != world and previous.get('world') not in {'lost', 'rift'}:
            game.world_simulation.setdefault('ghost_parades', {})[previous['world']] = previous
        game.ghost_parade = parade
        game.world_simulation.get('ghost_parades', {}).pop(world, None)
    else:
        game.world_simulation.setdefault('ghost_parades', {})[world] = parade


def adopt(game):
    # Earlier schema-10 code already processed this ecology on personal years.
    # Do not re-run that observed history when a frozen world catches up.
    rows = [game.ghost_parade, *game.world_simulation.get('ghost_parades', {}).values()]
    changed = False
    for row in rows:
        if row:
            changed = any(key not in row for key in ('settled_year', 'realm_index', 'unit_years')) or changed
            row.setdefault('settled_year', game.player.age)
            row.setdefault('realm_index', game.player.realm_index)
            row.setdefault('unit_years', max(1, int(WORLD_SYSTEMS['time_units'][str(row['realm_index'])])))
    return changed
