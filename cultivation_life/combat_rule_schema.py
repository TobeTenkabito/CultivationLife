"""Schema-v2 combat rule definitions and validation, independent of evaluators."""

from __future__ import annotations

from typing import Any


RULE_SCHEMA_VERSION = 2

MAX_HISTORY = 32

MAX_COUNTER_VALUE = 99

MAX_MARKS_PER_NAMESPACE = 32

MAX_OPERATIONS_PER_PHASE = 128

RULE_TRIGGERS = {
    "round_start": "开始时",
    "initiative_resolved": "先手确定后",
    "before_damage": "交锋结算前",
    "after_damage": "受创后",
    "round_end": "结束时",
}

RULE_SCHEDULES = {
    "every": "每轮",
    "odd": "奇数轮",
    "even": "偶数轮",
    "first": "首轮",
    "second": "第二轮",
    "third": "第三轮",
    "fourth": "第四轮",
    "fifth": "第五轮",
    "sixth": "第六轮",
    "seventh": "第七轮",
    "eighth": "第八轮",
    "last": "最后一轮",
    "penultimate": "倒数第二轮",
    "first_two": "前两轮",
    "first_three": "前三轮",
    "first_four": "前四轮",
    "last_two": "最后两轮",
    "last_three": "最后三轮",
    "after_second": "第三轮起每轮",
    "after_third": "第四轮起每轮",
    "first_and_last": "首轮与最后一轮",
    "second_and_fourth": "第二轮与第四轮",
    "random": "每场随机一轮",
    "random_two": "每场随机两轮",
}

CONDITION_NAMES = {
    "always": "没有额外限制",
    "enemy_same_or_lower": "敌方与自身同境或境界更低",
    "enemy_higher": "敌方境界高于自身",
    "player_state_50": "己方战斗态势不高于50%",
    "player_state_30": "己方战斗态势不高于30%",
    "enemy_state_40": "敌方战斗态势不高于40%",
    "player_mp_40": "己方法力不高于40%",
    "player_morale_50": "己方战意不高于50",
    "enemy_morale_50": "敌方战意不高于50",
    "terrain_open": "身处开阔战场",
    "terrain_narrow": "身处狭窄战场",
    "terrain_dangerous": "身处险要战场",
    "artificial_field": "战场存在禁制或大阵",
    "player_first": "己方取得先手",
    "enemy_first": "己方未取得先手",
    "control_success": "本轮神识压制成功",
    "received_12": "本轮态势损失达到12%",
    "dealt_15": "本轮削去敌方至少15%态势",
    "previous_player_first": "上一轮己方取得先手",
    "previous_enemy_first": "上一轮己方未取得先手",
    "previous_player_state_below_50": "上一轮结束时己方态势不高于50%",
    "previous_player_state_below_30": "上一轮结束时己方态势不高于30%",
    "previous_player_mp_below_40": "上一轮结束时己方法力不高于40%",
    "previous_received_12": "上一轮态势损失达到12%",
    "previous_dealt_15": "上一轮削去敌方至少15%态势",
}

STAT_NAMES = {
    "might": "威能",
    "guard": "防护",
    "mobility": "身法",
    "sense": "神识",
    "sustain": "续航",
    "breach": "破法",
}


def validate_rule(rule: Any) -> list[str]:
    if not isinstance(rule, dict):
        return ["规则不是对象"]
    errors: list[str] = []
    if int(rule.get("schema_version", -1)) != RULE_SCHEMA_VERSION:
        errors.append("规则版本未知")
    if str(rule.get("trigger", "")) not in RULE_TRIGGERS:
        errors.append("未知触发时点")
    if str(rule.get("schedule", "")) not in RULE_SCHEDULES:
        errors.append("未知轮次限制")
    conditions = rule.get("conditions", [])
    if not isinstance(conditions, list) or any(
        str(item) not in CONDITION_NAMES for item in conditions
    ):
        errors.append("存在未知条件")
    effect = rule.get("effect")
    if effect is not None and not isinstance(effect, dict):
        errors.append("效果格式无效")
    for operation in rule.get("runtime_operations", []):
        operation_type = str(operation.get("op", operation.get("type", "")))
        if operation_type not in {
            "counter_add",
            "counter_set",
            "counter_reset",
            "counter_consume",
            "set_mark",
            "consume_mark",
            "clear_mark",
        }:
            errors.append("未知运行时操作")
        if operation_type == "set_mark" and not (
            operation.get("ttl_rounds")
            or operation.get("expire_at_round_end")
            or any(
                str(other.get("op", other.get("type", ""))) == "consume_mark"
                and str(other.get("key", "")) == str(operation.get("key", ""))
                for other in rule.get("runtime_operations", [])
            )
        ):
            errors.append("印记缺少生命周期")
    allowed_runtime_conditions = {
        "counter_at_least",
        "counter_at_most",
        "counter_equals",
        "mark_exists",
        "mark_missing",
        "mark_stacks_at_least",
        "previous_delta_at_least",
    }
    if any(
        str(condition.get("type", "")) not in allowed_runtime_conditions
        for condition in rule.get("runtime_conditions", [])
    ):
        errors.append("未知运行时条件")
    return list(dict.fromkeys(errors))
