"""Machine-local interface preferences; independent of game saves and RNG."""
from __future__ import annotations

import json
import os
import tempfile
import re
from pathlib import Path
from threading import RLock

THEMES = frozenset("abdf")
DEFAULTS = {"theme": "a", "reduced_motion": False}
_LOCK = RLock()

def _navigation(value):
    if not isinstance(value, dict) or set(value) != {'pins', 'recent'}:
        raise ValueError('导航偏好须包含常用与最近记录')
    result = {}
    for key, limit in [('pins', 8), ('recent', 4)]:
        rows = value[key]
        if (not isinstance(rows, list) or len(rows) > limit or
            any(not isinstance(item, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', item) for item in rows)
            or len(set(rows)) != len(rows)):
            raise ValueError('导航偏好格式或数量无效')
        result[key] = list(rows)
    return result


def load_ui_preferences(root: Path) -> dict:
    with _LOCK:
        try:
            data = json.loads((root / "data" / "ui_preferences.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(DEFAULTS)
        if not isinstance(data, dict):
            return dict(DEFAULTS)
        result = {
            "theme": ({"c": "a", "e": "f"}.get(data["theme"], data["theme"])) if isinstance(data.get("theme"), str) and data["theme"] in THEMES | {"c", "e"} else "a",
            "reduced_motion": data.get("reduced_motion") if isinstance(data.get("reduced_motion"), bool) else False,
        }
        if 'navigation' in data:
            try:
                result['navigation'] = _navigation(data['navigation'])
            except ValueError:
                pass
        return result


def write_ui_preferences(root: Path, payload: dict) -> dict:
    if not isinstance(payload, dict) or not payload or set(payload) - (DEFAULTS.keys() | {'navigation'}):
        raise ValueError("界面偏好仅支持 theme、reduced_motion 与 navigation")
    if "theme" in payload and (not isinstance(payload["theme"], str) or payload["theme"] not in THEMES):
        raise ValueError("请选择松烟书院、月下观星、丹砂金阙或竹简纪年")
    if "reduced_motion" in payload and not isinstance(payload["reduced_motion"], bool):
        raise ValueError("减弱动态效果必须为布尔值")
    if 'navigation' in payload:
        payload = payload | {'navigation': _navigation(payload['navigation'])}
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
