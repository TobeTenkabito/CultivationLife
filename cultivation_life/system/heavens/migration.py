"""Finite sponsored civilian settlement by existing, willing local residents."""
from ...person_assignments import research_assignments, research_assignment
from .definitions import VISIT_DESTINATIONS
from .missions import contact_reason
from .state import active_task, get_echo, record, site_for

LABELS = {'migration_start': '资助迁居', 'migration_cancel': '撤销未抵达迁居'}
BUDGET = 4000


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    echo = get_echo(runtime, target)
    if not echo:
        raise ValueError('须先建立当地联系')
    reason = contact_reason(deps, game, target)
    if reason:
        raise ValueError(reason)
    row = echo.get('migration')
    if action == 'migration_cancel':
        if not row or row['status'] != 'active' or row['phase'] != 'outbound':
            raise ValueError('只能撤销尚未抵达的迁居')
        if deps.read_mission_facts(game, target, assignment='migration', check_route=False)['blocked_reason']:
            raise ValueError('须待本人恢复自由并回到出发地才能撤销')
        return dict(years=0, costs={}, refundable={}, message='本人仍在出发地；未耗路费和安置费退回原项目，不恢复此次接引名额。')
    if row:
        raise ValueError('每处联系仅提供一次民用接引名额')
    if not echo.get('visit', {}).get('studied') or not echo.get('correspondence_completed'):
        raise ValueError('须先校订旧录并亲自研读，确认接引地点')
    if active_task(runtime) or any(r['status'] == 'active' for _, r in research_assignments(game)):
        raise ValueError('请先结束当前亲自任务或已有同道行程')
    identity = options.get('person_id')
    npc = deps.resolve_person(game, identity) if identity else None
    if not npc or (npc.affinity or 0) < 20:
        raise ValueError('须选择当地已有交情的居民（交情至少 20）')
    if research_assignment(game, identity) or any(r.get('person_id') == identity for _, r in research_assignments(game)):
        raise ValueError('此人已有行程或已使用过迁居接引')
    reason = deps.read_mission_facts(game, target, assignment='migration', person_id=identity)['blocked_reason']
    if reason:
        raise ValueError(reason)
    if echo['project_stones'] < BUDGET:
        raise ValueError('合作项目实有资金不足 4000 灵石')
    return dict(years=0, costs={}, refundable={}, project_cost=BUDGET,
        message=f'{npc.name}接受本次民用迁居安排。项目预留 4000 灵石：通行 2 年共 2000，抵达后安置 1 年耗 2000；不从玩家背包收费。',
        warning='此为长期迁居，无自动返乡。原人物会留在目的地，出发地的交往与合作须按真实位置重新判断；每处名额及每人接引均仅一次。')


def finish(game, echo, status, *, year=None):
    row = echo['migration']
    refund = BUDGET-row['spent']-row['refunded']
    echo['project_stones'] += refund
    row['refunded'] += refund
    row['status'] = status
    record(game, {'completed': '居民已完成当地安置，解除行程占用；同一人物继续在目的界面生活。',
                  'cancelled': '居民尚未抵达，迁居已撤销，未耗接引款退回原项目。',
                  'failed': '迁居人物已陨落，原行程终止；未耗接引款退回原项目，不生成替代居民。'}[status], year=year)


def execute(deps, game, action, target, options):
    runtime = game.heavens_state['runtime']
    echo = get_echo(runtime, target)
    if action == 'migration_cancel':
        finish(game, echo, 'cancelled')
    else:
        echo['project_stones'] -= BUDGET
        echo['migration'] = dict(person_id=options['person_id'], destination=VISIT_DESTINATIONS[target],
            status='active', phase='outbound', progress=0, spent=0, refunded=0, elapsed=0,
            started_at=runtime['processed_years'], last_year=runtime['processed_years'])
        record(game, '原居民已接受民用接引，项目预留 4000 灵石，按世界年度通行与安置。')
    return {'message': '迁居安排已更新'}


def year_step(deps, game, echo, row, year):
    if row['status'] != 'active' or row['last_year'] >= year:
        return
    row['last_year'] = year
    facts = deps.read_mission_facts(game, echo['id'], assignment='migration')
    if not facts['alive']:
        finish(game, echo, 'failed', year=year)
        return
    if facts['blocked_reason']:
        return
    row['progress'] += 1
    row['elapsed'] += 1
    row['spent'] += 1000 if row['phase'] == 'outbound' else 2000
    if row['phase'] == 'settling':
        finish(game, echo, 'completed', year=year)
    elif row['progress'] == 2:
        deps.move_researcher(game, echo['id'], 'outbound', assignment='migration')
        row.update(phase='settling', progress=0)
        record(game, '原居民已实际抵达接引地点，开始一年的当地安置；可在当地见面。', year=year)


def project(deps, game, target, *, detail=True):
    echo = get_echo(game.heavens_state.get('runtime'), target)
    row = echo.get('migration') if echo else None
    result = dict(target_id=target, name=site_for(deps, game, target).name,
        destination_name=site_for(deps, game, VISIT_DESTINATIONS[target]).name,
        status=row['status'] if row else 'unavailable')
    if row:
        npc = deps.resolve_person(game, row['person_id'])
        result.update(row, person_name=npc.name if npc else '原迁居人物', remaining=BUDGET-row['spent']-row['refunded'])
        if detail:
            facts = deps.read_mission_facts(game, target, assignment='migration')
            result.update(world=facts['world'], location_id=facts['location_id'], alive=facts['alive'],
                          blocked_reason=facts['blocked_reason'] if row['status']=='active' else None)
    if not detail:
        return result
    result['candidates'] = deps.migration_candidates(game, target) if not row else []
    result['actions'] = []
    for action, label in LABELS.items():
        options = {'person_id': result['candidates'][0]['id']} if action == 'migration_start' and result['candidates'] else {}
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
