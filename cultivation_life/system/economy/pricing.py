"""Bounded economic rules, independent of saves and random streams."""
import math

_FLOOR = math.log(.35)
_CEILING = math.log(3.)


def growth(scale: float, years: int, rate: float = .003, ceiling: float = 1000.) -> float:
    """Logistic growth: the initial scale is one, not the player's age."""
    return min(ceiling, ceiling / (1 + (ceiling / scale - 1) * math.exp(-rate * years)))


def price_multiplier(stock: float, target: float) -> float:
    return min(3., max(.35, math.exp(max(-10., min(10., (1 - stock / max(1., target)) * .7)))))


def total_price(reference: float, stock: float, quantity: int, depth: float, side: str) -> int:
    """Integrate bounded marginal prices; a million units never needs a unit loop."""
    depth = max(1., depth)
    start = .7 * (1 - stock / depth)
    end = start + (.7 if side == 'buy' else -.7) * quantity / depth
    low, high = (start, end) if start <= end else (end, start)
    floor, ceiling = _FLOOR, _CEILING
    if floor <= low and high <= ceiling:
        integral = math.exp(high) - math.exp(low)
    elif high <= floor:
        integral = (high-low) * .35
    elif low >= ceiling:
        integral = (high-low) * 3.
    else:
        integral = max(0., min(high, floor) - low) * .35
        left, right = max(low, floor), min(high, ceiling)
        if right > left:
            integral += math.exp(right) - math.exp(left)
        integral += max(0., high - max(low, ceiling)) * 3.
    value = reference * depth / .7 * integral
    return max(1, math.ceil(value - 1e-7)) if side == 'buy' else max(0, math.floor(value * .8 + 1e-7))
