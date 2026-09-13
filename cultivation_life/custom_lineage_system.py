from __future__ import annotations

import copy
import re
from typing import Any

from .models import GameState, Player


STAT_KEYS = ("might", "guard", "mobility", "sense", "sustain", "breach")
SELF_NODE = re.compile(r"_NETHER_SELF_([1-4])$")


def self_lineage_stage(node_id: str | None) -> int:
    match = SELF_NODE.search(str(node_id or ""))
    return int(match.group(1)) if match else 0


def is_self_lineage_node(node_id: str | None) -> bool:
    return self_lineage_stage(node_id) > 0


def lineage_deed_budget(game: GameState, config: dict[str, Any]) -> dict[str, Any]:
    """Derive points only from the V4 whitelist; incidental player stats never count."""
    player = game.player
    rows: list[dict[str, Any]] = [{
        "id": "founder_base", "name": "立祖根基", "source": "固定",
        "points": max(0, int(config.get("founder_base_points", 0))),
        "detail": "每位立祖者固定获得，不受年龄、财富或声望影响。",
    }]
    history_ids = set(map(str, player.monster_evolution_history))
    definitions = list(config.get("deed_definitions", []))
    for deed in (row for row in definitions if row.get("kind") == "evolution"):
        if str(deed.get("evolution_id", "")) in history_ids:
            rows.append({
                "id": str(deed["id"]), "name": str(deed["name"]), "source": "特殊进化",
                "points": max(0, int(deed.get("points", 0))), "detail": str(deed.get("description", "")),
            })
    for deed in (row for row in definitions if row.get("kind") == "tribulation"):
        threshold = max(1, int(deed.get("threshold", 1)))
        if player.tribulation_count >= threshold:
            rows.append({
                "id": str(deed["id"]), "name": str(deed["name"]), "source": "渡劫里程碑",
                "points": max(0, int(deed.get("points", 0))),
                "detail": f"累计渡劫达到 {threshold} 次（只计一次）。",
            })
    for deed in (row for row in definitions if row.get("kind") == "history"):
        matched = any(
            record.event_id == deed.get("event_id")
            and (not deed.get("result") or record.result == deed.get("result"))
            and (not deed.get("choice_id") or record.choice_id == deed.get("choice_id"))
            for record in game.history
        )
        if matched:
            rows.append({
                "id": str(deed["id"]), "name": str(deed["name"]), "source": "明确事件",
                "points": max(0, int(deed.get("points", 0))), "detail": str(deed.get("description", "")),
            })
    recorded_definitions = {str(row["id"]): row for row in definitions if row.get("kind") == "recorded"}
    for deed_id, count in sorted(player.monster_lineage_deeds.items()):
        definition = recorded_definitions.get(str(deed_id))
        if not definition or count <= 0:
            continue
        cap = max(1, int(definition.get("cap", 1)))
        credited = min(cap, int(count))
        rows.append({
            "id": str(deed_id), "name": str(definition["name"]), "source": "已记录功业",
            "points": credited * max(0, int(definition.get("points", 0))),
            "detail": f"达成 {credited} 次；上限 {cap} 次。",
        })
    return {"total": sum(row["points"] for row in rows), "breakdown": rows}


def _index(config: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in config.get(key, [])}


def _value_entry(config: dict[str, Any], pool: str, raw: Any) -> dict[str, Any] | None:
    try:
        numeric = float(raw)
    except (TypeError, ValueError):
        return None
    return next(
        (row for row in config.get("values", {}).get(pool, []) if abs(float(row["value"]) - numeric) < 1e-9),
        None,
    )


def rule_cost(rule: dict[str, Any], config: dict[str, Any]) -> int:
    schedules, conditions = _index(config, "schedules"), _index(config, "conditions")
    targets, effects = _index(config, "targets"), _index(config, "effects")
    schedule = schedules.get(str(rule.get("schedule", "")))
    condition = conditions.get(str(rule.get("condition", "")))
    target = targets.get(str(rule.get("target", "")))
    effect = effects.get(str(rule.get("effect", "")))
    value = _value_entry(config, str(effect.get("value_pool", "")) if effect else "", rule.get("value"))
    if not all((schedule, condition, target, effect, value)):
        raise ValueError("自创血脉规则包含未知组件")
    return max(
        int(config.get("cost_rules", {}).get("minimum", config.get("minimum_rule_cost", 1))),
        int(schedule.get("cost", 0)) + int(effect.get("cost", 0)) + int(value.get("cost", 0))
        + int(target.get("cost", 0)) - int(condition.get("discount", 0)),
    )


def describe_rule(rule: dict[str, Any], config: dict[str, Any]) -> str:
    phase = _index(config, "phases")[rule["phase"]]
    schedule = _index(config, "schedules")[rule["schedule"]]["name"]
    condition = _index(config, "conditions")[rule["condition"]]
    target = "自身" if rule["target"] == "player" else "敌方"
    effect = _index(config, "effects")[rule["effect"]]
    value = _value_entry(config, effect["value_pool"], rule["value"])
    verb = "恢复" if effect["kind"] == "restore_combat_state" else "提高" if rule["target"] == "player" else "降低"
    timing = "开始时" if phase["id"] == "round_start" else "结束时"
    condition_text = "" if condition["kind"] == "always" else f"若{condition['name']}，"
    return f"{schedule}{timing}，{condition_text}{target}{effect['name']}{verb}{value['label']}。"


def normalize_rules(
    raw_rules: Any,
    config: dict[str, Any],
    *,
    slots: int,
    budget: int,
    existing_rules: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw_rules, list):
        raise ValueError("自创血脉规则必须为数组")
    if len(raw_rules) > slots:
        raise ValueError(f"当前立祖阶段最多铭刻 {slots} 条规则")
    phases, schedules = _index(config, "phases"), _index(config, "schedules")
    conditions, targets, effects = _index(config, "conditions"), _index(config, "targets"), _index(config, "effects")
    normalized: list[dict[str, Any]] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise ValueError("自创血脉规则格式不合法")
        rule = {key: raw.get(key) for key in ("phase", "schedule", "condition", "target", "effect", "value")}
        phase, schedule = phases.get(str(rule["phase"])), schedules.get(str(rule["schedule"]))
        condition, target = conditions.get(str(rule["condition"])), targets.get(str(rule["target"]))
        effect = effects.get(str(rule["effect"]))
        if not all((phase, schedule, condition, target, effect)):
            raise ValueError("自创血脉规则包含未知组件")
        if str(target["id"]) not in effect.get("targets", []):
            raise ValueError("这项效果不能作用于所选目标")
        if str(phase["id"]) not in effect.get("phases", []):
            raise ValueError("这项效果不能在所选时点触发")
        value = _value_entry(config, str(effect["value_pool"]), rule["value"])
        if value is None:
            raise ValueError("自创血脉规则的效果档位不合法")
        rule = {key: str(rule[key]) for key in ("phase", "schedule", "condition", "target", "effect")}
        rule["value"] = float(value["value"])
        rule["cost"] = rule_cost(rule, config)
        rule["description"] = describe_rule(rule, config)
        normalized.append(rule)
    frozen = existing_rules or []
    if len(normalized) < len(frozen):
        raise ValueError("已经铭刻的祖血规则不能删除")
    immutable_keys = ("phase", "schedule", "condition", "target", "effect", "value")
    for index, old in enumerate(frozen):
        if any(normalized[index].get(key) != old.get(key) for key in immutable_keys):
            raise ValueError("已经铭刻的祖血规则不能修改，只能在后续阶段追加")
    spent = sum(int(rule["cost"]) for rule in normalized)
    if spent > budget:
        raise ValueError(f"祖血功业点不足：需要 {spent}，当前仅有 {budget}")
    return normalized, spent


def public_custom_lineage(player: Player, config: dict[str, Any]) -> dict[str, Any] | None:
    lineage = player.monster_custom_lineage
    if not isinstance(lineage, dict):
        return None
    result = copy.deepcopy(lineage)
    result["rules"] = [dict(rule) for rule in lineage.get("rules", []) if isinstance(rule, dict)]
    result["stage_name"] = config.get("stage_names", {}).get(str(result.get("finalized_stage", 0)), "立祖")
    return result


def editor_payload(
    game: GameState,
    config: dict[str, Any],
    *,
    stage: int,
    evolution_id: str,
    retroactive: bool,
) -> dict[str, Any]:
    deeds = lineage_deed_budget(game, config)
    existing = public_custom_lineage(game.player, config)
    slots = int(config.get("rule_slots", {}).get(str(stage), 0))
    return {
        "evolution_id": evolution_id, "retroactive": retroactive, "stage": stage,
        "stage_name": config.get("stage_names", {}).get(str(stage), "立祖"),
        "slots": slots, "deeds": deeds, "existing": existing,
        "components": {
            key: copy.deepcopy(config.get(key, []))
            for key in ("phases", "schedules", "conditions", "targets", "effects")
        },
        "values": copy.deepcopy(config.get("values", {})),
        "minimum_rule_cost": int(config.get("cost_rules", {}).get("minimum", config.get("minimum_rule_cost", 1))),
        "irreversible": True,
    }


def evaluate_custom_lineage_rules(
    player: Player,
    config: dict[str, Any],
    *,
    phase: str,
    round_no: int,
    natural_terrain: str,
    artificial_conditions: list[str],
    player_state: float,
    enemy_state: float,
    player_morale: float,
    enemy_morale: float,
) -> dict[str, Any]:
    """Interpret the finite DSL. Invalid/tampered save entries are ignored safely."""
    output: dict[str, Any] = {
        "player_stat_multipliers": {}, "enemy_stat_multipliers": {},
        "player_state_delta": 0.0, "enemy_state_delta": 0.0,
        "player_morale_delta": 0.0, "enemy_morale_delta": 0.0, "events": [],
    }
    lineage = player.monster_custom_lineage
    if player.path != "monster" or not isinstance(lineage, dict):
        return output
    phases, schedules = _index(config, "phases"), _index(config, "schedules")
    conditions, targets, effects = _index(config, "conditions"), _index(config, "targets"), _index(config, "effects")
    terrain_values = {"narrow": "狭窄", "open": "开阔", "dangerous": "险要"}
    artificial_values = {"forbidden_air": "禁空", "forbidden_sense": "禁神识", "formation": "大阵"}

    def scheduled(schedule_id: str) -> bool:
        return {
            "every": True, "odd": round_no % 2 == 1, "even": round_no % 2 == 0,
            "first_two": round_no <= 2, "first_three": round_no <= 3,
            **{f"round_{number}": round_no == number for number in range(1, 6)},
        }.get(schedule_id, False)

    def condition_met(row: dict[str, Any]) -> bool:
        kind, value = row.get("kind"), row.get("value")
        if kind == "always": return True
        if kind == "terrain": return natural_terrain == terrain_values.get(str(value))
        if kind == "artificial": return artificial_values.get(str(value)) in artificial_conditions
        if kind == "state":
            actual = player_state if row.get("subject") == "player" else enemy_state
            return actual <= float(value)
        if kind == "morale":
            actual = player_morale if row.get("subject") == "player" else enemy_morale
            return actual <= float(value)
        return False

    for raw in lineage.get("rules", []):
        if not isinstance(raw, dict) or raw.get("phase") != phase or raw.get("phase") not in phases:
            continue
        schedule, condition = schedules.get(str(raw.get("schedule"))), conditions.get(str(raw.get("condition")))
        target, effect = targets.get(str(raw.get("target"))), effects.get(str(raw.get("effect")))
        if not all((schedule, condition, target, effect)) or not scheduled(str(schedule["id"])) or not condition_met(condition):
            continue
        value_row = _value_entry(config, str(effect.get("value_pool", "")), raw.get("value"))
        if value_row is None or target["id"] not in effect.get("targets", []) or phase not in effect.get("phases", []):
            continue
        value = float(value_row["value"])
        if effect["kind"] == "modify_stat" and effect.get("stat") in STAT_KEYS:
            bucket = output[f"{target['id']}_stat_multipliers"]
            factor = 1.0 + value if target["id"] == "player" else max(0.0, 1.0 - value)
            bucket[effect["stat"]] = bucket.get(effect["stat"], 1.0) * factor
        elif effect["kind"] == "restore_combat_state":
            output[f"{target['id']}_state_delta"] += value
        elif effect["kind"] == "modify_morale":
            direction = 1.0 if target["id"] == "player" else -1.0
            output[f"{target['id']}_morale_delta"] += direction * value
        output["events"].append(str(raw.get("description") or describe_rule(raw, config)))
    return output
