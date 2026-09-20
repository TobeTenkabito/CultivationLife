from __future__ import annotations

import math
from typing import Any

from .content_registry import TRANSFORMATION_CATALOG
from .models import Player, Technique, TransformationForm


STAT_NAMES = {
    "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
}
REALM_NAMES = ("凡人", "练气", "筑基", "结丹", "元婴", "化神", "炼虚", "合体", "大乘", "真仙", "金仙", "太乙", "大罗")
# 真灵素材能保留多少本体修为。属性上限仍由种族定义，素材纯度再决定实际解锁比例。
REALM_POTENCY = (0.03, 0.06, 0.11, 0.18, 0.28, 0.40, 0.54, 0.72, 1.0, 1.0, 1.0, 1.0, 1.0)
DIRECT_ABSORPTION_EFFICIENCY = 0.45
PURIFIED_ABSORPTION_EFFICIENCY = 0.92
BATCH_PAIR_BONUS = 0.30


def transformation_technique_limits(technique: Technique) -> tuple[int, int]:
    """Scale structural transformation slots to the nearest whole slot by level."""
    multiplier = technique.level_multiplier
    capacity = max(
        int(technique.transformation_capacity),
        math.floor(float(technique.transformation_capacity) * multiplier + 0.5),
    )
    space = max(
        int(technique.transformation_space),
        math.floor(float(technique.transformation_space) * multiplier + 0.5),
    )
    return capacity, min(capacity, space)


def normalized_transformation_weights(count: int) -> list[float]:
    """Normalize 1, 1/2, 1/4... so any active set contributes exactly one form."""
    if count <= 0:
        return []
    raw = [0.5 ** index for index in range(count)]
    total = sum(raw)
    return [value / total for value in raw]


def ensure_transformation_state(player: Player) -> None:
    """Normalize new saves and grandfather forms already unlocked by older saves."""
    legacy_forms = list(player.known_transformations)
    for loadout in player.transformation_loadouts.values():
        legacy_forms.extend(loadout.get("stored", []))
        legacy_forms.extend(loadout.get("active", []))
    for form_id in dict.fromkeys(legacy_forms):
        if form_id not in TRANSFORMATION_CATALOG:
            continue
        player.transformation_mastery.setdefault(form_id, {
            "purity": 0.25, "stats": {stat: 0.25 for stat in STAT_NAMES},
            "material_id": "legacy", "source_type": "旧存档传承",
        })
    for progress in player.transformation_mastery.values():
        legacy = max(0.0, min(1.0, float(progress.get("purity", 0.0))))
        saved_stats = progress.get("stats") if isinstance(progress.get("stats"), dict) else {}
        progress["stats"] = {
            stat: max(0.0, min(1.0, float(saved_stats.get(stat, legacy))))
            for stat in STAT_NAMES
        }
        progress["purity"] = sum(progress["stats"].values()) / len(STAT_NAMES)
    player.known_transformations = [
        form_id for form_id in dict.fromkeys([*player.known_transformations, *player.transformation_mastery])
        if form_id in TRANSFORMATION_CATALOG and float(player.transformation_mastery.get(form_id, {}).get("purity", 0)) > 0
    ]
    technique = player.transformation_technique
    if not technique:
        return
    loadout = player.transformation_loadouts.setdefault(technique.id, {"stored": [], "active": []})
    capacity, space = transformation_technique_limits(technique)
    known = set(player.known_transformations)
    stored = [form_id for form_id in loadout.get("stored", []) if form_id in known and form_id in TRANSFORMATION_CATALOG]
    active = [form_id for form_id in loadout.get("active", []) if form_id in stored]
    loadout["stored"] = stored[:capacity]
    loadout["active"] = compatible_active_forms(active, space)


def compatible_active_forms(form_ids: list[str], space: int) -> list[str]:
    result: list[str] = []
    for form_id in form_ids:
        form = TRANSFORMATION_CATALOG.get(form_id)
        if not form or len(result) >= space:
            continue
        if any(forms_are_incompatible(form_id, other) for other in result):
            continue
        result.append(form_id)
    return result


def forms_are_incompatible(left: str, right: str) -> bool:
    left_form = TRANSFORMATION_CATALOG.get(left)
    right_form = TRANSFORMATION_CATALOG.get(right)
    return bool(
        left_form and right_form
        and (right in left_form.incompatible_with or left in right_form.incompatible_with)
    )


def form_purity(player: Player, form_id: str) -> float:
    progress = form_stat_progress(player, form_id)
    return sum(progress.values()) / len(progress) if progress else 0.0


def form_stat_progress(player: Player, form_id: str) -> dict[str, float]:
    mastery = player.transformation_mastery.get(form_id, {})
    legacy = max(0.0, min(1.0, float(mastery.get("purity", 0.0))))
    saved = mastery.get("stats") if isinstance(mastery.get("stats"), dict) else {}
    return {
        stat: max(0.0, min(1.0, float(saved.get(stat, legacy))))
        for stat in STAT_NAMES
    }


def purified_material_purity(purity: float) -> float:
    purity = max(0.0, min(1.0, float(purity)))
    return 1 - (1 - purity) ** 2


def absorption_gain(purity: float, purify: bool = False) -> float:
    effective = purified_material_purity(purity) if purify else max(0.0, min(1.0, float(purity)))
    efficiency = PURIFIED_ABSORPTION_EFFICIENCY if purify else DIRECT_ABSORPTION_EFFICIENCY
    return min(1.0, effective * efficiency)


def form_potency(form: TransformationForm, purity: float) -> float:
    realm_factor = REALM_POTENCY[max(0, min(len(REALM_POTENCY) - 1, form.realm_index))]
    layer_factor = 0.92 + 0.08 * max(1, form.layer) / 3
    return min(1.0, max(0.0, purity) * realm_factor * layer_factor)


def effective_form_multipliers(form: TransformationForm, progress: float | dict[str, float]) -> dict[str, float]:
    values = {stat: float(progress.get(stat, 0.0)) for stat in STAT_NAMES} if isinstance(progress, dict) else {
        stat: float(progress) for stat in STAT_NAMES
    }
    return {
        stat: 1.0 + (cap - 1.0) * max(0.0, min(1.0, values.get(stat, 0.0)))
        for stat, cap in form.stat_multipliers.items()
    }


def unlocked_traits(form: TransformationForm, purity: float) -> list[tuple[str, str]]:
    requirements = form.trait_purity_requirements or tuple(0.5 for _ in form.traits)
    return [
        (trait, description)
        for trait, description, requirement in zip(form.traits, form.trait_descriptions, requirements)
        if purity >= requirement
    ]


def active_transformation_profile(player: Player) -> dict[str, Any]:
    if player.path == "monster":
        return {"forms": [], "weights": [], "stat_multipliers": {}, "traits": []}
    ensure_transformation_state(player)
    technique = player.transformation_technique
    if not technique:
        return {"forms": [], "weights": [], "stat_multipliers": {}, "traits": []}
    loadout = player.transformation_loadouts.get(technique.id, {"active": []})
    forms = [TRANSFORMATION_CATALOG[form_id] for form_id in loadout.get("active", []) if form_id in TRANSFORMATION_CATALOG]
    weights = normalized_transformation_weights(len(forms))
    effective = [effective_form_multipliers(form, form_stat_progress(player, form.id)) for form in forms]
    multipliers = {
        stat: sum(stats[stat] * weight for stats, weight in zip(effective, weights))
        for stat in STAT_NAMES
    } if forms else {}
    traits = list(dict.fromkeys(
        trait for form in forms for trait, _ in unlocked_traits(form, form_purity(player, form.id))
    ))
    return {"forms": forms, "weights": weights, "stat_multipliers": multipliers, "traits": traits}


def public_transformation_system(player: Player) -> dict[str, Any]:
    if player.path == "monster":
        return {
            "available": False, "disabled_reason": "妖修依靠自身血脉进化，不能使用变化术。",
            "materials": [], "technique": None, "capacity": 0, "space": 0,
            "stored": [], "known": [], "active": [], "combined_stats": [], "traits": [],
        }
    ensure_transformation_state(player)
    technique = player.transformation_technique
    known = [
        public_form(TRANSFORMATION_CATALOG[form_id], player)
        for form_id in player.known_transformations if form_id in TRANSFORMATION_CATALOG
    ]
    known_manuals = [
        technique_entry for technique_entry in player.known_techniques
        if technique_entry.category == "transformation"
    ]
    materials = [
        {
            "id": item.id, "name": item.name, "quantity": item.quantity,
            "form_id": item.transformation_form_id,
            "form_name": TRANSFORMATION_CATALOG[item.transformation_form_id].name,
            "source_type": item.transformation_source,
            "purity": round(item.transformation_purity, 8),
            "purified_purity": round(purified_material_purity(item.transformation_purity), 8),
            "direct_gain": round(absorption_gain(item.transformation_purity), 8),
            "purified_gain": round(absorption_gain(item.transformation_purity, True), 8),
            "batch_pair_gain": round(
                absorption_gain(item.transformation_purity, True) * (1 + BATCH_PAIR_BONUS), 8,
            ),
            "batch_pair_bonus_active": item.quantity > 2,
            "stat_progress": {stat: round(value, 8) for stat, value in form_stat_progress(player, item.transformation_form_id).items()},
            "can_improve": any(value < 1 - 1e-9 for value in form_stat_progress(player, item.transformation_form_id).values()),
            "can_purify": item.quantity >= 2 and any(value < 1 - 1e-9 for value in form_stat_progress(player, item.transformation_form_id).values()),
            "can_batch_absorb": any(value < 1 - 1e-9 for value in form_stat_progress(player, item.transformation_form_id).values()),
            "can_batch_purify": item.quantity >= 2 and any(value < 1 - 1e-9 for value in form_stat_progress(player, item.transformation_form_id).values()),
        }
        for item in player.inventory
        if item.quantity > 0 and item.transformation_form_id in TRANSFORMATION_CATALOG and item.transformation_purity > 0
    ]
    base = {
        "available": True, "disabled_reason": "", "materials": materials,
        "acquisition_hint": (
            f"你已掌握《{known_manuals[-1].name}》，请在功法栏将变身功法配置到“变”槽。"
            if known_manuals else
            "变身功法自元婴起随机流通于人界、灵界、魔界和真魔界的一般坊市；境界越高，容量与战斗空间通常越大。"
        ),
    }
    if not technique:
        return base | {
            "technique": None, "capacity": 0, "space": 0, "stored": [],
            "known": known, "active": [], "combined_stats": [], "traits": [],
        }
    loadout = player.transformation_loadouts[technique.id]
    profile = active_transformation_profile(player)
    weights_by_id = {form.id: weight for form, weight in zip(profile["forms"], profile["weights"])}
    stored = [
        public_form(TRANSFORMATION_CATALOG[form_id], player) | {
            "active": form_id in weights_by_id,
            "weight": round(weights_by_id.get(form_id, 0.0), 6),
            "active_order": next((index + 1 for index, form in enumerate(profile["forms"]) if form.id == form_id), None),
        }
        for form_id in loadout["stored"] if form_id in TRANSFORMATION_CATALOG
    ]
    capacity, space = transformation_technique_limits(technique)
    return base | {
        "technique": {"id": technique.id, "name": technique.name, "grade": technique.grade, "level": technique.level},
        "capacity": capacity, "space": space,
        "stored": stored,
        "known": [form for form in known if form["id"] not in loadout["stored"]],
        "active": [form.id for form in profile["forms"]],
        "combined_stats": [
            {"id": stat, "name": name, "multiplier": round(profile["stat_multipliers"].get(stat, 1.0), 4)}
            for stat, name in STAT_NAMES.items()
        ],
        "traits": [
            {"id": trait, "name": description}
            for form in profile["forms"]
            for trait, description in unlocked_traits(form, form_purity(player, form.id))
        ],
    }


def public_form(form: TransformationForm, player: Player | None = None) -> dict[str, Any]:
    purity = form_purity(player, form.id) if player else 0.0
    progress = form_stat_progress(player, form.id) if player else {stat: 0.0 for stat in STAT_NAMES}
    effective = effective_form_multipliers(form, progress)
    requirements = form.trait_purity_requirements or tuple(0.5 for _ in form.traits)
    return {
        "id": form.id, "name": form.name, "description": form.description,
        "realm_index": form.realm_index,
        "realm_name": (
            REALM_NAMES[max(0, min(12, form.realm_index))]
            if form.realm_index >= 9 else f"{REALM_NAMES[max(0, min(12, form.realm_index))]}{form.layer}层"
        ),
        "purity": round(purity, 6), "completion": round(purity, 6),
        "remaining": round(1 - purity, 6), "potency": round(form_potency(form, purity), 6),
        "source_type": player.transformation_mastery.get(form.id, {}).get("source_type") if player else None,
        "stats": [
            {"id": stat, "name": STAT_NAMES[stat], "multiplier": round(effective[stat], 4),
             "cap": round(cap, 4), "progress": round(progress[stat], 6), "remaining": round(1 - progress[stat], 6)}
            for stat, cap in form.stat_multipliers.items()
        ],
        "traits": [
            {"id": trait, "name": description, "required_purity": requirement, "unlocked": purity >= requirement}
            for trait, description, requirement in zip(form.traits, form.trait_descriptions, requirements)
        ],
        "incompatible_with": list(form.incompatible_with),
    }


def equip_transformation_technique(player: Player, technique: Technique) -> None:
    player.transformation_technique = technique
    ensure_transformation_state(player)
