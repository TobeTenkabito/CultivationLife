"""Original finite domain grants follow the same NPC after an expedition ends."""
from ...definition_data import definition as _content_definition
from ..combat.actor_state import read
from ..doctrine.voisinage_training import multiplier


DOMAIN = _content_definition(__name__, "DOMAIN")


def domain(identity, rank, realm):
    name = DOMAIN['perfected_name'] if rank == DOMAIN['perfected_rank'] else DOMAIN['name']
    strength = (1 + (realm - DOMAIN['base_realm']) * DOMAIN['growth']) * multiplier(rank)
    return dict(id=identity + ':domain', name=name, strength=strength, **DOMAIN['field'])


def definitions(npc):
    origin = (read(npc, 'family_traits', {}) or {}).get('dungeon_origin', {})
    rank = origin.get('domain_rank', 0)
    return [domain(read(npc, 'id'), rank, origin['true_realm'])] if rank else []
