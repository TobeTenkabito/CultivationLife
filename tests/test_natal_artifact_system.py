import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.crafting_system import store_crafted_artifact
from cultivation_life.rules import add_item, combat_power


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class NatalArtifactSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.engine = GameEngine(root)
        self.game_id = self.engine.create_game(
            "剑主", "heavenly", "dao", 3101, preset_id="core",
        )["id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_core_realm_can_bind_inventory_artifact_without_losing_base_power(self):
        before = self.engine.get_game(self.game_id)
        self.assertTrue(before["natal_artifact"]["visible"])
        self.assertIn("starfall_blade", {row["id"] for row in before["natal_artifact"]["candidates"]})
        before_power = before["player"]["combat_power"]
        shown = self.engine.natal_artifact_action(self.game_id, "bind", "starfall_blade")
        self.assertTrue(shown["natal_artifact"]["bound"])
        self.assertEqual(shown["natal_artifact"]["level"], 1)
        self.assertEqual(shown["natal_artifact"]["unlocked_slots"], 2)
        self.assertEqual(shown["player"]["combat_power"], before_power)
        bound = next(row for row in shown["player"]["inventory"] if row.get("is_natal_artifact"))
        self.assertEqual(bound["id"], "starfall_blade")
        saved = self.engine.store.load(self.game_id)
        self.assertNotIn("starfall_blade", {row.id for row in saved.player.inventory})

    def test_refining_levels_artifact_and_unlocks_slots(self):
        self.engine.natal_artifact_action(self.game_id, "bind", "starfall_blade")
        for _ in range(3):
            shown = self.engine.natal_artifact_action(self.game_id, "refine")
        self.assertEqual(shown["natal_artifact"]["level"], 2)
        self.assertGreater(shown["natal_artifact"]["bonuses"]["combat_bonus"], 380)
        game = self.engine.store.load(self.game_id)
        old_level, new_level = self.engine._add_natal_artifact_experience(game, 6)
        self.assertEqual((old_level, new_level), (2, 3))
        self.assertEqual(self.engine._natal_slots_for_level(new_level), 3)

    def test_geng_essence_socket_adds_power_and_can_be_recovered(self):
        self.engine.natal_artifact_action(self.game_id, "bind", "starfall_blade")
        game = self.engine.store.load(self.game_id)
        game.player.realm_index = 4
        add_item(game.player, "geng_essence")
        self.engine.store.save(game)
        shown = self.engine.natal_artifact_action(self.game_id, "socket", "geng_essence", 0)
        self.assertEqual(shown["natal_artifact"]["slots"][0]["name"], "庚精")
        self.assertEqual(shown["natal_artifact"]["bonuses"]["combat_bonus"], 2180)
        shown = self.engine.natal_artifact_action(self.game_id, "unsocket", slot_index=0)
        self.assertIsNone(shown["natal_artifact"]["slots"][0]["material_id"])
        self.assertIn("geng_essence", {row["id"] for row in shown["player"]["inventory"]})

    def test_thunder_material_reduces_real_tribulation_damage(self):
        self.engine.natal_artifact_action(self.game_id, "bind", "starfall_blade")
        game = self.engine.store.load(self.game_id)
        game.player.realm_index = 5
        add_item(game.player, "thunder_calamity_jade")
        self.engine.store.save(game)
        self.engine.natal_artifact_action(self.game_id, "socket", "thunder_calamity_jade", 0)
        game = self.engine.store.load(self.game_id)
        self.engine._ensure_natal_artifact(game)
        self.assertAlmostEqual(self.engine._tribulation_damage_reduction(game.player), 0.03)

    def test_material_catalog_covers_all_realm_bands_and_ancient_god_effects(self):
        materials = WORLD_SYSTEMS["natal_artifact"]["materials"]
        by_id = {row["item_id"]: row for row in materials}
        self.assertEqual(set(range(3, 13)), {int(row["minimum_realm"]) for row in materials})
        expected_gods = {
            "dijiang_tear", "zhulong_breath", "jumang_feather", "rushou_scale",
            "gonggong_water", "zhurong_flame", "qiangliang_thunder", "xizi_lightning",
            "xuanming_rain", "feilian_wind", "shebishi_orb", "houtu_clay",
        }
        self.assertTrue(expected_gods <= set(by_id))
        celestial_market = {
            row["content_id"] for row in MARKET_GOODS
            if row.get("world") == "celestial" and row["kind"] == "item"
        }
        self.assertTrue(expected_gods <= celestial_market)

    def test_socketed_materials_export_data_driven_combat_effects(self):
        self.engine.natal_artifact_action(self.game_id, "bind", "starfall_blade")
        game = self.engine.store.load(self.game_id)
        game.player.realm_index = 10
        game.natal_artifact["level"] = 12
        add_item(game.player, "dijiang_tear")
        add_item(game.player, "jumang_feather")
        self.engine.store.save(game)
        self.engine.natal_artifact_action(self.game_id, "socket", "dijiang_tear", 0)
        self.engine.natal_artifact_action(self.game_id, "socket", "jumang_feather", 1)
        game = self.engine.store.load(self.game_id)
        effects = self.engine._natal_artifact_combat_effects(game)
        self.assertIn("enemy_escape_lock", effects[0]["traits"])
        self.assertEqual(effects[1]["player_stat_multipliers"]["sense"], 1.2)

    def test_combination_artifact_uses_the_same_natal_levels_and_sockets(self):
        game = self.engine.store.load(self.game_id)
        artifact = {
            "id":"crafted-natal-test", "name":"玄元试剑", "quality_name":"精制",
            "mold_name":"剑器胎模", "actual_stats":{
                "combat_power":1000, "max_hp":200, "max_mp":300,
                "opportunity_efficiency":.02, "tribulation_reduction":.01,
            },
            "combat_effects":[], "anchor_value":10000, "description":"原始炼制描述不得丢失。",
            "is_natal":False,
        }
        store_crafted_artifact(game.player, artifact)
        self.engine.store.save(game)
        before = self.engine.get_game(self.game_id)["player"]["combat_power"]

        bound = self.engine.crafted_artifact_action(self.game_id, artifact["id"], "natal")
        self.assertEqual(bound["natal_artifact"]["crafted_artifact_id"], artifact["id"])
        self.assertEqual(bound["natal_artifact"]["description"], artifact["description"])
        self.assertEqual(bound["player"]["combat_power"], before)
        for _ in range(3):
            refined = self.engine.natal_artifact_action(self.game_id, "refine")
        self.assertEqual(refined["natal_artifact"]["level"], 2)
        self.assertGreater(refined["player"]["combat_power"], before)

        game = self.engine.store.load(self.game_id)
        game.player.realm_index = 4
        add_item(game.player, "geng_essence")
        self.engine.store.save(game)
        socketed = self.engine.natal_artifact_action(self.game_id, "socket", "geng_essence", 0)
        self.assertEqual(socketed["natal_artifact"]["slots"][0]["name"], "庚精")
        unbound = self.engine.crafted_artifact_action(self.game_id, artifact["id"], "unbind_natal")
        self.assertFalse(unbound["natal_artifact"]["bound"])
        self.assertTrue(any(row["id"] == artifact["id"] for row in unbound["player"]["inventory"]))
        self.assertTrue(any(row["id"] == "geng_essence" for row in unbound["player"]["inventory"]))


if __name__ == "__main__":
    unittest.main()
