from __future__ import annotations

import copy
import math
import random
from typing import Any

from .content_registry import (
    AFFINITY_NAMES, ELEMENT_NAMES, FACTION_DEFINITIONS, FACTION_NPC_TEMPLATES,
    FACTION_REWARDS, ITEM_CATALOG, KARMA_FACTORS, MUTATED_NAMES, PATH_NAMES,
    RACE_DEFINITIONS, REALMS, ROOT_DEFINITIONS, ROOT_NAMES, TECHNIQUE_CATALOG, TECHNIQUE_ELEMENT_NAMES,
    WORLD_SYSTEMS,
)
from .models import Item, Player, RealmDef, Technique
from .ghost_system import (
    effective_intrinsic_hp, effective_intrinsic_mp, hp_carry_ratio,
    intrinsic_hp_reference, intrinsic_mp_reference, mp_carry_ratio,
    ghost_external_hp_bonus, ghost_external_mp_bonus,
    ghost_opportunity_multiplier,
)
from .possession_system import current_body_age
from .transformation_system import (
    ensure_transformation_state, equip_transformation_technique, transformation_technique_limits,
)


LEGACY_ROOTS = {
    "metal": "supreme_metal", "wood": "supreme_wood", "water": "supreme_water",
    "fire": "supreme_fire", "earth": "supreme_earth", "mutated": "mutated_thunder",
    "heavenly": "heavenly_metal_wood",
}

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
TECHNIQUE_MAX_LEVEL = 9
TECHNIQUE_MANUAL_PREFIX = "technique_manual::"

def create_technique(
    technique_id: str, name: str, path: str, element: str,
    opportunity_bonus: float, hp_bonus: float, mp_bonus: float, combat_bonus: float,
    *, grade: int = 1, level: int = 1, karma_multiplier: float = 1.0,
    category: str = "spiritual", body_breakthrough_bonus: float = 0.0,
    body_bonus_max_layer: int | None = None,
    sources: dict[str, float] | None = None,
    combat_requirements: dict[str, Any] | None = None,
    divine_sense_bonus: float = 0.0,
    transformation_capacity: int = 0,
    transformation_space: int = 0,
    initial_transformations: list[str] | None = None,
    requires_immortal_power: bool = False,
    immortal_power_cost: float = 0.0,
    required_body_training: int = 0,
    possession_limit_bonus: int = 0,
    ignore_possession_limit: bool = False,
) -> Technique:
    technique = Technique(
        id=technique_id, name=name, path=path, element=element, grade=grade, level=level,
        opportunity_bonus=opportunity_bonus, hp_bonus=hp_bonus, mp_bonus=mp_bonus,
        combat_bonus=combat_bonus, karma_multiplier=karma_multiplier,
        category=category, body_breakthrough_bonus=body_breakthrough_bonus,
        body_bonus_max_layer=body_bonus_max_layer,
        sources=dict(sources or {}),
        combat_requirements=copy.deepcopy(combat_requirements or {}),
        divine_sense_bonus=divine_sense_bonus,
        transformation_capacity=transformation_capacity,
        transformation_space=transformation_space,
        initial_transformations=list(initial_transformations or []),
        requires_immortal_power=requires_immortal_power,
        immortal_power_cost=immortal_power_cost,
        required_body_training=required_body_training,
        possession_limit_bonus=possession_limit_bonus,
        ignore_possession_limit=ignore_possession_limit,
    )
    validate_technique(technique)
    return technique


def validate_technique(technique: Technique) -> None:
    """每一部功法自身必须完整覆盖机缘、HP、MP 与独立战力四项。"""
    values = (technique.opportunity_bonus, technique.hp_bonus, technique.mp_bonus, technique.combat_bonus)
    if any(value <= 0 for value in values):
        raise ValueError(f"功法 {technique.name} 缺少四项必备属性")
    if technique.karma_multiplier <= 0:
        raise ValueError("功法因果倍率必须大于 0")
    if technique.category not in {"spiritual", "body", "divine_sense", "transformation"}:
        raise ValueError("未知功法类型")
    if technique.category == "body" and technique.element != "neutral":
        raise ValueError("炼体功法必须为所有灵根均可修炼的无属性功法")
    if technique.category == "body" and (
        technique.body_breakthrough_bonus <= 0 or not technique.body_bonus_max_layer
    ):
        raise ValueError("炼体功法必须声明突破加成与适用层数")
    if technique.category == "divine_sense" and technique.divine_sense_bonus <= 0:
        raise ValueError("神识功法必须声明正数神识修炼加成")
    if technique.category == "transformation" and (
        technique.transformation_capacity <= 0
        or technique.transformation_space <= 0
        or technique.transformation_space > technique.transformation_capacity
        or bool(technique.initial_transformations)
    ):
        raise ValueError("变身功法只能声明合法的容量与空间，不能预设变身")
    if technique.requires_immortal_power and not 0 < technique.immortal_power_cost < 1:
        raise ValueError("仙家功法必须声明合法的仙灵力消耗")
    if not technique.requires_immortal_power and technique.immortal_power_cost != 0:
        raise ValueError("普通功法不能声明仙灵力消耗")
    if not 0 <= int(technique.required_body_training) <= 100:
        raise ValueError("功法炼体门槛必须位于零至一百层")
    if int(technique.possession_limit_bonus) < 0:
        raise ValueError("夺舍次数加成不能为负数")
    if not technique.sources or set(technique.sources) - set(QI_SOURCE_NAMES):
        raise ValueError("功法必须声明合法的先天源")
    if any(weight <= 0 for weight in technique.sources.values()):
        raise ValueError("功法的源利用权重必须大于 0")
    if not math.isclose(sum(technique.sources.values()), 1.0, abs_tol=1e-9):
        raise ValueError("功法的源利用权重之和必须为 1")
    if not valid_combat_requirement(technique.combat_requirements):
        raise ValueError("功法的战斗使用门槛表达式不合法")


def technique_scale(technique: Technique) -> float:
    """Keep the established grade balance and apply the explicit Lv.1–9 multiplier."""
    grade_multiplier = 1.0 + 0.12 * (max(1, int(technique.grade)) - 1)
    return grade_multiplier * technique.level_multiplier


def effective_technique_karma_multiplier(technique: Technique) -> float:
    """Amplify a karma modifier around the neutral value instead of multiplying 1.0."""
    return 1.0 + (float(technique.karma_multiplier) - 1.0) * technique.level_multiplier


def technique_manual_item_id(technique_id: str, level: int = 1) -> str:
    manual_level = max(1, min(TECHNIQUE_MAX_LEVEL, int(level)))
    return f"{TECHNIQUE_MANUAL_PREFIX}{technique_id}::lv{manual_level}"


def technique_manual_description(technique_name: str, level: int) -> str:
    if level >= TECHNIQUE_MAX_LEVEL:
        return f"可用于同名 Lv.{level} 功法的最终合参；此玉简已达最高等级，不能继续合成。"
    return (
        f"升级同名 Lv.{level} 功法时消耗一份；也可用两份同名同级玉简"
        f"合成一份 Lv.{level + 1} 玉简。"
    )


def _normalize_technique_manuals(player: Player) -> None:
    """Migrate legacy unlevelled manuals and merge equal ID/level stacks."""
    ordinary_items: list[Item] = []
    manuals: dict[tuple[str, int], Item] = {}
    known_names = {technique.id: technique.name for technique in player.known_techniques}
    for item in player.inventory:
        if not item.technique_id and not item.id.startswith(TECHNIQUE_MANUAL_PREFIX):
            ordinary_items.append(item)
            continue
        technique_id = str(item.technique_id or item.id.removeprefix(TECHNIQUE_MANUAL_PREFIX))
        parsed_level = 1
        if "::lv" in technique_id:
            technique_id, raw_level = technique_id.rsplit("::lv", 1)
            try:
                parsed_level = int(raw_level)
            except ValueError:
                parsed_level = 1
        manual_level = max(1, min(
            TECHNIQUE_MAX_LEVEL,
            int(item.technique_level if item.technique_level is not None else parsed_level),
        ))
        key = (technique_id, manual_level)
        if key in manuals:
            manuals[key].quantity += max(0, int(item.quantity))
            continue
        template = TECHNIQUE_CATALOG.get(technique_id)
        technique_name = known_names.get(technique_id) or (template.name if template else item.name)
        technique_name = technique_name.removeprefix("《").split("》", 1)[0]
        manuals[key] = Item(
            id=technique_manual_item_id(technique_id, manual_level),
            name=f"《{technique_name}》Lv.{manual_level} 传承玉简",
            quantity=max(0, int(item.quantity)),
            technique_id=technique_id,
            technique_level=manual_level,
            description=technique_manual_description(technique_name, manual_level),
            tags=list(dict.fromkeys([*item.tags, "technique_manual"])),
        )
    player.inventory = ordinary_items + [item for item in manuals.values() if item.quantity > 0]


def technique_copy_count(player: Player, technique_id: str, level: int | None = None) -> int:
    _normalize_technique_manuals(player)
    return sum(
        max(0, int(item.quantity)) for item in player.inventory
        if item.technique_id == technique_id
        and (level is None or item.technique_level == int(level))
    )


def add_technique_copy(
    player: Player, technique: Technique, quantity: int = 1, *, level: int | None = None,
) -> None:
    quantity = max(0, int(quantity))
    if quantity <= 0:
        return
    _normalize_technique_manuals(player)
    manual_level = max(1, min(TECHNIQUE_MAX_LEVEL, int(level if level is not None else technique.level)))
    item_id = technique_manual_item_id(technique.id, manual_level)
    for item in player.inventory:
        if item.id == item_id:
            item.quantity += quantity
            item.technique_id = technique.id
            item.technique_level = manual_level
            return
    player.inventory.append(Item(
        id=item_id,
        name=f"《{technique.name}》Lv.{manual_level} 传承玉简",
        quantity=quantity,
        technique_id=technique.id,
        technique_level=manual_level,
        description=technique_manual_description(technique.name, manual_level),
        tags=["technique_manual"],
    ))


def acquire_technique(player: Player, technique: Technique) -> bool:
    """Learn the first copy and put every later copy in the ordinary inventory."""
    if any(known.id == technique.id for known in player.known_techniques):
        add_technique_copy(player, technique)
        return False
    player.known_techniques.append(copy.deepcopy(technique))
    return True


def upgrade_known_technique(player: Player, technique_id: str) -> int:
    known = next((entry for entry in player.known_techniques if entry.id == technique_id), None)
    if known is None:
        raise ValueError("你尚未掌握这部功法")
    if known.level >= TECHNIQUE_MAX_LEVEL:
        raise ValueError(f"《{known.name}》已经达到 Lv.{TECHNIQUE_MAX_LEVEL}")
    if not remove_item(player, technique_manual_item_id(technique_id, known.level)):
        raise ValueError(f"升级《{known.name}》需要一份同名 Lv.{known.level} 传承玉简")
    new_level = known.level + 1
    equipped = [
        player.technique, player.support_technique, player.body_technique,
        player.divine_sense_technique, player.transformation_technique,
        *player.combat_techniques,
    ]
    for entry in [*player.known_techniques, *equipped]:
        if entry and entry.id == technique_id:
            entry.level = new_level
    return new_level


def merge_technique_copies(player: Player, technique_id: str, level: int) -> int:
    """Combine two same-name, same-level manuals into one manual of the next level."""
    manual_level = int(level)
    if not 1 <= manual_level < TECHNIQUE_MAX_LEVEL:
        raise ValueError(f"只有 Lv.1–{TECHNIQUE_MAX_LEVEL - 1} 玉简可以继续合成")
    known = next((entry for entry in player.known_techniques if entry.id == technique_id), None)
    template = known or TECHNIQUE_CATALOG.get(technique_id)
    if template is None:
        raise ValueError("未找到这部功法")
    item_id = technique_manual_item_id(technique_id, manual_level)
    if technique_copy_count(player, technique_id, manual_level) < 2:
        raise ValueError(f"合成需要两份《{template.name}》Lv.{manual_level} 传承玉简")
    remove_item(player, item_id)
    remove_item(player, item_id)
    add_technique_copy(player, template, level=manual_level + 1)
    return manual_level + 1


def ensure_technique_set(player: Player) -> None:
    """只迁移旧存档已有功法；新角色保持三个槽位为空。"""
    if player.technique and player.technique.opportunity_bonus <= 0:
        main = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        main.path, main.element = player.technique.path, player.technique.element
        main.grade, main.level, main.name = player.technique.grade, player.technique.level, player.technique.name
        player.technique = main
    for index, item in enumerate(player.inventory):
        if item.id in ITEM_CATALOG:
            quantity = item.quantity
            player.inventory[index] = Item(**(ITEM_CATALOG[item.id].to_dict() | {"quantity": quantity}))
    _normalize_technique_manuals(player)
    equipped = [
        player.technique, player.support_technique, player.body_technique,
        player.divine_sense_technique, player.transformation_technique,
        *player.combat_techniques,
    ]
    all_techniques = [*equipped, *player.known_techniques]
    levels_by_id: dict[str, int] = {}
    for technique in all_techniques:
        if technique:
            technique.level = max(1, min(TECHNIQUE_MAX_LEVEL, int(technique.level)))
            levels_by_id[technique.id] = max(levels_by_id.get(technique.id, 1), technique.level)
    for technique in all_techniques:
        if technique and not technique.combat_requirements and technique.id in TECHNIQUE_CATALOG:
            technique.combat_requirements = copy.deepcopy(TECHNIQUE_CATALOG[technique.id].combat_requirements)
        if technique and technique.id in TECHNIQUE_CATALOG:
            technique.required_body_training = int(TECHNIQUE_CATALOG[technique.id].required_body_training)
            technique.possession_limit_bonus = int(TECHNIQUE_CATALOG[technique.id].possession_limit_bonus)
            technique.ignore_possession_limit = bool(TECHNIQUE_CATALOG[technique.id].ignore_possession_limit)
        if technique:
            technique.level = levels_by_id[technique.id]
    for technique in equipped:
        if technique and all(known.id != technique.id for known in player.known_techniques):
            player.known_techniques.append(copy.deepcopy(technique))
    ensure_transformation_state(player)


def learn_technique(player: Player, technique: Technique) -> bool:
    if any(known.id == technique.id for known in player.known_techniques):
        return False
    player.known_techniques.append(copy.deepcopy(technique))
    return True


def assign_technique(player: Player, technique: Technique, slot: str) -> None:
    known = next((entry for entry in player.known_techniques if entry.id == technique.id), None)
    if known is not None:
        technique.level = max(technique.level, known.level)
    validate_technique(technique)
    if player.path == "monster" and (slot == "transformation" or technique.category == "transformation"):
        raise ValueError("妖修以血脉本体进化，不能修炼或配置变化术")
    if technique.requires_immortal_power and not player.immortal_power_converted:
        raise ValueError("尚未完成仙灵力转化，无法配置仙家功法")
    if not can_player_practice_technique(player, technique.element):
        raise ValueError("灵根属性与功法不合")
    if player.body_training < int(technique.required_body_training):
        raise ValueError(f"肉身不足：配置《{technique.name}》需要炼体{technique.required_body_training}层")
    if slot == "body":
        if technique.category != "body":
            raise ValueError("只有炼体功法可以放入炼体槽位")
        player.body_technique = technique
    elif slot == "divine_sense":
        if technique.category != "divine_sense":
            raise ValueError("只有神识功法可以放入神识槽位")
        player.divine_sense_technique = technique
    elif slot == "transformation":
        if technique.category != "transformation":
            raise ValueError("只有变身功法可以放入变身槽位")
        equip_transformation_technique(player, technique)
    elif technique.category in {"body", "divine_sense", "transformation"}:
        raise ValueError("专属功法只能配置在对应专属槽位")
    elif slot == "main":
        player.technique = technique
    elif slot == "support":
        player.support_technique = technique
    elif slot == "combat":
        if not combat_requirement_met(technique.combat_requirements, qi_levels(player)):
            raise ValueError(f"气等级不足：需要{combat_requirement_display(technique.combat_requirements)}")
        if all(entry.id != technique.id for entry in player.combat_techniques):
            player.combat_techniques.append(technique)
    else:
        raise ValueError("未知功法槽位")
    learn_technique(player, technique)


def realm(player: Player) -> RealmDef:
    return REALMS[player.realm_index]


def stage_name(player: Player) -> str:
    current = realm(player)
    if current.id == "mortal":
        return current.name
    if player.world == "asura" and player.realm_index >= 9:
        return WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
            str(player.realm_index), current.name,
        )
    if current.layers == 1:
        return current.name
    if player.path == "demonic":
        name = WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
            str(player.realm_index), current.name,
        )
        if player.realm_index == 1:
            return f"{name}{player.layer}层"
        stage = "初期" if player.layer <= 3 else "中期" if player.layer <= 6 else "后期"
        return f"{name}{stage}·{player.layer}层"
    if current.id == "qi":
        return f"{current.name}{player.layer}层"
    stage = "初期" if player.layer <= 3 else "中期" if player.layer <= 6 else "后期"
    return f"{current.name}{stage}·{player.layer}层"


def opportunity_required(player: Player) -> int:
    current = realm(player)
    return round(current.opportunity_base * (1 + 0.12 * (player.layer - 1)))


def raw_external_hp_bonus(player: Player) -> float:
    from .crafting_system import crafted_artifact_bonuses
    reference = intrinsic_hp_reference(player)
    support_bonus = 0.0
    if player.support_technique:
        support_bonus = (
            player.support_technique.hp_bonus * technique_scale(player.support_technique)
            * (1 + max(0.0, float(player.sage_effects.get("technique_learning_multiplier", 0.0))))
        )
    return (
        reference * support_bonus
        + sum(i.hp_bonus * i.quantity for i in player.inventory)
        + player.faction_hp_bonus
        + player.natal_artifact_hp_bonus
        + ghost_external_hp_bonus(player)
        + crafted_artifact_bonuses(player)["max_hp"]
    )


def max_hp(player: Player) -> int:
    return round(effective_intrinsic_hp(player) + raw_external_hp_bonus(player) * hp_carry_ratio(player))


def raw_external_mp_bonus(player: Player) -> float:
    from .crafting_system import crafted_artifact_bonuses
    reference = intrinsic_mp_reference(player)
    support_bonus = 0.0
    if player.support_technique:
        support_bonus = (
            player.support_technique.mp_bonus * technique_scale(player.support_technique)
            * (1 + max(0.0, float(player.sage_effects.get("technique_learning_multiplier", 0.0))))
        )
    return (
        reference * support_bonus
        + sum(i.mp_bonus * i.quantity for i in player.inventory)
        + player.faction_mp_bonus
        + player.natal_artifact_mp_bonus
        + ghost_external_mp_bonus(player)
        + crafted_artifact_bonuses(player)["max_mp"]
    )


def max_mp(player: Player) -> int:
    return round(effective_intrinsic_mp(player) + raw_external_mp_bonus(player) * mp_carry_ratio(player))


def combat_power(player: Player) -> float:
    from .crafting_system import crafted_artifact_bonuses
    current = realm(player)
    hp_ratio = max(0.0, min(1.0, player.hp / max_hp(player)))
    mp_ratio = max(0.0, min(1.0, player.mp / max_mp(player)))
    status = 0.35 + 0.40 * hp_ratio + 0.25 * mp_ratio
    layer_factor = 1 + 0.08 * (player.layer - 1)
    progress = min(1.5, player.opportunity / max(1, opportunity_required(player)))
    item_power = sum(item.combat_bonus * item.quantity for item in player.inventory)
    current_qi_levels = qi_levels(player)
    technique_power = sum(
        entry.combat_bonus * technique_scale(entry)
        * (1 + max(0.0, float(player.sage_effects.get("technique_learning_multiplier", 0.0))))
        for entry in player.combat_techniques
        if combat_requirement_met(entry.combat_requirements, current_qi_levels)
        and (not entry.requires_immortal_power or player.immortal_power_converted)
    )
    comprehensive = current.base_power * layer_factor * status + current.base_power * progress * 0.15 + item_power + player.body_training * 8
    total = (
        comprehensive + technique_power + player.faction_combat_bonus
        + player.natal_artifact_combat_bonus + crafted_artifact_bonuses(player)["combat_power"]
    )
    if any(item.plant_id == "golden_thunder_bamboo" and int(item.plant_years or 0) >= 10000 for item in player.inventory):
        total *= 1.01
    total *= 1.0 + max(0.0, float(player.sage_effects.get("combat_multiplier", 0.0)))
    return round(total, 1)


def expected_combat_power(realm_index: int, layer: int) -> float:
    """返回玩家、NPC 与动态事件共用的境界战力基准。"""
    definition = REALMS[realm_index]
    values = WORLD_SYSTEMS["combat_expectations"][definition.id]
    if definition.id == "mortal":
        return float(values["value"])
    if definition.id == "qi":
        return float(values["base"] + values["layer_step"] * (max(1, layer) - 1))
    if definition.layers == 1:
        return float(values["value"])
    stage = "early" if layer <= 3 else "middle" if layer <= 6 else "late"
    return float(values[stage])


def recommended_combat_power(realm_index: int, layer: int) -> float:
    """返回角色面板使用的同一套境界战力基准。"""
    return expected_combat_power(realm_index, layer)


def combat_power_assessment(player: Player) -> str:
    expected = recommended_combat_power(player.realm_index, player.layer)
    return combat_power_assessment_value(combat_power(player), expected)


def combat_power_assessment_value(actual: float, expected: float) -> str:
    ratio = float(actual) / max(1.0, float(expected))
    if ratio < 0.5:
        return "你的战力养成严重不足，尚未形成当前境界应有的护道体系"
    if ratio < 0.8:
        return "你的战力明显低于当前境界推荐线"
    if ratio < 1.0:
        return "你的战力已经接近当前境界推荐线"
    if ratio == 1.0:
        return "你的战斗力恰好达到当前境界的推荐水准"
    if ratio <= 1.25:
        return "你的完整养成略高于当前境界推荐线"
    if ratio <= 1.7:
        return "你的战力体系已经明显超过当前境界推荐线"
    return "你的额外资产与特殊体系令战力远超当前境界推荐线"


def effective_karma(player: Player) -> float:
    if player.path == "demonic":
        return 0.0
    if player.technique:
        return (
            max(0.0, player.karma) * KARMA_FACTORS[player.technique.path]
            * effective_technique_karma_multiplier(player.technique)
        )
    return max(0.0, player.karma)


def negative_event_multiplier(player: Player) -> float:
    return 1 + (effective_karma(player) / 100) ** 2 * 2


def qi_environment_multiplier(concentration: float) -> float:
    """把非负气浓度映射到 [0.25, 1.75) 的边际递减修炼倍率。"""
    concentration = float(concentration)
    if concentration < 0:
        raise ValueError("气浓度不得为负")
    return 0.25 + 1.5 * concentration / (concentration + 1)


def world_qi_concentrations(world: str) -> dict[str, float]:
    profile = WORLD_SYSTEMS.get("world_profiles", {}).get(world, {})
    configured = profile.get("qi_concentrations", {})
    return {source: max(0.0, float(configured.get(source, 0.0))) for source in QI_SOURCE_NAMES}


def technique_environment_multiplier(technique: Technique, world: str) -> float:
    """按功法内部源权重求环境倍率；多源收益不会直接相加。"""
    if (
        not technique.sources
        or set(technique.sources) - set(QI_SOURCE_NAMES)
        or any(weight <= 0 for weight in technique.sources.values())
        or not math.isclose(sum(technique.sources.values()), 1.0, abs_tol=1e-9)
    ):
        raise ValueError("功法的先天源配置不合法")
    concentrations = world_qi_concentrations(world)
    return sum(
        weight * qi_environment_multiplier(concentrations[source])
        for source, weight in technique.sources.items()
    )


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


def divine_sense_level_threshold(level: int) -> float:
    level = max(0, int(level))
    base = float(WORLD_SYSTEMS.get("demonic_cultivation", {}).get("divine_sense_experience_base", 20))
    return base * level * level


def divine_sense_level(player: Player) -> int:
    return max(0, int(player.divine_sense_rank))


def divine_sense_breakthrough_cost(player: Player) -> float:
    level = divine_sense_level(player)
    return divine_sense_level_threshold(level + 1) - divine_sense_level_threshold(level)


def puppet_capacity(player: Player) -> int:
    level = divine_sense_level(player)
    # 魔修开局必须至少能控制一具傀儡；此后每完整跨过三个神识等级才增加一栏。
    return max(1, (level + 2) // 3)


def grant_qi_experience(
    player: Player, opportunity_gain: float, location_efficiencies: dict[str, float],
) -> dict[str, float]:
    """主修与辅修各自按源权重吸收气经验，战斗/炼体槽不参与。"""
    gains = {source: 0.0 for source in QI_SOURCE_NAMES}
    if opportunity_gain <= 0:
        return gains
    for technique in (player.technique, player.support_technique):
        if technique is None:
            continue
        for source, weight in technique.sources.items():
            gained = float(opportunity_gain) * weight * max(0.0, float(location_efficiencies.get(source, 0.0)))
            player.qi_experience[source] = player.qi_experience.get(source, 0.0) + gained
            gains[source] += gained
    return gains


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


def opportunity_multiplier(player: Player) -> float:
    """原有效率保持独立，最后仅为当前主修乘上所在界面的气环境倍率。"""
    root_efficiency = root_definition(player.spirit_root)["efficiency"]
    if player.technique is None:
        return 0.0
    main_bonus = (
        player.technique.opportunity_bonus * technique_scale(player.technique)
        * (1 + max(0.0, float(player.sage_effects.get("technique_learning_multiplier", 0.0))))
    )
    from .crafting_system import crafted_artifact_bonuses
    item_bonus = (
        sum(item.opportunity_bonus * item.quantity for item in player.inventory)
        + player.natal_artifact_opportunity_bonus
        + crafted_artifact_bonuses(player)["opportunity_efficiency"]
    )
    inner_multiplier = (1 + main_bonus) * (1 + item_bonus)
    return (
        root_efficiency * inner_multiplier
        * technique_environment_multiplier(player.technique, player.world)
        * ghost_opportunity_multiplier(player)
        * (1 + max(0.0, float(player.sage_effects.get("opportunity_multiplier", 0.0))))
        * (0.8 if player.concubine_status else 1.0)
    )


def root_definition(root_id: str) -> dict[str, Any]:
    return ROOT_DEFINITIONS[LEGACY_ROOTS.get(root_id, root_id)]


def root_elements(root_id: str) -> list[str]:
    return list(root_definition(root_id)["elements"])


def can_practice_technique(root_id: str, technique_element: str) -> bool:
    """无属性功法不限灵根；五行功法必须命中灵根的五行属性。"""
    if technique_element in {"neutral", "sex"}:
        return True
    elements = set(root_elements(root_id))
    if technique_element == "five_elements":
        return {"metal", "wood", "water", "fire", "earth"} <= elements
    return technique_element in elements


def player_affinities(player: Player) -> list[str]:
    return list(dict.fromkeys([*root_elements(player.spirit_root), *player.additional_roots]))


def can_player_practice_technique(player: Player, technique_element: str) -> bool:
    if technique_element in {"neutral", "sex"}:
        return True
    affinities = set(player_affinities(player))
    if technique_element == "five_elements":
        return {"metal", "wood", "water", "fire", "earth"} <= affinities
    return technique_element in affinities


def roll_lifespan(player: Player, rng: random.Random) -> int | None:
    span = realm(player).lifespan
    if span is None:
        if player.path == "monster":
            player.monster_lifespan_scaled = True
        return None
    multiplier = int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3)) if player.path == "monster" else 1
    if player.path == "monster":
        player.monster_lifespan_scaled = True
    return rng.randint(*span) * multiplier


def add_item(player: Player, item_id: str, quantity: int = 1) -> None:
    for item in player.inventory:
        if item.id == item_id:
            item.quantity += quantity
            return
    source = ITEM_CATALOG[item_id]
    player.inventory.append(Item(**source.to_dict() | {"quantity": quantity}))


def remove_item(player: Player, item_id: str, quantity: int = 1) -> bool:
    for item in player.inventory:
        if item.id == item_id and item.quantity >= quantity:
            item.quantity -= quantity
            if item.quantity == 0:
                player.inventory.remove(item)
            return True
    return False


def has_item(player: Player, item_id: str, quantity: int = 1) -> bool:
    return any(item.id == item_id and item.quantity >= quantity for item in player.inventory)


def public_player(player: Player) -> dict[str, Any]:
    ensure_technique_set(player)
    data = player.to_dict()
    data["world_age"] = player.age
    data["age"] = current_body_age(player)
    data.pop("ghost_core_state", None)
    # Adaptation counters are deliberately hidden: the player sees acquired
    # life experiences, never another bar to grind.
    data.pop("monster_adaptation_progress", None)
    data.pop("monster_lifespan_scaled", None)
    # 心魔是规则层状态，普通界面不可见；引擎仅在 Debug 投影中显式加入。
    data.pop("heart_demon", None)
    concentrations = world_qi_concentrations(player.world)
    current_qi_levels = qi_levels(player)
    conversion_config = WORLD_SYSTEMS.get("immortal_power_conversion", {})
    conversion_total = max(1, int(conversion_config.get("stages", 5)))
    conversion_stage = conversion_total if player.immortal_power_converted else min(
        conversion_total, max(0, player.immortal_conversion_stage),
    )
    conversion_unit_years = max(1, int(conversion_config.get("time_unit_years", 500)))
    conversion_min_gap = max(1, int(conversion_config.get("min_gap_units", 10)))
    elapsed_conversion_units = (
        max(0, (player.age - player.immortal_conversion_last_age) // conversion_unit_years)
        if player.immortal_conversion_last_age is not None else 0
    )
    current_conversion_chance = (
        min(0.98, float(conversion_config.get("base_chance", 0.10))
            + float(conversion_config.get("chance_per_unit", 0.02)) * (elapsed_conversion_units - conversion_min_gap))
        if elapsed_conversion_units >= conversion_min_gap and not player.immortal_power_converted else 0.0
    )
    uses_immortal_resource = player.world == "celestial" or player.immortal_power_converted

    def public_technique(technique: Technique | None, environment_active: bool) -> dict[str, Any] | None:
        if technique is None:
            return None
        result = dict(technique.__dict__)
        level_multiplier = technique.level_multiplier
        effect_multiplier = technique_scale(technique)
        for field_name in (
            "opportunity_bonus", "hp_bonus", "mp_bonus", "combat_bonus", "divine_sense_bonus",
        ):
            base_value = float(getattr(technique, field_name))
            result[f"base_{field_name}"] = base_value
            result[field_name] = base_value * effect_multiplier
        result["base_body_breakthrough_bonus"] = float(technique.body_breakthrough_bonus)
        result["body_breakthrough_bonus"] = float(technique.body_breakthrough_bonus) * level_multiplier
        capacity, space = transformation_technique_limits(technique)
        result["base_transformation_capacity"] = technique.transformation_capacity
        result["base_transformation_space"] = technique.transformation_space
        result["transformation_capacity"] = capacity
        result["transformation_space"] = space
        result.update(
            level_multiplier=level_multiplier,
            effect_multiplier=effect_multiplier,
            max_level=TECHNIQUE_MAX_LEVEL,
            upgrade_copies=technique_copy_count(player, technique.id, technique.level),
            manuals_by_level=[
                {"level": level, "quantity": quantity}
                for level in range(1, TECHNIQUE_MAX_LEVEL + 1)
                if (quantity := technique_copy_count(player, technique.id, level)) > 0
            ],
            can_upgrade=(
                technique.level < TECHNIQUE_MAX_LEVEL
                and technique_copy_count(player, technique.id, technique.level) > 0
            ),
            effective_karma_multiplier=effective_technique_karma_multiplier(technique),
            source_names=[QI_SOURCE_NAMES[source] for source in technique.sources],
            source_display="、".join(
                QI_SOURCE_NAMES[source] + (f" {weight:.0%}" if len(technique.sources) > 1 else "")
                for source, weight in technique.sources.items()
            ),
            environment_active=environment_active,
            environment_multiplier=(
                round(technique_environment_multiplier(technique, player.world), 4)
                if environment_active else None
            ),
            combat_requirement_display=combat_requirement_display(technique.combat_requirements),
            combat_requirement_met=combat_requirement_met(technique.combat_requirements, current_qi_levels),
            immortal_power_met=(not technique.requires_immortal_power or player.immortal_power_converted),
            body_requirement_met=player.body_training >= int(technique.required_body_training),
        )
        return result

    data.update(
        gender_name="女" if player.gender == "female" else "男",
        realm_id=realm(player).id,
        realm_name=stage_name(player),
        opportunity_required=opportunity_required(player),
        max_hp=max_hp(player),
        max_mp=max_mp(player),
        combat_power=combat_power(player),
        expected_combat_power=recommended_combat_power(player.realm_index, player.layer),
        npc_expected_combat_power=expected_combat_power(player.realm_index, player.layer),
        combat_power_assessment=combat_power_assessment(player),
        effective_karma=round(effective_karma(player), 1),
        karma_factor=(
            0.0 if player.path == "demonic" else
            (KARMA_FACTORS[player.technique.path] * effective_technique_karma_multiplier(player.technique))
            if player.technique else 1.0
        ),
        path_name=PATH_NAMES[player.path],
        spirit_root_name=root_definition(player.spirit_root)["name"],
        spirit_root_tier=root_definition(player.spirit_root)["tier"],
        spirit_root_efficiency=root_definition(player.spirit_root)["efficiency"],
        cultivation_efficiency=round(opportunity_multiplier(player), 4),
        qi_mastery=[
            {
                "source": source,
                "name": QI_NAMES[source],
                "level": current_qi_levels[source],
                "experience": round(player.qi_experience.get(source, 0.0), 2),
                "level_experience": round(
                    player.qi_experience.get(source, 0.0) - qi_level_threshold(current_qi_levels[source]), 2,
                ),
                "next_level_experience": round(
                    qi_level_threshold(current_qi_levels[source] + 1) - qi_level_threshold(current_qi_levels[source]), 2,
                ),
            }
            for source in QI_SOURCE_NAMES
        ],
        qi_environment={
            "concentrations": concentrations,
            "display": [
                {"source": source, "name": name.removesuffix("源") + "气", "concentration": concentrations[source]}
                for source, name in QI_SOURCE_NAMES.items()
            ],
            "main_multiplier": (
                round(technique_environment_multiplier(player.technique, player.world), 4)
                if player.technique else None
            ),
            "body_multiplier": (
                round(technique_environment_multiplier(player.body_technique, player.world), 4)
                if player.body_technique else None
            ),
            "divine_sense_multiplier": (
                round(technique_environment_multiplier(player.divine_sense_technique, player.world), 4)
                if player.divine_sense_technique else None
            ),
        },
        spirit_root_elements=[AFFINITY_NAMES[element] for element in player_affinities(player)],
        additional_root_names=[AFFINITY_NAMES[element] for element in player.additional_roots],
        world_name=WORLD_SYSTEMS["world_names"].get(player.world, player.world),
        resource_name="仙灵力" if uses_immortal_resource else "MP",
        resource_kind="immortal" if uses_immortal_resource else "mana",
        immortal_power={
            "visible": player.world == "celestial",
            "converted": player.immortal_power_converted,
            "conversion_stage": conversion_stage,
            "conversion_total": conversion_total,
            "usable_ratio": round(conversion_stage / conversion_total, 4),
            "usable_max": round(max_mp(player) * conversion_stage / conversion_total, 2),
            "elapsed_units": elapsed_conversion_units,
            "minimum_gap_units": conversion_min_gap,
            "wait_units_remaining": max(0, conversion_min_gap - elapsed_conversion_units),
            "current_trigger_chance": round(current_conversion_chance, 4),
        },
        race_name=RACE_DEFINITIONS.get(player.race, {"name": player.race})["name"],
        lineage_race_name=RACE_DEFINITIONS.get(player.lineage_race or player.race, {"name":player.lineage_race or player.race})["name"],
        allegiance_race_name=RACE_DEFINITIONS.get(player.allegiance_race or player.lineage_race or player.race, {"name":player.allegiance_race or player.lineage_race or player.race})["name"],
        time_unit_years=int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]),
        spirit_root_display=(
            root_definition(player.spirit_root)["name"]
            + (" · 后天补全：" + "、".join(AFFINITY_NAMES[element] for element in player.additional_roots)
               if player.additional_roots else "")
        ),
        technique_element_name=TECHNIQUE_ELEMENT_NAMES[player.technique.element] if player.technique else None,
        technique_slots={
            "main": public_technique(player.technique, True),
            "support": public_technique(player.support_technique, True),
            "body": public_technique(player.body_technique, True),
            "divine_sense": public_technique(player.divine_sense_technique, True),
            "transformation": public_technique(player.transformation_technique, False),
            "combat": [public_technique(technique, False) for technique in player.combat_techniques],
        },
        known_techniques=[
            public_technique(technique, False) | {
                "element_name": TECHNIQUE_ELEMENT_NAMES[technique.element],
                "compatible": (
                    can_player_practice_technique(player, technique.element)
                    and (not technique.requires_immortal_power or player.immortal_power_converted)
                    and player.body_training >= int(technique.required_body_training)
                ),
                "category_name": (
                    "炼体" if technique.category == "body" else
                    "神识" if technique.category == "divine_sense" else
                    "变身" if technique.category == "transformation" else "修仙"
                ),
            }
            for technique in player.known_techniques
        ],
        divine_sense={
            "level": divine_sense_level(player),
            "experience": round(player.divine_sense_experience, 2),
            "level_experience": round(player.divine_sense_experience, 2),
            "next_level_experience": round(divine_sense_breakthrough_cost(player), 2),
            "breakthrough_ready": player.divine_sense_experience >= divine_sense_breakthrough_cost(player),
            "capacity": puppet_capacity(player),
            "used": len(player.puppets),
            "technique": public_technique(player.divine_sense_technique, True),
        },
    )
    return data
