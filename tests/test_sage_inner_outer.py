from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_technique_copy, combat_power
from cultivation_life.sage_system import haoran_level, haoran_passive_effects


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class SageInnerOuterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _game(self, seed: int = 21001):
        made = self.engine.create_game("浩然试法", "supreme_wood", "confucian", seed)
        return made["id"], self.engine.store.load(made["id"])

    @staticmethod
    def _grade_four_technique():
        return copy.deepcopy(next(row for row in TECHNIQUE_CATALOG.values() if row.grade == 4))

    def test_manual_records_origin_realm_separately_from_manual_level(self):
        _, game = self._game()
        technique = self._grade_four_technique()
        add_technique_copy(game.player, technique, level=7)
        manual = next(row for row in game.player.inventory if row.technique_id == technique.id)
        self.assertEqual(manual.technique_level, 7)
        self.assertEqual(manual.technique_origin_realm_index, 4)
        self.assertIn("元婴", manual.description)

    def test_refining_only_grants_new_levels_and_is_irreversible(self):
        game_id, game = self._game(21002)
        technique = self._grade_four_technique()
        add_technique_copy(game.player, technique, level=4)
        first_id = next(row.id for row in game.player.inventory if row.technique_id == technique.id)
        self.engine.store.save(game)

        shown = self.engine.sage_refine_manual(game_id, first_id)
        # Grade/origin 4 has weight 8; 8 * 10 * four newly understood levels.
        self.assertEqual(shown["player"]["haoran_exp"], 320)
        self.assertEqual(shown["player"]["refined_inheritances"][technique.id], 4)

        game = self.engine.store.load(game_id)
        add_technique_copy(game.player, technique, level=4)
        duplicate_id = next(row.id for row in game.player.inventory if row.technique_id == technique.id)
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "不能重复"):
            self.engine.sage_refine_manual(game_id, duplicate_id)

        game = self.engine.store.load(game_id)
        add_technique_copy(game.player, technique, level=6)
        higher_id = next(
            row.id for row in game.player.inventory
            if row.technique_id == technique.id and row.technique_level == 6
        )
        self.engine.store.save(game)
        shown = self.engine.sage_refine_manual(game_id, higher_id)
        self.assertEqual(shown["player"]["haoran_exp"], 480)
        self.assertEqual(shown["player"]["refined_inheritances"][technique.id], 6)

    def test_outer_king_spending_can_lower_level(self):
        game_id, game = self._game(21003)
        game.player.haoran_exp = 250
        self.engine.store.save(game)
        self.assertEqual(haoran_level(250), 2)
        shown = self.engine.sage_outer_king(game_id, "spirit_stone")
        self.assertEqual(shown["player"]["haoran_exp"], 50)
        self.assertEqual(shown["sage_system"]["inner_outer"]["level"], 0)

    def test_outer_king_combat_reward_is_fixed_at_purchase_time(self):
        game_id, game = self._game(21004)
        game.player.realm_index = 3
        game.player.layer = 1
        game.player.haoran_exp = 5000
        before = combat_power(game.player)
        self.engine.store.save(game)
        shown = self.engine.sage_outer_king(game_id, "combat")
        saved = self.engine.store.load(game_id)
        self.assertGreater(saved.player.outer_king_fixed_combat_power, 0)
        self.assertAlmostEqual(
            shown["player"]["outer_king_fixed_combat_power"],
            saved.player.outer_king_fixed_combat_power,
        )
        self.assertGreater(combat_power(saved.player), before)

    def test_forced_major_advance_uses_normal_completion_hook(self):
        game_id, game = self._game(21005)
        game.player.realm_index = 2
        game.player.layer = 9
        game.player.haoran_exp = 5000
        self.engine.store.save(game)
        shown = self.engine.sage_outer_king(game_id, "advance")
        self.assertEqual(shown["player"]["realm_index"], 3)
        self.assertEqual(shown["player"]["layer"], 1)
        saved = self.engine.store.load(game_id)
        self.assertEqual(saved.player.divine_sense_rank, self.engine._cultivation_sense_requirement(3, 1))

    def test_haoran_passives_grow_and_remain_capped(self):
        low = haoran_passive_effects(60)
        high = haoran_passive_effects(10**9)
        self.assertGreater(high["opportunity_multiplier"], low["opportunity_multiplier"])
        self.assertLessEqual(high["opportunity_multiplier"], 0.25)
        self.assertLessEqual(high["breakthrough_bonus"], 0.03)


if __name__ == "__main__":
    unittest.main()
