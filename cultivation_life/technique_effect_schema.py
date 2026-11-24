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
        raise ValueError('功法效果、触发条件或施展方式无效')
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
        if not isinstance(row, dict) or set(row) - {'damage_profile'} not in ({'id','name','level','effect'}, {'id','name','level','effect','cost_model'}):
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
        if 'damage_profile' in row:
            from .combat_attributes import validate_profile
            normalized['damage_profile'] = validate_profile(row['damage_profile'])
        if 'cost_model' in row:normalized['cost_model']=copy.deepcopy(row['cost_model'])
        result.append(normalized)
    return tuple(result)


def describe(effect):
    e = validate_effect(effect)
    if e['version'] == 3:
        from .technique_effect_copy import mechanics
        prefix=mechanics(e)
        if 'mana_cost' in e:
            return prefix + (f'Lv.1运功消耗：功法品阶低于自身境界时为{e["mana_cost"]:g}点法力，'
                    f'同阶为开战法力容量的{e["cost_bp"]/100:g}%，越阶为两者之和；每战至多{e["uses"]}次，'
                    'Lv.1—9逐步降低消耗，最高降低16%。')
        return prefix + (f'运功消耗：功法品阶低于自身境界时，按此品阶标准消耗固定灵力；同阶消耗开战'
                f'{"法力" if e["resource"] == "mana" else "元力"}容量的{e["cost_bp"]/100:g}%，越阶为两者之和，'
                f'每战至多{e["uses"]}次，Lv.1—9逐步降低消耗，最高降低16%。')
    p = e['strength_bp'] / 100
    trigger = {'opening': '普通交锋时', 'after_hit': '上轮普通攻击伤及敌人后',
               'after_hurt': '上轮受到敌人普通攻击的伤害后', 'first_exchange': '本场首次普通交锋时',
               'low_state': '自身战斗态势低至开战时一半时', 'target_wounded': '场上有战斗态势低至开战时一半的敌人时',
               'steady': '第三轮起，若上轮普通交锋毫发无损', 'odd_round': '奇数轮普通交锋时',
               'even_round': '偶数轮普通交锋时'}[e['trigger']]
    payload = {
        'guard': f'凝聚护身之力，可抵挡最多开战最大态势{p:g}%的伤害，护持随受击逐渐消耗',
        'strike': f'下一次普通攻击追加至多基础伤害的{p:g}%',
        'recover': f'恢复最多初始最大战斗态势{p:g}%，恢复上限为开战状态',
        'breach': f'一次普通交锋的破法提高{p:g}%，依当前仙凡层次作用',
        'frugal': f'凝聚开战最大态势{p:g}%的护身之力；挡下伤害后，可收回本次所耗灵力的{e["refund_bp"]/100:g}%，每次运功可回气一次',
    }[e['kind']]
    timing = {'immediate': '本轮准备后使用', 'delayed': '延至下一轮使用',
              'split': '招式分两轮施展，每轮发挥一半效果'}[e['delivery']]
    return (f'{trigger}，运转此法。{payload}；{timing}。功法与自身境界同阶时，消耗开战元力容量的{e["cost_bp"]/100:g}%；低阶按此品阶初层的标准消耗固定元力，越阶合计两项消耗。'
            f'每战最多{e["uses"]}次，冷却{e["cooldown"]}个完整轮，所蓄招势保留{e["duration"]}轮。'
            '运转需支付所列元力；Lv.1—9逐步减费，最高降低16%。')
