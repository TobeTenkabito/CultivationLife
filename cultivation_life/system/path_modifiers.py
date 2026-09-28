"""Neutral extension hooks. Providers must leave persisted player resources untouched."""
from __future__ import annotations

import math

_providers = {}


def register_provider(name, provider):
    _providers[name] = provider


def modifier(subject, key, default=1.0, **context):
    value = default
    for provider in _providers.values():
        result = provider(subject, key, **context)
        if result is not None:
            value = result
    return value


def projected_resource(player, name, context="general"):
    return float(modifier(player, name, getattr(player, name), context=context))


def adjusted_cost(game, amount, activity):
    return max(1, math.ceil(amount * modifier(game, "cost", activity=activity)))


def commission_duration(game, years):
    return max(1, math.ceil(years * modifier(game, "commission_duration")))


def pursuit_immunity(game, source):
    return bool(modifier(game, "pursuit_immunity", False, source=source))
