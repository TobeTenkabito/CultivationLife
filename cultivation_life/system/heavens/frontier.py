"""One bounded reconnaissance expedition, with separate facts and local reports."""
import copy

from .frontier_definitions import (FRONTIER_ID, FRONTIER_ACTIONS, LABELS, DURATIONS, ROUTE,
                                   SOURCE_FACTION, INITIAL_RESERVE, ANNUAL_COST, SCOUT_YEARS, MANDATE_YEARS)
from .state import active_task, record


def get(game):
    return game.heavens_state.get('runtime', {}).get('frontier')


def handles(runtime, action, target):
    task = active_task(runtime) if runtime else None
    return action in FRONTIER_ACTIONS or (action in {'resume', 'cancel'} and task
        and task['id'] == target and task['target_id'] == FRONTIER_ID)


def report(game, kind, text, year):
    row = get(game)
    if any(r['kind'] == kind for r in row['reports']):
        return
    row['reports'].append(dict(kind=kind, year=year, text=text))
    record(game, text, year=year)
    if kind == 'sighting':
        runtime = game.heavens_state['runtime']
        runtime['notifications'] = (runtime['notifications'] + [dict(id=FRONTIER_ID, text=text, expires_at=year+120)])[-3:]
        if game.heavens_state['watch'] and runtime['pause_on_opportunity']:
            runtime['pause_requested'] = True


def phase(row, name, duration):
    row.update(phase=name, progress=0, duration=duration, reason=None)


def close(game, outcome, year, *, communicate=False):
    row = get(game)
    row['budget']['refunded'] = INITIAL_RESERVE-row['budget']['spent']
    row.update(status=outcome, phase='closed', progress=0, duration=0)
    if row['source_evidence'] is None:
        report(game, 'inquiry', '问讯已终止，尚未向对方送出返程位置；此份登记不会重新派遣人物。', year)
    if communicate:
        report(game, 'reply', '阵眼回讯：此次有限勘察已经结清，未取得建设界门或输送军队的许可。', year)


def together(deps, game):
    row = get(game)
    npc = deps.resolve_person(game, row['person_id']) if row and row['person_id'] else None
    return bool(npc and npc.alive and row['status'] == 'active' and row['phase'] == 'scouting'
                and not deps.frontier_player_reason(game, ROUTE.destination_location)
                and not deps.frontier_route_reason(game, row, 'scouting'))


def task_reason(deps, game, task):
    action = task['action']
    location = 'wudi_plain' if action in {'frontier_inquire', 'frontier_report'} else ROUTE.destination_location if action in {'frontier_scout', 'frontier_parley'} else None
    reason = deps.frontier_player_reason(game, location)
    if reason:
        return reason
    if action == 'frontier_inquire' and game.heavens_state['runtime'].get('ruins', {}).get('ward', {}).get('component') is None:
        return '关联阵眼尚未恢复，不能递送问讯'
    if action in {'frontier_scout', 'frontier_parley'} and not together(deps, game):
        return '先遣已离开或不能接触，不能隔空完成现场行动'
    if action == 'frontier_parley' and game.heavens_state['runtime']['ruins']['ward']['component'] is None:
        return '关联阵眼尚未恢复，无法出示修复凭据'
    return None


def quote(deps, game, action, target, options):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        raise ValueError('请先启用诸天联系')
    row, task = get(game), active_task(runtime)
    if action in {'resume', 'cancel'}:
        if not task or task['id'] != target or task['target_id'] != FRONTIER_ID:
            raise ValueError('边情任务已经结束')
        if action == 'resume' and (reason := task_reason(deps, game, task)):
            raise ValueError(reason)
        return dict(years=task['duration']-task['progress'] if action == 'resume' else 0, costs={}, refundable={})
    if target != FRONTIER_ID or action not in FRONTIER_ACTIONS:
        raise ValueError('未知边情行动')
    if task:
        raise ValueError('请先完成或取消当前亲自任务')
    if reason := task_reason(deps, game, {'action': action}):
        raise ValueError(reason)
    if action == 'frontier_inquire':
        ruins = runtime.get('ruins', {})
        if row:
            raise ValueError('本次问讯仅可递送一次，不会刷新先遣或储备')
        if not game.heavens_state['generation_enabled'] or not deps.get_definitions().generation_available:
            raise ValueError('尚未允许生成新的诸天联系')
        if not ruins.get('contact_known') or 'ruins_contact' not in ruins.get('sent_records', {}):
            raise ValueError('须先查明因果遗址接触点，并等待阵眼送出接触记录')
        if not 4 <= game.player.realm_index <= 8 or game.player.sealed_cultivation or game.player.cultivation_suppression:
            raise ValueError('问讯须具备未封限的四至八阶修为')
    elif not row:
        raise ValueError('尚未登记此地边情')
    elif action == 'frontier_scout' and row['observed']:
        raise ValueError('已保存当面查得的身份与任务，不重复发放成果')
    elif action in {'frontier_report', 'frontier_parley'} and not row['observed']:
        raise ValueError('须先在岚疆当面查明来者身份')
    elif action == 'frontier_report' and row['reported']:
        raise ValueError('已向当地递交警讯')
    return dict(years=DURATIONS[action], costs={}, refundable={},
                warning='问讯将主动送出无棣原的回程位置。对方须另行批准一人勘察；可能拒绝，不会直接开战。' if action == 'frontier_inquire' else '',
                message='此行动仅代表个人，不授予征兵、军事建设或全界停战权。')


def execute(deps, game, action, target, options, proposal, *, run_task, cancel_task, task_result):
    runtime = game.heavens_state['runtime']
    if action in {'resume', 'cancel'}:
        task = active_task(runtime)
        if action == 'cancel':
            cancel_task(deps, game, task)
            return task_result(task)
    else:
        if action == 'frontier_inquire':
            runtime['frontier'] = dict(id=FRONTIER_ID, revision=1, created_at=runtime['processed_years'],
                last_year=runtime['processed_years'], status='inquiry', phase='inquiry', progress=0, duration=0,
                person_id=None, home=None, road=[], road_years=0, authorization=None,
                budget=dict(owner=SOURCE_FACTION, total=INITIAL_RESERVE, spent=0, refunded=0),
                source_evidence=None, withdrawal=False, reason=None, observed=False, reported=False, reports=[])
            game.heavens_state['definition_versions'][FRONTIER_ID] = 1
        task = dict(id=f'heavens-task-{runtime["next_task_seq"]}', action=action, target_id=FRONTIER_ID,
                    status='reserved', cycle=0, progress=0, duration=proposal['years'], person_id=None,
                    escrow=dict(total=0, spent=0, refunded=0, material=None, mp_paid=0))
        runtime['next_task_seq'] += 1
        runtime['tasks'] = runtime['tasks'][-3:]+[task]
    run_task(deps, game, task)
    return task_result(task)


def complete(deps, game, task):
    row, now = get(game), game.heavens_state['runtime']['processed_years']
    action = task['action']
    task['status'] = 'completed'
    if action == 'frontier_inquire':
        row['source_evidence'] = dict(source='causal_ruins', world='human', location='wudi_plain', sent_at=now)
        row.update(status='active', phase='review')
        report(game, 'inquiry', '你经因果阵眼递送问讯，留下无棣原回程位置；是否派人须由接收方自行决定。', now)
    elif action == 'frontier_scout':
        row['observed'] = True
        npc = deps.resolve_person(game, row['person_id'])
        npc.encountered_player = True
        report(game, 'identity', f'你当面核实了{npc.name}的血狱魔宗先遣身份：此行只获准调查阵眼与落点，尚无施工或增援许可。', now)
    elif action == 'frontier_report':
        row['reported'] = True
        report(game, 'reported', '你在无棣原公开递交了亲历警讯；当地修士可以据此避让，未因此被征入任何军队。', now)
    elif action == 'frontier_parley':
        row['withdrawal'] = True
        phase(row, 'returning', ROUTE.crossing_years)
        report(game, 'agreement', '先遣验明阵眼恢复，接受结束本次勘察；本人仍须经原路实际返乡，不代表双方宗门签订停战。', now)


def year_step(deps, game):
    row = get(game)
    if not row or row['status'] != 'active':
        return
    now = game.heavens_state['runtime']['processed_years']+1
    if now <= row['last_year']:
        return
    row['last_year'] = now
    if row['phase'] == 'review':
        candidate = deps.frontier_candidate(game)
        if not candidate or ANNUAL_COST*(2*candidate['road_years']+2*ROUTE.crossing_years+SCOUT_YEARS+2) > INITIAL_RESERVE:
            phase(row, 'reply', 2)
            row['reason'] = '缺少有效批准者、可用人物、道路或专项预算；拒绝派遣'
            return
        row.update({k: candidate[k] for k in ('person_id', 'home', 'road', 'road_years')})
        row['authorization'] = dict(**candidate['authority'], granted_at=now, expires_at=now+MANDATE_YEARS,
                                    route_id=ROUTE.id, capacity=1, purpose='inspect_linked_ward')
        deps.frontier_deploy(game, row['person_id'], row['home'])
        phase(row, 'gathering' if row['road_years'] else 'outbound', row['road_years'] or ROUTE.crossing_years)
        return
    if row['phase'] == 'reply':
        row['progress'] += 1
        if row['progress'] >= row['duration']:
            close(game, 'completed' if row['person_id'] else 'declined', now, communicate=True)
        return
    npc = deps.resolve_person(game, row['person_id'])
    if not npc or not npc.alive:
        close(game, 'failed', now)
        return
    if npc.realm_index > ROUTE.maximum_realm or npc.world not in {'human', 'demon'}:
        row['reason'] = '人物成长或迁界后不再适用此次有限部署；保留真实人物与所在界面'
        close(game, 'failed', now)
        return
    authorization = deps.frontier_authority(game)
    if (not authorization or authorization['issuer_id'] != row['authorization']['issuer_id']
            or now > row['authorization']['expires_at']):
        row['withdrawal'] = True
    if row['withdrawal'] and row['phase'] in {'gathering', 'outbound', 'scouting'}:
        if npc.world == 'human':
            phase(row, 'returning', ROUTE.crossing_years)
        elif npc.location_id == row['home']:
            phase(row, 'reply', 2)
            return
        else:
            phase(row, 'homeward' if row['road_years'] else 'reply', row['road_years'] or 2)
    if row['phase'] == 'reply':
        return
    row['reason'] = deps.frontier_route_reason(game, row, row['phase'])
    if row['reason']:
        return
    if together(deps, game):
        report(game, 'sighting', '你在岚疆草原亲见一名异界先遣；可以查明来意、离开当地，或递交警讯。', now)
    row['progress'] += 1
    row['budget']['spent'] += ANNUAL_COST
    if row['progress'] < row['duration']:
        return
    if row['phase'] == 'gathering':
        deps.frontier_move(game, row, 'demon', ROUTE.source_location)
        phase(row, 'outbound', ROUTE.crossing_years)
    elif row['phase'] == 'outbound':
        deps.frontier_move(game, row, 'human', ROUTE.destination_location)
        phase(row, 'scouting', SCOUT_YEARS)
        if together(deps, game):
            report(game, 'sighting', '你在岚疆草原亲见一名异界先遣；可以查明来意、离开当地，或递交警讯。', now)
    elif row['phase'] == 'scouting':
        row['landing_evidence'] = dict(world='human', location=ROUTE.destination_location, observer_id=row['person_id'], surveyed_at=now)
        phase(row, 'returning', ROUTE.crossing_years)
    elif row['phase'] == 'returning':
        deps.frontier_move(game, row, 'demon', ROUTE.source_location)
        phase(row, 'homeward' if row['road_years'] else 'reply', row['road_years'] or 2)
    elif row['phase'] == 'homeward':
        deps.frontier_move(game, row, 'demon', row['home'])
        phase(row, 'reply', 2)


def project(deps, game):
    row = get(game)
    result = dict(id=FRONTIER_ID, name='岚疆边情', known=bool(row), reports=[], actions=[])
    if row:
        result.update(reports=copy.deepcopy(row['reports']), observed=row['observed'], reported=row['reported'],
                      local=together(deps, game))
        if row['observed']:
            npc = deps.resolve_person(game, row['person_id'])
            result['person'] = dict(id=row['person_id'], name=npc.name if npc else '已登记先遣')
    for action in LABELS:
        item = dict(action=action, target_id=FRONTIER_ID, label=LABELS[action], options={})
        try:
            item.update(quote(deps, game, action, FRONTIER_ID, {}), enabled=True)
        except ValueError as exc:
            item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    return result
