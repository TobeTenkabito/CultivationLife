"""Ground-level evidence: perception never grants spatial-entry or power rights."""
import copy
from dataclasses import asdict

from .definitions import OMEN_IDS
from .state import active_task, contacts, record

LABELS = {'omen_study': '在当地对照征兆'}


def get(game, target_id):
    return game.heavens_state.get('runtime', {}).get('omens', {}).get(target_id)


def definition(deps, game, target_id):
    saved = get(game, target_id)
    return saved['definition'] if saved else next((asdict(row) for row in deps.get_definitions().omens if row.id == target_id), None)


def candidates(deps, game):
    runtime = game.heavens_state['runtime']
    if not deps.read_omen_facts or len(runtime['notifications']) >= 3:
        return []
    size = len(contacts(runtime)) + int('mirror' in runtime) + int('ruins' in runtime) + len(runtime.get('omens', {}))
    result = []
    for row in deps.get_definitions().omens:
        saved = get(game, row.id)
        facts = deps.read_omen_facts(game, row.id)
        if not facts['can_discover'] or saved and saved['studied'] or not saved and size >= 8:
            continue
        if saved and runtime['processed_years']-saved['last_seen'] < saved['definition']['cooldown_years']:
            continue
        if any(notice['id'] == row.id for notice in runtime['notifications']):
            continue
        result.append(row.id)
    return result


def discover(deps, game, target_id):
    runtime = game.heavens_state['runtime']
    now = runtime['processed_years']
    saved = get(game, target_id)
    if not saved:
        saved = dict(id=target_id, definition=definition(deps, game, target_id), first_seen=now, last_seen=now, studied=False)
        runtime.setdefault('omens', {})[target_id] = saved
        game.heavens_state['definition_versions'][target_id] = saved['definition']['revision']
    saved['last_seen'] = now
    desc = saved['definition']
    text = f'{desc["location_name"]} · {desc["name"]}：{desc["glimpse"]}'
    record(game, text)
    runtime['notifications'].append(dict(id=target_id, text=text, expires_at=now+desc['lifetime_years']))
    if game.heavens_state['watch'] and runtime['pause_on_opportunity']:
        runtime['pause_requested'] = True


def handles(runtime, action, target_id):
    task = active_task(runtime) if runtime else None
    return (action == 'omen_study' or target_id in OMEN_IDS or action in {'resume', 'cancel'}
            and task is not None and target_id == task['id'] and task.get('target_id') in OMEN_IDS)


def task_reason(deps, game, task):
    saved = get(game, task['target_id'])
    reason = deps.read_omen_facts(game, task['target_id'])['blocked_reason']
    if reason:
        return reason
    if game.heavens_state['runtime']['processed_years'] + task['duration']-task['progress'] > saved['last_seen']+saved['definition']['lifetime_years']:
        return '征兆已经消退；保留旧见闻，等待下次亲见再对照'
    return None


def quote(deps, game, action, target_id, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('尚未记录此征兆')
    task = active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target_id or task.get('target_id') not in OMEN_IDS:
            raise ValueError('征兆任务已结束或不存在')
        if action == 'resume' and (reason := task_reason(deps, game, task)):
            raise ValueError(reason)
        return dict(years=task['duration']-task['progress'] if action == 'resume' else 0, costs={}, refundable={})
    saved = get(game, target_id)
    if action != 'omen_study' or not saved:
        raise ValueError('须先亲见本地征兆，不能凭空补发见闻')
    if task:
        raise ValueError('请先继续或取消当前诸天任务')
    if saved['studied']:
        raise ValueError('已保存对照记录，重复阅读不再领取所得')
    duration = saved['definition']['study_years']
    if reason := task_reason(deps, game, dict(target_id=target_id, duration=duration, progress=0)):
        raise ValueError(reason)
    return dict(years=duration, costs=dict(stones=0, mp=0), refundable={}, deadline=saved['last_seen']+saved['definition']['lifetime_years'],
                warning='只在地面核对征兆，保存本地认识；不进入异象、不授予越阶力量。')


def execute(deps, game, action, target_id, options, proposal, *, cancel_task, run_task, task_result):
    runtime = game.heavens_state['runtime']
    task = active_task(runtime)
    if action == 'cancel':
        cancel_task(deps, game, task)
        return task_result(task)
    if action != 'resume':
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, status='reserved', target_id=target_id,
                    cycle=0, progress=0, duration=proposal['years'], person_id=None,
                    escrow=dict(total=0, spent=0, refunded=0, material=None, mp_paid=0))
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:] + [task]
    run_task(deps, game, task)
    return task_result(task)


def complete(game, task):
    saved = get(game, task['target_id'])
    saved['studied'] = True
    task['status'] = 'completed'
    runtime = game.heavens_state['runtime']
    runtime['notifications'] = [row for row in runtime['notifications'] if row['id'] != saved['id']]
    record(game, f'{saved["definition"]["name"]}对照完成：{saved["definition"]["finding"]}')


def project(deps, game):
    result = []
    runtime = game.heavens_state.get('runtime', {})
    for saved in runtime.get('omens', {}).values():
        desc = saved['definition']
        row = dict(id=saved['id'], name=desc['name'], world=desc['world'], location_id=desc['location_id'],
                   location_name=desc['location_name'], first_seen=saved['first_seen'], last_seen=saved['last_seen'],
                   studied=saved['studied'], remaining=max(0, saved['last_seen']+desc['lifetime_years']-runtime['processed_years']),
                   glimpse=desc['glimpse'], finding=desc['finding'] if saved['studied'] else None,
                   anomaly_id=desc['anomaly_id'] if saved['studied'] else None)
        action = dict(action='omen_study', target_id=saved['id'], label=LABELS['omen_study'], options={})
        try:
            action.update(quote(deps, game, 'omen_study', saved['id'], {}), enabled=True)
        except ValueError as exc:
            action.update(enabled=False, reason=str(exc))
        row['actions'] = [action]
        result.append(copy.deepcopy(row))
    return result
