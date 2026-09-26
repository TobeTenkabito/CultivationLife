"""Base-game release identity.

This is deliberately separate from save schema versions, content schema versions,
and DLC/MOD manifest versions.  Bump this value for each base-game release.
"""

from __future__ import annotations


BASE_GAME_ID = "cultivation-life"
BASE_GAME_NAME = "浮生问道"
BASE_GAME_VERSION = "1.34.0"
BASE_GAME_VERSION_TUPLE = tuple(int(part) for part in BASE_GAME_VERSION.split("."))


def base_game_metadata() -> dict[str, str]:
    return {
        "id": BASE_GAME_ID,
        "name": BASE_GAME_NAME,
        "version": BASE_GAME_VERSION,
        "version_label": f"本体 v{BASE_GAME_VERSION}",
    }
