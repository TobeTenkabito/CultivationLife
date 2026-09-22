from __future__ import annotations

import operator


OPS = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "in": lambda left, right: left in right,
    "contains": lambda left, right: right in left,
}

LEGACY_TRUE_DEMON_RACE_MAP = {
    "monster": "ancient_demon",
    "spirit": "heaven_demon",
    "woodborn": "blood_demon",
    "seafolk": "sea_demon",
    "featherfolk": "winged_demon",
    "stoneborn": "rock_demon",
    "cloudkin": "shadow_demon",
    "thunderkin": "flame_demon",
    "crystalfolk": "bone_demon",
    "starborn": "void_demon",
    "moonfolk": "soul_demon",
    "magnetfolk": "horn_demon",
    "silkkin": "corpse_demon",
    "miragefolk": "nightmare_demon",
    "sunwing": "flame_demon",
    "horned_drake": "horn_demon",
    "frostfolk": "frost_demon",
    "sandkin": "abyss_demon",
    "insectkin": "insect_demon",
}
