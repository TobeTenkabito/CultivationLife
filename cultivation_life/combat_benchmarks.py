"""Shared realm combat benchmarks derived only from loaded content."""
from .content_registry import REALMS, WORLD_SYSTEMS, GUIXU_TIDE_CONTENT


def standard_combat_power_dlc_bonus() -> float:
    """Add enabled DLC benchmark bonuses before applying one multiplier."""
    bonuses: list[float] = []
    tianji = WORLD_SYSTEMS.get("tianji_artifacts", {})
    if isinstance(tianji, dict) and tianji.get("enabled"):
        bonuses.append(max(0.0, float(tianji.get("standard_combat_power_bonus", 0.0))))
    guixu_settings = GUIXU_TIDE_CONTENT.get("settings", {})
    if GUIXU_TIDE_CONTENT.get("dungeons") and isinstance(guixu_settings, dict):
        bonuses.append(max(0.0, float(guixu_settings.get("standard_combat_power_bonus", 0.0))))
    return sum(bonuses)


def expected_combat_power(realm_index: int, layer: int) -> float:
    """返回玩家、NPC 与动态事件共用、含已启用 DLC 加成的境界战力基准。"""
    definition = REALMS[realm_index]
    values = WORLD_SYSTEMS["combat_expectations"][definition.id]
    if definition.id == "mortal":
        base = float(values["value"])
    elif definition.id == "qi":
        base = float(values["base"] + values["layer_step"] * (max(1, layer) - 1))
    elif "value" in values:
        base = float(values["value"]) * (1 + .08 * (max(1, min(9, layer)) - 1))
    else:
        stage = "early" if layer <= 3 else "middle" if layer <= 6 else "late"
        base = float(values[stage])
    return base * (1.0 + standard_combat_power_dlc_bonus())
