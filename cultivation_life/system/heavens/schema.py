"""Pure document validation; no models, content registry or gameplay imports.

Only implemented fields are accepted. Later milestones must explicitly extend
this contract before accepting their facts, references or random streams.
"""
from __future__ import annotations

import copy
import re
import math
from typing import Any
from .definitions import SITE_IDS, default_site, validate_site

SCHEMA_VERSION = 1
RECEIPT_LIMIT = 128
STATE_KEYS = frozenset({
    'schema_version', 'revision', 'generation_enabled', 'definition_versions',
    'watch', 'command_seq', 'receipts',
})


def migrate_heavens_v8(document: dict[str, Any]) -> None:
    # Do not silently discard a conflicting extension field.
    if 'heavens_state' in document and document['heavens_state'] != {}:
        raise ValueError('结构 8 的诸天字段与迁移冲突')
    document['heavens_state'] = {}


def initial_state() -> dict[str, Any]:
    return dict(schema_version=SCHEMA_VERSION, revision=0,
                generation_enabled=False, definition_versions={}, watch=True,
                command_seq=0, receipts=[])


def require_counter(value: Any, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f'诸天{label}必须为非负整数')


def validate_state(state: Any) -> None:
    if type(state) is not dict:
        raise ValueError('诸天状态必须为对象')
    if not state:
        return
    finite_tree(state)
    if type(state.get('schema_version')) is not int or state['schema_version'] != SCHEMA_VERSION:
        raise ValueError('不支持的诸天子协议版本')
    if set(state) - {'runtime'} != STATE_KEYS:
        raise ValueError('诸天状态含缺失或尚未支持的字段')
    for key in ('revision', 'command_seq'):
        require_counter(state[key], key)
    if type(state['generation_enabled']) is not bool or type(state['watch']) is not bool:
        raise ValueError('诸天设置必须为布尔值')
    if state['generation_enabled'] and 'runtime' not in state:
        raise ValueError('诸天启用状态缺少日历')
    if (type(state['definition_versions']) is not dict
            or any(key not in SITE_IDS or type(value) is not int or value != 1
                   for key, value in state['definition_versions'].items())):
        raise ValueError('诸天生成定义版本无效')
    if 'runtime' in state:
        validate_runtime(state['runtime'])
        expected_versions = {echo['id']: 1 for echo in runtime_contacts(state['runtime'])}
        if state['definition_versions'] != expected_versions:
            raise ValueError('诸天实例与生成定义版本不一致')
    receipts = state['receipts']
    seq = state['command_seq']
    if 'runtime' not in state and state['revision'] > seq:
        raise ValueError('诸天 M0 修订不能超过已提交命令数')
    if type(receipts) is not list or len(receipts) != min(seq, RECEIPT_LIMIT):
        raise ValueError('诸天回执窗口损坏')
    last_revision = 0
    for expected, receipt in enumerate(receipts, start=max(1, seq - RECEIPT_LIMIT + 1)):
        if type(receipt) is not dict or set(receipt) != {'command_seq', 'fingerprint', 'result'}:
            raise ValueError('诸天回执格式无效')
        require_counter(receipt['command_seq'], '回执序号')
        if receipt['command_seq'] != expected:
            raise ValueError('诸天回执序号不连续')
        fingerprint = receipt['fingerprint']
        if not isinstance(fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
            raise ValueError('诸天回执摘要无效')
        result = receipt['result']
        if type(result) is not dict or set(result) - {'task_id', 'progress', 'status', 'message'} != {
            'command_seq', 'revision', 'action', 'generation_enabled', 'watch',
        }:
            raise ValueError('诸天回执结果无效')
        require_counter(result['revision'], '回执修订')
        require_counter(result['command_seq'], '结果序号')
        if (result['command_seq'] != expected or result['action'] not in {
                'configure', 'watch', 'dismiss', 'observe', 'check_history', 'exchange', 'attune', 'maintain', 'correspond', 'resume', 'cancel'}
                or type(result['generation_enabled']) is not bool or type(result['watch']) is not bool
                or not last_revision <= result['revision'] <= state['revision']):
            raise ValueError('诸天回执与状态不一致')
        last_revision = result['revision']
    if receipts and 'runtime' not in state and (last_revision != state['revision']
                     or receipts[-1]['result']['watch'] != state['watch']):
        raise ValueError('诸天最新回执与状态不一致')


def finite_tree(value):
    if type(value) is float and not math.isfinite(value):
        raise ValueError('诸天状态含非有限数值')
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError('诸天状态键无效')
            finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            finite_tree(child)


def runtime_contacts(runtime):
    return ([runtime['sea_echo']] if runtime['sea_echo'] else []) + list(runtime.get('contacts', {}).values())


def validate_runtime(runtime):
    keys = {'epoch_age', 'processed_years', 'last_year_key', 'last_discovery_window',
            'rng_counter', 'next_task_seq', 'unit_credit', 'sea_echo', 'tasks',
            'history', 'notifications', 'pause_requested', 'pause_on_opportunity'}
    if type(runtime) is not dict or set(runtime) - {'contacts'} != keys:
        raise ValueError('诸天日历字段无效')
    extra = runtime.get('contacts', {})
    if type(extra) is not dict or set(extra) - (SITE_IDS - {'sea_echo'}):
        raise ValueError('诸天联系目录无效')
    for target_id, echo in extra.items():
        if type(echo) is not dict or echo.get('id') != target_id:
            raise ValueError('诸天联系身份不一致')
    if runtime['sea_echo'] is not None and (type(runtime['sea_echo']) is not dict or runtime['sea_echo'].get('id') != 'sea_echo'):
        raise ValueError('法则天海联系身份不一致')
    echoes = runtime_contacts(runtime)
    by_id = {}
    for echo in echoes:
        validate_echo(echo)
        by_id[echo['id']] = echo
    if sum(echo['application'] is not None for echo in echoes) > 1:
        raise ValueError('只能同时登记一项诸天参悟')
    finite_tree(runtime)
    for key in ('epoch_age', 'processed_years', 'last_year_key', 'rng_counter', 'next_task_seq'):
        require_counter(runtime[key], key)
    if runtime['last_year_key'] != runtime['processed_years'] or runtime['next_task_seq'] < 1:
        raise ValueError('诸天处理时钟无效')
    window = runtime['last_discovery_window']
    if type(window) is not int or not -1 <= window <= runtime['processed_years'] // 100:
        raise ValueError('诸天发现窗口无效')
    credit = runtime['unit_credit']
    if type(credit) is not dict or set(credit) != {'numerator', 'denominator'}:
        raise ValueError('诸天短活动余量无效')
    for key in credit:
        require_counter(credit[key], key)
    if not 0 <= credit['numerator'] < credit['denominator']:
        raise ValueError('诸天短活动余量必须小于一个单位')
    if type(runtime['pause_requested']) is not bool or type(runtime['pause_on_opportunity']) is not bool:
        raise ValueError('诸天暂停标记无效')
    for name, limit in (('tasks', 4), ('history', 128), ('notifications', 3)):
        if type(runtime[name]) is not list or len(runtime[name]) > limit:
            raise ValueError('诸天记录超出支持容量')
    for row in runtime['history']:
        if type(row) is not dict or set(row) != {'year', 'text'} or not isinstance(row['text'], str):
            raise ValueError('诸天纪要无效')
        require_counter(row['year'], '纪要时间')
    for row in runtime['notifications']:
        if (type(row) is not dict or set(row) != {'id', 'text', 'expires_at'}
                or row['id'] not in by_id or not isinstance(row['text'], str)):
            raise ValueError('诸天通知无效')
        require_counter(row['expires_at'], '通知期限')
    for echo in echoes:
        if echo['origin_year'] > runtime['processed_years']:
            raise ValueError('诸天现象起点在未来')
        if echo['cycle'] != (runtime['processed_years']-echo['origin_year']) // echo['definition']['period_years']:
            raise ValueError('诸天现象周期与日历不一致')
    active = 0
    ids = set()
    for task in runtime['tasks']:
        if type(task) is not dict or set(task) - {'target_id', 'project_reward'} != {'id', 'action', 'status', 'cycle', 'progress', 'duration', 'escrow', 'person_id'}:
            raise ValueError('诸天任务字段无效')
        target_id = task.get('target_id', 'sea_echo')
        if not isinstance(target_id, str):
            raise ValueError('诸天任务目标无效')
        echo = by_id.get(target_id)
        if not echo or task['id'] in ids or not isinstance(task['id'], str):
            raise ValueError('诸天任务引用无效')
        ids.add(task['id'])
        if task['action'] not in {'observe', 'check_history', 'exchange', 'maintain', 'correspond'}:
            raise ValueError('诸天任务动作无效')
        if task['status'] not in {'reserved', 'running', 'paused', 'completed', 'cancelled', 'failed'}:
            raise ValueError('诸天任务阶段无效')
        for key in ('cycle', 'progress', 'duration'):
            require_counter(task[key], key)
        if not 0 <= task['progress'] <= task['duration'] or task['duration'] < 1:
            raise ValueError('诸天任务进度无效')
        if task['person_id'] not in (None, echo['visitor_id']):
            raise ValueError('诸天任务人物引用无效')
        reward = task.get('project_reward', 0)
        require_counter(reward, '校订托管')
        is_active = task['status'] in {'reserved', 'running', 'paused'}
        if task['action'] == 'correspond':
            site = echo.get('site') or vars_site(echo['id'])
            if (task['person_id'] != echo['visitor_id'] or not echo['exchanged']
                    or task['duration'] != site['correspondence_years']
                    or reward != (site['correspondence_stones'] if is_active else 0)
                    or is_active and echo.get('correspondence_completed', False)
                    or task['status'] == 'completed' and not echo.get('correspondence_completed', False)):
                raise ValueError('诸天校订履约账目无效')
        elif reward:
            raise ValueError('非校订任务不能托管项目酬劳')
        escrow = task['escrow']
        if type(escrow) is not dict or set(escrow) != {'total', 'spent', 'refunded', 'material', 'mp_paid'}:
            raise ValueError('诸天托管字段无效')
        for key in ('total', 'spent', 'refunded'):
            require_counter(escrow[key], key)
        if escrow['spent'] + escrow['refunded'] > escrow['total'] or type(escrow['mp_paid']) not in (int, float) or escrow['mp_paid'] < 0:
            raise ValueError('诸天托管账目无效')
        if escrow['material'] is not None and (not isinstance(escrow['material'], dict) or not escrow['material'].get('id')):
            raise ValueError('诸天阵材托管无效')
        active += task['status'] in {'reserved', 'running', 'paused'}
    if active > 1:
        raise ValueError('只能同时进行一项诸天亲自任务')


def validate_echo(echo):
    keys = {'id', 'definition', 'origin_year', 'visitor_id', 'arrived_at', 'record_id',
        'cycle', 'observed_cycle', 'history_checked', 'exchanged', 'maintained',
        'maintenance_started', 'applications_used', 'reward_base', 'reward_claimed',
        'application', 'project_stones'}
    if type(echo) is not dict or set(echo) - {'site', 'correspondence_completed'} != keys or echo['id'] not in SITE_IDS:
        raise ValueError('诸天实例字段无效')
    if 'site' in echo:
        validate_site(echo['site'])
        if echo['site']['id'] != echo['id']:
            raise ValueError('诸天地点与实例身份不一致')
    elif echo['id'] != 'sea_echo':
        raise ValueError('诸天实例缺少地点快照')
    if (type(echo.get('correspondence_completed', False)) is not bool
            or echo.get('correspondence_completed', False) and not echo['exchanged']):
        raise ValueError('诸天校订事实无效')
    # Pure definition validation, independent of the runtime content registry.
    from .definitions import validate_echo_definition
    validate_echo_definition(echo['definition'])
    if not isinstance(echo['visitor_id'], str) or not echo['visitor_id'] or echo['record_id'] != default_site(echo['id']).record_id:
        raise ValueError('法则天海人物或记录引用无效')
    for key in ('origin_year', 'arrived_at', 'cycle', 'applications_used', 'project_stones'):
        require_counter(echo[key], key)
    if type(echo['observed_cycle']) is not int or not -1 <= echo['observed_cycle'] <= echo['cycle']:
        raise ValueError('法则天海观测周期无效')
    for key in ('history_checked', 'exchanged', 'maintained', 'maintenance_started'):
        if type(echo[key]) is not bool:
            raise ValueError('法则天海事实标记无效')
    if (echo['exchanged'] and not echo['history_checked']
            or echo['maintained'] and not echo['maintenance_started']
            or echo['applications_used'] > (2 if echo['maintained'] else 1)):
        raise ValueError('法则天海证据或应用资格不一致')
    if type(echo['reward_claimed']) not in (int, float) or echo['reward_claimed'] < 0:
        raise ValueError('法则天海奖励账目无效')
    base = echo['reward_base']
    if base is not None and (type(base) not in (int, float) or base <= 0):
        raise ValueError('法则天海奖励基准无效')
    if echo['reward_claimed'] > (base or 0) * .03 + 1e-6 or echo['applications_used'] > 2:
        raise ValueError('法则天海奖励超出上限')
    application = echo['application']
    if application is not None:
        if type(application) is not dict or set(application) != {'cycle', 'remaining', 'unit_years'}:
            raise ValueError('法则天海应用字段无效')
        for key in application:
            require_counter(application[key], key)
        if application['cycle'] != echo['cycle'] or not 0 < application['remaining'] <= application['unit_years']:
            raise ValueError('法则天海应用期限无效')


def vars_site(target_id):
    from dataclasses import asdict
    return asdict(default_site(target_id))


def validate_references(game):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        return
    people = set(game.world_npcs) | set(game.notable_npcs) | set(game.inactive_npcs) | set(game.relationship_npcs)
    for sect in game.sects.values():
        people.update(npc.id for npc in sect.npcs)
    if game.family:
        people.update(npc.id for npc in game.family.npcs)
    visitors = [echo['visitor_id'] for echo in runtime_contacts(runtime)]
    if len(set(visitors)) != len(visitors) or any(identity not in people for identity in visitors):
        raise ValueError('诸天合作人物引用已损坏，保留原档')
    held = [task['escrow']['material']['id'] for task in runtime['tasks'] if task['escrow']['material']]
    inventory = {row['id'] for row in game.player.formation_materials}
    if len(set(held)) != len(held) or inventory.intersection(held):
        raise ValueError('法则天海阵材出现重复所有权')


def decode_state(value: Any) -> dict[str, Any]:
    validate_state(value)
    return copy.deepcopy(value)
