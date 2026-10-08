"""Registry-independent validation of the optional soul-form catalog."""
import math

EFFECTS = {'strike', 'suppress', 'seal', 'restrict', 'isolate', 'restore_body', 'restore_spirit', 'restore_field'}
RESTRICTIONS = {'technique', 'support', 'voisinage'}
FEATURES = {'fortify', 'opening', 'retaliate', 'sacrifice', 'frugal', 'shelter', 'execution'}


def validate(doc):
    if doc.get('schema_version') != 1 or doc.get('blueprint_version') != 1:
        raise ValueError('魂相目录版本无效')
    causes, forms = doc['causes'], doc['forms']
    if len(causes) != 12 or len(forms) != 36:
        raise ValueError('魂相须覆盖十二魂因和三条道路')
    if set(forms) != {f'{cause}.{route}' for cause in causes for route in ('guard', 'sever', 'transmute')}:
        raise ValueError('魂相目录不完整')
    for key, row in forms.items():
        if row['cause'] + '.' + row['route'] != key:
            raise ValueError('魂相身份不符')
        for field in ('name', 'description', 'weakness', 'battle_role'):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError('魂相缺少说明')
        weights = [row[k] for k in ('stability', 'incursion', 'authority')]
        if any(type(v) not in (int, float) or not math.isfinite(v) or not .6 <= v <= 1.4 for v in weights) or sum(weights) > 3.00001:
            raise ValueError('魂相三维超出预算')
        effects = row['effects']
        if len(effects) != 2 or len(row['secondary_choices']) not in range(2, 5):
            raise ValueError('魂相主辅候选无效')
        for effect in effects + row['secondary_choices']:
            if effect['kind'] not in EFFECTS or set(effect) - {'kind', 'restriction'}:
                raise ValueError('未知魂相权能')
            if effect['kind'] in {'restrict', 'isolate'} and effect.get('restriction') not in RESTRICTIONS:
                raise ValueError('魂相禁制缺少合法对象')
        if len({(e['kind'], e.get('restriction')) for e in row['secondary_choices']}) != len(row['secondary_choices']):
            raise ValueError('辅权能候选重复')
        if not 2 <= len(row['feature_choices']) <= 3 or not set(row['feature_choices']) <= FEATURES:
            raise ValueError('魂痕候选无效')
        for k in ('opening_factor', 'upkeep_factor', 'effect_factor'):
            if not .8 <= row[k] <= 1.25:
                raise ValueError('魂相费用超出预算')
