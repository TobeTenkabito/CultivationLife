from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterable


SCHEMA_VERSION: Final = 1

# A soul trait is assembled when a night parade begins.  These tables are a
# finite, data-only grammar: saves retain only IDs from the catalogs below, so
# loading a save never rolls the trait again and no executable expression is
# persisted.
SOUL_TRAIT_PREFIXES: Final = (
    "凝霜", "逐影", "守烛", "吞煞", "归息", "照识", "镇念", "裂魄",
)
SOUL_RULE_TRIGGERS: Final[dict[str, str]] = {
    "round_start": "轮初",
    "initiative_resolved": "先手既定时",
    "before_damage": "交锋结算前",
    "after_damage": "受创后",
    "round_end": "轮末",
}
SOUL_RULE_SCHEDULES: Final[dict[str, tuple[str, float]]] = {
    "every": ("每轮", 1.00),
    "odd": ("奇数轮", 0.55),
    "even": ("偶数轮", 0.55),
    "first_two": ("前两轮", 0.45),
    "after_second": ("第三轮起", 0.55),
}


def _condition(name: str, family: str, triggers: Iterable[str], uptime: float) -> dict[str, Any]:
    return {"name": name, "family": family, "triggers": tuple(triggers), "uptime": uptime}


_ALL_TRIGGERS = tuple(SOUL_RULE_TRIGGERS)
_AFTER_INITIATIVE = ("initiative_resolved", "before_damage", "after_damage", "round_end")
_AFTER_DAMAGE = ("after_damage", "round_end")
SOUL_RULE_CONDITIONS: Final[dict[str, dict[str, Any]]] = {
    "always": _condition("无额外条件", "always", _ALL_TRIGGERS, 1.00),
    "enemy_same_or_lower": _condition("敌方不高于自身境界", "realm", _ALL_TRIGGERS, 0.68),
    "enemy_higher": _condition("敌方境界高于自身", "realm", _ALL_TRIGGERS, 0.32),
    "player_state_50": _condition("己方态势不高于50%", "player_state", _ALL_TRIGGERS, 0.45),
    "player_state_30": _condition("己方态势不高于30%", "player_state", _ALL_TRIGGERS, 0.28),
    "enemy_state_40": _condition("敌方态势不高于40%", "enemy_state", _ALL_TRIGGERS, 0.38),
    "player_mp_40": _condition("己方法力不高于40%", "player_mp", _ALL_TRIGGERS, 0.38),
    "terrain_open": _condition("身处开阔战场", "terrain", _ALL_TRIGGERS, 0.40),
    "terrain_narrow": _condition("身处狭窄战场", "terrain", _ALL_TRIGGERS, 0.35),
    "terrain_dangerous": _condition("身处险要战场", "terrain", _ALL_TRIGGERS, 0.35),
    "artificial_field": _condition("战场存在禁制或大阵", "artificial", _ALL_TRIGGERS, 0.35),
    "player_first": _condition("己方取得先手", "initiative", _AFTER_INITIATIVE, 0.52),
    "enemy_first": _condition("己方未取得先手", "initiative", _AFTER_INITIATIVE, 0.48),
    "control_success": _condition("本轮神识压制成功", "control", ("before_damage", "after_damage", "round_end"), 0.45),
    "received_12": _condition("本轮态势损失达到12%", "received", _AFTER_DAMAGE, 0.42),
    "dealt_15": _condition("本轮削去敌方至少15%态势", "dealt", _AFTER_DAMAGE, 0.45),
}


def _effect(name: str, description: str, triggers: Iterable[str], power: float, **payload: Any) -> dict[str, Any]:
    return {"name": name, "description": description, "triggers": tuple(triggers), "power": power, **payload}


SOUL_RULE_EFFECTS: Final[dict[str, dict[str, Any]]] = {
    "might_05": _effect("振威", "本轮威能提高5%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="player", stat="might", value=0.05),
    "guard_05": _effect("护生", "本轮防护提高5%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="player", stat="guard", value=0.05),
    "mobility_05": _effect("掠影", "本轮身法提高5%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="player", stat="mobility", value=0.05),
    "sense_05": _effect("照识", "本轮神识提高5%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="player", stat="sense", value=0.05),
    "sustain_05": _effect("续烛", "本轮续航提高5%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="player", stat="sustain", value=0.05),
    "breach_05": _effect("裂罅", "本轮破法提高5%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="player", stat="breach", value=0.05),
    "enemy_guard_04": _effect("蚀甲", "本轮敌方防护降低4%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="enemy", stat="guard", value=0.04),
    "enemy_mobility_04": _effect("缚影", "本轮敌方身法降低4%", ("round_start", "initiative_resolved"), 5.0, kind="stat_multiplier", target="enemy", stat="mobility", value=0.04),
    "damage_up_06": _effect("逐伤", "本轮造成的态势损耗提高6%", ("initiative_resolved", "before_damage"), 6.0, kind="damage_multiplier", target="enemy", value=0.06),
    "damage_down_06": _effect("卸煞", "本轮受到的态势损耗降低6%", ("initiative_resolved", "before_damage"), 6.0, kind="damage_multiplier", target="player", value=0.06),
    "restore_state_02": _effect("归魂", "恢复2%最大战斗态势", ("after_damage", "round_end"), 6.0, kind="restore_state", target="player", value=0.02),
    "restore_mp_02": _effect("纳阴", "恢复2%最大法力", ("after_damage", "round_end"), 5.0, kind="restore_mp", target="player", value=0.02),
    "morale_self_4": _effect("镇念", "恢复4点己方战意", ("after_damage", "round_end"), 4.0, kind="modify_morale", target="player", value=4.0),
    "morale_enemy_4": _effect("惊魄", "额外削弱敌方4点战意", ("after_damage", "round_end"), 4.0, kind="modify_morale", target="enemy", value=4.0),
}


def _condition_met(condition_id: str, context: dict[str, Any]) -> bool:
    return {
        "always": True,
        "enemy_same_or_lower": float(context.get("realm_delta", 0)) >= 0,
        "enemy_higher": float(context.get("realm_delta", 0)) < 0,
        "player_state_50": float(context.get("player_state", 1)) <= 0.50,
        "player_state_30": float(context.get("player_state", 1)) <= 0.30,
        "enemy_state_40": float(context.get("enemy_state", 1)) <= 0.40,
        "player_mp_40": float(context.get("player_mp", 1)) <= 0.40,
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


def _scheduled(schedule_id: str, round_no: int) -> bool:
    return {
        "every": True,
        "odd": round_no % 2 == 1,
        "even": round_no % 2 == 0,
        "first_two": round_no <= 2,
        "after_second": round_no >= 3,
    }.get(schedule_id, False)


def describe_generated_soul_trait(rule: dict[str, Any]) -> str:
    schedule = SOUL_RULE_SCHEDULES[str(rule["schedule"])][0]
    trigger = SOUL_RULE_TRIGGERS[str(rule["trigger"])]
    conditions = list(map(str, rule.get("conditions", [])))
    condition_text = ""
    if conditions != ["always"]:
        condition_text = "若" + "，且".join(SOUL_RULE_CONDITIONS[item]["name"] for item in conditions) + "，"
    effect = SOUL_RULE_EFFECTS[str(rule["effect"])]
    return f"{schedule}{trigger}，{condition_text}{effect['description']}。"


def generated_soul_trait_id(rule: dict[str, Any]) -> str:
    canonical = {
        "schema_version": int(rule.get("schema_version", SCHEMA_VERSION)),
        "prefix": str(rule.get("prefix", "")),
        "trigger": str(rule.get("trigger", "")),
        "schedule": str(rule.get("schedule", "")),
        "conditions": list(map(str, rule.get("conditions", []))),
        "effect": str(rule.get("effect", "")),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return f"ghost_soul_generated_{digest}"


def validate_generated_soul_trait(rule: Any) -> list[str]:
    if not isinstance(rule, dict):
        return ["魂性不是对象"]
    reasons: list[str] = []
    if int(rule.get("schema_version", -1)) != SCHEMA_VERSION:
        reasons.append("规则版本未知")
    prefix = str(rule.get("prefix", ""))
    trigger = str(rule.get("trigger", ""))
    schedule = str(rule.get("schedule", ""))
    effect_id = str(rule.get("effect", ""))
    conditions = list(map(str, rule.get("conditions", []))) if isinstance(rule.get("conditions"), list) else []
    if prefix not in SOUL_TRAIT_PREFIXES:
        reasons.append("未知魂相")
    if trigger not in SOUL_RULE_TRIGGERS:
        reasons.append("未知触发时点")
    if schedule not in SOUL_RULE_SCHEDULES:
        reasons.append("未知轮次节律")
    if effect_id not in SOUL_RULE_EFFECTS:
        reasons.append("未知效果")
    if not 1 <= len(conditions) <= 2 or any(item not in SOUL_RULE_CONDITIONS for item in conditions):
        reasons.append("条件词条非法")
    if len(set(conditions)) != len(conditions):
        reasons.append("条件词条重复")
    if reasons:
        return list(dict.fromkeys(reasons))
    effect = SOUL_RULE_EFFECTS[effect_id]
    if trigger not in effect["triggers"]:
        reasons.append("效果无法在所选时点结算")
    if any(trigger not in SOUL_RULE_CONDITIONS[item]["triggers"] for item in conditions):
        reasons.append("条件在触发时点尚无数据")
    families = [SOUL_RULE_CONDITIONS[item]["family"] for item in conditions]
    if len(set(families)) != len(families):
        reasons.append("条件重复约束同一战斗变量")
    if "always" in conditions and (len(conditions) > 1 or schedule == "every"):
        reasons.append("无条件魂性必须带有轮次限制")
    expected_name = f"{prefix}·{effect['name']}"
    if str(rule.get("id", "")) != generated_soul_trait_id(rule):
        reasons.append("魂性ID与词条组合不一致")
    if str(rule.get("name", "")) != expected_name:
        reasons.append("魂性名称与词条组合不一致")
    if str(rule.get("description", "")) != describe_generated_soul_trait(rule):
        reasons.append("魂性描述与词条组合不一致")
    return list(dict.fromkeys(reasons))


def _candidate_conditions(trigger: str, rng: Any) -> list[str]:
    if rng.random() < 0.12:
        return ["always"]
    compatible = [
        condition_id for condition_id, definition in SOUL_RULE_CONDITIONS.items()
        if condition_id != "always" and trigger in definition["triggers"]
    ]
    first = rng.choice(compatible)
    if rng.random() >= 0.35:
        return [first]
    family = SOUL_RULE_CONDITIONS[first]["family"]
    seconds = [item for item in compatible if SOUL_RULE_CONDITIONS[item]["family"] != family]
    return [first, rng.choice(seconds)] if seconds else [first]


def generate_soul_trait(rng: Any) -> dict[str, Any]:
    for _attempt in range(200):
        prefix = rng.choice(SOUL_TRAIT_PREFIXES)
        effect_id = rng.choice(tuple(SOUL_RULE_EFFECTS))
        effect = SOUL_RULE_EFFECTS[effect_id]
        trigger = rng.choice(effect["triggers"])
        schedule = rng.choice(tuple(SOUL_RULE_SCHEDULES))
        conditions = _candidate_conditions(trigger, rng)
        bare = {
            "schema_version": SCHEMA_VERSION,
            "prefix": prefix,
            "trigger": trigger,
            "schedule": schedule,
            "conditions": conditions,
            "effect": effect_id,
        }
        rule = {
            **bare,
            "id": generated_soul_trait_id(bare),
            "name": f"{prefix}·{effect['name']}",
            "description": describe_generated_soul_trait(bare),
            "generated": True,
            "origin": "ghost_parade",
            "power": {"raw": float(effect["power"])},
        }
        if not validate_generated_soul_trait(rule):
            return rule
    raise RuntimeError("无法生成合法的百鬼夜行魂性")


def evaluate_generated_soul_traits(
    rules: Iterable[dict[str, Any]], *, trigger: str, context: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "player_stat_multipliers": {}, "enemy_stat_multipliers": {},
        "dealt_multiplier": 1.0, "received_multiplier": 1.0,
        "player_state_restore": 0.0, "player_mp_restore": 0.0,
        "player_morale_delta": 0.0, "enemy_morale_delta": 0.0,
        "events": [], "triggered_ids": [],
    }
    round_no = int(context.get("round_no", 0))
    for rule in rules:
        if validate_generated_soul_trait(rule) or rule.get("trigger") != trigger:
            continue
        if not _scheduled(str(rule["schedule"]), round_no):
            continue
        if not all(_condition_met(str(item), context) for item in rule["conditions"]):
            continue
        effect = SOUL_RULE_EFFECTS[str(rule["effect"])]
        kind, target, value = str(effect["kind"]), str(effect["target"]), float(effect["value"])
        if kind == "stat_multiplier":
            bucket = result[f"{target}_stat_multipliers"]
            factor = 1.0 + value if target == "player" else 1.0 - value
            bucket[str(effect["stat"])] = bucket.get(str(effect["stat"]), 1.0) * factor
        elif kind == "damage_multiplier":
            key = "dealt_multiplier" if target == "enemy" else "received_multiplier"
            result[key] *= 1.0 + value if target == "enemy" else 1.0 - value
        elif kind == "restore_state":
            result["player_state_restore"] += value
        elif kind == "restore_mp":
            result["player_mp_restore"] += value
        elif kind == "modify_morale":
            result[f"{target}_morale_delta"] += value if target == "player" else -value
        result["events"].append(f"{rule['name']}：{rule['description']}")
        result["triggered_ids"].append(str(rule["id"]))

    result["dealt_multiplier"] = min(1.14, float(result["dealt_multiplier"]))
    result["received_multiplier"] = max(0.86, float(result["received_multiplier"]))
    result["player_state_restore"] = min(0.05, float(result["player_state_restore"]))
    result["player_mp_restore"] = min(0.05, float(result["player_mp_restore"]))
    result["player_morale_delta"] = min(8.0, float(result["player_morale_delta"]))
    result["enemy_morale_delta"] = max(-8.0, float(result["enemy_morale_delta"]))
    for bucket_name, lower, upper in (
        ("player_stat_multipliers", 1.0, 1.12),
        ("enemy_stat_multipliers", 0.88, 1.0),
    ):
        result[bucket_name] = {
            stat: max(lower, min(upper, float(multiplier)))
            for stat, multiplier in result[bucket_name].items()
        }
    return result
