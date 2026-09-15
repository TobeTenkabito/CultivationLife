import copy
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import MARKET_GOODS, TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, assign_technique, learn_technique
from cultivation_life.transformation_system import (
    BATCH_PAIR_BONUS, absorption_gain, active_transformation_profile, form_potency,
    normalized_transformation_weights,
)
from cultivation_life.content_registry import TRANSFORMATION_CATALOG
from cultivation_life.combat_traits import COMBAT_TRAIT_REGISTRY


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class TransformationSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name))
        self.created = self.engine.create_game("化形者", "supreme_metal", "dao", 901)
        game = self.engine.store.load(self.created["id"])
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BEAST_TRANSFORMATION"])
        learn_technique(game.player, technique)
        assign_technique(game.player, copy.deepcopy(technique), "transformation")
        add_item(game.player, "phoenix_soul_flame", 1)
        add_item(game.player, "azure_luan_essence", 1)
        add_item(game.player, "mountain_ape_soul", 2)
        add_item(game.player, "true_dragon_blood_trace", 1)
        self.engine.store.save(game)
        self.engine.absorb_transformation_material(self.created["id"], "phoenix_soul_flame", stat_id="sustain")
        self.engine.absorb_transformation_material(self.created["id"], "azure_luan_essence", stat_id="sustain")
        self.engine.absorb_transformation_material(self.created["id"], "mountain_ape_soul", stat_id="sustain")

    def tearDown(self):
        self.temp.cleanup()

    def test_geometric_weights_are_exactly_normalized(self):
        self.assertEqual(normalized_transformation_weights(1), [1.0])
        weights = normalized_transformation_weights(2)
        self.assertAlmostEqual(weights[0], 2 / 3)
        self.assertAlmostEqual(weights[1], 1 / 3)
        self.assertAlmostEqual(sum(normalized_transformation_weights(12)), 1.0)

    def test_transformation_traits_keep_their_original_names(self):
        self.assertEqual(COMBAT_TRAIT_REGISTRY["dragon_pressure"]["name"], "真龙威压")
        self.assertEqual(COMBAT_TRAIT_REGISTRY["prevent_defeat_once"]["name"], "涅槃")
        self.assertEqual(COMBAT_TRAIT_REGISTRY["damage_bonus_5"]["name"], "庚金杀伐")
        self.assertEqual(COMBAT_TRAIT_REGISTRY["round4_regen_10"]["name"], "朱焰回生")
        self.assertEqual(COMBAT_TRAIT_REGISTRY["morale_drain_5"]["name"], "修罗战意")
        self.assertEqual(COMBAT_TRAIT_REGISTRY["first_round_full_state"]["name"], "玄武镇界")

    def test_capacity_space_and_active_order_are_managed(self):
        self.engine.manage_transformation(self.created["id"], "FORM_PHOENIX", "store")
        self.engine.manage_transformation(self.created["id"], "FORM_AZURE_LUAN", "store")
        self.engine.manage_transformation(self.created["id"], "FORM_MOUNTAIN_APE", "store")
        first = self.engine.manage_transformation(self.created["id"], "FORM_PHOENIX", "activate")
        second = self.engine.manage_transformation(self.created["id"], "FORM_AZURE_LUAN", "activate")
        system = second["transformation_system"]
        self.assertEqual(len(system["stored"]), 3)
        self.assertEqual(system["active"], ["FORM_PHOENIX", "FORM_AZURE_LUAN"])
        active = {entry["id"]: entry["weight"] for entry in system["stored"] if entry["active"]}
        self.assertAlmostEqual(active["FORM_PHOENIX"], 2 / 3, places=5)
        self.assertAlmostEqual(active["FORM_AZURE_LUAN"], 1 / 3, places=5)
        self.assertFalse(any(trait["id"] == "prevent_defeat_once" for trait in system["traits"]))
        with self.assertRaisesRegex(ValueError, "空间已满"):
            self.engine.manage_transformation(self.created["id"], "FORM_MOUNTAIN_APE", "activate")
        removed = self.engine.manage_transformation(self.created["id"], "FORM_MOUNTAIN_APE", "remove")
        self.assertNotIn("FORM_MOUNTAIN_APE", [entry["id"] for entry in removed["transformation_system"]["stored"]])
        self.assertIn("FORM_MOUNTAIN_APE", [entry["id"] for entry in removed["transformation_system"]["known"]])
        self.assertIsNotNone(first["transformation_system"]["technique"])

    def test_switching_weight_order_changes_blended_profile(self):
        self.engine.manage_transformation(self.created["id"], "FORM_PHOENIX", "store")
        self.engine.manage_transformation(self.created["id"], "FORM_AZURE_LUAN", "store")
        self.engine.manage_transformation(self.created["id"], "FORM_PHOENIX", "activate")
        self.engine.manage_transformation(self.created["id"], "FORM_AZURE_LUAN", "activate")
        game = self.engine.store.load(self.created["id"])
        before = active_transformation_profile(game.player)["stat_multipliers"]["sustain"]
        self.engine.manage_transformation(self.created["id"], "FORM_AZURE_LUAN", "promote")
        game = self.engine.store.load(self.created["id"])
        after = active_transformation_profile(game.player)["stat_multipliers"]["sustain"]
        self.assertGreater(after, before)

    def test_technique_grants_no_forms_and_material_purity_controls_strength(self):
        game = self.engine.store.load(self.created["id"])
        self.assertNotIn("FORM_TRUE_DRAGON", game.player.known_transformations)
        self.engine.absorb_transformation_material(self.created["id"], "true_dragon_blood_trace", stat_id="might")
        game = self.engine.store.load(self.created["id"])
        mastery = game.player.transformation_mastery["FORM_TRUE_DRAGON"]
        self.assertAlmostEqual(mastery["stats"]["might"], 0.00045)
        self.assertAlmostEqual(mastery["purity"], 0.000075)
        dragon = form_potency(TRANSFORMATION_CATALOG["FORM_TRUE_DRAGON"], mastery["purity"])
        ape = form_potency(TRANSFORMATION_CATALOG["FORM_MOUNTAIN_APE"], 0.12)
        self.assertLess(dragon, ape)
        public = self.engine.get_game(self.created["id"])["transformation_system"]
        form = next(entry for entry in public["known"] if entry["id"] == "FORM_TRUE_DRAGON")
        self.assertAlmostEqual(form["remaining"], 0.999925)
        self.assertEqual(next(stat for stat in form["stats"] if stat["id"] == "might")["progress"], 0.00045)

    def test_two_materials_can_be_purified_before_absorption(self):
        game = self.engine.store.load(self.created["id"])
        game.player.transformation_mastery.pop("FORM_MOUNTAIN_APE", None)
        game.player.known_transformations.remove("FORM_MOUNTAIN_APE")
        game.player.inventory = [item for item in game.player.inventory if item.id != "mountain_ape_soul"]
        add_item(game.player, "mountain_ape_blood", 2)
        self.engine.store.save(game)
        self.engine.absorb_transformation_material(self.created["id"], "mountain_ape_blood", True, "guard")
        reloaded = self.engine.store.load(self.created["id"])
        mastery = reloaded.player.transformation_mastery["FORM_MOUNTAIN_APE"]
        self.assertAlmostEqual(mastery["stats"]["guard"], 0.036432)
        self.assertAlmostEqual(mastery["purity"], 0.006072)
        self.assertGreater(0.036432, 2 * 0.02 * 0.45)

    def test_transformation_manual_progression_covers_upper_and_demonic_worlds(self):
        transformation_ids = {
            technique_id for technique_id, technique in TECHNIQUE_CATALOG.items()
            if technique.category == "transformation"
        }
        self.assertEqual(len(transformation_ids), 11)
        market_rows = [
            row for row in MARKET_GOODS
            if row["kind"] == "technique" and row["content_id"] in transformation_ids
        ]
        self.assertTrue({"human", "spirit", "demon", "true_demon"}.issubset({row["world"] for row in market_rows}))
        self.assertTrue(all(int(row["tier"]) >= 4 for row in market_rows))
        self.assertEqual(TECHNIQUE_CATALOG["TECH_PRIMORDIAL_DEMON_TRANSFORMATION"].transformation_capacity, 10)
        self.assertEqual(TECHNIQUE_CATALOG["TECH_PRIMORDIAL_DEMON_TRANSFORMATION"].transformation_space, 5)
        for technique_id in transformation_ids:
            technique = TECHNIQUE_CATALOG[technique_id]
            self.assertLessEqual(technique.transformation_space, technique.transformation_capacity)

    def test_batch_purification_uses_thirty_percent_pair_bonus_and_odd_tail(self):
        game = self.engine.store.load(self.created["id"])
        game.player.transformation_mastery.pop("FORM_MOUNTAIN_APE", None)
        game.player.known_transformations.remove("FORM_MOUNTAIN_APE")
        game.player.inventory = [item for item in game.player.inventory if item.id != "mountain_ape_soul"]
        add_item(game.player, "mountain_ape_blood", 5)
        self.engine.store.save(game)

        shown = self.engine.batch_absorb_transformation_material(
            self.created["id"], "mountain_ape_blood", "purified", "guard",
        )
        standard_pair = absorption_gain(0.02, True)
        expected = standard_pair * (1 + BATCH_PAIR_BONUS) * 2 + absorption_gain(0.02)
        form = next(entry for entry in shown["transformation_system"]["known"] if entry["id"] == "FORM_MOUNTAIN_APE")
        guard = next(stat for stat in form["stats"] if stat["id"] == "guard")
        self.assertAlmostEqual(guard["progress"], expected, places=6)
        reloaded = self.engine.store.load(self.created["id"])
        self.assertFalse(any(item.id == "mountain_ape_blood" for item in reloaded.player.inventory))
        record = reloaded.history[-1]
        self.assertEqual(record.event_id, "SYS_TRANSFORMATION_MATERIAL_BATCH")
        self.assertEqual(record.state_diff["pairs"], 2)
        self.assertEqual(record.state_diff["singles"], 1)
        self.assertEqual(record.state_diff["pair_bonus"], 0.30)

    def test_batch_absorption_stops_as_soon_as_selected_stat_is_full(self):
        game = self.engine.store.load(self.created["id"])
        stats = game.player.transformation_mastery["FORM_PHOENIX"]["stats"]
        stats["might"] = 0.9999
        add_item(game.player, "phoenix_blood", 10)
        self.engine.store.save(game)

        shown = self.engine.batch_absorb_transformation_material(
            self.created["id"], "phoenix_blood", "direct", "might",
        )
        form = next(
            entry for entry in [*shown["transformation_system"]["known"], *shown["transformation_system"]["stored"]]
            if entry["id"] == "FORM_PHOENIX"
        )
        might = next(stat for stat in form["stats"] if stat["id"] == "might")
        self.assertEqual(might["progress"], 1.0)
        reloaded = self.engine.store.load(self.created["id"])
        remaining = next(item.quantity for item in reloaded.player.inventory if item.id == "phoenix_blood")
        self.assertEqual(remaining, 9)
        self.assertEqual(reloaded.history[-1].state_diff["quantity"], -1)


if __name__ == "__main__":
    unittest.main()
