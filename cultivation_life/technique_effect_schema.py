"""Finite, versioned technique effects; no registry, engine or save access."""
from __future__ import annotations

import copy
import math

VERSION = 3
KINDS = frozenset({'guard', 'strike', 'recover', 'breach', 'frugal'})
TRIGGERS = frozenset({'opening', 'after_hit', 'after_hurt'})
LINEAGE_TRIGGERS = TRIGGERS | {'first_exchange', 'low_state', 'target_wounded', 'steady', 'odd_round', 'even_round'}
DELIVERIES = frozenset({'immediate', 'delayed', 'split'})
FIELDS = {'version', 'generator_version', 'kind', 'trigger', 'delivery', 'strength_bp',
          'cost_bp', 'cooldown', 'uses', 'duration', 'refund_bp'}


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'功法效果{name}须为{low}至{high}的整数')
    return value


def finite(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'功法效果{name}超出有限范围')
    return float(value)


def validate_effect(value):
    if not isinstance(value, dict):
        raise ValueError('功法效果须为数据对象')
    version = integer(value.get('version'), 1, VERSION, '结构')
    if version == 3:
        from .catalog_effect_schema import validate_catalog
        return validate_catalog(value)
    fields = FIELDS | {'lineage', 'mastery'} if version == 2 else FIELDS
    if set(value) != fields:
        raise ValueError('功法效果字段缺失或包含未知字段')
    integer(value['generator_version'], version, version, '生成版本')
    if version == 2:
        from .technique_effect_profiles import PROFILES, UPPER_PROFILES
        if (not isinstance(value['lineage'], str) or value['lineage'] not in PROFILES.keys() | UPPER_PROFILES.keys()
                or type(value['mastery']) is not bool):
            raise ValueError('未知功法传承或合练标记')
        if value['mastery'] and value['lineage'] in UPPER_PROFILES:
            raise ValueError('三界本体功法尚无合练入口')
    if (not isinstance(value['kind'], str) or not isinstance(value['trigger'], str) or not isinstance(value['delivery'], str)
            or value['kind'] not in KINDS or value['trigger'] not in (LINEAGE_TRIGGERS if version == 2 else TRIGGERS) or value['delivery'] not in DELIVERIES):
        raise ValueError('未知功法效果、触发或兑现方式')
    ceiling = 150 if value['kind'] in {'guard', 'recover', 'frugal'} else 1000
    if value.get('mastery'):
        ceiling = ceiling * 6 // 5
    integer(value['strength_bp'], 1, ceiling, '强度')
    integer(value['cost_bp'], 100, 500, '费用')
    integer(value['cooldown'], 0, 3, '冷却')
    integer(value['uses'], 1, 3, '次数')
    integer(value['duration'], 1, 2, '期限')
    integer(value['refund_bp'], 0, 2000, '已付费用返还')
    if value['kind'] != 'frugal' and value['refund_bp']:
        raise ValueError('只有节流式可以返还本次实付费用')
    if value['kind'] == 'frugal' and not value['refund_bp']:
        raise ValueError('节流式须明确有限返还比例')
    if value['kind'] == 'breach' and value['delivery'] == 'split':
        raise ValueError('破法一次交锋修正不能分拆为两次完整修正')
    return copy.deepcopy(value)


def validate_loadout(rows):
    if not isinstance(rows, (tuple, list)) or len(rows) > 8192:
        raise ValueError('功法效果战斗快照超过技术容量')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) not in ({'id','name','level','effect'}, {'id','name','level','effect','cost_model'}):
            raise ValueError('功法效果战斗快照字段无效')
        if 'cost_model' in row:
            terms=row['cost_model']
            if not isinstance(terms,dict) or set(terms)!={'grade','realm','fixed'}:raise ValueError('功法混合费用字段无效')
            integer(terms['grade'],1,12,'费用品阶');integer(terms['realm'],0,12,'费用境界')
            finite(terms['fixed'],.01,10000000.,'固定费用')
        for key in ('id', 'name'):
            if not isinstance(row[key], str) or not 1 <= len(row[key]) <= 160:
                raise ValueError('功法效果身份无效')
        if row['id'] in seen:
            raise ValueError('同一功法不能重复进入战斗快照')
        seen.add(row['id'])
        integer(row['level'], 1, 9, '等级')
        effect = validate_effect(row['effect'])
        if effect.get('version') == 3 and effect.get('identity') != row['id']:
            raise ValueError('固定功法专属配方与原书身份不符')
        normalized={**row,'effect':effect}
        if 'cost_model' in row:normalized['cost_model']=copy.deepcopy(row['cost_model'])
        result.append(normalized)
    return tuple(result)


def describe(effect):
    e = validate_effect(effect)
    if e['version'] == 3:
        if 'mana_cost' in e:
            return (f'{e["clause"] or "本书专属运转"}：Lv.1费用低于自身境界时为{e["mana_cost"]:g}点法力，'
                    f'同阶为开战容量{e["cost_bp"]/100:g}%，越阶为两者之和；每战至多{e["uses"]}次，'
                    'Lv.1—9最多减费16%。完整触发与兑现见功法描述。')
        return (f'{e["clause"] or "本书专属运转"}：低阶按品阶标准固定付费，同阶实付开战'
                f'{"法力" if e["resource"] == "mana" else "元力"}容量的{e["cost_bp"]/100:g}%，越阶为两者之和，'
                f'每战至多{e["uses"]}次，Lv.1—9最多减费16%。完整触发与兑现见功法描述。')
    p = e['strength_bp'] / 100
    trigger = {'opening': '普通交锋可进行时', 'after_hit': '本人上轮普通交锋实际伤及敌人后',
               'after_hurt': '本人上轮普通交锋实际受敌人伤害后', 'first_exchange': '本人本场首次可进行普通交锋时',
               'low_state': '本人态势不高于开战时一半时', 'target_wounded': '存在可作用且态势不高于开战时一半的敌人时',
               'steady': '第三轮起且本人上轮未因普通交锋实际受伤时', 'odd_round': '奇数轮普通交锋时',
               'even_round': '偶数轮普通交锋时'}[e['trigger']]
    payload = {
        'guard': f'获得最多初始最大战斗态势{p:g}%的有限护持，受击逐次扣减余额',
        'strike': f'下一次合法普通交锋追加至多该次原始损耗{p:g}%，不增加攻击次数',
        'recover': f'恢复最多初始最大战斗态势{p:g}%，不能超过开战状态，不修复肉身或复活',
        'breach': f'一次普通交锋的破法提高{p:g}%，不提高仙凡作用资格',
        'frugal': f'获得最多初始最大战斗态势{p:g}%的有限护持；真实减免后返还该次实付资源的{e["refund_bp"]/100:g}%，不重复返还',
    }[e['kind']]
    timing = {'immediate': '本轮准备后使用', 'delayed': '延至下一轮使用',
              'split': '同一份效果额度分两轮各兑现一半'}[e['delivery']]
    return (f'{trigger}，同阶支付原可用元力容量的{e["cost_bp"]/100:g}%；低阶支付对应品阶初层元力标准的固定费用，越阶支付两者之和：{payload}；{timing}。'
            f'每战最多{e["uses"]}次，冷却{e["cooldown"]}个完整轮，待用效果{e["duration"]}轮过期。'
            '无真实可用元力时不发动；Lv.1—9只降低本书费用，最多降低16%，不放大效果。')
