"""Compatibility checks for the three reorganized system modules."""

from types import SimpleNamespace
from unittest.mock import patch

from cultivation_life.system import (
    crafting_system,
    economy_system,
    intrigue_system,
    tianji_system,
)


def test_economy_rules_use_the_original_module_binding() -> None:
    rules = {"cooldown_actions": 7}
    with patch.object(economy_system, "WORLD_SYSTEMS", {"auction_system": rules}):
        assert economy_system.EconomySystemMixin._auction_rules() is rules
        assert economy_system.EconomySystemMixin()._auction_rules() is rules


def test_tianji_rules_use_the_original_module_helper() -> None:
    rules = {"enabled": False, "artifact_count": 0}
    with patch.object(tianji_system, "tianji_config", return_value=rules):
        assert tianji_system.TianjiSystemMixin._tianji_config() is rules


def test_intrigue_threshold_uses_the_original_module_helper() -> None:
    rules = {"decision_thresholds": {"sect": 7}}
    with patch.object(intrigue_system, "intrigue_rules", return_value=rules):
        assert intrigue_system.IntrigueSystemMixin()._intrigue_decision_threshold("sect") == 7


def test_auction_cancellation_preserves_deferred_crafting_import() -> None:
    artifact = {"id": "consigned-artifact", "actual_stats": {"combat_power": 100}}
    player = SimpleNamespace()
    game = SimpleNamespace(
        player=player,
        auction_state={
            "status": "open",
            "lots": [],
            "consignments": [{"kind": "crafted_artifact", "artifact": artifact}],
        },
    )
    with (
        patch.object(economy_system, "WORLD_SYSTEMS", {
            "auction_system": {"cooldown_actions": 3},
        }),
        patch.object(crafting_system, "store_crafted_artifact") as store,
    ):
        economy_system.EconomySystemMixin()._cancel_auction_for_world_change(game)
    store.assert_called_once_with(player, artifact)
    assert store.call_args.args[1] is not artifact
    assert game.auction_state == {"status": "cooldown", "actions_remaining": 3}
