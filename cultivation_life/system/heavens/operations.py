"""Pure projections and isolated, single-document commands."""
from __future__ import annotations

import copy
import hashlib
import json

from .definitions import ACTIONS, VIEWS, HeavensDefinitions
from .dependencies import HeavensDependencies
from .schema import RECEIPT_LIMIT, initial_state, require_counter, validate_state, validate_references
from .state import initialize, phase
from . import tasks


def project(game, view: str, target_id: str | None = None, *, deps=None) -> dict:
    if not isinstance(view, str) or view not in VIEWS:
        raise ValueError('未知诸天视图')
    runtime = game.heavens_state.get('runtime')
    echo = runtime and runtime['sea_echo']
    if target_id is not None and (target_id != 'sea_echo' or not echo):
        raise ValueError('诸天对象不可见或不存在')
    validate_state(game.heavens_state)
    state = game.heavens_state or initial_state()
    # Never expose internal receipts, future objective facts or random states.
    result = dict(view=view, records=[], revision=state['revision'],
                next_command_seq=state['command_seq'] + 1,
                generation_enabled=state['generation_enabled'], watch=state['watch'],
                available_actions=['configure'], reason='启用后，可在仙界法则天海求证潮汐回响。')
    result['generation_available'] = bool(deps and deps.get_definitions().generation_available)
    result['pause_on_opportunity'] = bool(runtime and runtime['pause_on_opportunity'])
    if not runtime:
        return result
    result.update(year=runtime['processed_years'], tasks=copy.deepcopy(runtime['tasks']),
                  notifications=copy.deepcopy(runtime['notifications']) if state['watch'] else [],
                  history=copy.deepcopy(runtime['history']), unit_credit=copy.deepcopy(runtime['unit_credit']))
    if echo:
        cycle, offset, cutoff = phase(runtime, echo)
        person = deps.resolve_person(game, echo['visitor_id']) if deps else None
        result['echo'] = dict(id='sea_echo', name='法则天海 · 潮汐回响', cycle=cycle,
            origin_year=echo['origin_year'], remaining=max(0, cutoff-offset),
            next_cycle_in=echo['definition']['period_years']-offset,
            inscriptions=[echo['origin_year']-4000, echo['origin_year']-2000] if echo['history_checked'] else [],
            evidence=[label for label, acquired in [('E1 潮汐体察', echo['observed_cycle']==cycle),
                ('E2 接引碑旧记', echo['history_checked']), ('E3 因果天城合法抄录', echo['exchanged'])] if acquired],
            visitor=dict(id=echo['visitor_id'], name=person.name if person else '观澜散人',
                         available=bool(deps and deps.person_available(game, echo['visitor_id']))),
            application=copy.deepcopy(echo['application']), maintained=echo['maintained'],
            reward_claimed=echo['reward_claimed'], reward_base=echo['reward_base'],
            project_stones=echo['project_stones'])
    result['actions'] = []
    if deps:
        result['materials'] = deps.quote_materials(game)
        for action in ('observe', 'check_history', 'exchange', 'attune', 'maintain'):
            options = ({'person_id': echo['visitor_id']} if action=='exchange' and echo else
                       {'material_id': result['materials'][0]['id']} if action=='maintain' and result['materials'] else {})
            row = dict(action=action, label=tasks.LABELS[action], options=options)
            try:
                row.update(tasks.quote(deps, game, action, 'sea_echo', options), enabled=True)
            except ValueError as exc:
                row.update(enabled=False, reason=str(exc))
            result['actions'].append(row)
        result['available_actions'].extend(row['action'] for row in result['actions'] if row['enabled'])
        if tasks.active_task(runtime):
            result['available_actions'].extend(['resume', 'cancel'])
        elif echo and echo['application']:
            result['available_actions'].append('cancel')
        if runtime['notifications']:
            result['available_actions'].append('dismiss')
    result['records'] = ([result['echo']] if echo else []) if view in {'known','opportunities'} else result[view]
    return result


def plan(definitions: HeavensDefinitions, action: str, target_id, options) -> dict:
    if not isinstance(action, str) or action not in ACTIONS:
        raise ValueError('未知诸天动作')
    if action != 'configure':
        allowed = {'observe': set(), 'check_history': set(), 'exchange': {'person_id'},
                   'attune': set(), 'maintain': {'material_id'}, 'resume': set(), 'cancel': set(), 'dismiss': set()}
        if action not in allowed or not isinstance(target_id, str) or not target_id:
            raise ValueError('诸天动作或目标无效')
        if type(options) is not dict or set(options) != allowed[action] or any(not isinstance(v,str) or not v for v in options.values()):
            raise ValueError('诸天动作选项无效')
        return dict(action=action, target_id=target_id, options=dict(options))
    if target_id is not None:
        raise ValueError('诸天设置不接受目标对象')
    if type(options) is not dict or not options or set(options) - {'generation_enabled', 'watch', 'pause_on_opportunity'}:
        raise ValueError('诸天设置只接受生成开关和关注选项')
    if any(type(value) is not bool for value in options.values()):
        raise ValueError('诸天设置必须为布尔值')
    return dict(action=action, target_id=None, options=dict(options), years=0,
                costs={}, refundable={}, deadline=None)


def view(deps: HeavensDependencies, game_id: str, view: str, target_id=None) -> dict:
    return project(deps.load_game(game_id), view, target_id, deps=deps)


def preview(deps: HeavensDependencies, game_id: str, action: str, target_id, options) -> dict:
    game = deps.load_game(game_id)
    validate_state(game.heavens_state)
    result = plan(deps.get_definitions(), action, target_id, options)
    if action == 'configure':
        check_configuration(deps, game, options)
    else:
        result.update(quote_action(deps, game, action, target_id, options))
    result['revision'] = game.heavens_state.get('revision', 0)
    return result


def check_configuration(deps, game, options):
    if options.get('generation_enabled') and not deps.get_definitions().generation_available:
        raise ValueError('诸天玩法尚未开放，不能开启生成')
    if 'pause_on_opportunity' in options and not options.get('generation_enabled') and 'runtime' not in game.heavens_state:
        raise ValueError('请先启用诸天联系')


def apply_configuration(game, options: dict) -> None:
    """Mutate only the caller's working copy; never save or acquire a game."""
    original = game.heavens_state
    state = copy.deepcopy(original) if original else initial_state()
    game.heavens_state = state
    if options.get('generation_enabled'):
        initialize(game)
    if 'pause_on_opportunity' in options:
        if 'runtime' not in state:
            raise ValueError('请先启用诸天联系')
        state['runtime']['pause_on_opportunity'] = options['pause_on_opportunity']
    state.update({key: value for key, value in options.items() if key != 'pause_on_opportunity'})
    if state != original:
        state['revision'] += 1
    game.heavens_state = state


def quote_action(deps, game, action, target_id, options):
    if action == 'dismiss':
        runtime = game.heavens_state.get('runtime')
        if not runtime or not any(row['id'] == target_id for row in runtime['notifications']):
            raise ValueError('通知不存在或已到期')
        return dict(years=0, costs={}, refundable={})
    return tasks.quote(deps, game, action, target_id, options)


def command(deps: HeavensDependencies, game_id: str, command_seq: int,
            expected_revision: int, action: str, target_id, options) -> dict:
    require_counter(command_seq, '命令序号')
    require_counter(expected_revision, '预期修订')
    # Structural validation precedes hashing. No raw state patches or executors.
    proposal = plan(deps.get_definitions(), action, target_id, options)
    canonical = json.dumps(dict(action=action, target_id=target_id,
                                options=proposal['options'], expected_revision=expected_revision),
                           sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    fingerprint = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    game = deps.load_game(game_id)
    validate_state(game.heavens_state)
    state = game.heavens_state or initial_state()
    for receipt in state['receipts']:
        if receipt['command_seq'] == command_seq:
            if receipt['fingerprint'] != fingerprint:
                raise ValueError('相同诸天命令序号的参数不一致')
            return copy.deepcopy(receipt['result'])
    if command_seq <= state['command_seq']:
        raise ValueError('诸天命令回执已过期')
    if command_seq != state['command_seq'] + 1:
        raise ValueError('诸天新命令必须使用下一连续序号')
    if expected_revision != state['revision']:
        raise ValueError('诸天状态已过期，请重新查询')
    if action == 'configure':
        check_configuration(deps, game, options)
    else:
        proposal.update(quote_action(deps, game, action, target_id, options))
    work = copy.deepcopy(game)
    try:
        extra = {}
        if action == 'configure':
            apply_configuration(work, proposal['options'])
        elif action == 'dismiss':
            runtime = work.heavens_state['runtime']
            runtime['notifications'] = [row for row in runtime['notifications'] if row['id'] != target_id]
            runtime['pause_requested'] = False
            work.heavens_state['revision'] += 1
        else:
            extra = tasks.execute(deps, work, action, target_id, options, proposal)
            work.heavens_state['revision'] += 1
        state = work.heavens_state
        state['command_seq'] = command_seq
        result = dict(command_seq=command_seq, revision=state['revision'], action=action,
                      generation_enabled=state['generation_enabled'], watch=state['watch'])
        result.update(extra)
        state['receipts'].append(dict(command_seq=command_seq, fingerprint=fingerprint,
                                      result=copy.deepcopy(result)))
        state['receipts'] = state['receipts'][-RECEIPT_LIMIT:]
        validate_state(state)
        validate_references(work)
        deps.get_store().save(work)
    except Exception:
        # Even a save adapter that mutates its input cannot contaminate the
        # prepared state. The next access reloads the last durable document.
        deps.invalidate_game(game_id)
        raise
    deps.accept_committed(work)
    return result
