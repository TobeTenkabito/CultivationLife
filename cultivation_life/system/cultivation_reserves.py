"""Resource reserve policy independent of bloodline progression actions."""


def immortal_reserve(player):
    seal = player.sealed_cultivation or {}
    return (max(player.realm_index, int(seal.get('realm_index', 0))) >= 9
            and (player.world == 'celestial' or seal.get('upper_world') == 'celestial'))


def opportunity_unbounded(player):
    """Spendable upper-world reserves survive temporary lower-world sealing."""
    from .asura import enabled
    seal = player.sealed_cultivation or {}
    asura_reserve = (enabled() and player.path == 'demonic'
                     and max(player.realm_index, int(seal.get('realm_index', 0))) >= 9
                     and (player.world == 'asura' or seal.get('upper_world') == 'asura'))
    return immortal_reserve(player) or asura_reserve
