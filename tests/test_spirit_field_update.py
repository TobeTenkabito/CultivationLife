import math
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class SpiritFieldUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def _field_game(self):
        made = self.engine.create_game("药农", "supreme_wood", "dao", 12001, preset_id="core")
        game = self.engine.store.load(made["id"])
        game.player.spirit_field["reclaimed_qing"] = 1
        add_item(game.player, "purple_cloud_ginseng_seed", 1)
        self.engine.store.save(game)
        return made["id"]

    def test_plant_growth_rounds_down_by_magnitude_and_preserves_specific_years(self):
        game_id = self._field_game()
        planted = self.engine.plant_spirit_crop(game_id, "purple_cloud_ginseng")
        self.assertEqual(planted["spirit_field"]["free_qing"], 0)
        game = self.engine.store.load(game_id)
        game.player.spirit_field["plots"][0]["growth_years"] = 201
        self.engine.store.save(game)
        shown = self.engine.present(game)
        crop = shown["spirit_field"]["plots"][0]
        self.assertEqual(crop["display_years"], 200)
        self.assertFalse(crop["best"])
        harvested = self.engine.harvest_spirit_crop(game_id, crop["id"])
        item = next(row for row in harvested["player"]["inventory"] if row.get("plant_id") == "purple_cloud_ginseng")
        self.assertEqual(item["quantity"], 1)
        self.assertEqual(item["plant_years"], 200)
        alchemy = next(row for row in harvested["art_skills"] if row["id"] == "alchemy")
        self.assertGreater(alchemy["experience"], 0)

    def test_irrigation_costs_mp_and_grants_spirit_control_experience(self):
        game_id = self._field_game()
        planted = self.engine.plant_spirit_crop(game_id, "purple_cloud_ginseng")
        crop = planted["spirit_field"]["plots"][0]
        before_mp = planted["player"]["mp"]
        shown = self.engine.irrigate_spirit_crop(game_id, crop["id"])
        self.assertLess(shown["player"]["mp"], before_mp)
        self.assertGreater(shown["spirit_field"]["plots"][0]["growth_years"], 0)
        skill = next(row for row in shown["art_skills"] if row["id"] == "spirit_control")
        self.assertGreater(skill["experience"], 0)

    def test_same_mp_fraction_accelerates_far_more_at_mahayana_than_qi(self):
        low_id = self._field_game()
        low = self.engine.store.load(low_id)
        low.player.realm_index = 1
        low.player.mp = 10**9
        self.engine.store.save(low)
        low_crop = self.engine.plant_spirit_crop(low_id, "purple_cloud_ginseng")["spirit_field"]["plots"][0]
        low_max = self.engine._public_spirit_field(self.engine.store.load(low_id).player)["max_mp"]
        low_result = self.engine.irrigate_spirit_crop(low_id, low_crop["id"], low_max * 0.1)
        low_growth = low_result["spirit_field"]["plots"][0]["growth_years"]

        high = self.engine.create_game("大乘药农", "none", "dao", 12003, preset_id="mahayana")
        high_game = self.engine.store.load(high["id"])
        high_game.player.spirit_field["reclaimed_qing"] = 1
        high_game.player.mp = 10**12
        add_item(high_game.player, "purple_cloud_ginseng_seed", 1)
        self.engine.store.save(high_game)
        high_crop = self.engine.plant_spirit_crop(high["id"], "purple_cloud_ginseng")["spirit_field"]["plots"][0]
        high_max = self.engine._public_spirit_field(self.engine.store.load(high["id"]).player)["max_mp"]
        high_result = self.engine.irrigate_spirit_crop(high["id"], high_crop["id"], high_max * 0.1)
        high_growth = high_result["spirit_field"]["plots"][0]["growth_years"]
        self.assertGreater(high_growth, low_growth * 1000)

    def test_mystic_vine_requires_either_universal_booster_before_mp_irrigation(self):
        made = self.engine.create_game("仙藤培育", "none", "dao", 12005, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        game.player.spirit_field["reclaimed_qing"] = 1
        add_item(game.player, "mystic_heaven_vine_seed", 1)
        add_item(game.player, "formless_sumeru_water", 1)
        game.player.mp = 10**12
        self.engine.store.save(game)
        planted = self.engine.plant_spirit_crop(made["id"], "mystic_heaven_vine")
        crop = planted["spirit_field"]["plots"][0]
        mp_amount = math.ceil(planted["spirit_field"]["irrigation_min_mp"])
        with self.assertRaisesRegex(ValueError, "须先吸收"):
            self.engine.irrigate_spirit_crop(made["id"], crop["id"], mp_amount)
        shown = self.engine.irrigate_spirit_crop(
            made["id"], crop["id"], mp_amount, "formless_sumeru_water",
        )
        self.assertTrue(shown["spirit_field"]["plots"][0]["booster_unlocked"])
        self.assertFalse(any(row["id"] == "formless_sumeru_water" for row in shown["player"]["inventory"]))

    def test_black_market_pays_more_for_spirit_plants(self):
        game_id = self._field_game()
        game = self.engine.store.load(game_id)
        add_item(game.player, "purple_cloud_ginseng_hundred", 2)
        self.engine.store.save(game)
        before = self.engine._spirit_stones(game.player)
        market = self.engine.sell_spirit_plant(game_id, "purple_cloud_ginseng_hundred")
        market_gain = market["market"]["spirit_stones"] - before
        game = self.engine.store.load(game_id)
        location = self.engine.maps.normalize_location(game.player.world, game.player.location_id)
        game.auction_state = {
            "id":"plant-black", "status":"black_market", "world":game.player.world,
            "location_id":location, "location_name":self.engine.maps.location(game.player.world, location)["name"],
        }
        self.engine.store.save(game)
        before_black = self.engine._spirit_stones(game.player)
        black = self.engine.sell_black_market_asset(game_id, "item", "purple_cloud_ginseng_hundred")
        self.assertGreater(black["auction_system"]["spirit_stones"] - before_black, market_gain)

    def test_old_player_save_receives_field_and_five_art_defaults(self):
        made = self.engine.create_game("旧档", "supreme_wood", "dao", 12002)
        game = self.engine.store.load(made["id"])
        saved = game.to_dict()
        saved["player"].pop("spirit_field", None)
        saved["player"].pop("art_experience", None)
        from cultivation_life.models import GameState
        restored = GameState.from_dict(saved)
        self.assertEqual(restored.player.spirit_field["reclaimed_qing"], 0)
        self.assertEqual(set(restored.player.art_experience), {"alchemy", "refining", "formation", "talisman", "spirit_control"})

    def test_arbitrary_medicinal_mix_can_refine_a_selected_pill(self):
        game_id = self._field_game()
        game = self.engine.store.load(game_id)
        self.engine._add_harvested_plant(game.player, "purple_cloud_ginseng", 100)
        self.engine._add_harvested_plant(game.player, "nine_curve_herb", 3000)
        game.player.mp = 10**9
        self.engine.store.save(game)
        materials = [{"item_id":"harvest:purple_cloud_ginseng:100", "quantity":1}, {"item_id":"harvest:nine_curve_herb:3000", "quantity":1}]
        shown = self.engine.refine_pill(game_id, "foundation_pill", materials)
        self.assertFalse(any(row["id"].startswith("harvest:") for row in shown["player"]["inventory"]))
        self.assertGreater(next(row for row in shown["art_skills"] if row["id"] == "alchemy")["experience"], 0)

    def test_special_plants_unlock_sword_passive_power_and_next_thunder_guard(self):
        made = self.engine.create_game("灵植试验", "none", "dao", 12004, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        vine = self.engine._add_harvested_plant(game.player, "mystic_heaven_vine", 10000)
        flower = self.engine._add_harvested_plant(game.player, "nebula_manjushaka", 5000)
        bamboo = self.engine._add_harvested_plant(game.player, "golden_thunder_bamboo", 10000)
        self.engine.store.save(game)
        from cultivation_life.rules import combat_power
        with_bamboo = combat_power(game.player)
        game.player.inventory.remove(bamboo)
        without_bamboo = combat_power(game.player)
        game.player.inventory.append(bamboo)
        self.assertAlmostEqual(with_bamboo / without_bamboo, 1.01, places=3)
        self.engine.store.save(game)
        sword = self.engine.use_harvested_plant(made["id"], vine.id)
        self.assertTrue(any(row["id"] == "mystic_heaven_sword" for row in sword["player"]["inventory"]))
        guarded = self.engine.use_harvested_plant(made["id"], flower.id)
        self.assertEqual(guarded["player"]["next_thunder_damage_reduction"], 0.10)


if __name__ == "__main__":
    unittest.main()
