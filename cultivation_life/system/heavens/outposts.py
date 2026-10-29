"""Authorized frontier commands through the common heavens transaction."""
from ...system.faction_geography import faction_site
from ..economy import depot
from ..economy.ledger import account, balance, transfer_value
from ..economy.local_market import require_access
from .state import active_task, initialize
from .outpost_definitions import (ACTIONS, LABELS, ENDPOINTS, SITE_NAMES, WORLD_NAMES, OPTIONS,
    CROSSING_YEARS, BUILD_YEARS, BUILD_COST, WORKING_CASH, ANNUAL_COST, MAX_UNITS, TIMED_ACTIONS, target, is_target)
from . import outpost_runtime as runtime


def handles(state, action, target_id):
    task = active_task(state) if state else None
    return action in ACTIONS or bool(action in {'resume', 'cancel'} and task
        and is_target(task.get('target_id')) and task['id'] == target_id)


def entity_for(deps, game, target_id):
    if not is_target(target_id):
        raise ValueError('未知开拓驻地')
    entity = deps.outpost_owner(game, target_id.removeprefix('outpost:'))
    if not entity or entity.kind not in {'sect', 'family'}:
        raise ValueError('开拓势力不存在')
    return entity


def actor_reason(game):
    try:
        require_access(game)
    except ValueError:
        return '须先处理事件、劫关、受控或专属活动，并回到普通界面'
    if game.player.nascent_state.get('crisis'):
        return '须先处理当前元婴危机'
    return None


def require_actor(game):
    if reason := actor_reason(game):
        raise ValueError(reason)


def require_place(game, world, location):
    if (game.player.world, game.player.location_id) != (world, location):
        raise ValueError('须亲自到' + WORLD_NAMES[world] + '·' + location + '办理')


def require_control(deps, game, entity, row):
    if not deps.outpost_control(game, entity, row):
        raise ValueError('没有当前势力的开拓授权，原总部控制权或成员身份已失效')


def dispatch_plan(deps, game, row, entity, identity, courier):
    require_place(game, row['source'], row['home'])
    if faction_site(entity, persist=False)['id'] != row['home'] or entity.world != row['source']:
        raise ValueError('总部已迁址；须先结清原址开拓行程')
    recovery = row['status'] == 'withdrawing'
    if row['status'] == 'closed' or recovery and not courier:
        raise ValueError('驻地正在撤回或已经关闭')
    if sum(u['phase'] not in {'home', 'lost'} for u in row['units']) >= MAX_UNITS:
        raise ValueError('同一驻地最多三位原门人在途或驻守')
    if identity not in {n['id'] for n in deps.outpost_candidates(game, entity)}:
        raise ValueError('请选择位于原总部、自由且未被其他职责占用的门人')
    npc = deps.resolve_person(game, identity)
    road = deps.outpost_road(game, row['source'], row['home'], ENDPOINTS[row['source']], npc.realm_index)
    if not road or not deps.outpost_lane(game, row):
        raise ValueError('开拓道路或已登记跨界路线不可用')
    store = depot.find(game, entity)
    cargo = {} if courier else runtime.materials(row['source'])
    outstanding = sum(row['stock'].values()) + sum(sum(u['stock'].values()) for u in row['units'])
    if outstanding + sum(cargo.values()) > 10000:
        raise ValueError('当地及在途仓储容量不足，请先回收原物资')
    if not store or any(store['stock'].get(key, 0) < quantity for key, quantity in cargo.items()):
        raise ValueError('原总部府库须备齐二阶构材6、导灵矿2、储能矿2；请在府库采购后再派驻')
    working = 0 if recovery else WORKING_CASH + (0 if courier or row['progress'] else BUILD_COST)
    total = working + 2 * (road['years'] + CROSSING_YEARS) * ANNUAL_COST
    if balance(game, depot.treasury(game, entity)) < total:
        raise ValueError(f'原势力府库不足，本次须预留 {total} 灵石（含往返路费）')
    return dict(road=road, cargo=cargo, total=total)


def task_reason(deps, game, task):
    if reason := actor_reason(game):
        return reason
    row = runtime.get(game, task['target_id'])
    if not row:
        return '原开拓许可不存在'
    if task['action'] == 'outpost_wait':
        if game.player.world not in {row['source'], row['destination']}:
            return '须在开拓两端的普通界面推进'
        return None
    try:
        deps.outpost_player_plan(game, row, task['action'] == 'outpost_return')
    except ValueError as exc:
        return str(exc)
    return None


def quote(deps, game, action, target_id, options):
    require_actor(game)
    state = game.heavens_state.get('runtime')
    task = active_task(state) if state else None
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target_id or not is_target(task['target_id']):
            raise ValueError('开拓亲自行程已经结束')
        if action == 'resume' and (reason := task_reason(deps, game, task)):
            raise ValueError(reason)
        return dict(years=task['duration'] - task['progress'] if action == 'resume' else 0,
                    costs={}, refundable={}, message='取消返程表示暂停；预留返程资格继续保留。')
    if task:
        raise ValueError('请先完成或取消当前亲自任务')
    entity = entity_for(deps, game, target_id)
    row = runtime.get(game, target_id)
    years, costs, message = 0, {}, ''
    if action == 'outpost_authorize':
        if row:
            raise ValueError('本势力已有开拓许可，原记录不会刷新或覆盖')
        require_control(deps, game, entity, None)
        if entity.world not in ENDPOINTS:
            raise ValueError('首期开拓仅开放人界与魔界')
        require_place(game, entity.world, faction_site(entity, persist=False)['id'])
        if not game.heavens_state.get('generation_enabled') or not deps.get_definitions().generation_available:
            raise ValueError('请先在设置中允许发现新的诸天联系')
        if not 3 <= game.player.realm_index <= 5 or game.player.sealed_cultivation or game.player.cultivation_suppression:
            raise ValueError('首期开拓须具备未封限的结丹至炼虚修为')
        message = '原总部保留原址。批准对界固定落点的民用建设、派驻与补给；此许可不授予宣战或军队征服权。'
    else:
        if not row:
            raise ValueError('须先在原总部批准跨界开拓')
        if action not in {'outpost_return', 'outpost_wait'}:
            require_control(deps, game, entity, row)
        if action in {'outpost_dispatch', 'outpost_supply'}:
            plan = dispatch_plan(deps, game, row, entity, options['person_id'], action == 'outpost_supply')
            costs = {'organization_stones': plan['total']}
            message = f'原府库实付托管 {plan["total"]} 灵石；集结 {plan["road"]["years"]} 年、跨界 {CROSSING_YEARS} 年。' + ('使者交付后实际返乡。' if action == 'outpost_supply' else '另装运原府库二阶构材6、导灵矿2、储能矿2；抵达后施工10年。')
        elif action in {'outpost_depart', 'outpost_return'}:
            deps.outpost_player_plan(game, row, action == 'outpost_return')
            years = CROSSING_YEARS
            costs = {'stones': CROSSING_YEARS * ANNUAL_COST * (2 if action == 'outpost_depart' else 0)}
            if action == 'outpost_depart' and balance(game, 'player') < costs['stones']:
                raise ValueError('须从个人行囊预留1600灵石，含去程和返程各800')
            message = '本人单独循已授权路线通行，原组织职位不因临时通行清除；返程800灵石独立保留，不搬运门人或仓库。'
        elif action == 'outpost_wait':
            years = 1
            if game.player.world not in {row['source'], row['destination']}:
                raise ValueError('须在开拓两端的普通界面推进')
            message = '只推进实际一年。异界任务仍按所属地区冻结与入界补算，不发普通修炼收益。'
        elif action == 'outpost_recall':
            unit = next((u for u in row['units'] if u['person_id'] == options['person_id']), None)
            if not unit or unit['phase'] not in {'gathering', 'outbound', 'stationed'}:
                raise ValueError('所选原门人没有可召回的派驻行程')
            if (game.player.world, game.player.location_id) not in {(row['source'], row['home']), (row['destination'], ENDPOINTS[row['destination']])}:
                raise ValueError('须在原总部或异界驻地办理召回')
            if not runtime.free(game, deps.resolve_person(game, unit['person_id'])):
                raise ValueError('原门人受控或已陨落，须先处理实际状态')
            message = '撤销后续驻守，保留已经发生的时间与费用，原门人沿实际路线返乡。'
        else:
            require_place(game, row['destination'], ENDPOINTS[row['destination']])
            residents = [u for u in row['units'] if not u['courier'] and runtime.located(deps, game, row, u)]
            if action == 'outpost_appoint':
                if options['person_id'] not in {u['person_id'] for u in residents}:
                    raise ValueError('负责人须是实际在场且自由的原派驻门人')
            elif action == 'outpost_suspend':
                if row['status'] != 'active':
                    raise ValueError('只有已运营驻地可以暂停')
            elif action == 'outpost_activate':
                if row['status'] != 'suspended' or row['governor_id'] not in {u['person_id'] for u in residents} or balance(game, runtime.wallet(row)) < ANNUAL_COST:
                    raise ValueError('恢复须已建成、有自由驻守门人且当地经费至少100灵石')
            elif action == 'outpost_withdraw':
                if row['status'] in {'closed', 'withdrawing'}:
                    raise ValueError('驻地已经关闭或正在撤回')
                message = '停止施工经营。原人员循路撤回，最后一位驻守者携回当地剩余钱货；无人可搬运时须从总部另派回收使者。'
    return dict(years=years, costs=costs, refundable={}, message=message,
                warning='人物可能寿尽、被俘或因路线失效而滞留；不会生成替身或免费返乡。')


def execute(deps, game, action, target_id, options, proposal, *, run_task, cancel_task, task_result):
    if action in {'resume', 'cancel'}:
        task = active_task(game.heavens_state['runtime'])
        if action == 'cancel':
            cancel(deps, game, task)
        else:
            run_task(deps, game, task)
        return task_result(task)
    initialize(game, enabled=game.heavens_state['generation_enabled'])
    state = game.heavens_state['runtime']
    entity = entity_for(deps, game, target_id)
    if action == 'outpost_authorize':
        source = entity.world
        row = dict(id=target_id, owner_id=entity.id, owner_kind=depot.owner_kind(game, entity), issuer_id=game.id,
            source=source, destination='demon' if source == 'human' else 'human', home=faction_site(entity, persist=False)['id'],
            status='authorized', progress=0, stock={}, units=[], sequence=0, governor_id=None,
            last_year=game.player.age, visit=None, history=[])
        state.setdefault('outposts', {})[target_id] = row
        game.heavens_state['definition_versions']['outposts'] = 1
        account(game, runtime.wallet(row))
        runtime.note(game, row, '总部正式批准跨界开拓，原势力与山门保持唯一。')
        return {'message': '跨界开拓许可已登记'}
    row = runtime.get(game, target_id)
    if action in TIMED_ACTIONS:
        if action == 'outpost_depart':
            escrow = deps.reserve_resources(game, 1600, None, 0)
            escrow['total'] = 800
            row['visit'] = dict(status='preparing', return_fare=800)
        elif action == 'outpost_return':
            escrow = dict(total=800, spent=0, refunded=0, material=None, mp_paid=0)
            row['visit']['return_fare'] -= 800
        else:
            escrow = dict(total=0, spent=0, refunded=0, material=None, mp_paid=0)
        task = dict(id=f'heavens-task-{state["next_task_seq"]}', action=action, target_id=target_id,
            status='reserved', cycle=0, progress=0, duration=proposal['years'], escrow=escrow, person_id=None)
        state['next_task_seq'] += 1
        state['tasks'] = state['tasks'][-3:] + [task]
        run_task(deps, game, task)
        return task_result(task)
    if action in {'outpost_dispatch', 'outpost_supply'}:
        courier = action == 'outpost_supply'
        plan = dispatch_plan(deps, game, row, entity, options['person_id'], courier)
        # Finished logs are bounded; original people and monetary receipts
        # remain in their authoritative containers.
        for unit in row['units']:
            if unit['phase'] in {'home', 'lost'} and not balance(game, unit['wallet']):
                game.economy_v2['accounts'].pop(unit['wallet'], None)
        row['units'] = [u for u in row['units'] if u['phase'] not in {'home', 'lost'}]
        if row['governor_id'] not in {u['person_id'] for u in row['units']}:
            row['governor_id'] = None
        row['sequence'] += 1
        purse = f'heavens-{row["id"]}:cargo:{row["sequence"]}'
        account(game, purse)
        transfer_value(game, depot.treasury(game, entity), purse, plan['total'], '原总部批准开拓，实款封存随行')
        store = depot.find(game, entity)
        for key, quantity in plan['cargo'].items():
            store['stock'][key] -= quantity
        depot.record(store, game, '开拓装运原实物，原址库存已扣除')
        deps.outpost_prepare_npc(game, options['person_id'], entity, row['home'])
        unit = dict(person_id=options['person_id'], phase='gathering', progress=0, duration=plan['road']['years'],
            road=plan['road']['route'], road_years=plan['road']['years'], wallet=purse, stock=dict(plan['cargo']),
            courier=courier, delivered=False, last_year=game.player.age)
        if not unit['road_years']:
            runtime.phase(unit, 'outbound', CROSSING_YEARS)
        row['units'].append(unit)
        runtime.note(game, row, '原门人接受开拓行程，随身原款和实物已从总部移交。')
    elif action == 'outpost_recall':
        runtime.recall(row, next(u for u in row['units'] if u['person_id'] == options['person_id']))
    elif action == 'outpost_appoint':
        row['governor_id'] = options['person_id']
    elif action == 'outpost_suspend':
        row['status'] = 'suspended'
    elif action == 'outpost_activate':
        row['status'] = 'active'
    elif action == 'outpost_withdraw':
        row['status'] = 'withdrawing'
    return {'message': LABELS[action] + '已登记'}


def complete(deps, game, task, rng):
    row = runtime.get(game, task['target_id'])
    if task['action'] != 'outpost_wait':
        deps.outpost_move_player(game, row, task['action'] == 'outpost_return', rng)
        row['visit']['status'] = 'returned' if task['action'] == 'outpost_return' else 'visiting'
        runtime.note(game, row, '你已实际完成开拓路线返程。' if task['action'] == 'outpost_return' else '你已实际抵达异界分驻地。')
    task['status'] = 'completed'


def cancel(deps, game, task, *, failed=False, reason='主动取消'):
    row = runtime.get(game, task['target_id'])
    if task['action'] == 'outpost_return' and not failed:
        task['status'] = 'paused'
        return
    deps.refund_resources(game, task['escrow'])
    if task['action'] == 'outpost_depart' or failed and row['visit']:
        deps.grant_stones(game, row['visit']['return_fare'])
        row['visit'].update(return_fare=0, status='failed' if failed else 'cancelled')
    task['status'] = 'failed' if failed else 'cancelled'


def project(deps, game):
    rows = game.heavens_state.get('runtime', {}).get('outposts', {})
    entities = deps.outpost_owners(game)
    result = []
    for entity in entities:
        key = target(entity.id)
        row = rows.get(key)
        source = row['source'] if row else entity.world
        if source not in ENDPOINTS:
            continue
        destination = row['destination'] if row else 'demon' if source == 'human' else 'human'
        item = dict(id=key, name=entity.name + '·异界分驻地', source=source, destination=destination,
            source_name=WORLD_NAMES[source], destination_name=WORLD_NAMES[destination],
            gateway=SITE_NAMES[source], location_name=SITE_NAMES[destination],
            status=row['status'] if row else 'unregistered', actions=[], candidates=[], residents=[], units=[], history=[])
        local = game.player.world == destination and game.player.location_id == ENDPOINTS[destination]
        headquarters = game.player.world == source and game.player.location_id == (row['home'] if row else faction_site(entity, persist=False)['id'])
        if row:
            item.update(progress=row['progress'], duration=BUILD_YEARS,
                return_fare=row['visit']['return_fare'] if row['visit'] else 0,
                visit_status=row['visit']['status'] if row['visit'] else None,
                history=list(row['history']), governor_id=row['governor_id'])
            if local:
                item.update(stock=dict(row['stock']), balance=balance(game, runtime.wallet(row)))
                item['stock_rows'] = [dict(name=deps.outpost_item_name(k), quantity=n)
                                      for k, n in row['stock'].items() if n]
            else:
                item['notice'] = '异界详情以最后收到的记录为准；实际抵达当地后核实库存、负责人和建设进度。'
            for unit in row['units']:
                npc = deps.resolve_person(game, unit['person_id'])
                name = npc.name if npc else '原门人'
                notice = '受控暂停' if npc and npc.alive and not runtime.free(game, npc) else ''
                if unit['phase'] == 'stationed' and not unit['delivered']:
                    notice = '已抵达，原钱货待当地接收'
                if unit['phase'] in {'outbound', 'returning'} and not deps.outpost_lane(game, row, returning=unit['phase'] == 'returning', person_id=unit['person_id']):
                    notice = '通道关闭或实际修为超出承载，原地等候'
                elif unit['phase'] == 'homeward' and not unit['duration']:
                    notice = '已抵原址，等待仓库卸货与账目结清'
                if headquarters or local:
                    item['units'].append(dict(id=unit['person_id'], name=name, phase=unit['phase'],
                        progress=unit['progress'], duration=unit['duration'], alive=bool(npc and npc.alive),
                        free=runtime.free(game, npc), courier=unit['courier'], notice=notice))
                if local and not unit['courier'] and runtime.located(deps, game, row, unit):
                    item['residents'].append(dict(id=npc.id, name=npc.name))
        if headquarters:
            item['candidates'] = deps.outpost_candidates(game, entity)
        for action, label in LABELS.items():
            options = {}
            if OPTIONS[action]:
                choices = item['candidates'] if action in {'outpost_dispatch', 'outpost_supply'} else item['residents'] if action == 'outpost_appoint' else [u for u in item['units'] if u['phase'] in {'gathering', 'outbound', 'stationed'} and u['free']]
                options = {'person_id': choices[0]['id'] if choices else ''}
            control = dict(action=action, target_id=key, label=label, options=options)
            try:
                control.update(quote(deps, game, action, key, options), enabled=True)
            except ValueError as exc:
                control.update(enabled=False, reason=str(exc))
            item['actions'].append(control)
        result.append(item)
    return result
