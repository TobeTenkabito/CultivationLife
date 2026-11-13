"""Shared conventional damage curve; unaware of voisinages and persistence."""


def exchange_damage(attack: float, defense: float, breach_ratio: float, wave: float,
                    *, coefficient: float, minimum: float, maximum: float) -> float:
    # Keep the historical minimum argument for existing callers only. A weak
    # attack cannot guarantee a fixed fraction of a much stronger opponent.
    return max(0., min(maximum,
        coefficient * (attack / max(1.0, defense)) ** 0.58
        * (0.88 + min(0.28, breach_ratio * 0.13)) * wave))
