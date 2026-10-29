"""Local organization work funded and carried by the original frontier people."""
import hashlib
import json
import math
import random

from ..territory import state as territory, anchors, revenue
from ..territory.rules import POLICIES, permits, DECAY_PER_YEAR
from ..territory.geography import validate_claim, change_claim, contest_chance
from ..economy.ledger import account, balance, transfer_value
from ..economy.basket_trade import quote as market_quote, purchase
from ...regional_context import task_active, historical
from . import outpost_runtime as base
from .outpost_definitions import ENDPOINTS
from .outpost_routes import profile
from .development_definitions import LABELS, JOBS, LOCAL_PHASES, MAX_CLAIMS


def book(game, row):
    return territory.state(game)['holdings'].setdefault(row['destination'], {})


def ready(deps, game, row, *, operating=True):
    if operating and not anchors.operational(game, row):
        raise ValueError('须有正常运营的驻地及实际在场的自由负责人')
    entity = deps.outpost_owner(game, row['owner_id'])
    if not deps.outpost_control(game, entity, row):
        raise ValueError('原势力开拓控制权已失效')
    if (game.player.world, game.player.location_id) != (row['destination'], ENDPOINTS[row['destination']]):
        raise ValueError('须亲自到异界分驻地安排当地经营')


def workers(deps, game, row):
    return [dict(id=u['person_id'], name=deps.resolve_person(game, u['person_id']).name)
            for u in row['units'] if not u['courier'] and u['delivered']
            and u['person_id'] != row['governor_id'] and base.located(deps, game, row, u)]


def local_quote(deps, game, row):
    market = game.economy_v2.get('markets', {}).get(f'{row["destination"]}:{ENDPOINTS[row["destination"]]}')
    required = base.materials(row['destination'])
    bills = {}
    if market:
        for key, quantity in required.items():
            item = market['commodities'].get(key.removeprefix('item:'))
            if item and item['stock'] >= quantity:
                bills[key] = market_quote(item, 'buy', quantity)
    total = sum(r['total'] for r in bills.values())
    fingerprint = hashlib.sha256(json.dumps(dict(market=market['id'] if market else None,
        revision=market['revision'] if market else None, bills=bills), sort_keys=True).encode()).hexdigest()
    return market, required, bills, total, fingerprint


def job_plan(deps, game, row, action, options):
    terms = profile(row['source'])
    annual = terms['annual']
    location = options['location_id']
    maps = deps.outpost_maps()
    visible = territory.snapshot(game, maps, row['destination'])
    validate_claim(maps, row['destination'], visible, row['owner_id'], location,
                   existing=action == 'outpost_build_site')
    if deps.outpost_site_reason(game, row, location):
        raise ValueError(deps.outpost_site_reason(game, row, location))
    owned = visible.get(location, {}).get(row['owner_id'], {})
    if action == 'outpost_expand' and owned.get('value', 0) >= 100:
        raise ValueError('当地影响力已经达到上限')
    if action == 'outpost_build_site' and owned.get('outpost'):
        raise ValueError('当地已有本势力驻点')
    if location not in row['development']['claims'] and len(row['development']['claims']) >= MAX_CLAIMS:
        raise ValueError('首期经营最多八处实际地区')
    if any(u.get('local_job', {}).get('status') == 'active' and u['local_job']['location_id'] == location for u in row['units']):
        raise ValueError('当地已有原门人处理事务，请待其结束')
    identity = options['person_id']
    if identity not in {w['id'] for w in workers(deps, game, row)}:
        raise ValueError('须另有已到场的空闲驻守门人；负责人留守原驻地')
    npc = deps.resolve_person(game, identity)
    origin = ENDPOINTS[row['destination']]
    outward = deps.outpost_road(game, row['destination'], origin, location, npc.realm_index)
    homeward = deps.outpost_road(game, row['destination'], location, origin, npc.realm_index)
    if not outward or not homeward:
        raise ValueError('原门人没有合法的当地往返道路')
    cargo = {}
    if action == 'outpost_build_site':
        for role, quantity in (('ore_structure', 6), ('ore_conduct', 2), ('ore_store', 2)):
            for world in (row['source'], row['destination']):
                key = f'item:econ_{world}_{terms["grade"]}_{role}'
                if row['stock'].get(key, 0) >= quantity:
                    cargo[key] = quantity
                    break
            else:
                raise ValueError('当地仓库须备齐构材6、导灵矿2、储能矿2，可采购或从总部运入')
    if action == 'outpost_spar':
        rival = options['rival_id']
        if rival == row['owner_id'] or rival not in visible.get(location, {}):
            raise ValueError('须选择当地确有影响力的其他势力')
        opponents = deps.outpost_local_people(game, row, location, rival)
        if npc.realm_index < terms['minimum'] or not any(n.realm_index >= terms['minimum'] for n in opponents):
            raise ValueError('双方须有符合本界层修为、实际在场且可应约的修士')
    cost = JOBS[action][2]*terms['scale'] + (outward['years'] + homeward['years']) * annual
    if balance(game, base.wallet(row)) < cost + 3 * annual:
        raise ValueError(f'当地经费不足，须预留本次 {cost} 灵石及原驻地三年养护{3*annual}灵石')
    return dict(outward=outward, homeward=homeward, cargo=cargo, cost=cost)


def quote(deps, game, row, action, options):
    terms = profile(row['source'])
    annual = terms['annual']
    costs = {}
    ready(deps, game, row, operating=action not in {'outpost_invest', 'outpost_cancel_local', 'outpost_buy_materials'})
    if action == 'outpost_invest':
        if row['progress'] != 10 or row['status'] not in {'active', 'suspended'} or balance(game, 'player') < terms['transfer']:
            raise ValueError(f'须有已建成且未撤回的驻地，以及个人实有{terms["transfer"]}灵石')
        return dict(years=0, costs={'stones': terms['transfer']}, refundable={}, message=f'本人现场实付{terms["transfer"]}灵石进入当地原账户，可用于恢复养护与经营。')
    if action == 'outpost_develop':
        if row.get('development'):
            raise ValueError('已经开办地方经营，不会重置旧收益和工期')
        maps = deps.outpost_maps()
        visible = territory.snapshot(game, maps, row['destination'])
        if len(visible.get(ENDPOINTS[row['destination']], {})) >= 3:
            raise ValueError('驻地当地经营席位已满，不能额外挤入第四方影响力')
        message = '登记实际驻地50点影响力。旧手续费不补领，原总部及既有势力归属不变。'
    else:
        if not row.get('development'):
            raise ValueError('请先在已建成驻地开办地方经营')
        message = '钱货留在当地，所有费用与收益使用真实原账目。'
        if action in JOBS:
            plan = job_plan(deps, game, row, action, options)
            return dict(years=0, costs={'organization_stones': plan['cost']}, refundable={},
                message=f'原门人去程{plan["outward"]["years"]}年、办事{JOBS[action][1]}年、返程{plan["homeward"]["years"]}年，原款及所需材料随身托管；负责人留守。',
                warning='途中受控、离位、失路或原驻地停办会暂停；死亡损失原随身钱货。')
        if action == 'outpost_buy_materials':
            market, required, bills, total, fingerprint = local_quote(deps, game, row)
            if options['quote_id'] != fingerprint:
                raise ValueError('当地资材报价已经变化，请刷新后重新采购')
            used = sum(row['stock'].values()) + sum(sum(u['stock'].values()) + sum(u.get('local_job', {}).get('stock', {}).values()) for u in row['units'])
            if len(bills) != len(required) or used + 10 > 10000:
                raise ValueError('当地市场资材不足或驻地仓库容量不足')
            if balance(game, base.wallet(row)) < total:
                raise ValueError('当地经费不足以采购整份真实资材')
            costs = {'organization_stones': total}
            message = f'从当地实际市场采购构材6、导灵矿2、储能矿2，共{total}灵石。'
        if action in {'outpost_policy', 'outpost_retract'}:
            loc = options['location_id']
            owned = territory.snapshot(game, deps.outpost_maps(), row['destination']).get(loc, {}).get(row['owner_id'])
            if not owned:
                raise ValueError('当地没有本势力实际影响力')
            if action == 'outpost_policy' and not permits(options['policy'], owned['value']):
                raise ValueError('该政策不适用于当地影响力等级')
            if action == 'outpost_retract' and loc == ENDPOINTS[row['destination']]:
                raise ValueError('原驻地请通过整处撤回办理')
            if action == 'outpost_retract' and any(u.get('local_job', {}).get('status') == 'active' and u['local_job']['location_id'] == loc for u in row['units']):
                raise ValueError('须先结束当地原任务')
        if action == 'outpost_cancel_local':
            if not any(u['person_id'] == options['person_id'] and u.get('local_job', {}).get('status') == 'active' for u in row['units']):
                raise ValueError('没有可结束的原地方行程')
        if action == 'outpost_export':
            if options['person_id'] not in {w['id'] for w in workers(deps, game, row)} or balance(game, base.wallet(row)) < terms['transfer'] + 3*annual:
                raise ValueError(f'须有空闲原门人，并留下三年养护后实有{terms["transfer"]}灵石可运回')
            message = f'原门人携当地{terms["transfer"]}灵石循原跨界路线返乡；抵达原仓库后才结入原势力府库，不直接加到玩家行囊。'
    return dict(years=0, costs=costs, refundable={}, message=message)


def execute(deps, game, row, action, options):
    terms = profile(row['source'])
    if action == 'outpost_develop':
        main = ENDPOINTS[row['destination']]
        row['development'] = dict(version=1, started_at=game.player.age, claims={main: game.player.age},
                                  income=0, expense=0, counter_decade=game.player.age // 10)
        change_claim(book(game, row), main, row['owner_id'], 'build_outpost')
        for market in game.economy_v2.get('markets', {}).values():
            if market['world'] == row['destination']:
                revenue.adopt(game, market)
    elif action == 'outpost_invest':
        transfer_value(game, 'player', base.wallet(row), terms['transfer'], '本人现场向原异界驻地实付注资')
    elif action == 'outpost_buy_materials':
        market, required, bills, total, fingerprint = local_quote(deps, game, row)
        for key, quantity in required.items():
            amount, paid = purchase(game, market, base.wallet(row), key.removeprefix('item:'), quantity, bills[key]['total'], '驻地采购原当地普通资材')
            if amount != quantity:
                raise ValueError('当地真实库存或现款已变化')
            row['stock'][key] = row['stock'].get(key, 0) + amount
            row['development']['expense'] += paid
    elif action in JOBS:
        plan = job_plan(deps, game, row, action, options)
        unit = next(u for u in row['units'] if u['person_id'] == options['person_id'])
        old = unit.get('local_job')
        if old and not balance(game, old['wallet']):
            game.economy_v2['accounts'].pop(old['wallet'], None)
        row['sequence'] += 1
        purse = f'heavens-{row["id"]}:job:{row["sequence"]}'
        account(game, purse)
        transfer_value(game, base.wallet(row), purse, plan['cost'], '地方行程预留原当地经费')
        for key, quantity in plan['cargo'].items():
            row['stock'][key] -= quantity
        unit['local_job'] = dict(action=action, location_id=options['location_id'], rival_id=options.get('rival_id', ''),
            out_route=plan['outward']['route'], return_route=plan['homeward']['route'], out_years=plan['outward']['years'],
            return_years=plan['homeward']['years'], wallet=purse, stock=dict(plan['cargo']), fee_spent=0,
            started_at=game.player.age, cancel_requested=False, installed=False, status='active', result=None)
        base.phase(unit, 'local_outbound', plan['outward']['years'])
        if not unit['duration']:
            base.phase(unit, 'local_work', JOBS[action][1])
    elif action == 'outpost_policy':
        change_claim(book(game, row), options['location_id'], row['owner_id'], 'territory_policy', policy=options['policy'])
    elif action == 'outpost_retract':
        book(game, row).get(options['location_id'], {}).pop(row['owner_id'], None)
        row['development']['claims'].pop(options['location_id'], None)
    elif action == 'outpost_cancel_local':
        next(u for u in row['units'] if u['person_id'] == options['person_id'])['local_job']['cancel_requested'] = True
    elif action == 'outpost_export':
        unit = next(u for u in row['units'] if u['person_id'] == options['person_id'])
        transfer_value(game, base.wallet(row), unit['wallet'], terms['transfer'], '原门人装运当地原款返乡')
        base.recall(row, unit)
    base.note(game, row, LABELS[action] + '：沿原人、原款与原地理记录办理。')
    return {'message': LABELS[action] + '已登记'}


def settle_claims(deps, game, row):
    terms = profile(row['source'])
    annual = terms['annual']
    dev = row.get('development')
    if not dev or not task_active(game, row['destination']):
        return
    holdings = book(game, row)
    visible = territory.snapshot(game, deps.outpost_maps(), row['destination'])
    for loc, previous in list(dev['claims'].items()):
        if previous >= game.player.age:
            continue
        dev['claims'][loc] = game.player.age
        owned = holdings.get(loc, {}).get(row['owner_id'])
        if not owned:
            dev['claims'].pop(loc, None)
            continue
        years = game.player.age - previous
        policy = POLICIES.get(owned.get('policy')) if permits(owned.get('policy'), owned['value']) else None
        if not policy:
            owned['policy'] = ''
        main = loc == ENDPOINTS[row['destination']]
        due = 0 if main else math.ceil(10*terms['scale'] * (owned['value'] / 100 + (.3 if owned['outpost'] else 0)) * (policy['upkeep'] if policy else 1) * years)
        available = max(0, balance(game, base.wallet(row)) - 3*annual) if anchors.operational(game, row) else 0
        paid = min(due, available)
        transfer_value(game, base.wallet(row), f'background:{row["destination"]}', paid, '异界外围地方真实巡守与养护')
        dev['expense'] += paid
        coverage = paid / max(1, due) if due else float(anchors.operational(game, row))
        if not main and coverage < .5:
            owned['outpost'] = False
        floor = visible.get(loc, {}).get(row['owner_id'], {}).get('floor', 0)
        if not owned['outpost'] or not anchors.operational(game, row):
            floor = 0
        owned['value'] = max(floor, owned['value'] - DECAY_PER_YEAR * years * (policy['decay'] if policy else 1) * (1 + 3 * (1 - coverage)))
        if owned['value'] <= 0 and not main:
            holdings[loc].pop(row['owner_id'], None)
            dev['claims'].pop(loc, None)


def reaction(deps, game, row, unit):
    terms = profile(row['source'])
    dev, job = row['development'], unit['local_job']
    if historical(game) or game.player.age // 10 <= dev['counter_decade']:
        return
    location = job['location_id']
    visible = territory.snapshot(game, deps.outpost_maps(), row['destination']).get(location, {})
    from ...world_state import race_pair
    for identity in sorted(visible):
        if identity == row['owner_id']:
            continue
        enemy = anchors.organization(game, identity)
        if not enemy or enemy.world != row['destination'] or enemy.extinct:
            continue
        people = deps.outpost_local_people(game, row, location, identity)
        treasury = f'organization:{"family" if enemy is game.family else "sect"}:{identity}'
        funds = game.intrigue_state.get('factions', {}).get(f'{"family" if enemy is game.family else "sect"}:{identity}', {}).get('resources', 0)
        if not people or funds < 1000*terms['scale']:
            continue
        dev['counter_decade'] = game.player.age // 10
        transfer_value(game, treasury, f'background:{row["destination"]}', 1000*terms['scale'], '当地原势力实付巡边抵制经费')
        own = deps.resolve_person(game, unit['person_id'])
        rank = max((p.realm_index, p.layer) for p in people)
        draw = random.Random(f'{game.seed}:{row["id"]}:counter:{game.player.age // 10}').random()
        won = draw < contest_chance(rank, (own.realm_index, own.layer))
        if won:
            owned = book(game, row)[location][row['owner_id']]
            floor = visible[row['owner_id']]['floor']
            owned['value'] = max(floor, owned['value'] - 12)
            if not owned['value']:
                book(game, row)[location].pop(row['owner_id'])
                dev['claims'].pop(location, None)
        relation = game.sect_relations.setdefault(race_pair(row['owner_id'], identity), dict(status='neutral', affinity=0))
        relation['affinity'] = max(-100, relation.get('affinity', 0) - 4)
        base.note(game, row, f'{enemy.name}以原在场修士出资抵制当地扩张，' + ('削弱了尚未稳固的影响。' if won else '未能撼动本次经营。'))
        return


def abandon(game, row):
    if not row.get('development'):
        return
    for loc in list(row['development']['claims']):
        book(game, row).get(loc, {}).pop(row['owner_id'], None)
    row['development']['claims'] = {}


def end_job(deps, game, row, unit, *, lost=False):
    job = unit.get('local_job')
    if not job or job['status'] != 'active':
        return
    if lost:
        transfer_value(game, job['wallet'], f'background:{row["destination"]}', balance(game, job['wallet']), '地方行程人物陨落，随身原款遗失')
        job['stock'] = {}
        job.update(status='lost', result='lost')
        return
    for key, quantity in job['stock'].items():
        row['stock'][key] = row['stock'].get(key, 0) + quantity
    job['stock'] = {}
    transfer_value(game, job['wallet'], base.wallet(row), balance(game, job['wallet']), '地方原门人返抵驻地，未耗原款归还')
    job['status'] = 'cancelled' if job['cancel_requested'] else 'done'
    base.phase(unit, 'stationed')
    base.note(game, row, '原地方办事门人已实际返回驻地，未耗钱货结清一次。')


def advance_job(deps, game, row, unit):
    terms = profile(row['source'])
    annual = terms['annual']
    job = unit['local_job']
    npc = deps.resolve_person(game, unit['person_id'])
    main, location = ENDPOINTS[row['destination']], job['location_id']
    if npc.world != row['destination']:
        return
    if row['status'] in {'withdrawing', 'closed'}:
        job['cancel_requested'] = True
    if job['cancel_requested'] and unit['phase'] != 'local_return':
        job['result'] = 'cancelled'
        base.phase(unit, 'local_return', 0 if npc.location_id == main else job['return_years'])
    stage = unit['phase']
    expected = main if stage == 'local_outbound' or stage == 'local_return' and not unit['duration'] else location
    if npc.location_id != expected:
        return
    if stage == 'local_work':
        if not anchors.operational(game, row) or deps.outpost_site_reason(game, row, location):
            return
        try:
            validate_claim(deps.outpost_maps(), row['destination'], territory.snapshot(game, deps.outpost_maps(), row['destination']), row['owner_id'], location,
                           existing=job['action'] == 'outpost_build_site')
        except ValueError:
            return
        opponents = [p for p in deps.outpost_local_people(game, row, location, job['rival_id']) if p.realm_index >= terms['minimum']] if job['action'] == 'outpost_spar' else []
        if job['action'] == 'outpost_spar' and not opponents:
            return
        if not job['installed']:
            job['stock'] = {}
            job['installed'] = True
        progress = unit['progress'] + 1
        spent = JOBS[job['action']][2]*terms['scale'] * progress // unit['duration']
        amount = spent - job['fee_spent']
        if balance(game, job['wallet']) < amount:
            return
        transfer_value(game, job['wallet'], f'background:{row["destination"]}', amount, '地方事务按实际工时支出原款')
        row['development']['expense'] += amount
        job['fee_spent'] = spent
    elif unit['progress'] < unit['duration']:
        route = deps.outpost_road(game, row['destination'], expected, location if stage == 'local_outbound' else main, npc.realm_index)
        if not route or route['years'] > unit['duration'] or balance(game, job['wallet']) < annual:
            return
        transfer_value(game, job['wallet'], f'background:{row["destination"]}', annual, '地方门人沿实际道路行旅')
        row['development']['expense'] += annual
    if unit['progress'] < unit['duration']:
        unit['progress'] += 1
    if unit['progress'] < unit['duration']:
        return
    if stage == 'local_outbound':
        deps.outpost_move_npc(game, npc.id, row['destination'], location)
        base.phase(unit, 'local_work', JOBS[job['action']][1])
    elif stage == 'local_return':
        deps.outpost_move_npc(game, npc.id, row['destination'], main)
        end_job(deps, game, row, unit)
    else:
        settle_claims(deps, game, row)
        won = True
        if opponents:
            enemy = max((p.realm_index, p.layer) for p in opponents)
            won = random.Random(f'{game.seed}:{job["wallet"]}').random() < contest_chance((npc.realm_index, npc.layer), enemy)
        holdings = book(game, row)
        owned = change_claim(holdings, location, row['owner_id'], JOBS[job['action']][0], won=won)
        if owned['value'] or owned['outpost']:
            row['development']['claims'].setdefault(location, game.player.age)
        else:
            holdings[location].pop(row['owner_id'], None)
            row['development']['claims'].pop(location, None)
        from ...world_state import race_pair
        rivals = [job['rival_id']] if job['action'] == 'outpost_spar' else [identity for identity in holdings[location] if identity != row['owner_id']] if job['action'] == 'outpost_expand' else []
        for identity in rivals:
            relation = game.sect_relations.setdefault(race_pair(row['owner_id'], identity), dict(status='neutral', affinity=0))
            relation['affinity'] = max(-100, min(100, relation.get('affinity', 0) + (2 if job['action'] == 'outpost_spar' else -4)))
        job['result'] = 'built' if job['action'] == 'outpost_build_site' else 'expanded' if job['action'] == 'outpost_expand' else 'won' if won else 'lost'
        base.note(game, row, f'{npc.name}在{deps.outpost_maps().location(row["destination"], location)["name"]}完成{LABELS[job["action"]]}。')
        reaction(deps, game, row, unit)
        base.phase(unit, 'local_return', job['return_years'])
        if not unit['duration']:
            end_job(deps, game, row, unit)


def project(deps, game, row, target_id, blocked_reason=None):
    result = dict(registered=bool(row and row.get('development')), actions=[], locations=[], workers=[], jobs=[])
    if not row:
        result['reason'] = '须先完成第一批驻地建设'
        return result
    local = (game.player.world, game.player.location_id) == (row['destination'], ENDPOINTS[row['destination']])
    if not local:
        result['reason'] = '须亲自抵达异界驻地核实经营与安排人员'
        return result
    result['workers'] = workers(deps, game, row)
    for unit in row['units']:
        job = unit.get('local_job')
        if job:
            npc = deps.resolve_person(game, unit['person_id'])
            result['jobs'].append(dict(person_id=unit['person_id'], name=npc.name if npc else '原门人',
                action=job['action'], label=LABELS[job['action']], location_name=deps.outpost_maps().location(row['destination'], job['location_id'])['name'],
                phase=unit['phase'], progress=unit['progress'], duration=unit['duration'], status=job['status'], result=job['result']))
    def control(action, options=None):
        item = dict(action=action, target_id=target_id, label=(f'现场注资{profile(row["source"])["transfer"]}灵石' if action=='outpost_invest' else f'携{profile(row["source"])["transfer"]}灵石返回总部' if action=='outpost_export' else LABELS[action]), options=options or {})
        try:
            if blocked_reason:
                raise ValueError(blocked_reason)
            if action in JOBS or action == 'outpost_export':
                eligible = []
                for person in result['workers']:
                    candidate = {**item['options'], 'person_id': person['id']}
                    try:
                        quote(deps, game, row, action, candidate)
                    except ValueError:
                        continue
                    eligible.append(person)
                item['people'] = eligible
                if eligible:
                    item['options'] = {**item['options'], 'person_id': eligible[0]['id']}
            item.update(quote(deps, game, row, action, item['options']), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        return item
    result['actions'] = [control('outpost_develop'), control('outpost_invest')]
    if not result['registered']:
        return result
    dev = row['development']
    result.update(income=dev['income'], expense=dev['expense'], balance=balance(game, base.wallet(row)))
    result['actions'].append(control('outpost_buy_materials', {'quote_id': local_quote(deps, game, row)[4]}))
    person = result['workers'][0]['id'] if result['workers'] else ''
    result['actions'].append(control('outpost_export', {'person_id': person}))
    active = [j for j in result['jobs'] if j['status'] == 'active']
    result['actions'].append(control('outpost_cancel_local', {'person_id': active[0]['person_id'] if active else ''}))
    visible = territory.snapshot(game, deps.outpost_maps(), row['destination'])
    for site in deps.outpost_maps().worlds[row['destination']]['locations']:
        loc = site['id']
        try:
            validate_claim(deps.outpost_maps(), row['destination'], visible, row['owner_id'], loc, occupies_slot=False)
        except ValueError:
            continue
        own = visible.get(loc, {}).get(row['owner_id'], {})
        rivals = [dict(id=key, name=anchors.organization(game, key).name) for key in visible.get(loc, {}) if key != row['owner_id']
                  and any(n.realm_index >= profile(row['source'])['minimum'] for n in deps.outpost_local_people(game, row, loc, key))]
        place = dict(id=loc, name=site['name'], value=round(own.get('value', 0), 2), outpost=bool(own.get('outpost')),
                     rivals=rivals, policies=[dict(id=p, name=v['name']) for p, v in POLICIES.items() if permits(p, own.get('value', 0))], actions=[])
        for action in JOBS:
            options = dict(person_id=person, location_id=loc)
            if action == 'outpost_spar':
                options['rival_id'] = rivals[0]['id'] if rivals else ''
            place['actions'].append(control(action, options))
        place['actions'].append(control('outpost_policy', dict(location_id=loc, policy=place['policies'][0]['id'] if place['policies'] else '')))
        place['actions'].append(control('outpost_retract', dict(location_id=loc)))
        result['locations'].append(place)
    return result
