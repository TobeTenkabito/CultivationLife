from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain.character import (
    BootstrapGame,
    PerformTimedAction,
    character_view,
    register_character_domain,
)
from .infrastructure.sqlite_store import SQLiteSaveStore
from .kernel.bus import CommandBus
from .kernel.model import EventEnvelope, WorldState
from .kernel.services import validate_world_state


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class CommandExecution:
    game: dict[str, Any]
    events: tuple[dict[str, Any], ...]


class V2GameEngine:
    """Small application boundary for the V2 vertical slice."""

    def __init__(self, database_path: Path):
        self.store = SQLiteSaveStore(database_path)
        self.commands = CommandBus()
        register_character_domain(self.commands)

    def create_game(
        self,
        name: str,
        *,
        seed: int | None = None,
        starting_age: int = 16,
    ) -> dict[str, Any]:
        now = _now_iso()
        state = WorldState.new(seed=seed if seed is not None else secrets.randbits(63), created_at=now)
        events = self.commands.execute(state, BootstrapGame(name=name, starting_age=starting_age))
        validate_world_state(state)
        player = character_view(state)
        self.store.create(state, events, player_name=player["name"])
        return self._present(state)

    def execute(self, game_id: str, command: object) -> CommandExecution:
        state = self.store.load(game_id)
        validate_world_state(state)
        expected_revision = state.revision
        events = self.commands.execute(state, command)
        validate_world_state(state)
        state.updated_at = _now_iso()
        player = character_view(state)
        self.store.save(
            state,
            events,
            player_name=player["name"],
            expected_revision=expected_revision,
        )
        return CommandExecution(
            game=self._present(state),
            events=tuple(event.to_dict() for event in events),
        )

    def perform_timed_action(self, game_id: str, action: str, years: int = 1) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            PerformTimedAction(actor_id=actor_id, action=action, years=years),
        )

    def get_game(self, game_id: str) -> dict[str, Any]:
        state = self.store.load(game_id)
        validate_world_state(state)
        return self._present(state)

    def list_games(self) -> list[dict[str, Any]]:
        return self.store.list_games()

    def event_journal(self, game_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.store.load_events(game_id, after_sequence=after_sequence)]

    @staticmethod
    def _present(state: WorldState) -> dict[str, Any]:
        return {
            "format": "cultivation-life-v2",
            "id": state.game_id,
            "revision": state.revision,
            "schema_version": state.schema_version,
            "clock": {"year": state.clock.year},
            "player": character_view(state),
            "capabilities": {
                "character.cultivate": {"enabled": True, "reason": None},
                "character.rest": {"enabled": True, "reason": None},
            },
        }
