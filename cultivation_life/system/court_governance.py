"""Compatibility entry point; the engine composes these algorithms directly."""
from __future__ import annotations
from functools import cached_property
from .court import governance as governance_rules
from .court.wiring import bind_governance
from .court_lifecycle import CourtLifecycleMixin

class CourtGovernanceMixin(CourtLifecycleMixin):
    @cached_property
    def _court_governance_dependencies(self):
        return bind_governance(self)

    def _court_retire_unavailable(self, game):
        return governance_rules._court_retire_unavailable(self._court_governance_dependencies, game)

    def _court_autonomous_votes(self, court, actor_id, law_id, desired, rng):
        return governance_rules._court_autonomous_votes(self._court_governance_dependencies, court, actor_id, law_id, desired, rng)

    def _court_govern(self, game, rng):
        return governance_rules._court_govern(self._court_governance_dependencies, game, rng)
