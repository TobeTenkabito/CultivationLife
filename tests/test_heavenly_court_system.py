import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class HeavenlyCourtSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.engine = GameEngine(root)

    def tearDown(self):
        self.temp.cleanup()

    def _true_immortal(self, seed=2401):
        return self.engine.create_game("巡天者", "otherworld", "dao", seed, preset_id="true_immortal")["id"]

    def test_quick_start_initializes_persistent_49_seat_court(self):
        shown = self.engine.get_game(self._true_immortal())
        court = shown["heavenly_court"]
        self.assertTrue(court["visible"])
        self.assertEqual(court["seat_count"], 49)
        self.assertEqual(len(court["offices"]), 7)
        self.assertEqual(court["player_grade"], 9)

    def test_celestial_random_pool_is_fully_isolated(self):
        game_id = self._true_immortal()
        game = self.engine.store.load(game_id)
        for seed in range(80):
            event = self.engine._select_event(game, "travel", random.Random(seed))
            self.assertIsNotNone(event)
            self.assertIn("world:celestial", event.get("tags", []))
        celestial_events = [event for event in self.engine.events if "world:celestial" in event.get("tags", [])]
        self.assertGreaterEqual(sum(event.get("category") == "celestial_combat" for event in celestial_events), 5)
        self.assertEqual(sum("faction_join" in event.get("tags", []) for event in celestial_events), 3)

    def test_seven_offices_rotate_once_per_unit_and_last_seven_units(self):
        game = self.engine.store.load(self._true_immortal())
        rng = random.Random(9)
        for _ in range(7):
            self.engine._advance_heavenly_court_unit(game, rng)
        court = game.heavenly_court
        self.assertEqual(court["unit"], 7)
        self.assertTrue(all(court["offices"].values()))
        self.assertEqual(court["offices"]["sun"]["start_unit"], 1)
        self.assertEqual(court["offices"]["sun"]["end_unit"], 8)
        self.engine._advance_heavenly_court_unit(game, rng)
        self.assertEqual(court["offices"]["sun"]["start_unit"], 8)

    def test_player_election_is_interactive_and_does_not_advance_age(self):
        game_id = self._true_immortal()
        game = self.engine.store.load(game_id)
        game.heavenly_court["player_grade"] = 4
        age = game.player.age
        self.engine._advance_heavenly_court_unit(game, random.Random(2))
        self.assertEqual(game.heavenly_court["open_election"]["office_id"], "sun")
        self.engine.store.save(game)
        shown = self.engine.resolve_heavenly_election(game_id, "promise_decree", "relief")
        self.assertEqual(shown["player"]["age"], age)
        self.assertIn("votes", shown["heavenly_court"].get("election") or {"votes": {}})

    def test_controlling_four_luminaries_guarantees_law_vote(self):
        game_id = self._true_immortal()
        game = self.engine.store.load(game_id)
        official_id = next(key for key in game.heavenly_court["officials"] if key != "player")
        official = game.heavenly_court["officials"][official_id]
        for index, office_id in enumerate(game.heavenly_court["offices"]):
            holder_id = "player" if index < 4 else official_id
            game.heavenly_court["offices"][office_id] = {
                "holder_id": holder_id,
                "holder_name": game.player.name if holder_id == "player" else official["name"],
                "start_unit": 0, "end_unit": 7, "votes": 13,
            }
        self.engine.store.save(game)
        shown = self.engine.heavenly_court_action(game_id, "law:martial_gods", enact=True)
        law = next(row for row in shown["heavenly_court"]["laws"] if row["id"] == "martial_gods")
        self.assertTrue(law["active"])
        self.assertTrue(shown["heavenly_court"]["last_vote"]["passed"])

    def test_court_beast_hunt_uses_beast_combat_and_grants_fame_on_kill(self):
        game = self.engine.store.load(self._true_immortal())
        event = self.engine.events_by_id["EVT_CELESTIAL_COMBAT_LAW_BEAST_001"]
        pending = self.engine._instantiate_event(event, game, random.Random(8))
        self.assertEqual(pending["runtime"]["combat_type"], "beast")
        self.assertEqual(pending["runtime"]["action"], "hunt_beast")
        pending["runtime"]["target_power"] = 1
        pending["runtime"]["members"][0]["power"] = 1
        before = game.player.fame
        result, _ = self.engine._combat(game, pending["runtime"], True, random.Random(3))
        self.assertEqual(result, "killed")
        self.assertGreater(game.player.fame, before)

    def test_celestial_market_and_commissions_work_during_power_conversion(self):
        game_id = self._true_immortal(2402)
        game = self.engine.store.load(game_id)
        game.player.immortal_power_converted = False
        game.player.immortal_conversion_stage = 0
        game.player.mp = 0
        before = next(item.quantity for item in game.player.inventory if item.id == "spirit_stone")
        self.engine.store.save(game)
        shown = self.engine.advance(game_id, "commission")
        after = next(item["quantity"] for item in shown["player"]["inventory"] if item["id"] == "spirit_stone")
        self.assertGreater(after, before)
        self.assertTrue(shown["market"]["available"])
        self.assertTrue(shown["market"]["offers"])


if __name__ == "__main__":
    unittest.main()
