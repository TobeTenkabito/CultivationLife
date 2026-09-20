from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.sage_system import apply_external_influence, disciple_curve, sage_content_available


class SageWayDlcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(__file__).resolve().parents[1], Path(self.temp.name))
        shown = self.engine.create_game(
            "试教者", "supreme_wood", "confucian", seed=2207, preset_id="confucian_core",
        )
        self.game_id = shown["id"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_content_and_initial_worlds(self):
        self.assertTrue(sage_content_available())
        shown = self.engine.get_game(self.game_id)
        self.assertTrue(shown["sage_system"]["available"])
        self.assertEqual(len(shown["sage_system"]["doctrines"]), 2)
        saved = self.engine.store.load(self.game_id)
        self.assertEqual(set(saved.sage_state["worlds"]), {"human", "spirit"})

    def test_public_ui_data_explains_choices_sages_and_final_effects(self):
        shown = self.engine.get_game(self.game_id)["sage_system"]
        self.assertIn("战斗力", shown["choice_details"]["gongyang"]["effect_text"][0])
        self.assertTrue(shown["choice_details"]["gongyang"]["description"])
        self.assertTrue(shown["sages"]["mencius"]["description"])
        self.assertIn("心学", shown["sages"]["mencius"]["compatible_names"])
        self.assertTrue(shown["doctrines"][0]["passive_effect_text"])

        joined = self.engine.sage_doctrine_action(
            self.game_id, "join", {"doctrine_id": "sage-human-righteous"},
        )["sage_system"]
        self.assertTrue(joined["effect_text"])
        self.assertIn("神识修炼收益", joined["sages"]["confucius"]["applied_effect_text"][0])

    def test_breakthrough_ui_shows_sage_bonus_and_formats_control_threshold(self):
        script = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("breakthrough.chance.sage_bonus", script)
        self.assertIn("，学说 ", script)
        self.assertIn("Number(numeric.control_lead_percent ?? 10).toFixed(1)", script)
        self.assertIn("学说声望", script)
        self.assertIn("门内威望", script)
        self.assertNotIn("胜则内在", script)
        self.assertNotIn("胜则外在", script)

    def test_shared_pool_and_individual_cap(self):
        rows = [{"id":"a", "external":60.0}, {"id":"b", "external":40.0}]
        apply_external_influence(rows, "a", 10.0, {"influence_floor":.1, "doctrine_influence_cap":60, "world_influence_pool":100})
        self.assertEqual(rows[0]["external"], 60.0)
        apply_external_influence(rows, "b", 10.0, {"influence_floor":.1, "doctrine_influence_cap":60, "world_influence_pool":100})
        self.assertAlmostEqual(sum(row["external"] for row in rows), 100.0, places=3)
        self.assertLess(rows[0]["external"], 60.0)

    def test_disciple_curve_peak_and_floor(self):
        curve = disciple_curve(2, 0, {"disciple_n0_base":4,"disciple_n0_per_sense":2,"disciple_penalty_floor_pp":-8})
        self.assertEqual(curve["breakthrough_pp"], 5.0)
        self.assertEqual(curve["hard_cap"], 12)
        self.assertEqual(disciple_curve(20, 0, {"disciple_n0_base":4,"disciple_n0_per_sense":2,"disciple_penalty_floor_pp":-8})["breakthrough_pp"], -8)

    def test_join_action_and_cross_world_freeze(self):
        self.engine.sage_doctrine_action(self.game_id, "join", {"doctrine_id":"sage-human-righteous"})
        before = self.engine.store.load(self.game_id)
        doctrine = self.engine._player_doctrine(before)
        inner = next(row for row in doctrine["members"] if row.get("is_player"))["inner"]
        after = self.engine.advance(self.game_id, "sage_preach", 1)
        self.assertEqual(after["sage_system"]["last_action"]["years"], 1)
        self.assertGreater(after["sage_system"]["last_action"]["external"], .6)
        game = self.engine.store.load(self.game_id)
        member = next(row for row in self.engine._player_doctrine(game)["members"] if row.get("is_player"))
        self.assertGreater(member["inner"], inner * .97)
        game.player.world = "spirit"
        frozen_before = member["inner"]
        self.engine._advance_sage_year(game, random.Random(3))
        human = next(row for row in game.sage_state["worlds"]["human"]["doctrines"] if row["id"] == "sage-human-righteous")
        self.assertEqual(next(row for row in human["members"] if row.get("is_player"))["inner"], frozen_before)

    def test_found_unique_doctrine_and_save_round_trip(self):
        combo = {"classic":"guliang","philosophy":"mind","practice":"statecraft","script":"old_text"}
        shown = self.engine.sage_doctrine_action(self.game_id, "found", {"action":"found","name":"新民学","combo":combo})
        self.assertIsNotNone(shown["sage_system"]["membership_id"])
        restored = self.engine.store.load(self.game_id)
        self.assertEqual(restored.sage_state["version"], 2)
        self.assertTrue(restored.player.sage_effects)

    def test_only_confucians_rank_and_debate_changes_the_correct_influence(self):
        game = self.engine.store.load(self.game_id)
        doctrine = game.sage_state["worlds"]["human"]["doctrines"][0]
        doctrine["members"].append({
            "id": "outsider", "name": "外道客", "path": "dao", "inner": 99,
            "realm_index": 3, "layer": 1,
        })
        self.engine.store.save(game)
        self.engine.sage_doctrine_action(
            self.game_id, "join", {"doctrine_id": "sage-human-righteous"},
        )
        before = self.engine.get_game(self.game_id)["sage_system"]
        own = next(row for row in before["doctrines"] if row["id"] == "sage-human-righteous")
        self.assertNotIn("outsider", {row["id"] for row in own["members"]})
        self.assertEqual([row["rank"] for row in own["members"]], list(range(1, len(own["members"]) + 1)))
        player_before = next(row for row in own["members"] if row.get("is_player"))["inner"]
        result = self.engine.sage_debate(self.game_id, "sage-human-righteous", "sage-h-r-4")
        own_after = next(row for row in result["sage_system"]["doctrines"] if row["id"] == "sage-human-righteous")
        player_after = next(row for row in own_after["members"] if row.get("is_player"))["inner"]
        self.assertGreater(player_after, player_before)
        with self.assertRaisesRegex(ValueError, "论道需到"):
            self.engine.sage_debate(self.game_id, "sage-human-righteous", "sage-h-r-4")
        external_before = own_after["external"]
        result = self.engine.sage_debate(self.game_id, "sage-human-evidence", "sage-h-e-3")
        own_after = next(
            row for row in result["sage_system"]["doctrines"] if row["id"] == "sage-human-righteous"
        )
        self.assertGreater(own_after["external"], external_before)

    def test_two_thousand_year_simulation_keeps_all_bounds(self):
        game = self.engine.store.load(self.game_id)
        rng = random.Random(913)
        for _ in range(2000):
            game.player.age += 1
            self.engine._advance_sage_year(game, rng)
            for world_state in game.sage_state["worlds"].values():
                doctrines = world_state["doctrines"]
                self.assertGreaterEqual(len(doctrines), 1)
                self.assertLessEqual(len(doctrines), 5)
                self.assertLessEqual(sum(row["external"] for row in doctrines), 100.0001)
                self.assertTrue(all(.1 <= row["external"] <= 60 for row in doctrines))


if __name__ == "__main__":
    unittest.main()
