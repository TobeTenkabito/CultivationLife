"""Strict UTF-8 JSON reader shared by base content and extension packages."""
import json
from pathlib import Path
from typing import Any


class ExtensionError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExtensionError(f"JSON 含重复字段：{key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError, ExtensionError) as error:
        raise ExtensionError(f"{path.name} 无法读取：{error}") from error
    if not isinstance(value, dict):
        raise ExtensionError(f"{path.name} 顶层必须是对象")
    return value
