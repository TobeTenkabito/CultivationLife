"""Local evidence, physical fieldwork and finite consequences using shared tasks."""
from .incident_definitions import BY_ID, ALL_INCIDENTS, INCIDENT_IDS, INCIDENT_ACTIONS, LABELS, response, terms
from .state import active_task, record


def get(game, identity):
    return game.heavens_state.get('runtime', {}).get('incidents', {}).get(identity)


def handles(runtime, action, target):
    task = active_task(runtime) if runtime else None
    return (action in INCIDENT_ACTIONS or target in INCIDENT_IDS or action in {'resume', 'cancel'}
            and task is not None and task['id'] == target and task.get('target_id') in INCIDENT_IDS)


def task_reason(deps, game, task):
    return deps.incident_facts(game, task['target_id'], task['action'])['reason']


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('请先在诸天偏好中开启发现')
    task = active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target or task.get('target_id') not in INCIDENT_IDS:
            raise ValueError('界域事务已结束或不存在')
        if action == 'resume' and (reason := task_reason(deps, game, task)):
            raise ValueError(reason)
        escrow = task['escrow']
        return dict(years=task['duration']-task['progress'] if action == 'resume' else 0,
                    costs={}, refundable={'stones': escrow['total']-escrow['spent']-escrow['refunded']} if action == 'cancel' else {})
    if target not in BY_ID or action not in INCIDENT_ACTIONS:
        raise ValueError('未知界域事务')
    if task:
        raise ValueError('请先继续或取消当前诸天任务')
    desc, saved = BY_ID[target], get(game, target)
    stage = saved['stage'] if saved else 'unseen'
    allowed = {'unseen': {'incident_survey'}, 'surveying': {'incident_survey'},
               'surveyed': {'incident_preserve', 'incident_seal'}, 'treated': {'incident_review'}, 'closed': set()}
    if action not in allowed[stage]:
        raise ValueError('须依次求证、现场处理并返回复核；结案后不可重复领取')
    if not saved and (not game.heavens_state['generation_enabled'] or not deps.get_definitions().generation_available):
        raise ValueError('新事务发现已关闭，已有档案和任务仍可继续')
    facts = deps.incident_facts(game, target, action)
    if facts['reason']:
        raise ValueError(facts['reason'])
    years, stones, mana = terms(desc, action)
    mp = facts['max_mp'] * mana
    if facts['stones'] < stones or facts['mp'] < mp:
        raise ValueError('本次处理所需灵石或法力不足')
    return dict(years=years, costs=dict(stones=stones, mp=mp), refundable={'unspent_stones': True, 'mp': False},
                warning='亲自到场后才处理；完成现场事务后须沿普通地图返回复核。每案只结案一次，取消保留已耗年数和投入。')


def execute(deps, game, action, target, options, proposal, *, run_task, cancel_task, task_result):
    runtime = game.heavens_state['runtime']
    task = active_task(runtime)
    if action == 'cancel':
        cancel_task(deps, game, task)
        return task_result(task)
    if action != 'resume':
        if not get(game, target):
            runtime.setdefault('incidents', {})[target] = dict(stage='surveying', choice=None,
                opened_at=runtime['processed_years'], closed_at=None, remaining=0, base=0.0, claimed=0.0)
            game.heavens_state['definition_versions'][target] = 1
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, target_id=target,
                    status='reserved', cycle=0, progress=0, duration=proposal['years'], person_id=None,
                    escrow=deps.reserve_resources(game, proposal['costs']['stones'], None, proposal['costs']['mp']))
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:] + [task]
    run_task(deps, game, task)
    return task_result(task)


def complete(deps, game, task):
    desc, saved = BY_ID[task['target_id']], get(game, task['target_id'])
    action = task['action']
    if action == 'incident_survey':
        saved['stage'] = 'surveyed'
        finding = desc.evidence
    elif action in {'incident_preserve', 'incident_seal'}:
        saved.update(stage='treated', choice=action)
        finding = response(desc, action).finding
        if response(desc, action).effect == 'aid':
            saved['outcome'] = deps.incident_field_effect(game, desc.id)
            finding = saved['outcome']
    else:
        outcome = response(desc, saved['choice'])
        saved.update(stage='closed', closed_at=game.heavens_state['runtime']['processed_years'],
                     remaining=outcome.allowance, base=deps.opportunity_base(game))
        healed = deps.incident_relief(game) if outcome.effect == 'relief' else 0
        finding = (f'复核结案，实际恢复 {healed:.1f} 气血。' if outcome.effect == 'relief'
                   else f'复核结案，保留 {outcome.allowance} 年当地{ "修行" if outcome.effect == "practice" else "调息"}余量。')
        if outcome.effect == 'mana':
            saved['outcome'] = f'复核结案，实际恢复 {deps.incident_mana(game):.1f} 法力。'
            finding = saved['outcome']
        elif outcome.effect == 'aid':
            finding = '救护记录已归档：' + saved['outcome']
    task['status'] = 'completed'
    record(game, f'{desc.name}：{finding}')


def activity_extra(deps, game, base_gain, action):
    """Consume only physical local ordinary years; never create an extra grant."""
    extra, applied = 0.0, None
    for identity, saved in game.heavens_state.get('runtime', {}).get('incidents', {}).items():
        if saved['stage'] != 'closed' or not saved['remaining']:
            continue
        desc = BY_ID[identity]
        effect = response(desc, saved['choice']).effect
        if action != ('cultivate' if effect == 'practice' else 'rest'):
            continue
        facts = deps.incident_facts(game, identity, 'incident_review')
        if facts['reason'] or effect == 'practice' and not facts['can_apply']:
            continue
        if effect == 'practice':
            extra = min(max(0, base_gain) * .08, max(0, saved['base'] * .02 - saved['claimed']))
            applied = saved
        else:
            deps.incident_restore(game)
        saved['remaining'] -= 1
        game.heavens_state['revision'] += 1
        break
    return extra, applied


def project(deps, game, category='local'):
    directory = []
    for desc in ALL_INCIDENTS:
        if desc.category != category:
            continue
        saved = get(game, desc.id)
        stage = saved['stage'] if saved else 'unseen'
        local = game.player.world == desc.world
        row = dict(id=desc.id, world=desc.world, world_name=desc.world_name, name=desc.name,
                   location_name=desc.location_name, field_name=desc.field_name,
                   current=local, category=desc.category, stage=stage, rank=desc.rank, glimpse=desc.glimpse, evidence=None, finding=None,
                   choice=saved['choice'] if saved else None, remaining=saved['remaining'] if saved else 0, actions=[])
        if stage in {'surveyed', 'treated', 'closed'}:
            row['evidence'] = desc.evidence
        if stage in {'treated', 'closed'}:
            row['finding'] = saved.get('outcome') or response(desc, saved['choice']).finding
            row['effect'] = response(desc, saved['choice']).effect
        choices = ('incident_survey',) if stage in {'unseen', 'surveying'} else ('incident_preserve', 'incident_seal') if stage == 'surveyed' else ('incident_review',) if stage == 'treated' else ()
        for action in choices:
            option = dict(action=action, target_id=desc.id, options={}, label=LABELS[action])
            if action in {'incident_preserve', 'incident_seal'}:
                option.update(label=response(desc, action).label, description=response(desc, action).finding)
            try:
                option.update(quote(deps, game, action, desc.id, {}), enabled=True)
            except ValueError as exc:
                option.update(enabled=False, reason=str(exc))
            # Cost and time stay readable even when the player has yet to arrive.
            years, stones, _mana = terms(desc, action)
            option.setdefault('years', years)
            option.setdefault('costs', dict(stones=stones))
            row['actions'].append(option)
        directory.append(row)
    return directory
