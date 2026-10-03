"""Accessors for persistent actor objects and legacy dictionary records."""
from typing import Any


def read(owner: Any, key: str, default=None):
    return owner.get(key, default) if isinstance(owner, dict) else getattr(owner, key, default)


def _write(owner: Any, key: str, value: Any) -> None:
    if isinstance(owner, dict):
        owner[key] = value
    else:
        setattr(owner, key, value)
