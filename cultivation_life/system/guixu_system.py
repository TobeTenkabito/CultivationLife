from __future__ import annotations
from functools import cached_property
from .guixu.wiring import bind_guixu
from .guixu import state as guixu_state
from .guixu import rewards as guixu_rewards
from .guixu import presentation as guixu_presentation
from .guixu import npcs as guixu_npcs
from .guixu import encounters as guixu_encounters
from .guixu import calendar as guixu_calendar
from .guixu import actions as guixu_actions

from ..rules import effective_fame

import copy
import math
import random
from typing import Any

from ..content_registry import (
    ACTIONS, GUIXU_TIDE_CONTENT, ITEM_CATALOG, REALMS, TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from ..models import GameState, HistoryRecord, SectNpc
from ..rules import (
    acquire_technique, add_item, divine_sense_level, expected_combat_power, has_item,
    max_hp, max_mp, opportunity_multiplier, remove_item,
)
from ..runtime import decode_rng, encode_rng, now_iso
from .possession_system import advance_player_age


LAYER_ORDER = ("outer", "middle", "inner", "final")
MOVE_COSTS = {
    frozenset(("outer", "middle")): 3,
    frozenset(("middle", "inner")): 4,
    frozenset(("inner", "final")): 5,
    frozenset(("inner", "secret")): 2,
}


def guixu_content_available() -> bool:
    return bool(GUIXU_TIDE_CONTENT.get("dungeons"))


def _guixu_definitions() -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): row for row in GUIXU_TIDE_CONTENT.get("dungeons", [])
    }


def _guixu_settings() -> dict[str, Any]:
    return GUIXU_TIDE_CONTENT.get("settings", {})


def _next_guixu_open(definition: dict[str, Any], age: int) -> int:
    first = int(definition.get("first_open_year", definition["period_years"]))
    period = int(definition["period_years"])
    if age <= first:
        return first
    return first + math.ceil((age - first) / period) * period


def _guixu_weighted_key(weights: dict[str, Any], rng: random.Random) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[float(weights[key]) for key in keys], k=1)[0]


def _guixu_return_days(layer_id: str) -> int:
    return {"outer": 1, "middle": 4, "inner": 8, "final": 13, "secret": 10}[layer_id]


def _guixu_active_team(cycle, actor):
    if not actor.get("team_id"):
        return [actor]
    return [row for row in cycle.get("roster", []) if row.get("team_id") == actor["team_id"]
            and row.get("status") == "active" and row.get("layer_id") == actor.get("layer_id")]


def bind_guixu_compatibility(host):
    return bind_guixu(
        host,
        _get_MOVE_COSTS=lambda: MOVE_COSTS,
        decode_rng=lambda *args, **kwargs: decode_rng(*args, **kwargs),
        guixu_content_available=lambda *args, **kwargs: guixu_content_available(*args, **kwargs),
    )


class GuixuSystemMixin:
    """Compatibility adapter for periodic Guixu dungeons."""

    @cached_property
    def _guixu_dependencies(self):
        return bind_guixu_compatibility(self)

    @staticmethod
    def _guixu_definitions() -> dict[str, dict[str, Any]]:
        return _guixu_definitions()

    @staticmethod
    def _guixu_settings() -> dict[str, Any]:
        return _guixu_settings()

    @staticmethod
    def _next_guixu_open(definition: dict[str, Any], age: int) -> int:
        return _next_guixu_open(definition, age)

    def _ensure_guixu_state(self, game: GameState) -> bool:
        return guixu_state._ensure_guixu_state(self._guixu_dependencies.state, game)

    def _guixu_entry_definition(
        self, dungeon: dict[str, Any], pool_entry_id: str,
    ) -> dict[str, Any]:
        return guixu_state._guixu_entry_definition(self._guixu_dependencies.state, dungeon, pool_entry_id)

    @staticmethod
    def _guixu_weighted_key(weights: dict[str, Any], rng: random.Random) -> str:
        return _guixu_weighted_key(weights, rng)

    def _announce_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_calendar._announce_guixu_cycle(self._guixu_dependencies.calendar, game, dungeon, cycle, rng)

    def _guixu_relation_ids(self, game: GameState) -> set[str]:
        return guixu_npcs._guixu_relation_ids(self._guixu_dependencies.npcs, game)

    def _generate_guixu_roster(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> list[dict[str, Any]]:
        return guixu_npcs._generate_guixu_roster(self._guixu_dependencies.npcs, game, dungeon, cycle, rng)

    def _form_guixu_npc_teams(
        self, cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_npcs._form_guixu_npc_teams(self._guixu_dependencies.npcs, cycle, rng)

    def _dissolve_guixu_npc_team(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        team_id: str | None, reason: str,
    ) -> None:
        return guixu_npcs._dissolve_guixu_npc_team(self._guixu_dependencies.npcs, game, dungeon, cycle, team_id, reason)

    def _guixu_npc_claim_entry(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        row: dict[str, Any], actor: dict[str, Any], source: str,
    ) -> None:
        return guixu_npcs._guixu_npc_claim_entry(self._guixu_dependencies.npcs, game, dungeon, cycle, row, actor, source)

    def _open_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_calendar._open_guixu_cycle(self._guixu_dependencies.calendar, game, dungeon, cycle, rng)

    def _assign_due_guixu_entries(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        elapsed_days: int, rng: random.Random,
    ) -> None:
        return guixu_npcs._assign_due_guixu_entries(self._guixu_dependencies.npcs, game, dungeon, cycle, elapsed_days, rng)

    def _simulate_guixu_npc_conflict(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        day: int, rng: random.Random,
    ) -> None:
        return guixu_npcs._simulate_guixu_npc_conflict(self._guixu_dependencies.npcs, game, dungeon, cycle, day, rng)

    def _resolve_guixu_npc_kill(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        killer: dict[str, Any], victim: dict[str, Any], day: int,
    ) -> None:
        return guixu_npcs._resolve_guixu_npc_kill(self._guixu_dependencies.npcs, game, dungeon, cycle, killer, victim, day)

    def _close_guixu_cycle(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_calendar._close_guixu_cycle(self._guixu_dependencies.calendar, game, dungeon, cycle, rng)

    def _advance_guixu_calendar(
        self, game: GameState, rng: random.Random, era_news: list[str],
    ) -> bool:
        return guixu_calendar._advance_guixu_calendar(self._guixu_dependencies.calendar, game, rng, era_news)

    def _guixu_cycle_and_definition(
        self, game: GameState, dungeon_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return guixu_state._guixu_cycle_and_definition(self._guixu_dependencies.state, game, dungeon_id)

    def _enforce_guixu_rank_boundary(self, game: GameState, reason: str) -> str:
        return guixu_state._enforce_guixu_rank_boundary(self._guixu_dependencies.state, game, reason)

    def _guixu_grant_entry(
        self, game: GameState, dungeon: dict[str, Any], row: dict[str, Any], source: str,
    ) -> str:
        return guixu_rewards._guixu_grant_entry(self._guixu_dependencies.rewards, game, dungeon, row, source)

    def _guixu_transferable_player_entries(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        return guixu_rewards._guixu_transferable_player_entries(self._guixu_dependencies.rewards, game, dungeon, cycle, session)

    def _maybe_guixu_npc_threat(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], rng: random.Random,
    ) -> None:
        return guixu_encounters._maybe_guixu_npc_threat(self._guixu_dependencies.encounters, game, dungeon, cycle, session, rng)

    def _surrender_guixu_treasure(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], threat: dict[str, Any], actor: dict[str, Any],
    ) -> str:
        return guixu_rewards._surrender_guixu_treasure(self._guixu_dependencies.rewards, game, dungeon, cycle, session, threat, actor)

    def _guixu_elapsed_days(
        self, dungeon: dict[str, Any], session: dict[str, Any],
    ) -> int:
        return guixu_calendar._guixu_elapsed_days(self._guixu_dependencies.calendar, dungeon, session)

    def _consume_guixu_days(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], days: int, rng: random.Random,
    ) -> None:
        return guixu_calendar._consume_guixu_days(self._guixu_dependencies.calendar, game, dungeon, cycle, session, days, rng)

    @staticmethod
    def _guixu_return_days(layer_id: str) -> int:
        return _guixu_return_days(layer_id)

    def _guixu_actor(self, cycle: dict[str, Any], actor_id: str) -> dict[str, Any]:
        return guixu_encounters._guixu_actor(self._guixu_dependencies.encounters, cycle, actor_id)

    def _guixu_relationship_role(self, game: GameState, npc_id: str) -> str | None:
        return guixu_encounters._guixu_relationship_role(self._guixu_dependencies.encounters, game, npc_id)

    def _break_guixu_relationship(self, game: GameState, npc_id: str, *, player_defending: bool = False) -> None:
        return guixu_encounters._break_guixu_relationship(self._guixu_dependencies.encounters, game, npc_id, player_defending=player_defending)

    @staticmethod
    def _guixu_active_team(cycle, actor):
        return _guixu_active_team(cycle, actor)

    def _guixu_fight(
        self, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
        session: dict[str, Any], actor: dict[str, Any], rng: random.Random,
        *, player_defending: bool = False, enemy_first_round: bool = False,
    ) -> tuple[str, str]:
        return guixu_encounters._guixu_fight(self._guixu_dependencies.encounters, game, dungeon, cycle, session, actor, rng, player_defending=player_defending, enemy_first_round=enemy_first_round)

    def _guixu_offer_team(self, game, cycle, session):
        return guixu_encounters._guixu_offer_team(self._guixu_dependencies.encounters, game, cycle, session)

    def _guixu_team_tick(self, game, dungeon, cycle, session, rng):
        return guixu_encounters._guixu_team_tick(self._guixu_dependencies.encounters, game, dungeon, cycle, session, rng)

    def guixu_action(self, game_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return guixu_actions.guixu_action(self._guixu_dependencies.actions, game_id, action, payload)

    def _guixu_trapped_training(
        self, game_id: str, action: str, units: int = 1,
    ) -> dict[str, Any]:
        return guixu_actions._guixu_trapped_training(self._guixu_dependencies.actions, game_id, action, units)

    def assert_guixu_operation_allowed(self, game_id: str, operation: str) -> None:
        # When the DLC is disabled, let the requested operation reach ``_load``;
        # its compatibility migration safely returns an active explorer first.
        return guixu_state.assert_guixu_operation_allowed(self._guixu_dependencies.state, game_id, operation)

    def _public_guixu(self, game: GameState) -> dict[str, Any]:
        return guixu_presentation._public_guixu(self._guixu_dependencies.presentation, game)
