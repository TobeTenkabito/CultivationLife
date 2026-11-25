"""Shared personal traits, mastery sources and birth weights."""
from .definition_data import definition as _content_definition
import random
from .combat_attributes import LABELS, read
from .trait_mechanics import SIGNATURES
from .trait_lineages import ARTIFACT_TRAITS, LINEAGES, LINEAGE_BODY_TRAITS

# id -> name, rarity, replacement family, level
TRAITS = _content_definition(__name__, "TRAITS")
MASTERY_ONLY = _content_definition(__name__, "MASTERY_ONLY")
BIRTH_WEIGHTS = {"空": 8000, "绿": 1400, "蓝": 480, "紫": 110, "橙": 10}
COMPATIBLE = _content_definition(__name__, "COMPATIBLE")
EXCLUSIVE_WITH_ALL = frozenset()
EXCLUSIVE_TYPES = {}
EXCLUSIVE = _content_definition(__name__, "EXCLUSIVE")
MASTERY = _content_definition(__name__, "MASTERY")


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


BREAKTHROUGH = _content_definition(__name__, "BREAKTHROUGH")
PRACTICE = _content_definition(__name__, "PRACTICE")


def wash(owner, key):
    if key not in active(owner):
        raise ValueError("尚未拥有此特质")
    record = read(owner, "trait_state")
    del record["owned"][key]
    if key == BREAKTHROUGH["retry_trait"]:
        record.pop("failed_gate", None)


def gate(owner):
    return [read(owner, "realm_index"), read(owner, "layer")]


def breakthrough_bonus(owner, major):
    traits = active(owner)
    previous = state(owner).get("failed_gate", {})
    failures = previous.get("count",0) if previous.get("gate") == gate(owner) else 0
    bonus = sum(value for key, value in BREAKTHROUGH["always"].items() if key in traits)
    if not major:
        bonus += sum(value for key, value in BREAKTHROUGH["minor"].items() if key in traits)
    if BREAKTHROUGH["retry_trait"] in traits:
        bonus += BREAKTHROUGH["retry_bonus"] * min(BREAKTHROUGH["retry_cap"], failures)
    return bonus


def record_roll(owner, success):
    if BREAKTHROUGH["retry_trait"] in active(owner):
        record = read(owner, "trait_state")
        previous = record.pop("failed_gate", {})
        if not success:
            count = previous.get("count",0) if previous.get("gate") == gate(owner) else 0
            record["failed_gate"] = dict(gate=gate(owner), count=min(BREAKTHROUGH["retry_cap"], count + 1))

BODY_TRAITS = _content_definition(__name__, "BODY_TRAITS")
SPECIAL_EFFECTS = _content_definition(__name__, "SPECIAL_EFFECTS")
EFFECTS = _content_definition(__name__, "EFFECTS")


FAMILY_NAMES = {"strength":"膂力","hearing":"听觉","sight":"目力","focus":"心境","body":"体质",
                "speed":"身法","gates":"关窍","lungs":"肺腑","channels":"经脉","will":"道心",
                "bones":"根骨", "skin":"肌肤", "sword":"剑心", "perception":"灵识",
                "polarity":"阴阳", "circulation":"行气", "seal":"法印",
                "destiny":"命格","roots":"灵根","flame":"神通"}


FAMILY_NAMES.update(weave="配气", breath="息法", palm="掌法", sinew="筋络", wood_heart="木心", fist="拳意",
                    yang_channels="阳脉", sword_bone="剑骨", thunder_mark="雷纹", furnace_heart="炉心")
for _key, _lineage in LINEAGES.items():
    if _key in TRAITS:
        raise ValueError(f"特质 ID 重复：{_key}")
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
NON_COMBAT_TRAITS = _content_definition(__name__, "NON_COMBAT_TRAITS") | _PRACTICE_LINEAGES.keys()


def practice_multiplier(owner):
    owned = active(owner)
    bonus = sum(value for key, value in PRACTICE["flat"].items() if key in owned)
    for key in owned:
        lineage = _PRACTICE_LINEAGES.get(key)
        if not lineage:
            continue
        if lineage.rule == "foundation_practice" and read(owner, "realm_index") not in PRACTICE["foundation_realms"]:
            continue
        if lineage.rule == "balanced" and ((read(owner, "spirit_state", {}) or {}).get("mode") == "wandering"
                or (read(owner, "body_training") or 0) < PRACTICE["balanced_minimum"] or (read(owner, "divine_sense_rank") or 0) < PRACTICE["balanced_minimum"]):
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
            or type(failed.get("count")) is not int or not 1 <= failed["count"] <= BREAKTHROUGH["retry_cap"]):
        raise ValueError("特质突破记录无效")
    return record
