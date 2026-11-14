"""Shared qi thresholds and technique eligibility, with no settlement dependency."""
from __future__ import annotations

import math
from typing import Any

from .content_registry import WORLD_SYSTEMS
from .models import Player


QI_SOURCE_NAMES = {
    "spirit": "灵源",
    "demon": "魔源",
    "monster": "妖源",
    "yin": "阴源",
}
QI_NAMES = {source: name.removesuffix("源") + "气" for source, name in QI_SOURCE_NAMES.items()}
COMBAT_REQUIREMENT_OPERATORS = {
    ">=": lambda left, right: left >= right,
    ">": lambda left, right: left > right,
    "<=": lambda left, right: left <= right,
    "<": lambda left, right: left < right,
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
}
def qi_level_threshold(level: int) -> float:
    """某等级的累计经验下限；平方曲线让高等级逐步放缓。"""
    level = max(0, int(level))
    base = float(WORLD_SYSTEMS.get("qi_mastery", {}).get("experience_base", 25))
    return base * level * level


def qi_level(experience: float) -> int:
    base = float(WORLD_SYSTEMS.get("qi_mastery", {}).get("experience_base", 25))
    return max(0, int(math.sqrt(max(0.0, float(experience)) / base)))


def qi_levels(player: Player) -> dict[str, int]:
    return {source: qi_level(player.qi_experience.get(source, 0.0)) for source in QI_SOURCE_NAMES}


def valid_combat_requirement(requirement: Any) -> bool:
    if not isinstance(requirement, dict) or len(requirement) != 1:
        return False
    if "all" in requirement or "any" in requirement:
        key = "all" if "all" in requirement else "any"
        children = requirement[key]
        return isinstance(children, list) and bool(children) and all(valid_combat_requirement(child) for child in children)
    if "not" in requirement:
        return valid_combat_requirement(requirement["not"])
    leaf = requirement.get("source")
    if not isinstance(leaf, dict) or set(leaf) != {"id", "op", "level"}:
        return False
    return (
        leaf["id"] in QI_SOURCE_NAMES
        and leaf["op"] in COMBAT_REQUIREMENT_OPERATORS
        and isinstance(leaf["level"], int)
        and leaf["level"] >= 0
    )


def combat_requirement_met(requirement: dict[str, Any], levels: dict[str, int]) -> bool:
    if "all" in requirement:
        return all(combat_requirement_met(child, levels) for child in requirement["all"])
    if "any" in requirement:
        return any(combat_requirement_met(child, levels) for child in requirement["any"])
    if "not" in requirement:
        return not combat_requirement_met(requirement["not"], levels)
    leaf = requirement["source"]
    return COMBAT_REQUIREMENT_OPERATORS[leaf["op"]](int(levels.get(leaf["id"], 0)), leaf["level"])


def combat_requirement_display(requirement: dict[str, Any]) -> str:
    if "all" in requirement or "any" in requirement:
        key, conjunction = ("all", " 且 ") if "all" in requirement else ("any", " 或 ")
        return "（" + conjunction.join(combat_requirement_display(child) for child in requirement[key]) + "）"
    if "not" in requirement:
        return "非" + combat_requirement_display(requirement["not"])
    leaf = requirement["source"]
    return f"{QI_NAMES[leaf['id']]} {leaf['op']} {leaf['level']}级"


