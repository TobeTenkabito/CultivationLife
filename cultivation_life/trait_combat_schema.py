"""Validation of trait and element data frozen into a battle snapshot."""
from math import isfinite
from .combat_attributes import LABELS, FIVE, validate_profile
from .traits import TRAITS


def validate_snapshot(value):
    if value == {}:
        return {}
    required = {"attacks", "ward", "wards", "traits", "flame"}
    if not isinstance(value, dict) or set(value)-{"ward_sources"} != required:
        raise ValueError("战斗属性快照无效")
    traits, wards, attacks = value["traits"], value["wards"], value["attacks"]
    if (not isinstance(traits, (tuple,list)) or len(traits) > len(TRAITS) or set(traits) - TRAITS.keys()
            or not isinstance(wards, (tuple,list)) or len(wards) > len(LABELS)-1
            or set(wards) - (LABELS.keys()-{"physical"}) or len(set(wards)) != len(wards)
            or (value["ward"] is not None and value["ward"] not in wards) or value["flame"] not in FIVE
            or not isinstance(attacks, dict) or set(attacks)-{"technique","artifact"}):
        raise ValueError("战斗属性来源无效")
    result = {}
    for kind, entry in attacks.items():
        if (not isinstance(entry,dict) or set(entry)-{"name","id","tier","profile","power"}
                or not isinstance(entry.get("name"),str) or entry.get("tier") not in (1,2)
                or not isinstance(entry.get("id"), (str,type(None)))
                or type(entry.get("power",0)) not in (int,float) or not isfinite(entry.get("power",0))):
            raise ValueError("战斗出手来源无效")
        result[kind] = {**entry,"profile":validate_profile(entry.get("profile"))}
    kinds = value.get("ward_sources", {})
    if (not isinstance(kinds,dict) or set(kinds)-set(wards)
            or any(not isinstance(v,list) or not v or set(v)-{"technique","artifact","body"} for v in kinds.values())):
        raise ValueError("护身来源无效")
    return dict(attacks=result, traits=list(traits), wards=list(wards), ward=value["ward"],
                ward_sources={k:list(v) for k,v in kinds.items()}, flame=value["flame"])
