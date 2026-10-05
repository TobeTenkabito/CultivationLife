"""A finite civilian consignment carried by the existing authoritative person."""
import copy

from ...person_assignments import research_assignments
from .definitions import VISIT_DESTINATIONS
from .state import active_task, get_echo, record, site_for

LABELS = {'freight_start': '委托运送阵材', 'freight_cancel': '撤销未抵达货运', 'freight_collect': '领取托存物资与款项'}
BUDGET, REWARD = 7000, 3000


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    echo = get_echo(runtime, target)
    if not echo:
        raise ValueError('须先登记当地联系')
    reason = deps.read_actor_facts(game, target)['blocked_reason']
    if reason:
        raise ValueError(reason)
    freight = echo.get('freight')
    if action == 'freight_collect':
        if not freight or not (freight['cargo_owner'] == 'depot' or freight['delivered'] and not freight['claimed']):
            raise ValueError('当前没有可在出发地领取的物资或款项')
        return dict(years=0, costs={}, refundable={}, message='在原联系地点取回撤销后托存的原阵材，或领取已交货的 3000 灵石。')
    if action == 'freight_cancel':
        if not freight or freight['status'] != 'active' or freight['phase'] != 'outbound':
            raise ValueError('只可撤销尚未抵达的货运')
        if deps.read_mission_facts(game, target, assignment='freight', check_route=False)['blocked_reason']:
            raise ValueError('承运人须恢复自由并回到原地点，才能卸下托运物资')
        return dict(years=0, costs={}, refundable={}, message='撤销后原物资存于出发地，须单独领取；未耗经费退回项目。')
    if freight:
        raise ValueError('每处联系仅接收一次阵材委托')
    prior = echo.get('mission', {})
    if prior.get('status') != 'completed' or not prior.get('studied'):
        raise ValueError('须由已完成研读并返乡的同道承运')
    if active_task(runtime) or any(row['status'] == 'active' for _, row in research_assignments(game)):
        raise ValueError('请先结束亲自任务或已有同道行程')
    reason = deps.read_mission_facts(game, target, assignment='freight')['blocked_reason']
    if reason:
        raise ValueError(reason)
    if options.get('material_id') not in {row['id'] for row in deps.quote_materials(game, target)}:
        raise ValueError('须提供一件本界闲置九阶普通阵材')
    if echo['project_stones'] < BUDGET:
        raise ValueError('合作项目实有资金不足 7000 灵石')
    return dict(years=0, costs={'material_id': options['material_id']}, refundable={}, project_cost=BUDGET,
        message='将所选原阵材捐赠给异界研究项目，交货后不再属于玩家；3000 灵石为定额供材补贴，并非市价收购。项目预留 4000 往返路费及 3000 供材报酬。去程、返程各 2 年，到达即交货，报酬须在出发地领取。每处仅一次。',
        warning='承运途中陨落，未交付物资随身遗失，不补发；已交货物不可撤回。')


def finish(game, echo, status, *, year=None):
    row = echo['freight']
    remaining = BUDGET-row['spent']-(REWARD if row['delivered'] else 0)-row['refunded']
    echo['project_stones'] += remaining
    row['refunded'] += remaining
    row['status'] = status
    record(game, {'completed': '承运同道已实际返乡，运材委托结束。',
                  'cancelled': '未抵达货运已撤销，原阵材托存在出发地，未耗款退回项目。',
                  'failed': '承运人已陨落，货运终止；未交货物遗失，已交货报酬仍可领取，未耗款退回项目。'}[status], year=year)


def execute(deps, game, action, target, options):
    runtime = game.heavens_state['runtime']
    echo = get_echo(runtime, target)
    if action == 'freight_start':
        material = deps.reserve_resources(game, 0, options['material_id'], 0, target_id=target)['material']
        echo['project_stones'] -= BUDGET
        echo['freight'] = dict(destination=VISIT_DESTINATIONS[target], status='active', phase='outbound',
            progress=0, elapsed=0, spent=0, refunded=0, started_at=runtime['processed_years'],
            last_year=runtime['processed_years'], material=material, cargo_owner='carrier', delivered=False, claimed=False)
        record(game, '原阵材已移交承运同道，项目预留 7000 灵石；普通世界年度开始推进行程。')
    elif action == 'freight_cancel':
        echo['freight']['cargo_owner'] = 'depot'
        finish(game, echo, 'cancelled')
    else:
        row = echo['freight']
        if row['cargo_owner'] == 'depot':
            game.player.formation_materials.append(copy.deepcopy(row['material']))
            row['cargo_owner'] = 'player'
        if row['delivered'] and not row['claimed']:
            deps.grant_stones(game, REWARD)
            row['claimed'] = True
        record(game, '已在出发地领取运材委托的托存物资或已交货款项。')
    return {'message': '运材委托已更新'}


def year_step(deps, game, echo, row, year):
    if row['status'] != 'active' or row['last_year'] >= year:
        return
    row['last_year'] = year
    facts = deps.read_mission_facts(game, echo['id'], assignment='freight')
    if not facts['alive']:
        if not row['delivered']:
            row['cargo_owner'] = 'lost'
        finish(game, echo, 'failed', year=year)
        return
    if facts['blocked_reason']:
        return
    row['progress'] += 1
    row['elapsed'] += 1
    row['spent'] += 1000
    if row['progress'] < 2:
        return
    phase = row['phase']
    deps.move_researcher(game, echo['id'], phase, assignment='freight')
    if phase == 'outbound':
        row.update(phase='returning', progress=0, delivered=True, cargo_owner='destination')
        record(game, '承运人已抵达约定地点；同一阵材交入当地研究库存，3000 灵石报酬可在出发地领取。', year=year)
    else:
        finish(game, echo, 'completed', year=year)


def project(deps, game, target):
    echo = get_echo(game.heavens_state.get('runtime'), target)
    row = echo.get('freight') if echo else None
    result = dict(target_id=target, name=site_for(deps, game, target).visitor_name,
        destination_name=site_for(deps, game, VISIT_DESTINATIONS[target]).name,
        status=row['status'] if row else 'unavailable', actions=[], materials=deps.quote_materials(game, target))
    if row:
        result.update(copy.deepcopy(row), remaining=BUDGET-row['spent']-row['refunded']-(REWARD if row['delivered'] else 0),
            reward_available=REWARD if row['delivered'] and not row['claimed'] else 0,
            blocked_reason=deps.read_mission_facts(game, target, assignment='freight')['blocked_reason'] if row['status']=='active' else None)
    for action, label in LABELS.items():
        options = {'material_id': result['materials'][0]['id']} if action == 'freight_start' and result['materials'] else {}
        item = dict(action=action, target_id=target, label=label, options=options)
        try:
            item.update(quote(deps, game, action, target, options), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    if row and row['status'] == 'active':
        from . import missions
        item = dict(action='mission_wait', target_id=target, label='等候一年', options={})
        try:
            item.update(missions.quote(deps, game, 'mission_wait', target, {}), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    return result
