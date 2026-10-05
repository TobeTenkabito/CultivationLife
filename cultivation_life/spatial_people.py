"""Spatial membership references share the ordinary authoritative NPC registry."""
from .relationship_records import find_person


def bind(game, npc_type):
    for scene in game.spatial_state.get('instances', {}).values():
        if 'npcs' not in scene:
            continue
        ids = scene.setdefault('npc_ids', [])
        for row in scene.pop('npcs'):
            identity = row['id']
            if find_person(game, identity, include_inactive=True) is None:
                game.relationship_npcs[identity] = npc_type.from_dict(row)
            if identity not in ids:
                ids.append(identity)


def people(game, scene=None):
    scene = scene or game.spatial_state.get('instances', {}).get(game.spatial_state.get('current')) or {}
    return [npc for identity in scene.get('npc_ids', [])
            if (npc := find_person(game, identity, include_inactive=True)) is not None]


def instance_of(game, identity):
    return next((key for key, scene in game.spatial_state.get('instances', {}).items()
                 if identity in scene.get('npc_ids', [])), None)


def accessible(game, person):
    """Same 'lost' world code is insufficient: instances cannot contact each other."""
    identity = person.get('npc_id', person.get('id')) if isinstance(person, dict) else person.id
    from .person_assignments import research_assignment
    assignment = research_assignment(game, identity)
    if assignment:
        location = person.get('location_id') if isinstance(person, dict) else person.location_id
        if assignment['phase'] not in {'studying', 'settling'} or location != game.player.location_id:
            return False
    world = person.get('world') if isinstance(person, dict) else person.world
    owner = instance_of(game, identity)
    current = game.spatial_state.get('current') if game.player.world in {'lost', 'rift'} else None
    return world == game.player.world and owner == current


def require_access(game, person):
    identity = person.get('npc_id', person.get('id')) if isinstance(person, dict) else getattr(person, 'id', None)
    from .person_assignments import research_assignment
    if person and research_assignment(game, identity) and not accessible(game, person):
        raise ValueError('此人正在访学途中或不在当前接待地点')
    spatial = game.player.world in {'lost', 'rift'} or instance_of(game, identity)
    if person and spatial and not accessible(game, person):
        raise ValueError('此人不在当前空间，无法与外界或其他失落界面交互')
