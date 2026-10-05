"""Finite personal study permits, real crossings and separately held return fares."""
from .definitions import VISIT_ACTIONS, VISIT_DESTINATIONS
from .state import active_task, get_echo, site_for, record

LABELS = {'visit_depart': '启程访学', 'visit_study': '实地研读', 'visit_return': '循约返程'}
YEARS = {'visit_depart': 2, 'visit_study': 4, 'visit_return': 2}
FARE = 2000


def handles(runtime, action, target):
    task = active_task(runtime) if runtime else None
    return action in VISIT_ACTIONS or (action in {'resume', 'cancel'} and task
        and target == task['id'] and task['action'] in VISIT_ACTIONS)


def task_reason(deps, game, task):
    return deps.read_visit_facts(game, task['target_id'], task['action'])['blocked_reason']


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('请先启用诸天联系')
    task = active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target or task['action'] not in VISIT_ACTIONS:
            raise ValueError('访学任务不存在')
        echo = get_echo(runtime, task['target_id'])
        if action == 'cancel':
            remaining = task['escrow']['total'] - task['escrow']['spent'] - task['escrow']['refunded']
            return dict(years=0, costs={}, refundable={'stones':
                remaining + echo['visit']['return_fare'] if task['action'] == 'visit_depart'
                else 0 if task['action'] == 'visit_return' else remaining},
                message='取消返程仅暂停行程，未耗路费仍保留供续办。' if task['action'] == 'visit_return'
                        else '取消不会移动角色；已经取得的访学记录保留。')
        reason = task_reason(deps, game, task)
        if reason:
            raise ValueError(reason)
        return dict(years=task['duration']-task['progress'], costs={}, refundable={})
    if target not in VISIT_DESTINATIONS:
        raise ValueError('没有此个人访学路线')
    echo = get_echo(runtime, target)
    if not echo or not echo.get('correspondence_completed'):
        raise ValueError('先完成合法抄录的协作校订，再申请个人访学')
    if task:
        raise ValueError('请先继续或取消当前诸天任务')
    visit = echo.get('visit')
    if action == 'visit_depart':
        if visit:
            raise ValueError('每份校订旧录仅能申请一次个人访学')
        if not deps.person_available(game, echo['visitor_id']):
            raise ValueError('须由在场且未被占用的合作人物核验申请')
        if any(row.get('visit', {}).get('status') == 'visiting' for row in
               ([runtime['sea_echo']] if runtime['sea_echo'] else []) + list(runtime.get('contacts', {}).values())):
            raise ValueError('请先结束已有的跨界访学')
    elif not visit or visit['status'] != 'visiting':
        raise ValueError('须先抵达约定访学地点')
    elif action == 'visit_study' and visit['studied']:
        raise ValueError('已取得实地研读记录，无需重复研读')
    facts = deps.read_visit_facts(game, target, action)
    if facts['blocked_reason']:
        raise ValueError(facts['blocked_reason'])
    cost = 2*FARE if action == 'visit_depart' else 0
    if facts['stones'] < cost:
        raise ValueError('灵石不足，须同时预留去程与返程路费')
    return dict(years=YEARS[action], costs={'stones': cost, 'mp': 0},
                refundable={'unspent_stones': True}, return_fare=FARE if action == 'visit_depart' else 0)


def execute(deps, game, action, target, options, proposal, *, run_task, task_result):
    runtime = game.heavens_state['runtime']
    task = active_task(runtime)
    if action == 'cancel':
        if task['action'] == 'visit_return':
            # A return ticket is resumable, never converted to cash while abroad.
            task['status'] = 'paused'
            record(game, '返程暂缓，未耗路费继续托管；回到约定地点即可续办。')
        else:
            cancel(deps, game, task)
        return task_result(task)
    if action != 'resume':
        echo = get_echo(runtime, target)
        if action == 'visit_depart':
            escrow = deps.reserve_resources(game, 2*FARE, None, 0)
            escrow['total'] = FARE
            echo['visit'] = dict(destination=VISIT_DESTINATIONS[target], status='preparing',
                return_fare=FARE, studied=False, started_at=runtime['processed_years'], arrived_at=None, returned_at=None)
        else:
            escrow = dict(total=FARE if action == 'visit_return' else 0, spent=0, refunded=0, material=None, mp_paid=0)
            if action == 'visit_return':
                echo['visit']['return_fare'] -= FARE
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, status='reserved', target_id=target,
            cycle=echo['cycle'], progress=0, duration=YEARS[action], escrow=escrow, person_id=None)
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:] + [task]
    run_task(deps, game, task)
    return task_result(task)


def cancel(deps, game, task, *, failed=False, reason='主动取消'):
    visit = get_echo(game.heavens_state['runtime'], task['target_id'])['visit']
    deps.refund_resources(game, task['escrow'])
    if failed or task['action'] == 'visit_depart':
        deps.grant_stones(game, visit['return_fare'])
        visit.update(return_fare=0, status='failed' if failed else 'cancelled')
    task['status'] = 'failed' if failed else 'cancelled'
    record(game, f'{LABELS[task["action"]]}结束：{reason}。未耗路费已退还，原地与已耗时间保留。')


def reconcile(deps, game, task):
    if not game.player.alive:
        cancel(deps, game, task, failed=True, reason='此生已结束')


def complete(deps, game, task, rng):
    echo = get_echo(game.heavens_state['runtime'], task['target_id'])
    visit = echo['visit']
    year = game.heavens_state['runtime']['processed_years']
    if task['action'] == 'visit_depart':
        deps.move_visit(game, task['target_id'], task['action'], rng)
        visit.update(status='visiting', arrived_at=year)
        text = '已经抵达约定访学地点，可研读旧录或提前循约返程；返程路费仍在托管。'
    elif task['action'] == 'visit_return':
        deps.move_visit(game, task['target_id'], task['action'], rng)
        visit.update(status='returned', returned_at=year)
        text = '已经返回出发地点，此次个人访学结束。'
    else:
        visit['studied'] = True
        text = '完成实地研读，取得与合法旧录相符的现场对照记录。'
    task['status'] = 'completed'
    record(game, text)


def project(deps, game, target):
    destination = site_for(deps, game, VISIT_DESTINATIONS[target])
    echo = get_echo(game.heavens_state.get('runtime'), target)
    visit = echo.get('visit') if echo else None
    status = visit['status'] if visit else 'unavailable'
    return dict(destination_name=destination.name, status=status,
        studied=bool(visit and visit['studied']), return_fare=visit['return_fare'] if visit else 0,
        finding=f'已在{destination.name.split(" · ")[0]}实地对照合法旧录，确认异地节点确有同类响应。' if visit and visit['studied'] else None)
