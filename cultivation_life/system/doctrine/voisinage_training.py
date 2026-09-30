"""Independent voisinage attainment; old axis investments remain intact."""
from dataclasses import replace

STAGES = ('初成', '化境', '大成', '至臻')
MAX_RANK = 13
BOUNDARIES = (4, 8, 12)


def rank(training):
    return max(1, min(MAX_RANK, int(training.get('rank', 1))))


def label(value):
    value = max(1, min(MAX_RANK, value))
    return '至臻' if value == 13 else f'{STAGES[(value - 1) // 4]}{(value - 1) % 4 + 1}层'


def multiplier(value):
    return 1 + .22 * (max(1, min(MAX_RANK, value)) - 1)


def project(definition, training):
    factor = multiplier(rank(training))
    return replace(definition, **{axis: getattr(definition, axis) * factor
        for axis in ('stability', 'incursion', 'authority') if getattr(definition, axis) is not None})


def cost(training, rules):
    value = rank(training)
    return {'opportunity': rules['voisinage_opportunity_base'] * value * 4,
            'traces': rules['voisinage_trace_base'] * value * 4}


def public(training, rules):
    value = rank(training)
    return dict(rank=value, label=label(value), stage=STAGES[(value - 1) // 4],
                layer=None if value == 13 else (value - 1) % 4 + 1, maximum=13,
                next_label=label(value + 1) if value < 13 else None,
                backlash=value in BOUNDARIES, cost=cost(training, rules) if value < 13 else None)


def dao_ancestor(game):
    record = game.doctrine_state.get('player', {})
    return (game.player.realm_index >= 12
            and any(p.get('level', 0) >= 9 for p in record.get('progress', {}).values())
            and any(record.get('progress', {}).get(key, {}).get('level', 0) >= 4 and rank(t) == 13
                    for key, t in record.get('voisinage_training', {}).items()))
