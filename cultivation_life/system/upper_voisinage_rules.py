"""World-local voisinage definitions and combat projection, without UI or government actions."""
from ..content_registry import WORLD_SYSTEMS
from .combat.contracts import CapabilitySource, VoisinageDefinition, VoisinageEffect


def config():
    return WORLD_SYSTEMS.get('upper_voisinages', {})


def world_config(player):
    return config().get('worlds', {}).get(player.world)


def available(player):
    return bool(world_config(player)) and player.realm_index >= 9


def record(player):
    return player.world_voisinages.get(player.world, {})


def level(player, key):
    return max(0, min(9, int(record(player).get('levels', {}).get(key, 0))))


def definitions(player):
    from .monster_true_form import definition
    rows = list((world_config(player) or {}).get('fields', []))
    dynamic = definition(player)
    if dynamic:
        rows.append(dynamic)
    return rows


def project(definition, rank):
    strength = config()['strengths'][rank - 1]
    cost = 20 + 4 * rank
    kinds = list(definition['effects'])
    weights = [definition[k] for k in ('stability', 'incursion', 'authority')]
    if definition.get('true_form'):
        if rank >= 4 and definition.get('secondary'):
            kinds.append(definition['secondary'])
        if rank >= 7:
            from .monster_true_form import TUNINGS
            weights = [v + delta for v, delta in zip(weights, TUNINGS[definition['tuning']][1])]
    effects = tuple(VoisinageEffect(kind, cost, .2 if kind == 'strike' else .15,
        target='self' if kind.startswith('restore_') else 'enemy',
        restriction='technique' if kind == 'restrict' else 'support' if kind == 'isolate' else None) for kind in kinds)
    return VoisinageDefinition(id=definition['id'], name=definition['name'],
        attainment=definition['id'], required_level=1, strength=strength,
        stability=round(strength * weights[0], 2),
        incursion=round(strength * weights[1], 2),
        authority=round(strength * weights[2], 2),
        opening_cost=45 + 5 * rank, upkeep_cost=15 + 2 * rank,
        effect=effects[0].kind, effect_cost=cost, effect_power=effects[0].power,
        max_investment=120, extra_target_cost=5, max_targets=3,
        effects=effects, features=(definition['feature'],))


def player_source(player):
    from .asura import active as asura_active, source as asura_source
    if asura_active(player):
        return asura_source(player)
    if not available(player):
        return CapabilitySource()
    key = record(player).get('active')
    definition = next((d for d in definitions(player) if d['id'] == key), None)
    rank = level(player, key)
    if not definition or not rank:
        return CapabilitySource()
    return CapabilitySource((project(definition, rank),), {key: rank})
