from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain.character import (
    BootstrapGame,
    PerformTimedAction,
    character_invariants,
    character_view,
    register_character_domain,
)
from .domain.cultivation import (
    AttemptBreakthrough,
    PerformActionUnits,
    cultivation_invariants,
    cultivation_view,
    register_cultivation_domain,
)
from .domain.factions import (
    faction_catalog_view,
    faction_invariants,
    faction_view,
    register_faction_domain,
)
from .domain.relations import relationship_invariants, relationship_view, register_relationship_domain
from .domain.world import TravelWithinWorld, register_world_domain, world_invariants, world_view
from .infrastructure.content_loader import V2ContentLoader
from .infrastructure.sqlite_store import SQLiteSaveStore
from .kernel.bus import CommandBus
from .kernel.model import WorldState
from .kernel.services import InvariantRegistry


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class CommandExecution:
    game: dict[str, Any]
    events: tuple[dict[str, Any], ...]


class V2GameEngine:
    """Transactional application boundary for the V2 simulation."""

    def __init__(self, database_path: Path, *, content_directory: Path | None = None):
        default_content = Path(__file__).resolve().parents[2] / "content"
        self.definitions = V2ContentLoader.load(content_directory or default_content)
        self.store = SQLiteSaveStore(database_path)
        self.commands = CommandBus()
        self.invariants = InvariantRegistry()
        register_character_domain(self.commands, self.definitions)
        register_cultivation_domain(self.commands, self.definitions)
        register_world_domain(self.commands, self.definitions)
        register_relationship_domain(self.commands)
        register_faction_domain(self.commands, self.definitions)
        self.invariants.register("character", character_invariants)
        self.invariants.register("cultivation", cultivation_invariants(self.definitions))
        self.invariants.register("world", world_invariants(self.definitions))
        self.invariants.register("relations", relationship_invariants)
        self.invariants.register("factions", faction_invariants(self.definitions))

    def create_game(
        self,
        name: str,
        *,
        seed: int | None = None,
        starting_age: int = 16,
        gender: str = "male",
        race: str = "human",
        spirit_root: str = "supreme_wood",
        path: str = "dao",
        start_world: str = "human",
    ) -> dict[str, Any]:
        now = _now_iso()
        state = WorldState.new(seed=seed if seed is not None else secrets.randbits(63), created_at=now)
        events = self.commands.execute(state, BootstrapGame(
            name=name,
            starting_age=starting_age,
            gender=gender,
            race=race,
            spirit_root=spirit_root,
            path=path,
            start_world=start_world,
        ))
        self.invariants.validate(state)
        player = character_view(state)
        self.store.create(state, events, player_name=player["name"])
        return self._present(state)

    def execute(self, game_id: str, command: object) -> CommandExecution:
        state = self.store.load(game_id)
        self.invariants.validate(state)
        expected_revision = state.revision
        events = self.commands.execute(state, command)
        self.invariants.validate(state)
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

    def perform_action(self, game_id: str, action: str, units: int = 1) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PerformActionUnits(actor_id=actor_id, action=action, units=units))

    def attempt_breakthrough(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, AttemptBreakthrough(actor_id=actor_id))

    def travel(self, game_id: str, destination_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, TravelWithinWorld(actor_id=actor_id, destination_id=destination_id))

    def get_game(self, game_id: str) -> dict[str, Any]:
        state = self.store.load(game_id)
        self.invariants.validate(state)
        return self._present(state)

    def list_games(self) -> list[dict[str, Any]]:
        return self.store.list_games()

    def event_journal(self, game_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.store.load_events(game_id, after_sequence=after_sequence)]

    def _present(self, state: WorldState) -> dict[str, Any]:
        player = character_view(state)
        cultivation = cultivation_view(state, self.definitions)
        current_world = world_view(state, self.definitions)
        alive = bool(player["alive"])
        return {
            "format": "cultivation-life-v2",
            "id": state.game_id,
            "revision": state.revision,
            "schema_version": state.schema_version,
            "clock": {"year": state.clock.year},
            "player": {**player, "cultivation": cultivation},
            "world": current_world,
            "relationships": relationship_view(state),
            "faction": faction_view(state),
            "available_factions": faction_catalog_view(state, current_world["world_id"]),
            "capabilities": {
                "character.cultivate": {
                    "enabled": alive,
                    "reason": None if alive else "角色已经死亡",
                },
                "character.rest": {
                    "enabled": alive,
                    "reason": None if alive else "角色已经死亡",
                },
                "cultivation.breakthrough": {
                    "enabled": alive and cultivation["bottleneck"] in {"minor", "major"},
                    "reason": None if alive and cultivation["bottleneck"] else "尚未抵达突破瓶颈",
                },
                "world.travel": {
                    "enabled": alive,
                    "reason": None if alive else "角色已经死亡",
                },
            },
        }
