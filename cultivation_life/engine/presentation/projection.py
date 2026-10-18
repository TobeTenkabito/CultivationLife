"""Detached response snapshots; projection has no gameplay or persistence ports."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping
from typing import Any


class _ListValue(tuple):
    """Distinguish JSON lists from the historical tuple-valued public fields."""


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        if any(not isinstance(key, (str, int, float, bool, type(None))) for key in value):
            raise TypeError('视图快照只允许普通展示数据键')
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _ListValue(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError('视图快照不能持有游戏对象或运行时服务')


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, _ListValue):
        return [_thaw(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_thaw(item) for item in value)
    return value


@dataclass(frozen=True, slots=True, init=False)
class PreparedGameView:
    _payload: Mapping[str, Any]

    def __init__(self, payload: dict[str, Any]):
        if not isinstance(payload, dict):
            raise TypeError('视图快照须从已准备的展示数据创建')
        # Freeze only the exposed response, never a GameState, NPC registry or pool.
        object.__setattr__(self, '_payload', _freeze(payload))


def project_game(prepared: PreparedGameView) -> dict[str, Any]:
    """Return independent output; caller edits cannot change this snapshot."""
    if not isinstance(prepared, PreparedGameView):
        raise TypeError('投影只接受已经准备好的视图快照')
    return _thaw(prepared._payload)
