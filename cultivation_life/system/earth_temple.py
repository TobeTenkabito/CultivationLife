"""Original land-temple network and local services through real yearly actions."""
import copy
import hashlib
import json

from ..building_schema import address
from ..building_rules import ensure_state, may_use
from ..content_registry import ITEM_CATALOG
from ..economy_content import BASE_PRICES, material_id
from ..models import HistoryRecord
from ..runtime import now_iso
from . import building_projects as construction
from .building_assets import local_rows
from .earth_temple_rules import state, temple, city, reason, local_reason, bonus, root, ledgers, occupied_reason, slots
from . import earth_temple_network as network
from . import earth_temple_facilities as facilities
from . import earth_disputes as disputes
from .westward_rules import enabled
from .immortal_identity_rules import official


DUTIES = {
    'watch': dict(name='巡境护民', mark='境', description='勘查城郊公共道路，定期巡守并维护沿途警示。',
                  role='ore_structure', count=12, labor=120, trust=10),
    'care': dict(name='庙前济用', mark='生', description='核对庙前公共设施，补置导灵器材并持续照料。',
                 role='ore_conduct', count=8, labor=180, trust=15),
    'teach': dict(name='开坛讲习', mark='教', description='筹备凡人可听的养生与识险讲习，亲自轮值授课。',
                  role='ore_store', count=4, labor=80, trust=5),
}


def signature(game):
    facts = dict(earth=root(game), age=game.player.age, place=address(game), opportunity=game.player.opportunity,
                 network=[(temple(game,s['temple_id']),city(game,temple(game,s['temple_id']))) for s in ledgers(game)],
                 city=city(game), temple=temple(game), inventory=[(i.id, i.quantity) for i in game.player.inventory],
                 cities=[r for r in local_rows(game) if r['type'] == 'city'])
    return hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def bill(game, *, kind=None, careful=False):
    rank = construction.grade('celestial')
    if kind:
        spec = DUTIES[kind]
        scale = 2 if careful else 1
        materials = {material_id('celestial', rank, spec['role']): (spec['count'] + scale - 1) // scale}
        coins = int(BASE_PRICES[rank - 1] * spec['labor']) // scale
    else:
        costs = construction.land_temple_cost('celestial')
        materials, coins = costs['materials'], costs['coins']
    held = {i.id: i.quantity for i in game.player.inventory}
    missing = held.get('spirit_stone', 0) < coins or any(held.get(k, 0) < n for k, n in materials.items())
    return dict(coins=coins, materials=materials, reason='灵石或工程材料不足' if missing else '')


def view_bill(game, value):
    held = {i.id: i.quantity for i in game.player.inventory}
    return dict(value, recipe=[dict(id=k, name=ITEM_CATALOG[k].name, needed=n, owned=held.get(k, 0))
                               for k, n in value['materials'].items()])


def build_reason(game, target, maps=None):
    if blocked := reason(game):
        return blocked
    if (not target or target['type'] != 'city' or target['address'] != address(game)
            or target.get('population') not in {'mortal', 'mixed'}
            or not may_use(target, 'player', game.id)):
        return '须在有使用许可且完好的凡人城或混居城奉建'
    # One local catchment, even when several cities share a map location.
    if any(r.get('subtype') == 'land_temple' for r in local_rows(game)):
        return '此地已有土地庙或原庙遗址，不可重复占用同一地区香火'
    if root(game).get('temple_id'):
        if blocked := network.branch_reason(game, maps):
            return blocked
    return bill(game)['reason']


def duty_reason(game):
    if blocked := local_reason(game):
        return blocked
    s = state(game)
    if blocked := occupied_reason(game):
        return blocked
    if s.get('allowance', 0) > 0 and game.player.age < s.get('until', 0):
        return '本轮香火尚未用尽；不可覆盖额度或提前刷新期限'
    return ''


def work_reason(game):
    if disputes.current(game): return disputes.work_reason(game)
    if blocked := local_reason(game):
        return blocked
    duty = state(game).get('duty')
    if duty and duty.get('special') and duty['kind'] not in slots(game):
        return '原专项设施不可用，须恢复设施后继续原案'
    return ''


def begin_work(game):
    if disputes.current(game): return disputes.begin_work(game)
    if blocked := work_reason(game):
        raise ValueError(blocked)
    works = state(game).get('works')
    if works:
        if works['progress'] >= works['years']:
            raise ValueError('实际施工已完成，请办理竣工')
        return works['years'] - works['progress']
    duty = state(game).get('duty')
    if not duty:
        raise ValueError('请先承接地方事务')
    limit = 10 if duty['stage'] == 'survey' else duty['years']
    if duty['progress'] >= limit:
        raise ValueError('勘查已完成，请选择方案；履约完成后请验收')
    return limit - duty['progress']


def finish_work(game, elapsed, time_unit, identity=None):
    s = state(game, identity)
    duty = disputes.current(game,identity) or s.get('works') or s['duty']
    duty['progress'] = min(duty['years'], duty['progress'] + max(0, elapsed))
    # Share the paid short-action remainder with Yaochi projects.
    westward = game.yaochi_state['westward']
    units, westward['settlement_years'] = divmod(westward.get('settlement_years', 0) + max(0, elapsed), time_unit)
    return units


def action(deps, game, command, token, amount):
    if type(amount) is not int or amount != 1:
        raise ValueError('庙务每次只能办理一件')
    parts = token.split('|') if isinstance(token, str) else []
    if not parts or parts[0] != signature(game):
        raise ValueError('庙务记录或报价已变化，请刷新后重试')
    target = parts[1] if len(parts) == 2 else ''
    recovery = command in {'earth_cancel', 'earth_suspend', 'earth_cancel_works'}
    blocked = (disputes.access(game,disputes.current(game),recovery=True) if command.startswith('earth_case_') or command=='earth_work' and disputes.current(game)
               else reason(game) if command == 'earth_build' else local_reason(game, recovery=recovery or command == 'earth_resume'))
    if blocked:
        raise ValueError(blocked)
    s = state(game)
    if command.startswith('earth_case_'):
        summary = disputes.command(game,deps.maps,command,target)
    elif command == 'earth_build':
        original = next((r for r in local_rows(game) if r['id'] == target), None)
        if blocked := build_reason(game, original, deps.maps):
            raise ValueError(blocked)
        cost = bill(game)
        construction.pay(game, cost, '奉建土地庙')
        buildings = ensure_state(game)
        buildings['sequence'] += 1
        identity = f"land-temple:{game.id}:{buildings['sequence']}"
        parent = network.parent_for(game, deps.maps) if root(game).get('temple_id') else None
        buildings['records'][identity] = dict(id=identity, name=original['name'] + ('土地分庙' if parent else '土地庙'),
            type='artificiality', subtype='land_temple', level=1, status='intact', address=address(game),
            owner=dict(kind='player', id=game.id), users=[], public=False, city_id=original['id'],
            description='供奉当地居民的土地庙；主持护民，香火助修。',
            **({'parent_temple_id':parent['id']} if parent else {}))
        main = game.yaochi_state.setdefault('westward', {}).setdefault('earth', {})
        s = main.setdefault('branches', {}).setdefault(identity, {}) if parent else main
        s.update(temple_id=identity, active=not official(game), trust=50, allowance=0, until=0, completed=0, revision=0)
        summary = ('分庙' if parent else '主庙') + '奉建完成，香火信任50。须在本地实际护民取得本庙助修；各庙不叠加、不转移额度，城市仍归原主。'
    elif command == 'earth_facility':
        summary = facilities.start_works(game, target)
    elif command == 'earth_complete_works':
        summary = facilities.finish_works(game)
    elif command == 'earth_cancel_works':
        if not s.get('works'):
            raise ValueError('没有待退出的专项营造')
        s.pop('works')
        summary = '退出专项营造；该设施位保持空置，已投入的工料与实际工时不返还，旧设施不复原。'
    elif command == 'earth_special':
        summary = facilities.execute(game, target, duty_reason(game))
    elif command == 'earth_accept':
        if blocked := duty_reason(game):
            raise ValueError(blocked)
        if target not in DUTIES:
            raise ValueError('未知地方事务')
        s['duty'] = dict(kind=target, started=game.player.age, stage='survey', progress=0, years=100)
        summary = f"承接{DUTIES[target]['name']}：先亲自勘查10年，再选择投入方案。此案只换香火，不另发功德功勋。"
    elif command == 'earth_work':
        begin_work(game)
        return deps.advance(game.id, 'earth_service', 1)
    elif command == 'earth_cultivate':
        if not s.get('allowance') or game.player.age >= s.get('until', 0):
            raise ValueError('当前没有可用的本地香火助修额度')
        return deps.advance(game.id, 'cultivate', 1)
    elif command == 'earth_plan':
        duty = s.get('duty')
        if not duty or duty['stage'] != 'survey' or duty['progress'] != 10 or target not in {'standard', 'careful'}:
            raise ValueError('须先完成勘查，再选择当前方案')
        careful = target == 'careful'
        cost = bill(game, kind=duty['kind'], careful=careful)
        construction.pay(game, cost, DUTIES[duty['kind']]['name'] + '实付筹备')
        duty.update(stage='service', years=150 if careful else 100, plan=target, paid=copy.deepcopy(cost))
        summary = f"方案已落实，物资投入原址使用；累计须履约{duty['years']}年。取消不返还已投入物资，且已耗年份不返还。"
    elif command == 'earth_claim':
        if blocked := work_reason(game):
            raise ValueError(blocked)
        duty = s.get('duty')
        if not duty or duty['stage'] != 'service' or duty['progress'] < duty['years']:
            raise ValueError('实际履约工时尚未完成')
        s['trust'] = min(100, s['trust'] + DUTIES[duty['kind']]['trust'])
        s.update(allowance=400 if not official(game) and game.player.age < duty['started'] + 500 else 0,
                 until=duty['started'] + 500, completed=s['completed'] + 1)
        summary = f"{DUTIES[duty['kind']]['name']}验收完成，信任升至{s['trust']}。本地助修额度{s['allowance']}年，截止世界历{s['until']}年；到期不补发。"
        s.pop('duty')
    elif command == 'earth_cancel':
        duty = s.get('duty')
        if not duty:
            raise ValueError('没有待退出的地方事务')
        loss = 10 if duty['progress'] else 0
        s['trust'] = max(0, s['trust'] - loss)
        s.pop('duty')
        summary = f'退出地方事务，信任减少{loss}；已投入资材及实际工时不返还，未取得香火额度。'
    elif command in {'earth_suspend', 'earth_resume'}:
        if s.get('duty') or s.get('works') or disputes.current(game):
            raise ValueError('请先完成或退出已承接的地方事务')
        active = command == 'earth_resume'
        if active:
            if official(game):raise ValueError('须先在玉京交接玄仙职司及七曜席位，再恢复地仙主持')
            if blocked := reason(game):
                raise ValueError(blocked)
        if s['active'] == active:
            raise ValueError('主持状态已经变化，请刷新')
        s['active'] = active
        summary = '恢复地仙主持，旧香火额度与期限保持不变。' if active else '暂停地仙主持，停止香火助修；庙宇仍留原址，旧额度不续期。'
    else:
        raise ValueError('未知庙务')
    s['revision'] += 1
    s['last_result'] = summary
    game.history.append(HistoryRecord('SYS_EARTH_TEMPLE', 1, game.player.age, '地仙庙域', command,
                                     'completed', summary, {}, ['building', 'yaochi']))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def public(game, maps=None):
    s, original = state(game), temple(game)
    if not (original or enabled() and game.player.path == 'dao' and game.player.realm_index >= 9):
        return dict(available=False)
    stamp = signature(game)
    duty = copy.deepcopy(s.get('duty'))
    if duty:
        duty.update(name=DUTIES[duty['kind']]['name'], work_reason=work_reason(game),
                    cancel_reason=local_reason(game, recovery=True))
        duty['plans'] = [dict(id=key, name=name, years=years, **view_bill(game, bill(game, kind=duty['kind'], careful=key=='careful')))
                         for key, name, years in [('standard', '备足资材 · 常规履约', 100), ('careful', '节用亲为 · 多付工时', 150)]]
    here = bool(original and original['address'] == address(game))
    return dict(available=True, enabled=enabled(), token=stamp, active=s.get('active', False),
        local=here, network=network.public(game, maps), main_id=root(game).get('temple_id'),
        occupied_reason=occupied_reason(game), facilities=facilities.public(game, duty_reason(game)) if original else None,
        disputes=disputes.public(game,maps) if original else None,
        reason=local_reason(game) if original else reason(game), temple=copy.deepcopy(original),
        city_name=(city(game) or {}).get('name', ''), trust=s.get('trust', 50),
        allowance=s.get('allowance', 0) if game.player.age < s.get('until', 0) else 0,
        until=s.get('until', 0), bonus=bonus(game), potential_bonus=s.get('trust', 50)*.005,
        duty=duty, completed=s.get('completed', 0), last_result=s.get('last_result', ''),
        recovery_reason=local_reason(game, recovery=True), resume_reason=reason(game) or ('须先交接玄仙编制再恢复主持' if official(game) else '') or local_reason(game, recovery=True),
        build_cost=view_bill(game, bill(game)),
        cities=[dict(id=r['id'], name=r['name'], population=r.get('population'), reason=build_reason(game, r, maps))
                for r in local_rows(game) if r['type']=='city'] if not here else [],
        duties=[dict(id=k, **v, reason=duty_reason(game), cost=view_bill(game, bill(game, kind=k)))
                for k,v in DUTIES.items()])
