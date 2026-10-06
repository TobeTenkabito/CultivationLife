"""A finite, persistent anomaly. Mechanics never borrow ordinary activity rewards."""
import copy
from dataclasses import asdict
from hashlib import sha256

from ...runtime import decode_rng, encode_rng
from .definitions import MIRROR_ID, MIRROR_ACTIONS
from .state import active_task, record

LABELS = {'mirror_enter': '进入镜律场域', 'mirror_leave': '沿原路退出',
          'mirror_probe': '低耗试探', 'mirror_decipher': '低耗破解',
          'mirror_isolate': '材料隔断', 'mirror_assault': '强攻机关',
          'mirror_repair': '修补并立约', 'mirror_release': '解除守约'}

PACT_YEARS = 3


def get(game):
    return game.heavens_state.get('runtime', {}).get('mirror')


def handles(runtime, action, target_id):
    task = active_task(runtime) if runtime else None
    return (action in MIRROR_ACTIONS or target_id == MIRROR_ID
            or action in {'resume', 'cancel'} and task is not None
            and target_id == task['id'] and task.get('target_id') == MIRROR_ID)


def create(deps, game, *, known=True, year=None):
    runtime = game.heavens_state['runtime']
    identity = 'heavens-mirror-' + sha256(f'{game.id}:{game.seed}:mirror:v1'.encode()).hexdigest()[:20]
    definition = asdict(deps.get_definitions().mirror)
    materials = deps.mirror_materials(game, identity)
    mirror = dict(id=MIRROR_ID, definition=definition, scene_id=identity,
                  created_year=runtime['processed_years'] if year is None else year, probed=False,
                  mana_capacity=deps.read_mirror_facts(game)['max_mp'] * definition['capacity_fraction'] if known else 0.0,
                  paid_mana=0.0, collected_mana=0.0, stored_mana=0.0,
                  record_acquired=False, chambers=[dict(opened=False, isolated=False,
                      guardian=None, reward=materials[index] if index < 2 else None)
                      for index in range(3)], traces=[])
    runtime['mirror'] = mirror
    game.heavens_state['definition_versions'][MIRROR_ID] = definition['revision']
    if known:
        record(game, '穆陵沙漠的镜纹通往镜律场域；入口有稳定退路，施术可能被镜阵收集。')
    else:
        mirror.update(player_known=False, capacity_pending=True)
    return mirror


def trace(game, kind, chamber=None):
    mirror = get(game)
    mirror['traces'].append(dict(year=game.heavens_state['runtime']['processed_years'], kind=kind, chamber=chamber))
    mirror['traces'] = mirror['traces'][-32:]


def collect(mirror, paid, chamber):
    """Only explicit, actually paid local MP enters this accounting boundary."""
    mirror['paid_mana'] += paid
    if chamber is not None and mirror['chambers'][chamber]['isolated']:
        return
    amount = min(paid * mirror['definition']['collection_fraction'],
                 max(0.0, mirror['mana_capacity'] - mirror['collected_mana']))
    mirror['collected_mana'] += amount
    mirror['stored_mana'] += amount


def quote(deps, game, action, target_id, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('请先启用诸天联系')
    mirror, task = get(game), active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target_id or task.get('target_id') != MIRROR_ID:
            raise ValueError('镜律任务不存在或已结束')
        if action == 'resume':
            reason = task_reason(deps, game, task)
            if reason:
                raise ValueError(reason)
        return dict(action=action, target_id=target_id,
                    years=task['duration']-task['progress'] if action == 'resume' else 0,
                    costs={}, refundable={}, deadline=None)
    if target_id != MIRROR_ID or action not in MIRROR_ACTIONS:
        raise ValueError('未知镜律动作或目标')
    facts = deps.read_mirror_facts(game)
    reason = facts['blocked_reason']
    if reason:
        raise ValueError(reason)
    if task:
        raise ValueError('请先继续或取消当前诸天任务')
    if action == 'mirror_enter':
        if facts['inside']:
            raise ValueError('已经在镜律场域中')
        if facts['entry_reason']:
            raise ValueError(facts['entry_reason'])
        if not mirror and (not game.heavens_state['generation_enabled'] or not deps.get_definitions().generation_available):
            raise ValueError('未允许发现新的诸天联系')
        return dict(years=0, costs={}, refundable={}, deadline=None,
                    warning='独立场域与外界隔绝；队友留在原界。入口保留退路，机关与所得不会因重访重置。')
    if not mirror or not facts['inside']:
        raise ValueError('须先从人界穆陵沙漠进入镜律场域')
    if action == 'mirror_leave':
        return dict(years=0, costs={}, refundable={}, deadline=None)
    if facts['activity_reason']:
        raise ValueError(facts['activity_reason'])
    definition = mirror['definition']
    pact = mirror.get('pact')
    if action == 'mirror_release':
        if not pact or pact['status'] != 'kept':
            raise ValueError('没有可解除的守约')
        return dict(years=0, costs={}, refundable={}, deadline=None,
                    message='解除保留两处材料核心的约定，已有规律记录保留。',
                    warning='守护机关会永久关闭这两处的低耗破解与材料隔断许可；以后只能实际强攻取物。不会重置机关、镜储或战斗快照，也不退修补投入。')
    if action == 'mirror_repair':
        if not mirror['probed']:
            raise ValueError('须先低耗试探，读懂镜纹留下的修补条件')
        if pact:
            raise ValueError('每处镜律场域只接受一次修补约定')
        if any(row['opened'] or row['isolated'] or row['guardian'] for row in mirror['chambers']):
            raise ValueError('须在三处机关尚未被解开、隔断或强攻时立约')
        if options.get('material_id') not in {m['id'] for m in deps.quote_materials(game, MIRROR_ID)}:
            raise ValueError('须提供一件闲置的人界四阶普通阵材')
        return dict(years=PACT_YEARS, costs=dict(stones=0, mp=0, material_id=options['material_id']),
                    refundable={}, deadline=None, chamber=None, material_consumed=True,
                    message='以一件阵材修补镜阵，实际工作 3 年，不额外施法。完成后取得第三处同一份规律记录，承诺保留前两处材料核心；不领取阵材或额外机缘。',
                    warning='阵材安装即消耗，中断可续做，取消不退且不再受理。守约期间不能操作两处核心；以后可明确解除，但解除后只能强攻取物。')
    chamber = None
    if action == 'mirror_probe':
        if mirror['probed']:
            raise ValueError('已确认收集规律，无需重复试探')
    else:
        if not mirror['probed']:
            raise ValueError('请先低耗试探，确认镜纹与施术的联系')
        if options.get('chamber') not in {'0', '1', '2'}:
            raise ValueError('请选择场域内实际存在的机关')
        chamber = int(options['chamber'])
        row = mirror['chambers'][chamber]
        if row['opened']:
            raise ValueError('此机关已解开，所得不会刷新')
        if chamber < 2 and pact and pact['status'] == 'kept':
            raise ValueError('已承诺保留此核心；须先在守约页明确解除约定')
        if chamber < 2 and pact and pact['status'] == 'released' and action != 'mirror_assault':
            raise ValueError('解除约定后，此核心只接受实际强攻，不再开放破解或隔断')
        if action == 'mirror_isolate':
            if row['isolated']:
                raise ValueError('此机关已与镜阵隔断')
            if options.get('material_id') not in {m['id'] for m in deps.quote_materials(game, MIRROR_ID)}:
                raise ValueError('须使用一件闲置的人界四阶普通阵材')
    key = action.removeprefix('mirror_')
    mp = facts['max_mp'] * definition['mana_fraction'] if action in {'mirror_probe', 'mirror_decipher'} else 0
    if facts['mp'] < mp:
        raise ValueError('法力不足；已付法力不会因取消或重访返还')
    years = 2 if action == 'mirror_decipher' and mirror.get('survey', {}).get('shared') else definition[f'{key}_years']
    return dict(years=years, costs=dict(stones=0, mp=mp, material_id=options.get('material_id')),
                refundable={}, deadline=None, chamber=chamber, material_consumed=action == 'mirror_isolate',
                warning=('强攻将使用当前战斗预案，可能负伤或死亡；后续机关可能获得本次实付法力供给。'
                         if action == 'mirror_assault' else '登记施术实付法力会被未隔断的镜阵收集；不会获得普通修炼机缘。'))


def task_reason(deps, game, task):
    facts = deps.read_mirror_facts(game)
    return facts['blocked_reason'] or facts['activity_reason'] or (None if facts['inside'] else '已离开本镜律场域，不能继续机关任务')


def execute(deps, game, action, target_id, options, proposal, *, cancel_task, run_task, task_result):
    runtime = game.heavens_state['runtime']
    task = active_task(runtime)
    if action == 'cancel':
        cancel_task(deps, game, task)
        return task_result(task)
    if action == 'resume':
        run_task(deps, game, task)
        return task_result(task)
    if action in {'mirror_enter', 'mirror_leave'}:
        mirror = get(game) or create(deps, game)
        rng = decode_rng(game.seed, game.rng_state)
        if action == 'mirror_enter':
            deps.enter_mirror(game, mirror, rng)
        else:
            deps.leave_mirror(game, mirror, rng)
        game.rng_state = encode_rng(rng)
        record(game, '进入镜律场域，镜纹随施术明灭；可先试探，也可沿原路退出。' if action == 'mirror_enter' else '沿稳定入口退出镜律场域；机关、记录与所得归属均已保留。')
        return {'message': LABELS[action]}
    mirror = get(game)
    if action == 'mirror_release':
        mirror['pact'].update(status='released', released_at=runtime['processed_years'])
        trace(game, action)
        record(game, '已明确解除镜律守约；原记录与修补事实保留，两处材料核心关闭和平取用许可，只能实际强攻。')
        return {'message': '镜律守约已解除'}
    before = game.player.mp
    escrow = deps.reserve_resources(game, 0, options.get('material_id'), proposal['costs']['mp'], target_id=MIRROR_ID)
    if action == 'mirror_repair':
        mirror['pact'] = dict(revision=1, status='repairing', duration=PACT_YEARS,
            task_id=f'heavens-task-{runtime["next_task_seq"]}', started_at=runtime['processed_years'],
            settled_at=None, released_at=None, material=escrow['material'])
        escrow['material'] = None
    if action == 'mirror_isolate':
        # A fitted material is physically consumed when work starts, including interruption.
        escrow['material'] = None
    task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, status='reserved',
                target_id=MIRROR_ID, cycle=0, progress=0, duration=proposal['years'],
                chamber=proposal['chamber'], escrow=escrow, person_id=None)
    runtime['next_task_seq'] += 1
    runtime['tasks'] = runtime['tasks'][-3:] + [task]
    collect(mirror, max(0.0, before-game.player.mp), task['chamber'])
    trace(game, action, task['chamber'])
    run_task(deps, game, task)
    return task_result(task)


def open_chamber(game, chamber):
    mirror = get(game)
    row = mirror['chambers'][chamber]
    if row['opened']:
        return
    row['opened'] = True
    if row['reward']:
        game.player.formation_materials.append(copy.deepcopy(row['reward']))
    else:
        mirror['record_acquired'] = True
    record(game, f'镜律第 {chamber+1} 处机关已解开：' + (f'取得{row["reward"]["name"]}，本份实体归你持有。' if row['reward'] else '取得镜律规律记录，不重复发放机缘。'))


def end_repair(game, status):
    get(game)['pact'].update(status=status, settled_at=game.heavens_state['runtime']['processed_years'])


def complete(deps, game, task, rng):
    mirror = get(game)
    action, chamber = task['action'], task['chamber']
    task['status'] = 'completed'
    if action == 'mirror_repair':
        end_repair(game, 'kept')
        open_chamber(game, 2)
        record(game, '镜阵修补完成，守护机关依约开放规律抄录；两处材料核心继续留在场域，约定不因离开或重访失效。')
    elif action == 'mirror_probe':
        mirror['probed'] = True
        record(game, '低耗试探证实：登记施术实付法力的 25% 留在镜阵，隔断可停止对应联系；普通浏览与未关联消耗不被收集。')
    elif action == 'mirror_isolate':
        mirror['chambers'][chamber]['isolated'] = True
        record(game, f'第 {chamber+1} 处镜阵联系已隔断；已完成的遭遇快照与施力记录不撤销。')
    elif action == 'mirror_decipher':
        open_chamber(game, chamber)
    elif action == 'mirror_assault':
        row = mirror['chambers'][chamber]
        if row['guardian'] is None:
            mana = 0.0 if row['isolated'] else mirror['stored_mana']
            mirror['stored_mana'] -= mana
            bonus = mirror['definition']['strength_cap'] * mana/max(1.0, mirror['mana_capacity'])
            row['guardian'] = dict(mana=mana, power=mirror['definition']['guardian_power'] * (1+bonus),
                                   wounds=0, encounters=0, result=None)
        guardian = row['guardian']
        before = game.player.mp
        outcome, summary, wounds = deps.fight_mirror(game, mirror, chamber, rng)
        guardian.update(wounds=wounds, encounters=guardian['encounters']+1, result=outcome)
        collect(mirror, max(0.0, before-game.player.mp), chamber)
        record(game, f'镜律第 {chamber+1} 处强攻：{summary}')
        if outcome == 'victory':
            open_chamber(game, chamber)


def project(deps, game):
    mirror = get(game)
    facts = deps.read_mirror_facts(game)
    known = bool(mirror and mirror.get('player_known', True))
    value = dict(id=MIRROR_ID, name='镜律场域', entry='人界 · 穆陵沙漠', inside=facts['inside'],
                 known=known, probed=bool(known and mirror['probed']), actions=[],
                 description='镜纹随施术明灭，三处机关共享有限供给。入口保留退路；每处所得只归属一次。',
                 materials=deps.quote_materials(game, MIRROR_ID))
    candidates = [('mirror_leave' if facts['inside'] else 'mirror_enter', {})]
    if known:
        value['pact'] = copy.deepcopy(mirror.get('pact'))
        value.update(capacity_pending=mirror.get('capacity_pending', False), record_acquired=mirror['record_acquired'], traces=copy.deepcopy(mirror['traces']),
                     chambers=[dict(index=i, opened=row['opened'], isolated=row['isolated'],
                         guardian=copy.deepcopy(row['guardian']),
                         reward=row['reward']['name'] if row['opened'] and row['reward'] else None)
                         for i, row in enumerate(mirror['chambers'])])
        if mirror['probed']:
            value.update(stored_mana=mirror['stored_mana'], collected_mana=mirror['collected_mana'],
                         mana_capacity=mirror['mana_capacity'])
        if facts['inside']:
            candidates.append(('mirror_probe', {}))
            candidates.extend([('mirror_repair', {'material_id': value['materials'][0]['id']} if value['materials'] else {}), ('mirror_release', {})])
            for i in range(3):
                candidates.extend((action, dict(chamber=str(i), **({'material_id': value['materials'][0]['id']} if action == 'mirror_isolate' and value['materials'] else {})))
                                  for action in ('mirror_decipher', 'mirror_isolate', 'mirror_assault'))
    for action, options in candidates:
        row = dict(action=action, target_id=MIRROR_ID, label=LABELS[action], options=options)
        try:
            row.update(quote(deps, game, action, MIRROR_ID, options), enabled=True)
        except ValueError as exc:
            row.update(enabled=False, reason=str(exc))
        value['actions'].append(row)
    return value
