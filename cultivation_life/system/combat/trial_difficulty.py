"""Validated authored trial pressure, independent of worlds and persistence."""
from dataclasses import replace
from math import isfinite


def stage(config,realm,defaults):
    if not isinstance(config,dict) or set(config)-{'9','10','11'}:
        raise ValueError('Invalid high-realm trial stages')
    row=config.get(str(realm),{})
    if not isinstance(row,dict) or set(row)-{'enemy_ratios','field_copy_cap','field_copy_scale'}:
        raise ValueError('Unknown trial pressure setting')
    ratios=row.get('enemy_ratios',defaults)
    if (not isinstance(ratios,(list,tuple)) or len(ratios)!=len(defaults) or
            any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or not 0<v<=2 for v in ratios)):
        raise ValueError('Trial opponents require positive bounded ratios and unchanged roster size')
    cap=row.get('field_copy_cap',8);scale=row.get('field_copy_scale',1.)
    if type(cap) is not int or not 1<=cap<=13:raise ValueError('Invalid copied field rank')
    if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not isfinite(scale) or not 0<scale<=1:
        raise ValueError('Invalid copied field pressure')
    return tuple(ratios),cap,scale


def copied_field(field,scale):
    if scale==1:return field
    # Keep the frozen reference, costs, features and real attack qualification.
    return replace(field,**{key:getattr(field,key)*scale for key in ('strength','stability','incursion','authority')
                            if getattr(field,key) is not None})


def validate_upper_stages(stages, *, monster):
    if not isinstance(stages, dict) or set(stages) != {'9', '10', '11'}:
        raise ValueError('妖鬼劫战须覆盖三个高阶境界')
    for realm, row in stages.items():
        fields = {'title', 'opponents'}
        if monster and realm == '10':
            fields.add('self_lineage_opponents')
        if not isinstance(row, dict) or set(row) != fields or not isinstance(row['title'], str) or not row['title'].strip():
            raise ValueError('妖鬼劫战名称或阵容字段无效')
        for field in fields - {'title'}:
            names = row[field]
            if (not isinstance(names, list) or len(names) != (2 if realm == '11' else 1)
                    or not all(isinstance(name, str) and name.strip() for name in names)):
                raise ValueError('妖鬼劫战对手无效')


def validate_asura_encounters(config):
    encounters = config.get('trial_encounters', {})
    if not isinstance(encounters, dict) or not all(isinstance(encounters.get(key), str) and encounters[key].strip()
                                                  for key in ('fusion_title', 'breakthrough_title')):
        raise ValueError('修罗劫战缺少标题')
    opponents = encounters.get('opponents')
    if not isinstance(opponents, dict) or set(opponents) != {'9', '10', '11'}:
        raise ValueError('修罗劫战须覆盖三个高阶境界')
    for realm, rows in opponents.items():
        if not isinstance(rows, list) or len(rows) != (1 if realm == '9' else 2):
            raise ValueError('修罗劫战对手数量无效')
        for row in rows:
            if (not isinstance(row, dict) or type(row.get('copy_field')) is not bool
                    or not all(isinstance(row.get(k), str) and row[k].strip() for k in ('name', 'visual_variant'))):
                raise ValueError('修罗劫战对手定义无效')
        defaults = tuple(row['ratio'] for row in rows)
        stage({}, realm, defaults)
        stage(config.get('breakthrough_trials', {}), realm, defaults)


def validate(systems):
    for world in systems.get('upper_voisinages',{}).get('worlds',{}).values():
        for row in world.get('fields',[]):
            factor=row.get('strength_factor',1.)
            if isinstance(factor,bool) or not isinstance(factor,(int,float)) or not isfinite(factor) or not 0<factor<=3:
                raise ValueError('Invalid authored field strength multiplier')
    upper=systems.get('upper_voisinages',{}).get('breakthrough_trials',{})
    if not isinstance(upper,dict) or set(upper)-{'monster','ghost'}:raise ValueError('Unknown upper trial path')
    for family,config in upper.items():
        for realm in (9,10,11):stage(config,realm,(1.,1.) if realm==11 else (1.,))
    if 'asura_manifestation' in systems:
        validate_asura_encounters(systems['asura_manifestation'])
    threshold=systems.get('asura_manifestation',{}).get('restore_threshold',1.)
    if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not isfinite(threshold) or not 0<threshold<=1:
        raise ValueError('Invalid automatic restoration threshold')
