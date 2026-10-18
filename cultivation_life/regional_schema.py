"""Validate regional clocks and resumable travel without advancing either."""
import ast
import random
# Schema 10 normal-world identifiers; independent of the runtime registry.
WORLDS = frozenset({'human', 'demon', 'spirit', 'true_demon', 'monster_realm',
                   'phantom_underworld', 'hell', 'celestial', 'asura', 'nether', 'reincarnation'})


def validate(value):
    known = WORLDS
    age = value['player'].get('age', 16)
    state = value.get('world_simulation', {})
    if not isinstance(state, dict):
        raise ValueError('地区时间状态必须为对象')
    if state:
        if state.get('version') != 1 or set(state.get('regions', {})) != known:
            raise ValueError('地区时间版本或界面清单不兼容')
        base = state.get('base_year')
        if type(base) is not int or not 0 <= base <= age:
            raise ValueError('地区结算基准无效')
        for row in state['regions'].values():
            if (not isinstance(row, dict) or type(row.get('year')) is not int
                    or not base <= row['year'] <= age or type(row.get('initialized')) is not bool
                    or type(row.get('merchant_year')) is not int or not base <= row['merchant_year'] <= row['year']):
                raise ValueError('地区时钟无效或超前')
            if not isinstance(row.get('rng'), str) or len(row['rng']) > 30000:
                raise ValueError('地区随机状态无效')
            try:
                random.Random().setstate(ast.literal_eval(row['rng']))
            except (ValueError, TypeError, SyntaxError, OverflowError) as exc:
                raise ValueError('地区随机状态损坏') from exc
        if not isinstance(state.get('people'), dict) or any(
                not isinstance(k, str) or type(v) is not int or not base <= v <= age
                for k, v in state['people'].items()):
            raise ValueError('人物年度结算标记无效')
        families = state.get('family_years', {})
        if not isinstance(families, dict) or any(not isinstance(k, str) or type(v) is not int
                or not base <= v <= age for k,v in families.items()):
            raise ValueError('家族年度结算标记无效')
        if type(state.get('revision')) is not int or state['revision'] < 0 or not isinstance(state.get('recent'), list) or len(state['recent']) > 16:
            raise ValueError('地区同步记录无效')
        if 'deferred' in state:
            validate_deferred(state['deferred'], age)
        parades = state.get('ghost_parades', {})
        if not isinstance(parades, dict) or any(w not in known for w in parades):
            raise ValueError('百鬼夜行归属无效')
        for world, parade in parades.items():
            if (not isinstance(parade, dict) or parade and (
                    parade.get('world') != world or type(parade.get('settled_year')) is not int
                    or not 0 <= parade['settled_year'] <= age)):
                raise ValueError('百鬼夜行地区年份无效')
        spans = state.get('space_years', [])
        if not isinstance(spans, list):
            raise ValueError('空间年份区间无效')
        last = base-1
        for span in spans:
            if (not isinstance(span, list) or len(span)!=2 or any(type(y) is not int for y in span)
                    or not max(base, last+1) <= span[0] <= span[1] <= age):
                raise ValueError('空间年份区间重叠或无效')
            last = span[1]
        units = state.get('society_units', {})
        if not isinstance(units, dict) or any(w not in known for w in units):
            raise ValueError('地区行动单位归属无效')
        for rows in [*units.values(), *(w.get('deferred_units', []) for w in value.get('wars', []))]:
            if not isinstance(rows, list):
                raise ValueError('地区行动单位必须为列表')
            previous = (-1, -1)
            for row in rows:
                if (not isinstance(row, dict) or type(row.get('year')) is not int
                        or not base <= row['year'] <= age or type(row.get('unit')) is not int
                        or row['unit'] < 0 or (row['year'], row['unit']) <= previous):
                    raise ValueError('地区行动单位重复或无效')
                previous = row['year'], row['unit']
        factions = state.get('faction_units', {})
        if not isinstance(factions, dict) or any(w not in known for w in factions):
            raise ValueError('异界议事归属无效')
        for rows in factions.values():
            if not isinstance(rows, list):
                raise ValueError('异界议事记录无效')
            seen = set()
            for row in rows:
                if (not isinstance(row, dict) or type(row.get('year')) is not int
                        or not base <= row['year'] <= age or type(row.get('unit')) is not int
                        or row['unit'] < 0 or not isinstance(row.get('faction'), str)):
                    raise ValueError('异界议事记录无效')
                key = row['year'], row['unit'], row['faction']
                if key in seen:
                    raise ValueError('异界议事记录重复')
                seen.add(key)
        if not isinstance(state.get('arrivals', {}), dict) or any(
                not isinstance(k,str) or not isinstance(r,dict) or r.get('world') not in known
                or type(r.get('year')) is not int or not base <= r['year'] <= age
                or type(r.get('entered', r['year'])) is not int or not r['year'] <= r.get('entered', r['year']) <= age
                for k,r in state.get('arrivals',{}).items()):
            raise ValueError('异界迁入记录无效')
    journey = value.get('map_journey')
    if journey is not None:
        if (not isinstance(journey, dict) or journey.get('world') not in known | {'lost', 'rift'}
                or not isinstance(journey.get('origin'), str) or not isinstance(journey.get('destination'), str)
                or type(journey.get('years')) is not int or journey['years'] < 0
                or type(journey.get('completed')) is not int or not 0 <= journey['completed'] <= journey['years']
                or type(journey.get('unit_years', 1)) is not int or journey.get('unit_years', 1) <= 0
                or not isinstance(journey.get('route'), list) or len(journey['route']) < 2
                or journey['route'][0] != journey['origin'] or journey['route'][-1] != journey['destination']):
            raise ValueError('远行进度无效')


def validate_deferred(book, age):
    if not isinstance(book, dict):
        raise ValueError('异界待结算账必须为对象')
    for key in ('sequence', 'advanced', 'repaid', 'applied'):
        if type(book.get(key)) is not int or book[key] < 0:
            raise ValueError('异界收据计数无效')
    if book['repaid'] > book['advanced']:
        raise ValueError('核销不能超过系统垫款')
    for key in ('pending', 'cash_delta', 'debts', 'goods_issued'):
        if not isinstance(book.get(key), dict):
            raise ValueError('异界待结算账结构无效')
    expected, identities = {}, set()
    for world, rows in book['pending'].items():
        if world not in WORLDS or not isinstance(rows, list):
            raise ValueError('异界收据归属无效')
        for row in rows:
            if (not isinstance(row, dict) or type(row.get('id')) is not int
                    or not 0 < row['id'] <= book['sequence'] or row['id'] in identities
                    or type(row.get('year')) is not int or not 0 <= row['year'] <= age):
                raise ValueError('异界收据编号或年份无效')
            identities.add(row['id'])
            if row.get('kind') in {'debit', 'credit'}:
                if type(row.get('amount')) is not int or row['amount'] <= 0 or not isinstance(row.get('account'), str):
                    raise ValueError('异界款项收据无效')
                key = row['account']
                expected[key] = expected.get(key, 0)+row['amount']*(1 if row['kind']=='credit' else -1)
            elif row.get('kind') == 'goods':
                if (type(row.get('quantity')) is not int or not row['quantity']
                        or not isinstance(row.get('market'), str) or not row['market'].startswith(world+':')
                        or not isinstance(row.get('item'), str) or not isinstance(row.get('definition'), dict)
                        or any(type(row.get(k)) is not int or row[k]<0 for k in ('gross','fee'))):
                    raise ValueError('异界货物收据无效')
            elif row.get('kind') == 'service':
                if type(row.get('amount')) is not int or row['amount']<=0 or not str(row.get('market','')).startswith(world+':'):
                    raise ValueError('异界劳务收据无效')
            elif row.get('kind') == 'depot':
                if (type(row.get('quantity')) is not int or row['quantity']<=0 or row.get('owner_kind') not in {'sect','family'}
                        or not isinstance(row.get('owner'),str) or not isinstance(row.get('item'),str)):
                    raise ValueError('异界府库收据无效')
            else:
                raise ValueError('未知异界收据类型')
    if {k:v for k,v in expected.items() if v} != {k:v for k,v in book['cash_delta'].items() if v}:
        raise ValueError('异界款项汇总与收据不符')
    if any(type(v) is not int or v < 0 for v in book['debts'].values()):
        raise ValueError('异界垫款余额无效')
    if any(not isinstance(k, str) or type(v) is not int for k,v in book['cash_delta'].items()):
        raise ValueError('异界款项汇总无效')
    import math
    if any(not isinstance(k, str) or type(v) not in {int, float} or not math.isfinite(v) or v < 0
           for k,v in book['goods_issued'].items()):
        raise ValueError('异界垫付商品无效')
