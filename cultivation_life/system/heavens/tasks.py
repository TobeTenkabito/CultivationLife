"""Local evidence, escrow and resumable actual-year activities."""
from fractions import Fraction

from ...runtime import decode_rng, encode_rng, now_iso
from .state import active_task, create_echo, phase, record

LABELS = {'observe': '体察潮汐', 'check_history': '查证旧碑', 'exchange': '对照抄录',
          'attune': '登记本地参悟', 'maintain': '维护观测节点', 'resume': '继续任务', 'cancel': '取消任务'}


def local_reason(deps, game):
    facts = deps.read_actor_facts(game)
    return facts['blocked_reason']


def quote(deps, game, action, target_id, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('请先启用诸天联系')
    echo = runtime['sea_echo']
    task = active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or target_id != task['id']:
            # Cancelling a registered, unused application is also explicit.
            if action == 'cancel' and target_id == 'sea_echo' and echo and echo['application']:
                return dict(action=action, target_id=target_id, years=0, costs={}, refundable={})
            raise ValueError('诸天任务不可见或已结束')
        if action == 'cancel':
            escrow = task['escrow']
            return dict(action=action, target_id=target_id, years=0, costs={},
                        refundable={'stones': escrow['total'] - escrow['spent'] - escrow['refunded'],
                                    'material_id': (escrow['material'] or {}).get('id')})
        reason = task_reason(deps, game, task)
        if reason:
            raise ValueError(reason)
        return dict(action=action, target_id=target_id, years=task['duration'] - task['progress'],
                    costs={}, refundable={}, deadline=deadline(runtime, echo))
    if target_id != 'sea_echo':
        raise ValueError('诸天对象不可见或不存在')
    reason = local_reason(deps, game)
    if reason:
        raise ValueError(reason)
    if task:
        raise ValueError('请先继续或取消当前诸天任务')
    if not echo:
        if not game.heavens_state['generation_enabled'] or not deps.get_definitions().generation_available or action != 'observe':
            raise ValueError('尚未登记法则天海联系；可先在当地体察')
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
        if echo['application'] or echo['applications_used'] >= (2 if echo['maintained'] else 1):
            raise ValueError('本周期可登记的参悟次数已用完')
        return dict(action=action, target_id=target_id, years=0, costs={}, refundable={}, deadline=deadline(runtime, echo))
    if action == 'maintain' and echo['maintenance_started']:
        raise ValueError('本周期维护机会已使用')
    durations = {'observe': 'observe_years', 'check_history': 'history_years', 'exchange': 'exchange_years', 'maintain': 'maintain_years'}
    costs = {'observe': 0, 'check_history': definition['history_stones'],
             'exchange': definition['exchange_stones'], 'maintain': definition['maintain_stones']}
    years = definition[durations[action]]
    if years > cutoff - offset:
        raise ValueError('窗口余量不足以完成此项任务，可等待下一周期或退出')
    facts = deps.read_actor_facts(game)
    if facts['stones'] < costs[action]:
        raise ValueError('灵石不足')
    mp = facts['max_mp'] * .05 if action == 'maintain' else 0
    if mp > facts['mp']:
        raise ValueError('维护所需法力不足')
    if action == 'maintain' and options.get('material_id') not in {row['id'] for row in deps.quote_materials(game)}:
        raise ValueError('请选择一件闲置的本体九阶普通阵材')
    return dict(action=action, target_id=target_id, years=years,
                costs={'stones': costs[action], 'mp': mp, 'material_id': options.get('material_id')},
                refundable={'unspent_stones': True, 'unused_material': action == 'maintain', 'mp': False},
                deadline=deadline(runtime, echo))


def deadline(runtime, echo):
    cycle, _offset, cutoff = phase(runtime, echo)
    return echo['origin_year'] + cycle * echo['definition']['period_years'] + cutoff


def task_reason(deps, game, task):
    reason = local_reason(deps, game)
    if reason:
        return reason
    runtime = game.heavens_state['runtime']
    echo = runtime['sea_echo']
    cycle, offset, cutoff = phase(runtime, echo)
    if task['cycle'] != cycle or offset + task['duration'] - task['progress'] > cutoff:
        return '任务错过当前观测窗口'
    if task['person_id'] and not deps.person_available(game, task['person_id']):
        return '合作人物不在场、已受控或被其他事务占用'
    return None


def cancel(deps, game, task, *, failed=False, reason='主动取消'):
    deps.refund_resources(game, task['escrow'])
    task['status'] = 'failed' if failed else 'cancelled'
    record(game, f'{LABELS[task["action"]]}结束：{reason}。保留已耗时间与投入，退还未耗托管。')


def reconcile(deps, game):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        return
    task = active_task(runtime)
    if task:
        # Pending events pause a task; they do not cancel its escrow.
        facts = deps.read_actor_facts(game)
        if not facts['alive']:
            cancel(deps, game, task, failed=True, reason='此生已结束')
        elif task['cycle'] != runtime['sea_echo']['cycle'] or runtime['processed_years'] > deadline(runtime, runtime['sea_echo']):
            cancel(deps, game, task, failed=True, reason='窗口已结束')
        elif task['person_id'] and not deps.person_available(game, task['person_id']):
            cancel(deps, game, task, failed=True, reason='合作人物无法继续履约')


def execute(deps, game, action, target_id, options, proposal):
    runtime = game.heavens_state['runtime']
    if action == 'cancel':
        task = active_task(runtime)
        if target_id == 'sea_echo':
            echo = runtime['sea_echo']
            application = echo['application']
            if application['remaining'] == application['unit_years']:
                echo['applications_used'] -= 1
            echo['application'] = None
            record(game, '取消本地参悟安排；完全未执行的登记退回次数，已经执行的时间与所得保留。')
            return {'message': '已取消参悟安排'}
        cancel(deps, game, task)
        return result(task)
    echo = runtime['sea_echo'] or create_echo(deps, game)
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
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, status='reserved',
            cycle=echo['cycle'], progress=0, duration=proposal['years'],
            escrow=deps.reserve_resources(game, proposal['costs']['stones'],
                options.get('material_id'), proposal['costs'].get('mp', 0)),
            person_id=echo['visitor_id'] if action == 'exchange' else None)
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
    echo = runtime['sea_echo']
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
    physical_reason = deps.read_actor_facts(game)['physical_reason']
    if task['status'] != 'failed' and physical_reason and task['progress'] == task['duration']:
        cancel(deps, game, task, failed=True, reason=physical_reason)
    if task['status'] != 'failed' and task['progress'] == task['duration'] and game.player.alive:
        complete(game, task)
    elif task['status'] == 'running':
        task['status'] = 'paused'
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()


def complete(game, task):
    echo = game.heavens_state['runtime']['sea_echo']
    action = task['action']
    task['status'] = 'completed'
    if action == 'observe':
        echo['observed_cycle'] = echo['cycle']
        text = '取得 E1：潮汐回响有稳定相位差，尚不能仅凭本地阵法解释。'
    elif action == 'check_history':
        echo['history_checked'] = True
        text = '取得 E2：接引碑的两段旧记修正了“全部由本地阵法造成”的解释，可在本地应用。'
    elif action == 'exchange':
        echo['exchanged'] = True
        text = '取得 E3：合法抄录支持因果天城旧节点与本地潮汐的联系；个人合作履约一次。'
    else:
        echo['maintained'] = True
        task['escrow']['material'] = None
        text = '维护完成，九阶阵材已消耗。本周期本地余韵延续至原截止后 600 年，原客观潮汐周期不变。'
    record(game, text)
