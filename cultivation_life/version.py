"""Base-game release identity.

This is deliberately separate from save schema versions, content schema versions,
and DLC/MOD manifest versions.  Bump this value for each base-game release.
"""

from __future__ import annotations
import re


BASE_GAME_ID = "cultivation-life"
BASE_GAME_NAME = "浮生问道"
BASE_GAME_VERSION = "3.0.1"
# Windows file metadata requires numeric components even for the public alpha label.
BASE_GAME_VERSION_TUPLE = (3, 0, 1)


def release_order(value: str) -> tuple:
    match = re.fullmatch(r'(\d{1,4})\.(\d{1,4})\.(\d{1,4})(?:-(alpha|beta|rc)\.([1-9]\d{0,3}))?', value) if isinstance(value, str) else None
    if match:
        major, minor, patch, phase, iteration = match.groups()
        return (int(major), int(minor), int(patch), {'alpha':0, 'beta':1, 'rc':2, None:3}[phase], int(iteration or 0))
    raise ValueError('存档版本无效')


def base_game_metadata() -> dict[str, str]:
    return {
        "id": BASE_GAME_ID,
        "name": BASE_GAME_NAME,
        "version": BASE_GAME_VERSION,
        "version_label": f"本体 v{BASE_GAME_VERSION}",
    }
