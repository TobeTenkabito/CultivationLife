"""Read-only DLC appearance selection from the actual bloodline, never location/RNG."""
import json
from functools import lru_cache

from . import content_registry as registry
from .visual_assets import extension_asset
from .errors import NotFoundError

OWNER = 'official.monster-bloodlines'
URL = f'/extension-assets/{OWNER}/visual/fox/manifest.json'


@lru_cache(maxsize=8)
def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def fox_appearance(player):
    """Return an ephemeral identity; no save migration or inferred branch mutation.

    A bloodline's own realm survives sealed descent. Ambiguous merged nodes use
    the latest recorded explicit branch; incomplete/unknown histories fall back.
    """
    if (player.path != 'monster' or player.monster_species_id != 'fox'
            or player.ghost_host_body or player.ghost_attachment
            or player.transformation_loadouts.get(getattr(player.transformation_technique, 'id', None), {}).get('active')):
        return None
    if not any(r.get('id') == OWNER and r.get('status') == 'loaded' for r in registry.EXTENSION_REPORT):
        return None
    node_id = player.monster_evolution_id
    node = registry.MONSTER_EVOLUTIONS.get(node_id)
    if not node or node.get('species') != 'fox':
        return None
    try:
        path = extension_asset(registry.default_content_root().parent, registry.default_extension_root(),
                               registry.EXTENSION_REPORT, URL)
        data = _read(path)
    except (OSError, ValueError, NotFoundError):
        return None
    rule = data['nodes'].get(node_id)
    if not rule or rule['realm'] != node['realm_index']:
        return None
    if 'static' in rule:
        return dict(static='actor.monster.'+rule['static'], combat=rule['combat'])
    if player.gender not in {'male', 'female'}:
        return None
    route = rule.get('route')
    if not route:
        route = next((data['history_routes'][h] for h in reversed(player.monster_evolution_history)
                      if h in data['history_routes'] and h in registry.MONSTER_EVOLUTIONS
                      and registry.MONSTER_EVOLUTIONS[h]['realm_index'] <= node['realm_index']), None)
    if not route:
        return None
    identity = f"fox-{rule['stage']}-{route}-{player.gender}"
    if identity not in data['actors']:
        return None
    return dict(static='actor.monster.'+identity, combat=identity)
