import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import REALMS, TECHNIQUE_CATALOG, TRANSFORMATION_CATALOG, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import assign_technique, max_hp, max_mp, opportunity_required, public_player, stage_name


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class CelestialSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.engine = GameEngine(root)

    def tearDown(self):
        self.temp.cleanup()

    def _prepared_mahayana(self):
        shown = self.engine.create_game("飞升者", "otherworld", "dao", 912, preset_id="mahayana")
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.realm_index = 8
        player.layer = 9
        player.opportunity = opportunity_required(player)
        player.karma = 0
        player.heart_demon = 0
        player.faction_combat_bonus = 100_000_000
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        self.engine.store.save(game)
        return shown["id"]

    def test_realm_framework_has_four_layerless_immortal_realms(self):
        self.assertEqual([realm.name for realm in REALMS[9:]], ["真仙", "金仙", "太乙", "大罗"])
        self.assertTrue(all(realm.layers == 1 for realm in REALMS[9:]))
        shown = self.engine.create_game("真仙", "otherworld", "dao", 913)
        game = self.engine.store.load(shown["id"])
        game.player.realm_index = 9
        game.player.layer = 1
        self.assertEqual(stage_name(game.player), "真仙")

    def test_nine_stage_ascension_and_five_stage_power_conversion(self):
        game_id = self._prepared_mahayana()
        shown = self.engine.begin_celestial_ascension(game_id)
        self.assertEqual(shown["trial"]["total_steps"], 9)
        for _ in range(9):
            game = self.engine.store.load(game_id)
            game.player.hp = max_hp(game.player)
            game.player.mp = max_mp(game.player)
            self.engine.store.save(game)
            choice_id = self.engine.get_game(game_id)["pending_event"]["choices"][0]["id"]
            shown = self.engine.choose(game_id, choice_id)
        self.assertEqual(shown["player"]["world"], "celestial")
        self.assertEqual(shown["player"]["realm_index"], 9)
        self.assertFalse(shown["player"]["immortal_power_converted"])
        self.assertFalse(shown["trial"]["active"])
        self.assertIsNone(shown["pending_event"])
        self.assertEqual(shown["player"]["mp"], 0)
        self.assertEqual(shown["player"]["time_unit_years"], 500)
        with self.assertRaises(ValueError):
            self.engine.advance(game_id, "travel")

        class CertainRng:
            @staticmethod
            def random():
                return 0.0

        for stage in range(1, 6):
            game = self.engine.store.load(game_id)
            game.player.age += 5000
            self.assertTrue(self.engine._maybe_immortal_conversion_event(game, CertainRng()))
            self.engine.store.save(game)
            choice_id = self.engine.get_game(game_id)["pending_event"]["choices"][0]["id"]
            shown = self.engine.choose(game_id, choice_id)
            self.assertEqual(shown["player"]["immortal_conversion_stage"], stage)
            self.assertAlmostEqual(shown["player"]["immortal_power"]["usable_ratio"], stage / 5)
        self.assertTrue(shown["player"]["immortal_power_converted"])
        self.assertEqual(shown["player"]["resource_name"], "仙灵力")
        self.assertEqual(shown["player"]["immortal_conversion_stage"], 5)
        self.assertIn("TECH_CELESTIAL_BREATHING", [entry["id"] for entry in shown["player"]["known_techniques"]])

        descended = self.engine.cross_world(game_id, "spirit")
        self.assertTrue(descended["world_travel"]["can_return_celestial"])
        self.assertFalse(descended["world_travel"]["can_ascend_celestial"])
        restored = self.engine.cross_world(game_id, "celestial")
        self.assertEqual(restored["player"]["realm_index"], 9)

    def test_conversion_probability_starts_after_ten_units_and_grows_two_percent(self):
        shown = self.engine.create_game("转元者", "otherworld", "dao", 916, preset_id="true_immortal")
        game = self.engine.store.load(shown["id"])
        game.player.immortal_power_converted = False
        game.player.immortal_conversion_stage = 0
        game.player.immortal_conversion_last_age = game.player.age
        game.player.immortal_conversion_checked_units = 0
        game.player.mp = 0

        class ThresholdRng:
            @staticmethod
            def random():
                return 0.15

        game.player.age += 5000
        self.assertFalse(self.engine._maybe_immortal_conversion_event(game, ThresholdRng()))
        self.assertEqual(game.player.immortal_conversion_checked_units, 10)
        game.player.age += 1500
        self.assertTrue(self.engine._maybe_immortal_conversion_event(game, ThresholdRng()))
        self.assertEqual(game.pending_event["runtime"]["waited_units"], 13)
        self.assertAlmostEqual(game.pending_event["runtime"]["trigger_chance"], 0.16)

    def test_lower_world_periodic_thunder_is_fifty_percent_stronger(self):
        shown = self.engine.create_game("逆界者", "law_space", "dao", 914)
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.realm_index = 7
        player.layer = 3
        player.world = "human"
        player.sealed_cultivation = {"realm_index":7, "layer":3, "upper_world":"spirit", "lower_world":"human"}
        player.next_tribulation_age = player.age
        player.tribulation_power = 1000
        self.engine._check_tribulation(game, random.Random(1))
        self.assertEqual(game.active_trial["base_power"], 1000)
        self.assertEqual(game.active_trial["power"], 1500)
        self.assertEqual(game.active_trial["world_power_multiplier"], 1.5)

    def test_lower_world_caps_local_thunder_without_erasing_accumulated_power(self):
        shown = self.engine.create_game("携劫下界", "law_space", "dao", 1914)
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.realm_index, player.layer = 7, 3
        player.world = "human"
        player.sealed_cultivation = {
            "realm_index": 7, "layer": 3, "upper_world": "spirit", "lower_world": "human",
        }
        player.next_tribulation_age = player.age
        player.tribulation_power = 1_000_000
        player.hp, player.mp = max_hp(player), max_mp(player)

        self.engine._check_tribulation(game, random.Random(1))
        self.assertEqual(game.active_trial["uncapped_base_power"], 1_000_000)
        self.assertEqual(game.active_trial["world_base_power_cap"], 4000)
        self.assertEqual(game.active_trial["base_power"], 4000)
        self.assertEqual(game.active_trial["power"], 6000)
        for step in ("thunder_1", "thunder_2", "thunder_3"):
            result, _ = self.engine._resolve_trial_step(game, step, random.Random(2))
        self.assertEqual(result, "trial_completed")
        self.assertEqual(player.tribulation_power, 2_000_000)

    def test_celestial_level_worlds_do_not_cap_thunder_base_power(self):
        shown = self.engine.create_game("仙界承劫", "otherworld", "dao", 1915)
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.realm_index, player.layer = 9, 1
        player.world = "celestial"
        player.next_tribulation_age = player.age
        player.tribulation_power = 1_000_000
        self.engine._check_tribulation(game, random.Random(1))
        self.assertIsNone(game.active_trial["world_base_power_cap"])
        self.assertEqual(game.active_trial["base_power"], 1_000_000)
        self.assertEqual(game.active_trial["power"], 1_000_000)

    def test_only_worlds_below_celestial_tier_define_thunder_caps(self):
        profiles = WORLD_SYSTEMS["world_profiles"]
        for profile in profiles.values():
            if int(profile["tier"]) < 3:
                self.assertGreater(float(profile["tribulation_base_power_cap"]), 0)
            else:
                self.assertNotIn("tribulation_base_power_cap", profile)

    def test_immortal_technique_requires_completed_conversion(self):
        shown = self.engine.create_game("求仙者", "otherworld", "dao", 915)
        game = self.engine.store.load(shown["id"])
        technique = TECHNIQUE_CATALOG["TECH_CELESTIAL_BREATHING"]
        with self.assertRaisesRegex(ValueError, "仙灵力转化"):
            assign_technique(game.player, technique, "main")
        game.player.immortal_power_converted = True
        assign_technique(game.player, technique, "main")
        self.assertEqual(game.player.technique.id, technique.id)

    def test_new_transformation_definitions(self):
        expected = {
            "FORM_WHITE_TIGER":"damage_bonus_5",
            "FORM_VERMILION_BIRD":"round4_regen_10",
            "FORM_ASURA":"higher_realm_damage_10",
            "FORM_XUANWU":"first_round_full_state",
        }
        for form_id, trait in expected.items():
            self.assertIn(trait, TRANSFORMATION_CATALOG[form_id].traits)


if __name__ == "__main__":
    unittest.main()
