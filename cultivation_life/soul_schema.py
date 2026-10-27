"""Strict structure-11 personal soul ledger validation."""
import copy
from .soul_rules import SECRETS, validate_energy


def validate_nascent(value, *, age=0):
    if not isinstance(value, dict) or set(value) - {'known', 'revision', 'second', 'refining', 'stagnant', 'depleted', 'crisis', 'last_year'}:
        raise ValueError('元婴账本结构无效')
    value = copy.deepcopy(value)
    if any(x not in SECRETS for x in value.get('known', [])):
        raise ValueError('未知元婴秘法')
    for key in ('revision', 'last_year'):
        if key in value and (type(value[key]) is not int or value[key] < 0):
            raise ValueError('元婴时钟无效')
    for key in ('stagnant', 'depleted'):
        if key in value and type(value[key]) is not bool:
            raise ValueError('魂伤标记无效')
    if value.get('crisis') not in (None, 'possession'):
        raise ValueError('魂伤危机无效')
    for key in ('second', 'refining'):
        row = value.get(key)
        if row is None:
            continue
        keys = {'id', 'due', 'interval', 'integrity', 'auto', 'equipment', 'control', 'age_year'} if key == 'second' else {'id', 'years'}
        if key == 'second' and isinstance(row, dict):
            # Structure-11 additions: adopt once, without retroactively aging an old soul.
            row.setdefault('control', 100.)
            row.setdefault('age_year', age)
        if not isinstance(row, dict) or set(row) != keys or not isinstance(row.get('id'), str):
            raise ValueError('第二元婴来源无效')
        if key == 'refining':
            if type(row['years']) is not int or not 0 <= row['years'] < 3:
                raise ValueError('炼化进度无效')
        else:
            for field in ('due', 'interval', 'integrity', 'control'):
                validate_energy(row[field])
            if (row['interval'] < 1 or row['integrity'] > 100 or row['control'] > 100
                    or type(row['age_year']) is not int or not 0 <= row['age_year'] <= age
                    or type(row['auto']) is not bool):
                raise ValueError('同化状态无效')
            if not isinstance(row['equipment'], list) or len(row['equipment']) > 3:
                raise ValueError('元婴装备无效')
            for item in row['equipment']:
                if not isinstance(item, dict) or type(item.get('quantity')) is not int or item['quantity'] != 1:
                    raise ValueError('元婴装备数量无效')
    return value
