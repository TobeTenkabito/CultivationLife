"""Damage composition belongs to the attack source. Root eligibility is independent."""
from math import isfinite

from .trait_lineages import LINEAGES

FIVE = ("metal", "wood", "earth", "water", "fire")
LABELS = dict(physical="物理", metal="金", wood="木", water="水", fire="火", earth="土",
              yin="阴", yang="阳", wind="风", thunder="雷")
THEMES = {
    "thunder": "雷霆电", "wind": "风岚飙", "water": "水海江河潮泉雨浪冰雪霜渊",
    "fire": "火焰炎灼烬熔焚", "wood": "木树藤竹花草林", "earth": "土岩山岳砂石",
    "metal": "金铁铜银钢刃剑锋", "yin": "阴冥幽鬼魂魄", "yang": "阳日曦曜",
}
PHYSICAL = {"physical": 1.0}


def read(owner, key, default=None):
    return owner.get(key, default) if isinstance(owner, dict) else getattr(owner, key, default)


def validate_profile(profile):
    if (not isinstance(profile, dict) or not profile or set(profile) - LABELS.keys()
            or any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in profile.values())
            or abs(sum(profile.values()) - 1) > 1e-6):
        raise ValueError("伤害属性及其占比无效")
    return dict(profile)


def profile_for(entry):
    profile = read(entry, "damage_profile")
    if profile is not None:
        return validate_profile(profile)
    name = read(entry, "name", "")
    if "五行" in name or "五色" in name:
        return dict.fromkeys(FIVE, .2)
    elements = [key for key, chars in THEMES.items() if any(ch in name for ch in chars)]
    if read(entry, "category") == "body":
        return {"physical": .7, elements[0]: .3} if elements else dict(PHYSICAL)
    if len(elements) > 1:
        return {elements[0]: .7, elements[1]: .3}
    return {elements[0]: 1.} if elements else dict(PHYSICAL)


def catalog_profile(entry):
    profile = profile_for(entry)
    if read(entry, "id") == "TECH_BLOOD_RIVER":
        return {"water": .7, "yin": .3}
    if profile == PHYSICAL and read(entry, "category") != "body":
        theme = read(entry, "element")
        if theme in LABELS:
            return {theme: 1.}
        if theme == "five_elements":
            return dict.fromkeys(FIVE, .2)
    return profile


def label(profile):
    return "、".join(f"{LABELS[k]} {v:.0%}" for k, v in profile.items())


def relation(attack, ward, traits=(), defense_traits=()):
    for key in defense_traits:
        lineage = LINEAGES.get(key)
        if lineage and lineage.rule == "guard" and attack == lineage.element and ward == lineage.other:
            return 1 + lineage.percent / 100
    if attack == "wood" and ward == "earth" and "mountain_body" in defense_traits:
        return 1.05
    if attack in FIVE and ward in FIVE:
        distance = (FIVE.index(ward) - FIVE.index(attack)) % 5
        return {1: 1.2, 4: .8}.get(distance, 1.)
    if {attack, ward} == {"yin", "yang"}:
        return 1.32 if "paired_poles" in traits else 1.2
    if {attack, ward} == {"wind", "thunder"}:
        return .9 if "wind_thunder" in traits else .8
    return 1.


def lineage_damage(lineage, element, profile, own_ward):
    if lineage.rule == "pair":
        if element in (lineage.element, lineage.other) and lineage.element in profile and lineage.other in profile:
            return lineage.percent / 100
    elif element == lineage.element and (lineage.rule == "damage"
            or lineage.rule == "pure" and len(profile) == 1
            or lineage.rule == "own" and lineage.other == own_ward):
        return lineage.percent / 100
    return 0.


def components(profile, traits, ward, defense_traits, own_ward=None):
    mixed = "physical" in profile and "fire" in profile and "red_bones" in traits
    steam = "water" in profile and "fire" in profile and "steam_cycle" in traits
    lineages = [LINEAGES[key] for key in traits if key in LINEAGES]
    result = {}
    for element, share in profile.items():
        bonus = .12 if mixed and element in {"physical", "fire"} else 0.
        bonus += sum(lineage_damage(lineage, element, profile, own_ward) for lineage in lineages)
        if steam and element in {"water", "fire"}:
            bonus += .14
        if BASIC_DAMAGE_TRAITS.get(element) in traits:
            bonus += .05
        if element == "physical" and "star_body" in traits:
            bonus += .12
        if element == "metal" and own_ward == "earth" and "earth_metal" in traits:
            bonus += .12
        resist = resistance(element, defense_traits)
        if element == "metal":
            if len(profile) == 1 and ("sheathed_edge" in traits or "sundering_edge" in traits):
                bonus += .08
            if "sundering_edge" in traits:
                resist = max(0., resist - .12)
        if element == "yang" and ward == "yin" and "night_sense" in traits:
            bonus += .08
        if "storm_seal" in traits and {element, own_ward} == {"wind", "thunder"}:
            bonus += .16
        penetration = sum(lineage.percent for lineage in lineages if lineage.rule == "pierce" and lineage.element == element)
        resist = max(0., resist - penetration / 100)
        factor = relation(element, ward, traits, defense_traits)
        result[element] = dict(share=share, bonus=bonus, relation=factor, resistance=resist,
                               multiplier=share*(1+bonus)*factor*(1-resist))
    return result


BASIC_DAMAGE_TRAITS = {"physical": "strength", "fire": "fire_eye", "water": "fish_scales",
                       "wood": "green_veins", "yang": "sun_eye"}
RESISTANCE_TRAITS = {
    "water": (("tide_ear", .06), ("fish_scales", .12)),
    "thunder": (("thunder_bone", .06),),
    "yin": (("night_sense", .10),),
    "earth": (("sand_skin", .06), ("stone_frame", .08), ("mountain_body", .08)),
}


def resistance(element, traits):
    value = .1 if element in FIVE and "five_body" in traits else 0.
    value += sum(amount for key, amount in RESISTANCE_TRAITS.get(element, ()) if key in traits)
    for key in traits:
        lineage = LINEAGES.get(key)
        if lineage and lineage.rule == "resist" and element == lineage.element:
            value += lineage.percent / 100
    return min(.8, value)
