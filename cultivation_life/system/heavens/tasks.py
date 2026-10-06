"""Local evidence, escrow and resumable actual-year activities."""
from fractions import Fraction

from ...runtime import decode_rng, encode_rng, now_iso
from .state import active_task, create_echo, phase, record, get_echo, echo_site, site_for, contacts
from . import mirror, ruins, omens, visits, missions, freight, migration, survey, upkeep, frontier
from .frontier_definitions import FRONTIER_ID
from .definitions import MIRROR_ID, RUINS_ID, OMEN_IDS, VISIT_ACTIONS

LABELS = {'observe': '体察本地现象', 'check_history': '查证旧碑', 'exchange': '对照抄录',
          'attune': '登记本地参悟', 'maintain': '维护观测节点', 'correspond': '协作校订旧录', 'resume': '继续任务', 'cancel': '取消任务'}
LABELS.update(mirror.LABELS)
LABELS.update(ruins.LABELS)
LABELS.update(omens.LABELS)
LABELS.update(visits.LABELS)
LABELS.update(missions.LABELS)
LABELS.update(survey.LABELS)
LABELS.update(upkeep.LABELS)
LABELS.update(frontier.LABELS)


def local_reason(deps, game, target_id=None):
    facts = deps.read_actor_facts(game, target_id)
    return facts['blocked_reason']


def quote(deps, game, action, target_id, options):
    runtime = game.heavens_state.get('runtime')
    if frontier.handles(runtime, action, target_id):
        return frontier.quote(deps, game, action, target_id, options)
    if action in upkeep.LABELS:
        return upkeep.quote(deps, game, action, target_id, options)
    if survey.handles(runtime, action, target_id):
        return survey.quote(deps, game, action, target_id, options)
    if action in migration.LABELS:
        return migration.quote(deps, game, action, target_id, options)
    if action in freight.LABELS:
        return freight.quote(deps, game, action, target_id, options)
    if missions.handles(runtime, action, target_id):
        return missions.quote(deps, game, action, target_id, options)
    if visits.handles(runtime, action, target_id):
        return visits.quote(deps, game, action, target_id, options)
    if omens.handles(runtime, action, target_id):
        return omens.quote(deps, game, action, target_id, options)
    if ruins.handles(runtime, action, target_id):
        return ruins.quote(deps, game, action, target_id, options)
    if mirror.handles(runtime, action, target_id):
        return mirror.quote(deps, game, action, target_id, options)
    if not runtime:
        raise ValueError('请先启用诸天联系')
    echo = get_echo(runtime, target_id)
    task = active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or target_id != task['id']:
            # Cancelling a registered, unused application is also explicit.
            if action == 'cancel' and echo and echo['application']:
                return dict(action=action, target_id=target_id, years=0, costs={}, refundable={})
            raise ValueError('诸天任务不可见或已结束')
        if action == 'cancel':
            escrow = task['escrow']
            return dict(action=action, target_id=target_id, years=0, costs={},
                        refundable={'stones': escrow['total'] - escrow['spent'] - escrow['refunded'],
                                    'material_id': (escrow['material'] or {}).get('id')})
        echo = get_echo(runtime, task.get('target_id', 'sea_echo'))
        reason = task_reason(deps, game, task)
        if reason:
            raise ValueError(reason)
        return dict(action=action, target_id=target_id, years=task['duration'] - task['progress'],
                    costs={}, refundable={}, deadline=deadline(runtime, echo))
    if site_for(deps, game, target_id) is None:
        raise ValueError('诸天对象不可见或不存在')
    reason = local_reason(deps, game, target_id)
    if reason:
        raise ValueError(reason)
    if task:
        raise ValueError('请先继续或取消当前诸天任务')
    if not echo:
        if not game.heavens_state['generation_enabled'] or not deps.get_definitions().generation_available or action != 'observe':
            raise ValueError('尚未登记此地诸天联系；可先在当地体察')
        definition = deps.get_definitions().sea_echo
        return dict(action=action, target_id=target_id, years=definition.observe_years,
                    costs={'stones': 0, 'mp': 0}, refundable={}, deadline=runtime['processed_years'] + definition.window_years)
    cycle, offset, cutoff = phase(runtime, echo)
    if offset >= cutoff:
        raise ValueError('当前窗口已结束，可等待下一周期或继续原有修行')
    definition = echo['definition']
    if action == 'observe' and echo['observed_cycle'] == cycle:
        raise ValueError('本周期已完成体察')
    if action != 'observe' and echo['observed_cycle'] != cycle:
        raise ValueError('请先完成本周期体察')
    if action == 'check_history' and echo['history_checked']:
        raise ValueError('已持有相容的旧碑证据，无需重复查证')
    if action in {'exchange', 'attune', 'maintain'} and not echo['history_checked']:
        raise ValueError('请先查证旧碑，取得本地应用依据')
    if action == 'exchange':
        if echo['exchanged']:
            raise ValueError('已取得合法抄录，不再重复支付或领取')
        if options.get('person_id') != echo['visitor_id'] or not deps.person_available(game, echo['visitor_id']):
            raise ValueError('合作人物不在场、已受控或正被其他事务占用')
    if action == 'attune':
        if any(row['application'] for row in contacts(runtime)):
            raise ValueError('请先完成或取消已经登记的参悟安排')
        if echo['application'] or echo['applications_used'] >= (2 if echo['maintained'] else 1):
            raise ValueError('本周期可登记的参悟次数已用完')
        return dict(action=action, target_id=target_id, years=0, costs={}, refundable={}, deadline=deadline(runtime, echo))
    if action == 'correspond':
        site = echo_site(echo)
        if not echo['exchanged'] or echo.get('correspondence_completed', False):
            raise ValueError('须先取得合作抄录；每份旧录仅校订履约一次')
        if options.get('person_id') != echo['visitor_id'] or not deps.person_available(game, echo['visitor_id']):
            raise ValueError('合作人物不在场、已受控或正被其他事务占用')
        if echo['project_stones'] < site.correspondence_stones:
            raise ValueError('合作项目实有资金不足，不能凭空支付酬劳')
        if site.correspondence_years > cutoff-offset:
            raise ValueError('窗口余量不足以完成校订')
        return dict(action=action, target_id=target_id, years=site.correspondence_years,
                    costs={'stones': 0, 'mp': 0}, refundable={},
                    reward_stones=site.correspondence_stones, deadline=deadline(runtime, echo))
    if action == 'maintain' and echo['maintenance_started']:
        raise ValueError('本周期维护机会已使用')
    durations = {'observe': 'observe_years', 'check_history': 'history_years', 'exchange': 'exchange_years', 'maintain': 'maintain_years'}
    costs = {'observe': 0, 'check_history': definition['history_stones'],
             'exchange': definition['exchange_stones'], 'maintain': definition['maintain_stones']}
    years = definition[durations[action]]
    if years > cutoff - offset:
        raise ValueError('窗口余量不足以完成此项任务，可等待下一周期或退出')
    facts = deps.read_actor_facts(game, target_id)
    if facts['stones'] < costs[action]:
        raise ValueError('灵石不足')
    mp = facts['max_mp'] * .05 if action == 'maintain' else 0
    if mp > facts['mp']:
        raise ValueError('维护所需法力不足')
    if action == 'maintain' and options.get('material_id') not in {row['id'] for row in deps.quote_materials(game, target_id)}:
        raise ValueError('请选择一件闲置的本体九阶普通阵材')
    return dict(action=action, target_id=target_id, years=years,
                costs={'stones': costs[action], 'mp': mp, 'material_id': options.get('material_id')},
                refundable={'unspent_stones': True, 'unused_material': action == 'maintain', 'mp': False},
                deadline=deadline(runtime, echo))


def deadline(runtime, echo):
    cycle, _offset, cutoff = phase(runtime, echo)
    return echo['origin_year'] + cycle * echo['definition']['period_years'] + cutoff


def task_reason(deps, game, task):
    if task.get('target_id') == FRONTIER_ID:
        return frontier.task_reason(deps, game, task)
    if task['action'] == 'survey_wait':
        return survey.actor_reason(deps, game, task['target_id'])
    if task['action'] == 'mission_wait':
        return missions.wait_reason(deps, game)
    if task['action'] in VISIT_ACTIONS:
        return visits.task_reason(deps, game, task)
    if task.get('target_id') in OMEN_IDS:
        return omens.task_reason(deps, game, task)
    if task.get('target_id') == RUINS_ID:
        return ruins.task_reason(deps, game, task)
    if task.get('target_id') == MIRROR_ID:
        return mirror.task_reason(deps, game, task)
    reason = local_reason(deps, game, task.get('target_id', 'sea_echo'))
    if reason:
        return reason
    runtime = game.heavens_state['runtime']
    echo = get_echo(runtime, task.get('target_id', 'sea_echo'))
    cycle, offset, cutoff = phase(runtime, echo)
    if task['cycle'] != cycle or offset + task['duration'] - task['progress'] > cutoff:
        return '任务错过当前观测窗口'
    if task['person_id'] and not deps.person_available(game, task['person_id']):
        return '合作人物不在场、已受控或被其他事务占用'
    return None


def cancel(deps, game, task, *, failed=False, reason='主动取消'):
    if task['action'] in VISIT_ACTIONS:
        return visits.cancel(deps, game, task, failed=failed, reason=reason)
    deps.refund_resources(game, task['escrow'])
    if task.get('project_reward', 0):
        get_echo(game.heavens_state['runtime'], task.get('target_id', 'sea_echo'))['project_stones'] += task['project_reward']
        task['project_reward'] = 0
    task['status'] = 'failed' if failed else 'cancelled'
    if task['action'] == 'frontier_inquire':
        frontier.close(game, 'failed' if failed else 'cancelled', game.heavens_state['runtime']['processed_years'])
    if task['action'] == 'mirror_repair':
        mirror.end_repair(game, task['status'])
    record(game, f'{LABELS[task["action"]]}结束：{reason}。保留已耗时间与投入，退还未耗托管。')


def reconcile(deps, game):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        return
    if not game.player.alive:
        for echo in contacts(runtime):
            visit = echo.get('visit')
            if visit and visit['status'] in {'preparing', 'visiting'}:
                deps.grant_stones(game, visit['return_fare'])
                visit.update(status='failed', return_fare=0)
    task = active_task(runtime)
    if task:
        if task.get('target_id') == FRONTIER_ID:
            if not game.player.alive:
                cancel(deps, game, task, failed=True, reason='此生已结束')
            return
        if task['action'] in {'mission_wait', 'survey_wait'}:
            if not game.player.alive:
                cancel(deps, game, task, failed=True, reason='此生已结束')
            return
        if task['action'] in VISIT_ACTIONS:
            visits.reconcile(deps, game, task)
            return
        # Pending events pause a task; they do not cancel its escrow.
        if task.get('target_id') in OMEN_IDS:
            saved = omens.get(game, task['target_id'])
            if not game.player.alive or runtime['processed_years'] > saved['last_seen']+saved['definition']['lifetime_years']:
                cancel(deps, game, task, failed=True, reason='此生已结束或征兆已消退')
            return
        if task.get('target_id') in {MIRROR_ID, RUINS_ID}:
            facts = (deps.read_ruins_facts if task['target_id'] == RUINS_ID else deps.read_mirror_facts)(game)
            if not facts['alive'] or not facts['inside']:
                cancel(deps, game, task, failed=True, reason='此生已结束或离开原诸天异象')
            return
        echo = get_echo(runtime, task.get('target_id', 'sea_echo'))
        facts = deps.read_actor_facts(game, echo['id'])
        if not facts['alive']:
            cancel(deps, game, task, failed=True, reason='此生已结束')
        elif task['cycle'] != echo['cycle'] or runtime['processed_years'] > deadline(runtime, echo):
            cancel(deps, game, task, failed=True, reason='窗口已结束')
        elif task['person_id'] and not deps.person_available(game, task['person_id']):
            cancel(deps, game, task, failed=True, reason='合作人物无法继续履约')


def execute(deps, game, action, target_id, options, proposal):
    runtime = game.heavens_state['runtime']
    if frontier.handles(runtime, action, target_id):
        return frontier.execute(deps, game, action, target_id, options, proposal, run_task=run_segment, cancel_task=cancel, task_result=result)
    if action in upkeep.LABELS:
        return upkeep.execute(deps, game, action, target_id, options, proposal)
    if survey.handles(runtime, action, target_id):
        return survey.execute(deps, game, action, target_id, options, run_task=run_segment, cancel_task=cancel, task_result=result)
    if action in migration.LABELS:
        return migration.execute(deps, game, action, target_id, options)
    if action in freight.LABELS:
        return freight.execute(deps, game, action, target_id, options)
    if missions.handles(runtime, action, target_id):
        return missions.execute(deps, game, action, target_id, options, proposal,
            run_task=run_segment, cancel_task=cancel, task_result=result)
    if visits.handles(runtime, action, target_id):
        return visits.execute(deps, game, action, target_id, options, proposal,
                              run_task=run_segment, task_result=result)
    if omens.handles(runtime, action, target_id):
        return omens.execute(deps, game, action, target_id, options, proposal,
                             cancel_task=cancel, run_task=run_segment, task_result=result)
    if ruins.handles(runtime, action, target_id):
        return ruins.execute(deps, game, action, target_id, options, proposal,
                             cancel_task=cancel, run_task=run_segment, task_result=result)
    if mirror.handles(runtime, action, target_id):
        return mirror.execute(deps, game, action, target_id, options, proposal,
                              cancel_task=cancel, run_task=run_segment, task_result=result)
    if action == 'cancel':
        task = active_task(runtime)
        echo = get_echo(runtime, target_id)
        if echo:
            application = echo['application']
            if application['remaining'] == application['unit_years']:
                echo['applications_used'] -= 1
            echo['application'] = None
            record(game, '取消本地参悟安排；完全未执行的登记退回次数，已经执行的时间与所得保留。')
            return {'message': '已取消参悟安排'}
        cancel(deps, game, task)
        return result(task)
    if action == 'resume':
        echo = get_echo(runtime, active_task(runtime).get('target_id', 'sea_echo'))
    else:
        echo = get_echo(runtime, target_id) or create_echo(deps, game, target_id)
    if action == 'attune':
        if echo['reward_base'] is None:
            echo['reward_base'] = deps.opportunity_base(game)
        unit = deps.unit_years(game)
        echo['application'] = dict(cycle=echo['cycle'], remaining=unit, unit_years=unit)
        echo['applications_used'] += 1
        record(game, '已登记本地参悟，仅对随后实际完成的合法普通修炼生效。')
        return {'message': '已登记参悟，请选择正常修炼'}
    if action == 'resume':
        task = active_task(runtime)
    else:
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, status='reserved', target_id=target_id,
            cycle=echo['cycle'], progress=0, duration=proposal['years'],
            escrow=deps.reserve_resources(game, proposal['costs']['stones'],
                options.get('material_id'), proposal['costs'].get('mp', 0)),
            person_id=echo['visitor_id'] if action in {'exchange', 'correspond'} else None)
        if action == 'correspond':
            task['project_reward'] = proposal['reward_stones']
            echo['project_stones'] -= task['project_reward']
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:] + [task]
        if action == 'maintain':
            echo['maintenance_started'] = True
    run_segment(deps, game, task)
    return result(task)


def result(task):
    return {'task_id': task['id'], 'progress': task['progress'], 'status': task['status']}


def run_segment(deps, game, task):
    from ..possession_system import advance_player_age
    runtime = game.heavens_state['runtime']
    echo = get_echo(runtime, task.get('target_id', 'sea_echo'))
    unit = deps.unit_years(game)
    rng = decode_rng(game.seed, game.rng_state)
    start_age, elapsed, news = game.player.age, 0, []
    task['status'] = 'running'
    for _ in range(min(100, task['duration'] - task['progress'])):
        reason = task_reason(deps, game, task)
        if reason:
            task['status'] = 'paused'
            break
        advance_player_age(game.player)
        elapsed += 1
        task['progress'] += 1
        escrow = task['escrow']
        spent = escrow['total'] * task['progress'] // task['duration']
        if task['action'] == 'exchange':
            echo['project_stones'] += spent - escrow['spent']
        escrow['spent'] = spent
        proceed = deps.advance_year(game, rng, news)
        if task['status'] == 'failed' or not game.player.alive:
            break
        if not proceed or game.pending_event:
            task['status'] = 'paused'
            break
    credit = Fraction(**{'numerator': runtime['unit_credit']['numerator'], 'denominator': runtime['unit_credit']['denominator']}) + Fraction(elapsed, unit)
    units = credit.numerator // credit.denominator
    credit -= units
    runtime['unit_credit'] = dict(numerator=credit.numerator, denominator=credit.denominator)
    if elapsed:
        deps.settle_activity_units(game, rng, units, elapsed, start_age, unit, news)
    reconcile(deps, game)  # Soul erosion and unit settlement may have killed or captured someone.
    if task.get('target_id') == FRONTIER_ID:
        if task['status'] != 'failed':
            reason = frontier.task_reason(deps, game, task)
            if task['progress'] == task['duration'] and not reason:
                frontier.complete(deps, game, task)
            else:
                task['status'] = 'paused'
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        return
    if task['action'] in {'mission_wait', 'survey_wait'}:
        if task['status'] != 'failed':
            task['status'] = 'completed' if task['progress'] == task['duration'] else 'paused'
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        return
    if task['action'] in VISIT_ACTIONS:
        # Crossing occurs only after both real time and unit settlement succeed.
        # A final-year event or changed route keeps the paid task resumable.
        if task['status'] != 'failed':
            if task['progress'] == task['duration'] and not visits.task_reason(deps, game, task):
                visits.complete(deps, game, task, rng)
            else:
                task['status'] = 'paused'
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        return
    physical_reason = (deps.read_omen_facts(game, task['target_id'])['physical_reason'] if task.get('target_id') in OMEN_IDS
                       else deps.read_ruins_facts(game)['physical_reason'] if task.get('target_id') == RUINS_ID
                       else deps.read_mirror_facts(game)['physical_reason'] if task.get('target_id') == MIRROR_ID
                       else deps.read_actor_facts(game, echo['id'])['physical_reason'])
    if task['status'] != 'failed' and physical_reason and task['progress'] == task['duration']:
        cancel(deps, game, task, failed=True, reason=physical_reason)
    if (task['status'] != 'failed' and task['progress'] == task['duration'] and game.player.alive
            and not (task['action'] in {'mirror_assault', 'mirror_repair', 'ruins_take'} and game.pending_event)):
        complete(game, task, deps, rng)
    elif task['status'] == 'running':
        task['status'] = 'paused'
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()


def complete(game, task, deps, rng):
    if task.get('target_id') in OMEN_IDS:
        omens.complete(game, task)
        return
    if task.get('target_id') == RUINS_ID:
        ruins.complete(deps, game, task, rng)
        return
    if task.get('target_id') == MIRROR_ID:
        mirror.complete(deps, game, task, rng)
        return
    echo = get_echo(game.heavens_state['runtime'], task.get('target_id', 'sea_echo'))
    site = echo_site(echo)
    action = task['action']
    task['status'] = 'completed'
    if action == 'observe':
        echo['observed_cycle'] = echo['cycle']
        text = f'取得 E1：{site.findings[0]}'
    elif action == 'check_history':
        echo['history_checked'] = True
        text = f'取得 E2：{site.findings[1]}'
    elif action == 'exchange':
        echo['exchanged'] = True
        text = f'取得 E3：{site.findings[2]}'
    elif action == 'correspond':
        amount = task['project_reward']
        deps.grant_stones(game, amount)
        task['project_reward'] = 0
        echo['correspondence_completed'] = True
        text = f'已与{site.visitor_name}完成旧录校订，合法副本留给本地研究；从合作项目实有资金支付{amount}灵石，一次履约。'
    else:
        echo['maintained'] = True
        task['escrow']['material'] = None
        text = f'维护完成，九阶阵材已消耗。本周期本地余韵延续至原截止后 {echo["definition"]["extension_years"]} 年，原客观周期不变。'
    record(game, f'{site.name}：{text}')
