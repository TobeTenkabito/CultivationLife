"""Owned artifact projections, independent of forging actions and aggregated player rules."""
from __future__ import annotations
import copy
from typing import Any
from ..content_registry import WORLD_SYSTEMS
from ..models import Player


STAT_NAMES = {
    "combat_power": "战斗力", "max_hp": "最大HP", "max_mp": "最大MP",
    "opportunity_efficiency": "机缘效率", "body_training_efficiency": "炼体效率",
    "divine_sense_efficiency": "神识效率", "tribulation_reduction": "渡劫减伤",
    "breakthrough_bonus": "突破加成",
}


def tianji_world_combat_power_cap(world: str) -> float | None:
    """Return the hard per-artifact combat-power cap of the current world.

    This is deliberately separate from forging/replica caps.  A replica keeps
    its true inherited power in the save, while only the amount permitted by
    the current world's laws contributes to combat.
    """
    config = WORLD_SYSTEMS.get("tianji_artifacts", {})
    caps = config.get("world_combat_power_caps", {}) if isinstance(config, dict) else {}
    world_id = str(world)
    if isinstance(caps, dict) and world_id in caps:
        raw = caps[world_id]
        # An explicit null means this third-tier world fully releases the
        # artifact.  It must not be confused with an unknown future world.
        if raw is None:
            return None
    else:
        profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world_id, {})
        tier = max(1, int(profile.get("tier", 1))) if isinstance(profile, dict) else 1
        if tier >= 3:
            return None
        raw = 9_999_999 if tier == 2 else 99_999
    value = float(raw)
    return value if value > 0 else None


def effective_tianji_combat_power(raw_power: float, world: str) -> float:
    raw = max(0.0, float(raw_power))
    cap = tianji_world_combat_power_cap(world)
    return min(raw, cap) if cap is not None else raw


def active_crafted_artifacts(player: Player) -> list[dict[str, Any]]:
    active_ids = {
        str(item.crafted_artifact_id)
        for item in player.inventory
        if item.quantity > 0 and item.crafted_artifact_id
    }
    # In-memory legacy fixtures may not have passed through Player.from_dict;
    # the new rule is that every owned crafted artifact is automatically live.
    if not active_ids and player.crafted_artifacts:
        active_ids = {str(row.get("id", "")) for row in player.crafted_artifacts}
    equipped_tianji = set(map(str, player.equipped_crafted_artifact_ids))
    return [
        row for row in player.crafted_artifacts
        if isinstance(row, dict) and str(row.get("id")) in active_ids
        and (
            not row.get("tianji")
            or (
                bool(WORLD_SYSTEMS.get("tianji_artifacts", {}).get("enabled"))
                and str(row.get("id")) in equipped_tianji
            )
        )
    ]


def crafted_artifact_bonuses(player: Player) -> dict[str, float]:
    totals = {key: 0.0 for key in STAT_NAMES}
    breakthrough_values: list[float] = []
    for artifact in active_crafted_artifacts(player):
        stats = artifact.get("actual_stats", {})
        for key in totals:
            value = max(0.0, float(stats.get(key, 0.0)))
            if key == "breakthrough_bonus":
                breakthrough_values.append(min(0.05, value))
            else:
                totals[key] += value
    # 炼器法宝的突破属性永远只取当前生效法宝里的最高值，禁止多件叠加。
    totals["breakthrough_bonus"] = max(breakthrough_values, default=0.0)
    return totals


def effective_artifact_combat_bonus(player: Player) -> float:
    """Resolve crafted and natal combat power after per-Tianji world caps.

    Every active Tianji is capped independently.  If it is also the natal
    artifact, all refinement, socket and future natal combat growth is folded
    into that same capped contribution so no secondary progression path can
    bypass the world's hard ceiling.  Non-combat stats and combat effects are
    intentionally untouched.
    """
    active = active_crafted_artifacts(player)
    natal_tianji = next(
        (row for row in player.crafted_artifacts if row.get("is_natal") and row.get("tianji")),
        None,
    )
    total = 0.0
    for artifact in active:
        raw = max(0.0, float(artifact.get("actual_stats", {}).get("combat_power", 0.0)))
        if artifact.get("tianji"):
            if artifact.get("is_natal"):
                raw += max(0.0, float(player.natal_artifact_combat_bonus))
            total += effective_tianji_combat_power(raw, player.world)
        else:
            total += raw
    if natal_tianji is None:
        total += max(0.0, float(player.natal_artifact_combat_bonus))
    return total


def crafted_combat_effects(player: Player) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for artifact in active_crafted_artifacts(player):
        for effect in artifact.get("combat_effects", []):
            if isinstance(effect, dict):
                effects.append(copy.deepcopy(effect) | {
                    "item_id": str(artifact.get("id", "")), "name": str(artifact.get("name", "法宝")),
                })
    return effects
