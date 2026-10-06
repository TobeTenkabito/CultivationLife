"""Read-only local policy seam for ordinary travel and resource actions."""
from ...relationship_records import find_person
from ...npc_custody import is_free
from ...spatial_people import instance_of
from .campaign_definitions import TARGET_SITE, SOURCE


def occupied(game, world=None, location=None):
    world = world or game.player.world
    location = location or game.player.location_id
    if world != 'human' or location != TARGET_SITE:
        return False
    row = game.heavens_state.get('runtime', {}).get('campaign')
    if (not row or not row.get('settlement') or row['status'] != 'active'
            or row['gate']['state'] != 'open' or not row['supply']['target']):
        return False
    for unit in row['units']:
        if unit['role'] != 'soldier' or unit['phase'] != 'stationed':
            continue
        npc = find_person(game, unit['person_id'], include_inactive=True)
        if (npc and is_free(npc) and npc.world == world and npc.location_id == location
                and npc.realm_index <= 5 and npc.wounds < 3
                and not instance_of(game, npc.id)
                and npc.id not in game.intrigue_state.get('npc_prisons', {})):
            return True
    return False


def resource_reason(game, action):
    if action in {'travel', 'treasure'} and occupied(game) and game.player.faction_id != SOURCE:
        return '岚疆实际驻军暂封野外取材；仍可修行、调息、救护，或沿地图道路撤离。'
    return None


def arrival_notice(game):
    if not occupied(game):
        return ''
    return ' 岚疆驻军查验了你的行迹：普通通行与修行开放，野外探索取材暂受限制；可在诸天战局查阅现场。'
