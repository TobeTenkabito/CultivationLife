"""Pure validation for the optional, data-only true-form catalog."""
import math

EFFECTS = {'strike', 'suppress', 'seal', 'restrict', 'isolate',
           'restore_body', 'restore_spirit', 'restore_field'}
FEATURES = {'fortify', 'opening', 'retaliate', 'sacrifice', 'frugal', 'shelter'}


def validate(document, species, evolutions=None):
    if not isinstance(document, dict) or document.get('schema_version') != 1 or document.get('blueprint_version') != 1:
        raise ValueError('本相目录版本不受支持')
    rows = document.get('forms')
    if not isinstance(rows, dict) or set(rows) != set(species):
        raise ValueError('本相目录须覆盖全部本源种属')
    for key, row in rows.items():
        if evolutions is not None:
            for route in ('TRUE', 'SELF'):
                for stage in range(1, 5):
                    node = evolutions.get(f'{key.upper()}_NETHER_{route}_{stage}', {})
                    if node.get('species') != key or node.get('realm_index') != stage + 8:
                        raise ValueError('本相缺少合法的高阶血脉引用')
        if not isinstance(row, dict) or set(row) != {'name', 'description', 'effects', 'feature', 'stability', 'incursion', 'authority'}:
            raise ValueError(f'本相 {key} 含未知或缺失字段')
        if not all(isinstance(row[k], str) and 1 <= len(row[k]) <= 180 for k in ('name', 'description')):
            raise ValueError('本相名称与描述无效')
        if not isinstance(row['effects'], list) or len(row['effects']) != 2 or any(e not in EFFECTS for e in row['effects']) or len(set(row['effects'])) != 2:
            raise ValueError('本相须有两项不同的合法权能')
        feature = row['feature']
        if not isinstance(feature, dict) or set(feature) != {'kind', 'value'} or feature['kind'] not in FEATURES:
            raise ValueError('本相特征无效')
        values = [row[k] for k in ('stability', 'incursion', 'authority')] + [feature['value']]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('本相预算须为有限数值')
        if any(not .8 <= v <= 1.2 for v in values[:3]) or sum(values[:3]) > 3.000001 or not 0 < values[3] <= .12:
            raise ValueError('本相超出统一强度预算')
