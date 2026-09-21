import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import REALMS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.rules import max_hp, max_mp


class SecretArtsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def _core_game(self):
        shown = self.engine.create_game(
            "藏锋", "supreme_metal", "dao", 2301, preset_id="core",
        )
        return shown["id"], self.engine.store.load(shown["id"])

    def test_natural_divine_sense_threshold_matches_every_cultivation_layer(self):
        self.assertEqual(self.engine._cultivation_sense_requirement(1, 1), 1)
        self.assertEqual(self.engine._cultivation_sense_requirement(2, 1), 14)
        self.assertEqual(self.engine._cultivation_sense_requirement(3, 1), 23)
        self.assertEqual(self.engine._cultivation_sense_requirement(4, 1), 32)
        self.assertEqual(self.engine._cultivation_sense_requirement(4, 9), 40)

    def test_concealment_changes_only_outward_realm_and_enemy_anchor(self):
        game_id, before = self._core_game()
        real_realm = (before.player.realm_index, before.player.layer)
        real_power = self.engine._player_intrinsic_combat_power(before.player)
        shown = self.engine.manage_secret_art(game_id, "conceal", "activate", 1)
        self.assertEqual((shown["player"]["realm_index"], shown["player"]["layer"]), real_realm)
        self.assertEqual(shown["player"]["external_realm_name"], "练气1层")
        self.assertEqual(shown["player"]["combat_power"], real_power)

        game = self.engine.store.load(game_id)
        settings = {
            "realm_offsets": [[0, 1.0]], "expectation_multiplier": 1.0,
            "power_sigma": 0.0, "power_bounds": [1.0, 1.0],
        }
        old_bias = WORLD_SYSTEMS["secret_arts"]["concealed_enemy_bias"]
        old_party = WORLD_SYSTEMS["faction_conflict"]["npc_team_chance"]
        try:
            WORLD_SYSTEMS["secret_arts"]["concealed_enemy_bias"] = 1.0
            WORLD_SYSTEMS["faction_conflict"]["npc_team_chance"] = 0.0
            target = self.engine._generate_cultivator_target(
                game.player, "试锋散修", settings, random.Random(7),
                game=game, use_player_concealment=True,
            )
        finally:
            WORLD_SYSTEMS["secret_arts"]["concealed_enemy_bias"] = old_bias
            WORLD_SYSTEMS["faction_conflict"]["npc_team_chance"] = old_party
        self.assertEqual(target["target_realm_index"], 1)

        restored = self.engine.manage_secret_art(game_id, "conceal", "cancel")
        self.assertFalse(restored["secret_arts"]["concealment"]["active"])
        self.assertIn("结丹初期", restored["player"]["external_realm_name"])

    def test_suppression_changes_real_stats_but_preserves_sense_and_restores(self):
        game_id, game = self._core_game()
        game.player.realm_index = 4
        game.player.layer = 5
        game.player.divine_sense_rank = 47
        game.player.opportunity = 321.0
        game.player.hp = max_hp(game.player) * 0.62
        game.player.mp = max_mp(game.player) * 0.41
        true_power = self.engine._player_intrinsic_combat_power(game.player)
        self.engine.store.save(game)

        suppressed = self.engine.manage_secret_art(game_id, "suppress", "activate", 2)
        self.assertEqual((suppressed["player"]["realm_index"], suppressed["player"]["layer"]), (2, 1))
        self.assertEqual(suppressed["player"]["divine_sense"]["level"], 47)
        self.assertLess(suppressed["player"]["combat_power"], true_power)
        self.assertFalse(suppressed["breakthrough"]["enabled"])
        with self.assertRaisesRegex(ValueError, "压制修为期间不能运转主修功法"):
            self.engine.advance(game_id, "cultivate")
        with self.assertRaisesRegex(ValueError, "秘法压制"):
            self.engine.breakthrough(game_id)

        active = self.engine.store.load(game_id)
        active.player.opportunity = 12.0
        self.engine.store.save(active)
        restored = self.engine.manage_secret_art(game_id, "suppress", "cancel")
        self.assertEqual((restored["player"]["realm_index"], restored["player"]["layer"]), (4, 5))
        self.assertEqual(restored["player"]["divine_sense"]["level"], 47)
        self.assertEqual(restored["player"]["opportunity"], 333.0)
        self.assertAlmostEqual(restored["player"]["hp"] / restored["player"]["max_hp"], 0.62, places=3)
        self.assertAlmostEqual(restored["player"]["mp"] / restored["player"]["max_mp"], 0.41, places=3)

    def test_every_lower_cultivation_layer_is_a_secret_art_target(self):
        game_id, game = self._core_game()
        game.player.realm_index = 4
        game.player.layer = 5
        self.engine.store.save(game)

        shown = self.engine.get_game(game_id)
        targets = {
            (row["realm_index"], row["layer"]) for row in shown["secret_arts"]["targets"]
        }
        self.assertIn((4, 4), targets)
        self.assertIn((3, REALMS[3].layers), targets)
        self.assertNotIn((4, 5), targets)

        concealed = self.engine.manage_secret_art(game_id, "conceal", "activate", 4, 4)
        self.assertEqual(concealed["secret_arts"]["concealment"]["realm_index"], 4)
        self.assertEqual(concealed["secret_arts"]["concealment"]["layer"], 4)
        self.engine.manage_secret_art(game_id, "conceal", "cancel")

        suppressed = self.engine.manage_secret_art(game_id, "suppress", "activate", 4, 4)
        self.assertEqual(
            (suppressed["player"]["realm_index"], suppressed["player"]["layer"]), (4, 4),
        )

    def test_suppression_does_not_pause_or_hide_periodic_tribulation(self):
        game_id, game = self._core_game()
        game.player.realm_index = 6
        game.player.layer = 3
        game.player.next_tribulation_age = game.player.age + 500
        game.player.tribulation_power = 9000
        original_due_age = game.player.next_tribulation_age
        self.engine.store.save(game)

        suppressed = self.engine.manage_secret_art(game_id, "suppress", "activate", 4, 1)
        self.assertEqual(suppressed["tribulation"]["next_age"], original_due_age)
        self.assertEqual(suppressed["tribulation"]["years_remaining"], 500)

        active = self.engine.store.load(game_id)
        active.player.age += 25
        self.engine.store.save(active)
        shown = self.engine.get_game(game_id)
        self.assertEqual(shown["tribulation"]["next_age"], original_due_age)
        self.assertEqual(shown["tribulation"]["years_remaining"], 475)

        active = self.engine.store.load(game_id)
        active.player.age = original_due_age
        self.engine._check_tribulation(active, random.Random(2302))
        self.assertEqual(active.active_trial["kind"], "periodic_thunder")
        self.assertEqual(active.active_trial["source_realm"], 6)

    def test_npc_concealment_has_detect_and_reveal_thresholds(self):
        _, game = self._core_game()
        npc = SectNpc(
            "masked-elder", "藏岳", "游方修士", 4, 1, 600, 1400,
            path="dao", world="human", concealed_realm_index=2, concealed_layer=1,
        )
        game.player.divine_sense_rank = 13
        hidden = self.engine._npc_cultivation_perception(game, npc)
        self.assertEqual(hidden["realm_name"], "筑基初期")
        self.assertFalse(hidden["detected"])
        self.assertIsNone(hidden["actual_realm_name"])

        game.player.divine_sense_rank = 14
        detected = self.engine._npc_cultivation_perception(game, npc)
        self.assertTrue(detected["detected"])
        self.assertFalse(detected["revealed"])
        self.assertIn("气机有异", detected["realm_name"])
        self.assertIsNone(detected["actual_realm_name"])

        game.player.divine_sense_rank = 32
        revealed = self.engine._npc_cultivation_perception(game, npc)
        self.assertTrue(revealed["revealed"])
        self.assertIn("真实元婴初期", revealed["realm_name"])
        self.assertEqual(revealed["actual_realm_name"], "元婴初期")

    def test_world_npc_api_does_not_leak_hidden_real_realm(self):
        _, game = self._core_game()
        npc = SectNpc(
            "masked-api", "隐真", "散修", 5, 7, 1500, 3100,
            path="dao", world="human", concealed_realm_index=2, concealed_layer=3,
        )
        game.world_npcs[npc.id] = npc
        game.player.divine_sense_rank = 14
        shown = next(row for row in self.engine._public_world_npcs(game) if row["id"] == npc.id)
        self.assertEqual((shown["realm_index"], shown["layer"]), (2, 3))
        self.assertNotIn("化神", shown["realm_name"])
        self.assertIsNone(shown["cultivation_concealment"]["actual_realm_name"])
        self.assertNotIn("concealed_realm_index", shown)


if __name__ == "__main__":
    unittest.main()
