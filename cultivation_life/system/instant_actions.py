"""One immediate encounter per action type and lived year, persisted in saves."""

INSTANT_ACTIONS = frozenset({'spar', 'capture', 'slay', 'befriend_neighbors'})


def available(player, action):
    return player.instant_action_ages.get(action) != player.age


def public(player):
    return {action: available(player, action) for action in sorted(INSTANT_ACTIONS)}
