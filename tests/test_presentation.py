import tempfile
import unittest
from pathlib import Path

from cultivation_life import GameEngine


class V2PresentationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temporary.name) / "games.sqlite3")
        self.created = self.engine.create_game("观世者", seed=20260916)
        self.game_id = self.created["id"]

    def tearDown(self):
        self.temporary.cleanup()

    def test_settings_are_validated_persisted_and_presented(self):
        self.assertEqual(
            self.created["settings"],
            {
                "combat_popup": True,
                "achievement_popup": True,
                "auto_advance_player_wars": False,
            },
        )
        changed = self.engine.update_setting(
            self.game_id, "combat_popup", False
        ).game
        self.assertFalse(changed["settings"]["combat_popup"])
        self.assertFalse(self.engine.get_game(self.game_id)["settings"]["combat_popup"])
        with self.assertRaisesRegex(ValueError, "未知设置项"):
            self.engine.update_setting(self.game_id, "unknown", True)
        self.assertEqual(self.engine.get_game(self.game_id)["revision"], changed["revision"])

        with self.assertRaisesRegex(ValueError, "所属世界无效"):
            self.engine.record_world_news(self.game_id, "not-a-world", "伪讯", "不应写入")
        self.assertEqual(self.engine.get_game(self.game_id)["revision"], changed["revision"])

    def test_world_news_is_simulated_but_hidden_across_worlds_until_debug(self):
        self.engine.record_world_news(self.game_id, "human", "人界大事", "当前界面可见")
        self.engine.record_world_news(self.game_id, "spirit", "灵界大事", "默认应隐藏")
        self.engine.record_world_news(self.game_id, "global", "诸天大事", "所有界面可见")

        normal = self.engine.get_game(self.game_id)
        self.assertEqual(
            [row["title"] for row in normal["world_news"]],
            ["诸天大事", "人界大事"],
        )
        self.assertFalse(normal["debug_world_news"])

        debug = self.engine.set_world_news_debug(self.game_id, True).game
        self.assertTrue(debug["debug_world_news"])
        self.assertEqual(
            [row["title"] for row in debug["world_news"]],
            ["诸天大事", "灵界大事", "人界大事"],
        )
        journal = self.engine.event_journal(self.game_id)
        self.assertEqual(
            sum(row["event_type"] == "presentation.world_news.recorded" for row in journal),
            3,
        )


if __name__ == "__main__":
    unittest.main()
