"""Pure frontier shape validation. No registry, models or action imports."""
from .outpost_definitions import ENDPOINTS, PHASES, TIMED_ACTIONS, BUILD_YEARS, CROSSING_YEARS, is_target
from .development_schema import validate_development, validate_job
from .development_definitions import LOCAL_PHASES
from .conquest_schema import mandate, wars as validate_conquest_wars
from .outpost_routes import profile, paired, target_for, peers


def counter(value):
    if type(value) is not int or value < 0:
        raise ValueError('开拓数量与年份必须为非负整数')


def stock(value, source, destination=None):
    if type(value) is not dict or len(value) > 32:
        raise ValueError('开拓库存格式无效')
    worlds = (source, destination) if destination else (source, *peers(source))
    allowed = {f'item:econ_{world}_{profile(source)["grade"]}_{role}' for world in worlds
               for role in ('ore_structure', 'ore_conduct', 'ore_store')}
    for key, quantity in value.items():
        if key not in allowed:
            raise ValueError('开拓库存只能保存原普通物资编号')
        counter(quantity)
        if quantity > 10000:
            raise ValueError('开拓库存超出容量')
    if sum(value.values()) > 10000:
        raise ValueError('开拓库存超出总容量')


def validate_outposts(rows):
    if type(rows) is not dict or len(rows) > 8:
        raise ValueError('开拓驻地目录无效')
    people = set()
    for key, row in rows.items():
        keys = {'id', 'owner_id', 'owner_kind', 'issuer_id', 'source', 'destination', 'home',
                'status', 'progress', 'stock', 'units', 'sequence', 'governor_id', 'last_year', 'visit', 'history'}
        if type(row) is not dict or set(row) - {'development', 'military'} != keys or not is_target(key) or row['id'] != key or not isinstance(row['owner_id'], str):
            raise ValueError('开拓驻地身份或字段无效')
        if (not paired(row['source'], row['destination']) or target_for(row['owner_id'],row['source'],row['destination']) != key
                or row['owner_kind'] not in {'sect', 'family'} or not isinstance(row['issuer_id'], str)
                or not isinstance(row['home'], str) or not row['home']
                or row['status'] not in {'authorized', 'building', 'active', 'suspended', 'withdrawing', 'closed'}):
            raise ValueError('开拓地址、授权或阶段无效')
        for field in ('progress', 'sequence', 'last_year'):
            counter(row[field])
        if row['progress'] > BUILD_YEARS or row['status'] == 'active' and row['progress'] != BUILD_YEARS:
            raise ValueError('开拓施工进度无效')
        stock(row['stock'], row['source'], row['destination'])
        if 'development' in row:
            validate_development(row['development'])
        if 'military' in row:
            mandate(row['military'], row)
        if type(row['units']) is not list or len(row['units']) > 12:
            raise ValueError('开拓门人名册无效')
        wallets = set()
        if sum(u.get('phase') not in {'home', 'lost'} for u in row['units'] if isinstance(u, dict)) > 3:
            raise ValueError('开拓同时派驻人数超限')
        local_people = set()
        for unit in row['units']:
            if type(unit) is not dict or set(unit) - {'local_job', 'war_id'} != {'person_id', 'phase', 'progress', 'duration', 'road', 'road_years', 'wallet', 'stock', 'courier', 'delivered', 'last_year'}:
                raise ValueError('开拓门人行程字段无效')
            identity = unit['person_id']
            if not isinstance(identity, str) or identity in local_people or unit['phase'] not in PHASES or type(unit['courier']) is not bool:
                raise ValueError('开拓门人重复或阶段无效')
            if type(unit['delivered']) is not bool or unit['phase'] in {'gathering', 'outbound'} and unit['delivered']:
                raise ValueError('开拓到货状态与实际行程不符')
            local_people.add(identity)
            if unit['phase'] not in {'home', 'lost'}:
                if identity in people:
                    raise ValueError('同一原门人不能同时派驻多个目的界')
                people.add(identity)
            for field in ('progress', 'duration', 'road_years', 'last_year'):
                counter(unit[field])
            if unit['progress'] > unit['duration'] or not isinstance(unit['wallet'], str):
                raise ValueError('开拓行程进度无效')
            if unit['wallet'] in wallets:
                raise ValueError('开拓人员不能共享随身资金账户')
            wallets.add(unit['wallet'])
            durations = {CROSSING_YEARS} if unit['phase'] in {'outbound', 'returning'} else {unit['road_years']} if unit['phase'] == 'gathering' else {0, unit['road_years']} if unit['phase'] == 'homeward' else {0}
            if unit['phase'] not in LOCAL_PHASES and unit['duration'] not in durations:
                raise ValueError('开拓工期与行程阶段不一致')
            validate_job(unit, row, stock)
            if unit['phase'] == 'campaign' and (not isinstance(unit.get('war_id'), str) or not row.get('military') or unit['courier'] or not unit['delivered']):
                raise ValueError('驻地出征须有原军令、已到场原门人及原战役引用')
            if unit.get('local_job'):
                if unit['local_job']['wallet'] in wallets:
                    raise ValueError('地方行程资金不能与其他运输账户共用')
                wallets.add(unit['local_job']['wallet'])
            if (type(unit['road']) is not list or not unit['road'] or unit['road'][0] != row['home']
                    or unit['road'][-1] != ENDPOINTS[row['source']] or any(not isinstance(loc, str) for loc in unit['road'])):
                raise ValueError('开拓集结道路无效')
            stock(unit['stock'], row['source'], row['destination'])
        if sum(row['stock'].values()) + sum(sum(u['stock'].values()) + sum(u.get('local_job', {}).get('stock', {}).values()) for u in row['units']) > 10000:
            raise ValueError('驻地及原在途物资总量超出容量')
        if row['governor_id'] is not None and row['governor_id'] not in {u['person_id'] for u in row['units']}:
            raise ValueError('开拓负责人须引用原派驻名册')
        visit = row['visit']
        if visit is not None:
            if type(visit) is not dict or set(visit) != {'status', 'return_fare'} or visit['status'] not in {'preparing', 'visiting', 'returned', 'cancelled', 'failed'}:
                raise ValueError('开拓个人往返许可无效')
            counter(visit['return_fare'])
            if visit['return_fare'] > CROSSING_YEARS * profile(row['source'])['annual']:
                raise ValueError('开拓返程预留超出实付')
        if type(row['history']) is not list or len(row['history']) > 24:
            raise ValueError('开拓纪要超出容量')
        for entry in row['history']:
            if type(entry) is not dict or set(entry) != {'year', 'text'} or not isinstance(entry['text'], str):
                raise ValueError('开拓纪要无效')
            counter(entry['year'])


def validate_task(task, row):
    if (task['action'] not in TIMED_ACTIONS or task['person_id'] is not None or task['cycle'] != 0
            or task['duration'] != (1 if task['action'] == 'outpost_wait' else CROSSING_YEARS)):
        raise ValueError('开拓亲自行程无效')
    escrow = task['escrow']
    cost = 0 if task['action'] == 'outpost_wait' else CROSSING_YEARS * profile(row['source'])['annual']
    if (escrow['total'] != cost or escrow['spent'] != cost * task['progress'] // task['duration']
            or escrow['material'] is not None or escrow['mp_paid'] != 0
            or task['status'] == 'completed' and task['progress'] != task['duration']):
        raise ValueError('开拓亲自行程路费无效')
    if task['action'] != 'outpost_wait' and row['visit'] is None:
        raise ValueError('开拓亲自行程缺少往返许可')


def validate_references(game):
    validate_conquest_wars(game)
    rows = game.heavens_state.get('runtime', {}).get('outposts', {})
    if not rows:
        return
    raw = [*game.world_npcs, *game.notable_npcs, *game.inactive_npcs, *game.relationship_npcs]
    raw += [n.id for s in game.sects.values() for n in s.npcs]
    if game.family:
        raw += [n.id for n in game.family.npcs]
    accounts = game.economy_v2.get('accounts', {})
    for row in rows.values():
        entity = game.family if game.family and game.family.id == row['owner_id'] else game.sects.get(row['owner_id'])
        if not entity or row['issuer_id'] != game.id or row['owner_kind'] != ('family' if entity is game.family else 'sect'):
            raise ValueError('开拓原势力或批准者引用丢失')
        local = f'heavens-{row["id"]}:local'
        if local not in accounts:
            raise ValueError('开拓当地原账目丢失')
        for unit in row['units']:
            job = unit.get('local_job')
            if job and (job['wallet'] not in accounts or not job['wallet'].startswith(f'heavens-{row["id"]}:job:')):
                raise ValueError('地方行程原运输账户丢失')
            if raw.count(unit['person_id']) != 1 or unit['wallet'] not in accounts or not unit['wallet'].startswith(f'heavens-{row["id"]}:cargo:'):
                raise ValueError('开拓门人必须只有一个权威名册及原运输账户')
            identity = unit['person_id']
            if unit['phase'] not in {'home', 'lost'}:
                for w in game.wars:
                    if w.get('status') not in {'active', 'peace_ready', 'withdrawing'} or not any(identity in ids for ids in w.get('roster', {}).values()):
                        continue
                    same = w.get('outpost_id') == row['id']
                    returned = same and any(j['person_id'] == identity and j['phase'] in {'home', 'lost'} for rows in w.get('journeys', {}).values() for j in rows)
                    if not returned and not (same and unit.get('war_id') == w['id']):
                        raise ValueError('开拓人物不能同时出征其他战役')
                for echo in ([game.heavens_state['runtime']['sea_echo']] if game.heavens_state['runtime'].get('sea_echo') else []) + list(game.heavens_state['runtime'].get('contacts', {}).values()):
                    if any(echo.get(key, {}).get('status') == 'active' and echo[key].get('person_id', echo['visitor_id']) == identity for key in ('mission', 'freight', 'migration')):
                        raise ValueError('开拓人物不能重复占用其他行程')
