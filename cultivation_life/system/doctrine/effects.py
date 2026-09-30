"""Stable effect enrichment without rerolling names, stats or future stages."""
from .generation import rng_for


def enrich_effects(definitions):
    changed = False
    for key, definition in definitions.items():
        for stage in definition['stages']:
            domain = stage.get('voisinage')
            if not domain or 'effects' in domain:
                continue
            primary = next((f['kind'] for f in domain.get('features', ())), 'opening')
            # An isolated stream means migrating a saved catalog never changes
            # its immutable names, numerical dimensions or cultivation rolls.
            choices = {
                'shelter': ['restore_body', 'restore_spirit'],
                'frugal': ['restore_spirit', 'restore_body'],
                'fortify': ['restore_field', 'seal'],
                'retaliate': ['restore_field', 'restrict'],
                'opening': ['restrict', 'isolate'],
                'sacrifice': ['isolate', 'strike'],
                'execution': ['strike', 'restrict'],
            }[primary]
            secondary = rng_for(0, 1, key + ':effects').choice(choices)
            kinds = list(dict.fromkeys([domain['effect'], secondary]))
            if stage['level'] >= 6:
                kinds = list(dict.fromkeys([*kinds, 'suppress' if primary == 'execution' else choices[-1]]))
            domain['effects'] = []
            for kind in kinds:
                entry = dict(kind=kind, cost=domain['effect_cost'], power=domain['effect_power'],
                             target='ally' if kind.startswith('restore_') else 'enemy',
                             defense='ward' if kind == 'strike' else 'bypass', tier=2)
                if kind in {'restrict', 'isolate'}:
                    entry['restriction'] = 'technique' if kind == 'restrict' else 'artifact'
                domain['effects'].append(entry)
            changed = True
    return changed
