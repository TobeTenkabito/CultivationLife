"""One relic, two linked mechanisms, finite rewards and scoped evidence."""
import copy
from dataclasses import asdict
from hashlib import sha256

from ...runtime import decode_rng, encode_rng
from .definitions import RUINS_ID, RUINS_ACTIONS
from .state import active_task, record

LABELS = dict(zip(('ruins_'+key for key in ('enter', 'leave', 'observe', 'verify', 'read', 'take', 'replace', 'erase', 'contact', 'return')),
                 ('进入因果遗址', '退出因果遗址', '观察阵纹', '查证两端关联', '读取合法抄本', '直接取走阵芯', '替换后取芯', '清理未读残留', '追查回响接触点', '归还并安装阵芯')))


def get(game):
    return game.heavens_state.get('runtime', {}).get('ruins')


def handles(runtime, action, target_id):
    task = active_task(runtime) if runtime else None
    return (action in RUINS_ACTIONS or target_id == RUINS_ID or action in {'resume', 'cancel'}
            and task is not None and target_id == task['id'] and task.get('target_id') == RUINS_ID)


def create(deps, game):
    runtime = game.heavens_state['runtime']
    identity = 'heavens-ruins-' + sha256(f'{game.id}:{game.seed}:ruins:v1'.encode()).hexdigest()[:20]
    definition = asdict(deps.get_definitions().ruins)
    ruins = dict(id=RUINS_ID, scene_id=identity, definition=definition, created_year=runtime['processed_years'],
                 observed=False, verified=False, record_acquired=False, contact_known=False,
                 reward=deps.ruins_material(game, identity),
                 core=dict(id=identity+'-core', definition_id='returning_tide_core', name='回潮阵芯', owner='ward', acquisition=None),
                 ward=dict(id=identity+'-ward', world=definition['linked_world'], location_id=definition['linked_location_id'], component='core'),
                 guardian=dict(wounds=0, encounters=0, result=None), local_traces={}, guardian_records={}, sent_records={})
    runtime['ruins'] = ruins
    game.heavens_state['definition_versions'][RUINS_ID] = definition['revision']
    record(game, '无棣原旧阵通往因果遗址：阵芯与异界回响一同明灭，擅取可能切断另一端机关；入口可原路返回。')
    return ruins


def trace(game, kind, *, witnessed=False):
    ruins = get(game)
    now = game.heavens_state['runtime']['processed_years']
    if kind not in ruins['guardian_records']:
        if witnessed:
            origin = ruins['local_traces'].pop(kind, now)
            ruins['guardian_records'][kind] = dict(year=origin, read_at=now)
        else:
            ruins['local_traces'].setdefault(kind, now)


def year_step(game):
    """The saved mechanism scans residues; no NPC is aged or given source coordinates."""
    ruins = get(game)
    if not ruins:
        return
    now = game.heavens_state['runtime']['processed_years']
    definition = ruins['definition']
    for kind, year in list(ruins['local_traces'].items()):
        if now-year >= definition['trace_read_years']:
            ruins['guardian_records'][kind] = dict(year=year, read_at=now)
            del ruins['local_traces'][kind]
    if ruins['ward']['component'] is not None:
        for kind, row in ruins['guardian_records'].items():
            if kind not in ruins['sent_records'] and now-row['read_at'] >= definition['trace_send_years']:
                ruins['sent_records'][kind] = dict(**row, sent_at=now)


def quote(deps, game, action, target_id, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('请先启用诸天联系')
    ruins, task = get(game), active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target_id or task.get('target_id') != RUINS_ID:
            raise ValueError('遗址任务不存在或已结束')
        if action == 'resume' and (reason := task_reason(deps, game, task)):
            raise ValueError(reason)
        escrow = task['escrow']
        return dict(years=task['duration']-task['progress'] if action == 'resume' else 0, costs={},
                    refundable={'stones': escrow['total']-escrow['spent']-escrow['refunded']} if action == 'cancel' else {}, deadline=None)
    if action not in RUINS_ACTIONS or target_id != RUINS_ID:
        raise ValueError('未知遗址动作或目标')
    facts = deps.read_ruins_facts(game)
    if facts['blocked_reason']:
        raise ValueError(facts['blocked_reason'])
    if task:
        raise ValueError('请先继续或取消当前诸天任务')
    if action == 'ruins_enter':
        if facts['inside']:
            raise ValueError('已经在因果遗址中')
        if facts['entry_reason']:
            raise ValueError(facts['entry_reason'])
        if not ruins and (not game.heavens_state['generation_enabled'] or not deps.get_definitions().generation_available):
            raise ValueError('未允许发现新的诸天联系')
        return dict(years=0, costs={}, refundable={}, deadline=None, warning='队友留在原界；独立遗址保留稳定退路，阵芯与抄本不会刷新。')
    if not ruins or not facts['inside']:
        raise ValueError('须先从人界无棣原进入因果遗址')
    if action == 'ruins_leave':
        return dict(years=0, costs={}, refundable={}, deadline=None, warning='保留所得与记录；退出不会自动抹迹，也不自动生成追兵。')
    if facts['activity_reason']:
        raise ValueError(facts['activity_reason'])
    core, definition = ruins['core'], ruins['definition']
    if action == 'ruins_observe' and ruins['observed']:
        raise ValueError('已持有阵纹观察记录')
    if action in {'ruins_verify', 'ruins_read'} and not ruins['observed']:
        raise ValueError('请先观察阵纹')
    if action == 'ruins_verify' and ruins['verified']:
        raise ValueError('已查明两端关联')
    if action == 'ruins_read' and ruins['record_acquired']:
        raise ValueError('本份抄本与预留阵材已领取，不会刷新')
    if action in {'ruins_take', 'ruins_replace'} and core['acquisition'] is not None:
        raise ValueError('唯一阵芯已领取；归还也不会生成第二份')
    if action == 'ruins_take' and facts['combat_reason']:
        raise ValueError(facts['combat_reason'])
    if action in {'ruins_replace', 'ruins_contact'} and not ruins['verified']:
        raise ValueError('请先查证两端关联')
    if action == 'ruins_replace' and options.get('material_id') not in {row['id'] for row in deps.quote_materials(game, RUINS_ID)}:
        raise ValueError('须使用一件闲置的人界四阶普通阵材')
    if action == 'ruins_contact':
        if ruins['contact_known']:
            raise ValueError('已取得有限接触线索，不重复授予坐标')
        if ruins['ward']['component'] is None:
            raise ValueError('关联阵眼失效，回响通信中断；须先归还安装阵芯')
    if action == 'ruins_return' and core['owner'] != 'player':
        raise ValueError('你未持有此唯一阵芯')
    if action == 'ruins_erase' and not ruins['local_traces']:
        raise ValueError('没有尚未读取的本地残留；守阵机关留档与送出记录不能抹除')
    key = action.removeprefix('ruins_')
    mp = facts['max_mp'] * definition['mana_fraction'] if key in {'verify', 'replace'} else 0
    stones = definition.get(key+'_stones', 0)
    if facts['mp'] < mp or facts['stones'] < stones:
        raise ValueError('法力或灵石不足')
    warning = ('取芯即切断两端阵眼和回响通信，并留下目击记录；随后按当前战斗预案交锋，可能负伤或死亡。' if key == 'take' else
               '安装后移交唯一阵芯，恢复对应阵眼；已送出的记录不撤回，不能再次领取阵芯。' if key == 'return' else
               '只能清除完成时仍未读到的残留；施工期间仍可能被读到，已留档或送出的证据不撤回。' if key == 'erase' else
               '遗址机关在残留形成后扫描留档，关联阵眼完好时继续送出；不会因此获得你的来源坐标。')
    return dict(years=definition[key+'_years'], costs=dict(stones=stones, mp=mp, material_id=options.get('material_id')),
                refundable={}, deadline=None, material_consumed=key == 'replace', warning=warning)


def task_reason(deps, game, task):
    facts = deps.read_ruins_facts(game)
    return (facts['blocked_reason'] or facts['activity_reason'] or (None if facts['inside'] else '已离开本因果遗址')
            or (facts['combat_reason'] if task['action'] == 'ruins_take' else None))


def execute(deps, game, action, target_id, options, proposal, *, cancel_task, run_task, task_result):
    runtime = game.heavens_state['runtime']
    task = active_task(runtime)
    if action == 'cancel':
        cancel_task(deps, game, task)
        return task_result(task)
    if action == 'resume':
        run_task(deps, game, task)
        return task_result(task)
    if action in {'ruins_enter', 'ruins_leave'}:
        ruins = get(game) or create(deps, game)
        rng = decode_rng(game.seed, game.rng_state)
        (deps.enter_ruins if action == 'ruins_enter' else deps.leave_ruins)(game, ruins, rng)
        game.rng_state = encode_rng(rng)
        record(game, LABELS[action]+'；唯一归属、阵眼与证据状态均保留。')
        return {'message': LABELS[action]}
    escrow = deps.reserve_resources(game, proposal['costs']['stones'], options.get('material_id'), proposal['costs']['mp'], target_id=RUINS_ID)
    # Fitting the substitute consumes the material at the start, even if interrupted.
    escrow['material'] = None
    task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, status='reserved', target_id=RUINS_ID,
                cycle=0, progress=0, duration=proposal['years'], escrow=escrow, person_id=None)
    runtime['next_task_seq'] += 1
    runtime['tasks'] = runtime['tasks'][-3:] + [task]
    if action != 'ruins_erase':
        trace(game, action)
    run_task(deps, game, task)
    return task_result(task)


def complete(deps, game, task, rng):
    ruins = get(game)
    action = task['action']
    task['status'] = 'completed'
    message = LABELS[action]+'完成。'
    if action == 'ruins_observe':
        ruins['observed'] = True
        message = '阵芯与异界阵纹同步明灭；守阵机关会扫描残留，取用前可继续查证。'
    elif action == 'ruins_verify':
        ruins['verified'] = True
        message = '已证实唯一阵芯同时维系本地机关与另一端回响阵眼；守阵机关存在，但尚未取得另一端接触位置。'
    elif action == 'ruins_read':
        ruins['record_acquired'] = True
        game.player.formation_materials.append(copy.deepcopy(ruins['reward']))
        message = '取得回潮阵纹合法抄本与一件预留四阶阵材；阵芯所有权不变，不发普通修炼机缘。'
    elif action in {'ruins_take', 'ruins_replace'}:
        ruins['core'].update(owner='player', acquisition=action)
        ruins['ward']['component'] = 'replacement' if action == 'ruins_replace' else None
        if action == 'ruins_take':
            trace(game, action, witnessed=True)
            outcome, summary, wounds = deps.fight_ruins(game, ruins, rng)
            if outcome == 'technique_blocked':
                # A last-year capability change must not turn a rejected battle into free loot.
                raise ValueError('当前功法无法迎战，请先调整战斗预案')
            ruins['guardian'].update(wounds=wounds, encounters=ruins['guardian']['encounters']+1, result=outcome)
            message = '阵芯已移交，关联阵眼失效、回响通信中断。守阵交锋：'+summary
        else:
            message = '替代阵材已接续两端机关；取得同一枚回潮阵芯，施工记录仍保留。'
    elif action == 'ruins_erase':
        count = len(ruins['local_traces'])
        ruins['local_traces'].clear()
        message = f'清除了 {count} 类尚未读取的本地残留；守阵机关留档与送出记录均保留。'
    elif action == 'ruins_contact':
        ruins['contact_known'] = True
        message = '回响旧铭指向魔界赤髓城的旧阵传讯节点。这是有限接触线索，不是可穿越路线或可施工坐标。'
    elif action == 'ruins_return':
        ruins['core']['owner'] = 'ward'
        ruins['ward']['component'] = 'core'
        message = '回潮阵芯已归还安装，两端机关及回响通信恢复；唯一所有权已移交，不能再次领取。'
    record(game, message)


def project(deps, game):
    ruins, facts = get(game), deps.read_ruins_facts(game)
    value = dict(id=RUINS_ID, name='因果遗址', entry='人界 · 无棣原', known=bool(ruins), inside=facts['inside'],
                 description='唯一阵芯与异界阵纹同步明灭。可调查、读取、替换、取芯或原路退出；所得不刷新。',
                 materials=deps.quote_materials(game, RUINS_ID), actions=[])
    candidates = [('ruins_leave' if facts['inside'] else 'ruins_enter', {})]
    if ruins:
        value.update(observed=ruins['observed'], verified=ruins['verified'], record_acquired=ruins['record_acquired'],
                     contact='魔界 · 赤髓城旧阵传讯节点（无通行或施工坐标）' if ruins['contact_known'] else None,
                     core=copy.deepcopy(ruins['core']), ward_active=ruins['ward']['component'] is not None,
                     replacement=ruins['ward']['component'] == 'replacement',
                     traces=dict(local=len(ruins['local_traces']), held=len(ruins['guardian_records']), sent=len(ruins['sent_records'])))
        if ruins['observed']:
            value['trace_rule'] = f'残留形成 {ruins["definition"]["trace_read_years"]} 年后被守阵机关留档；再过 {ruins["definition"]["trace_send_years"]} 年，阵眼完好时送往另一端。抹迹只清除完成时仍未读取的残留。'
        if facts['inside']:
            for action in ('ruins_observe', 'ruins_verify', 'ruins_read', 'ruins_contact', 'ruins_replace', 'ruins_take', 'ruins_return', 'ruins_erase'):
                candidates.append((action, {'material_id': value['materials'][0]['id']} if action == 'ruins_replace' and value['materials'] else {}))
    for action, options in candidates:
        row = dict(action=action, target_id=RUINS_ID, label=LABELS[action], options=options)
        try:
            row.update(quote(deps, game, action, RUINS_ID, options), enabled=True)
        except ValueError as exc:
            row.update(enabled=False, reason=str(exc))
        value['actions'].append(row)
    return value
