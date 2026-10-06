"""Player mediation, named casualty relief and a real local evacuation road."""
from .campaign_definitions import SOURCE, DEFENDER, TARGET_SITE
from .settlement import valid_mandate, sign, treaty_active
from .settlement_definitions import LABELS, TREATY_NAMES
from .campaign_logistics import located, retreat


def patient(deps, game, row, *, captive=False, identity=None):
    state = row.get('settlement', {})
    for unit in row['units']:
        if identity is not None and unit['person_id'] != identity:
            continue
        facts = deps.campaign_facts(game, unit)
        if captive:
            if facts.get('held_by_player') and facts['alive'] and facts['location'] == TARGET_SITE:
                return unit
        elif (located(deps, game, unit, 'human', TARGET_SITE) and facts['wounds'] > 0
              and unit['person_id'] not in state.get('treated', [])
              and (unit['faction_id'] == DEFENDER or treaty_active(row) or row['status'] != 'active')):
            return unit
    return None


def reason(deps, game, row, task):
    action = task['action']
    if action not in LABELS:
        return None
    state = row.get('settlement')
    if not state:
        return '等待下一实际年度登记地方职责'
    if action == 'campaign_evacuate':
        plan = deps.campaign_escape_plan(game)
        if not plan or task.get('duration') and plan['years'] > task['duration']:
            return '原撤离道路已不可通行或工期发生变化，可取消后重新规划'
        return None
    if action in {'campaign_relief', 'campaign_release'}:
        target = patient(deps, game, row, captive=action == 'campaign_release', identity=task.get('person_id'))
        if not target:
            return '原伤员或俘虏已不在此地、已获救护或不受你控制'
        return None
    if state['treaty']:
        return '本案已订立一次协议，不能反复签约刷新期限'
    if row['status'] != 'active':
        return '军事部署已结束或正在撤回，可继续救护与撤离'
    now = game.heavens_state['runtime']['processed_years']
    for faction in (SOURCE, DEFENDER):
        mandate = state['mandates'].get(faction)
        if not mandate or not valid_mandate(deps, game, mandate, now):
            return '双方须各有现任权力主体事先批准的当地议约委任；不能代替宗门签署'
        unit = next(u for u in row['units'] if u['person_id'] == mandate['delegate_id'])
        if unit['phase'] != 'stationed' or not located(deps, game, unit, 'human', TARGET_SITE):
            return '双方具名代表须实际同处岚疆，返乡、远方或受控者不能签署'
    if action == 'campaign_withdrawal' and game.heavens_state['runtime']['ruins']['ward']['component'] is None:
        return '关联阵眼尚未实际修复，不能承诺虚假的修复凭据'
    if action == 'campaign_vassal' and (row['gate']['state'] != 'open' or row['supply']['target'] < 8):
        return '限期附约须有已开放的界门和至少八份当地补给'
    if action == 'campaign_vassal':
        guard = next(u for u in row['units'] if u['role'] == 'soldier')
        facts = deps.campaign_facts(game, guard)
        if guard['phase'] not in {'gathering', 'stationed', 'transport'} or not facts['free'] or facts['wounds'] >= 3:
            return '原驻军已失去履职条件，不能签署没有驻军的附约'
    return None


def complete(deps, game, row, task, now, withdraw, report):
    action = task['action']
    if action == 'campaign_evacuate':
        deps.campaign_escape(game)
        report(game, 'evacuation', f'你沿本界原有道路行进 {task["duration"]} 年，抵达无棣原；岚疆军政状态没有随你迁移。', now)
    elif action in {'campaign_relief', 'campaign_release'}:
        unit = next(u for u in row['units'] if u['person_id'] == task['person_id'])
        name = deps.campaign_facts(game, unit)['name']
        if action == 'campaign_release':
            deps.campaign_release(game, unit)
            retreat(unit, deps.campaign_facts(game, unit))
            text = f'你当面释放了原俘虏{name}，同一人物恢复自由后沿原许可返乡，未抹去伤势或生成替身。'
        else:
            deps.campaign_relief(game, unit)
            row['settlement']['treated'].append(unit['person_id'])
            text = f'你花两年救护{name}，减轻一重实际伤势；每位本案伤员只接受一次此项救护。'
        report(game, 'relief', text, now)
    else:
        kind = action.removeprefix('campaign_')
        sign(deps, game, row, kind, now, withdraw)
        report(game, 'treaty', f'你见证双方受委任代表订立「{TREATY_NAMES[kind]}」。文书仅及岚疆，人物去留仍按实际道路办理。', now)
