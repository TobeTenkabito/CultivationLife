"""Explicit capabilities of response orchestration, independent of adapters."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..models import GameState


@dataclass(frozen=True, slots=True)
class ResponseDependencies:
    settle_boundary: Callable[[GameState], bool]
    commit: Callable[[GameState], None]
    prepare_view: Callable[[GameState], dict[str, Any]]
