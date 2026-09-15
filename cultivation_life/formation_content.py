from __future__ import annotations

import copy
from typing import Any


def expanded_formation_materials(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the compact per-world/per-tier material matrix.

    Hand-authored materials always win for their world/tier/nature cell.  The
    progression matrix only supplies missing basic choices and deliberately
    carries no relation override or battlefield lock.
    """
    result = [copy.deepcopy(row) for row in document.get("materials", [])]
    occupied = {
        (str(row.get("world", "")), int(row.get("tier", -1)), str(row.get("nature", "")))
        for row in result
    }
    progression = document.get("material_progression", {})
    natures = list(map(str, progression.get("natures", [])))
    nature_names = {str(key): str(value) for key, value in progression.get("nature_names", {}).items()}
    tier_definitions = progression.get("tiers", {})
    for world, world_definition in progression.get("worlds", {}).items():
        world = str(world)
        prefix = str(world_definition.get("prefix", world))
        multiplier = float(world_definition.get("value_multiplier", 1.0))
        for tier_value in world_definition.get("tiers", []):
            tier = int(tier_value)
            tier_definition = tier_definitions.get(str(tier), {})
            tier_label = str(tier_definition.get("label", f"{tier}阶"))
            for nature in natures:
                key = (world, tier, nature)
                if key in occupied:
                    continue
                result.append({
                    "id": f"progression_{world}_{tier}_{nature}",
                    "name": f"{prefix}{tier_label}{nature_names.get(nature, nature + '阵材')}",
                    "world": world,
                    "tier": tier,
                    "base_value": max(1, round(float(tier_definition.get("base_value", 1)) * multiplier)),
                    "formation_value": round(
                        float(tier_definition.get("formation_value", 1.0))
                        * float(progression.get("nature_value_multipliers", {}).get(nature, 1.0)),
                        2,
                    ),
                    "nature": nature,
                    "relation_overrides": {},
                    "field_hook": None,
                })
                occupied.add(key)
    return result
