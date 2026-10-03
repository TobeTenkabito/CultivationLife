"""Explicit relationship rules operations; callers own composition."""
from __future__ import annotations

from typing import Any

from ..models import Player, SectNpc


def _rank(value: Player | SectNpc | dict[str, Any]) -> tuple[int, int]:
    if isinstance(value, dict):
        return int(value.get("realm_index", 0)), int(value.get("layer", 1))
    return int(value.realm_index), int(value.layer)


def _stable_gender(identity: str, name: str = "") -> str:
    return "female" if sum(ord(char) for char in (identity or name)) % 2 else "male"
