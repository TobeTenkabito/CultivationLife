"""Bounded references to original buildings, adjacent roads and original permissions."""
from ..building_schema import address
from ..building_rules import may_use
from .earth_temple_rules import root, ledgers, temple, city, reason, occupied_reason


def parent_for(game, maps):
    if maps is None or game.player.world != 'celestial':
        return None
    here = game.player.location_id
    neighbors = {r['to'] if r['from'] == here else r['from']
                 for r in maps.worlds['celestial']['routes'] if here in (r['from'], r['to'])}
    for s in ledgers(game):
        row = temple(game, s['temple_id'])
        if not row or row['address']['world'] != 'celestial' or row['address']['instance_id'] is not None:
            continue
        original = city(game, row)
        if (row['status'] != 'intact' or row['address']['location_id'] not in neighbors or not s.get('active')
                or row['owner'] != dict(kind='player', id=game.id) or not original
                or original.get('population') not in {'mortal', 'mixed'} or not may_use(original, 'player', game.id)):
            continue
        plan = maps.travel_plan('celestial', here, row['address']['location_id'], game.player.realm_index)
        if plan.status == 'ok':
            return row
    return None


def branch_reason(game, maps):
    if blocked := reason(game) or occupied_reason(game):
        return blocked
    if len(ledgers(game)) >= 4:
        return '一主三分已满；遗址仍占原庙位置，不能拆建刷新名额'
    if not parent_for(game, maps):
        return '须亲赴与一座有效庙宇有直接道路相连的地域，并取得当地城市许可'
    return ''


def public(game, maps):
    rows = []
    for s in ledgers(game):
        row = temple(game, s['temple_id'])
        if not row:
            continue
        original = city(game, row)
        place = row['address']
        rows.append(dict(id=row['id'], name=row['name'], address=dict(place),
            main=row['id'] == root(game)['temple_id'], local=place == address(game), status=row['status'],
            active=s.get('active', False), trust=s.get('trust', 0),
            allowance=s.get('allowance', 0) if game.player.age < s.get('until', 0) else 0,
            until=s.get('until', 0), completed=s.get('completed', 0),
            location_name=maps.location(place['world'], place['location_id'])['name'] if maps else place['location_id'],
            city_name=(original or {}).get('name', '原城市不可用'),
            facilities=list(row.get('temple_facilities', [None, None])),
            pending='地方争议' if s.get('cases',{}).get('active') else '专项营造' if s.get('works') else '地方事务' if s.get('duty') else '',
            parent_id=row.get('parent_temple_id')))
    return rows
