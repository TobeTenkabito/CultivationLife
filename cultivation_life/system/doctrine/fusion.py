"""Pure collection recipe, stable manual compiler and combat projection."""
import copy
from dataclasses import replace

from .generation import rng_for


def manual_id(key):
    return key + ':concordance'


def eligible(definition):
    return len(definition['manuals']) >= 6


def compile_manual(seed, definition, words):
    books = definition['manuals']
    if not eligible(definition):
        raise ValueError('至少六部原始功法的道统才能合练')
    rng = rng_for(0 if definition['fixed'] else seed, 1, definition['id'] + ':fusion')
    book = copy.deepcopy(books[0])
    book.update(id=manual_id(definition['id']), level=1, grade=max(b['grade'] for b in books),
                name=rng.choice(words['prefixes']) + rng.choice(words['manual_verbs']) + '归一真典',
                growth_preference='balanced')
    for stat in ('combat_bonus', 'hp_bonus', 'mp_bonus', 'opportunity_bonus'):
        book[stat] = round(max(b[stat] for b in books) * (2.2 if stat == 'combat_bonus' else 1.8), 3)
    return book


def project(field, level):
    """Enhance the field's own operations; no extra effect or energy creation."""
    if level <= 0:
        return field
    gain = .08 + .02 * (min(9, level) - 1)
    primary = next((f['kind'] for f in field.features), 'opening')
    changes = {'name': field.name if field.name.startswith('真·') else '真·' + field.name}
    if primary in {'fortify', 'shelter', 'retaliate'}:
        changes['stability'] = (field.stability or field.strength) * (1 + gain)
    if primary in {'opening', 'sacrifice', 'execution'}:
        changes['incursion'] = (field.incursion or field.strength) * (1 + gain)
    if primary == 'frugal':
        changes.update(opening_cost=field.opening_cost * (1-gain), upkeep_cost=field.upkeep_cost * (1-gain))
    changes['authority'] = (field.authority or field.authority_reference) * (1 + gain / 2)
    changes['effects'] = tuple(replace(e,
        power=min(1, e.power * (1 + gain)) if e.kind == 'strike' or e.kind.startswith('restore_') else e.power,
        cost=e.cost * (1-gain) if primary == 'frugal' else e.cost) for e in field.actions())
    return replace(field, **changes)
