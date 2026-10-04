"""Cultivation is owned by the cultivator; worlds reject exposed excess power."""

from ..content_registry import WORLD_SYSTEMS


def destination(player):
    profile = WORLD_SYSTEMS["world_profiles"][player.world]
    tier = profile["tier"]
    rank = (player.realm_index, player.layer)
    if tier == -1:
        return None
    # Concealment only fools observers. Suppression and historical seals really
    # reduce the rank used for abilities, and therefore permit a lower stay.
    suppressed = bool(player.cultivation_suppression or player.sealed_cultivation)
    exceeds = (
        tier == 1
        and (rank > (5, 9) or rank >= (5, 7) and not suppressed)
        or tier in {0, 2}
        and rank >= (9, 1)
    )
    if not exceeds:
        return None
    wanted = 3 if rank >= (9, 1) else 2
    route = next(
        r
        for r in WORLD_SYSTEMS["cultivation_routes"].values()
        if player.path in r["paths"]
    )
    return next(
        (
            s["world"]
            for s in route["stages"]
            if s.get("world")
            and WORLD_SYSTEMS["world_profiles"][s["world"]]["tier"] == wanted
            and WORLD_SYSTEMS["world_profiles"][s["world"]]["enabled"]
        ),
        None,
    )


def descent_rank(player):
    true = player.cultivation_suppression or player.sealed_cultivation or {}
    return (
        int(true.get("realm_index", player.realm_index)),
        int(true.get("layer", player.layer)),
    )


def can_descend(player, target_tier):
    ceiling = (5, 9) if target_tier == 1 else (8, 9)
    return bool(
        player.cultivation_suppression
        and descent_rank(player) >= (6 if target_tier == 1 else 9, 1)
        and (player.realm_index, player.layer) <= ceiling
    )
