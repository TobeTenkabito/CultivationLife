from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import GameEngine


ROOT = Path(__file__).resolve().parent.parent


class V2AchievementIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "games.db"
        self.engine = GameEngine(
            self.database,
            content_directory=ROOT / "content",
            extension_root=ROOT,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_unlock_is_cross_save_persistent_and_announced_only_once(self) -> None:
        first = self.engine.create_game(
            "第一位", seed=91, spirit_root="otherworld"
        )
        self.assertIn(
            "cultivation_otherworld_root",
            {row["id"] for row in first["new_achievements"]},
        )
        second = self.engine.create_game(
            "第二位", seed=92, spirit_root="otherworld"
        )
        self.assertNotIn(
            "cultivation_otherworld_root",
            {row["id"] for row in second["new_achievements"]},
        )

        reopened = GameEngine(
            self.database,
            content_directory=ROOT / "content",
            extension_root=ROOT,
        )
        achievement = next(
            row for row in reopened.list_achievements()["achievements"]
            if row["id"] == "cultivation_otherworld_root"
        )
        self.assertTrue(achievement["unlocked"])
        self.assertEqual(achievement["player_name"], "第一位")

    def test_existing_save_is_evaluated_after_state_progression(self) -> None:
        created = self.engine.create_game("进境者", seed=93)
        state = self.engine.store.load(created["id"])
        actor_id = str(state.controlled_entity_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="nascent", layer=1)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="进境者", expected_revision=state.revision
        )

        loaded = self.engine.get_game(created["id"])
        self.assertIn(
            "cultivation_nascent",
            {row["id"] for row in loaded["new_achievements"]},
        )
        self.assertEqual(self.engine.get_game(created["id"])["new_achievements"], [])

    def test_enabled_dlc_achievements_are_part_of_the_public_catalog(self) -> None:
        catalog = self.engine.list_achievements()
        self.assertEqual(catalog["total"], 58)
        self.assertTrue(catalog["progress_available"])
        by_id = {row["id"]: row for row in catalog["achievements"]}
        self.assertEqual(
            by_id["monster_custom_lineage_founded"]["source"]["id"],
            "official.monster-bloodlines",
        )
        ghost = next(
            row for row in catalog["achievements"]
            if row["source"]["id"] == "official.ghost-reincarnation"
        )
        self.assertEqual(ghost["source"]["kind"], "dlc")


if __name__ == "__main__":
    unittest.main()
