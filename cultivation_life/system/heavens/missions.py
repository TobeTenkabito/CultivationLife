"""One finite, funded round trip by an existing authoritative researcher."""
from ...person_assignments import research_assignments
from .definitions import MISSION_ACTIONS, VISIT_DESTINATIONS
from .state import get_echo, active_task, record, site_for

LABELS = {'mission_start': '约请同道回访', 'mission_recall': '结束研读并返乡', 'mission_wait': '等候一年'}
DURATIONS = {'outbound': 2, 'studying': 4, 'returning': 2}
RATES = {'outbound': 1000, 'studying': 500, 'returning': 1000}
BUDGET = 6000


def handles(runtime, action, target):
    task = active_task(runtime) if runtime else None
    return action in MISSION_ACTIONS or (action in {'resume', 'cancel'} and task
        and task['id'] == target and task['action'] == 'mission_wait')


def wait_reason(deps, game):
    return deps.read_actor_facts(game)['blocked_reason']


def contact_reason(deps, game, target):
    local = target if game.player.world == site_for(deps, game, target).world else VISIT_DESTINATIONS[target]
    return deps.read_actor_facts(game, local)['blocked_reason']


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('请先启用诸天联系')
    task = active_task(runtime)
    if action in {'resume', 'cancel'}:
        if action == 'resume' and wait_reason(deps, game):
            raise ValueError(wait_reason(deps, game))
        return dict(years=1-task['progress'] if action == 'resume' else 0, costs={}, refundable={})
    echo = get_echo(runtime, target)
    if not echo:
        raise ValueError('须先登记该地联系')
    mission = echo.get('mission')
    if action == 'mission_wait':
        if not mission or mission['status'] != 'active':
            raise ValueError('暂无正在进行的同道行程')
        reason = wait_reason(deps, game)
        if reason or task:
            raise ValueError(reason or '请先结束当前亲自任务')
        return dict(years=1, costs={}, refundable={})
    if action == 'mission_recall':
        if not mission or mission['status'] != 'active' or mission['phase'] == 'returning':
            raise ValueError('此行已结束或正在返程')
        if contact_reason(deps, game, target):
            raise ValueError(contact_reason(deps, game, target))
        if deps.read_mission_facts(game, target, check_route=False)['blocked_reason']:
            raise ValueError('本人无法接洽，须待其恢复自由并回到约定位置')
        return dict(years=0, costs={}, refundable={}, message='去程未抵达则撤销余下安排；已抵达则保留返程路费，按实际路线返回。')
    if mission:
        raise ValueError('每位合作人物仅履行一次回访约定')
    if not echo.get('visit', {}).get('studied') or not echo.get('correspondence_completed'):
        raise ValueError('须先亲自完成跨界研读，确认接待地点')
    if task or any(m['status'] == 'active' for _, m in research_assignments(game)):
        raise ValueError('请先结束当前亲自任务或已有同道行程')
    reason = contact_reason(deps, game, target) or deps.read_mission_facts(game, target)['blocked_reason']
    if reason:
        raise ValueError(reason)
    if echo['project_stones'] < BUDGET:
        raise ValueError('合作项目实有资金不足 6000 灵石')
    return dict(years=0, costs={}, refundable={}, project_cost=BUDGET,
                message='从合作项目预留 6000 灵石。本人将自主去程 2 年、研读 4 年、返程 2 年；未耗款退回项目。')


def finish(game, echo, status, message, *, year=None):
    mission = echo['mission']
    remaining = BUDGET - mission['spent'] - mission['refunded']
    echo['project_stones'] += remaining
    mission['refunded'] += remaining
    mission['status'] = status
    record(game, message, year=year)


def execute(deps, game, action, target, options, proposal, *, run_task, cancel_task, task_result):
    runtime = game.heavens_state['runtime']
    task = active_task(runtime)
    if action == 'cancel':
        cancel_task(deps, game, task)
        return task_result(task)
    if action == 'resume':
        run_task(deps, game, task)
        return task_result(task)
    echo = get_echo(runtime, target)
    if action == 'mission_start':
        echo['project_stones'] -= BUDGET
        echo['mission'] = dict(destination=VISIT_DESTINATIONS[target], status='active', phase='outbound',
            progress=0, spent=0, refunded=0, studied=False, elapsed=0,
            last_year=runtime['processed_years'], started_at=runtime['processed_years'])
        record(game, f'为{site_for(deps, game, target).visitor_name}预留回访经费 6000 灵石，行程由世界年度推进。')
        return {'message': '回访约定已登记，人物与通道已占用'}
    if action == 'mission_recall':
        if echo['mission']['phase'] == 'outbound':
            finish(game, echo, 'cancelled', '同道尚未抵达，余下行程已撤销，未耗款退回项目。')
        else:
            echo['mission'].update(phase='returning', progress=0)
            record(game, '同道结束本次研读，待实际路线可用后循约返乡。')
        return {'message': '返乡安排已登记'}
    task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action='mission_wait', status='reserved', target_id=target,
        cycle=echo['cycle'], progress=0, duration=1, person_id=None,
        escrow=dict(total=0, spent=0, refunded=0, material=None, mp_paid=0))
    runtime['next_task_seq'] += 1
    runtime['tasks'] = runtime['tasks'][-3:] + [task]
    run_task(deps, game, task)
    return task_result(task)


def year_step(deps, game):
    """Called only after the ordinary authoritative NPC year, never in isolation."""
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        return
    year = runtime['processed_years'] + 1
    for echo, mission in research_assignments(game):
        if mission['status'] != 'active' or mission['last_year'] >= year:
            continue
        mission['last_year'] = year
        facts = deps.read_mission_facts(game, echo['id'])
        if not facts['alive']:
            finish(game, echo, 'failed', '回访人物已经陨落或失去权威引用，原行程终止，未耗款退回项目。', year=year)
            continue
        if facts['blocked_reason']:
            continue
        phase = mission['phase']
        mission['progress'] += 1
        mission['elapsed'] += 1
        mission['spent'] += RATES[phase]
        if mission['progress'] < DURATIONS[phase]:
            continue
        if phase == 'studying':
            mission.update(studied=True, phase='returning', progress=0)
            record(game, '回访人物已完成现场研读，携本人对照记录准备返乡。', year=year)
        elif phase == 'outbound':
            deps.move_researcher(game, echo['id'], 'outbound')
            mission.update(phase='studying', progress=0)
            record(game, '回访人物已经实际抵达，可在约定地点见面。', year=year)
        else:
            deps.move_researcher(game, echo['id'], 'returning')
            finish(game, echo, 'completed', '同道已循约返乡；现场认识与已耗经费永久保留。', year=year)


def project(deps, game, target):
    echo = get_echo(game.heavens_state.get('runtime'), target)
    mission = echo.get('mission') if echo else None
    result = dict(target_id=target, name=site_for(deps, game, target).visitor_name,
        destination_name=site_for(deps, game, VISIT_DESTINATIONS[target]).name,
        status=mission['status'] if mission else 'unavailable', actions=[])
    if mission:
        facts = deps.read_mission_facts(game, target)
        result.update(phase=mission['phase'], progress=mission['progress'], duration=DURATIONS[mission['phase']],
            spent=mission['spent'], remaining=BUDGET-mission['spent']-mission['refunded'], refunded=mission['refunded'],
            studied=mission['studied'], blocked_reason=facts['blocked_reason'] if mission['status'] == 'active' else None,
            person_id=echo['visitor_id'], world=facts['world'], location_id=facts['location_id'])
    for action in MISSION_ACTIONS:
        row = dict(action=action, target_id=target, label=LABELS[action], options={})
        if action == 'mission_recall' and mission and mission['phase'] == 'outbound':
            row['label'] = '撤销未抵达行程'
        try:
            row.update(quote(deps, game, action, target, {}), enabled=True)
        except ValueError as exc:
            row.update(enabled=False, reason=str(exc))
        result['actions'].append(row)
    result['actions'].sort(key=lambda r: ('mission_start', 'mission_wait', 'mission_recall').index(r['action']))
    return result
