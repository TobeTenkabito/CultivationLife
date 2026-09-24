"""Theme-first gameplay generator for Tianji artifacts.

Power and rank are intentionally absent from every public function in this
module.  A caller can change an artifact's base power without changing its
blueprint, rule count or compiled combat rules.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .combat_rule_engine import describe_rule, validate_rule


GAMEPLAY_SCHEMA_VERSION = 1

AXIS_NAMES = {
    "initiative": "先后手", "combat_state": "战斗态势", "morale": "战意",
    "mana": "法力", "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
    "realm_delta": "境界差", "damage_exchange": "攻防交换", "terrain": "地形",
    "artificial_field": "禁制阵势", "group_relation": "敌我关系",
    "status_interaction": "状态交互",
}
ARCHETYPE_NAMES = {
    "burst": "爆发", "growth": "递增", "counter": "反制", "conversion": "转化",
    "steady": "稳态", "suppression": "压制", "adversity": "逆境",
    "dual_mode": "双相", "threshold": "阈值", "charge": "蓄势",
    "chain": "连锁", "reversal": "翻转",
}
CADENCE_NAMES = {"opening": "开局", "sustained": "持续", "endgame": "终盘", "periodic": "周期"}

# Group relation remains in the public catalog but is disabled until the base
# combat context has stable multi-target identity and allegiance information.
ENABLED_PRIMARY_AXES = tuple(axis for axis in AXIS_NAMES if axis != "group_relation")
ARCHETYPES = tuple(ARCHETYPE_NAMES)
CADENCES = tuple(CADENCE_NAMES)

AXIS_COMPATIBILITY = {
    "initiative": ("combat_state", "morale", "damage_exchange", "mobility"),
    "combat_state": ("guard", "sustain", "damage_exchange", "morale"),
    "morale": ("combat_state", "might", "damage_exchange", "initiative"),
    "mana": ("sustain", "sense", "breach", "combat_state"),
    "might": ("damage_exchange", "breach", "initiative", "morale"),
    "guard": ("combat_state", "sustain", "damage_exchange", "terrain"),
    "mobility": ("initiative", "breach", "damage_exchange", "sense"),
    "sense": ("initiative", "status_interaction", "mana", "breach"),
    "sustain": ("combat_state", "mana", "guard", "morale"),
    "breach": ("damage_exchange", "initiative", "sense", "might"),
    "realm_delta": ("combat_state", "damage_exchange", "might", "guard"),
    "damage_exchange": ("combat_state", "might", "guard", "morale"),
    "terrain": ("guard", "mobility", "sense", "damage_exchange"),
    "artificial_field": ("sense", "breach", "guard", "mana"),
    "status_interaction": ("sense", "breach", "initiative", "damage_exchange"),
}

FLAVOR_AXIS_PREFERENCES = {
    "thunder": ("initiative", "mobility", "breach"),
    "soul": ("sense", "morale", "status_interaction"),
    "star": ("initiative", "realm_delta", "sense"),
    "void": ("mobility", "breach", "artificial_field"),
    "flame": ("might", "damage_exchange", "burst"),
    "frost": ("guard", "combat_state", "terrain"),
    "life": ("sustain", "combat_state", "mana"),
    "slaughter": ("might", "damage_exchange", "morale"),
}

AXIS_EFFECTS: dict[str, tuple[dict[str, Any], ...]] = {
    "initiative": (
        {"kind": "stat_multiplier", "target": "player", "stat": "mobility", "value": .07, "core": "抢机"},
        {"kind": "damage_multiplier", "target": "enemy", "value": .07, "core": "争先"},
    ),
    "combat_state": (
        {"kind": "restore_state", "target": "player", "value": .025, "core": "回势"},
        {"kind": "stat_multiplier", "target": "player", "stat": "guard", "value": .07, "core": "守元"},
    ),
    "morale": (
        {"kind": "modify_morale", "target": "player", "value": 5.0, "core": "振魄"},
        {"kind": "modify_morale", "target": "enemy", "value": 5.0, "core": "慑心"},
    ),
    "mana": (
        {"kind": "restore_mp", "target": "player", "value": .025, "core": "纳灵"},
        {"kind": "stat_multiplier", "target": "player", "stat": "sustain", "value": .07, "core": "法海"},
    ),
    "might": ({"kind": "stat_multiplier", "target": "player", "stat": "might", "value": .08, "core": "神威"},),
    "guard": ({"kind": "stat_multiplier", "target": "player", "stat": "guard", "value": .08, "core": "镇守"},),
    "mobility": ({"kind": "stat_multiplier", "target": "player", "stat": "mobility", "value": .08, "core": "遁空"},),
    "sense": ({"kind": "stat_multiplier", "target": "player", "stat": "sense", "value": .08, "core": "照神"},),
    "sustain": (
        {"kind": "stat_multiplier", "target": "player", "stat": "sustain", "value": .08, "core": "归元"},
        {"kind": "restore_state", "target": "player", "value": .02, "core": "生息"},
    ),
    "breach": (
        {"kind": "stat_multiplier", "target": "player", "stat": "breach", "value": .08, "core": "破界"},
        {"kind": "stat_multiplier", "target": "enemy", "stat": "guard", "value": .06, "core": "蚀甲"},
    ),
    "realm_delta": (
        {"kind": "damage_multiplier", "target": "enemy", "value": .08, "core": "越境"},
        {"kind": "stat_multiplier", "target": "player", "stat": "guard", "value": .07, "core": "衡岳"},
    ),
    "damage_exchange": (
        {"kind": "damage_multiplier", "target": "enemy", "value": .08, "core": "猎伤"},
        {"kind": "damage_multiplier", "target": "player", "value": .08, "core": "卸力"},
    ),
    "terrain": (
        {"kind": "stat_multiplier", "target": "player", "stat": "guard", "value": .08, "core": "地脉"},
        {"kind": "stat_multiplier", "target": "player", "stat": "mobility", "value": .08, "core": "借势"},
    ),
    "artificial_field": (
        {"kind": "stat_multiplier", "target": "player", "stat": "sense", "value": .08, "core": "解阵"},
        {"kind": "stat_multiplier", "target": "player", "stat": "breach", "value": .08, "core": "破禁"},
    ),
    "status_interaction": (
        {"kind": "damage_multiplier", "target": "enemy", "value": .08, "core": "乘隙"},
        {"kind": "stat_multiplier", "target": "enemy", "stat": "sense", "value": .06, "core": "乱识"},
    ),
}


def _weighted_choice(rng: Any, values: tuple[str, ...], preferred: tuple[str, ...]) -> str:
    pool = [*values, *(item for item in preferred for _ in range(2) if item in values)]
    return str(rng.choice(pool))


def generate_gameplay_blueprint(
    *, blueprint_rng: Any, axis_count_rng: Any, archetype_rng: Any,
    cadence_rng: Any, flavor_theme_id: str,
) -> dict[str, Any]:
    preferred = tuple(item for item in FLAVOR_AXIS_PREFERENCES.get(flavor_theme_id, ()) if item in ENABLED_PRIMARY_AXES)
    primary = _weighted_choice(blueprint_rng, ENABLED_PRIMARY_AXES, preferred)
    roll = axis_count_rng.random()
    axis_count = 1 if roll < .56 else 2 if roll < .90 else 3
    compatible = list(AXIS_COMPATIBILITY.get(primary, ()))
    axis_count = min(axis_count, 1 + len(compatible))
    secondaries = axis_count_rng.sample(compatible, axis_count - 1) if axis_count > 1 else []
    archetype = str(archetype_rng.choice(ARCHETYPES))
    cadence = str(cadence_rng.choice(CADENCES))
    frozen: dict[str, Any] = {}
    all_axes = {primary, *secondaries}
    if "initiative" in all_axes:
        frozen["initiative_side"] = blueprint_rng.choice(("player_first", "enemy_first"))
    if "terrain" in all_axes:
        frozen["terrain"] = blueprint_rng.choice(("terrain_open", "terrain_narrow", "terrain_dangerous"))
    if "combat_state" in all_axes:
        frozen["state_threshold"] = blueprint_rng.choice((.30, .50))
    if "morale" in all_axes:
        frozen["morale_side"] = blueprint_rng.choice(("player_morale_50", "enemy_morale_50"))
    if "realm_delta" in all_axes:
        frozen["realm_relation"] = blueprint_rng.choice(("enemy_higher", "enemy_same_or_lower"))
    if "damage_exchange" in all_axes:
        frozen["damage_relation"] = blueprint_rng.choice(("received_12", "dealt_15"))
    blueprint_id = f"{primary}.{archetype}.{cadence}.{'-'.join(secondaries) or 'single'}"
    tendency = f"以{AXIS_NAMES[primary]}为核心的{ARCHETYPE_NAMES[archetype]}流派"
    if secondaries:
        tendency += "，并借" + "、".join(AXIS_NAMES[item] for item in secondaries) + "形成联动"
    tendency += f"，偏向{CADENCE_NAMES[cadence]}阶段发力。"
    return {
        "schema_version": GAMEPLAY_SCHEMA_VERSION,
        "blueprint_id": blueprint_id, "primary_axis": primary,
        "secondary_axes": secondaries, "archetype": archetype, "cadence": cadence,
        "frozen_parameters": frozen, "axis_count": axis_count,
        "stateful": archetype in {"growth", "counter", "charge", "chain", "reversal"},
        "tendency": tendency,
    }


def sample_total_effect_count(rng: Any) -> int:
    count = 1
    while rng.random() < .72:
        count += 1
    return count


def _axis_condition(axis: str, frozen: dict[str, Any]) -> str:
    if axis == "initiative":
        return str(frozen.get("initiative_side", "player_first"))
    if axis == "combat_state":
        return "player_state_30" if float(frozen.get("state_threshold", .50)) <= .30 else "player_state_50"
    if axis == "morale":
        return str(frozen.get("morale_side", "player_morale_50"))
    if axis == "mana":
        return "player_mp_40"
    if axis == "realm_delta":
        return str(frozen.get("realm_relation", "enemy_higher"))
    if axis == "damage_exchange":
        return str(frozen.get("damage_relation", "received_12"))
    if axis == "terrain":
        return str(frozen.get("terrain", "terrain_open"))
    if axis == "artificial_field":
        return "artificial_field"
    if axis == "status_interaction":
        return "control_success"
    return "always"


def _trigger_for(conditions: list[str], rng: Any) -> str:
    if any(condition in {"received_12", "dealt_15"} for condition in conditions):
        return str(rng.choice(("after_damage", "round_end")))
    if any(condition in {"player_first", "enemy_first", "control_success"} for condition in conditions):
        return str(rng.choice(("initiative_resolved", "before_damage", "after_damage", "round_end")))
    return str(rng.choice(("round_start", "initiative_resolved", "before_damage", "after_damage", "round_end")))


def _schedule_for(cadence: str, rng: Any) -> str:
    pools = {
        "opening": ("first", "second", "third", "first_two", "first_three", "first_and_last"),
        "sustained": ("every", "after_second", "odd", "even", "fourth"),
        "endgame": ("last", "last_two", "last_three", "penultimate", "after_third", "fourth"),
        "periodic": ("odd", "even", "random", "random_two", "second_and_fourth", "second", "third", "fourth"),
    }
    return str(rng.choice(pools[cadence]))


def _scaled_effect(raw: dict[str, Any], restriction_count: int, archetype: str) -> dict[str, Any]:
    effect = {key: copy.deepcopy(value) for key, value in raw.items() if key != "core"}
    generosity = max(1, restriction_count)
    if archetype in {"burst", "threshold", "charge"}:
        generosity += 1
    effect["value"] = round(float(effect["value"]) * generosity, 6)
    return effect


def _stable_rule_id(source_id: str, payload: dict[str, Any], index: int) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{source_id}:{index}:{encoded}".encode()).hexdigest()[:16]
    return f"tianji-rule-{digest}"


def compile_theme_rules(
    blueprint: dict[str, Any], *, rule_count: int, rng: Any, source_id: str,
) -> list[dict[str, Any]]:
    """Compile exactly ``rule_count`` coherent rules (with no hard ceiling)."""
    if rule_count <= 0:
        return []
    primary = str(blueprint["primary_axis"])
    secondaries = list(map(str, blueprint.get("secondary_axes", [])))
    axes = [primary, *secondaries]
    frozen = dict(blueprint.get("frozen_parameters", {}))
    archetype = str(blueprint["archetype"])
    cadence = str(blueprint["cadence"])
    rules: list[dict[str, Any]] = []
    counter_key = f"{archetype}_stacks"
    mark_key = f"{primary}_opening"
    for index in range(rule_count):
        axis = axes[index % len(axes)]
        core_condition = _axis_condition(primary if index % 3 else axis, frozen)
        condition_candidates = [core_condition, *(_axis_condition(item, frozen) for item in axes)]
        previous_map = {
            "player_first": "previous_player_first", "enemy_first": "previous_enemy_first",
            "player_state_50": "previous_player_state_below_50",
            "player_state_30": "previous_player_state_below_30",
            "player_mp_40": "previous_player_mp_below_40",
            "received_12": "previous_received_12", "dealt_15": "previous_dealt_15",
        }
        if archetype in {"growth", "counter", "adversity", "threshold", "charge", "chain"}:
            condition_candidates.extend(
                previous_map[item] for item in tuple(condition_candidates) if item in previous_map
            )
        unique_candidates = list(dict.fromkeys(item for item in condition_candidates if item != "always"))
        target_conditions = min(4, 1 + index % 4)
        conditions = unique_candidates[:target_conditions] or ["always"]
        if archetype == "dual_mode" and primary == "initiative" and index % 2 == 1:
            original = str(frozen.get("initiative_side", "player_first"))
            opposite = "enemy_first" if original == "player_first" else "player_first"
            conditions = [opposite if item == original else item for item in conditions]
        trigger = _trigger_for(conditions, rng)
        schedule = _schedule_for(cadence, rng)
        runtime_conditions: list[dict[str, Any]] = []
        runtime_operations: list[dict[str, Any]] = []

        # Stateful archetypes use a shared source namespace.  Slot rotation
        # creates setup/payoff/transition rules even for very long tails.
        slot = index % 4
        if archetype == "growth":
            if slot in {0, 3}:
                runtime_operations.append({"op": "counter_add", "key": counter_key, "value": 1, "max": 5})
            else:
                runtime_conditions.append({"type": "counter_at_least", "key": counter_key, "value": 1 + (index % 3)})
        elif archetype == "charge":
            if slot in {0, 1}:
                runtime_operations.append({"op": "counter_add", "key": counter_key, "value": 1, "max": 6})
            else:
                runtime_conditions.append({"type": "counter_at_least", "key": counter_key, "value": 3})
                runtime_operations.append({"op": "counter_consume", "key": counter_key, "value": 3})
        elif archetype == "chain":
            if slot in {0, 2}:
                runtime_operations.append({"op": "set_mark", "key": mark_key, "stacks": 1, "max_stacks": 2, "ttl_rounds": 1})
            else:
                runtime_conditions.append({"type": "mark_exists", "key": mark_key})
                runtime_operations.append({"op": "consume_mark", "key": mark_key, "stacks": 1})
        elif archetype == "counter" and slot in {1, 3}:
            previous = "previous_enemy_first" if frozen.get("initiative_side") == "enemy_first" else "previous_received_12"
            if previous not in conditions:
                conditions.append(previous)
        elif archetype == "reversal" and slot == 0:
            runtime_operations.append({"op": "set_mark", "key": mark_key, "stacks": 1, "ttl_rounds": 1})
        elif archetype == "reversal" and slot == 1:
            runtime_conditions.append({"type": "mark_exists", "key": mark_key})
            runtime_operations.append({"op": "consume_mark", "key": mark_key})

        effect_pool = AXIS_EFFECTS.get(axis, AXIS_EFFECTS[primary])
        raw_effect = copy.deepcopy(effect_pool[(index // len(axes)) % len(effect_pool)])
        restrictions = len([item for item in conditions if item != "always"]) + len(runtime_conditions)
        effect = _scaled_effect(raw_effect, restrictions, archetype)
        if archetype == "suppression" and effect.get("kind") == "stat_multiplier":
            effect["target"] = "enemy"
        if archetype == "conversion" and slot % 2:
            effect = {"kind": "restore_mp" if "mana" in axes else "restore_state", "target": "player", "value": round(.025 * max(1, restrictions), 6)}
        payload = {
            "schema_version": 2, "source_id": source_id, "trigger": trigger,
            "schedule": schedule, "conditions": conditions, "effect": effect,
            "runtime_conditions": runtime_conditions, "runtime_operations": runtime_operations,
            "theme_axis": axis, "theme_slot": slot, "variant": index,
        }
        payload["id"] = _stable_rule_id(source_id, payload, index)
        payload["name"] = str(raw_effect.get("core", ARCHETYPE_NAMES[archetype]))
        payload["display_name"] = payload["name"]
        payload["description"] = describe_rule(payload)
        rules.append(payload)
    return rules


def validate_theme_consistency(blueprint: dict[str, Any], rules: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    primary = str(blueprint.get("primary_axis", ""))
    secondaries = list(map(str, blueprint.get("secondary_axes", [])))
    if primary not in ENABLED_PRIMARY_AXES:
        errors.append("主玩法轴不可用")
    allowed = set(AXIS_COMPATIBILITY.get(primary, ()))
    if any(axis not in allowed for axis in secondaries):
        errors.append("副玩法轴不兼容")
    if int(blueprint.get("axis_count", 0)) != 1 + len(secondaries):
        errors.append("玩法轴数量不一致")
    frozen = dict(blueprint.get("frozen_parameters", {}))
    if primary == "initiative" and blueprint.get("archetype") != "dual_mode":
        forbidden = "enemy_first" if frozen.get("initiative_side") == "player_first" else "player_first"
        if any(forbidden in rule.get("conditions", []) for rule in rules):
            errors.append("先手主题出现互斥条件")
    if primary == "terrain":
        allowed_terrain = str(frozen.get("terrain"))
        terrain_conditions = {"terrain_open", "terrain_narrow", "terrain_dangerous"}
        if any(any(condition in terrain_conditions and condition != allowed_terrain for condition in rule.get("conditions", [])) for rule in rules):
            errors.append("地形主题出现互斥条件")
    for rule in rules:
        errors.extend(validate_rule(rule))
    return list(dict.fromkeys(errors))


def gameplay_debug_row(artifact: dict[str, Any]) -> dict[str, Any]:
    blueprint = artifact.get("gameplay_blueprint", {})
    rules = [effect["rule"] for effect in artifact.get("effects", []) if isinstance(effect.get("rule"), dict)]
    return {
        "artifact_id": artifact.get("id"), "rank": artifact.get("rank"),
        "power": artifact.get("base_combat_power"), "flavor_theme": artifact.get("theme_id"),
        "primary_axis": blueprint.get("primary_axis"), "secondary_axes": blueprint.get("secondary_axes", []),
        "archetype": blueprint.get("archetype"), "cadence": blueprint.get("cadence"),
        "rule_count": len(rules),
        "stateful_rules": sum(bool(rule.get("runtime_conditions") or rule.get("runtime_operations")) for rule in rules),
        "validation_errors": validate_theme_consistency(blueprint, rules) if blueprint else ["旧版神器没有玩法蓝图"],
    }
