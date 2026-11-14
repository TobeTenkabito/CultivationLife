"""Shared cultivation quotes; callers supply world policy explicitly."""
from .content_registry import REALMS
from .models import Player


def opportunity_required(player: Player) -> int:
    current = REALMS[player.realm_index]
    return round(current.opportunity_base * (1 + 0.12 * (player.layer - 1)))


def breakthrough_cost(player: Player, *, upper_cultivation: bool) -> int:
    if upper_cultivation and 9 <= player.realm_index <= 12:
        from .system.doctrine.cultivation import immortal_breakthrough_cost
        from .system.immortal_cultivation import rules as immortal_rules
        amount = immortal_breakthrough_cost(player.realm_index, player.layer, immortal_rules())
    else:
        amount = opportunity_required(player)
    from .system.technique_secret_rules import bonus as secret_bonus
    import math
    return max(1,math.ceil(amount*(1-secret_bonus(player,'cost_discount'))))
