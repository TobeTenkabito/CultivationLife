"""Base-game ancestry identity, independent of optional bloodline benefits."""
import hashlib

SPECIES = ('serpent', 'avian', 'ape', 'fox', 'turtle', 'insect', 'aquatic', 'flora')


def stable_species(identity):
    return SPECIES[int.from_bytes(hashlib.sha256(str(identity).encode()).digest()[:4], 'big') % len(SPECIES)]


def identity(actor, *, hide_route=False):
    from ..content_registry import WORLD_SYSTEMS
    read = actor.get if isinstance(actor, dict) else lambda key, default=None: getattr(actor, key, default)
    species = read('monster_species_id')
    if read('path') == 'monster' and not species:
        species = stable_species(read('id') or read('name'))
    result = {'monster_species_id': species,
              'monster_species_name': WORLD_SYSTEMS.get('monster_species', {}).get(species, {}).get('name', '')}
    from .asura import enabled, ROUTE_NAMES
    route = read('asura_route') or read('asura_cultivation', {}).get('route')
    if enabled() and not hide_route and read('path') == 'demonic' and (route or read('realm_index', 0) >= 9):
        if not route and not hasattr(actor, 'asura_cultivation'):
            index = int.from_bytes(hashlib.sha256(str(read('id') or read('name')).encode()).digest()[:4], 'big') % 8
            route = tuple(ROUTE_NAMES)[index]
        result.update(asura_route=route, asura_route_name=ROUTE_NAMES.get(route, ''))
    elif hide_route:
        result.update(asura_route=None, asura_route_name='')
    return result
