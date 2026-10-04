"""Deterministic, world-local talisman recipes and tiered materials.

No mutable runtime registry or dependency on the engine. Instance catalogs are
derived only for the occupied space, and never become outside trade goods.
"""

from functools import lru_cache
from itertools import combinations

DIMENSIONS = ("power", "protection", "assistance")
TIER_NAMES = ("", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二")
WORLD_TIERS = {
    "human": ("灵", range(1, 6)), "demon": ("魔", range(1, 6)),
    "spirit": ("玄灵", range(5, 9)), "true_demon": ("真魔", range(5, 9)),
    "monster_realm": ("妖元", range(5, 9)), "phantom_underworld": ("冥阴", range(5, 9)),
    "hell": ("冥火", range(5, 9)), "celestial": ("仙", range(9, 13)),
    "asura": ("修罗", range(9, 13)), "nether": ("幽天", range(9, 13)),
    "reincarnation": ("轮回", range(9, 13)),
}
PATTERN_NAMES = ("破军", "护元", "扶灵", "攻守", "御风", "护灵", "三元")
PATTERNS = dict(zip(
    ("_".join(c) for size in (1, 2, 3) for c in combinations(DIMENSIONS, size)),
    PATTERN_NAMES,
))
QUALITIES = {"poor": ("下品", .65), "normal": ("中品", 1.),
             "fine": ("上品", 1.35), "perfect": ("极品", 1.7)}


def generate(world, prefix, tiers):
    materials, methods = {}, {}
    for tier in tiers:
        label = TIER_NAMES[tier] + "阶"
        value = round(6 * 3.2 ** (tier - 1))
        for suffix, name, quality in (("paper", "符纸", 1.), ("ink", "朱砂", 1.2),
                                      ("jade", "符玉", 1.4)):
            identity = f"talisman_{world}_{tier}_{suffix}"
            materials[identity] = dict(id=identity, name=f"{label}{prefix}{name}",
                world=world, tier=tier, quality=quality, base_value=round(value * quality),
                description=f"{label}符材，仅供本界同阶制符法使用。")
        for pattern, name in PATTERNS.items():
            strong = [d for d in DIMENSIONS if d in pattern.split("_")]
            identity = f"talisman_{world}_{tier}_{pattern}"
            methods[identity] = dict(id=identity, name=f"{label}{prefix}{name}符",
                world=world, tier=tier, pattern=pattern, strong=strong,
                cost=value * (2 + len(strong)), uses=8 + tier * 2,
                **{d: round((9 if d in strong else 2) * tier, 2) for d in DIMENSIONS})
    return materials, methods


@lru_cache(maxsize=1)
def catalog():
    materials, methods = {}, {}
    for world, (prefix, tiers) in WORLD_TIERS.items():
        mats, recipes = generate(world, prefix, tiers)
        materials.update(mats)
        methods.update(recipes)
    return materials, methods


def local_catalog(game):
    scene = game.spatial_state.get("instances", {}).get(game.spatial_state.get("current"))
    if game.player.world in {"rift", "lost"}:
        if not scene:
            return {}, {}
        return generate(scene["id"], scene["name"].removesuffix("秘境").removesuffix("界"),
                        range(1, 13 if scene["kind"] == "secluded" else (scene.get("resource_ceiling") or 8) + 1))
    return tuple({k: v for k, v in rows.items() if v["world"] == game.player.world}
                 for rows in catalog())


def item_definitions():
    return [dict(id=r["id"], name=r["name"], description=r["description"],
                 tags=["material", "talisman_material"]) for r in catalog()[0].values()]
