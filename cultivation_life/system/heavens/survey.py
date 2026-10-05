"""One real resident surveys a known ruin using its existing isolated clock."""
from .definitions import RUINS_ID, SURVEY_ACTIONS
from .state import active_task, record

LABELS = {'survey_start': '邀约勘察', 'survey_recall': '结束勘察', 'survey_share': '交换勘察笔记', 'survey_wait': '等候一年'}
DURATIONS = {'outbound': 2, 'studying': 8, 'returning': 1}


def get(game):
    return game.heavens_state.get('runtime', {}).get('ruins', {}).get('survey')


def handles(runtime, action, target):
    task = active_task(runtime) if runtime else None
    return action in SURVEY_ACTIONS or (action in {'resume', 'cancel'} and task and task['id'] == target and task['action'] == 'survey_wait')


def actor_reason(deps, game):
    facts = deps.read_ruins_facts(game)
    return facts['blocked_reason'] or facts['activity_reason'] or (None if facts['inside'] else facts['entry_reason'])


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    scene = runtime.get('ruins') if runtime else None
    row = get(game)
    task = active_task(runtime) if runtime else None
    if action in {'resume', 'cancel'}:
        if action == 'resume' and actor_reason(deps, game):
            raise ValueError(actor_reason(deps, game))
        return dict(years=1-task['progress'] if action == 'resume' else 0, costs={}, refundable={})
    if target != RUINS_ID or not scene:
        raise ValueError('须先亲自发现因果遗址，再在无棣原邀约')
    reason = actor_reason(deps, game)
    if reason or task:
        raise ValueError(reason or '请先完成或取消当前亲自任务')
    if action == 'survey_wait':
        if not row or row['status'] != 'active':
            raise ValueError('暂无进行中的勘察')
        inside = deps.read_ruins_facts(game)['inside']
        if row['phase'] == 'outbound':
            message = '经过一个空间年；外界赴约冻结，须先退出遗址才能继续赴约。' if inside else '经过一个外界年；本人符合条件时继续赴约。'
        else:
            message = '经过一个遗址空间年；本人符合条件时继续勘察或退出。' if inside else '本次只经过外界一年，遗址内部冻结；须进入同一遗址继续勘察。'
        return dict(years=1, costs={}, refundable={}, message=message)
    if action == 'survey_start':
        if row:
            raise ValueError('每座遗址仅安排一次居民勘察')
        if deps.read_ruins_facts(game)['inside']:
            raise ValueError('须先返回人界无棣原发出邀约')
        identity = options.get('person_id')
        if identity not in {p['id'] for p in deps.survey_candidates(game)}:
            raise ValueError('须选择人界自由、无其他职责、交情至少 20 的四至五阶居民')
        return dict(years=0, costs={}, refundable={}, message='本人先花 2 个外界年赴约入场，再按遗址空间年度观察 2 年、抄录 6 年、退出 1 年。只调查抄本，不取阵芯或阵材。',
            warning='你离开遗址时内部年度冻结，外界往来不补算。人物会真实衰老或陨落；笔记须在实际会面时交换，可将玩家后续读取由 6 年缩短为 3 年。')
    if not row:
        raise ValueError('尚无勘察人物')
    facts = deps.read_survey_facts(game)
    if facts['blocked_reason'] and not (action == 'survey_recall' and row['status'] == 'active' and row['phase'] == 'outbound'):
        raise ValueError(facts['blocked_reason'])
    if action == 'survey_share':
        if not row['learned'] or row['shared']:
            raise ValueError('尚无新的完整笔记可交换')
        if not facts['together']:
            raise ValueError('须在遗址内或退出地点与本人实际会面')
        return dict(years=0, costs={}, refundable={}, message='交换本人合法抄录，后续亲自读取只需 3 年；唯一阵材仍由玩家实际完成读取后领取，不额外发奖。')
    if row['status'] != 'active' or row['phase'] == 'returning':
        raise ValueError('勘察已结束或本人正在退出')
    if row['phase'] != 'outbound' and not facts['together']:
        raise ValueError('须进入同一遗址当面提出结束，不能隔空召回')
    return dict(years=0, costs={}, refundable={}, message='未入场则撤销后续邀约；已入场则花一个实际空间年原路退出，不瞬移人物。')


def execute(deps, game, action, target, options, *, run_task, cancel_task, task_result):
    runtime = game.heavens_state['runtime']
    if action in {'resume', 'cancel'}:
        task = active_task(runtime)
        (run_task if action == 'resume' else cancel_task)(deps, game, task)
        return task_result(task)
    row = get(game)
    if action == 'survey_wait':
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, target_id=RUINS_ID, status='reserved',
                    cycle=0, progress=0, duration=1, person_id=None,
                    escrow=dict(total=0, spent=0, refunded=0, mp_paid=0, material=None))
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:]+[task]
        run_task(deps, game, task)
        return task_result(task)
    if action == 'survey_start':
        npc = deps.resolve_person(game, options['person_id'])
        runtime['ruins']['survey'] = dict(person_id=npc.id, origin_location=npc.location_id,
            status='active', phase='outbound', progress=0, elapsed=0, observed=False, learned=False, shared=False,
            started_at=runtime['processed_years'], last_year=runtime['processed_years'])
        record(game, f'{npc.name}接受遗址勘察邀约，开始由人界赴约；不取用阵芯与预留阵材。')
    elif action == 'survey_share':
        row['shared'] = True
        record(game, '已当面交换勘察笔记；下一项亲自读取可减少三年核对工时，材料归属不变。')
    elif row['phase'] == 'outbound':
        row['status'] = 'cancelled'
        record(game, '赴约尚未完成，余下勘察已撤销；本人仍在原人界位置。')
    else:
        row.update(phase='returning', progress=0)
        record(game, '勘察人物停止后续抄录，准备花一个空间年沿原路退出。')
    return {'message': '遗址勘察安排已更新'}


def year_step(deps, game, *, outside):
    row = get(game)
    if not row or row['status'] != 'active' or (row['phase'] == 'outbound') != outside:
        return
    runtime = game.heavens_state['runtime']
    year = runtime['processed_years']+int(outside)
    if row['last_year'] >= year:
        return
    if not outside and not deps.read_ruins_facts(game)['inside']:
        return
    row['last_year'] = year
    facts = deps.read_survey_facts(game)
    if not facts['alive']:
        row['status'] = 'failed'
        record(game, '勘察人物已经陨落，邀约终止；不复活或生成替代人物。', year=year)
        return
    if facts['blocked_reason']:
        return
    row['progress'] += 1
    row['elapsed'] += 1
    if row['phase'] == 'studying':
        row['observed'] = row['progress'] >= 2
        if row['progress'] == 8:
            row.update(learned=True, phase='returning', progress=0)
            record(game, '勘察人物完成自己的抄录，准备原路退出；玩家尚未自动获得这些笔记。', year=year)
    elif row['progress'] == DURATIONS[row['phase']]:
        deps.move_surveyor(game, row['phase'])
        if outside:
            row.update(phase='studying', progress=0)
            record(game, '原居民已经赴约并进入同一因果遗址，后续研究只由该空间年度推进。', year=year)
        else:
            row['status'] = 'completed'
            record(game, '勘察人物已沿稳定入口退出到人界无棣原，所学与本人经历保留。', year=year)


def project(deps, game):
    row = get(game)
    result = dict(status=row['status'] if row else 'unavailable', actions=[], candidates=[])
    if row:
        npc = deps.resolve_person(game, row['person_id'])
        result.update(row, name=npc.name if npc else '原勘察人物', duration=DURATIONS[row['phase']],
                      blocked_reason=deps.read_survey_facts(game)['blocked_reason'])
    elif not deps.read_ruins_facts(game)['entry_reason']:
        result['candidates'] = deps.survey_candidates(game)
    for action, label in LABELS.items():
        options = {'person_id': result['candidates'][0]['id']} if action == 'survey_start' and result['candidates'] else {}
        item = dict(action=action, target_id=RUINS_ID, label=label, options=options)
        try:
            item.update(quote(deps, game, action, RUINS_ID, options), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    return result
