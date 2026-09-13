from __future__ import annotations

import hashlib
import json
from itertools import combinations
from typing import Any, Final, Iterable


SCHEMA_VERSION: Final = 1
STAT_NAMES: Final = {
    "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
}
SPECIES_NAMES: Final = {
    "serpent": "潜鳞", "avian": "天羽", "ape": "战猿", "fox": "月狐",
    "turtle": "玄甲", "insect": "百蜕", "aquatic": "沧澜", "flora": "灵木",
}

# This is deliberately a finite, data-only grammar. Saved traits contain IDs
# from these tables rather than executable expressions.
BLOODLINE_RULE_TRIGGERS: Final[dict[str, dict[str, Any]]] = {
    "round_start": {"name": "开始时"},
    "initiative_resolved": {"name": "先手确定后"},
    "before_damage": {"name": "交锋结算前"},
    "after_damage": {"name": "受创后"},
    "round_end": {"name": "结束时"},
}
BLOODLINE_RULE_SCHEDULES: Final[dict[str, dict[str, Any]]] = {
    "every": {"name": "每轮", "uptime": 1.00},
    "odd": {"name": "奇数轮", "uptime": 0.55},
    "even": {"name": "偶数轮", "uptime": 0.55},
    "first_two": {"name": "前两轮", "uptime": 0.45},
    "after_second": {"name": "第三轮起每轮", "uptime": 0.55},
}


def _condition(
    name: str, family: str, triggers: Iterable[str], uptime: float,
    *, tags: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "name": name, "family": family, "triggers": tuple(triggers),
        "uptime": uptime, "tags": tuple(tags),
    }


_ALL_TRIGGERS = tuple(BLOODLINE_RULE_TRIGGERS)
_AFTER_INITIATIVE = ("initiative_resolved", "before_damage", "after_damage", "round_end")
_AFTER_DAMAGE = ("after_damage", "round_end")
BLOODLINE_RULE_CONDITIONS: Final[dict[str, dict[str, Any]]] = {
    "always": _condition("没有额外限制", "always", _ALL_TRIGGERS, 1.00),
    "enemy_same_or_lower": _condition("敌方与自身同境或境界更低", "realm", _ALL_TRIGGERS, 0.68),
    "enemy_higher": _condition("敌方境界高于自身", "realm", _ALL_TRIGGERS, 0.32),
    "player_state_50": _condition("己方战斗态势不高于50%", "player_state", _ALL_TRIGGERS, 0.45),
    "player_state_30": _condition("己方战斗态势不高于30%", "player_state", _ALL_TRIGGERS, 0.28),
    "enemy_state_40": _condition("敌方战斗态势不高于40%", "enemy_state", _ALL_TRIGGERS, 0.38),
    "player_mp_40": _condition("己方法力不高于40%", "player_mp", _ALL_TRIGGERS, 0.38),
    "player_morale_50": _condition("己方战意不高于50", "player_morale", _ALL_TRIGGERS, 0.32),
    "enemy_morale_50": _condition("敌方战意不高于50", "enemy_morale", _ALL_TRIGGERS, 0.38),
    "terrain_open": _condition("身处开阔战场", "terrain", _ALL_TRIGGERS, 0.40),
    "terrain_narrow": _condition("身处狭窄战场", "terrain", _ALL_TRIGGERS, 0.35),
    "terrain_dangerous": _condition("身处险要战场", "terrain", _ALL_TRIGGERS, 0.35),
    "artificial_field": _condition("战场存在禁制或大阵", "artificial", _ALL_TRIGGERS, 0.35),
    "player_first": _condition("己方取得先手", "initiative", _AFTER_INITIATIVE, 0.52),
    "enemy_first": _condition("己方未取得先手", "initiative", _AFTER_INITIATIVE, 0.48),
    "control_success": _condition("本轮神识压制成功", "control", ("before_damage", "after_damage", "round_end"), 0.45),
    "received_12": _condition("本轮态势损失达到12%", "received_loss", _AFTER_DAMAGE, 0.42),
    "dealt_15": _condition("本轮削去敌方至少15%态势", "dealt_loss", _AFTER_DAMAGE, 0.45),
}


def _effect(
    name: str, description: str, family: str, triggers: Iterable[str], power: float,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "name": name, "description": description, "family": family,
        "triggers": tuple(triggers), "power": power, **payload,
    }


BLOODLINE_RULE_EFFECTS: dict[str, dict[str, Any]] = {}
for _stat, _label in STAT_NAMES.items():
    for _suffix, _value, _power in (("minor", 0.06, 6.0), ("major", 0.10, 10.0)):
        BLOODLINE_RULE_EFFECTS[f"self_{_stat}_{_suffix}"] = _effect(
            f"{_label}滋长", f"本轮自身{_label}提高{_value:.0%}", f"self_stat:{_stat}",
            ("round_start", "initiative_resolved"), _power,
            kind="stat_multiplier", target="player", stat=_stat, value=_value,
        )
for _stat, _label in STAT_NAMES.items():
    for _suffix, _value, _power in (("minor", 0.05, 6.0), ("major", 0.08, 10.0)):
        BLOODLINE_RULE_EFFECTS[f"enemy_{_stat}_{_suffix}"] = _effect(
            f"{_label}侵蚀", f"本轮敌方{_label}降低{_value:.0%}", f"enemy_stat:{_stat}",
            ("round_start", "initiative_resolved"), _power,
            kind="stat_multiplier", target="enemy", stat=_stat, value=_value,
        )
BLOODLINE_RULE_EFFECTS.update({
    "damage_up_08": _effect("猎伤", "本轮造成的态势损耗提高8%", "damage_up", ("initiative_resolved", "before_damage"), 7.0, kind="damage_multiplier", target="enemy", value=0.08),
    "damage_up_12": _effect("猎杀", "本轮造成的态势损耗提高12%", "damage_up", ("initiative_resolved", "before_damage"), 10.5, kind="damage_multiplier", target="enemy", value=0.12),
    "damage_down_08": _effect("卸力", "本轮受到的态势损耗降低8%", "damage_down", ("initiative_resolved", "before_damage"), 7.5, kind="damage_multiplier", target="player", value=0.08),
    "damage_down_12": _effect("护生", "本轮受到的态势损耗降低12%", "damage_down", ("initiative_resolved", "before_damage"), 11.0, kind="damage_multiplier", target="player", value=0.12),
    "damage_cap_28": _effect("分震", "使本轮战斗态势损失不超过28%", "damage_cap", ("before_damage",), 9.0, kind="damage_cap", target="player", value=0.28),
    "damage_cap_24": _effect("锁命", "使本轮战斗态势损失不超过24%", "damage_cap", ("before_damage",), 13.0, kind="damage_cap", target="player", value=0.24),
    "reclaim_15": _effect("回元", "回收本轮态势损失的15%，每轮最多恢复3%", "reclaim", ("after_damage",), 8.0, kind="reclaim_loss", target="player", value=0.15, cap=0.03),
    "reclaim_20": _effect("返生", "回收本轮态势损失的20%，每轮最多恢复4%", "reclaim", ("after_damage",), 11.5, kind="reclaim_loss", target="player", value=0.20, cap=0.04),
    "restore_state_02": _effect("养命", "恢复2%最大战斗态势", "state_restore", ("round_end",), 7.0, kind="restore_state", target="player", value=0.02),
    "restore_state_03": _effect("生息", "恢复3%最大战斗态势", "state_restore", ("round_end",), 10.5, kind="restore_state", target="player", value=0.03),
    "restore_mp_02": _effect("回气", "恢复2%最大法力", "mp_restore", ("round_end",), 4.5, kind="restore_mp", target="player", value=0.02),
    "restore_mp_03": _effect("纳灵", "恢复3%最大法力", "mp_restore", ("round_end",), 6.5, kind="restore_mp", target="player", value=0.03),
    "morale_self_4": _effect("定魄", "恢复4点己方战意", "self_morale", ("after_damage", "round_end"), 4.0, kind="modify_morale", target="player", value=4.0),
    "morale_self_6": _effect("不屈", "恢复6点己方战意", "self_morale", ("after_damage", "round_end"), 6.0, kind="modify_morale", target="player", value=6.0),
    "morale_enemy_4": _effect("惊魂", "额外削弱敌方4点战意", "enemy_morale", ("after_damage", "round_end"), 4.0, kind="modify_morale", target="enemy", value=4.0),
    "morale_enemy_6": _effect("慑魄", "额外削弱敌方6点战意", "enemy_morale", ("after_damage", "round_end"), 6.0, kind="modify_morale", target="enemy", value=6.0),
})
BLOODLINE_RULE_EFFECTS = dict(BLOODLINE_RULE_EFFECTS)

_SPECIES_EFFECT_FAMILIES: Final[dict[str, tuple[str, ...]]] = {
    "serpent": ("damage_up", "enemy_stat:mobility", "enemy_stat:guard", "self_stat:breach"),
    "avian": ("damage_up", "self_stat:mobility", "self_stat:sense", "self_stat:breach"),
    "ape": ("damage_up", "damage_down", "self_stat:might", "self_stat:guard", "reclaim"),
    "fox": ("enemy_morale", "enemy_stat:sense", "self_stat:sense", "self_stat:mobility"),
    "turtle": ("damage_cap", "damage_down", "reclaim", "state_restore", "self_stat:guard"),
    "insect": ("reclaim", "mp_restore", "enemy_stat:sense", "self_stat:sustain"),
    "aquatic": ("mp_restore", "reclaim", "damage_down", "self_stat:sustain"),
    "flora": ("state_restore", "reclaim", "damage_down", "self_stat:guard", "self_stat:sustain"),
}

_SPECIAL_EFFECT_CONDITION_FAMILIES: Final[dict[str, frozenset[str]]] = {
    "damage_up": frozenset({"always", "realm", "player_state", "enemy_state", "terrain", "artificial", "initiative", "control"}),
    "damage_down": frozenset({"always", "realm", "player_state", "terrain", "artificial", "initiative", "control"}),
    "damage_cap": frozenset({"always", "realm", "player_state", "terrain", "artificial", "initiative", "control"}),
    "reclaim": frozenset({"always", "realm", "player_state", "terrain", "artificial", "initiative", "control", "received_loss"}),
    "state_restore": frozenset({"always", "realm", "player_state", "terrain", "artificial", "initiative", "received_loss"}),
    "mp_restore": frozenset({"always", "realm", "player_mp", "terrain", "artificial", "initiative", "control"}),
    "self_morale": frozenset({"always", "realm", "player_state", "player_morale", "artificial", "initiative", "received_loss"}),
    "enemy_morale": frozenset({"always", "realm", "enemy_state", "enemy_morale", "artificial", "initiative", "control", "dealt_loss"}),
}


def _allowed_condition_families(effect: dict[str, Any]) -> frozenset[str]:
    return _SPECIAL_EFFECT_CONDITION_FAMILIES.get(
        str(effect["family"]),
        frozenset(definition["family"] for definition in BLOODLINE_RULE_CONDITIONS.values()),
    )

MAX_RAW_POWER: Final = 13.0
MAX_EXPECTED_POWER: Final = 8.25
MAX_COLLECTION_EXPECTED_POWER: Final = 96.0
MAX_TRAITS: Final = 16


def _scheduled(schedule_id: str, round_no: int) -> bool:
    return {
        "every": True, "odd": round_no % 2 == 1, "even": round_no % 2 == 0,
        "first_two": round_no <= 2, "after_second": round_no >= 3,
    }.get(schedule_id, False)


def describe_generated_trait(rule: dict[str, Any]) -> str:
    schedule = BLOODLINE_RULE_SCHEDULES[str(rule["schedule"])]["name"]
    trigger = BLOODLINE_RULE_TRIGGERS[str(rule["trigger"])]["name"]
    condition_ids = list(map(str, rule.get("conditions", [])))
    condition_text = ""
    if condition_ids != ["always"]:
        condition_text = "若" + "，且".join(BLOODLINE_RULE_CONDITIONS[item]["name"] for item in condition_ids) + "，"
    effect = BLOODLINE_RULE_EFFECTS[str(rule["effect"])]
    return f"{schedule}{trigger}，{condition_text}{effect['description']}。"


def _power(rule: dict[str, Any]) -> tuple[float, float]:
    effect = BLOODLINE_RULE_EFFECTS[str(rule["effect"])]
    raw = float(effect["power"])
    uptime = float(BLOODLINE_RULE_SCHEDULES[str(rule["schedule"])]["uptime"])
    condition_uptime = 1.0
    for condition_id in rule.get("conditions", []):
        condition_uptime *= float(BLOODLINE_RULE_CONDITIONS[str(condition_id)]["uptime"])
    # Multiple conditions are correlated in actual battles. A floor prevents
    # stacking rare-looking clauses from buying an unjustified huge effect.
    uptime *= max(0.28, condition_uptime)
    return raw, round(raw * uptime, 3)


def validate_generated_trait(rule: Any) -> list[str]:
    reasons: list[str] = []
    if not isinstance(rule, dict):
        return ["特质不是对象"]
    if int(rule.get("schema_version", -1)) != SCHEMA_VERSION:
        reasons.append("规则版本未知")
    species_id = str(rule.get("species_id", ""))
    trigger_id, schedule_id, effect_id = map(str, (
        rule.get("trigger", ""), rule.get("schedule", ""), rule.get("effect", ""),
    ))
    if species_id not in SPECIES_NAMES:
        reasons.append("未知本源种")
    if trigger_id not in BLOODLINE_RULE_TRIGGERS:
        reasons.append("未知触发时点")
    if schedule_id not in BLOODLINE_RULE_SCHEDULES:
        reasons.append("未知轮次限制")
    if effect_id not in BLOODLINE_RULE_EFFECTS:
        reasons.append("未知效果")
    raw_conditions = rule.get("conditions")
    if not isinstance(raw_conditions, list) or not 1 <= len(raw_conditions) <= 2:
        reasons.append("条件数量必须为一至两个")
        condition_ids: list[str] = []
    else:
        condition_ids = list(map(str, raw_conditions))
        if len(set(condition_ids)) != len(condition_ids):
            reasons.append("条件重复")
        if any(item not in BLOODLINE_RULE_CONDITIONS for item in condition_ids):
            reasons.append("存在未知条件")
    if reasons:
        return reasons
    effect = BLOODLINE_RULE_EFFECTS[effect_id]
    if trigger_id not in effect["triggers"]:
        reasons.append("效果无法在所选时点结算")
    families = [BLOODLINE_RULE_CONDITIONS[item]["family"] for item in condition_ids]
    if len(set(families)) != len(families):
        reasons.append("条件重复约束同一战斗变量")
    if "always" in condition_ids and (len(condition_ids) > 1 or schedule_id == "every"):
        reasons.append("无条件规则必须带有轮次限制，且不能伪装成复合条件")
    for condition_id in condition_ids:
        if trigger_id not in BLOODLINE_RULE_CONDITIONS[condition_id]["triggers"]:
            reasons.append(f"条件“{BLOODLINE_RULE_CONDITIONS[condition_id]['name']}”在触发时点尚无数据")
        if BLOODLINE_RULE_CONDITIONS[condition_id]["family"] not in _allowed_condition_families(effect):
            reasons.append(f"条件“{BLOODLINE_RULE_CONDITIONS[condition_id]['name']}”与效果语义不相容")
    # Causal/semantic guards: generated effects never damage their beneficiary,
    # heal their enemy, or use a result as a pre-result condition.
    kind, target = str(effect["kind"]), str(effect["target"])
    if target == "player" and kind in {"damage_self", "drain_state"}:
        reasons.append("规则会在受益条件下反向伤害自身")
    if target == "enemy" and kind in {"restore_state", "restore_mp"}:
        reasons.append("规则会恢复敌方资源")
    if effect["family"] == "reclaim" and trigger_id != "after_damage":
        reasons.append("回收本轮损失只能在受创后结算")
    raw_power, expected_power = _power(rule)
    if raw_power > MAX_RAW_POWER:
        reasons.append(f"单次效果强度{raw_power:g}超过硬上限{MAX_RAW_POWER:g}")
    if expected_power > MAX_EXPECTED_POWER:
        reasons.append(f"按预计触发率折算强度{expected_power:g}超过上限{MAX_EXPECTED_POWER:g}")
    expected_id = generated_trait_id(rule)
    if rule.get("id") and str(rule["id"]) != expected_id:
        reasons.append("特质ID与规则内容不一致")
    expected_name = f"{SPECIES_NAMES[species_id]}·{effect['name']}"
    if rule.get("name") and str(rule["name"]) != expected_name:
        reasons.append("特质名称与规则内容不一致")
    if rule.get("description") and str(rule["description"]) != describe_generated_trait(rule):
        reasons.append("特质描述与规则内容不一致")
    saved_power = rule.get("power")
    if isinstance(saved_power, dict) and (
        abs(float(saved_power.get("raw", -1)) - raw_power) > 1e-9
        or abs(float(saved_power.get("expected", -1)) - expected_power) > 1e-9
    ):
        reasons.append("特质强度快照与规则内容不一致")
    return reasons


def generated_trait_id(rule: dict[str, Any]) -> str:
    canonical = {
        "schema_version": int(rule.get("schema_version", SCHEMA_VERSION)),
        "species_id": str(rule.get("species_id", "")),
        "trigger": str(rule.get("trigger", "")),
        "schedule": str(rule.get("schedule", "")),
        "conditions": list(map(str, rule.get("conditions", []))),
        "effect": str(rule.get("effect", "")),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return f"bloodline_generated_{digest}"


def validate_generated_collection(rules: Iterable[dict[str, Any]]) -> list[str]:
    rows = list(rules)
    reasons: list[str] = []
    if len(rows) > MAX_TRAITS:
        reasons.append(f"随机族血最多保留{MAX_TRAITS}项")
    ids = [str(row.get("id", "")) for row in rows]
    if len(set(ids)) != len(ids):
        reasons.append("存在完全相同的重复特质")
    slots = [str(row.get("slot_id")) for row in rows if row.get("slot_id")]
    if len(set(slots)) != len(slots):
        reasons.append("多个复合特质占用了同一族血槽位")
    families: dict[str, int] = {}
    for row in rows:
        reasons.extend(validate_generated_trait(row))
        effect = BLOODLINE_RULE_EFFECTS.get(str(row.get("effect", "")), {})
        family = str(effect.get("family", ""))
        families[family] = families.get(family, 0) + 1
    limits = {"damage_cap": 1, "reclaim": 2, "state_restore": 2, "damage_up": 2, "damage_down": 2}
    for family, limit in limits.items():
        if families.get(family, 0) > limit:
            reasons.append(f"同类效果“{family}”超过叠加上限{limit}")
    expected_total = sum(
        _power(row)[1] for row in rows
        if str(row.get("effect", "")) in BLOODLINE_RULE_EFFECTS
        and str(row.get("schedule", "")) in BLOODLINE_RULE_SCHEDULES
        and all(str(item) in BLOODLINE_RULE_CONDITIONS for item in row.get("conditions", []))
    )
    if expected_total > MAX_COLLECTION_EXPECTED_POWER:
        reasons.append(
            f"整套族血的预计强度{expected_total:g}超过上限{MAX_COLLECTION_EXPECTED_POWER:g}"
        )
    return list(dict.fromkeys(reasons))


def _condition_met(condition_id: str, context: dict[str, Any]) -> bool:
    return {
        "always": True,
        "enemy_same_or_lower": float(context.get("realm_delta", 0)) >= 0,
        "enemy_higher": float(context.get("realm_delta", 0)) < 0,
        "player_state_50": float(context.get("player_state", 1)) <= 0.50,
        "player_state_30": float(context.get("player_state", 1)) <= 0.30,
        "enemy_state_40": float(context.get("enemy_state", 1)) <= 0.40,
        "player_mp_40": float(context.get("player_mp", 1)) <= 0.40,
        "player_morale_50": float(context.get("player_morale", 100)) <= 50,
        "enemy_morale_50": float(context.get("enemy_morale", 100)) <= 50,
        "terrain_open": context.get("natural_terrain") == "开阔",
        "terrain_narrow": context.get("natural_terrain") == "狭窄",
        "terrain_dangerous": context.get("natural_terrain") == "险要",
        "artificial_field": bool(context.get("artificial_conditions", [])),
        "player_first": context.get("player_first") is True,
        "enemy_first": context.get("player_first") is False,
        "control_success": context.get("controlled") is True,
        "received_12": float(context.get("received", 0)) >= 0.12,
        "dealt_15": float(context.get("dealt", 0)) >= 0.15,
    }.get(condition_id, False)


def evaluate_generated_traits(
    rules: Iterable[dict[str, Any]], *, trigger: str, context: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "player_stat_multipliers": {}, "enemy_stat_multipliers": {},
        "dealt_multiplier": 1.0, "received_multiplier": 1.0,
        "received_cap": None, "player_state_restore": 0.0,
        "player_mp_restore": 0.0, "player_morale_delta": 0.0,
        "enemy_morale_delta": 0.0, "events": [], "triggered_ids": [],
    }
    round_no = int(context.get("round_no", 0))
    for rule in rules:
        if validate_generated_trait(rule) or rule.get("trigger") != trigger:
            continue
        if not _scheduled(str(rule["schedule"]), round_no):
            continue
        if not all(_condition_met(str(item), context) for item in rule["conditions"]):
            continue
        effect = BLOODLINE_RULE_EFFECTS[str(rule["effect"])]
        kind, target, value = str(effect["kind"]), str(effect["target"]), float(effect["value"])
        if kind == "stat_multiplier":
            bucket = result[f"{target}_stat_multipliers"]
            factor = 1.0 + value if target == "player" else 1.0 - value
            bucket[effect["stat"]] = bucket.get(effect["stat"], 1.0) * factor
        elif kind == "damage_multiplier":
            key = "dealt_multiplier" if target == "enemy" else "received_multiplier"
            result[key] *= 1.0 + value if target == "enemy" else 1.0 - value
        elif kind == "damage_cap":
            result["received_cap"] = value if result["received_cap"] is None else min(result["received_cap"], value)
        elif kind == "reclaim_loss":
            result["player_state_restore"] += min(float(effect["cap"]), float(context.get("received", 0)) * value)
        elif kind == "restore_state":
            result["player_state_restore"] += value
        elif kind == "restore_mp":
            result["player_mp_restore"] += value
        elif kind == "modify_morale":
            result[f"{target}_morale_delta"] += value if target == "player" else -value
        result["events"].append(f"{rule['name']}：{rule['description']}")
        result["triggered_ids"].append(str(rule["id"]))
    # A collection may contain individually legal rules that happen to trigger
    # together. Runtime ceilings prevent multiplicative burst and recovery
    # loops without changing the saved traits.
    result["dealt_multiplier"] = min(1.18, float(result["dealt_multiplier"]))
    result["received_multiplier"] = max(0.82, float(result["received_multiplier"]))
    result["received_cap"] = (
        max(0.24, float(result["received_cap"]))
        if result["received_cap"] is not None else None
    )
    result["player_state_restore"] = min(0.06, float(result["player_state_restore"]))
    result["player_mp_restore"] = min(0.06, float(result["player_mp_restore"]))
    result["player_morale_delta"] = min(10.0, float(result["player_morale_delta"]))
    result["enemy_morale_delta"] = max(-10.0, float(result["enemy_morale_delta"]))
    for bucket_name, lower, upper in (
        ("player_stat_multipliers", 1.0, 1.16),
        ("enemy_stat_multipliers", 0.86, 1.0),
    ):
        result[bucket_name] = {
            stat: max(lower, min(upper, float(multiplier)))
            for stat, multiplier in result[bucket_name].items()
        }
    return result


def _candidate_conditions(trigger: str, effect: dict[str, Any], rng: Any) -> list[str]:
    allowed_families = _allowed_condition_families(effect)
    compatible = [
        condition_id for condition_id, definition in BLOODLINE_RULE_CONDITIONS.items()
        if (
            trigger in definition["triggers"] and condition_id != "always"
            and definition["family"] in allowed_families
        )
    ]
    first = rng.choice(compatible)
    if rng.random() >= 0.38:
        return [first]
    first_family = BLOODLINE_RULE_CONDITIONS[first]["family"]
    seconds = [item for item in compatible if BLOODLINE_RULE_CONDITIONS[item]["family"] != first_family]
    return [first, rng.choice(seconds)] if seconds else [first]


def generate_species_bloodline_trait(
    species_id: str, rng: Any, existing: Iterable[dict[str, Any]] = (),
) -> dict[str, Any] | None:
    if species_id not in SPECIES_NAMES:
        raise ValueError("未知妖族本源种")
    existing_rows = list(existing)
    if len(existing_rows) >= MAX_TRAITS:
        return None
    preferred = set(_SPECIES_EFFECT_FAMILIES[species_id])
    effect_ids = list(BLOODLINE_RULE_EFFECTS)
    weighted_effects = [
        effect_id for effect_id in effect_ids
        for _ in range(4 if BLOODLINE_RULE_EFFECTS[effect_id]["family"] in preferred else 1)
    ]
    for _attempt in range(400):
        effect_id = rng.choice(weighted_effects)
        effect = BLOODLINE_RULE_EFFECTS[effect_id]
        trigger = rng.choice(effect["triggers"])
        schedule = rng.choice(tuple(BLOODLINE_RULE_SCHEDULES))
        conditions = _candidate_conditions(trigger, effect, rng)
        bare = {
            "schema_version": SCHEMA_VERSION, "species_id": species_id,
            "trigger": trigger, "schedule": schedule,
            "conditions": conditions, "effect": effect_id,
        }
        trait_id = generated_trait_id(bare)
        raw_power, expected_power = _power(bare)
        rule = {
            **bare, "id": trait_id,
            "name": f"{SPECIES_NAMES[species_id]}·{effect['name']}",
            "description": describe_generated_trait(bare),
            "power": {"raw": raw_power, "expected": expected_power},
        }
        if not validate_generated_collection([*existing_rows, rule]):
            return rule
    return None


def public_generated_trait(rule: dict[str, Any]) -> dict[str, Any]:
    reasons = validate_generated_trait(rule)
    return {
        "id": str(rule.get("id", "")), "name": str(rule.get("name", "未知族血")),
        "description": str(rule.get("description", "")), "generated": True,
        "valid": not reasons, "invalid_reasons": reasons,
        "trigger": str(rule.get("trigger", "")), "schedule": str(rule.get("schedule", "")),
        "conditions": list(map(str, rule.get("conditions", []))), "effect": str(rule.get("effect", "")),
        "slot_id": str(rule.get("slot_id", "")),
        "power": dict(rule.get("power", {})) if isinstance(rule.get("power"), dict) else {},
    }


def validate_rule_catalog() -> None:
    if set(BLOODLINE_RULE_TRIGGERS) != {"round_start", "initiative_resolved", "before_damage", "after_damage", "round_end"}:
        raise ValueError("族血组合器触发时点注册不完整")
    for effect_id, effect in BLOODLINE_RULE_EFFECTS.items():
        if not effect["triggers"] or set(effect["triggers"]) - set(BLOODLINE_RULE_TRIGGERS):
            raise ValueError(f"族血效果 {effect_id} 的触发时点非法")
        if float(effect["power"]) > MAX_RAW_POWER:
            raise ValueError(f"族血效果 {effect_id} 超过单项硬强度上限")
    for condition_id, condition in BLOODLINE_RULE_CONDITIONS.items():
        if not condition["triggers"] or set(condition["triggers"]) - set(BLOODLINE_RULE_TRIGGERS):
            raise ValueError(f"族血条件 {condition_id} 的触发时点非法")


validate_rule_catalog()
