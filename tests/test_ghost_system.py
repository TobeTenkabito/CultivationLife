import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import (
    ITEM_CATALOG,
    MARKET_GOODS,
    TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp


class GhostSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_hell_is_enabled_as_complete_base_game_world(self):
        profile = WORLD_SYSTEMS["world_profiles"]["hell"]
        self.assertTrue(profile["enabled"])
        self.assertEqual(profile["npc_realm_cap"], 8)
        self.assertTrue({"events", "market", "factions", "ranking"} <= set(profile["supports"]))
        route = WORLD_SYSTEMS["cultivation_routes"]["ghost"]
        self.assertTrue(next(stage for stage in route["stages"] if stage.get("world") == "hell")["enabled"])
        self.assertFalse(next(stage for stage in route["stages"] if stage.get("world") == "reincarnation")["enabled"])

    def test_native_ghost_start_has_starter_manual_sense_map_and_sects(self):
        shown = self.engine.create_game(
            "照夜", "mutated_yin", "ghost", 1401, start_world="hell",
        )
        player = shown["player"]
        self.assertEqual(player["world"], "hell")
        self.assertEqual(player["technique_slots"]["main"]["id"], "TECH_GHOST_BREATHING")
        self.assertEqual(player["technique_slots"]["divine_sense"]["id"], "TECH_SOUL_ECHO_SENSE")
        self.assertEqual(shown["map"]["current"], "ghost_gate")
        self.assertEqual(
            {row["id"] for row in shown["faction"]["available"]},
            {"ghost_passage_court", "forgetful_river_archive", "iron_tree_prison_sect"},
        )
        self.assertTrue(shown["spirit_ranking"]["available"])
        self.assertEqual(shown["spirit_ranking"]["title"], "地狱界天榜前二十")
        self.assertEqual(len(shown["spirit_ranking"]["entries"]), 20)

    def test_ghost_core_quick_start_and_hell_market_are_world_local(self):
        shown = self.engine.create_game(
            "渡川", "none", "dao", 1402, preset_id="ghost_core",
        )
        self.assertEqual((shown["player"]["path"], shown["player"]["world"]), ("ghost", "hell"))
        self.assertEqual(shown["player"]["realm_index"], 3)
        power_ratio = shown["player"]["combat_power"] / shown["player"]["expected_combat_power"]
        self.assertGreaterEqual(power_ratio, 0.9)
        self.assertLessEqual(power_ratio, 1.1)
        self.assertTrue(shown["market"]["offers"])
        self.assertTrue(all(offer["world"] == "hell" for offer in shown["market"]["offers"]))
        hell_ids = {
            row["content_id"] for row in MARKET_GOODS if row.get("world") == "hell"
        }
        self.assertTrue(all(offer["content_id"] in hell_ids for offer in shown["market"]["offers"]))
        game = self.engine.store.load(shown["id"])
        for category in ("artifact", "technique", "pill"):
            pool = self.engine._treasure_reward_pool(game, category)
            self.assertTrue(pool, category)
            self.assertTrue(all(row["world"] == "hell" for row in pool), category)

    def test_hell_has_local_breakthrough_aids_for_every_supported_scope(self):
        expected = {
            *(f"major:{realm}" for realm in range(1, 8)),
            *(f"minor:{realm}" for realm in range(2, 9)),
        }
        ghost_aids = {
            item.breakthrough_scope
            for item in ITEM_CATALOG.values()
            if item.breakthrough_bonus > 0 and "ghost" in item.tags
        }
        self.assertEqual(ghost_aids, expected)
        sold = {
            ITEM_CATALOG[row["content_id"]].breakthrough_scope
            for row in MARKET_GOODS
            if row.get("world") == "hell" and row["kind"] == "item"
            and ITEM_CATALOG[row["content_id"]].breakthrough_bonus > 0
        }
        self.assertEqual(sold, expected)

    def test_ghost_crossing_enters_hell_and_mahayana_can_visit_human_world(self):
        created = self.engine.create_game("归渡", "mutated_yin", "ghost", 1403)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 3
        result, _ = self.engine._effect(
            {"type": "enter_spirit_realm"}, game, {"id": "TEST"}, random.Random(1),
        )
        self.assertEqual(result, "entered_spirit_realm")
        self.assertEqual(game.player.world, "hell")
        game.player.realm_index = 8
        game.player.layer = 9
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        self.engine.store.save(game)

        descended = self.engine.cross_world(game.id, "human")
        self.assertEqual(descended["player"]["world"], "human")
        self.assertTrue(descended["world_travel"]["can_return_hell"])
        restored = self.engine.cross_world(game.id, "hell")
        self.assertEqual((restored["player"]["world"], restored["player"]["realm_index"]), ("hell", 8))
        self.assertFalse(restored["world_travel"]["suppressed"])

    def test_hell_events_are_world_scoped_and_reference_ghost_content(self):
        events = [event for event in self.engine.events if event["id"].startswith("EVT_HELL_")]
        self.assertGreaterEqual(len(events), 14)
        self.assertTrue(all("world:hell" in event.get("tags", []) for event in events))
        self.assertIn("TECH_REINCARNATION_GATE_CANON", TECHNIQUE_CATALOG)


if __name__ == "__main__":
    unittest.main()
