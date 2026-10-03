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
        return immortal_breakthrough_cost(player.realm_index, player.layer, immortal_rules())
    return opportunity_required(player)
