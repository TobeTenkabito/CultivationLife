import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from cultivation_life.content_registry import GUIXU_TIDE_CONTENT, ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class GuixuTideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def _open_human_dungeon(self, seed=17):
        created = self.engine.create_game("潮生", "supreme_water", "dao", seed, "water")
        game = self.engine.store.load(created["id"])
        dungeon = next(row for row in GUIXU_TIDE_CONTENT["dungeons"] if row["world"] == "human")
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._open_guixu_cycle(game, dungeon, cycle, random.Random(seed))
        game.pending_event = None
        game.player.world = dungeon["world"]
        game.player.location_id = dungeon["entry_location_id"]
        game.player.realm_index = 3
        game.player.layer = 1
        self.engine.store.save(game)
        return created["id"], dungeon

    def test_content_has_two_rich_non_repeating_pools(self):
        dungeons = GUIXU_TIDE_CONTENT["dungeons"]
        self.assertEqual({row["world"] for row in dungeons}, {"human", "spirit"})
        seen = set()
        expected = {
            "technique": 10, "equipment": 12, "consumable": 8,
            "plant": 10, "material": 10, "currency": 10,
        }
        for dungeon in dungeons:
            pool = dungeon["treasure_pool"]
            self.assertEqual(len(pool), 60)
            self.assertEqual(Counter(row["category"] for row in pool), expected)
            self.assertFalse(seen.intersection(row["id"] for row in pool))
            seen.update(row["id"] for row in pool)
            for row in pool:
                catalog = TECHNIQUE_CATALOG if row["kind"] == "technique" else ITEM_CATALOG
                self.assertIn(row["content_id"], catalog)

    def test_enter_search_and_close_permanently_depletes_pool(self):
        game_id, dungeon = self._open_human_dungeon()
        entered = self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        self.assertEqual(entered["guixu_tide"]["session"]["remaining_days"], dungeon["window_days"] - 1)

        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        target = cycle["round_entries"][0]
        for row in cycle["round_entries"][1:]:
            row["layer_id"] = "middle"
        target["layer_id"] = "outer"
        target["claim_at_day"] = dungeon["window_days"] - 2
        target_id = target["pool_entry_id"]
        self.engine.store.save(game)

        searched = self.engine.guixu_action(game_id, "search", {})
        self.assertEqual(searched["history"][0]["event_id"], "SYS_GUIXU_SEARCH")
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        target = next(row for row in cycle["round_entries"] if row["pool_entry_id"] == target_id)
        self.assertEqual(target["resolution"], "player")
        self.assertNotIn(target_id, cycle["pool_remaining"])

        self.engine._close_guixu_cycle(game, dungeon, cycle, random.Random(99))
        self.assertEqual(cycle["phase"], "closed")
        self.assertIn(
            self.engine._guixu_entry_definition(dungeon, target_id)["name"],
            cycle["last_report"]["player"],
        )
        self.assertNotIn(target_id, cycle["pool_remaining"])

    def test_failed_return_traps_player_until_next_cycle(self):
        game_id, dungeon = self._open_human_dungeon(seed=23)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        session = game.guixu_state["player_session"]
        session["layer_id"] = "inner"
        session["remaining_days"] = 2
        self.engine.store.save(game)

        trapped = self.engine.guixu_action(game_id, "return", {})
        self.assertTrue(trapped["guixu_tide"]["session"]["trapped"])
        with self.assertRaisesRegex(ValueError, "外界操作"):
            self.engine.assert_guixu_operation_allowed(game_id, "advance")

        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._announce_guixu_cycle(game, dungeon, cycle, random.Random(24))
        game.pending_event = None
        self.engine._open_guixu_cycle(game, dungeon, cycle, random.Random(25))
        self.assertFalse(game.guixu_state["player_session"]["trapped"])
        self.assertEqual(game.guixu_state["player_session"]["remaining_days"], dungeon["window_days"])

    def test_state_round_trips_in_save_file(self):
        game_id, dungeon = self._open_human_dungeon(seed=31)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        loaded = self.engine.store.load(game_id)
        self.assertEqual(loaded.guixu_state["player_session"]["dungeon_id"], dungeon["id"])
        self.assertEqual(len(loaded.guixu_state["cycles"][dungeon["id"]]["round_entries"]), 6)

    def test_one_pending_notice_does_not_delay_another_due_dungeon(self):
        created = self.engine.create_game("并潮", "supreme_water", "dao", 41, "water")
        game = self.engine.store.load(created["id"])
        for cycle in game.guixu_state["cycles"].values():
            cycle["next_announce_age"] = game.player.age
            cycle["next_open_age"] = game.player.age
        needs_input = self.engine._advance_guixu_calendar(game, random.Random(41), [])
        self.assertTrue(needs_input)
        self.assertTrue(game.pending_event["id"].startswith("EVT_GUIXU_"))
        self.assertTrue(all(
            cycle["phase"] == "open" for cycle in game.guixu_state["cycles"].values()
        ))

    def test_disabling_dlc_allows_safe_ejection_before_external_action(self):
        game_id, dungeon = self._open_human_dungeon(seed=37)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        with patch.dict(GUIXU_TIDE_CONTENT, {"dungeons": []}):
            self.engine.assert_guixu_operation_allowed(game_id, "advance")
            loaded = self.engine._load(game_id)
        self.assertIsNone(loaded.guixu_state["player_session"])
        self.assertEqual(loaded.player.location_id, dungeon["entry_location_id"])
        self.assertTrue(any(row.event_id == "SYS_GUIXU_DISABLED_EJECT" for row in loaded.history))

    def test_suppression_grants_entry_but_concealment_does_not_and_release_ejects(self):
        created = self.engine.create_game("藏境入墟", "supreme_water", "dao", 47, "water")
        game_id = created["id"]
        game = self.engine.store.load(game_id)
        dungeon = next(row for row in GUIXU_TIDE_CONTENT["dungeons"] if row["world"] == "spirit")
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._open_guixu_cycle(game, dungeon, cycle, random.Random(47))
        game.pending_event = None
        game.player.world = dungeon["world"]
        game.player.location_id = dungeon["entry_location_id"]
        game.player.realm_index, game.player.layer = dungeon["eject_rank"]
        self.engine.store.save(game)

        concealed = self.engine.manage_secret_art(
            game_id, "conceal", "activate", *dungeon["max_entry_rank"],
        )
        public_dungeon = next(
            row for row in concealed["guixu_tide"]["dungeons"] if row["id"] == dungeon["id"]
        )
        self.assertFalse(public_dungeon["can_enter"])
        self.engine.manage_secret_art(game_id, "conceal", "cancel")

        suppressed = self.engine.manage_secret_art(
            game_id, "suppress", "activate", *dungeon["max_entry_rank"],
        )
        public_dungeon = next(
            row for row in suppressed["guixu_tide"]["dungeons"] if row["id"] == dungeon["id"]
        )
        self.assertTrue(public_dungeon["can_enter"])
        entered = self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        self.assertIsNotNone(entered["guixu_tide"]["session"])

        released = self.engine.manage_secret_art(game_id, "suppress", "cancel")
        self.assertIsNone(released["guixu_tide"]["session"])
        self.assertEqual(released["player"]["location_id"], dungeon["entry_location_id"])
        self.assertEqual(released["history"][0]["event_id"], "SYS_SECRET_ART")
        self.assertEqual(released["history"][1]["event_id"], "SYS_GUIXU_EJECT")


if __name__ == "__main__":
    unittest.main()
