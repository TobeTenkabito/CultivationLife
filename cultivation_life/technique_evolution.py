"""Reviewed exceptional manual progression; no character realm or world mutation."""
FROST = 'TECH_HUNDRED_THOUSAND_FROST'
WIND = 'TECH_LINLAN_DEMON'


def evolve(book):
    if book.id != FROST:
        return book
    immortal = book.level >= 7
    book.grade = 9 if immortal else 8
    book.force_tier = 2 if immortal else 1
    book.requires_immortal_power = immortal
    book.immortal_power_cost = .03 if immortal else 0.
    book.combat_effect = dict(book.combat_effect)
    book.combat_effect['resource'] = 'energy' if immortal else 'mana'
    if immortal:
        book.combat_effect.pop('mana_cost', None)
    return book


def promotion_reason(player, identity, level):
    if identity == FROST and level >= 7 and (player.realm_index < 9 or not player.immortal_power_converted):
        return '仙阶霜阵须达到九阶并完成仙灵力转化，才能合参至 Lv.7 及以上'
    return ''
