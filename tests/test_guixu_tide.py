import random
import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from cultivation_life.content_registry import (
    CONTENT, CONTENT_DOCUMENTS, GUIXU_EXCLUSIVE_ITEM_IDS,
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS, GUIXU_TIDE_CONTENT, ITEM_CATALOG,
    MARKET_GOODS, TECHNIQUE_CATALOG, ContentError, validate_guixu_catalog,
)
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc


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
        manifest = json.loads(
            (SOURCE_ROOT / "dlc" / "guixu-tide" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], "1.0.0")
        dungeons = GUIXU_TIDE_CONTENT["dungeons"]
        self.assertEqual({row["world"] for row in dungeons}, {"human", "spirit"})
        self.assertEqual({row["name"] for row in dungeons}, {"葬海天渊", "诸界尾闾"})
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

    def test_public_panel_only_exposes_the_current_world_dungeon(self):
        created = self.engine.create_game("观潮", "supreme_water", "dao", 19, "water")
        game_id = created["id"]
        human = self.engine.get_game(game_id)["guixu_tide"]
        self.assertTrue(human["available"])
        self.assertEqual([row["world"] for row in human["dungeons"]], ["human"])

        game = self.engine.store.load(game_id)
        game.player.world = "spirit"
        self.engine.store.save(game)
        spirit = self.engine.get_game(game_id)["guixu_tide"]
        self.assertEqual([row["world"] for row in spirit["dungeons"]], ["spirit"])

        game = self.engine.store.load(game_id)
        game.player.world = "celestial"
        self.engine.store.save(game)
        celestial = self.engine.get_game(game_id)["guixu_tide"]
        self.assertFalse(celestial["available"])
        self.assertEqual(celestial["dungeons"], [])

    def test_guixu_treasures_are_excluded_from_every_generic_acquisition_pool(self):
        market_ids = {str(row["content_id"]) for row in MARKET_GOODS}
        self.assertFalse(market_ids & GUIXU_EXCLUSIVE_ITEM_IDS)
        self.assertFalse(market_ids & GUIXU_EXCLUSIVE_TECHNIQUE_IDS)

        created = self.engine.create_game("守池", "supreme_metal", "dao", 13, "metal")
        game = self.engine.store.load(created["id"])
        npc = SectNpc(
            "pool-audit", "守池人", "", 8, 9, 1000, None,
            spirit_root="supreme_metal", path="dao", world="spirit",
        )
        npc_technique = self.engine._default_npc_main_technique(npc)
        self.assertNotIn(npc_technique, GUIXU_EXCLUSIVE_TECHNIQUE_IDS)
        self.assertFalse(
            set(self.engine._owner_technique_candidates(game.player, npc))
            & GUIXU_EXCLUSIVE_TECHNIQUE_IDS
        )
        alchemy_ids = {
            row["id"] for row in self.engine._public_spirit_field(game.player)["alchemy"]["targets"]
        }
        self.assertFalse(alchemy_ids & GUIXU_EXCLUSIVE_ITEM_IDS)

    def test_guixu_validator_rejects_any_declarative_side_channel(self):
        documents = copy.deepcopy(CONTENT_DOCUMENTS)
        leaked_id = next(iter(GUIXU_EXCLUSIVE_ITEM_IDS))
        documents["illegal_events.json"] = {
            "schema_version": 1,
            "events": [{"id": "LEAK", "choices": [{"effects": [{"item_id": leaked_id}]}]}],
        }
        with self.assertRaisesRegex(ContentError, "不得被其他内容表引用"):
            validate_guixu_catalog(GUIXU_TIDE_CONTENT, CONTENT, documents)

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
        self.assertEqual(trapped["guixu_tide"]["session"]["actors"], [])
        self.assertEqual(trapped["guixu_tide"]["session"]["treasures"], [])
        self.engine.assert_guixu_operation_allowed(game_id, "advance")
        with self.assertRaisesRegex(ValueError, "外界操作"):
            self.engine.assert_guixu_operation_allowed(game_id, "map-travel")

        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.assertEqual(cycle["roster"], [])
        self.engine._announce_guixu_cycle(game, dungeon, cycle, random.Random(24))
        game.pending_event = None
        self.engine._open_guixu_cycle(game, dungeon, cycle, random.Random(25))
        self.assertFalse(game.guixu_state["player_session"]["trapped"])
        self.assertEqual(game.guixu_state["player_session"]["remaining_days"], dungeon["window_days"])

    def test_guixu_rest_restores_resources_and_costs_expedition_time(self):
        game_id, dungeon = self._open_human_dungeon(seed=27)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        game.player.hp = 1
        game.player.mp = 1
        before_days = game.guixu_state["player_session"]["remaining_days"]
        self.engine.store.save(game)

        rested = self.engine.guixu_action(game_id, "rest", {})
        self.assertGreater(rested["player"]["hp"], 1)
        self.assertGreater(rested["player"]["mp"], 1)
        self.assertEqual(
            rested["guixu_tide"]["session"]["remaining_days"],
            before_days - GUIXU_TIDE_CONTENT["settings"]["action_days"]["rest"],
        )
        self.assertEqual(rested["history"][0]["event_id"], "SYS_GUIXU_REST")

    def test_trapped_main_training_reuses_body_and_sense_progression(self):
        game_id, dungeon = self._open_human_dungeon(seed=29)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        game.guixu_state["player_session"]["remaining_days"] = 0
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._close_guixu_cycle(game, dungeon, cycle, random.Random(29))
        game.player.body_technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BODY_MORTAL"])
        game.player.divine_sense_technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_SPIRIT_SENSE"])
        self.engine.store.save(game)

        body = self.engine.advance(game_id, "body_train")
        self.assertGreater(body["body_cultivation"]["progress"], 0)
        sense = self.engine.advance(game_id, "sense_train")
        self.assertGreater(sense["player"]["divine_sense"]["experience"], 0)
        self.assertTrue(sense["guixu_tide"]["session"]["trapped"])
        with self.assertRaisesRegex(ValueError, "只能修炼"):
            self.engine.advance(game_id, "befriend_neighbors")

    def test_guixu_combat_uses_cramped_pursuit_rules(self):
        game_id, dungeon = self._open_human_dungeon(seed=33)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        actor = next(row for row in cycle["roster"] if row["layer_id"] == "outer")
        with patch.object(self.engine, "_combat", return_value=("victory_escape", "test")) as combat:
            self.engine._guixu_fight(
                game, dungeon, cycle, game.guixu_state["player_session"], actor,
                random.Random(33),
            )
        target = combat.call_args.args[1]
        settings = GUIXU_TIDE_CONTENT["settings"]
        self.assertEqual(target["natural_terrain"], "狭窄")
        self.assertEqual(target["kill_pursuit_threshold"], settings["combat_kill_pursuit_threshold"])
        self.assertEqual(target["pursuit_chance_bonus"], settings["combat_pursuit_chance_bonus"])
        self.assertLess(settings["flee_base_chance"], .48)

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
        self.assertFalse(public_dungeon["entry_requirements"]["rank_matches"])
        self.assertFalse(public_dungeon["entry_requirements"]["suppression_active"])
        self.assertTrue(public_dungeon["entry_requirements"]["max_rank_name"])
        self.engine.manage_secret_art(game_id, "conceal", "cancel")

        suppressed = self.engine.manage_secret_art(
            game_id, "suppress", "activate", *dungeon["max_entry_rank"],
        )
        public_dungeon = next(
            row for row in suppressed["guixu_tide"]["dungeons"] if row["id"] == dungeon["id"]
        )
        self.assertTrue(public_dungeon["can_enter"])
        self.assertTrue(public_dungeon["entry_requirements"]["rank_matches"])
        self.assertTrue(public_dungeon["entry_requirements"]["suppression_active"])
        entered = self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        self.assertIsNotNone(entered["guixu_tide"]["session"])

        released = self.engine.manage_secret_art(game_id, "suppress", "cancel")
        self.assertIsNone(released["guixu_tide"]["session"])
        self.assertEqual(released["player"]["location_id"], dungeon["entry_location_id"])
        self.assertEqual(released["history"][0]["event_id"], "SYS_SECRET_ART")
        self.assertEqual(released["history"][1]["event_id"], "SYS_GUIXU_EJECT")


if __name__ == "__main__":
    unittest.main()
