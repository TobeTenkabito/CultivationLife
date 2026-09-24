from __future__ import annotations

import random

from cultivation_life.system.tianji_system import _scaled_effects
from cultivation_life.tianji_theme_rules import (
    compile_theme_rules, generate_gameplay_blueprint, validate_theme_consistency,
)


def _blueprint(seed: int = 71) -> dict:
    return generate_gameplay_blueprint(
        blueprint_rng=random.Random(seed), axis_count_rng=random.Random(seed + 1),
        archetype_rng=random.Random(seed + 2), cadence_rng=random.Random(seed + 3),
        flavor_theme_id="thunder",
    )


def test_blueprint_and_rules_do_not_accept_or_depend_on_power_or_rank() -> None:
    first = _blueprint()
    second = _blueprint()
    assert first == second
    a = compile_theme_rules(first, rule_count=19, rng=random.Random(99), source_id="tianji-049")
    b = compile_theme_rules(second, rule_count=19, rng=random.Random(99), source_id="tianji-049")
    assert a == b
    assert len(a) == 19
    assert not validate_theme_consistency(first, a)


def test_compiler_supports_unusually_long_tail_without_losing_theme() -> None:
    blueprint = {
        "schema_version": 1, "blueprint_id": "initiative.counter.sustained.state",
        "primary_axis": "initiative", "secondary_axes": ["combat_state", "morale"],
        "axis_count": 3, "archetype": "counter", "cadence": "sustained",
        "frozen_parameters": {"initiative_side": "enemy_first", "state_threshold": .30, "morale_side": "player_morale_50"},
        "stateful": True, "tendency": "后手反制",
    }
    rules = compile_theme_rules(blueprint, rule_count=50, rng=random.Random(108), source_id="tail-test")
    assert len(rules) == 50
    assert len({rule["id"] for rule in rules}) == 50
    assert all("player_first" not in rule["conditions"] for rule in rules)
    assert not validate_theme_consistency(blueprint, rules)


def test_replica_scaling_keeps_stateful_structure_and_thresholds() -> None:
    blueprint = _blueprint(113)
    rule = compile_theme_rules(blueprint, rule_count=1, rng=random.Random(17), source_id="replica-test")[0]
    effect = {
        "primitive": "rule:test", "name": "试制器理", "conditions": rule["conditions"],
        "rule": rule, "replica_scaling": "rule_scale",
    }
    for ratio in (.25, .50, .90, 1.08):
        combat, _ = _scaled_effects([effect], ratio)
        scaled = combat[0]["generated_rules"][0]
        assert scaled["effect_scale"] == ratio
        assert scaled["conditions"] == rule["conditions"]
        assert scaled["runtime_conditions"] == rule["runtime_conditions"]
        assert scaled["runtime_operations"] == rule["runtime_operations"]
