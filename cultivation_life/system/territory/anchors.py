"""Addressed foreign branches reference original organizations, never clones."""
from ...relationship_records import find_person
from ...npc_custody import is_free
from ...spatial_people import instance_of
from ..heavens.outpost_definitions import ENDPOINTS


def branches(game, world=None):
    return [r for r in game.heavens_state.get('runtime', {}).get('outposts', {}).values()
            if r.get('development') and r['status'] not in {'closed', 'withdrawing'}
            and (world is None or r['destination'] == world)]


def branch(game, world, identity):
    return next((r for r in branches(game, world) if r['owner_id'] == identity), None)


def organization(game, identity):
    return game.family if game.family and game.family.id == identity else game.sects.get(identity)


def owners(game, world):
    result = {s.id: s for s in game.sects.values() if s.world == world and not s.extinct and s.kind == 'sect'}
    for row in branches(game, world):
        entity = organization(game, row['owner_id'])
        if entity and not entity.extinct:
            result[entity.id] = entity
    return result


def operational(game, row):
    entity = organization(game, row['owner_id'])
    npc = find_person(game, row['governor_id'], include_inactive=True) if row['governor_id'] else None
    return bool(entity and not entity.extinct and row['status'] == 'active' and npc and is_free(npc)
                and npc.faction_id == entity.id and npc.world == row['destination']
                and npc.location_id == ENDPOINTS[row['destination']] and not instance_of(game, npc.id)
                and npc.id not in game.intrigue_state.get('npc_prisons', {})
                and any(u['person_id'] == npc.id and u['phase'] == 'stationed' and u['delivered'] for u in row['units']))
