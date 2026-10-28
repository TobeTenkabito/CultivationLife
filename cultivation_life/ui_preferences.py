"""Machine-local interface preferences; independent of game saves and RNG."""
from __future__ import annotations

import json
import os
import tempfile
import re
from pathlib import Path
from threading import RLock

THEMES = frozenset("abdf")
DEFAULTS = {"theme": "a", "reduced_motion": False, "pixel_art": False,
            "pixel_theme": "light", "compact_docks": True}
_LOCK = RLock()


def _voisinage_appearance(value, *, stored=False):
    from .domain_styles import catalog, controls
    styles = {'mist', 'star', 'frost', 'lotus', 'sword', 'seal', 'water', 'mountain', 'wood', 'thunder', 'moon', 'void', 'time'}
    styles.update(row['id'] for row in catalog())
    allowed = {'outline': styles, 'pattern': styles,
               'palette': {'rose', 'peach', 'gold', 'lime', 'green', 'jade', 'cyan', 'blue', 'indigo', 'violet', 'lilac', 'pink'},
               'control': {row['id'] for row in controls(all_paths=True)}}
    if not isinstance(value, dict) or set(value) != set(allowed) | {'density'}:
        raise ValueError('邻域外观须包含轮廓、意象、配色、控制样式与质感')
    for key, choices in allowed.items():
        # Keep optional saved identities while a package is temporarily off.
        # Projection and new submissions separately enforce eligibility.
        if stored and key in {'outline', 'pattern', 'control'} and isinstance(value[key], str) and re.fullmatch(r'[a-z][a-z0-9-]{0,47}', value[key]):
            continue
        if key == 'palette' and isinstance(value[key], str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value[key]):
            continue
        if not isinstance(value[key], str) or value[key] not in choices:
            raise ValueError('请选择有效的邻域外观组件')
    if type(value['density']) is not int or not 20 <= value['density'] <= 100:
        raise ValueError('邻域质感须为20至100的整数')
    return dict(value) | {'palette': value['palette'].lower()}

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
            "pixel_art": data.get("pixel_art") is True,
            "pixel_theme": 'dark' if data.get('pixel_theme') == 'dark' else 'light',
            "compact_docks": data.get('compact_docks') is not False,
        }
        if 'navigation' in data:
            try:
                result['navigation'] = _navigation(data['navigation'])
            except ValueError:
                pass
        if 'voisinage_appearance' in data:
            try:
                result['voisinage_appearance'] = _voisinage_appearance(data['voisinage_appearance'], stored=True)
            except ValueError:
                pass
        return result


def write_ui_preferences(root: Path, payload: dict, *, character_path=None) -> dict:
    if not isinstance(payload, dict) or not payload or set(payload) - (DEFAULTS.keys() | {'navigation', 'voisinage_appearance'}):
        raise ValueError("界面偏好字段无效")
    if "theme" in payload and (not isinstance(payload["theme"], str) or payload["theme"] not in THEMES):
        raise ValueError("请选择松烟书院、月下观星、丹砂金阙或竹简纪年")
    if "reduced_motion" in payload and not isinstance(payload["reduced_motion"], bool):
        raise ValueError("减弱动态效果必须为布尔值")
    if "pixel_art" in payload and not isinstance(payload["pixel_art"], bool):
        raise ValueError("像素绘景必须为布尔值")
    if 'pixel_theme' in payload and payload['pixel_theme'] not in ('light', 'dark'):
        raise ValueError('新版界面仅支持浅色和暗色主题')
    if 'compact_docks' in payload and not isinstance(payload['compact_docks'], bool):
        raise ValueError('侧栏悬停名称必须为布尔值')
    if 'navigation' in payload:
        payload = payload | {'navigation': _navigation(payload['navigation'])}
    if 'voisinage_appearance' in payload:
        payload = payload | {'voisinage_appearance': _voisinage_appearance(payload['voisinage_appearance'])}
        from .domain_styles import validate
        validate(payload['voisinage_appearance'], character_path)
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
