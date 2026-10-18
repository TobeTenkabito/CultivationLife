"""Shared availability checks for the one owned puppet asset."""
from .relationship_records import find_person


def usable(puppet, game=None):
    # Control can naturally decay to zero without destroying the living body.
    condition = {'corpse': 'corpse_integrity', 'mechanical': 'durability'}
    if not puppet.get('alive', True) or float(puppet.get(condition.get(puppet.get('type')), 100)) <= 0:
        return False
    if game is not None and puppet.get('type') == 'living' and puppet.get('source_npc_id'):
        source = find_person(game, str(puppet['source_npc_id']), include_inactive=True)
        if source is not None and not source.alive:
            return False
    return True


def training_facts(game, puppet):
    """Missing lifecycle facts adopt the original, never inferred past rewards."""
    row = dict(puppet)
    if row.get('type') == 'living' and row.get('source_npc_id'):
        source = find_person(game, str(row['source_npc_id']), include_inactive=True)
        if source is not None:
            row.setdefault('age', source.age)
            row.setdefault('lifespan', source.lifespan)
    return row
