"""Damage composition belongs to the attack source. Root eligibility is independent."""
from .definition_data import definition as _content_definition
from math import isfinite

from .damage_weaves import FIVE, LABELS, validate_weave, woven_profile
from .trait_repertoires import WEAVES
from .trait_lineages import LINEAGES

THEMES = {
    "thunder": "雷霆电", "wind": "风岚飙", "water": "水海江河潮泉雨浪冰雪霜渊",
    "fire": "火焰炎灼烬熔焚", "wood": "木树藤竹花草林", "earth": "土岩山岳砂石",
    "metal": "金铁铜银钢刃剑锋", "yin": "阴冥幽鬼魂魄", "yang": "阳日曦曜",
}
PHYSICAL = {"physical": 1.0}


CATALOG_OVERRIDES = _content_definition(__name__, "CATALOG_OVERRIDES")
GUARD_RELATIONS = _content_definition(__name__, "GUARD_RELATIONS")
PAIR_OVERRIDES = _content_definition(__name__, "PAIR_OVERRIDES")
STANCES = _content_definition(__name__, "STANCES")
DAMAGE_BONUSES = _content_definition(__name__, "DAMAGE_BONUSES")
PENETRATION = _content_definition(__name__, "PENETRATION")
RESISTANCE_CAP = .8
for _stance in STANCES.values():
    validate_weave(_stance)


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
    override = CATALOG_OVERRIDES.get(read(entry, "id"))
    if override:
        return dict(override)
    if profile == PHYSICAL and read(entry, "category") != "body":
        theme = read(entry, "element")
        if theme in LABELS:
            return {theme: 1.}
        if theme == "five_elements":
            return dict.fromkeys(FIVE, 1 / len(FIVE))
    return profile


def label(profile):
    return "、".join(f"{LABELS[k]} {v:.0%}" for k, v in profile.items())


def relation(attack, ward, traits=(), defense_traits=()):
    for key in defense_traits:
        lineage = LINEAGES.get(key)
        if lineage and lineage.rule == "guard" and attack == lineage.element and ward == lineage.other:
            return 1 + lineage.percent / 100
    for guard in GUARD_RELATIONS:
        if attack == guard["attack"] and ward == guard["ward"] and guard["trait"] in defense_traits:
            return guard["factor"]
    for override in PAIR_OVERRIDES:
        if override["trait"] in traits and {attack, ward} == set(override["elements"]):
            return override["factor"]
    if attack in FIVE and ward in FIVE:
        distance = (FIVE.index(ward) - FIVE.index(attack)) % len(FIVE)
        return {1: 1.2, len(FIVE) - 1: .8}.get(distance, 1.)
    if {attack, ward} == {"yin", "yang"}:
        return 1.2
    if {attack, ward} == {"wind", "thunder"}:
        return .8
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
    # Each stance uses one live ward, so their conversions are mutually exclusive.
    for key, recipe in STANCES.items():
        if key in traits:
            profile = woven_profile(profile, recipe, ward, own_ward)
    lineages = [LINEAGES[key] for key in traits if key in LINEAGES]
    weave = next((WEAVES[key] for key in traits if key in WEAVES), None)
    if weave:
        profile = woven_profile(profile, weave, ward, own_ward)
    bonuses = [rule for rule in DAMAGE_BONUSES
               if any(key in traits for key in rule["traits"])
               and all(e in profile for e in rule.get("requires", ()))
               and (not rule.get("pure") or len(profile) == 1)
               and rule.get("own_ward", own_ward) == own_ward and rule.get("ward", ward) == ward]
    result = {}
    for element, share in profile.items():
        bonus = sum((rule["bonus"] for rule in bonuses if element in rule["elements"]), 0.)
        bonus += sum(lineage_damage(lineage, element, profile, own_ward) for lineage in lineages)
        resist = resistance(element, defense_traits)
        resist -= sum(value for key, value in PENETRATION.get(element, {}).items() if key in traits)
        penetration = sum(lineage.percent for lineage in lineages if lineage.rule == "pierce" and lineage.element == element)
        resist = max(0., resist - penetration / 100)
        factor = relation(element, ward, traits, defense_traits)
        result[element] = dict(share=share, bonus=bonus, relation=factor, resistance=resist,
                               multiplier=share*(1+bonus)*factor*(1-resist))
    return result


RESISTANCE_TRAITS = _content_definition(__name__, "RESISTANCE_TRAITS")


def resistance(element, traits):
    value = sum((amount for key, amount in RESISTANCE_TRAITS.get(element, ()) if key in traits), 0.)
    for key in traits:
        lineage = LINEAGES.get(key)
        if lineage and lineage.rule == "resist" and element == lineage.element:
            value += lineage.percent / 100
    return min(RESISTANCE_CAP, value)
