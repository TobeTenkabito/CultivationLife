"""Curated personal lineages. Books and artifacts refer to canonical content IDs."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Lineage:
    name: str
    rarity: str
    family: str
    level: int
    rule: str
    percent: int
    element: str = ""
    other: str = ""
    innate: bool = False
    books: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()

    def description(self, labels):
        a = labels.get(self.element, "")
        b = labels.get(self.other, "")
        damage = "物理伤害" if self.element == "physical" else f"{a}属性伤害"
        n = self.percent
        return {
            "damage": f"{damage}提高 {n}%",
            "resist": f"{a}抗提高 {n} 个百分点",
            "own": f"自身以{b}护身时，{damage}提高 {n}%",
            "pure": f"纯{a}攻击伤害提高 {n}%",
            "pair": f"同一击兼具{a}和{b}时，这两项伤害各提高 {n}%",
            "pierce": f"{damage}穿透至多 {n} 个百分点{a}抗",
            "guard": f"以{b}护身承受{a}伤时，克制倍率由 1.20 降至 {1 + n / 100:.2f}",
            "foundation_practice": f"练气期和筑基期的日常修炼所得进度提高 {n}%",
            "practice": f"日常修炼所得进度提高 {n}%",
            "balanced": f"身在肉身且炼体和神识均达三级时，日常修炼所得进度提高 {n}%",
        }[self.rule]


LINEAGES = {
    "first_circuit": Lineage("小周天", "绿", "focus", 1, "foundation_practice", 5, innate=True,
        books=("TECH_BASIC_QI",)),
    "needle_intent": Lineage("引针意", "绿", "sword", 1, "damage", 5, "metal", innate=True,
        books=("TECH_OPEN_SONGCHUANG_METAL_MAIN",)),
    "palm_spark": Lineage("掌心雷纹", "绿", "thunder_mark", 1, "damage", 5, "thunder", innate=True,
        books=("TECH_OPEN_SONGCHUANG_THUNDER_COMBAT",)),
    "frost_soul": Lineage("霜魄", "绿", "perception", 1, "resist", 6, "yin", innate=True,
        books=("TECH_OPEN_SONGCHUANG_YIN_SUPPORT",)),
    "morning_veil": Lineage("朝霞衣", "绿", "yang_channels", 1, "resist", 6, "yang", innate=True,
        books=("TECH_OPEN_SONGCHUANG_YANG_COMBAT",)),
    "rooted_stance": Lineage("沉桩劲", "绿", "fist", 1, "own", 6, "physical", "earth", innate=True,
        books=("TECH_OPEN_SONGCHUANG_EARTH_MAIN",), artifacts=("mortal_beast_core_charm",)),
    "duckweed_step": Lineage("踏萍步", "绿", "speed", 1, "own", 6, "physical", "water", innate=True,
        books=("TECH_OPEN_SONGCHUANG_WATER_SUPPORT",), artifacts=("guixu_canghai_equipment_09",)),
    "cinder_finger": Lineage("引炭指", "绿", "palm", 1, "pure", 6, "fire", innate=True,
        books=("TECH_OPEN_SONGCHUANG_FIRE_COMBAT",)),
    "pine_needle": Lineage("松针劲", "绿", "wood_heart", 1, "pure", 6, "wood", innate=True,
        books=("TECH_OPEN_SONGCHUANG_WOOD_MAIN",)),
    "sand_breath": Lineage("聚砂息", "绿", "breath", 1, "pure", 6, "earth", innate=True,
        books=("TECH_DEMON_HERITAGE_1",)),
    "moon_thread": Lineage("纤月引", "绿", "perception", 1, "pure", 6, "yin", innate=True,
        books=("TECH_OPEN_SONGCHUANG_YIN_MAIN",)),
    "stream_leaf": Lineage("浮花劲", "绿", "circulation", 1, "pair", 6, "water", "wood", innate=True,
        books=("TECH_OPEN_SONGCHUANG_WOOD_COMBAT",)),
    "iron_grain": Lineage("铁砂筋", "绿", "sinew", 1, "pair", 6, "metal", "earth", innate=True,
        books=("TECH_OPEN_SONGCHUANG_EARTH_METAL_SUPPORT",)),
    "well_edge": Lineage("泉刃", "绿", "sword", 1, "pair", 6, "water", "metal", innate=True,
        books=("TECH_OPEN_SONGCHUANG_METAL_WATER_COMBAT",)),
    "storm_reed": Lineage("听霆息", "绿", "breath", 1, "pair", 6, "wind", "thunder", innate=True,
        books=("TECH_OPEN_SONGCHUANG_WIND_THUNDER_MAIN",)),
    "flat_stone": Lineage("叠石掌", "绿", "palm", 1, "own", 6, "earth", "earth", innate=True,
        books=("TECH_OPEN_SONGCHUANG_EARTH_COMBAT",)),
    "ember_meridian": Lineage("温炉脉", "绿", "channels", 1, "own", 6, "fire", "fire", innate=True,
        books=("TECH_OPEN_SONGCHUANG_FIRE_MAIN",)),
    "silver_scale": Lineage("银鳞气", "绿", "circulation", 1, "own", 6, "water", "metal", innate=True,
        books=("TECH_OPEN_SONGCHUANG_METAL_WATER_SUPPORT",)),
    "mirror_glint": Lineage("镜里锋", "绿", "sight", 1, "own", 6, "metal", "yin", innate=True,
        books=("TECH_OPEN_SONGCHUANG_YIN_COMBAT",)),
    "sunlit_branch": Lineage("向阳枝", "绿", "wood_heart", 1, "own", 6, "wood", "yang", innate=True,
        books=("TECH_OPEN_SONGCHUANG_WOOD_FIRE_MAIN",)),
    "clear_foundation": Lineage("澄台筑基", "蓝", "focus", 2, "foundation_practice", 9, innate=True,
        books=("TECH_HUMAN_HERITAGE_3",)),
    "anvil_breath": Lineage("百炼整劲", "蓝", "fist", 2, "pure", 9, "physical", innate=True,
        books=("TECH_BODY_HUNDRED_REFINEMENT",)),
    "hidden_thunder": Lineage("藏震指", "蓝", "thunder_mark", 2, "pure", 10, "thunder", innate=True,
        books=("TECH_OPEN_YUNXIU_THUNDER_COMBAT",)),
    "returning_ash": Lineage("烬中真火", "蓝", "furnace_heart", 2, "pure", 10, "fire", innate=True,
        books=("TECH_DEMON_HERITAGE_2",)),
    "iron_rib": Lineage("岩铜骨", "蓝", "sinew", 2, "pair", 10, "metal", "earth", innate=True,
        books=("TECH_OPEN_YUNXIU_EARTH_METAL_COMBAT",)),
    "rill_branch": Lineage("溪桥折柳", "蓝", "circulation", 2, "pair", 10, "wood", "water", innate=True,
        books=("TECH_OPEN_SONGCHUANG_WOOD_WATER_FIRE_EARTH_MAIN",)),
    "dark_thunder": Lineage("阴雷痕", "蓝", "thunder_mark", 2, "pair", 10, "yin", "thunder",
        books=("TECH_OPEN_YUNXIU_WIND_THUNDER_YIN_COMBAT",)),
    "ghost_marrows": Lineage("白骨凝阴", "蓝", "bones", 2, "pair", 10, "physical", "yin",
        books=("TECH_BONE_VESSEL_BODY",)),
    "sunstone_bone": Lineage("曜石骨", "蓝", "bones", 2, "pair", 10, "physical", "yang", innate=True,
        books=("TECH_DEMON_HERITAGE_6",)),
    "mountain_step": Lineage("负山劲", "蓝", "fist", 2, "pair", 10, "physical", "earth", innate=True,
        books=("TECH_HUMAN_HERITAGE_6",), artifacts=("guixu_canghai_equipment_07",)),
    "deep_keel": Lineage("分波劲", "蓝", "palm", 2, "pierce", 8, "water",
        books=("TECH_GUIXU_CANGHAI_03",), artifacts=("guixu_canghai_equipment_05",)),
    "quiet_shade": Lineage("镇幽识", "蓝", "perception", 2, "pierce", 8, "yin", innate=True,
        books=("TECH_YIN_ADVANCED",), artifacts=("ghost_gate_ward",)),
    "flood_bank": Lineage("束水成堤", "蓝", "circulation", 2, "guard", 12, "earth", "water", innate=True,
        books=("TECH_OPEN_YUNXIU_WATER_SUPPORT",), artifacts=("guixu_canghai_equipment_04",)),
    "tempered_edge": Lineage("淬火金衣", "蓝", "skin", 2, "guard", 12, "fire", "metal",
        books=("TECH_OPEN_YUNXIU_METAL_WATER_SUPPORT",)),
    "reed_breath": Lineage("芦风息", "绿", "breath", 1, "damage", 5, "wind", innate=True,
        books=("TECH_WIND",)),
    "dew_palm": Lineage("凝露掌", "绿", "palm", 1, "damage", 5, "water", innate=True,
        books=("TECH_GUIXU_CANGHAI_01",), artifacts=("guixu_canghai_equipment_12",)),
    "dusky_pupil": Lineage("识幽瞳", "绿", "sight", 1, "damage", 5, "yin", innate=True,
        books=("TECH_SOUL_ECHO_SENSE",)),
    "stone_palm": Lineage("叩石掌", "绿", "palm", 1, "damage", 5, "earth", innate=True,
        books=("TECH_CONFUCIAN_PEOPLE_ROOT",)),
    "ember_skin": Lineage("避火肤", "绿", "skin", 1, "resist", 6, "fire", innate=True,
        books=("TECH_CRIMSON_FURNACE",)),
    "willow_sinew": Lineage("柳韧筋", "绿", "sinew", 1, "resist", 6, "wood", innate=True,
        books=("TECH_MONSTER_HIDE_FORGING",)),
    "bell_bone": Lineage("金声骨", "绿", "bones", 1, "resist", 6, "metal", innate=True,
        books=("TECH_BODY_MORTAL",), artifacts=("beast_pattern_bone",)),
    "still_breath": Lineage("守一息", "绿", "breath", 1, "resist", 6, "wind", innate=True,
        books=("TECH_COMMON_QI",)),
    "tide_edge": Lineage("洗剑潮生", "蓝", "sword", 2, "own", 12, "metal", "water", innate=True,
        books=("TECH_GUIXU_CANGHAI_02",), artifacts=("guixu_canghai_equipment_03",)),
    "wood_kiln": Lineage("青薪火候", "蓝", "circulation", 2, "own", 12, "fire", "wood", innate=True,
        books=("TECH_FIRE_SCRIPTURE",)),
    "rainwood": Lineage("春霖木心", "蓝", "wood_heart", 2, "own", 12, "wood", "water", innate=True,
        books=("TECH_WOOD_SCRIPTURE",), artifacts=("guixu_monster_realm_equipment_02",)),
    "thunder_fist": Lineage("惊蛰拳意", "蓝", "fist", 2, "own", 10, "physical", "thunder",
        artifacts=("thunder_plume_talisman",)),
    "moon_lamp": Lineage("守魄灯心", "蓝", "perception", 2, "resist", 12, "yin", innate=True,
        books=("TECH_SOUL_LAMP_CANON",), artifacts=("soul_lamp",)),
    "golden_cicada": Lineage("金蝉息", "蓝", "breath", 2, "resist", 12, "yang", innate=True,
        books=("TECH_PUTI",), artifacts=("ghost_silk_robe",)),
    "river_pearl": Lineage("定海珠心", "蓝", "circulation", 2, "pure", 10, "water",
        books=("TECH_WATER_SCRIPTURE",), artifacts=("guixu_canghai_equipment_01",)),
    "scarlet_wick": Lineage("赤心烛", "蓝", "yang_channels", 2, "pure", 10, "yang", innate=True,
        books=("TECH_YANG", "TECH_CONFUCIAN_VAST_QI",)),
    "cloud_tread": Lineage("御罡步", "蓝", "speed", 2, "pure", 10, "wind", innate=True,
        books=("TECH_GUIXU_CANGHAI_08",)),
    "jade_platform": Lineage("玉台守静", "蓝", "focus", 2, "practice", 7, innate=True,
        books=("TECH_COMMON_FOUNDATION", "TECH_BAOPU_CANON",)),
    "bamboo_edge": Lineage("青篁剑骨", "紫", "sword_bone", 3, "pair", 14, "wood", "metal",
        books=("TECH_QINGYUAN_SWORD",), artifacts=("green_bamboo_sword",)),
    "river_blade": Lineage("天河淬锋", "紫", "sword_bone", 3, "pair", 14, "water", "metal",
        books=("TECH_HEAVENLY_RIVER_REFINING",), artifacts=("heavenly_river_sword_embryo",)),
    "nether_tide": Lineage("冥潮魂印", "紫", "seal", 3, "pair", 14, "water", "yin", innate=True,
        books=("TECH_NETHER_TIDE_CANON", "TECH_BLOOD_RIVER",), artifacts=("guixu_yellow_spring_equipment_01",)),
    "ghost_wick": Lineage("幽焰灯芯", "紫", "flame", 3, "pair", 14, "yin", "fire",
        books=("TECH_GHOSTFIRE_BLADE",)),
    "black_sun": Lineage("黑日火种", "紫", "flame", 3, "pair", 14, "fire", "yang",
        books=("TECH_BLACK_SUN_TRUE_FLAME",)),
    "storm_tide": Lineage("霆潮交鸣", "紫", "seal", 3, "pair", 14, "thunder", "water",
        artifacts=("guixu_nether_equipment_02",)),
    "soul_hunting": Lineage("摄魂幡意", "紫", "perception", 3, "pierce", 12, "yin",
        books=("TECH_MYRIAD_SOUL_SENSE",), artifacts=("soul_banner", "guixu_bloodriver_equipment_07",)),
    "sky_thunder": Lineage("天罚雷纹", "紫", "thunder_mark", 3, "pierce", 12, "thunder",
        books=("TECH_NINE_HEAVENS_THUNDER",), artifacts=("guixu_beast_vortex_equipment_05",)),
    "lotus_heart": Lineage("烬里莲心", "紫", "wood_heart", 3, "guard", 6, "metal", "wood",
        books=("TECH_QINGPAN_SWORD_ARRAY",)),
    "quenched_flame": Lineage("不熄炉心", "紫", "furnace_heart", 3, "guard", 6, "water", "fire", innate=True,
        artifacts=("guixu_asura_equipment_01",)),
    "sea_sun": Lineage("海上生阳", "紫", "yang_channels", 3, "pair", 14, "water", "yang",
        books=("TECH_SEA",)),
    "yellow_court": Lineage("黄庭内照", "紫", "focus", 3, "balanced", 12,
        books=("TECH_YELLOW_COURT_INNER", "TECH_NINE_TURN_UNITY",)),
}

# Selected old traits also have an artifact lineage. All other items retain their ordinary use.
ARTIFACT_TRAITS = {
    "spirit_sword": "sheathed_edge", "blood_banner": "night_sense",
    "yuanhe_five_poles_mountain": "mountain_body", "celestial_star_array": "star_body",
    "guixu_canghai_equipment_08": "tide_ear", "guixu_monster_realm_equipment_06": "stone_frame",
    "guixu_celestial_equipment_03": "sundering_edge", "guixu_celestial_equipment_12": "paired_poles",
    **{item: key for key, lineage in LINEAGES.items() for item in lineage.artifacts},
}

# These abilities follow the physical body during wandering and possession.
LINEAGE_BODY_TRAITS = {"iron_grain", "iron_rib", "ghost_marrows", "sunstone_bone", "tempered_edge",
                       "dusky_pupil", "ember_skin", "willow_sinew", "bell_bone", "bamboo_edge", "river_blade"}
