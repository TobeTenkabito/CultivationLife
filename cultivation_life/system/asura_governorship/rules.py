"""DLC-specific qualification and read-only original city/office projections."""
from ... import building_rules
from ...building_schema import address
from ...content_registry import WORLD_SYSTEMS
from ...relationship_records import find_person
from .. import asura, institution_authority as authority
from ..asura_court_finance import COURT
from ..institution_ai.rules import digest, person_reason
from ..building_assets import rows_at
from ..economy.ledger import balance

ID = 'asura-governorship'
SOURCE = 'organization:upper:asura'


def config():
    return WORLD_SYSTEMS.get('asura_governorship', {})


def enabled():
    return asura.enabled() and bool(config().get('enabled'))


def offices(game):
    return [r for r in authority.records(game).values() if r['provider'] == ID]


def require_handover(game):
    if any('player' in (r['holder'],r['nominee'],r['controller']) for r in offices(game)):
        raise ValueError('须先到原总督府交接外任责任，再退出王庭')


def court(game):
    return game.upper_institutions.get('asura', {})


def king(game):
    state = court(game)
    return state.get('joined') and state.get('court', {}).get('holders', {}).get('5') == 'player'


def cities(game):
    result = []
    for spec in building_rules.config()['cities'].get('asura', []):
        if spec['id'] not in config().get('cities', []):
            continue
        place = dict(world='asura', instance_id=None, location_id=spec['location_id'])
        row = next((r for r in rows_at(game, place) if r['id'] == 'city:asura:' + spec['id']), None)
        if row:
            result.append(row)
    return result


def legal_city(game, city):
    # The DLC charter explicitly licenses these original public cities. Open
    # access on arbitrary or privately acquired cities never grants military land.
    return (city['status'] == 'intact' and city['owner'] == dict(kind='background', id=city['id'])
            and city['address']['world'] == 'asura' and city.get('content_id') in config().get('cities', []))


def local(game, row):
    return address(game) == dict(world=row['world'], location_id=row['location'], instance_id=None)


def shell(row):
    return dict(id=row['building_id'], name=row['name'], type='artificiality', subtype='public_office',
        level=1, status='destroyed', address=dict(world=row['world'], location_id=row['location'], instance_id=None),
        owner=dict(row['owner']), users=[], public=True, city_id=row['city_id'],
        dependency='official.asura-manifestation', construction=dict(config()['construction']),
        description='王庭公署；任职授予有限管理权，公款与建筑不属于总督私产。')


def building(game, row):
    return game.building_state.get('records', {}).get(row['building_id'])


def eligible_people(game, row):
    identities = set(game.world_npcs) | set(game.notable_npcs)
    identities.update(n.id for s in game.sects.values() if s.world == row['world'] for n in s.npcs)
    if game.family and game.family.world == row['world']:
        identities.update(n.id for n in game.family.npcs)
    result = []
    for identity in sorted(identities):
        npc = find_person(game, identity)
        if (not npc or npc.realm_index < 9 or npc.faction_id not in (None,COURT) or identity == row['holder']
                or identity in court(game).get('court', {}).get('offices', {}).values()
                or identity == court(game).get('court', {}).get('holders', {}).get('5')):
            continue
        if any(identity in r['people'] or identity in (r['holder'],r['nominee'],r['controller']) for r in offices(game) if r['id'] != row['id']):
            continue
        if not person_reason(game, identity, row['world'], row['location'], assignment='institution-delegate:' + row['id']):
            result.append(dict(id=identity, name=npc.name))
    return result


def token(game):
    state = court(game)
    return digest([offices(game), cities(game), [building(game,r) for r in offices(game)],
        state.get('rank'), state.get('earned'), state.get('regard'), state.get('court',{}).get('holders'),
        state.get('treasury'), game.player.age, address(game), game.pending_event, enabled(),
        [(r['id'], balance(game,r['wallet']), eligible_people(game,r)) for r in offices(game) if local(game,r)]])
