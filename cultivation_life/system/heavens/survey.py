"""Bounded resident surveys share the authoritative clock of each anomaly."""
from .definitions import RUINS_ID, MIRROR_ID, SURVEY_ACTIONS
from .state import active_task, record

LABELS = {'survey_start': '邀约勘察', 'survey_recall': '结束勘察', 'survey_share': '交换勘察笔记', 'survey_wait': '等候一年'}
DURATIONS = {'outbound': 2, 'studying': 8, 'returning': 1}
SITES = {RUINS_ID: ('ruins', '因果遗址', '无棣原'), MIRROR_ID: ('mirror', '镜律场域', '穆陵沙漠')}


def scene_for(game, target=RUINS_ID):
    return game.heavens_state.get('runtime', {}).get(SITES[target][0])


def get(game, target=RUINS_ID):
    return (scene_for(game, target) or {}).get('survey')


def occupied(game):
    return any(get(game, target) and get(game, target)['status'] == 'active' for target in SITES)


def player_facts(deps, game, target):
    return (deps.read_mirror_facts if target == MIRROR_ID else deps.read_ruins_facts)(game)


def benefit(target):
    return ('后续镜律破解由 4 年缩短为 2 年；仍须亲自试探并实付法力，每处机关所得归属不变。'
            if target == MIRROR_ID else '后续亲自读取由 6 年缩短为 3 年；唯一阵材仍须本人读取后领取。')


def assignment(npc, year):
    return dict(person_id=npc.id, origin_location=npc.location_id,
                status='active', phase='outbound', progress=0, elapsed=0,
                observed=False, learned=False, shared=False, started_at=year, last_year=year)


def known(row):
    return not row.get('autonomous') or row['introduced']


def reveal(deps, game, *, year=None, target=RUINS_ID):
    row = get(game, target)
    if not row or known(row) or player_facts(deps, game, target)['blocked_reason']:
        return
    facts = deps.read_survey_facts(game, target=target)
    if not facts['blocked_reason'] and facts['together']:
        row['introduced'] = True
        scene_for(game, target)['player_known'] = True
        npc = deps.resolve_person(game, row['person_id'])
        record(game, f'你实际遇到自行探访{SITES[target][1]}的{npc.name}。对方正沿旧路求证；所见笔记须当面商谈，不能隔空指挥。', year=year)


def record_known(game, text, *, year, target=RUINS_ID):
    if known(get(game, target)):
        record(game, text, year=year)


def handles(runtime, action, target):
    task = active_task(runtime) if runtime else None
    return action in SURVEY_ACTIONS or (action in {'resume', 'cancel'} and task and task['id'] == target and task['action'] == 'survey_wait')


def actor_reason(deps, game, target=RUINS_ID):
    facts = player_facts(deps, game, target)
    return facts['blocked_reason'] or facts['activity_reason'] or (None if facts['inside'] else facts['entry_reason'])


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    scene = scene_for(game, target) if target in SITES else None
    task = active_task(runtime) if runtime else None
    if action in {'resume', 'cancel'}:
        target = task['target_id']
    if target not in SITES:
        raise ValueError('未知勘察目标')
    row = get(game, target)
    if action in {'resume', 'cancel'}:
        if action == 'resume' and actor_reason(deps, game, target):
            raise ValueError(actor_reason(deps, game, target))
        return dict(years=1-task['progress'] if action == 'resume' else 0, costs={}, refundable={})
    if target not in SITES or not scene:
        raise ValueError('须先亲自发现对应异象，再返回入口邀约')
    reason = actor_reason(deps, game, target)
    if reason or task:
        raise ValueError(reason or '请先完成或取消当前亲自任务')
    if row and not known(row):
        raise ValueError('尚未实际接触可商谈的勘察人物，请在场域中留意来访者')
    if action == 'survey_wait':
        if not row or row['status'] != 'active':
            raise ValueError('暂无进行中的勘察')
        inside = player_facts(deps, game, target)['inside']
        if row['phase'] == 'outbound':
            message = '经过一个空间年；外界赴约冻结，须先退出场域才能继续赴约。' if inside else '经过一个外界年；本人符合条件时继续赴约。'
        else:
            message = '经过一个场域空间年；本人符合条件时继续勘察或退出。' if inside else '本次只经过外界一年，场域内部冻结；须进入同一场域继续勘察。'
        return dict(years=1, costs={}, refundable={}, message=message)
    if action == 'survey_start':
        if row or occupied(game):
            raise ValueError('每座异象仅安排一次居民勘察，且同时只能进行一项')
        if player_facts(deps, game, target)['inside']:
            raise ValueError(f'须先返回人界{SITES[target][2]}发出邀约')
        identity = options.get('person_id')
        if identity not in {p['id'] for p in deps.survey_candidates(game, target=target)}:
            raise ValueError('须选择人界自由、无其他职责、交情至少 20 的四至五阶居民')
        return dict(years=0, costs={}, refundable={}, message='本人先花 2 个外界年赴约入场，再按同一场域年度观察 2 年、整理笔记 6 年、退出 1 年。只观察纹路，不动机关、阵芯或阵材。',
            warning='你离开时内部年度冻结，外界往来不补算。人物会真实衰老或陨落；笔记须在实际会面时交换。'+benefit(target))
    if not row:
        raise ValueError('尚无勘察人物')
    facts = deps.read_survey_facts(game, target=target)
    if facts['blocked_reason'] and not (action == 'survey_recall' and row['status'] == 'active' and row['phase'] == 'outbound'):
        raise ValueError(facts['blocked_reason'])
    if row.get('autonomous') and action in {'survey_share', 'survey_recall'}:
        npc = deps.resolve_person(game, row['person_id'])
        if not facts['together']:
            raise ValueError('对方自行探访，须与本人实际会面后商谈')
        if (npc.affinity or 0) < 20:
            raise ValueError('对方自行探访，交换笔记或商请返程须交情至少 20；可在人际关系页当面交流')
    if action == 'survey_share':
        if not row['learned'] or row['shared']:
            raise ValueError('尚无新的完整笔记可交换')
        if not facts['together']:
            raise ValueError('须在场域内或退出地点与本人实际会面')
        return dict(years=0, costs={}, refundable={}, message='交换本人合法抄录。'+benefit(target))
    if row['status'] != 'active' or row['phase'] == 'returning':
        raise ValueError('勘察已结束或本人正在退出')
    if row['phase'] != 'outbound' and not facts['together']:
        raise ValueError('须进入同一场域当面提出结束，不能隔空召回')
    return dict(years=0, costs={}, refundable={}, message='未入场则撤销后续邀约；已入场则花一个实际空间年原路退出，不瞬移人物。')


def execute(deps, game, action, target, options, *, run_task, cancel_task, task_result):
    runtime = game.heavens_state['runtime']
    if action in {'resume', 'cancel'}:
        task = active_task(runtime)
        (run_task if action == 'resume' else cancel_task)(deps, game, task)
        return task_result(task)
    row = get(game, target)
    if action == 'survey_wait':
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, target_id=target, status='reserved',
                    cycle=0, progress=0, duration=1, person_id=None,
                    escrow=dict(total=0, spent=0, refunded=0, mp_paid=0, material=None))
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:]+[task]
        run_task(deps, game, task)
        return task_result(task)
    if action == 'survey_start':
        npc = deps.resolve_person(game, options['person_id'])
        scene_for(game, target)['survey'] = assignment(npc, runtime['processed_years'])
        record(game, f'{npc.name}接受{SITES[target][1]}勘察邀约，开始由人界赴约；不动机关与预留所得。')
    elif action == 'survey_share':
        row['shared'] = True
        record(game, '已当面交换勘察笔记；'+benefit(target))
    elif row['phase'] == 'outbound':
        row['status'] = 'cancelled'
        record(game, '赴约尚未完成，余下勘察已撤销；本人仍在原人界位置。')
    else:
        row.update(phase='returning', progress=0)
        record(game, '勘察人物停止后续抄录，准备花一个空间年沿原路退出。')
    return {'message': '异象勘察安排已更新'}


def year_step(deps, game, *, outside):
    for target in SITES:
        advance_one(deps, game, outside=outside, target=target)


def advance_one(deps, game, *, outside, target):
    row = get(game, target)
    year = game.heavens_state.get('runtime', {}).get('processed_years', 0)+int(outside)
    reveal(deps, game, year=year, target=target)
    if not row or row['status'] != 'active' or (row['phase'] == 'outbound') != outside:
        return
    runtime = game.heavens_state['runtime']
    if row['last_year'] >= year:
        return
    if not outside and not player_facts(deps, game, target)['inside']:
        return
    row['last_year'] = year
    facts = deps.read_survey_facts(game, target=target)
    if not facts['alive']:
        row['status'] = 'failed'
        record_known(game, '勘察人物已经陨落，勘察终止；不复活或生成替代人物。', year=year, target=target)
        return
    if facts['blocked_reason']:
        if row.get('autonomous') and row['phase'] == 'outbound' and facts['departure_lost']:
            row['status'] = 'cancelled'
            record_known(game, '探访者的原出发位置或人界修为资格已改变，本人结束旧路探访；保留实际所在，解除行程占用。', year=year, target=target)
        return
    row['progress'] += 1
    row['elapsed'] += 1
    if row['phase'] == 'studying':
        row['observed'] = row['progress'] >= 2
        if row['progress'] == 8:
            row.update(learned=True, phase='returning', progress=0)
            record_known(game, '勘察人物完成自己的抄录，准备原路退出；玩家尚未自动获得这些笔记。', year=year, target=target)
    elif row['progress'] == DURATIONS[row['phase']]:
        deps.move_surveyor(game, row['phase'], target=target)
        if outside:
            row.update(phase='studying', progress=0)
            record_known(game, f'原居民已经进入{SITES[target][1]}，后续研究只由该空间年度推进。', year=year, target=target)
        else:
            row['status'] = 'completed'
            record_known(game, f'勘察人物已沿稳定入口退出到人界{SITES[target][2]}，所学与本人经历保留。', year=year, target=target)


def project(deps, game, target=RUINS_ID):
    row = get(game, target)
    scene = scene_for(game, target)
    if not scene or not scene.get('player_known', True) or row and not known(row):
        return dict(status='unmet', actions=[], candidates=[])
    result = dict(status=row['status'] if row else 'unavailable', actions=[], candidates=[], benefit=benefit(target), exit=SITES[target][2])
    if row:
        npc = deps.resolve_person(game, row['person_id'])
        result.update(row, name=npc.name if npc else '原勘察人物', duration=DURATIONS[row['phase']],
                      blocked_reason=deps.read_survey_facts(game, target=target)['blocked_reason'],
                      affinity=npc.affinity if npc else None)
    elif not player_facts(deps, game, target)['entry_reason']:
        result['candidates'] = deps.survey_candidates(game, target=target)
    for action, label in LABELS.items():
        if row and row.get('autonomous') and action == 'survey_recall':
            label = '商请结束勘察'
        options = {'person_id': result['candidates'][0]['id']} if action == 'survey_start' and result['candidates'] else {}
        item = dict(action=action, target_id=target, label=label, options=options)
        try:
            item.update(quote(deps, game, action, target, options), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    return result
