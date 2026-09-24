"""Human-editable runtime switches loaded from beside the launcher.

The parser intentionally accepts a small, explicit vocabulary instead of
executing arbitrary expressions.  This keeps the convenience of a game-style
text config without turning the file into code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


RUNTIME_CONFIG_FILENAME = "game_config.txt"
DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {"debug": False, "mode": "release"}

_DEBUG_KEYS = {"debug", "debugmode", "debug_mode", "调试", "调试模式"}
_MODE_KEYS = {"mode", "runmode", "run_mode", "runtimemode", "runtime_mode", "运行模式", "加载模式"}
_TRUE_VALUES = {"1", "true", "yes", "y", "on", "enable", "enabled", "开", "开启", "启用", "是"}
_FALSE_VALUES = {"0", "false", "no", "n", "off", "disable", "disabled", "关", "关闭", "停用", "否"}
_DEBUG_MODES = {"debug", "dev", "developer", "development", "调试", "调试模式", "开发", "开发模式"}
_RELEASE_MODES = {"release", "normal", "production", "正式", "正式模式", "正常", "普通"}


def _normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "")


def _assignment(line: str) -> tuple[str, str] | None:
    for separator in ("=", "：", ":"):
        if separator in line:
            key, value = line.split(separator, 1)
            return _normalized(key), _normalized(value)
    pieces = line.split()
    if len(pieces) >= 2:
        return _normalized(pieces[0]), _normalized("".join(pieces[1:]))
    return None


def parse_runtime_config(text: str) -> dict[str, Any]:
    result = dict(DEFAULT_RUNTIME_CONFIG)
    for raw_line in text.lstrip("\ufeff").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        for marker in (" #", " ;", " //"):
            line = line.split(marker, 1)[0].strip()
        phrase = _normalized(line)
        if phrase in {"开启调试模式", "打开调试模式", "启用调试模式", "debugon"}:
            result.update(debug=True, mode="debug")
            continue
        if phrase in {"关闭调试模式", "停用调试模式", "debugoff"}:
            result.update(debug=False, mode="release")
            continue
        assignment = _assignment(line)
        if not assignment:
            continue
        key, value = assignment
        if key in _DEBUG_KEYS:
            if value in _TRUE_VALUES | _DEBUG_MODES:
                result.update(debug=True, mode="debug")
            elif value in _FALSE_VALUES | _RELEASE_MODES:
                result.update(debug=False, mode="release")
        elif key in _MODE_KEYS:
            if value in _DEBUG_MODES | _TRUE_VALUES:
                result.update(debug=True, mode="debug")
            elif value in _RELEASE_MODES | _FALSE_VALUES:
                result.update(debug=False, mode="release")
    return result


def load_runtime_config(app_root: Path) -> dict[str, Any]:
    path = app_root / RUNTIME_CONFIG_FILENAME
    try:
        parsed = parse_runtime_config(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        parsed = dict(DEFAULT_RUNTIME_CONFIG)
    return {**parsed, "path": str(path), "exists": path.is_file()}
