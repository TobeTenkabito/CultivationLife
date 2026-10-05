"""Pure document validation; no models, content registry or gameplay imports.

Only implemented fields are accepted. Later milestones must explicitly extend
this contract before accepting their facts, references or random streams.
"""
from __future__ import annotations

import copy
import re
import math
from typing import Any
from .definitions import SITE_IDS, default_site, validate_site, MIRROR_ID, MIRROR_ACTIONS, validate_mirror_definition, RUINS_ID, RUINS_ACTIONS, validate_ruins_definition

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
            or any(key not in SITE_IDS | {MIRROR_ID, RUINS_ID} or type(value) is not int or value != 1
                   for key, value in state['definition_versions'].items())):
        raise ValueError('诸天生成定义版本无效')
    if 'runtime' in state:
        validate_runtime(state['runtime'])
        expected_versions = {echo['id']: 1 for echo in runtime_contacts(state['runtime'])}
        if 'mirror' in state['runtime']:
            expected_versions[MIRROR_ID] = 1
        if 'ruins' in state['runtime']:
            expected_versions[RUINS_ID] = 1
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
                'configure', 'watch', 'dismiss', 'observe', 'check_history', 'exchange', 'attune', 'maintain', 'correspond', 'resume', 'cancel'} | MIRROR_ACTIONS | RUINS_ACTIONS
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
    if type(runtime) is not dict or set(runtime) - {'contacts', 'mirror', 'ruins'} != keys:
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
    if 'mirror' in runtime:
        validate_mirror(runtime['mirror'], runtime['processed_years'])
    if 'ruins' in runtime:
        validate_ruins(runtime['ruins'], runtime['processed_years'])
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
        if type(task) is not dict or set(task) - {'target_id', 'project_reward', 'chamber'} != {'id', 'action', 'status', 'cycle', 'progress', 'duration', 'escrow', 'person_id'}:
            raise ValueError('诸天任务字段无效')
        target_id = task.get('target_id', 'sea_echo')
        if not isinstance(target_id, str):
            raise ValueError('诸天任务目标无效')
        is_mirror, is_ruins = target_id == MIRROR_ID, target_id == RUINS_ID
        echo = runtime.get('ruins') if is_ruins else runtime.get('mirror') if is_mirror else by_id.get(target_id)
        if not echo or task['id'] in ids or not isinstance(task['id'], str):
            raise ValueError('诸天任务引用无效')
        ids.add(task['id'])
        actions = (RUINS_ACTIONS - {'ruins_enter', 'ruins_leave'}) if is_ruins else MIRROR_ACTIONS - {'mirror_enter', 'mirror_leave'} if is_mirror else {'observe', 'check_history', 'exchange', 'maintain', 'correspond'}
        if task['action'] not in actions:
            raise ValueError('诸天任务动作无效')
        if task['status'] not in {'reserved', 'running', 'paused', 'completed', 'cancelled', 'failed'}:
            raise ValueError('诸天任务阶段无效')
        for key in ('cycle', 'progress', 'duration'):
            require_counter(task[key], key)
        if not 0 <= task['progress'] <= task['duration'] or task['duration'] < 1:
            raise ValueError('诸天任务进度无效')
        if task['person_id'] not in (None, echo.get('visitor_id')):
            raise ValueError('诸天任务人物引用无效')
        if is_ruins:
            if (task['cycle'] != 0 or 'chamber' in task or task['person_id'] is not None
                    or task['duration'] != echo['definition'][task['action'].removeprefix('ruins_')+'_years']
                    or task['status'] == 'completed' and task['progress'] != task['duration']):
                raise ValueError('因果遗址任务引用或时长无效')
            completed_flag = {'ruins_observe': 'observed', 'ruins_verify': 'verified', 'ruins_read': 'record_acquired', 'ruins_contact': 'contact_known'}.get(task['action'])
            if task['status'] == 'completed' and (completed_flag and not echo[completed_flag]
                    or task['action'] in {'ruins_take', 'ruins_replace'} and echo['core']['acquisition'] != task['action']
                    or task['action'] == 'ruins_return' and (echo['core']['owner'] != 'ward' or echo['core']['acquisition'] is None)):
                raise ValueError('因果遗址任务完成事实不一致')
        if is_mirror:
            chamber = task.get('chamber')
            if (('chamber' not in task) or task['cycle'] != 0
                    or task['action'] == 'mirror_probe' and chamber is not None
                    or task['action'] != 'mirror_probe' and (type(chamber) is not int or not 0 <= chamber < 3)
                    or task['duration'] != echo['definition'][task['action'].removeprefix('mirror_')+'_years']):
                raise ValueError('镜律任务引用或时长无效')
            if task['status'] == 'completed':
                row = echo['chambers'][chamber] if chamber is not None else None
                if (task['progress'] != task['duration']
                        or task['action'] == 'mirror_probe' and not echo['probed']
                        or task['action'] == 'mirror_decipher' and not row['opened']
                        or task['action'] == 'mirror_isolate' and not row['isolated']
                        or task['action'] == 'mirror_assault' and row['guardian'] is None):
                    raise ValueError('镜律任务完成事实不一致')
        elif 'chamber' in task:
            raise ValueError('非镜律任务不能引用机关')
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
        if is_mirror and (escrow['total'] or escrow['spent'] or escrow['refunded'] or escrow['material'] is not None):
            raise ValueError('镜律任务不持有可退款托管')
        if is_ruins:
            expected_cost = echo['definition'].get(task['action'].removeprefix('ruins_')+'_stones', 0)
            if escrow['material'] is not None or escrow['total'] != expected_cost or escrow['spent'] != expected_cost * task['progress'] // task['duration']:
                raise ValueError('因果遗址投入账目无效')
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


def validate_mirror(mirror, year):
    fields = {'id', 'definition', 'scene_id', 'created_year', 'probed', 'mana_capacity',
              'paid_mana', 'collected_mana', 'stored_mana', 'record_acquired', 'chambers', 'traces'}
    if type(mirror) is not dict or set(mirror) != fields or mirror['id'] != MIRROR_ID:
        raise ValueError('镜律实例字段无效')
    validate_mirror_definition(mirror['definition'])
    if not isinstance(mirror['scene_id'], str) or not re.fullmatch(r'heavens-mirror-[0-9a-f]{20}', mirror['scene_id']):
        raise ValueError('镜律空间引用无效')
    require_counter(mirror['created_year'], '镜律创建时间')
    if mirror['created_year'] > year:
        raise ValueError('镜律创建时间在未来')
    if any(type(mirror[key]) is not bool for key in ('probed', 'record_acquired')):
        raise ValueError('镜律证据标记无效')
    for key in ('mana_capacity', 'paid_mana', 'collected_mana', 'stored_mana'):
        if type(mirror[key]) not in (int, float) or not math.isfinite(mirror[key]) or mirror[key] < 0:
            raise ValueError('镜律法力账目无效')
    if (not 0 < mirror['mana_capacity'] or mirror['collected_mana'] > mirror['mana_capacity'] + 1e-6
            or mirror['collected_mana'] > mirror['paid_mana'] * mirror['definition']['collection_fraction'] + 1e-6):
        raise ValueError('镜律收集超出实付来源或容量')
    rows = mirror['chambers']
    if type(rows) is not list or len(rows) != 3:
        raise ValueError('镜律实例必须保留三处唯一机关')
    allocated, materials = 0.0, set()
    for index, row in enumerate(rows):
        if type(row) is not dict or set(row) != {'opened', 'isolated', 'guardian', 'reward'}:
            raise ValueError('镜律机关字段无效')
        if type(row['opened']) is not bool or type(row['isolated']) is not bool:
            raise ValueError('镜律机关事实无效')
        if (row['opened'] or row['isolated'] or row['guardian']) and not mirror['probed']:
            raise ValueError('镜律机关缺少试探证据')
        reward = row['reward']
        if index < 2:
            if (type(reward) is not dict or set(reward) != {'id', 'material_id', 'name', 'source', 'origin_world', 'acquired_tier', 'base_value'}
                    or reward['id'] != f'{mirror["scene_id"]}-material-{index}'
                    or reward['origin_world'] != 'human' or type(reward['acquired_tier']) is not int or reward['acquired_tier'] != 4
                    or any(not isinstance(reward[key], str) or not reward[key] for key in ('name', 'source', 'material_id'))):
                raise ValueError('镜律材料预留无效')
            require_counter(reward['base_value'], '镜律材料价值')
            if reward['id'] in materials:
                raise ValueError('镜律材料重复归属')
            materials.add(reward['id'])
        elif reward is not None or mirror['record_acquired'] != row['opened']:
            raise ValueError('镜律规律记录归属无效')
        guardian = row['guardian']
        if guardian is not None:
            if type(guardian) is not dict or set(guardian) != {'mana', 'power', 'wounds', 'encounters', 'result'}:
                raise ValueError('镜律守护快照无效')
            for key in ('mana', 'power'):
                if type(guardian[key]) not in (int, float) or not math.isfinite(guardian[key]) or guardian[key] < 0:
                    raise ValueError('镜律守护数值无效')
            expected = mirror['definition']['guardian_power'] * (1 + mirror['definition']['strength_cap'] * guardian['mana']/max(1.0, mirror['mana_capacity']))
            if guardian['mana'] > mirror['mana_capacity'] + 1e-6 or abs(guardian['power']-expected) > 1e-6:
                raise ValueError('镜律强度缺少真实供给')
            require_counter(guardian['wounds'], '镜律机关损伤')
            require_counter(guardian['encounters'], '镜律遭遇次数')
            if guardian['wounds'] > 4 or guardian['encounters'] < 1 or not isinstance(guardian['result'], str) or not guardian['result']:
                raise ValueError('镜律遭遇后果无效')
            allocated += guardian['mana']
    if abs(mirror['stored_mana'] + allocated - mirror['collected_mana']) > 1e-6:
        raise ValueError('镜律供给与储量不守恒')
    if type(mirror['traces']) is not list or len(mirror['traces']) > 32:
        raise ValueError('镜律痕迹超出容量')
    for row in mirror['traces']:
        if type(row) is not dict or set(row) != {'year', 'kind', 'chamber'} or row['kind'] not in MIRROR_ACTIONS:
            raise ValueError('镜律痕迹无效')
        require_counter(row['year'], '镜律痕迹时间')
        if row['year'] > year or row['chamber'] is not None and (type(row['chamber']) is not int or not 0 <= row['chamber'] < 3):
            raise ValueError('镜律痕迹来源无效')


def validate_ruins(ruins, year):
    fields = {'id', 'scene_id', 'definition', 'created_year', 'observed', 'verified', 'record_acquired', 'contact_known',
              'reward', 'core', 'ward', 'guardian', 'local_traces', 'guardian_records', 'sent_records'}
    if type(ruins) is not dict or set(ruins) != fields or ruins['id'] != RUINS_ID:
        raise ValueError('因果遗址实例字段无效')
    validate_ruins_definition(ruins['definition'])
    identity = ruins['scene_id']
    if not isinstance(identity, str) or not re.fullmatch(r'heavens-ruins-[0-9a-f]{20}', identity):
        raise ValueError('因果遗址空间身份无效')
    require_counter(ruins['created_year'], '遗址创建时间')
    if ruins['created_year'] > year:
        raise ValueError('因果遗址创建时间在未来')
    for key in ('observed', 'verified', 'record_acquired', 'contact_known'):
        if type(ruins[key]) is not bool:
            raise ValueError('因果遗址证据标记无效')
    if ((ruins['verified'] or ruins['record_acquired']) and not ruins['observed']
            or ruins['contact_known'] and not ruins['verified']):
        raise ValueError('因果遗址缺少前置证据')
    reward = ruins['reward']
    if (type(reward) is not dict or set(reward) != {'id', 'material_id', 'name', 'source', 'origin_world', 'acquired_tier', 'base_value'}
            or reward['id'] != identity+'-material-0' or reward['origin_world'] != 'human'
            or type(reward['acquired_tier']) is not int or reward['acquired_tier'] != 4
            or any(not isinstance(reward[key], str) or not reward[key] for key in ('name', 'source', 'material_id'))):
        raise ValueError('因果遗址阵材预留无效')
    require_counter(reward['base_value'], '遗址阵材价值')
    core = ruins['core']
    if (type(core) is not dict or set(core) != {'id', 'definition_id', 'name', 'owner', 'acquisition'}
            or core['id'] != identity+'-core' or core['definition_id'] != 'returning_tide_core' or core['name'] != '回潮阵芯'
            or core['owner'] not in {'ward', 'player'} or core['acquisition'] not in {None, 'ruins_take', 'ruins_replace'}
            or core['owner'] == 'player' and core['acquisition'] is None
            or core['acquisition'] == 'ruins_replace' and not ruins['verified']):
        raise ValueError('回潮阵芯唯一所有权无效')
    ward = ruins['ward']
    expected_component = 'core' if core['owner'] == 'ward' else 'replacement' if core['acquisition'] == 'ruins_replace' else None
    if (type(ward) is not dict or set(ward) != {'id', 'world', 'location_id', 'component'}
            or ward['id'] != identity+'-ward' or ward['world'] != ruins['definition']['linked_world']
            or ward['location_id'] != ruins['definition']['linked_location_id'] or ward['component'] != expected_component):
        raise ValueError('因果遗址两端阵眼与唯一阵芯不一致')
    guardian = ruins['guardian']
    if type(guardian) is not dict or set(guardian) != {'wounds', 'encounters', 'result'}:
        raise ValueError('因果遗址守阵机关无效')
    for key in ('wounds', 'encounters'):
        require_counter(guardian[key], '守阵机关后果')
    fought = core['acquisition'] == 'ruins_take'
    if (guardian['wounds'] > 4 or guardian['encounters'] != int(fought)
            or fought and (not isinstance(guardian['result'], str) or not guardian['result'])
            or not fought and (guardian['result'] is not None or guardian['wounds'])):
        raise ValueError('因果遗址战果与取芯事实不一致')
    kinds = RUINS_ACTIONS - {'ruins_enter', 'ruins_leave', 'ruins_erase'}
    local, held, sent = (ruins[key] for key in ('local_traces', 'guardian_records', 'sent_records'))
    if any(type(rows) is not dict or set(rows) - kinds for rows in (local, held, sent)):
        raise ValueError('因果遗址痕迹超出有限动作范围')
    if set(local).intersection(held) or set(sent) - set(held):
        raise ValueError('因果遗址证据持有关系无效')
    for stamp in local.values():
        require_counter(stamp, '残留时间')
        if not ruins['created_year'] <= stamp <= year:
            raise ValueError('因果遗址残留时间无效')
    for kind, row in held.items():
        if type(row) is not dict or set(row) != {'year', 'read_at'}:
            raise ValueError('守阵机关留档字段无效')
        for stamp in row.values():
            require_counter(stamp, '留档时间')
        if not ruins['created_year'] <= row['year'] <= row['read_at'] <= year:
            raise ValueError('守阵机关留档来源无效')
        if kind != 'ruins_take' and row['read_at']-row['year'] < ruins['definition']['trace_read_years']:
            raise ValueError('守阵机关提前读取残留')
    for kind, row in sent.items():
        if type(row) is not dict or set(row) != {'year', 'read_at', 'sent_at'}:
            raise ValueError('阵眼送出证据字段无效')
        require_counter(row['sent_at'], '证据送出时间')
        if (any(row[key] != held[kind][key] for key in ('year', 'read_at')) or row['sent_at'] > year
                or row['sent_at']-row['read_at'] < ruins['definition']['trace_send_years']):
            raise ValueError('阵眼送出证据缺少真实来源或时间')
    if fought and 'ruins_take' not in held:
        raise ValueError('直接取芯缺少守阵目击记录')


def validate_references(game):
    runtime = game.heavens_state.get('runtime')
    scenes = [row for row in game.spatial_state.get('instances', {}).values() if row.get('heavens_target') == MIRROR_ID]
    ruins_scenes = [row for row in game.spatial_state.get('instances', {}).values() if row.get('heavens_target') == RUINS_ID]
    if ruins_scenes and (not runtime or not runtime.get('ruins')):
        raise ValueError('因果遗址空间缺少对应诸天实例，保留原档')
    if scenes and (not runtime or not runtime.get('mirror')):
        raise ValueError('镜律空间缺少对应诸天实例，保留原档')
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
    ruins = runtime.get('ruins')
    if ruins:
        scene = game.spatial_state.get('instances', {}).get(ruins['scene_id'])
        if (not scene or len(ruins_scenes) != 1 or scene.get('id') != ruins['scene_id']
                or scene.get('heavens_target') != RUINS_ID or scene.get('kind') != 'heavens'
                or scene.get('location_id') != 'causal_hall' or len(scene.get('locations', [])) != 1
                or scene['locations'][0].get('id') != 'causal_hall' or any(scene.get(key) != [] for key in ('npc_ids', 'materials', 'techniques', 'sects'))):
            raise ValueError('因果遗址空间引用已损坏，保留原档')
        owned = [row['id'] for row in game.player.formation_materials]
        if len(owned) != len(set(owned)) or not ruins['record_acquired'] and ruins['reward']['id'] in inventory.union(held):
            raise ValueError('因果遗址阵材出现重复所有权')
        generic = inventory.union(held) | {row.id for row in game.player.inventory}
        if generic.intersection({ruins['core']['id'], ruins['core']['definition_id']}):
            raise ValueError('唯一任务阵芯不能复制为普通库存物品')
    mirror = runtime.get('mirror')
    if mirror:
        scene = game.spatial_state.get('instances', {}).get(mirror['scene_id'])
        if (not scene or len(scenes) != 1 or scene.get('heavens_target') != MIRROR_ID or scene.get('kind') != 'heavens'
                or scene.get('id') != mirror['scene_id']):
            raise ValueError('镜律场域空间引用已损坏，保留原档')
        if (scene.get('location_id') != 'mirror_hall' or len(scene.get('locations', [])) != 1
                or scene['locations'][0].get('id') != 'mirror_hall' or scene.get('npc_ids') != []
                or scene.get('materials') != [] or scene.get('techniques') != [] or scene.get('sects') != []):
            raise ValueError('镜律场域只能保留固定机关与出口')
        unclaimed = {row['reward']['id'] for row in mirror['chambers'] if row['reward'] and not row['opened']}
        owned = [row['id'] for row in game.player.formation_materials]
        if len(owned) != len(set(owned)) or unclaimed.intersection(owned + held):
            raise ValueError('镜律材料出现重复所有权')


def decode_state(value: Any) -> dict[str, Any]:
    validate_state(value)
    return copy.deepcopy(value)
