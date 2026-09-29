"""Shared conventional damage curve; unaware of voisinages and persistence."""


def exchange_damage(attack: float, defense: float, breach_ratio: float, wave: float,
                    *, coefficient: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum,
        coefficient * (attack / max(1.0, defense)) ** 0.58
        * (0.88 + min(0.28, breach_ratio * 0.13)) * wave))
