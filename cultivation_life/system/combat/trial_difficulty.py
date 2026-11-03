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
    config=systems.get('asura_manifestation',{}).get('breakthrough_trials',{})
    for realm,defaults in ((9,(1.,)),(10,(1.,.8)),(11,(1.5,1.))):stage(config,realm,defaults)
    threshold=systems.get('asura_manifestation',{}).get('restore_threshold',1.)
    if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not isfinite(threshold) or not 0<threshold<=1:
        raise ValueError('Invalid automatic restoration threshold')
