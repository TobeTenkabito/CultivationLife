import json
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.models import HistoryRecord
from cultivation_life.rules import add_item


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class AchievementSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.save_directory = Path(self.temp.name) / "data" / "saves"
        self.engine = GameEngine(SOURCE_ROOT, self.save_directory)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_game_creates_cross_save_metadata_and_unlocks_start_condition(self):
        created = self.engine.create_game("沈砚", "otherworld", "dao", 991)
        metadata_path = self.save_directory / "global_metadata.json"

        self.assertTrue(metadata_path.is_file())
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["schema_version"], 1)
        self.assertIn("cultivation_otherworld_root", metadata["achievements"])
        self.assertIn("主角配置", [row["name"] for row in created["new_achievements"]])
        self.assertNotIn("global_metadata", [row["id"] for row in self.engine.list_games()])

    def test_unlocked_achievement_is_shared_and_not_announced_twice(self):
        first = self.engine.create_game("甲", "otherworld", "dao", 992)
        self.assertIn("主角配置", [row["name"] for row in first["new_achievements"]])

        second = self.engine.create_game("乙", "otherworld", "dao", 993)
        self.assertNotIn("主角配置", [row["name"] for row in second["new_achievements"]])
        catalog = self.engine.list_achievements()
        achievement = next(row for row in catalog["achievements"] if row["id"] == "cultivation_otherworld_root")
        self.assertTrue(achievement["unlocked"])
        self.assertEqual(achievement["player_name"], "甲")

    def test_story_and_combined_cultivation_conditions(self):
        created = self.engine.create_game("凡人", "none", "dao", 994)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 8
        game.player.additional_roots = ["metal", "wood", "water", "fire", "earth"]
        game.player.story_flags.extend(["kunwu_completed", "five_poles_completed"])
        add_item(game.player, "virtual_heaven_cauldron")
        game.history.append(HistoryRecord(
            "EVT_KUNWU_002", 1, game.player.age, "万修争道", "break_line", "dead",
            "你在天裂古台中陨落。", {}, ["kunwu"],
        ))

        shown = self.engine.present(game)
        names = {row["name"] for row in shown["new_achievements"]}
        self.assertTrue({"月沉海宫", "天裂葬身", "补天遗客", "三元归一", "五行缺德", "逆天改命", "修仙大能", "一步之遥"} <= names)

    def test_achievement_popup_setting_is_persisted(self):
        created = self.engine.create_game("静修", "supreme_water", "dao", 995)
        self.assertTrue(created["settings"]["achievement_popup"])
        changed = self.engine.update_setting(created["id"], "achievement_popup", False)
        self.assertFalse(changed["settings"]["achievement_popup"])
        self.assertFalse(self.engine.get_game(created["id"])["settings"]["achievement_popup"])

    def test_demonic_monster_and_ghost_story_achievements_have_correct_sources(self):
        catalog = {row["name"]: row for row in self.engine.list_achievements()["achievements"]}
        base_story = {
            "我命由我", "血河再生", "月落尸眠", "裂谷余息", "一羽新日",
            "星子远行", "祖渊重生", "祖藤封根", "万灵斩仙", "忘川有名",
        }
        self.assertTrue(base_story <= set(catalog))
        self.assertTrue(all(catalog[name]["source"]["kind"] == "base" for name in base_story))
        self.assertEqual(catalog["百族立碑"]["source"]["id"], "official.monster-bloodlines")
        self.assertEqual(catalog["今夜百鬼行"]["source"]["id"], "official.ghost-reincarnation")
        self.assertEqual(catalog["胯下之辱"]["source"]["id"], "official.ghost-reincarnation")


if __name__ == "__main__":
    unittest.main()
