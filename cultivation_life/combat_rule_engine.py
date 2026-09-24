"""Shared finite combat-rule language and battle-local memory.

The engine deliberately accepts data only.  Rules cannot contain Python
expressions or callbacks, which keeps generated DLC content safe to freeze in
save files.  Schema-v1 bloodline rules remain supported through a compatibility
adapter; schema-v2 rules add counters, marks and previous-round conditions.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable


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
    "every": "每轮", "odd": "奇数轮", "even": "偶数轮",
    "first": "首轮", "second": "第二轮", "third": "第三轮",
    "fourth": "第四轮", "fifth": "第五轮", "sixth": "第六轮",
    "seventh": "第七轮", "eighth": "第八轮", "last": "最后一轮",
    "penultimate": "倒数第二轮", "first_two": "前两轮",
    "first_three": "前三轮", "first_four": "前四轮",
    "last_two": "最后两轮", "last_three": "最后三轮",
    "after_second": "第三轮起每轮", "after_third": "第四轮起每轮",
    "first_and_last": "首轮与最后一轮", "second_and_fourth": "第二轮与第四轮",
    "random": "每场随机一轮", "random_two": "每场随机两轮",
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
    "terrain_open": "身处开阔战场", "terrain_narrow": "身处狭窄战场",
    "terrain_dangerous": "身处险要战场", "artificial_field": "战场存在禁制或大阵",
    "player_first": "己方取得先手", "enemy_first": "己方未取得先手",
    "control_success": "本轮神识压制成功",
    "received_12": "本轮态势损失达到12%", "dealt_15": "本轮削去敌方至少15%态势",
    "previous_player_first": "上一轮己方取得先手",
    "previous_enemy_first": "上一轮己方未取得先手",
    "previous_player_state_below_50": "上一轮结束时己方态势不高于50%",
    "previous_player_state_below_30": "上一轮结束时己方态势不高于30%",
    "previous_player_mp_below_40": "上一轮结束时己方法力不高于40%",
    "previous_received_12": "上一轮态势损失达到12%",
    "previous_dealt_15": "上一轮削去敌方至少15%态势",
}
STAT_NAMES = {
    "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
}


def empty_rule_result() -> dict[str, Any]:
    return {
        "player_stat_multipliers": {}, "enemy_stat_multipliers": {},
        "dealt_multiplier": 1.0, "received_multiplier": 1.0,
        "received_cap": None, "player_state_restore": 0.0,
        "player_mp_restore": 0.0, "player_morale_delta": 0.0,
        "enemy_morale_delta": 0.0, "events": [], "triggered_ids": [],
    }


@dataclass
class BattleRuleRuntime:
    """Bounded state shared by finite rules for one combat only."""

    max_rounds: int
    round_no: int = 0
    previous: dict[str, dict[str, Any]] = field(default_factory=dict)
    current: dict[str, dict[str, Any]] = field(default_factory=dict)
    round_start: dict[str, dict[str, Any]] = field(default_factory=dict)
    counters: dict[str, dict[str, int]] = field(default_factory=dict)
    marks: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    _phase_key: tuple[int, str, str] | None = None
    _phase_executed: set[str] = field(default_factory=set)
    _phase_operations: int = 0

    def begin_round(self, round_no: int, snapshots: dict[str, dict[str, Any]]) -> None:
        self.round_no = int(round_no)
        self.round_start = copy.deepcopy(snapshots)
        self.current = copy.deepcopy(snapshots)
        for namespace_marks in self.marks.values():
            for key, mark in list(namespace_marks.items()):
                if int(mark.get("expires_after_round", self.round_no)) < self.round_no:
                    del namespace_marks[key]

    def begin_phase(self, side: str, trigger: str, context: dict[str, Any]) -> None:
        key = (self.round_no, str(side), str(trigger))
        if key != self._phase_key:
            self._phase_key = key
            self._phase_executed.clear()
            self._phase_operations = 0
        self.current[str(side)] = copy.deepcopy(context)

    def finish_round(self, snapshots: dict[str, dict[str, Any]]) -> None:
        for side, snapshot in snapshots.items():
            start = self.round_start.get(side, {})
            row = copy.deepcopy(snapshot)
            row.update({
                "player_state_lost": max(0.0, float(start.get("player_state", 0)) - float(snapshot.get("player_state", 0))),
                "player_state_restored": max(0.0, float(snapshot.get("player_state", 0)) - float(start.get("player_state", 0))),
                "player_mp_spent": max(0.0, float(start.get("player_mp", 0)) - float(snapshot.get("player_mp", 0))),
                "player_mp_restored": max(0.0, float(snapshot.get("player_mp", 0)) - float(start.get("player_mp", 0))),
                "player_morale_lost": max(0.0, float(start.get("player_morale", 0)) - float(snapshot.get("player_morale", 0))),
                "player_morale_gained": max(0.0, float(snapshot.get("player_morale", 0)) - float(start.get("player_morale", 0))),
            })
            self.previous[side] = row
            self.current[side] = copy.deepcopy(snapshot)
        self.history.append({"round": self.round_no, "sides": copy.deepcopy(self.previous)})
        if len(self.history) > MAX_HISTORY:
            del self.history[:-MAX_HISTORY]

    @staticmethod
    def namespace(side: str, rule: dict[str, Any]) -> str:
        source = str(rule.get("source_id") or rule.get("namespace") or rule.get("id") or "anonymous")
        return f"{side}:{source}"

    def counter(self, namespace: str, key: str) -> int:
        return int(self.counters.get(namespace, {}).get(key, 0))

    def mark(self, namespace: str, key: str) -> dict[str, Any] | None:
        return self.marks.get(namespace, {}).get(key)

    def apply_operations(self, side: str, rule: dict[str, Any]) -> None:
        namespace = self.namespace(side, rule)
        counters = self.counters.setdefault(namespace, {})
        marks = self.marks.setdefault(namespace, {})
        for operation in rule.get("runtime_operations", []):
            if self._phase_operations >= MAX_OPERATIONS_PER_PHASE:
                break
            self._phase_operations += 1
            op = str(operation.get("op", operation.get("type", "")))
            key = str(operation.get("key", ""))
            if not key:
                continue
            if op == "counter_add":
                maximum = min(MAX_COUNTER_VALUE, max(1, int(operation.get("max", MAX_COUNTER_VALUE))))
                counters[key] = min(maximum, max(0, counters.get(key, 0) + int(operation.get("value", 1))))
            elif op == "counter_set":
                counters[key] = min(MAX_COUNTER_VALUE, max(0, int(operation.get("value", 0))))
            elif op == "counter_reset":
                counters[key] = 0
            elif op == "counter_consume":
                counters[key] = max(0, counters.get(key, 0) - max(0, int(operation.get("value", 1))))
            elif op == "set_mark" and (key in marks or len(marks) < MAX_MARKS_PER_NAMESPACE):
                ttl = 0 if operation.get("expire_at_round_end") else max(1, min(8, int(operation.get("ttl_rounds", 1))))
                old_stacks = int(marks.get(key, {}).get("stacks", 0))
                stacks = min(max(1, int(operation.get("max_stacks", 1))), old_stacks + int(operation.get("stacks", 1)))
                marks[key] = {"stacks": stacks, "source": str(rule.get("id", "")), "expires_after_round": self.round_no + ttl}
            elif op == "consume_mark":
                if key in marks:
                    consume = max(1, int(operation.get("stacks", 1)))
                    marks[key]["stacks"] = int(marks[key].get("stacks", 1)) - consume
                    if marks[key]["stacks"] <= 0:
                        del marks[key]
            elif op == "clear_mark":
                marks.pop(key, None)


def _fallback_random_rounds(rule: dict[str, Any], max_rounds: int, count: int) -> tuple[int, ...]:
    digest = hashlib.sha256(f"{rule.get('id')}:{max_rounds}:schedule".encode()).digest()
    available = list(range(1, max_rounds + 1))
    picked: list[int] = []
    for offset in range(min(count, max_rounds)):
        index = int.from_bytes(digest[offset * 2:offset * 2 + 2], "big") % len(available)
        picked.append(available.pop(index))
    return tuple(sorted(picked))


def prepare_rules(rules: Iterable[dict[str, Any]], *, max_rounds: int, rng: Any) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    maximum = max(1, int(max_rounds))
    for raw in rules:
        rule = copy.deepcopy(raw)
        rule["_battle_max_rounds"] = maximum
        count = 1 if rule.get("schedule") == "random" else 2 if rule.get("schedule") == "random_two" else 0
        if count:
            rule["_battle_random_rounds"] = sorted(rng.sample(range(1, maximum + 1), min(count, maximum)))
        prepared.append(rule)
    return prepared


def _scheduled(rule: dict[str, Any], round_no: int, max_rounds: int) -> bool:
    schedule = str(rule.get("schedule", "every"))
    random_rounds = tuple(map(int, rule.get("_battle_random_rounds", ())))
    if schedule in {"random", "random_two"} and not random_rounds:
        random_rounds = _fallback_random_rounds(rule, max_rounds, 1 if schedule == "random" else 2)
    return {
        "every": True, "odd": round_no % 2 == 1, "even": round_no % 2 == 0,
        "first": round_no == 1, "second": round_no == 2, "third": round_no == 3,
        "fourth": round_no == 4, "fifth": round_no == 5, "sixth": round_no == 6,
        "seventh": round_no == 7, "eighth": round_no == 8,
        "last": round_no == max_rounds, "penultimate": round_no == max(1, max_rounds - 1),
        "first_two": round_no <= 2, "first_three": round_no <= 3, "first_four": round_no <= 4,
        "last_two": round_no >= max(1, max_rounds - 1), "last_three": round_no >= max(1, max_rounds - 2),
        "after_second": round_no >= 3, "after_third": round_no >= 4,
        "first_and_last": round_no in {1, max_rounds}, "second_and_fourth": round_no in {2, 4},
        "random": round_no in random_rounds, "random_two": round_no in random_rounds,
    }.get(schedule, False)


def _condition_met(condition: str, context: dict[str, Any], previous: dict[str, Any]) -> bool:
    return {
        "always": True,
        "enemy_same_or_lower": float(context.get("realm_delta", 0)) >= 0,
        "enemy_higher": float(context.get("realm_delta", 0)) < 0,
        "player_state_50": float(context.get("player_state", 1)) <= .50,
        "player_state_30": float(context.get("player_state", 1)) <= .30,
        "enemy_state_40": float(context.get("enemy_state", 1)) <= .40,
        "player_mp_40": float(context.get("player_mp", 1)) <= .40,
        "player_morale_50": float(context.get("player_morale", 100)) <= 50,
        "enemy_morale_50": float(context.get("enemy_morale", 100)) <= 50,
        "terrain_open": context.get("natural_terrain") == "开阔",
        "terrain_narrow": context.get("natural_terrain") == "狭窄",
        "terrain_dangerous": context.get("natural_terrain") == "险要",
        "artificial_field": bool(context.get("artificial_conditions")),
        "player_first": context.get("player_first") is True,
        "enemy_first": context.get("player_first") is False,
        "control_success": context.get("controlled") is True,
        "received_12": float(context.get("received", 0)) >= .12,
        "dealt_15": float(context.get("dealt", 0)) >= .15,
        "previous_player_first": previous.get("player_first") is True,
        "previous_enemy_first": previous.get("player_first") is False,
        "previous_player_state_below_50": float(previous.get("player_state", 1)) <= .50,
        "previous_player_state_below_30": float(previous.get("player_state", 1)) <= .30,
        "previous_player_mp_below_40": float(previous.get("player_mp", 1)) <= .40,
        "previous_received_12": float(previous.get("received", 0)) >= .12,
        "previous_dealt_15": float(previous.get("dealt", 0)) >= .15,
    }.get(condition, False)


def _runtime_conditions_met(runtime: BattleRuleRuntime, side: str, rule: dict[str, Any]) -> bool:
    namespace = runtime.namespace(side, rule)
    for condition in rule.get("runtime_conditions", []):
        kind = str(condition.get("type", ""))
        key = str(condition.get("key", ""))
        numeric_value = float(condition.get("value", 0))
        value = int(numeric_value)
        counter = runtime.counter(namespace, key)
        mark = runtime.mark(namespace, key)
        if kind == "counter_at_least" and counter < value:
            return False
        if kind == "counter_at_most" and counter > value:
            return False
        if kind == "counter_equals" and counter != value:
            return False
        if kind == "mark_exists" and mark is None:
            return False
        if kind == "mark_missing" and mark is not None:
            return False
        if kind == "mark_stacks_at_least" and int((mark or {}).get("stacks", 0)) < value:
            return False
        if kind == "previous_delta_at_least":
            previous = runtime.previous.get(side, {})
            allowed = {
                "player_morale_lost", "player_morale_gained", "player_state_lost",
                "player_state_restored", "player_mp_spent", "player_mp_restored",
            }
            if key not in allowed or float(previous.get(key, 0)) < numeric_value:
                return False
    return True


def _apply_effect(result: dict[str, Any], effect: dict[str, Any], scale: float) -> None:
    kind = str(effect.get("kind", ""))
    target = str(effect.get("target", "player"))
    value = float(effect.get("value", 0)) * scale
    if kind == "stat_multiplier":
        bucket = result[f"{target}_stat_multipliers"]
        factor = 1 + value if target == "player" else 1 - value
        stat = str(effect["stat"])
        bucket[stat] = bucket.get(stat, 1.0) * factor
    elif kind == "damage_multiplier":
        key = "dealt_multiplier" if target == "enemy" else "received_multiplier"
        result[key] *= 1 + value if target == "enemy" else 1 - value
    elif kind == "damage_cap":
        cap = 1 - (1 - float(effect.get("value", 1))) * scale
        result["received_cap"] = cap if result["received_cap"] is None else min(result["received_cap"], cap)
    elif kind == "reclaim_loss":
        result["player_state_restore"] += min(float(effect.get("cap", .04)) * scale, value)
    elif kind == "restore_state":
        result["player_state_restore"] += value
    elif kind == "restore_mp":
        result["player_mp_restore"] += value
    elif kind == "modify_morale":
        result[f"{target}_morale_delta"] += value if target == "player" else -value


def _merge_results(base: dict[str, Any], extra: dict[str, Any]) -> None:
    for bucket_name in ("player_stat_multipliers", "enemy_stat_multipliers"):
        for stat, multiplier in extra[bucket_name].items():
            base[bucket_name][stat] = base[bucket_name].get(stat, 1.0) * float(multiplier)
    base["dealt_multiplier"] *= float(extra["dealt_multiplier"])
    base["received_multiplier"] *= float(extra["received_multiplier"])
    if extra["received_cap"] is not None:
        base["received_cap"] = extra["received_cap"] if base["received_cap"] is None else min(base["received_cap"], extra["received_cap"])
    for key in ("player_state_restore", "player_mp_restore", "player_morale_delta", "enemy_morale_delta"):
        base[key] += float(extra[key])
    base["events"].extend(extra["events"])
    base["triggered_ids"].extend(extra["triggered_ids"])


def _cap_result(result: dict[str, Any]) -> dict[str, Any]:
    result["dealt_multiplier"] = min(1.48, float(result["dealt_multiplier"]))
    result["received_multiplier"] = max(.52, float(result["received_multiplier"]))
    if result["received_cap"] is not None:
        result["received_cap"] = max(.06, float(result["received_cap"]))
    result["player_state_restore"] = min(.12, float(result["player_state_restore"]))
    result["player_mp_restore"] = min(.12, float(result["player_mp_restore"]))
    result["player_morale_delta"] = min(24.0, float(result["player_morale_delta"]))
    result["enemy_morale_delta"] = max(-24.0, float(result["enemy_morale_delta"]))
    result["player_stat_multipliers"] = {key: min(1.48, float(value)) for key, value in result["player_stat_multipliers"].items()}
    result["enemy_stat_multipliers"] = {key: max(.68, float(value)) for key, value in result["enemy_stat_multipliers"].items()}
    return result


def evaluate_rules(
    rules: Iterable[dict[str, Any]], *, trigger: str, context: dict[str, Any],
    runtime: BattleRuleRuntime | None = None, side: str = "player",
) -> dict[str, Any]:
    """Evaluate legacy and stateful rules through one public entry point."""
    rows = list(rules)
    result = empty_rule_result()
    legacy = [row for row in rows if int(row.get("schema_version", 1)) < RULE_SCHEMA_VERSION]
    if legacy:
        from .monster_bloodline_rules import evaluate_generated_traits
        _merge_results(result, evaluate_generated_traits(legacy, trigger=trigger, context=context))
    stateful = [row for row in rows if int(row.get("schema_version", 1)) >= RULE_SCHEMA_VERSION]
    if not stateful:
        return _cap_result(result)
    local_runtime = runtime or BattleRuleRuntime(max_rounds=int(context.get("max_rounds", 5)))
    if local_runtime.round_no != int(context.get("round_no", 0)):
        local_runtime.round_no = int(context.get("round_no", 0))
    local_runtime.begin_phase(side, trigger, context)
    previous = local_runtime.previous.get(side, {})
    maximum = max(1, int(context.get("max_rounds", local_runtime.max_rounds)))
    for rule in stateful:
        rule_id = str(rule.get("id", ""))
        execution_key = f"{side}:{rule_id}"
        if execution_key in local_runtime._phase_executed:
            continue
        if rule.get("trigger") != trigger or not _scheduled(rule, int(context.get("round_no", 0)), maximum):
            continue
        if not all(_condition_met(str(condition), context, previous) for condition in rule.get("conditions", ["always"])):
            continue
        if not _runtime_conditions_met(local_runtime, side, rule):
            continue
        local_runtime._phase_executed.add(execution_key)
        effect = rule.get("effect")
        if isinstance(effect, dict):
            _apply_effect(result, effect, max(0.0, min(1.20, float(rule.get("effect_scale", 1.0)))))
        local_runtime.apply_operations(side, rule)
        result["triggered_ids"].append(rule_id)
        result["events"].append(f"{rule.get('display_name', rule.get('name', '无名器理'))}：{describe_rule(rule)}")
    return _cap_result(result)


def describe_rule(rule: dict[str, Any]) -> str:
    if rule.get("description"):
        return str(rule["description"])
    schedule = RULE_SCHEDULES.get(str(rule.get("schedule", "every")), "每轮")
    trigger = RULE_TRIGGERS.get(str(rule.get("trigger", "round_start")), "触发时")
    conditions = [str(item) for item in rule.get("conditions", []) if str(item) != "always"]
    condition_text = "若" + "，且".join(CONDITION_NAMES.get(item, item) for item in conditions) + "，" if conditions else ""
    effect = rule.get("effect", {})
    if not isinstance(effect, dict):
        return f"{schedule}{trigger}，{condition_text}引动器理。"
    kind, target, value = str(effect.get("kind", "")), str(effect.get("target", "player")), float(effect.get("value", 0))
    if kind == "stat_multiplier":
        owner, verb = ("自身", "提高") if target == "player" else ("敌方", "降低")
        body = f"{owner}{STAT_NAMES.get(str(effect.get('stat')), str(effect.get('stat')))}{verb}{value:.0%}"
    elif kind == "damage_multiplier":
        body = f"造成的态势损耗提高{value:.0%}" if target == "enemy" else f"受到的态势损耗降低{value:.0%}"
    elif kind == "restore_state":
        body = f"恢复{value:.0%}最大战斗态势"
    elif kind == "restore_mp":
        body = f"恢复{value:.0%}最大法力"
    elif kind == "modify_morale":
        body = f"恢复{value:g}点己方战意" if target == "player" else f"削弱敌方{value:g}点战意"
    elif kind == "damage_cap":
        body = f"使本轮战斗态势损失不超过{value:.0%}"
    else:
        body = "改变战局"
    return f"{schedule}{trigger}，{condition_text}{body}。"


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
    if not isinstance(conditions, list) or any(str(item) not in CONDITION_NAMES for item in conditions):
        errors.append("存在未知条件")
    effect = rule.get("effect")
    if effect is not None and not isinstance(effect, dict):
        errors.append("效果格式无效")
    for operation in rule.get("runtime_operations", []):
        operation_type = str(operation.get("op", operation.get("type", "")))
        if operation_type not in {
            "counter_add", "counter_set", "counter_reset", "counter_consume",
            "set_mark", "consume_mark", "clear_mark",
        }:
            errors.append("未知运行时操作")
        if operation_type == "set_mark" and not (
            operation.get("ttl_rounds") or operation.get("expire_at_round_end")
            or any(
                str(other.get("op", other.get("type", ""))) == "consume_mark"
                and str(other.get("key", "")) == str(operation.get("key", ""))
                for other in rule.get("runtime_operations", [])
            )
        ):
            errors.append("印记缺少生命周期")
    allowed_runtime_conditions = {
        "counter_at_least", "counter_at_most", "counter_equals", "mark_exists",
        "mark_missing", "mark_stacks_at_least", "previous_delta_at_least",
    }
    if any(str(condition.get("type", "")) not in allowed_runtime_conditions for condition in rule.get("runtime_conditions", [])):
        errors.append("未知运行时条件")
    return list(dict.fromkeys(errors))
