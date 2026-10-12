"""Small immutable reward recipes; no executable effects or mutable catalog registration."""
import math

FAMILIES = {
    'technique': {'combat_bonus', 'hp_bonus', 'mp_bonus', 'opportunity_bonus'},
    'artifact': {'combat_power', 'max_hp', 'max_mp'},
    'treasure': {'combat_bonus', 'hp_bonus', 'mp_bonus'},
    'item': {'permanent_intrinsic_hp_bonus', 'permanent_intrinsic_mp_bonus'},
}


def validate_reward(reward):
    if set(reward) != {'kind', 'content_id', 'name', 'tier', 'roll'}:
        raise ValueError('随机遗宝字段无效')
    roll = reward['roll']
    if not isinstance(roll, dict) or set(roll) != {'family', 'path', 'quality', 'stats'}:
        raise ValueError('随机遗宝配方无效')
    family = roll['family']
    if family not in FAMILIES or reward['kind'] != ('technique' if family == 'technique' else 'item'):
        raise ValueError('随机遗宝种类无效')
    if roll['path'] not in {'dao', 'demonic', 'monster', 'ghost', 'buddhist', 'confucian'}:
        raise ValueError('随机遗宝道途无效')
    if roll['quality'] not in {'上品', '极品', '绝品'}:
        raise ValueError('随机遗宝品相无效')
    if not isinstance(reward['content_id'], str) or not reward['content_id'].startswith('RELIC_') or len(reward['content_id']) > 120:
        raise ValueError('随机遗宝身份无效')
    if not isinstance(reward['name'], str) or not 1 <= len(reward['name']) <= 120:
        raise ValueError('随机遗宝名号无效')
    if type(reward['tier']) is not int or not 1 <= reward['tier'] <= 12:
        raise ValueError('随机遗宝品阶无效')
    stats = roll['stats']
    if not isinstance(stats, dict) or not stats or set(stats) - FAMILIES[family]:
        raise ValueError('随机遗宝属性无效')
    if family == 'technique' and set(stats) != FAMILIES['technique']:
        raise ValueError('随机功法须包含完整修炼属性')
    for value in stats.values():
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= 1e18:
            raise ValueError('随机遗宝数值无效')
