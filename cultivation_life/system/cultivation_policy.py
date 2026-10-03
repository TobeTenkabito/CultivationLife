"""World-specific progression policy, shared by presentation and cultivation."""

from .cultivation_reserves import (
    immortal_reserve as immortal_reserve,
    opportunity_unbounded as opportunity_unbounded,
)

ORDINARY_UPPER_WORLDS = frozenset({'asura', 'nether', 'reincarnation'})


def ordinary_upper(actor):
    return actor.world in ORDINARY_UPPER_WORLDS and 9 <= actor.realm_index <= 12


def bloodline_upper(player, available=None):
    if player.path != 'monster' or player.world != 'nether' or player.realm_index < 9:
        return False
    if available is None:
        from .monster_bloodline_system import bloodline_content_available
        available = bloodline_content_available()
    return bool(available)
