"""Pure validation of original war references and explicit frontier authority."""
from .outpost_routes import profile
from .conquest_definitions import WAR_LIMIT


def counter(value):
    if type(value) is not int or value < 0:
        raise ValueError('驻地征战数量或年份无效')


def mandate(value, row):
    if type(value) is not dict or set(value) != {'issuer_id', 'granted_at', 'source', 'destination'}:
        raise ValueError('驻地军事授权字段无效')
    if any(value[k] != row[k] for k in ('issuer_id', 'source', 'destination')):
        raise ValueError('军事军令不属于原开拓文书')
    counter(value['granted_at'])


def wars(game):
    outposts = game.heavens_state.get('runtime', {}).get('outposts', {})
    counts = {}
    people = set()
    for war in game.wars:
        if not war.get('outpost_id'):
            continue
        row = outposts.get(war['outpost_id'])
        if not row or not row.get('military') or war.get('kind') != 'sect' or war.get('world') != row['destination'] or war.get('attacker_id') != row['owner_id']:
            raise ValueError('驻地战役缺少原文书、军令或原组织')
        counts[row['id']] = counts.get(row['id'], 0) + 1
        if counts[row['id']] > WAR_LIMIT:
            raise ValueError('驻地战役历史超限')
        meta = war.get('frontier')
        if type(meta) is not dict or set(meta) != {'last_year', 'next_battle', 'deadline', 'player_last_year', 'victory_battles', 'occupation', 'occupation_awarded'}:
            raise ValueError('驻地战役时钟字段无效')
        for key, value in meta.items():
            if key != 'occupation_awarded': counter(value)
        if type(meta['occupation_awarded']) is not bool or meta['occupation'] > 5 or meta['occupation_awarded'] != (meta['occupation'] == 5):
            raise ValueError('实际总部目标战果记录无效')
        if war.get('campaign_phase') not in {'marching', 'engaged', 'returning', 'home'}:
            raise ValueError('驻地战役阶段无效')
        if not war.get('logistics') or war['logistics']['sides']['attacker']['contributions'] != {row['owner_id']: profile(row['source'])['war_budget']}:
            raise ValueError('驻地战役原军费记录无效')
        guests = war.get('defensive_guests')
        if type(guests) is not list or len(guests) != len(set(guests)) or not set(guests) <= set(war['roster']['defender']):
            raise ValueError('驻地战役原防御客卿名册无效')
        for side in ('attacker', 'defender'):
            journeys = war.get('journeys', {}).get(side)
            if type(journeys) is not list or not 1 <= len(journeys) <= 48 or set(war['roster'][side]) != {j['person_id'] for j in journeys}:
                raise ValueError('驻地战役名册与原行程不符')
            if len(journeys) != len(war['roster'][side]):
                raise ValueError('驻地战役人物重复')
            for j in journeys:
                keys = {'person_id', 'origin', 'destination', 'route', 'years', 'return_route', 'return_years', 'progress', 'duration', 'phase', 'travel_paid', 'travel_spent'}
                if type(j) is not dict or set(j) != keys or j['phase'] not in {'outbound', 'stationed', 'returning', 'home', 'lost'}:
                    raise ValueError('驻地战役道路字段无效')
                for k in ('years', 'return_years', 'progress', 'duration', 'travel_paid', 'travel_spent'): counter(j[k])
                if j['progress'] > j['duration'] or j['travel_spent'] > j['travel_paid']:
                    raise ValueError('驻地战役道路进度无效')
                for key, a, b in [('route', j['origin'], j['destination']), ('return_route', j['destination'], j['origin'])]:
                    if type(j[key]) is not list or not j[key] or j[key][0] != a or j[key][-1] != b or any(not isinstance(i, str) for i in j[key]):
                        raise ValueError('驻地战役道路起讫无效')
                if j['destination'] != war['location_id']:
                    raise ValueError('驻地战役目的地址不符')
                if j['phase'] not in {'home', 'lost'}:
                    if j['person_id'] in people: raise ValueError('驻地战役人物重复占用')
                    people.add(j['person_id'])
                    if side == 'attacker' and not any(u['person_id'] == j['person_id'] and u.get('war_id') == war['id'] and u['phase'] == 'campaign' for u in row['units']):
                        raise ValueError('原派驻人物未交接给战役')
