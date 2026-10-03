"""Base-game ancestry identity, independent of optional bloodline benefits."""
import hashlib

from ..ancestry import (
    SPECIES as SPECIES,
    species_identity,
    stable_species as stable_species,
)


def identity(actor, *, hide_route=False):
    from ..content_registry import WORLD_SYSTEMS
    read = actor.get if isinstance(actor, dict) else lambda key, default=None: getattr(actor, key, default)
    result = species_identity(actor, WORLD_SYSTEMS.get('monster_species', {}))
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
