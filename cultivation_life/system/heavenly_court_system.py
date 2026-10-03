"""Compatibility entry point; the engine composes these algorithms directly."""
from __future__ import annotations
from functools import cached_property
from typing import Any
from ..models import GameState
from .court import state as state_rules
from .court.wiring import bind_state
from .court_governance import CourtGovernanceMixin

class HeavenlyCourtSystemMixin(CourtGovernanceMixin):
    @cached_property
    def _court_state_dependencies(self):
        return bind_state(self)

    @staticmethod
    def _court_config() -> dict[str, Any]:
        return state_rules._court_config()

    @staticmethod
    def _court_grade_for_realm(realm_index: int) -> int:
        return state_rules._court_grade_for_realm(realm_index)

    def _ensure_heavenly_court(self, game: GameState, rng: Any) -> bool:
        return state_rules._ensure_heavenly_court(self._court_state_dependencies, game, rng)

    def _player_court_representative(self, game: GameState) -> bool:
        return state_rules._player_court_representative(self._court_state_dependencies, game)

    def _sync_player_court_identity(self, game: GameState) -> None:
        return state_rules._sync_player_court_identity(self._court_state_dependencies, game)

    @staticmethod
    def _court_holder_ids(court: dict[str, Any]) -> list[str]:
        return state_rules._court_holder_ids(court)

    @staticmethod
    def _court_player_controls(court: dict[str, Any]) -> int:
        return state_rules._court_player_controls(court)

    def _court_open_election(self, game: GameState, office_id: str, rng: Any) -> None:
        return state_rules._court_open_election(self._court_state_dependencies, game, office_id, rng)

    def _court_open_next_queued_election(self, game: GameState, rng: Any) -> None:
        return state_rules._court_open_next_queued_election(self._court_state_dependencies, game, rng)

    def _court_resolve_election_round(
        self, game: GameState, rng: Any, method: str, pledge_id: str,
    ) -> tuple[bool, str]:
        return state_rules._court_resolve_election_round(self._court_state_dependencies, game, rng, method, pledge_id)

    def _advance_heavenly_court_unit(self, game: GameState, rng: Any) -> list[str]:
        return state_rules._advance_heavenly_court_unit(self._court_state_dependencies, game, rng)

    def resolve_heavenly_election(self, game_id: str, method: str = "none", pledge_id: str = "") -> dict[str, Any]:
        return state_rules.resolve_heavenly_election(self._court_state_dependencies, game_id, method, pledge_id)

    @staticmethod
    def _court_honor_pledge(court: dict[str, Any], kind: str, policy_id: str) -> None:
        return state_rules._court_honor_pledge(court, kind, policy_id)

    def heavenly_court_action(
        self, game_id: str, action: str, target_id: str = "", enact: bool | None = None,
        influence_spend: int = 0,
    ) -> dict[str, Any]:
        return state_rules.heavenly_court_action(self._court_state_dependencies, game_id, action, target_id, enact, influence_spend)

    def _court_examination(self, game: GameState, rng: Any) -> tuple[str, str]:
        return state_rules._court_examination(self._court_state_dependencies, game, rng)

    def _court_enact_decree(
        self, game: GameState, decree_id: str, target_id: str, rng: Any, influence_spend: int = 0, *, actor_id: str = "player",
    ) -> tuple[str, str]:
        return state_rules._court_enact_decree(self._court_state_dependencies, game, decree_id, target_id, rng, influence_spend, actor_id=actor_id)

    def _court_vote_law(
        self, game: GameState, law_id: str, enact: bool | None, rng: Any, influence_spend: int = 0, *, actor_id: str = "player",
    ) -> tuple[str, str]:
        return state_rules._court_vote_law(self._court_state_dependencies, game, law_id, enact, rng, influence_spend, actor_id=actor_id)

    def _court_spend_influence(self, game: GameState, requested: int) -> int:
        return state_rules._court_spend_influence(self._court_state_dependencies, game, requested)

    def _add_court_merit(self, game: GameState, amount: int) -> str:
        return state_rules._add_court_merit(self._court_state_dependencies, game, amount)

    def _public_heavenly_court(self, game: GameState) -> dict[str, Any]:
        return state_rules._public_heavenly_court(self._court_state_dependencies, game)

    def _court_law_active(self, game: GameState, law_id: str) -> bool:
        return state_rules._court_law_active(self._court_state_dependencies, game, law_id)
