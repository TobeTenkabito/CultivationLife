import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp, opportunity_required, qi_level_threshold, stage_name


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class AsuraSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.engine = GameEngine(root)

    def tearDown(self):
        self.temp.cleanup()

    def _prepared_demon_lord(self):
        shown = self.engine.create_game("叩关魔尊", "mutated_yin", "demonic", 14001, preset_id="demonic_core")
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.world = "true_demon"
        player.location_id = self.engine.maps.default_location("true_demon")
        player.realm_index, player.layer = 8, 9
        player.opportunity = opportunity_required(player)
        player.qi_experience["demon"] = qi_level_threshold(30)
        player.karma = 0
        player.sha_qi = 120
        player.heart_demon = 0
        player.faction_combat_bonus = 100_000_000
        player.hp, player.mp = max_hp(player), max_mp(player)
        self.engine.store.save(game)
        return shown["id"]

    def test_asura_content_has_realms_maps_factions_items_and_techniques(self):
        self.assertEqual(
            [WORLD_SYSTEMS["demonic_cultivation"]["realm_names"][str(index)] for index in range(9, 13)],
            ["迦楼罗", "紧那罗", "摩睺罗", "阿修罗"],
        )
        self.assertTrue(WORLD_SYSTEMS["world_profiles"]["asura"]["enabled"])
        self.assertEqual(len(self.engine.maps.worlds["asura"]["locations"]), 5)
        asura_factions = [sect for sect in self.engine._new_sects().values() if sect.world == "asura"]
        self.assertEqual({sect.name for sect in asura_factions}, {"修罗战庭", "血月魔宫", "寂灭海宗"})
        self.assertTrue({
            "asura_blood_crystal", "heavenly_demon_heart_marrow", "war_soul_banner",
            "annihilation_demon_blade", "wusheng_dao_embryo", "primordial_asura_bone",
        } <= set(ITEM_CATALOG))
        self.assertTrue({
            "TECH_ASURA_WAR_HEAVEN", "TECH_BLOOD_SEA_IMPERISHABLE",
            "TECH_MYRIAD_CALAMITY_DEMON_FORM", "TECH_ANNIHILATION_SKY_BLADE",
        } <= set(TECHNIQUE_CATALOG))

    def test_demonic_quick_start_is_born_in_demon_world(self):
        shown = self.engine.create_game("魔界新生", "none", "dao", 14002, preset_id="demonic_core")
        self.assertEqual((shown["player"]["path"], shown["player"]["world"]), ("demonic", "demon"))
        self.assertEqual(shown["player"]["realm_name"], "魔丹初期·1层")
        self.assertEqual(shown["player"]["technique"]["id"], "TECH_WANMO")

    def test_nine_stage_asura_ascension_and_locked_upper_breakthroughs(self):
        game_id = self._prepared_demon_lord()
        shown = self.engine.begin_asura_ascension(game_id)
        self.assertEqual(shown["trial"]["kind"], "asura_ascension")
        self.assertEqual(shown["trial"]["total_steps"], 9)
        for _ in range(9):
            game = self.engine.store.load(game_id)
            game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
            self.engine.store.save(game)
            choice_id = self.engine.get_game(game_id)["pending_event"]["choices"][0]["id"]
            shown = self.engine.choose(game_id, choice_id)
        self.assertEqual((shown["player"]["world"], shown["player"]["realm_index"]), ("asura", 9))
        self.assertEqual(shown["player"]["realm_name"], "迦楼罗")
        self.assertFalse(shown["breakthrough"]["enabled"])
        self.assertIsNone(shown["pending_event"])
        self.assertTrue(shown["market"]["available"])
        self.assertEqual(shown["map"]["world_name"], "修罗界")
        self.assertEqual(len(shown["faction"]["available"]), 3)

        descended = self.engine.cross_world(game_id, "true_demon")
        self.assertTrue(descended["world_travel"]["can_return_asura"])
        self.assertFalse(descended["world_travel"]["can_ascend_asura"])
        restored = self.engine.cross_world(game_id, "asura")
        self.assertEqual(restored["player"]["realm_name"], "迦楼罗")

    def test_asura_random_events_do_not_mix_with_celestial_or_lower_world_events(self):
        game_id = self._prepared_demon_lord()
        game = self.engine.store.load(game_id)
        game.player.world = "asura"
        game.player.location_id = self.engine.maps.default_location("asura")
        game.player.realm_index, game.player.layer = 9, 1
        for seed in range(20):
            event = self.engine._select_event(game, "travel", random.Random(seed))
            self.assertIsNotNone(event)
            self.assertIn("world:asura", event.get("tags", []))

    def test_asura_npc_realm_names_use_the_four_world_specific_titles(self):
        game_id = self._prepared_demon_lord()
        game = self.engine.store.load(game_id)
        game.player.world = "asura"
        game.player.realm_index = 12
        self.assertEqual(stage_name(game.player), "阿修罗")
        names = {
            self.engine._npc_realm_name(npc)
            for sect in game.sects.values() if sect.world == "asura"
            for npc in sect.npcs
        }
        self.assertTrue({"迦楼罗", "紧那罗", "摩睺罗", "阿修罗"} <= names)


if __name__ == "__main__":
    unittest.main()
