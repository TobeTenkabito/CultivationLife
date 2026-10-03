"""Compatibility entry point; the engine composes these algorithms directly."""
from __future__ import annotations
from functools import cached_property
from .court import lifecycle as lifecycle_rules
from .court.wiring import bind_lifecycle
from .court.lifecycle import private_combat as private_combat

class CourtLifecycleMixin:
    @cached_property
    def _court_lifecycle_dependencies(self):
        return bind_lifecycle(self)

    def _court_conflicts(self, law_id):
        return lifecycle_rules._court_conflicts(self._court_lifecycle_dependencies, law_id)

    def _court_normalize(self, game):
        return lifecycle_rules._court_normalize(self._court_lifecycle_dependencies, game)

    def _court_prune_decrees(self, court):
        return lifecycle_rules._court_prune_decrees(self._court_lifecycle_dependencies, court)

    def _court_finish_unattended(self, game, rng):
        return lifecycle_rules._court_finish_unattended(self._court_lifecycle_dependencies, game, rng)

    def _court_schedule_elections(self, game, rng):
        return lifecycle_rules._court_schedule_elections(self._court_lifecycle_dependencies, game, rng)

    def _court_pay_stipend(self, game):
        return lifecycle_rules._court_pay_stipend(self._court_lifecycle_dependencies, game)
