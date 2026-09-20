from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS
from cultivation_life.engine import GameEngine


SOURCE_ROOT = Path(__file__).resolve().parent.parent
CHAINS = {
    "sage_human_annals": {
        "count": 6,
        "world": "human",
        "realm": 3,
        "start": "EVT_SAGE_HUMAN_ANNALS_001",
        "choices": ("take_case", "open_granary", "name_them", "save_people", "public_covenant", "leave_blank_page"),
        "flag": "sage_human_annals_completed",
        "reward": "people_annals_bamboo",
        "achievement": "sage_story_human_annals",
    },
    "sage_spirit_covenant": {
        "count": 6,
        "world": "spirit",
        "realm": 6,
        "start": "EVT_SAGE_SPIRIT_COVENANT_001",
        "choices": ("hear_all", "keep_forms", "refute", "bear_law", "living_covenant", "sign_without_name"),
        "flag": "sage_spirit_covenant_completed",
        "reward": "myriad_voices_blank_seal",
        "achievement": "sage_story_spirit_covenant",
    },
}


class SageStoryChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_both_chains_are_closed_and_have_one_escalating_entry(self) -> None:
        for tag, spec in CHAINS.items():
            members = {
                event["id"]: event for event in self.engine.events
                if tag in event.get("tags", [])
            }
            self.assertEqual(len(members), spec["count"])
            starts = [event for event in members.values() if "probability_gate" in event.get("tags", [])]
            self.assertEqual(len(starts), 1)
            self.assertEqual(starts[0]["id"], spec["start"])
            self.assertTrue(all(f"world:{spec['world']}" in event.get("tags", []) for event in members.values()))

            reached: set[str] = set()
            pending = [spec["start"]]
            while pending:
                event_id = pending.pop()
                if event_id in reached:
                    continue
                reached.add(event_id)
                for choice in members[event_id]["choices"]:
                    for effect in choice.get("effects", []):
                        queued = effect.get("event_id") if effect.get("type") == "queue_event" else None
                        if queued in members:
                            pending.append(queued)
            self.assertEqual(reached, set(members))

    def test_chain_entries_require_exact_world_path_and_realm(self) -> None:
        created = self.engine.create_game("守经人", "supreme_wood", "confucian", 7711, preset_id="confucian_core")
        game = self.engine.store.load(created["id"])
        for spec in CHAINS.values():
            start = self.engine.events_by_id[spec["start"]]
            game.player.path = "confucian"
            game.player.world = spec["world"]
            game.player.realm_index = spec["realm"]
            self.assertTrue(self.engine._condition(start["conditions"], game))
            game.player.realm_index += 1
            self.assertFalse(self.engine._condition(start["conditions"], game))
            game.player.realm_index = spec["realm"]
            game.player.technique.path = "dao"
            self.assertFalse(self.engine._condition(start["conditions"], game))
            game.player.technique.path = "confucian"

    def test_each_chain_can_reach_reward_and_unlock_its_achievement(self) -> None:
        for offset, spec in enumerate(CHAINS.values()):
            created = self.engine.create_game(
                f"儒修{offset}", "supreme_wood", "confucian", 7720 + offset,
                preset_id="confucian_core",
            )
            game = self.engine.store.load(created["id"])
            game.player.world = spec["world"]
            game.player.realm_index = spec["realm"]
            game.player.layer = 1
            game.player.hp = 10**9
            game.player.mp = 10**9
            game.pending_event = self.engine._instantiate_event(
                self.engine.events_by_id[spec["start"]], game, random.Random(7720 + offset),
            )
            self.engine.store.save(game)

            shown = None
            for choice_id in spec["choices"]:
                shown = self.engine.choose(created["id"], choice_id)
            self.assertIsNotNone(shown)
            self.assertIn(spec["flag"], shown["player"]["story_flags"])
            self.assertIn(spec["reward"], {item["id"] for item in shown["player"]["inventory"]})
            self.assertIn(spec["achievement"], {row["id"] for row in shown["new_achievements"]})

    def test_story_rewards_are_dlc_only_and_not_sold(self) -> None:
        sold = {row["content_id"] for row in MARKET_GOODS}
        for item_id in ("people_annals_bamboo", "myriad_voices_blank_seal"):
            self.assertIn("story", ITEM_CATALOG[item_id].tags)
            self.assertNotIn(item_id, sold)


if __name__ == "__main__":
    unittest.main()
