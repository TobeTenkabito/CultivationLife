from __future__ import annotations

import random
from typing import Any, Final, Iterable

from .models import Player


STAT_KEYS: Final = ("might", "guard", "mobility", "sense", "sustain", "breach")

# These are the base-game fallback for monster cultivators whose bloodline DLC
# is disabled.  Their 2-4% bonuses are intentionally below bloodline traits,
# which commonly grant 8-18% or change a combat rule outright.
GENERAL_MONSTER_TRAIT_REGISTRY: Final[dict[str, dict[str, Any]]] = {
    "monster_common_stout_hide": {
        "name": "坚韧皮膜", "description": "防护提高 3%。",
        "condition": "always", "multipliers": {"guard": 1.03},
    },
    "monster_common_heavy_sinew": {
        "name": "厚重筋力", "description": "威能提高 3%。",
        "condition": "always", "multipliers": {"might": 1.03},
    },
    "monster_common_light_step": {
        "name": "轻灵步态", "description": "身法提高 3%。",
        "condition": "always", "multipliers": {"mobility": 1.03},
    },
    "monster_common_clear_sense": {
        "name": "澄明灵觉", "description": "神识提高 3%。",
        "condition": "always", "multipliers": {"sense": 1.03},
    },
    "monster_common_long_breath": {
        "name": "绵长吐息", "description": "续航提高 3%。",
        "condition": "always", "multipliers": {"sustain": 1.03},
    },
    "monster_common_sharp_claw": {
        "name": "锐爪利齿", "description": "破法提高 3%。",
        "condition": "always", "multipliers": {"breach": 1.03},
    },
    "monster_common_hunting_instinct": {
        "name": "寻隙本能", "description": "威能与神识各提高 2%。",
        "condition": "always", "multipliers": {"might": 1.02, "sense": 1.02},
    },
    "monster_common_rock_bones": {
        "name": "岩骨沉血", "description": "防护与续航各提高 2%。",
        "condition": "always", "multipliers": {"guard": 1.02, "sustain": 1.02},
    },
    "monster_common_wind_listener": {
        "name": "听风辨位", "description": "身法与神识各提高 2%。",
        "condition": "always", "multipliers": {"mobility": 1.02, "sense": 1.02},
    },
    "monster_common_armor_gnawer": {
        "name": "啮甲习性", "description": "威能与破法各提高 2%。",
        "condition": "always", "multipliers": {"might": 1.02, "breach": 1.02},
    },
    "monster_common_evasive_hide": {
        "name": "滑鳞卸势", "description": "身法与防护各提高 2%。",
        "condition": "always", "multipliers": {"mobility": 1.02, "guard": 1.02},
    },
    "monster_common_qi_cycle": {
        "name": "妖息小周天", "description": "续航与破法各提高 2%。",
        "condition": "always", "multipliers": {"sustain": 1.02, "breach": 1.02},
    },
    "monster_common_open_stride": {
        "name": "旷野疾行", "description": "开阔战场中，身法提高 4%。",
        "condition": "terrain_open", "multipliers": {"mobility": 1.04},
    },
    "monster_common_tight_footing": {
        "name": "窄地盘踞", "description": "狭窄战场中，防护提高 4%。",
        "condition": "terrain_narrow", "multipliers": {"guard": 1.04},
    },
    "monster_common_peril_awareness": {
        "name": "险地警觉", "description": "险要战场中，神识提高 4%。",
        "condition": "terrain_dangerous", "multipliers": {"sense": 1.04},
    },
    "monster_common_uphill_tenacity": {
        "name": "禁制耐性", "description": "战场存在禁空、禁神识或大阵时，防护提高 4%。",
        "condition": "artificial_field", "multipliers": {"guard": 1.04},
    },
}


def public_general_monster_trait(trait_id: str) -> dict[str, str]:
    definition = GENERAL_MONSTER_TRAIT_REGISTRY.get(trait_id)
    if not definition:
        return {"id": trait_id, "name": trait_id, "description": ""}
    return {
        "id": trait_id,
        "name": str(definition["name"]),
        "description": str(definition["description"]),
    }


def active_general_monster_traits(player: Player, *, bloodline_available: bool) -> list[str]:
    """Return fallback traits only while the bloodline DLC is unavailable."""
    if player.path != "monster" or bloodline_available:
        return []
    return list(dict.fromkeys(
        trait_id for trait_id in map(str, player.monster_general_traits)
        if trait_id in GENERAL_MONSTER_TRAIT_REGISTRY
    ))


def grant_random_general_monster_trait(
    player: Player, rng: random.Random, *, bloodline_available: bool,
) -> dict[str, str] | None:
    """Grant one non-repeating base-game trait after a major breakthrough."""
    if player.path != "monster" or bloodline_available:
        return None
    owned = set(map(str, player.monster_general_traits))
    remaining = [trait_id for trait_id in GENERAL_MONSTER_TRAIT_REGISTRY if trait_id not in owned]
    if not remaining:
        return None
    trait_id = rng.choice(remaining)
    player.monster_general_traits.append(trait_id)
    return public_general_monster_trait(trait_id)


def general_monster_trait_modifiers(
    trait_ids: Iterable[str], *, natural_terrain: str, artificial_conditions: Iterable[str] = (),
) -> tuple[dict[str, float], list[str]]:
    """Resolve the small passive multipliers for the current battlefield."""
    factors = {stat: 1.0 for stat in STAT_KEYS}
    triggered: list[str] = []
    conditions = {
        "always": True,
        "terrain_open": natural_terrain == "开阔",
        "terrain_narrow": natural_terrain == "狭窄",
        "terrain_dangerous": natural_terrain == "险要",
        "artificial_field": bool(tuple(artificial_conditions)),
    }
    for trait_id in dict.fromkeys(map(str, trait_ids)):
        definition = GENERAL_MONSTER_TRAIT_REGISTRY.get(trait_id)
        if not definition or not conditions.get(str(definition.get("condition")), False):
            continue
        for stat, multiplier in definition.get("multipliers", {}).items():
            if stat in factors:
                factors[stat] *= float(multiplier)
        triggered.append(trait_id)
    return factors, triggered


def _validate_registry() -> None:
    if len(GENERAL_MONSTER_TRAIT_REGISTRY) != 16:
        raise RuntimeError("本体妖修通用特质池必须恰好包含 16 项")
    valid_conditions = {
        "always", "terrain_open", "terrain_narrow", "terrain_dangerous", "artificial_field",
    }
    for trait_id, definition in GENERAL_MONSTER_TRAIT_REGISTRY.items():
        multipliers = definition.get("multipliers", {})
        if (
            not trait_id.startswith("monster_common_")
            or not definition.get("name") or not definition.get("description")
            or definition.get("condition") not in valid_conditions
            or not multipliers or set(multipliers) - set(STAT_KEYS)
            or any(not 1.0 < float(value) <= 1.04 for value in multipliers.values())
        ):
            raise RuntimeError(f"本体妖修通用特质定义不合法：{trait_id}")


_validate_registry()
