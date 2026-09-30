"""Stable effect enrichment without rerolling names, stats or future stages."""
from .generation import rng_for


def ensure_offensive_doctrine(definitions, seed, version):
    """Guarantee one random tradition can strike from Lv4 through Lv9.

    Run only at catalog generation or its one-time save migration. An isolated
    stream keeps names, books, cultivation rolls and the main game RNG intact.
    """
    candidates = {key: definition for key, definition in definitions.items()
                  if not definition.get('fixed')}
    if not candidates:
        return False

    def can_strike(domain):
        if 'effects' not in domain:
            return domain.get('effect') == 'strike' and domain.get('effect_power', 0) > 0
        return any(effect.get('kind') == 'strike' and effect.get('target', 'enemy') == 'enemy'
                   and effect.get('power', 0) > 0 for effect in domain['effects'])

    def fields(definition):
        return [stage['voisinage'] for stage in definition['stages'] if stage['level'] >= 4]

    if any(all(can_strike(domain) for domain in fields(d)) for d in candidates.values()):
        return False
    offensive = [key for key, d in candidates.items()
                 if any(f['kind'] in {'opening', 'sacrifice', 'execution'}
                        for f in fields(d)[0].get('features', ()))]
    key = rng_for(seed, version, 'offensive-guarantee').choice(sorted(offensive or candidates))
    for domain in fields(candidates[key]):
        if not can_strike(domain):
            domain['effects'].append(dict(kind='strike', cost=domain['effect_cost'],
                                          power=domain['effect_power'], target='enemy',
                                          defense='ward', tier=2))
    return True


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
