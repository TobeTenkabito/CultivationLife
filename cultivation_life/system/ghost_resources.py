"""Ghost resource state and soul projections without reincarnation or world actions."""
from __future__ import annotations
import copy
import math
from typing import Any
from ..content_registry import REALMS, WORLD_SYSTEMS
from ..ghost_soul_traits import validate_generated_soul_trait
from ..models import Player
from .possession_system import is_possessed
from .immortal_cultivation import body_intrinsic_bonus, vein_intrinsic_bonus
from .asura import intrinsic_bonus as asura_intrinsic_bonus


GHOST_DLC_NAME = "百鬼夜行：往生轮回"


SOUL_SLOTS = {
    "胎光": ("opportunity", "机缘效率"), "爽灵": ("external_mp", "外源 MP"),
    "幽精": ("external_hp", "外源 HP"), "尸狗": ("mobility", "身法"),
    "伏矢": ("might", "威能"), "雀阴": ("resolve", "定力"),
    "吞贼": ("guard", "护御"), "非毒": ("sense", "神识"),
    "除秽": ("breach", "破防"), "臭肺": ("sustain", "续战"),
}


THREE_SOUL_STATS = frozenset({"opportunity", "external_mp", "external_hp"})


# Legacy fixed soul traits remain executable so existing saves keep their exact
# behavior.  Newly spawned night-parade souls use the generated rule grammar in
# ghost_soul_traits.py instead.
SOUL_TRAIT_RULES = {
    "寒魄": "失去先手时，本轮防护提高 12%",
    "执念": "受到的战意损失降低 25%，战意最低保留 8 点",
    "迅影": "前两轮争夺先手时，身法判定提高 12%",
    "噬灵": "每次有效攻势侵蚀敌方 4% 防护，最多叠加三层",
    "宿慧": "所有机缘获取额外提高 8%",
    "不灭": "每场战斗首次陷入危局时，恢复 8% 战斗态势与 5% 法力",
    "凶魂": "敌方战斗态势不高于 35% 时，造成的损耗提高 15%",
    "明识": "禁神识环境的惩罚由 14% 降至 6%",
}


def ghost_cultivation_config() -> dict[str, Any]:
    return WORLD_SYSTEMS.get("ghost_cultivation", {})


def ghost_cultivation_active(player: Player) -> bool:
    config = ghost_cultivation_config()
    return bool(config.get("enabled", False) and player.path == "ghost")


def ghost_phase_two_config() -> dict[str, Any]:
    return ghost_cultivation_config().get("phase_two", {})


def active_bound_souls(player: Player) -> list[tuple[str, dict[str, Any]]]:
    if not ghost_cultivation_active(player) or is_possessed(player):
        return []
    by_id = {str(row.get("id")): row for row in player.ghost_bound_souls}
    return [(slot, by_id[soul_id]) for slot, soul_id in player.ghost_soul_slots.items()
            if slot in SOUL_SLOTS and soul_id in by_id]


def active_soul_traits(player: Player) -> set[str]:
    return {
        str(soul.get("soul_trait", {}).get("name", ""))
        for _, soul in active_bound_souls(player)
        if str(soul.get("soul_trait", {}).get("name", "")) in SOUL_TRAIT_RULES
    }


def active_generated_soul_traits(player: Player) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(trait)
        for _, soul in active_bound_souls(player)
        if isinstance((trait := soul.get("soul_trait")), dict)
        and bool(trait.get("generated"))
        and not validate_generated_soul_trait(trait)
    ]


def ghost_soul_effects(player: Player) -> dict[str, float]:
    config = ghost_phase_two_config().get("soul_slots", {})
    seven_cap = max(0.0, float(config.get("seven_effect_cap", config.get("effect_cap", 0.25))))
    three_coefficient = max(0.0, float(config.get("three_soul_log_coefficient", 0.18)))
    scale = max(1.0, float(config.get("power_scale", 2500.0)))
    result = {key: 0.0 for key in {
        "opportunity", "external_mp", "external_hp", "mobility", "might",
        "resolve", "guard", "sense", "breach", "sustain",
    }}
    for slot, soul in active_bound_souls(player):
        stat = SOUL_SLOTS[slot][0]
        power = max(0.0, float(soul.get("combat_power", 0.0)))
        value = (
            three_coefficient * math.log1p(power / scale)
            if stat in THREE_SOUL_STATS
            else seven_cap * (1.0 - math.exp(-power / scale))
        )
        result[stat] += value
    return result


def ghost_soul_pressure(player: Player) -> tuple[float, float]:
    if not ghost_cultivation_active(player) or is_possessed(player):
        return 0.0, 0.0
    pressure = sum(max(0.0, float(soul.get("soul_pressure", 0.0)))
                   for _, soul in active_bound_souls(player))
    per_point = max(0.0, float(ghost_phase_two_config().get("pressure_modifier_per_point", 0.01)))
    return pressure, pressure * per_point


def ghost_external_hp_bonus(player: Player) -> float:
    return intrinsic_hp_reference(player) * ghost_soul_effects(player)["external_hp"]


def ghost_external_mp_bonus(player: Player) -> float:
    return intrinsic_mp_reference(player) * ghost_soul_effects(player)["external_mp"]


def ghost_opportunity_multiplier(player: Player) -> float:
    multiplier = 1.0 + ghost_soul_effects(player)["opportunity"]
    if "宿慧" in active_soul_traits(player):
        multiplier *= 1.08
    if ghost_cultivation_active(player) and player.ghost_attachment:
        multiplier *= max(0.0, float(player.ghost_attachment.get("cultivation_efficiency_multiplier", 1.0)))
    return multiplier


def canonical_intrinsic_hp(
    player: Player, *, realm_index: int | None = None, layer: int | None = None,
) -> float:
    definition = REALMS[player.realm_index if realm_index is None else realm_index]
    actual_layer = player.layer if layer is None else layer
    return float(
        100
        + int(definition.base_power ** 0.5 * 16)
        + actual_layer * 8
        + player.body_training * 12
        + body_intrinsic_bonus(player, "hp")
        + vein_intrinsic_bonus(player, "hp")
        + asura_intrinsic_bonus(player, "hp")
        + player.permanent_intrinsic_hp_bonus
    )


def canonical_intrinsic_mp(
    player: Player, *, realm_index: int | None = None, layer: int | None = None,
) -> float:
    definition = REALMS[player.realm_index if realm_index is None else realm_index]
    actual_layer = player.layer if layer is None else layer
    return float(
        40
        + int(definition.base_power ** 0.5 * 20)
        + actual_layer * 11
        + player.body_training * 10
        + body_intrinsic_bonus(player, "mp")
        + vein_intrinsic_bonus(player, "mp")
        + asura_intrinsic_bonus(player, "mp")
        + player.permanent_intrinsic_mp_bonus
    )


def ensure_ghost_cultivation_state(player: Player) -> bool:
    """Initialize new/legacy ghost saves without retroactive erosion."""
    if not ghost_cultivation_active(player):
        return False
    changed = False
    if player.ghost_intrinsic_hp_reference is None:
        player.ghost_intrinsic_hp_reference = canonical_intrinsic_hp(player)
        changed = True
    if player.ghost_intrinsic_mp_reference is None:
        player.ghost_intrinsic_mp_reference = canonical_intrinsic_mp(player)
        changed = True
    if player.ghost_intrinsic_hp_current is None:
        player.ghost_intrinsic_hp_current = player.ghost_intrinsic_hp_reference
        changed = True
    if player.ghost_intrinsic_mp_current is None:
        player.ghost_intrinsic_mp_current = player.ghost_intrinsic_mp_reference
        changed = True
    if player.ghost_intrinsic_highwater_realm is None:
        player.ghost_intrinsic_highwater_realm = player.realm_index
        player.ghost_intrinsic_highwater_layer = player.layer
        changed = True
    # V2 reuses the base milestone map for achievements.  Derive the count from
    # permanent V1 imprints so existing saves receive full credit on first load.
    imprint_total = sum(max(0, int(count)) for count in player.ghost_reincarnation_imprints.values())
    if int(player.milestones.get("ghost_reincarnations", 0)) < imprint_total:
        player.milestones["ghost_reincarnations"] = imprint_total
        changed = True
    if ghost_cultivation_config().get("infinite_lifespan", True) and player.lifespan is not None:
        player.lifespan = None
        changed = True
    return changed


def intrinsic_hp_reference(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_hp_reference or 0.0))
    return canonical_intrinsic_hp(player)


def intrinsic_mp_reference(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_mp_reference or 0.0))
    return canonical_intrinsic_mp(player)


def effective_intrinsic_hp(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_hp_current or 0.0))
    return intrinsic_hp_reference(player)


def effective_intrinsic_mp(player: Player) -> float:
    if ghost_cultivation_active(player):
        ensure_ghost_cultivation_state(player)
        return max(0.0, float(player.ghost_intrinsic_mp_current or 0.0))
    return intrinsic_mp_reference(player)


def hp_carry_ratio(player: Player) -> float:
    reference = intrinsic_hp_reference(player)
    return 1.0 if not ghost_cultivation_active(player) else max(
        0.0, min(1.0, effective_intrinsic_hp(player) / max(reference, 1e-12)),
    )


def mp_carry_ratio(player: Player) -> float:
    reference = intrinsic_mp_reference(player)
    return 1.0 if not ghost_cultivation_active(player) else max(
        0.0, min(1.0, effective_intrinsic_mp(player) / max(reference, 1e-12)),
    )
