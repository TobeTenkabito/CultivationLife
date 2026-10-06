"""One saved location, finite duties and separately delegated peace authority."""
from .campaign_definitions import SOURCE, DEFENDER, TARGET_SITE, ANNUAL_COST
from .campaign_logistics import stationed, located
from .settlement_definitions import ADMIN_COST, TERM_YEARS, CONTROL_NAMES, TREATY_NAMES, CLAUSES
from .state import record


def ensure(row):
    return row.setdefault('settlement', dict(control='original', ever_occupied=False,
        governor_id=None, garrison_id=None, administration_spent=0, mandates={},
        treaty=None, treated=[], outcome=None, concluded_at=None))


def delegate(deps, game, row, faction, now):
    """Issue a separate, scoped letter before the original delegate leaves home."""
    state = ensure(row)
    if faction in state['mandates']:
        return
    role = 'builder' if faction == SOURCE else 'defender'
    unit = next((u for u in row['units'] if u['role'] == role), None)
    if not unit or unit['phase'] != 'gathering':
        return
    facts = deps.campaign_facts(game, unit)
    if not facts['free'] or facts['location'] != unit['home']:
        return
    authority = deps.campaign_authority(game, faction, 'local_settlement')
    if authority:
        state['mandates'][faction] = dict(**authority, delegate_id=unit['person_id'],
            world='human', location=TARGET_SITE, granted_at=now, expires_at=now+600)


def valid_mandate(deps, game, mandate, now):
    current = deps.campaign_authority(game, mandate['faction_id'], 'local_settlement')
    return bool(current and current['issuer_id'] == mandate['issuer_id'] and now <= mandate['expires_at'])


def treaty_active(row):
    return bool(row.get('settlement', {}).get('treaty')
                and row['settlement']['treaty']['status'] == 'active')


def before_year(deps, game, row, now, withdraw):
    state = ensure(row)
    for faction in (SOURCE, DEFENDER):
        delegate(deps, game, row, faction, now)
    treaty = state['treaty']
    if not treaty or treaty['status'] != 'active':
        return
    if not all(valid_mandate(deps, game, m, now) for m in state['mandates'].values()):
        treaty['status'] = 'review'
        withdraw(row, '签署职权发生继任或失效，停止附约驻防；原撤离与救护许可保留')
    elif now >= treaty['expires_at']:
        treaty['status'] = 'expired'
        withdraw(row, '岚疆协议期满，按原路线结束有限部署')


def control(deps, game, row):
    """Read actual people and stock, including between two annual callbacks."""
    state = row.get('settlement')
    if not state:
        return 'original', None, None
    soldier = stationed(deps, game, row, 'soldier')
    defender = stationed(deps, game, row, 'defender')
    builder = stationed(deps, game, row, 'builder')
    supplied = (row['status'] == 'active' and row['gate']['state'] == 'open'
                and row['supply']['target'] > 0)
    if soldier and supplied:
        if defender:
            if treaty_active(row) and state['treaty']['kind'] == 'vassal':
                return 'vassal', defender, soldier
            return 'contested', None, soldier
        if builder:
            return 'occupied', builder, soldier
    if defender:
        return ('restored' if state['ever_occupied'] else 'original'), defender, None
    return ('uncontrolled' if state['ever_occupied'] else 'original'), None, None


def after_year(deps, game, row, now, withdraw):
    state = ensure(row)
    previous = state['control']
    status, governor, garrison = control(deps, game, row)
    treaty = state['treaty']
    if (treaty_active(row) and treaty['kind'] == 'vassal'
            and (not stationed(deps, game, row, 'defender') or row['status'] != 'active'
                 or state['ever_occupied'] and status != 'vassal')):
        treaty['status'] = 'lapsed'
        withdraw(row, '附约的实际守备或保障已失去，不能延续地方管辖')
        status, governor, garrison = control(deps, game, row)
    if status in {'occupied', 'vassal'}:
        reserve = sum((u['road_years']+8)*ANNUAL_COST for u in row['units'] if u['faction_id'] == SOURCE)
        if row['budget']['total']-row['budget']['spent'] < reserve+ADMIN_COST:
            withdraw(row, '地方护路经费不足，只保留实际撤离储备')
            status, governor, garrison = control(deps, game, row)
        else:
            row['budget']['spent'] += ADMIN_COST
            state['administration_spent'] += ADMIN_COST
            state['ever_occupied'] = True
    state.update(control=status, governor_id=governor['person_id'] if governor else None,
                 garrison_id=garrison['person_id'] if garrison else None)
    if previous != status and not deps.frontier_player_reason(game, TARGET_SITE):
        text = f'岚疆现场秩序变为「{CONTROL_NAMES[status]}」。范围只及此地，普通修行与撤离仍可继续。'
        row['known'] = True
        row['reports'] = (row['reports']+[dict(kind='control', text=text, year=now)])[-24:]
        record(game, text, year=now)
    if row['status'] in {'withdrawn', 'failed'} and state['outcome'] is None:
        state['outcome'] = (treaty['kind'] if treaty else 'defended' if row['gate']['state'] == 'destroyed'
                            else 'occupation_ended' if state['ever_occupied'] else 'expedition_ended')
        state['concluded_at'] = now


def sign(deps, game, row, kind, now, withdraw):
    state = ensure(row)
    state['treaty'] = dict(kind=kind, status='active', signed_at=now, expires_at=now+TERM_YEARS,
        world='human', location=TARGET_SITE, signatories={k: m['delegate_id'] for k, m in state['mandates'].items()})
    if kind != 'vassal':
        withdraw(row, '双方具名代表已订立'+TREATY_NAMES[kind]+'，停止输送并实际撤回')


def public(deps, game, row):
    state = row.get('settlement')
    if not state:
        return None
    local = not deps.frontier_player_reason(game, TARGET_SITE)
    result = dict(local=local, site='岚疆草原', policies=['普通修行与调息开放', '允许沿本界道路离境', '军事占领期间暂停当地冒险取材'],
                  clauses=CLAUSES, treaty=None, control=None, duties=[], patients=[], resolution=None)
    if local:
        status, governor, garrison = control(deps, game, row)
        result['control'] = CONTROL_NAMES[status]
        source_present = any(u['faction_id'] == SOURCE and located(deps, game, u, 'human', TARGET_SITE) for u in row['units'])
        if not source_present and row['gate']['state'] in {'destroyed', 'interrupted'}:
            result['resolution'] = '当地来方军队已经离开，军事输送停止。' + ('旧驻防仍待实际重建。' if state['ever_occupied'] and not governor else '可继续在本地修行或沿原道路离开。')
        for duty, unit in [('地方秩序', governor), ('驻防护路', garrison)]:
            if unit:
                result['duties'].append(dict(duty=duty, name=deps.campaign_facts(game, unit)['name']))
        for unit in row['units']:
            facts = deps.campaign_facts(game, unit)
            if located(deps, game, unit, 'human', TARGET_SITE) and facts['wounds'] > 0:
                result['patients'].append(dict(id=unit['person_id'], name=facts['name'], wounds=facts['wounds'],
                                               treated=unit['person_id'] in state['treated']))
    if state['treaty']:
        # The player mediated this signed document; remote troop status stays private.
        treaty = state['treaty']
        result['treaty'] = dict(name=TREATY_NAMES[treaty['kind']], kind=treaty['kind'],
                               signed_at=treaty['signed_at'], expires_at=treaty['expires_at'],
                               clauses=CLAUSES[treaty['kind']])
    return result
