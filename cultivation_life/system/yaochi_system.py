"""Compatibility entry point; the engine composes these algorithms directly."""
from __future__ import annotations
from functools import cached_property
from .court import yaochi as yaochi_rules
from .court.wiring import bind_yaochi
from .yaochi_rules import (
    config as config,
    account as account,
    spend as spend,
    require_market as require_market,
    offers as offers,
    grant as grant,
    experience as experience,
    commission_reward as commission_reward,
    lock_price as lock_price,
)

class YaochiMixin:
    @cached_property
    def _court_yaochi_dependencies(self):
        return bind_yaochi(self)

    def _begin_yaochi_action(self, game, action):
        return yaochi_rules._begin_yaochi_action(self._court_yaochi_dependencies, game, action)

    def _finish_yaochi_action(self, game, action, elapsed):
        return yaochi_rules._finish_yaochi_action(self._court_yaochi_dependencies, game, action, elapsed)

    def yaochi_action(self, game_id, action, target_id='', amount=1):
        return yaochi_rules.yaochi_action(self._court_yaochi_dependencies, game_id, action, target_id, amount)

    def _public_yaochi(self, game):
        return yaochi_rules._public_yaochi(self._court_yaochi_dependencies, game)
