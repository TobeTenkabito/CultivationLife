"""Player energy ledger and realm rules shared by combat and cultivation.

Migration and resource writes retain their original timing; no presentation,
action dispatch, doctrine catalog or institution dependencies belong here.
"""
from ..content_registry import WORLD_SYSTEMS
from ..rules import max_mp


def true_realm(player):
    return max(player.realm_index, int((player.sealed_cultivation or {}).get('realm_index', 0)))


def cultivation_stage(player):
    sealed = player.sealed_cultivation or {}
    realm, layer = max((player.realm_index, player.layer),
                       (int(sealed.get('realm_index', 0)), int(sealed.get('layer', 1))))
    return max(0, (realm - 9) * 3 + (max(1, layer) - 1) // 3)


def investment_multiplier(player):
    return 1 if lower_world(player) else 1 + .5 * cultivation_stage(player)


def spirit_books(player):
    return [t for t in player.known_techniques if t.spirit_voisinage_id and t.level >= 4 and t.active_in(player.world)]


def lower_world(player):
    return WORLD_SYSTEMS['world_profiles'].get(player.world, {}).get('tier', 1) < 3


def available(player):
    return true_realm(player) >= 9 or bool(spirit_books(player))


def ensure_aperture(player):
    if not available(player):
        return False
    capacity = 1000 * (1 + cultivation_stage(player))
    if player.immortal_aperture:
        old = player.immortal_aperture['capacity']
        player.immortal_aperture['capacity'] = max(old, capacity)
        return old != player.immortal_aperture['capacity']
    # One-time legacy conversion. Subsequent loads and realm crossings conserve reserves.
    player.immortal_aperture = {'version': 1, 'capacity': capacity,
        'current': capacity * min(1, max(0, player.mp / max_mp(player))) if player.immortal_power_converted else 0,
        'imitation_current': 0, 'imitation_capacity': 60}
    return True


def energy_state(player):
    ensure_aperture(player)
    if not available(player):
        return None
    ledger = player.immortal_aperture
    lower = lower_world(player)
    from .immortal_cultivation import golden_light
    from .asura import active as asura_active
    asura_conversion = player.asura_cultivation.get('conversion', 0) if asura_active(player) else 0
    converted = player.immortal_power_converted or player.immortal_conversion_stage > 0 or asura_conversion > 0
    return dict(version=1, resource_link='independent',
        capacity=ledger['imitation_capacity'] if lower else ledger['capacity'],
        current=ledger['imitation_current'] if lower else ledger['current'],
        conversion=asura_conversion / 5 if asura_active(player) else 1,
        force_tier=2 if converted and true_realm(player) >= 9 else 1,
        ward_tier=2 if golden_light(player) else 1,
        attack_cost=1 if lower else 10, ward_cost=0)


def commit_energy(player, current):
    ensure_aperture(player)
    ledger = player.immortal_aperture
    pool, capacity = ('imitation_current', 'imitation_capacity') if lower_world(player) else ('current', 'capacity')
    ledger[pool] = max(0, min(ledger[capacity], current))
