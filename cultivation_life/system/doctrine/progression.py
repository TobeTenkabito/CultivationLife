"""Pure projection of cultivated facts into a neutral combat capability."""
from __future__ import annotations

from ..combat.contracts import CapabilitySource, VoisinageDefinition
from .cultivation import cultivated_voisinage


def source(record: dict, definitions: dict, world: str, *, training_gain=.03) -> CapabilitySource:
    if world != "celestial":
        return CapabilitySource()
    key = record.get("active")
    definition = definitions.get(key)
    level = int(record.get("progress", {}).get(key, {}).get("level", 0))
    if not definition or level < 4:
        return CapabilitySource()
    if level > 4 and record.get("origin") != key:
        raise ValueError("非本源道统不能超过 Lv4")
    if level > 9:
        raise ValueError("道统等级不能超过 Lv9")
    base = VoisinageDefinition(**definition["stages"][level - 1]["voisinage"])
    trained = cultivated_voisinage(base, record.get("voisinage_training", {}).get(key, {}), training_gain)
    return CapabilitySource((trained,), {key: level})
