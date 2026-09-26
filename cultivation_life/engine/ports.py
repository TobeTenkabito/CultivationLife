"""Resource interfaces used by engine algorithms, independent of their adapters."""

from __future__ import annotations

from typing import Any, Protocol

from ..models import GameState


class SavePort(Protocol):
    def load(self, game_id: str) -> GameState: ...

    def save(self, game: GameState) -> None: ...


class MapPort(Protocol):
    worlds: dict[str, Any]

    def default_location(self, world: str) -> str: ...

    def location(self, world: str, location_id: str) -> dict[str, Any]: ...

    def normalize_location(self, world: str, location_id: str | None) -> str: ...

    def qi_gain_efficiencies(self, world: str, location_id: str | None) -> dict[str, float]: ...


class AchievementPort(Protocol):
    def ensure_global_metadata(self) -> None: ...

    def evaluate(
        self, game: GameState, *, player_rank: int | None = None,
    ) -> list[dict[str, Any]]: ...
