"""Achievement catalog validation, independent of gameplay and persistent metadata."""
import copy
from typing import Any


ALLOWED_SOURCE_KINDS = {"base", "dlc", "mod"}


ALLOWED_CATEGORIES = {"story", "cultivation"}


def load_achievement_definitions(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Validate and freeze the data-driven achievement catalog."""
    if document.get("schema_version") != 1 or not isinstance(document.get("achievements"), list):
        raise ValueError("achievements.json 须声明 schema_version=1 与 achievements 数组")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in document["achievements"]:
        if not isinstance(row, dict):
            raise ValueError("成就定义必须是对象")
        achievement_id = str(row.get("id", ""))
        source = row.get("source", {})
        if not achievement_id or achievement_id in seen:
            raise ValueError("成就定义存在缺失或重复 ID")
        if not row.get("name") or not row.get("description") or row.get("category") not in ALLOWED_CATEGORIES:
            raise ValueError(f"成就 {achievement_id} 缺少名称、条件说明或合法分类")
        if not isinstance(source, dict) or source.get("kind") not in ALLOWED_SOURCE_KINDS:
            raise ValueError(f"成就 {achievement_id} 必须声明本体、DLC 或 MOD 来源")
        if not source.get("id") or not source.get("name") or not isinstance(row.get("condition"), dict):
            raise ValueError(f"成就 {achievement_id} 的来源或解锁条件不完整")
        seen.add(achievement_id)
        result.append(copy.deepcopy(row))
    return tuple(result)
