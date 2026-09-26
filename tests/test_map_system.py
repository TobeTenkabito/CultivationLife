import tempfile
import unittest
import json
from pathlib import Path

from cultivation_life.content_registry import CONTENT_DOCUMENTS, MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.system.map_system import MapCatalog
from cultivation_life.rules import TECHNIQUE_CATALOG, assign_technique


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class MapCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = MapCatalog(CONTENT_DOCUMENTS["maps.json"], set(WORLD_SYSTEMS["world_profiles"]))

    def test_all_world_interfaces_have_connected_maps(self):
        self.assertEqual(set(self.catalog.worlds), set(WORLD_SYSTEMS["world_profiles"]))
        human_names = {row["name"] for row in self.catalog.public_map("human", "wudi_plain", 4, "人界")["locations"]}
        self.assertTrue({"无棣原", "穆陵沙漠", "岚疆草原", "风语群岛", "澜沧海"}.issubset(human_names))
        self.assertEqual(len(human_names), 10)

    def test_lower_and_middle_world_maps_expand_while_upper_worlds_stay_fixed(self):
        expected_counts = {
            "human":10, "spirit":10, "demon":9, "true_demon":9,
            "monster_realm":16, "phantom_underworld":16, "hell":12,
        }
        self.assertEqual(
            {world:len(self.catalog.worlds[world]["locations"]) for world in expected_counts},
            expected_counts,
        )
        self.assertEqual(
            {world:len(self.catalog.worlds[world]["locations"]) for world in ("celestial", "asura", "nether", "reincarnation")},
            {"celestial":3, "asura":5, "nether":9, "reincarnation":3},
        )

    def test_monster_and_ghost_maps_live_in_base_content(self):
        base = json.loads((SOURCE_ROOT / "content" / "maps.json").read_text(encoding="utf-8"))
        monster = json.loads((SOURCE_ROOT / "dlc" / "monster-bloodlines" / "content" / "maps.json").read_text(encoding="utf-8"))
        ghost = json.loads((SOURCE_ROOT / "dlc" / "ghost-reincarnation" / "content" / "maps.json").read_text(encoding="utf-8"))
        self.assertEqual(monster["worlds"], {})
        self.assertEqual(ghost["worlds"], {})
        self.assertIn("monster_realm", base["worlds"])
        self.assertIn("yin_market_capital", {row["id"] for row in base["worlds"]["hell"]["locations"]})
        self.assertIn("tiger_roar_cliff", {row["id"] for row in base["worlds"]["monster_realm"]["locations"]})
        self.assertIn("hollow_moon_chasm", {row["id"] for row in base["worlds"]["phantom_underworld"]["locations"]})
        self.assertIn("yin_market_capital", {row["id"] for row in base["worlds"]["hell"]["locations"]})

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
        formerly_blocked = self.catalog.travel_plan("human", "wudi_plain", "cangwu_mountains", 1)
        fast = self.catalog.travel_plan("human", "wudi_plain", "lanjiang_steppe", 4)
        self.assertLess(near.years, far.years)
        self.assertLess(fast.years, near.years)
        self.assertEqual(far.status, "lethal")
        self.assertEqual(formerly_blocked.status, "lethal")
        self.assertIn("必然身死道消", formerly_blocked.warning)
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

    def test_low_realm_can_enter_any_gated_map_but_dies_on_arrival(self):
        created = self.engine.create_game("越境者", "supreme_earth", "dao", 2305)
        result = self.engine.travel_map(created["id"], "cangwu_mountains")
        self.assertFalse(result["player"]["alive"])
        self.assertEqual(result["player"]["location_id"], "cangwu_mountains")
        self.assertIn("境界低于此地要求", result["player"]["death_reason"])
        self.assertTrue(any(
            row["event_id"] == "SYS_MAP_TRAVEL" and row["result"] == "dead"
            for row in result["history"]
        ))

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
