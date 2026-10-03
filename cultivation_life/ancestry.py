"""Stable ancestry defaults independent of content and optional systems."""
import hashlib


SPECIES = ('serpent', 'avian', 'ape', 'fox', 'turtle', 'insect', 'aquatic', 'flora')


def stable_species(identity):
    return SPECIES[int.from_bytes(hashlib.sha256(str(identity).encode()).digest()[:4], 'big') % len(SPECIES)]


def species_identity(actor, species_catalog):
    """Project base ancestry without consulting optional demonic cultivation."""
    read = actor.get if isinstance(actor, dict) else lambda key, default=None: getattr(actor, key, default)
    species = read('monster_species_id')
    if read('path') == 'monster' and not species:
        species = stable_species(read('id') or read('name'))
    return {'monster_species_id': species,
            'monster_species_name': species_catalog.get(species, {}).get('name', '')}
