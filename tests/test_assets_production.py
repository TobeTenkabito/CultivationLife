from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import (
    GrantItem,
    GameEngine,
)
from cultivation_life.domain.assets import (
    ASSET_LEDGER,
    create_asset,
    release_reservation,
    reserve_asset,
    settle_reservation,
)
from cultivation_life.domain.cultivation import CULTIVATION
from cultivation_life.kernel.bus import SimulationContext


class V2AssetsAndProductionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.directory.name) / "v2.sqlite3")
        game = self.engine.create_game("百工修士", seed=330077)
        self.game_id = game["id"]
        self.actor_id = game["player"]["id"]

    def tearDown(self):
        self.directory.cleanup()

    def _save(self, state) -> None:
        self.engine.store.save(
            state, [], player_name="百工修士", expected_revision=state.revision
        )

    def _resolve_pending(self) -> dict:
        game = self.engine.get_game(self.game_id)
        while game["pending_event"] is not None:
            choice = next(
                row for row in game["pending_event"]["choices"] if row["enabled"]
            )
            game = self.engine.choose(self.game_id, choice["id"]).game
        return game

    def _become_cultivator(self) -> None:
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(realm_id="qi", layer=1)
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self._save(state)

    def test_healing_and_breakthrough_items_are_consumed_atomically(self):
        state = self.engine.store.load(self.game_id)
        condition = state.entities.require(self.actor_id, "combat.condition")
        condition["hp_ratio"] = 0.4
        state.entities.put(self.actor_id, "combat.condition", condition)
        self._save(state)
        self.engine.execute(self.game_id, GrantItem(self.actor_id, "healing_pill", 1))
        healed = self.engine.use_item(self.game_id, "healing_pill")
        self.assertAlmostEqual(healed.game["combat"]["snapshot"]["hp_ratio"], 0.75)
        self.assertNotIn("healing_pill", {row["id"] for row in healed.game["inventory"]})

        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(
            realm_id="qi", layer=13, opportunity=1_000_000.0, bottleneck="major"
        )
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self._save(state)
        self.engine.execute(self.game_id, GrantItem(self.actor_id, "foundation_pill", 1))
        prepared = self.engine.use_item(self.game_id, "foundation_pill")
        self.assertEqual(
            prepared.game["player"]["cultivation"]["active_breakthrough_aids"],
            ["foundation_pill"],
        )
        resolved = self.engine.attempt_breakthrough(self.game_id)
        self.assertEqual(
            resolved.game["player"]["cultivation"]["active_breakthrough_aids"], []
        )

    def test_trial_recovery_item_can_be_used_without_resolving_pending_choice(self):
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(
            realm_id="nascent", layer=9, opportunity=10_000_000.0,
            bottleneck="major", heart_demon=0.0,
        )
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self._save(state)
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "tribulation_vitality_pill", 1)
        )
        table = self.engine.definitions.breakthrough["major_base"]["4"]
        previous = dict(table)
        try:
            for key in table:
                table[key] = 1.0
            self.engine.attempt_breakthrough(self.game_id)
        finally:
            table.clear()
            table.update(previous)
        drained = self.engine.choose(self.game_id, "endure")
        pending_id = drained.game["pending_event"]["id"]
        self.assertLess(drained.game["combat"]["snapshot"]["hp_ratio"], 1.0)
        restored = self.engine.use_item(self.game_id, "tribulation_vitality_pill")
        self.assertEqual(restored.game["pending_event"]["id"], pending_id)
        self.assertEqual(restored.game["combat"]["snapshot"]["hp_ratio"], 1.0)
        self.assertNotIn(
            "tribulation_vitality_pill",
            {row["id"] for row in restored.game["inventory"]},
        )

    def test_spirit_field_is_instant_to_reclaim_and_grows_on_unified_clock(self):
        self._become_cultivator()
        self.engine.execute(self.game_id, GrantItem(self.actor_id, "spirit_stone", 500))
        self.engine.execute(self.game_id, GrantItem(self.actor_id, "dew_grass_seed", 1))
        reclaimed = self.engine.reclaim_spirit_field(self.game_id)
        self.assertEqual(reclaimed.game["clock"]["year"], 0)
        self.assertEqual(reclaimed.game["production"]["reclaim_years"], 0)
        planted = self.engine.plant_spirit_crop(self.game_id, "dew_grass")
        plot_id = planted.game["production"]["plots"][0]["id"]
        advanced = self.engine.perform_action(self.game_id, "rest", 1)
        self.assertEqual(advanced.game["production"]["plots"][0]["growth_years"], 1.0)
        self._resolve_pending()

        harvested = self.engine.harvest_spirit_crop(self.game_id, plot_id)
        asset = harvested.game["assets"]["instances"][0]
        self.assertEqual(asset["kind"], "harvested_spirit_plant")
        before = harvested.game["market"]["spirit_stones"]
        sold = self.engine.sell_spirit_plant(self.game_id, asset["id"])
        self.assertEqual(sold.game["assets"]["instances"], [])
        self.assertGreater(sold.game["market"]["spirit_stones"], before)

    def test_irrigation_harvest_and_alchemy_share_instance_assets(self):
        self._become_cultivator()
        self.engine.execute(self.game_id, GrantItem(self.actor_id, "spirit_stone", 500))
        self.engine.execute(self.game_id, GrantItem(self.actor_id, "dew_grass_seed", 1))
        self.engine.reclaim_spirit_field(self.game_id)
        planted = self.engine.plant_spirit_crop(self.game_id, "dew_grass")
        plot_id = planted.game["production"]["plots"][0]["id"]
        irrigated = self.engine.irrigate_spirit_crop(self.game_id, plot_id, 0.15)
        self.assertAlmostEqual(irrigated.game["combat"]["snapshot"]["mp_ratio"], 0.85)
        harvested = self.engine.harvest_spirit_crop(self.game_id, plot_id)
        asset_id = harvested.game["assets"]["instances"][0]["id"]
        refined = self.engine.refine_pill(
            self.game_id, "healing_pill", ((asset_id, 1),)
        )
        self.assertEqual(refined.game["assets"]["instances"], [])
        self.assertAlmostEqual(refined.game["combat"]["snapshot"]["mp_ratio"], 0.70)
        self.assertGreater(refined.game["production"]["alchemy_experience"], 0)
        self.assertTrue(any(
            event["event_type"] == "crafting.alchemy.resolved"
            for event in refined.events
        ))

    def test_reservations_cover_stacks_and_instances_without_copying_assets(self):
        self.engine.execute(self.game_id, GrantItem(self.actor_id, "spirit_stone", 20))
        state = self.engine.store.load(self.game_id)
        context = SimulationContext(state=state, event_bus=self.engine.commands.event_bus)
        asset_id = create_asset(
            context,
            self.actor_id,
            kind="test_artifact",
            definition_id="test",
            name="试验法宝",
        )
        stack_reservation = reserve_asset(
            context,
            self.actor_id,
            purpose="test:stack",
            item_id="spirit_stone",
            quantity=8,
        )
        instance_reservation = reserve_asset(
            context,
            self.actor_id,
            purpose="test:instance",
            asset_id=asset_id,
        )
        inventory = state.entities.require(self.actor_id, "economy.inventory")
        self.assertEqual(inventory["reserved"]["spirit_stone"], 8)
        ledger = state.entities.require(self.actor_id, ASSET_LEDGER)
        self.assertEqual(
            ledger["instances"][asset_id]["reservation_id"], instance_reservation
        )
        release_reservation(context, self.actor_id, stack_reservation)
        settled = settle_reservation(context, self.actor_id, instance_reservation)
        self.assertEqual(settled["asset_id"], asset_id)
        self.assertNotIn(
            asset_id,
            state.entities.require(self.actor_id, ASSET_LEDGER)["instances"],
        )
        self.engine.invariants.validate(state)


if __name__ == "__main__":
    unittest.main()
