"""Local personal actions and evidence-only military presentation."""
import copy

from . import campaign
from .campaign_definitions import (CAMPAIGN_ID, CAMPAIGN_ACTIONS, LABELS, DURATIONS, SOURCE,
                                  TARGET_SITE, REPORT_SITE, AID_BUDGET, BUILD_YEARS)
from .campaign_logistics import located, retreat
from .state import active_task


def handles(runtime, action, target):
    task = active_task(runtime) if runtime else None
    return action in CAMPAIGN_ACTIONS or bool(action in {'resume', 'cancel'} and task
                    and task['id'] == target and task.get('target_id') == CAMPAIGN_ID)


def guards(deps, game):
    row = campaign.get(game)
    return [u for u in row['units'] if u['faction_id'] == SOURCE and u['phase'] == 'stationed'
            and located(deps, game, u, 'human', TARGET_SITE)] if row else []


def task_reason(deps, game, task):
    action = task['action']
    location = REPORT_SITE if action in {'campaign_report', 'campaign_aid', 'campaign_collect', 'campaign_decline'} else None if action == 'campaign_wait' else TARGET_SITE
    reason = deps.frontier_player_reason(game, location)
    if reason:
        return reason
    row = campaign.get(game)
    if not row:
        return '尚未收到军事施工情报'
    if action in {'campaign_assault', 'campaign_capture'}:
        actual = guards(deps, game)
        if not actual or task.get('person_id') and task['person_id'] not in {u['person_id'] for u in actual}:
            return '原对手已离开或受控，不能隔空完成交锋'
    if action == 'campaign_sabotage':
        if guards(deps, game):
            return '须先处理目标端实际守卫'
        if row['gate']['state'] == 'destroyed' or not row['gate']['target_progress']:
            return '当地没有可拆除的界门设施'
    if action == 'campaign_collect' and (not row['aid'] or row['aid']['status'] != 'arrived'):
        return '援助物资尚未实际抵达无棣原，或已经交付'
    return None


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    row, task = campaign.get(game), active_task(runtime) if runtime else None
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target or task.get('target_id') != CAMPAIGN_ID:
            raise ValueError('当前军情任务已经结束')
        if action == 'resume' and (reason := task_reason(deps, game, task)):
            raise ValueError(reason)
        return dict(years=task['duration']-task['progress'] if action == 'resume' else 0, costs={}, refundable={})
    if target != CAMPAIGN_ID or action not in CAMPAIGN_ACTIONS:
        raise ValueError('未知局部军事行动')
    if task:
        raise ValueError('请先结束当前亲自任务')
    if reason := task_reason(deps, game, dict(action=action)):
        raise ValueError(reason)
    if action not in {'campaign_wait', 'campaign_scout'} and not row['known']:
        raise ValueError('须先取得实际预警或亲自查勘')
    if action == 'campaign_report' and row['defense_requested']:
        raise ValueError('已递交过此次守备请求')
    if action in {'campaign_aid', 'campaign_decline'}:
        if not row['defense_requested']:
            raise ValueError('须先递交真实守备报告')
        if row['aid'] is not None:
            raise ValueError('本次有限援助已经作出选择，不会刷新物资')
    return dict(years=DURATIONS[action], costs={}, refundable={},
                message='仅在实际所在地执行个人行动。击退不等于占领；援助不附带军队指挥权。',
                warning='这是实际交锋，可能负伤、受控或陨落。' if action in {'campaign_assault', 'campaign_capture'} else '')


def execute(deps, game, action, target, options, proposal, *, run_task, cancel_task, task_result):
    runtime = game.heavens_state['runtime']
    if action == 'campaign_decline':
        complete(deps, game, {'action': action}, None)
        return {'message': '已婉拒本次援助'}
    if action in {'resume', 'cancel'}:
        task = active_task(runtime)
        if action == 'cancel':
            cancel_task(deps, game, task)
            return task_result(task)
    else:
        opponent = guards(deps, game)[-1]['person_id'] if action in {'campaign_assault', 'campaign_capture'} else None
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, target_id=CAMPAIGN_ID,
                    status='reserved', cycle=0, progress=0, duration=proposal['years'], person_id=opponent,
                    escrow=dict(total=0, spent=0, refunded=0, material=None, mp_paid=0))
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:]+[task]
    run_task(deps, game, task)
    return task_result(task)


def complete(deps, game, task, rng):
    row = campaign.get(game)
    now, action = game.heavens_state['runtime']['processed_years'], task['action']
    task['status'] = 'completed'
    if action == 'campaign_scout':
        row['surveyed'] = True
        for unit in row['units']:
            if located(deps, game, unit, 'human', TARGET_SITE):
                unit['observed'] = True
        state = {'planned': '人员尚未施工', 'building': '仍在施工', 'open': '已经稳定输送',
                 'interrupted': '已中断', 'destroyed': '已拆毁'}[row['gate']['state']]
        campaign.report(game, 'survey', f'你在岚疆亲自查明：目标端界门{state}。此记录只代表本次现场见闻。', now)
    elif action == 'campaign_report':
        row['defense_requested'] = True
        campaign.request_defense(deps, game, now)
        campaign.report(game, 'defense', '天剑宗已收到守备请求，' + ('批准一位门人循本界道路护守岚疆。玩家未获征发全宗的权限。' if row['defense']['status'] == 'approved' else '现有权限或可用人物不足，未派出守军。'), now)
    elif action in {'campaign_assault', 'campaign_capture'}:
        result, summary = deps.campaign_fight(game, task['person_id'], action == 'campaign_capture', rng)
        unit = next(u for u in row['units'] if u['person_id'] == task['person_id'])
        facts = deps.campaign_facts(game, unit)
        unit['observed'] = True
        if not facts['alive']:
            phase_name = 'lost'
            unit.update(phase=phase_name, progress=0, duration=0)
        elif facts['free'] and result in {'victory', 'victory_escape', 'killed'}:
            retreat(unit, facts)
        if unit['role'] == 'builder' and (unit['phase'] != 'stationed' or not facts['free']):
            campaign.withdraw(row, '目标端阵师已败退或受控，结束此次建设')
        campaign.report(game, 'personal_battle', summary[:1200], now)
    elif action == 'campaign_sabotage':
        row['gate'].update(state='destroyed', stability=0)
        row['materials']['target']['owner'] = 'spent'
        campaign.withdraw(row, '目标端界门已被实际拆除，停止增援并按有限路线撤离')
        campaign.report(game, 'demolition', '你拆除了岚疆目标端界门。未抵达输送停止，在界人物仍须实际撤走；个人拆门没有转移地区归属。', now)
    elif action == 'campaign_aid':
        campaign.request_aid(deps, game, now)
    elif action == 'campaign_collect':
        aid = row['aid']
        game.player.formation_materials.append(copy.deepcopy(aid['material']))
        aid.update(status='claimed', owner='player')
        campaign.report(game, 'aid_delivery', '你在无棣原接收了实际到达的灵界阵材，唯一物权已转交，可按本体阵法规则使用。', now)
    elif action == 'campaign_decline':
        row['aid'] = dict(status='declined', authorization=None, material=None, progress=0, duration=16,
                          spent=0, refunded=AID_BUDGET, owner='donor', last_year=now,
                          notice_progress=0, notice_delivered=False)
        campaign.report(game, 'aid', '你婉拒了此次有限物资援助；不会因此获得另一份储备或替代援军。', now)


def project(deps, game):
    row = campaign.get(game)
    visible = bool(row and row['known'])
    result = dict(id=CAMPAIGN_ID, name='岚疆界门', known=visible, reports=[], actions=[], local=False)
    if not visible:
        return result
    result['reports'] = copy.deepcopy(row['reports'])
    result['local'] = campaign.local(deps, game, TARGET_SITE)
    if result['local'] and row['surveyed']:
        result['gate'] = dict(state=row['gate']['state'], target_progress=row['gate']['target_progress'],
                              duration=BUILD_YEARS, stability=row['gate']['stability'])
        result['people'] = [dict(id=u['person_id'], name=deps.campaign_facts(game, u)['name'],
                                side='守备' if u['faction_id'] != SOURCE else '来犯')
                            for u in row['units'] if u['observed'] and located(deps, game, u, 'human', TARGET_SITE)]
    if row['aid']:
        # Public application facts are kept; distant transport clocks and offices are not.
        aid = row['aid']
        result['aid'] = dict(requested=True, collected=aid['status'] == 'claimed',
                            available=aid['status'] == 'arrived' and campaign.local(deps, game, REPORT_SITE),
                            refused=aid['status'] == 'declined', cancelled=aid['notice_delivered'])
    for action, label in LABELS.items():
        item = dict(action=action, target_id=CAMPAIGN_ID, label=label, options={})
        try:
            item.update(quote(deps, game, action, CAMPAIGN_ID, {}), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    return result

