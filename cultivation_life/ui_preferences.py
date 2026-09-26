"""Machine-local appearance preferences; independent of game saves and RNG."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

THEMES = frozenset("abcdef")
DEFAULTS = {"theme": "a", "reduced_motion": False}
_LOCK = RLock()


def load_ui_preferences(root: Path) -> dict:
    with _LOCK:
        try:
            data = json.loads((root / "data" / "ui_preferences.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(DEFAULTS)
        if not isinstance(data, dict):
            return dict(DEFAULTS)
        return {
            "theme": data.get("theme") if isinstance(data.get("theme"), str) and data["theme"] in THEMES else "a",
            "reduced_motion": data.get("reduced_motion") if isinstance(data.get("reduced_motion"), bool) else False,
        }


def write_ui_preferences(root: Path, payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload or set(payload) - DEFAULTS.keys():
        raise ValueError("界面偏好仅支持 theme 与 reduced_motion")
    if "theme" in payload and (not isinstance(payload["theme"], str) or payload["theme"] not in THEMES):
        raise ValueError("主题必须为 A 至 F 对应的 a–f")
    if "reduced_motion" in payload and not isinstance(payload["reduced_motion"], bool):
        raise ValueError("减弱动态效果必须为布尔值")
    with _LOCK:
        value = load_ui_preferences(root) | payload
        destination = root / "data" / "ui_preferences.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                             prefix=".ui-preferences-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return value
