"""Absolute ordinary resource references; no equipment or enlarged pool tax."""


def mana_reference(base_power, layer=1, body_training=0):
    return float(40 + int(base_power ** .5 * 20) + layer * 11 + body_training * 10)


def health_reference(base_power, layer=1, body_training=0):
    return float(100 + int(base_power ** .5 * 16) + layer * 8 + body_training * 12)


def exertion(own_power, opposing_power):
    # Equal or stronger opposition demands full effort; weak opposition does
    # not turn a larger mana reserve into a larger mandatory expense.
    return min(1., max(0., opposing_power) / max(1., own_power)) ** .5


def technique_cost(book, capacity):
    effect = book['effect']
    rate = capacity * effect['cost_bp'] / 10000
    if 'cost_model' in book:
        terms=book['cost_model']
        return graded_cost(terms['grade'],terms['realm'],terms['fixed'],rate) * (1 - .02 * (book['level'] - 1))
    base = (effect['mana_cost'] if effect.get('resource') == 'mana' and 'mana_cost' in effect
            else rate)
    return base * (1 - .02 * (book['level'] - 1))


def graded_cost(grade, realm, fixed, proportional):
    if grade<realm:return fixed
    if grade==realm:return proportional
    return fixed+proportional
