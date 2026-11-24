"""Shared personal traits, mastery sources and birth weights."""
import random
from .combat_attributes import LABELS, read
from .trait_mechanics import SIGNATURES
from .trait_lineages import ARTIFACT_TRAITS, LINEAGES, LINEAGE_BODY_TRAITS

# id -> name, rarity, replacement family, level
TRAITS = {
    "strength": ("天生膂力","绿","strength",1), "tide_ear": ("听潮耳","绿","hearing",1),
    "fire_eye": ("丹炉火眼","绿","sight",1), "meditation": ("易入定","绿","focus",1),
    "fish_scales": ("鱼鳞之体","蓝","body",2), "swift_bone": ("追风骨","蓝","speed",2),
    "open_gates": ("关窍通明","蓝","gates",2), "earth_metal": ("地肺藏金","蓝","lungs",2),
    "wind_thunder": ("风雷双窍","紫","channels",3), "tenacity": ("百折道心","紫","will",3),
    "red_bones": ("赤炼筋骨","紫","body",3), "five_body": ("五行之体","紫","body",3),
    "heaven": ("昊天之仙","橙","destiny",4), "confluence": ("万法归流","橙","roots",4),
    "star_body": ("星辰之体","紫","body",4), "five_flame": ("五行之焰","紫","flame",3),
    "green_veins": ("青枝灵脉", "绿", "channels", 1),
    "thunder_bone": ("鸣雷骨", "绿", "bones", 1),
    "sun_eye": ("朝阳眼", "绿", "sight", 1),
    "sand_skin": ("御砂肤", "绿", "skin", 1),
    "sheathed_edge": ("藏锋剑心", "蓝", "sword", 2),
    "stone_frame": ("磐山骨", "蓝", "body", 2),
    "night_sense": ("照夜灵识", "蓝", "perception", 2),
    "paired_poles": ("两仪同心", "紫", "polarity", 3),
    "steam_cycle": ("水火既济", "紫", "circulation", 3),
    "sundering_edge": ("破障剑心", "紫", "sword", 3),
    "mountain_body": ("镇岳之体", "紫", "body", 3),
    "storm_seal": ("风雷法印", "紫", "seal", 3),
}
MASTERY_ONLY = {"star_body", "five_flame", "mountain_body", "storm_seal"}
BIRTH_WEIGHTS = {"空": 8000, "绿": 1400, "蓝": 480, "紫": 110, "橙": 10}
COMPATIBLE = {frozenset(("red_bones", "five_body")), frozenset(("fish_scales", "five_body"))}
EXCLUSIVE_WITH_ALL = frozenset()
EXCLUSIVE_TYPES = {}
EXCLUSIVE = {frozenset(("red_bones", "star_body"))}
MASTERY = {
    "TECH_OPEN_HUANGZE_METAL_SUPPORT": "fish_scales",
    "TECH_YUAN_MAGNETIC_LIGHT": "five_body", "TECH_GUIXU_WEIR_07": "five_body",
    "TECH_OPEN_ZIFU_FIRE_MAIN": "five_flame", "TECH_OPEN_QINGDU_FIRE_MAIN": "five_flame",
    "light:kan": "fish_scales", "light:li": "five_flame", "light:qian": "five_body",
    "TECH_TIANJIAN": "sundering_edge",
    "TECH_METAL_SCRIPTURE": "sheathed_edge",
    "TECH_EARTH_SCRIPTURE": "stone_frame",
    "TECH_YINYANG_BLISS": "paired_poles", "TECH_YIN_YANG_SOUL_UNITY": "paired_poles",
    "TECH_DRY_BLUE_ICE_FLAME": "steam_cycle", "TECH_GUIXU_CANGHAI_09": "steam_cycle",
    "TECH_MOUNTAIN_BEARING_BODY": "mountain_body", "TECH_MYSTIC_MOUNTAIN": "mountain_body",
    "TECH_WIND_ADVANCED": "storm_seal", "TECH_THUNDER_ADVANCED": "storm_seal",
    "TECH_BODY_STARS": "star_body", "TECH_OPEN_HONGHUANG_METAL_SUPPORT": "fish_scales",
}


def state(owner):
    return read(owner, "trait_state", {}) or {}


def active(owner):
    owned = state(owner).get("owned", {})
    if (read(owner, "spirit_state", {}) or {}).get("mode") == "wandering":
        return {k:v for k,v in owned.items() if k not in BODY_TRAITS}
    return owned


def grant(record, key, source):
    if key not in TRAITS:
        raise ValueError("未知特质")
    owned = record.setdefault("owned", {})
    family, level = TRAITS[key][2:]
    replace = []
    for other in owned:
        pair = frozenset((key, other))
        if other != key and (pair in EXCLUSIVE or key in EXCLUSIVE_WITH_ALL or other in EXCLUSIVE_WITH_ALL
                or family in EXCLUSIVE_TYPES.get(other, ()) or TRAITS[other][2] in EXCLUSIVE_TYPES.get(key, ())):
            return False
        if other != key and TRAITS[other][2] == family and pair not in COMPATIBLE:
            if TRAITS[other][3] >= level:
                return False
            replace.append(other)
    for other in replace:
        del owned[other]
    sources = owned.setdefault(key, [])
    if source not in sources:
        sources.append(source)
    return True


def birth(seed, identity):
    rng = random.Random(f"trait-birth/{seed}/{identity}")
    grade = rng.choices(tuple(BIRTH_WEIGHTS), weights=tuple(BIRTH_WEIGHTS.values()))[0]
    record = {}
    if grade != "空":
        options = [k for k,v in TRAITS.items() if v[1] == grade and k not in MASTERY_ONLY]
        grant(record, options[rng.randrange(len(options))], "先天")
    return record


def mastery(owner, book_id):
    key = MASTERY.get(book_id)
    if not key:
        return False
    record = read(owner, "trait_state")
    if record is None:
        if not isinstance(owner, dict):
            return False
        record = owner.setdefault("trait_state", {})
    record.setdefault("mastery", {})[book_id] = key
    return grant(record, key, book_id)


def wash(owner, key):
    if key not in active(owner):
        raise ValueError("尚未拥有此特质")
    record = read(owner, "trait_state")
    del record["owned"][key]
    if key == "tenacity":
        record.pop("failed_gate", None)


def gate(owner):
    return [read(owner, "realm_index"), read(owner, "layer")]


def breakthrough_bonus(owner, major):
    traits = active(owner)
    previous = state(owner).get("failed_gate", {})
    failures = previous.get("count",0) if previous.get("gate") == gate(owner) else 0
    return .25*("heaven" in traits) + .06*(not major and "open_gates" in traits) + (
        .04*min(3, failures) if "tenacity" in traits else 0.)


def record_roll(owner, success):
    if "tenacity" in active(owner):
        record = read(owner, "trait_state")
        previous = record.pop("failed_gate", {})
        if not success:
            count = previous.get("count",0) if previous.get("gate") == gate(owner) else 0
            record["failed_gate"] = dict(gate=gate(owner), count=min(3,count+1))

BODY_TRAITS = {"strength", "tide_ear", "fire_eye", "fish_scales", "swift_bone",
               "earth_metal", "wind_thunder", "red_bones", "five_body", "star_body",
               "green_veins", "thunder_bone", "sun_eye", "sand_skin", "stone_frame", "mountain_body"}
EFFECTS = {
    "green_veins": "木伤 +5%", "thunder_bone": "雷抗 +6 个百分点",
    "sun_eye": "阳伤 +5%", "sand_skin": "土抗 +6 个百分点",
    "sheathed_edge": "纯金攻击的金伤 +8%",
    "stone_frame": "可用土属性护身，土抗 +8 个百分点",
    "night_sense": "阴抗 +10 个百分点，对阴护身目标造成的阳伤 +8%",
    "paired_poles": "以阴攻阳或以阳攻阴时，克制倍率升至 1.32",
    "steam_cycle": "同一击兼具水火时，水伤和火伤各 +14%",
    "sundering_edge": "纯金攻击的金伤 +8%，任何金伤都可穿透至多 12 个百分点金抗",
    "mountain_body": "可用土属性护身，土抗 +8 个百分点。土护身承受木伤时，克制倍率降至 1.05",
    "storm_seal": "风护身时雷伤 +16%，雷护身时风伤 +16%",
    "strength":"物理伤害 +5%", "tide_ear":"水抗 +6%", "fire_eye":"火伤 +5%",
    "meditation":"日常修炼进度 +4%", "fish_scales":"水抗 +12%，水伤 +5%",
    "swift_bone":"首次普通交锋先手 +16%", "open_gates":"小境界突破率 +6 个百分点",
    "earth_metal":"土属性护身时金伤 +12%", "wind_thunder":"风雷互抗的减伤幅度减半",
    "tenacity":"同关每次失败使下次突破率 +4 个百分点，至多 +12",
    "red_bones":"同击兼具物理和火时，这两项伤害各 +12%", "five_body":"五行各项抗性 +10%",
    "heaven":"大、小境界突破率 +25 个百分点，沿用原上限。纯劫战无额外护持",
    "confluence":"以自身五行灵根种数满足同数或更少的功法五行灵根要求",
    "star_body":"物理伤害 +12%", "five_flame":"相应真火功法可选择五行之一出手",
}


FAMILY_NAMES = {"strength":"膂力","hearing":"听觉","sight":"目力","focus":"心境","body":"体质",
                "speed":"身法","gates":"关窍","lungs":"肺腑","channels":"经脉","will":"道心",
                "bones":"根骨", "skin":"肌肤", "sword":"剑心", "perception":"灵识",
                "polarity":"阴阳", "circulation":"行气", "seal":"法印",
                "destiny":"命格","roots":"灵根","flame":"神通"}


FAMILY_NAMES.update(weave="配气", breath="息法", palm="掌法", sinew="筋络", wood_heart="木心", fist="拳意",
                    yang_channels="阳脉", sword_bone="剑骨", thunder_mark="雷纹", furnace_heart="炉心")
for _key, _lineage in LINEAGES.items():
    TRAITS[_key] = (_lineage.name, _lineage.rarity, _lineage.family, _lineage.level)
    EFFECTS[_key] = SIGNATURES[_key].description if _lineage.rule == "signature" else _lineage.description(LABELS)
    if not _lineage.innate:
        MASTERY_ONLY.add(_key)
    for _book in _lineage.books:
        if _book in MASTERY:
            raise ValueError(f"功法大成特质重复配置：{_book}")
        MASTERY[_book] = _key
BODY_TRAITS.update(LINEAGE_BODY_TRAITS)


_PRACTICE_LINEAGES = {key: row for key, row in LINEAGES.items()
                      if row.rule in {"practice", "balanced", "foundation_practice"}}
NON_COMBAT_TRAITS = {"meditation", "open_gates", "tenacity", "heaven", "confluence"} | _PRACTICE_LINEAGES.keys()


def practice_multiplier(owner):
    owned = active(owner)
    bonus = .04 if "meditation" in owned else 0.
    for key in owned:
        lineage = _PRACTICE_LINEAGES.get(key)
        if not lineage:
            continue
        if lineage.rule == "foundation_practice" and read(owner, "realm_index") not in (1, 2):
            continue
        if lineage.rule == "balanced" and ((read(owner, "spirit_state", {}) or {}).get("mode") == "wandering"
                or (read(owner, "body_training") or 0) < 3 or (read(owner, "divine_sense_rank") or 0) < 3):
            continue
        bonus += lineage.percent / 100
    return 1 + bonus


def valid_source(key, source):
    if source == "先天":
        return key not in MASTERY_ONLY
    if source.startswith("artifact:"):
        return ARTIFACT_TRAITS.get(source.removeprefix("artifact:")) == key
    return MASTERY.get(source) == key


def public(owner):
    return [dict(id=k, name=TRAITS[k][0], rarity=TRAITS[k][1], family=FAMILY_NAMES[TRAITS[k][2]],
                 level=TRAITS[k][3], effect=EFFECTS[k], sources=list(sources))
            for k, sources in active(owner).items()]


def validate(record):
    if not isinstance(record, dict) or set(record) - {"owned","mastery","ward","flame","failed_gate"}:
        raise ValueError("特质记录字段无效")
    owned = record.get("owned", {})
    if not isinstance(owned, dict) or set(owned) - TRAITS.keys():
        raise ValueError("持有特质无效")
    for key,sources in owned.items():
        if (not isinstance(sources,list) or not sources or not all(isinstance(s,str) for s in sources)
                or len(sources) != len(set(sources))
                or any(not valid_source(key, s) for s in sources)):
            raise ValueError("特质来源无效")
    mastery = record.get("mastery", {})
    if not isinstance(mastery,dict) or any(MASTERY.get(s) != k or k not in TRAITS for s,k in mastery.items()):
        raise ValueError("大成记录无效")
    from .combat_attributes import LABELS, FIVE
    if ("ward" in record and record["ward"] not in set(LABELS)-{"physical"}
            or "flame" in record and record["flame"] not in FIVE):
        raise ValueError("所选护身或火焰属性无效")
    failed = record.get("failed_gate")
    if failed is not None and (not isinstance(failed,dict) or not isinstance(failed.get("gate"),list)
            or len(failed["gate"]) != 2 or not all(type(v) is int for v in failed["gate"])
            or type(failed.get("count")) is not int or not 1 <= failed["count"] <= 3):
        raise ValueError("特质突破记录无效")
    return record
