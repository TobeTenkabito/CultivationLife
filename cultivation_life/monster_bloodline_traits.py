from __future__ import annotations

from typing import Any, Final


# Bloodline traits are permanent bodily instincts. Their identifiers,
# presentation and combat hooks are deliberately separate from temporary
# transformation traits.
BLOODLINE_TRAIT_REGISTRY: Final[dict[str, dict[str, Any]]] = {
    "bloodline_skyborn": {
        "name": "御空吐纳", "description": "身处开阔战场时，每轮交锋后恢复 2% 最大法力。",
        "combat_hook": "open_terrain_mana_recovery",
    },
    "bloodline_savage_force": {
        "name": "撕伤追猎", "description": "敌方战斗态势不高于 35% 时，造成的伤害提高 18%。",
        "combat_hook": "wounded_target_execution",
    },
    "bloodline_ancestral_aura": {
        "name": "祖血蚀甲", "description": "面对同境及以下生灵时，祖血气息令敌方防护降低 8%。",
        "combat_hook": "same_or_lower_realm_guard_erosion",
    },
    "bloodline_carapace_guard": {
        "name": "厚甲卸力", "description": "甲壳与鳞皮分散冲击，使单轮战斗态势损失不超过 24%。",
        "combat_hook": "per_round_damage_cap",
    },
    "bloodline_giant_killer": {
        "name": "越阶适应", "description": "面对更高境界敌手时，所受境界压制按少一重大境界计算。",
        "combat_hook": "realm_pressure_resistance",
    },
    "bloodline_terror_aura": {
        "name": "妖煞惊惧", "description": "己方取得先手的回合，敌方本轮威能降低 8%。",
        "combat_hook": "initiative_enemy_might_suppression",
    },
    "bloodline_vital_spark": {
        "name": "本源激生", "description": "每场战斗一次，受创后尚未溃败且态势不高于 25% 时，恢复 8% 态势与 6% 法力；不能起死回生。",
        "combat_hook": "wounded_vitality_surge",
    },
    "bloodline_regeneration": {
        "name": "伤势回收", "description": "每轮受创后回收该轮态势损失的 20%，每轮最多恢复 4%。",
        "combat_hook": "received_damage_reclamation",
    },
    "bloodline_feral_resolve": {
        "name": "困兽护生", "description": "回合开始时己方态势不高于 40%，本轮受到的伤害降低 12%。",
        "combat_hook": "low_state_damage_reduction",
    },
    "bloodline_coiling_lock": {
        "name": "蟠身锁域", "description": "战斗开始时以蛇躯封锁腾挪空间，使敌方身法降低 8%。",
        "combat_hook": "enemy_mobility_erosion",
    },
    "bloodline_gale_feathers": {
        "name": "罡羽破界", "description": "身处开阔战场时，借俯冲与罡羽令自身破法提高 10%。",
        "combat_hook": "open_terrain_breach_bonus",
    },
    "bloodline_counterforce_sinew": {
        "name": "反震战筋", "description": "单轮损失至少 12% 战斗态势后，下一轮自身威能提高 12%。",
        "combat_hook": "damage_taken_counterforce",
    },
    "bloodline_dream_pupil": {
        "name": "梦瞳摄魄", "description": "每当神识压制成功，梦境余波额外削弱敌方 4 点战意。",
        "combat_hook": "control_morale_shock",
    },
    "bloodline_reactive_shell": {
        "name": "应击灵甲", "description": "未能取得先手时，甲纹预判来势，使本轮防护提高 12%。",
        "combat_hook": "lost_initiative_guard_bonus",
    },
    "bloodline_faceted_sense": {
        "name": "万象复眼", "description": "复眼分担神识负荷，使禁神识战场造成的神识惩罚由 14% 降至 6%。",
        "combat_hook": "forbidden_sense_resistance",
    },
    "bloodline_tidal_pulse": {
        "name": "潮脉回环", "description": "偶数轮交锋结束后，潮汐妖脉恢复 3% 最大法力。",
        "combat_hook": "even_round_mana_recovery",
    },
    "bloodline_earthroot": {
        "name": "地脉扎根", "description": "身处狭窄或险要战场时，根系借地，使自身防护提高 10%。",
        "combat_hook": "rooted_terrain_guard_bonus",
    },
}


# Every biological species receives its own sixteen-entry awakening library.
# The shared shapes keep balance auditable, while names and descriptions retain
# the species identity.  A full route has only twelve major evolutions, leaving
# at least four unrolled entries even at the current Da Luo cap.
_SPECIES_POOL_FLAVOR: Final[dict[str, tuple[str, str]]] = {
    "serpent": ("潜鳞", "盘绕筋束与层叠鳞膜"),
    "avian": ("天羽", "翼骨、翎脉与高空本能"),
    "ape": ("战猿", "肩背战筋与返古骨架"),
    "fox": ("月狐", "灵尾、梦瞳与月华妖息"),
    "turtle": ("玄甲", "甲纹、沉血与负岳根骨"),
    "insect": ("百蜕", "复眼、甲节与蜕生腺体"),
    "aquatic": ("沧鳞", "潮腔、水脉与深海感官"),
    "flora": ("灵木", "根网、年轮与生机髓质"),
}
_POOL_ARCHETYPES: Final[tuple[tuple[str, str, str, dict[str, float]], ...]] = (
    ("01", "蛮力", "always", {"might": 1.07}),
    ("02", "护体", "always", {"guard": 1.07}),
    ("03", "迅行", "always", {"mobility": 1.07}),
    ("04", "灵觉", "always", {"sense": 1.07}),
    ("05", "长息", "always", {"sustain": 1.07}),
    ("06", "破罡", "always", {"breach": 1.07}),
    ("07", "猎脉", "always", {"might": 1.045, "sense": 1.045}),
    ("08", "守元", "always", {"guard": 1.045, "sustain": 1.045}),
    ("09", "听风", "always", {"mobility": 1.045, "sense": 1.045}),
    ("10", "裂甲", "always", {"might": 1.045, "breach": 1.045}),
    ("11", "游身", "always", {"mobility": 1.045, "guard": 1.045}),
    ("12", "回气", "always", {"sustain": 1.045, "breach": 1.045}),
    ("13", "凌空", "terrain_open", {"mobility": 1.09}),
    ("14", "盘踞", "terrain_narrow", {"guard": 1.09}),
    ("15", "危觉", "terrain_dangerous", {"sense": 1.09}),
    ("16", "抗禁", "artificial_field", {"guard": 1.06, "breach": 1.06}),
)


def _modifier_description(condition: str, multipliers: dict[str, float]) -> str:
    stat_names = {
        "might": "威能", "guard": "防护", "mobility": "身法",
        "sense": "神识", "sustain": "续航", "breach": "破法",
    }
    condition_text = {
        "always": "",
        "terrain_open": "在开阔战场中，",
        "terrain_narrow": "在狭窄战场中，",
        "terrain_dangerous": "在险要战场中，",
        "artificial_field": "战场存在禁空、禁神识或大阵时，",
    }[condition]
    bonuses = "、".join(
        f"{stat_names[stat]}提高{(multiplier - 1):.1%}"
        for stat, multiplier in multipliers.items()
    )
    return f"{condition_text}{bonuses}。"


for _species_id, (_prefix, _body) in _SPECIES_POOL_FLAVOR.items():
    for _slot, _suffix, _condition, _multipliers in _POOL_ARCHETYPES:
        _trait_id = f"bloodline_{_species_id}_pool_{_slot}"
        BLOODLINE_TRAIT_REGISTRY[_trait_id] = {
            "name": f"{_prefix}·{_suffix}",
            "description": f"{_body}进一步觉醒；{_modifier_description(_condition, _multipliers)}",
            "combat_hook": f"species_pool_{_species_id}_{_slot}",
            "condition": _condition,
            "multipliers": dict(_multipliers),
            "pool_species": _species_id,
        }


def public_bloodline_trait(trait_id: str) -> dict[str, str]:
    definition = BLOODLINE_TRAIT_REGISTRY.get(trait_id)
    if not definition:
        return {"id": trait_id, "name": trait_id, "description": ""}
    return {
        "id": trait_id,
        "name": str(definition["name"]),
        "description": str(definition["description"]),
    }


def bloodline_grants_hook(traits: set[str], combat_hook: str) -> bool:
    return any(
        BLOODLINE_TRAIT_REGISTRY.get(trait_id, {}).get("combat_hook") == combat_hook
        for trait_id in traits
    )


def bloodline_hook_names(traits: set[str], combat_hook: str) -> list[str]:
    return [
        str(BLOODLINE_TRAIT_REGISTRY[trait_id]["name"])
        for trait_id in traits
        if BLOODLINE_TRAIT_REGISTRY.get(trait_id, {}).get("combat_hook") == combat_hook
    ]


def bloodline_stat_modifiers(
    traits: set[str], *, natural_terrain: str, artificial_conditions: list[str],
) -> tuple[dict[str, float], list[str]]:
    factors = {stat: 1.0 for stat in ("might", "guard", "mobility", "sense", "sustain", "breach")}
    conditions = {
        "always": True,
        "terrain_open": natural_terrain == "开阔",
        "terrain_narrow": natural_terrain == "狭窄",
        "terrain_dangerous": natural_terrain == "险要",
        "artificial_field": bool(artificial_conditions),
    }
    triggered: list[str] = []
    for trait_id in sorted(traits):
        definition = BLOODLINE_TRAIT_REGISTRY.get(trait_id, {})
        multipliers = definition.get("multipliers", {})
        if not multipliers or not conditions.get(str(definition.get("condition")), False):
            continue
        for stat, multiplier in multipliers.items():
            if stat in factors:
                factors[stat] *= float(multiplier)
        triggered.append(trait_id)
    return factors, triggered
