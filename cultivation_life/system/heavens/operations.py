"""Pure projections and isolated, single-document commands."""
from __future__ import annotations

import copy
import hashlib
import json

from .definitions import ACTIONS, VIEWS, HeavensDefinitions, MIRROR_ID, RUINS_ID, RUINS_ACTIONS, OMEN_IDS, VISIT_ACTIONS
from .dependencies import HeavensDependencies
from .schema import RECEIPT_LIMIT, initial_state, require_counter, validate_state, validate_references
from .state import initialize, phase, contacts, get_echo, echo_site, current_site, site_for
from . import tasks, mirror, ruins, omens, visits, incidents, intelligence
from .incident_definitions import INCIDENT_IDS, INCIDENT_ACTIONS
from . import missions, freight, migration, survey, upkeep, frontier, campaign_actions
from .frontier_definitions import FRONTIER_ID, FRONTIER_ACTIONS
from .campaign_definitions import CAMPAIGN_ID, CAMPAIGN_ACTIONS
from .definitions import MISSION_ACTIONS, FREIGHT_ACTIONS, MIGRATION_ACTIONS, SURVEY_ACTIONS, UPKEEP_ACTIONS


def project(game, view: str, target_id: str | None = None, *, deps=None) -> dict:
    if not isinstance(view, str) or view not in VIEWS:
        raise ValueError('未知诸天视图')
    runtime = game.heavens_state.get('runtime')
    requested_target = target_id
    validate_state(game.heavens_state)
    site = (site_for(deps, game, target_id) if target_id else current_site(deps, game)) if deps else None
    if target_id and (not intelligence.knows(game, target_id) or site and intelligence.level(game.player.world, site.world) < 5 and not get_echo(runtime, site.id)):
        raise ValueError('当前只能获知远界传闻，尚不了解此处详情')
    if target_id is not None and site is None and target_id not in {MIRROR_ID, RUINS_ID, FRONTIER_ID, CAMPAIGN_ID} | OMEN_IDS | INCIDENT_IDS:
        raise ValueError('诸天对象不可见或不存在')
    target_id = site.id if site else None
    echo = get_echo(runtime, target_id)
    state = game.heavens_state or initial_state()
    # Never expose internal receipts, future objective facts or random states.
    result = dict(view=view, records=[], revision=state['revision'],
                next_command_seq=state['command_seq'] + 1,
                generation_enabled=state['generation_enabled'], watch=state['watch'],
                available_actions=['configure'], target_id=target_id,
                reason=f'可在{site.name.split(" · ")[0]}体察并登记此地诸天联系。' if site else '诸天联系开放于仙界、修罗界、幽冥界和轮回界的观测地点。')
    world_names = {'celestial': '仙界', 'asura': '修罗界', 'nether': '幽冥界', 'reincarnation': '轮回界'}
    result['sites'] = [dict(id=row.id, world=row.world, world_name=world_names[row.world], name=row.name,
                          location_id=row.location_id, known=bool(get_echo(runtime, row.id)),
                          current=row.world == game.player.world)
                       for row in ([site_for(deps, game, item.id) for item in deps.get_definitions().contact_sites] if deps else ())]
    result['upkeeps'] = [dict(name=row['name'], **upkeep.project(deps, game, row['id'])) for row in result['sites']] if deps else []
    if deps and target_id:
        result['upkeep'] = upkeep.project(deps, game, target_id, detail=True)
    result['generation_available'] = bool(deps and deps.get_definitions().generation_available)
    result['pause_on_opportunity'] = bool(runtime and runtime['pause_on_opportunity'])
    if deps and deps.read_mirror_facts:
        result['mirror'] = mirror.project(deps, game)
        if deps.read_survey_facts:
            result['mirror']['survey'] = survey.project(deps, game, target=MIRROR_ID)
        if requested_target == MIRROR_ID or requested_target is None and result['mirror']['inside']:
            result['target_id'] = MIRROR_ID
    if deps and deps.read_ruins_facts:
        result['ruins'] = ruins.project(deps, game)
        if deps.read_survey_facts:
            result['ruins']['survey'] = survey.project(deps, game)
        if requested_target == RUINS_ID or requested_target is None and result['ruins']['inside']:
            result['target_id'] = RUINS_ID
    result['incidents'] = incidents.project(deps, game) if deps and deps.incident_facts else []
    result['anomalies'] = incidents.project(deps, game, 'anomaly') if deps and deps.incident_facts else []
    result['conflicts'] = incidents.project(deps, game, 'conflict') if deps and deps.incident_facts else []
    if requested_target in INCIDENT_IDS:
        result['target_id'] = requested_target
    result['omens'] = omens.project(deps, game) if deps and deps.read_omen_facts else []
    if deps and deps.frontier_player_reason:
        result['frontier'] = frontier.project(deps, game)
    if deps and deps.campaign_facts:
        result['campaign'] = campaign_actions.project(deps, game)
    if requested_target in {FRONTIER_ID, CAMPAIGN_ID}:
        result['target_id'] = requested_target
    if requested_target in OMEN_IDS:
        if not any(row['id'] == requested_target for row in result['omens']):
            raise ValueError('诸天征兆尚不可见')
        result['target_id'] = requested_target
    if deps and deps.migration_candidates:
        result['migrations'] = [migration.project(deps, game, row.id, detail=False) for row in deps.get_definitions().contact_sites]
        if target_id:
            result['migration'] = migration.project(deps, game, target_id)
    if not runtime:
        return intelligence.restrict(game, result)
    result.update(year=runtime['processed_years'], tasks=copy.deepcopy(runtime['tasks']),
                  notifications=copy.deepcopy(runtime['notifications']) if state['watch'] else [],
                  history=copy.deepcopy(runtime['history']), unit_credit=copy.deepcopy(runtime['unit_credit']))
    result['visits'] = [dict(target_id=row['id'], name=echo_site(row).name, **visits.project(deps, game, row['id']))
                        for row in contacts(runtime) if row.get('visit')] if deps else []
    result['missions'] = [missions.project(deps, game, row['id']) for row in contacts(runtime)
                          if row.get('mission')] if deps and deps.read_mission_facts else []
    result['freights'] = [freight.project(deps, game, row['id']) for row in contacts(runtime)
                           if row.get('freight')] if deps and deps.read_mission_facts else []
    def echo_view(echo):
        site = echo_site(echo)
        cycle, offset, cutoff = phase(runtime, echo)
        person = deps.resolve_person(game, echo['visitor_id']) if deps else None
        return dict(id=echo['id'], name=site.name, world=site.world, location_id=site.location_id, cycle=cycle,
            origin_year=echo['origin_year'], remaining=max(0, cutoff-offset),
            next_cycle_in=echo['definition']['period_years']-offset,
            inscriptions=[echo['origin_year']-4000, echo['origin_year']-2000] if echo['history_checked'] else [],
            evidence=[f'E{index+1} {label}' for index, (label, acquired) in enumerate(zip(site.evidence,
                      (echo['observed_cycle']==cycle, echo['history_checked'], echo['exchanged']))) if acquired],
            visitor=dict(id=echo['visitor_id'], name=person.name if person else site.visitor_name,
                         available=bool(deps and deps.person_available(game, echo['visitor_id']))),
            application=copy.deepcopy(echo['application']), maintained=echo['maintained'],
            reward_claimed=echo['reward_claimed'], reward_base=echo['reward_base'],
            project_stones=echo['project_stones'], correspondence_completed=echo.get('correspondence_completed', False))
    known = [echo_view(row) for row in contacts(runtime)]
    if echo:
        result['echo'] = next(row for row in known if row['id'] == echo['id'])
    if deps and target_id and deps.read_visit_facts:
        result['visit'] = visits.project(deps, game, target_id)
    if deps and target_id and deps.read_mission_facts:
        result['mission'] = missions.project(deps, game, target_id)
        result['freight'] = freight.project(deps, game, target_id)
    result['registered_application'] = next((dict(target_id=row['id'], name=row['name'], **row['application'])
                                           for row in known if row['application']), None)
    result['actions'] = []
    if deps and target_id:
        result['materials'] = deps.quote_materials(game, target_id)
        for action in ('observe', 'check_history', 'exchange', 'attune', 'maintain', 'correspond',
                       'visit_depart', 'visit_study', 'visit_return'):
            options = ({'person_id': echo['visitor_id']} if action in {'exchange', 'correspond'} and echo else
                       {'material_id': result['materials'][0]['id']} if action=='maintain' and result['materials'] else {})
            row = dict(action=action, target_id=target_id, label=tasks.LABELS[action], options=options)
            if action == 'observe':
                row['label'] = '体察潮汐' if target_id == 'sea_echo' else f'体察{site.evidence[0]}'
            try:
                row.update(tasks.quote(deps, game, action, target_id, options), enabled=True)
            except ValueError as exc:
                row.update(enabled=False, reason=str(exc))
            result['actions'].append(row)
        result['available_actions'].extend(row['action'] for row in result['actions'] if row['enabled'])
    if tasks.active_task(runtime):
        result['available_actions'].extend(['resume', 'cancel'])
    elif result['registered_application']:
        result['available_actions'].append('cancel')
    if runtime['notifications']:
        result['available_actions'].append('dismiss')
    known_anomalies = [result[key] for key in ('mirror', 'ruins') if result.get(key, {}).get('known')]
    result['records'] = known + known_anomalies + result['omens'] if view in {'known','opportunities'} else result[view]
    return intelligence.restrict(game, result)


def plan(definitions: HeavensDefinitions, action: str, target_id, options) -> dict:
    if not isinstance(action, str) or action not in ACTIONS:
        raise ValueError('未知诸天动作')
    if action != 'configure':
        allowed = {'observe': set(), 'check_history': set(), 'exchange': {'person_id'}, 'correspond': {'person_id'},
                   'omen_study': set(), 'attune': set(), 'maintain': {'material_id'}, 'resume': set(), 'cancel': set(), 'dismiss': set(),
                   'mirror_enter': set(), 'mirror_leave': set(), 'mirror_probe': set(),
                   'mirror_repair': {'material_id'}, 'mirror_release': set(),
                   'mirror_decipher': {'chamber'}, 'mirror_isolate': {'chamber', 'material_id'}, 'mirror_assault': {'chamber'}}
        allowed.update({key: {'material_id'} if key == 'ruins_replace' else set() for key in RUINS_ACTIONS})
        allowed.update({key: set() for key in VISIT_ACTIONS | FRONTIER_ACTIONS | CAMPAIGN_ACTIONS | INCIDENT_ACTIONS})
        allowed.update({key: set() for key in MISSION_ACTIONS})
        allowed.update({key: {'material_id'} if key == 'freight_start' else set() for key in FREIGHT_ACTIONS})
        allowed.update({key: {'person_id'} if key == 'migration_start' else set() for key in MIGRATION_ACTIONS})
        allowed.update({key: {'person_id'} if key == 'survey_start' else set() for key in SURVEY_ACTIONS})
        allowed.update({key: {'material_id'} if key == 'upkeep_start' else set() for key in UPKEEP_ACTIONS})
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
    if not intelligence.knows(game, target_id):
        raise ValueError('当前只能获知远界传闻，尚不了解此处详情')
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
