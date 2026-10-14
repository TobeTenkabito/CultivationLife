"""Shared pure local-world strength projection for fields and residual manuals."""
from ..content_registry import WORLD_SYSTEMS
from .combat.contracts import VoisinageDefinition, VoisinageEffect


def project(definition, rank, cap=None):
    strength = WORLD_SYSTEMS['upper_voisinages']['strengths'][min(rank, cap or 13) - 1]
    cost = 20 + 4 * rank
    kinds = list(definition['effects'])
    weights = [definition[k] for k in ('stability', 'incursion', 'authority')]
    if definition.get('true_form'):
        if rank >= 5 and definition.get('secondary'):
            kinds.append(definition['secondary'])
        if rank >= 9:
            from .monster_true_form import TUNINGS
            weights = [v + delta for v, delta in zip(weights, TUNINGS[definition['tuning']][1])]
    features = (definition['feature'],) if definition.get('feature') else ()
    if definition.get('soul_form'):
        kinds = definition['effects'][:1]
        if rank >= 5 and definition.get('secondary'):
            kinds = [*definition['effects'], definition['secondary']]
        kinds = list({(e['kind'], e.get('restriction')): e for e in kinds}.values())
        effects = tuple(VoisinageEffect(e['kind'], round(cost * definition['effect_factor'], 2),
            .2 if e['kind'] == 'strike' else .15,
            target='self' if e['kind'].startswith('restore_') else 'enemy', restriction=e.get('restriction')) for e in kinds)
        features = ({'kind': definition['feature'], 'value': .1},) if rank >= 9 and definition.get('feature') else ()
    else:
        effects = tuple(VoisinageEffect(kind, cost, .2 if kind == 'strike' else .15, target='self' if kind.startswith('restore_') else 'enemy',
            restriction='technique' if kind == 'restrict' else 'support' if kind == 'isolate' else None) for kind in kinds)
    inherited = definition.get('inheritance_template')
    if inherited:
        total = sum(weights)
        weights = [(v * 3 / total + inherited[k]) / 2
                   for v, k in zip(weights, ('stability', 'incursion', 'authority'))]
    return VoisinageDefinition(id=definition['id'], name=definition['name'], attainment=definition['id'],
        required_level=1, strength=strength, stability=round(strength * weights[0], 2),
        incursion=round(strength * weights[1], 2), authority=round(strength * weights[2], 2),
        opening_cost=(45 + 5 * rank) * definition.get('opening_factor', 1), upkeep_cost=(15 + 2 * rank) * definition.get('upkeep_factor', 1),
        effect=effects[0].kind, effect_cost=effects[0].cost, effect_power=effects[0].power,
        max_investment=120, extra_target_cost=5, max_targets=3, effects=effects, features=features)
