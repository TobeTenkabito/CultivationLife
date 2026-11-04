"""Growth-coordinate baselines, in opportunity-equivalent training units.

Ordinary cultivation uses the original breakthrough curve. Body and sense use
their actual progress/experience thresholds, one point per reference unit. This
is a balance denominator, not a claim that players pay opportunity for those axes.
"""
from ...content_registry import REALMS, WORLD_SYSTEMS
from ...cultivation_costs import opportunity_required
from ...rules import divine_sense_level_threshold
from types import SimpleNamespace


def reference_cost(before,after,axis):
    if axis=='cultivation':
        r,l=before['realm_index'],before['layer'];total=0
        while (r,l)<(after['realm_index'],after['layer']):
            if r>=9:
                from ..doctrine.cultivation import immortal_breakthrough_cost
                from ..immortal_cultivation import rules as immortal_rules
                total+=immortal_breakthrough_cost(r,l,immortal_rules())
            else:total+=opportunity_required(SimpleNamespace(realm_index=r,layer=l))
            r,l=(r,l+1) if l<REALMS[r].layers else (r+1,1)
        return float(total)
    if axis=='conversion':
        from ..conversion import COSTS
        start=round(float((before.get('transcendence') or {}).get('conversion',0))*5)
        end=round(after['transcendence']['conversion']*5)
        return float(sum(COSTS[start:end]))
    if axis=='sense':
        return divine_sense_level_threshold(after['divine_sense_rank'])-divine_sense_level_threshold(before['divine_sense_rank'])
    rules=WORLD_SYSTEMS['body_cultivation']
    ordinary=sum(float(rules['progress_base'])+n*float(rules['progress_per_layer'])
                 for n in range(before['body_training'],after['body_training']))
    # Existing high-body coordinates have a separate 50-step progression.
    from ..immortal_cultivation import rules as immortal_rules
    high=sum(immortal_rules()['vein_opportunity_base']*(1+n) for n in range(before['immortal_body_level'],after['immortal_body_level']))
    return ordinary+high
