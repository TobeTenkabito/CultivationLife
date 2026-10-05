"""Pure document validation; no models, content registry or gameplay imports.

Only implemented fields are accepted. Later milestones must explicitly extend
this contract before accepting their facts, references or random streams.
"""
from __future__ import annotations

import copy
import re
import math
from typing import Any

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
    if type(state['definition_versions']) is not dict or state['definition_versions'] not in ({}, {'sea_echo': 1}):
        raise ValueError('诸天生成定义版本无效')
    if 'runtime' in state:
        validate_runtime(state['runtime'])
        expected_versions = {'sea_echo': 1} if state['runtime']['sea_echo'] else {}
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
                'configure', 'watch', 'dismiss', 'observe', 'check_history', 'exchange', 'attune', 'maintain', 'resume', 'cancel'}
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


def validate_runtime(runtime):
    keys = {'epoch_age', 'processed_years', 'last_year_key', 'last_discovery_window',
            'rng_counter', 'next_task_seq', 'unit_credit', 'sea_echo', 'tasks',
            'history', 'notifications', 'pause_requested', 'pause_on_opportunity'}
    if type(runtime) is not dict or set(runtime) != keys:
        raise ValueError('诸天日历字段无效')
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
                or row['id'] != 'sea_echo' or not isinstance(row['text'], str)):
            raise ValueError('诸天通知无效')
        require_counter(row['expires_at'], '通知期限')
    echo = runtime['sea_echo']
    if echo is not None:
        validate_echo(echo)
        if echo['origin_year'] > runtime['processed_years']:
            raise ValueError('诸天现象起点在未来')
        if echo['cycle'] != (runtime['processed_years']-echo['origin_year']) // echo['definition']['period_years']:
            raise ValueError('诸天现象周期与日历不一致')
    active = 0
    ids = set()
    for task in runtime['tasks']:
        if type(task) is not dict or set(task) != {'id', 'action', 'status', 'cycle', 'progress', 'duration', 'escrow', 'person_id'}:
            raise ValueError('诸天任务字段无效')
        if not echo or task['id'] in ids or not isinstance(task['id'], str):
            raise ValueError('诸天任务引用无效')
        ids.add(task['id'])
        if task['action'] not in {'observe', 'check_history', 'exchange', 'maintain'}:
            raise ValueError('诸天任务动作无效')
        if task['status'] not in {'reserved', 'running', 'paused', 'completed', 'cancelled', 'failed'}:
            raise ValueError('诸天任务阶段无效')
        for key in ('cycle', 'progress', 'duration'):
            require_counter(task[key], key)
        if not 0 <= task['progress'] <= task['duration'] or task['duration'] < 1:
            raise ValueError('诸天任务进度无效')
        if task['person_id'] not in (None, echo['visitor_id']):
            raise ValueError('诸天任务人物引用无效')
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
    if type(echo) is not dict or set(echo) != keys or echo['id'] != 'sea_echo':
        raise ValueError('法则天海实例字段无效')
    # Pure definition validation, independent of the runtime content registry.
    from .definitions import validate_echo_definition
    validate_echo_definition(echo['definition'])
    if not isinstance(echo['visitor_id'], str) or not echo['visitor_id'] or echo['record_id'] != 'karma_city_old_copy':
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


def validate_references(game):
    runtime = game.heavens_state.get('runtime')
    if not runtime or not runtime['sea_echo']:
        return
    people = set(game.world_npcs) | set(game.notable_npcs) | set(game.inactive_npcs) | set(game.relationship_npcs)
    for sect in game.sects.values():
        people.update(npc.id for npc in sect.npcs)
    if game.family:
        people.update(npc.id for npc in game.family.npcs)
    if runtime['sea_echo']['visitor_id'] not in people:
        raise ValueError('法则天海合作人物引用已损坏，保留原档')
    held = [task['escrow']['material']['id'] for task in runtime['tasks'] if task['escrow']['material']]
    inventory = {row['id'] for row in game.player.formation_materials}
    if len(set(held)) != len(held) or inventory.intersection(held):
        raise ValueError('法则天海阵材出现重复所有权')


def decode_state(value: Any) -> dict[str, Any]:
    validate_state(value)
    return copy.deepcopy(value)
