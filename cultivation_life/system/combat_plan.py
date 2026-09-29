"""Player-owned decisions compiled at the combat boundary; no NPC tick work."""
from .combat.contracts import number

DEFAULTS = dict(manual=False, stance='press', investment=0.0, burst='auto',
                mp_reserve=.28, transformations=True, support_guard=True)


def effective_plan(player):
    saved = {**DEFAULTS, **player.combat_plan}
    return saved if saved['manual'] else dict(DEFAULTS)


def public_plan(player):
    from .immortal_aperture import investment_multiplier
    return {**DEFAULTS, **player.combat_plan, 'investment_multiplier': investment_multiplier(player)}


def validate_plan(payload):
    allowed = set(DEFAULTS) - {'manual'}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError('未知战斗预案字段')
    data = dict(payload)
    if 'stance' in data and data['stance'] not in {'press', 'guard', 'protect', 'off'}:
        raise ValueError('未知邻域姿态')
    if 'burst' in data and data['burst'] not in {'auto', 'early', 'never'}:
        raise ValueError('未知爆发策略')
    for key in ('transformations', 'support_guard'):
        if key in data and type(data[key]) is not bool:
            raise ValueError('预案开关必须为布尔值')
    for key, maximum in (('investment', 1000000), ('mp_reserve', 1)):
        if key in data:
            data[key] = number(data[key], key)
            if data[key] > maximum:
                raise ValueError('预案数值超出范围')
    return data
