import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import CONTENT_DOCUMENTS, MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.map_system import MapCatalog
from cultivation_life.rules import TECHNIQUE_CATALOG, assign_technique


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class MapCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = MapCatalog(CONTENT_DOCUMENTS["maps.json"], set(WORLD_SYSTEMS["world_profiles"]))

    def test_all_world_interfaces_have_connected_maps(self):
        self.assertEqual(set(self.catalog.worlds), set(WORLD_SYSTEMS["world_profiles"]))
        human_names = {row["name"] for row in self.catalog.public_map("human", "wudi_plain", 4, "人界")["locations"]}
        self.assertEqual(human_names, {"无棣原", "穆陵沙漠", "岚疆草原", "风语群岛", "澜沧海"})

    def test_every_location_has_distinct_four_qi_gain_efficiencies(self):
        expected = {"spirit", "demon", "monster", "yin"}
        for world in self.catalog.worlds:
            shown = self.catalog.public_map(world, self.catalog.default_location(world), 8, world)
            for location in shown["locations"]:
                self.assertEqual(set(location["qi_gain_efficiencies"]), expected)
                self.assertTrue(all(value >= 0 for value in location["qi_gain_efficiencies"].values()))
        plain = self.catalog.qi_gain_efficiencies("human", "wudi_plain")
        desert = self.catalog.qi_gain_efficiencies("human", "muling_desert")
        self.assertNotEqual(plain, desert)
        self.assertGreater(plain["spirit"], desert["spirit"])
        self.assertLess(plain["demon"], desert["demon"])

    def test_distance_speed_and_lethal_realm_gate(self):
        near = self.catalog.travel_plan("human", "wudi_plain", "lanjiang_steppe", 1)
        far = self.catalog.travel_plan("human", "wudi_plain", "lancang_sea", 1)
        fast = self.catalog.travel_plan("human", "wudi_plain", "lanjiang_steppe", 4)
        self.assertLess(near.years, far.years)
        self.assertLess(fast.years, near.years)
        self.assertEqual(far.status, "lethal")
        self.assertEqual(self.catalog.travel_plan("human", "wudi_plain", "lancang_sea", 4).status, "ok")

    def test_market_and_treasure_sources_are_regionally_partitioned(self):
        plain = {row["content_id"] for row in self.catalog.localize_goods(MARKET_GOODS, "human", "wudi_plain", "market")}
        desert = {row["content_id"] for row in self.catalog.localize_goods(MARKET_GOODS, "human", "muling_desert", "market")}
        treasure = {row["content_id"] for row in self.catalog.localize_goods(MARKET_GOODS, "human", "wudi_plain", "treasure")}
        self.assertNotEqual(plain, desert)
        self.assertNotEqual(plain, treasure)


class MapEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def test_create_and_safe_travel_advance_the_shared_world_clock(self):
        created = self.engine.create_game("远客", "supreme_metal", "dao", 2301, preset_id="nascent")
        start_age = created["player"]["age"]
        result = self.engine.travel_map(created["id"], "lanjiang_steppe")
        self.assertEqual(result["player"]["location_id"], "lanjiang_steppe")
        self.assertEqual(result["player"]["age"], start_age + 2)
        self.assertEqual(result["market"]["location_id"], "lanjiang_steppe")
        self.assertTrue(any(row["event_id"] == "SYS_MAP_TRAVEL" for row in result["history"]))

    def test_core_cultivator_forcing_lancang_crossing_dies(self):
        created = self.engine.create_game("逐浪", "supreme_water", "dao", 2302, preset_id="core")
        result = self.engine.travel_map(created["id"], "lancang_sea")
        self.assertFalse(result["player"]["alive"])
        self.assertEqual(result["player"]["location_id"], "lancang_sea")
        self.assertIn("澜沧海", result["player"]["death_reason"])

    def test_legacy_save_without_location_is_migrated(self):
        created = self.engine.create_game("旧卷", "supreme_earth", "dao", 2303)
        game = self.engine.store.load(created["id"])
        game.player.location_id = None
        self.engine.store.save(game)
        loaded = self.engine.get_game(created["id"])
        self.assertEqual(loaded["player"]["location_id"], "wudi_plain")

    def test_opportunity_awards_qi_experience_using_current_region(self):
        created = self.engine.create_game("择地纳气", "supreme_metal", "dao", 2304)
        game = self.engine.store.load(created["id"])
        assign_technique(game.player, TECHNIQUE_CATALOG["TECH_COMMON_QI"], "main")
        assign_technique(game.player, TECHNIQUE_CATALOG["TECH_BLOOD_RIVER"], "support")
        self.engine._add_opportunity(game.player, 10)
        self.assertEqual(game.player.qi_experience["spirit"], 10)
        self.assertEqual(game.player.qi_experience["demon"], 4.5)
        game.player.qi_experience = {source: 0.0 for source in game.player.qi_experience}
        game.player.location_id = "muling_desert"
        self.engine._add_opportunity(game.player, 10)
        self.assertEqual(game.player.qi_experience["spirit"], 7.5)
        self.assertEqual(game.player.qi_experience["demon"], 8.5)


if __name__ == "__main__":
    unittest.main()
