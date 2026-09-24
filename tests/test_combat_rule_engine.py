from __future__ import annotations

import random

from cultivation_life.combat_rule_engine import BattleRuleRuntime, evaluate_rules, prepare_rules


def _context(round_no: int, *, first: bool = False) -> dict:
    return {
        "round_no": round_no, "max_rounds": 5, "realm_delta": 0,
        "natural_terrain": "狭窄", "artificial_conditions": [],
        "player_state": .8, "enemy_state": .7, "player_mp": .6,
        "player_morale": 80, "enemy_morale": 75, "player_first": first,
        "controlled": False, "received": .05, "dealt": .08,
    }


def _rule(rule_id: str, **updates) -> dict:
    rule = {
        "schema_version": 2, "id": rule_id, "source_id": "artifact-a",
        "trigger": "initiative_resolved", "schedule": "every",
        "conditions": ["enemy_first"],
        "effect": {"kind": "stat_multiplier", "target": "player", "stat": "mobility", "value": .08},
        "runtime_conditions": [], "runtime_operations": [], "display_name": rule_id,
    }
    rule.update(updates)
    return rule


def test_counter_and_namespaces_are_battle_local_and_side_isolated() -> None:
    runtime = BattleRuleRuntime(max_rounds=5)
    runtime.begin_round(1, {"player": _context(1), "enemy": _context(1)})
    setup = _rule("setup", runtime_operations=[{"op": "counter_add", "key": "streak", "value": 1, "max": 3}])
    payoff = _rule("payoff", runtime_conditions=[{"type": "counter_at_least", "key": "streak", "value": 1}])
    result = evaluate_rules([setup, payoff], trigger="initiative_resolved", context=_context(1), runtime=runtime, side="player")
    assert result["player_stat_multipliers"]["mobility"] > 1.16
    assert runtime.counter("player:artifact-a", "streak") == 1
    assert runtime.counter("enemy:artifact-a", "streak") == 0


def test_previous_snapshot_mark_ttl_and_random_schedule_are_bounded() -> None:
    runtime = BattleRuleRuntime(max_rounds=5)
    runtime.begin_round(1, {"player": _context(1), "enemy": _context(1)})
    marker = _rule("marker", runtime_operations=[{"op": "set_mark", "key": "gap", "ttl_rounds": 1}])
    evaluate_rules([marker], trigger="initiative_resolved", context=_context(1), runtime=runtime, side="player")
    player_end = _context(1, first=False)
    player_end["player_mp"] = .4
    runtime.finish_round({"player": player_end, "enemy": _context(1, first=True)})
    runtime.begin_round(2, {"player": _context(2), "enemy": _context(2)})
    follow = _rule(
        "follow", conditions=["previous_enemy_first"],
        runtime_conditions=[
            {"type": "mark_exists", "key": "gap"},
            {"type": "previous_delta_at_least", "key": "player_mp_spent", "value": .19},
        ],
        runtime_operations=[{"op": "consume_mark", "key": "gap"}],
    )
    result = evaluate_rules([follow], trigger="initiative_resolved", context=_context(2), runtime=runtime, side="player")
    assert result["triggered_ids"] == ["follow"]
    assert runtime.mark("player:artifact-a", "gap") is None
    prepared = prepare_rules([_rule("random", schedule="random_two")], max_rounds=5, rng=random.Random(4))
    assert len(prepared[0]["_battle_random_rounds"]) == 2
