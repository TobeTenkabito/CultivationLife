"""Read-only DLC appearance selection from the actual bloodline, never location/RNG."""
import json
from functools import lru_cache

from . import content_registry as registry
from .visual_assets import extension_asset, public_catalog
from .realm_appearance import resolve_realm_appearance
from .errors import NotFoundError

OWNER = 'official.monster-bloodlines'
URL = f'/extension-assets/{OWNER}/visual/fox/manifest.json'


@lru_cache(maxsize=8)
def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _appearance(player, species, *, node_id=None):
    """Return an ephemeral identity; no save migration or inferred branch mutation.

    A bloodline's own realm survives sealed descent. Ambiguous merged nodes use
    the latest recorded explicit branch; incomplete/unknown histories fall back.
    """
    if (player.path != 'monster' or player.monster_species_id != species
            or player.ghost_host_body or player.ghost_attachment
            or player.transformation_loadouts.get(getattr(player.transformation_technique, 'id', None), {}).get('active')):
        return None
    if not any(r.get('id') == OWNER and r.get('status') == 'loaded' for r in registry.EXTENSION_REPORT):
        return None
    node_id = node_id or player.monster_evolution_id
    node = registry.MONSTER_EVOLUTIONS.get(node_id)
    if not node or node.get('species') != species:
        return None
    root, extension_root = registry.default_content_root().parent, registry.default_extension_root()
    entry = next((row for row in public_catalog(root, registry.EXTENSION_REPORT, extension_root)['assets'].values()
                  if row.get('appearance_key') == species and OWNER in row.get('requires', [])), None)
    if not entry:
        return None
    try:
        path = extension_asset(root, extension_root, registry.EXTENSION_REPORT, entry['file'])
        data = _read(path)
    except (OSError, ValueError, NotFoundError):
        return None
    rule = data['nodes'].get(node_id)
    if not rule or rule['realm'] != node['realm_index']:
        return None
    if 'static' not in rule and player.gender not in {'male', 'female'}:
        return None
    # Physical bloodline stage is authoritative even during sealed descent.
    history = [h for h in player.monster_evolution_history if h in registry.MONSTER_EVOLUTIONS
               and registry.MONSTER_EVOLUTIONS[h]['species'] == species
               and registry.MONSTER_EVOLUTIONS[h]['realm_index'] <= node['realm_index']]
    result = resolve_realm_appearance(data.get('realm_forms', []), node['realm_index'],
                                      branch=node_id, variant=player.gender, history=history)
    if result and (result.get('combat') is None or result['combat'] in data['actors']):
        return result
    return None


def fox_appearance(player):
    return _appearance(player, 'fox')


def serpent_appearance(player):
    return _appearance(player, 'serpent')


def monster_appearance(player):
    species = player.monster_species_id
    return _appearance(player, species) if species else None
