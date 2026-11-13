"""Original-person ordinary mana; independent of immortal energy and inventory."""
import copy
from .technique_effect_schema import finite


def validate(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'capacity', 'current', 'at', 'world'}:
        raise ValueError('人物普通法力账本字段无效')
    capacity = finite(value['capacity'], 0, 1e30, '人物法力容量')
    finite(value['current'], 0, capacity, '人物当前法力')
    if value['at'] is not None:
        finite(value['at'], 0, 1e15, '人物法力时钟')
    if not isinstance(value['world'], str):
        raise ValueError('人物法力归属界面无效')
    return copy.deepcopy(value)
