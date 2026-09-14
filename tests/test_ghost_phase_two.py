import copy
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.ghost_system import (
    SOUL_SLOTS, apply_soul_erosion, ensure_ghost_cultivation_state,
    ghost_opportunity_multiplier, ghost_soul_effects, ghost_soul_pressure,
)
from cultivation_life.models import Item, Player
from cultivation_life.possession_system import (
    can_possess, enter_host_body, is_possessed, leave_host_body, possession_limit,
)
from cultivation_life.rules import combat_power
from cultivation_life.version import BASE_GAME_VERSION


class GhostPhaseTwoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def _game(self):
        created = self.engine.create_game("照夜", "mutated_yin", "ghost", seed=731)
        return self.engine.store.load(created["id"])

    @staticmethod
    def _soul(soul_id="soul-a", power=4200, pressure=2.0):
        return {
            "id": soul_id, "npc_id": f"npc-{soul_id}", "name": "顾忘川", "path": "ghost",
            "race": "human", "realm_index": 3, "layer": 4, "combat_power": power,
            "affinity": 0, "defeated": True, "is_bound_soul": True,
            "soul_pressure": pressure,
            "soul_trait": {"name": "宿慧", "description": "前尘未泯", "stat": "opportunity"},
        }

    def test_release_versions_and_phase_two_config(self):
        self.assertEqual(BASE_GAME_VERSION, "1.3.0")
        manifest = (Path(__file__).parents[1] / "dlc/ghost-reincarnation/manifest.json").read_text("utf-8")
        self.assertIn('"version": "3.0.0"', manifest)

    def test_ten_fixed_slots_saturate_and_pressure_only_changes_future_growth(self):
        player = Player("魂主", "mutated_yin", path="ghost", realm_index=3, layer=2)
        ensure_ghost_cultivation_state(player)
        player.ghost_bound_souls = [self._soul()]
        player.ghost_soul_slots = {"胎光": "soul-a"}
        self.assertEqual(len(SOUL_SLOTS), 10)
        self.assertGreater(ghost_soul_effects(player)["opportunity"], 0)
        self.assertLess(ghost_soul_effects(player)["opportunity"], 0.34)
        self.assertGreater(ghost_opportunity_multiplier(player), 1)
        self.assertEqual(ghost_soul_pressure(player), (2.0, 0.02))
        hp_before = player.ghost_intrinsic_hp_current
        result = apply_soul_erosion(player, 1)
        self.assertEqual(player.ghost_intrinsic_hp_current, hp_before)
        self.assertAlmostEqual(result["rate_pp"], 0.0002 * 1.02)

    def test_souls_can_be_swapped_while_an_event_is_pending(self):
        game = self._game()
        game.player.ghost_bound_souls = [self._soul()]
        game.pending_event = {"id": "TEST", "title": "战中", "body": "", "choices": []}
        self.engine.store.save(game)
        result = self.engine.ghost_soul_action(game.id, "soul-a", "equip", "伏矢")
        self.assertEqual(result["ghost_system"]["phase_two"]["slots"][4]["soul_id"], "soul-a")

    def test_attachment_keeps_free_control_and_changes_only_growth_and_efficiency(self):
        game = self._game()
        game.player.inventory.append(Item("test_sword", "照魂剑", combat_bonus=600))
        self.engine.store.save(game)
        attached = self.engine.ghost_attachment_action(game.id, "attach", "test_sword")
        state = attached["ghost_system"]["phase_two"]
        self.assertEqual(state["state"], "attached")
        self.assertLess(state["attachment"]["erosion_growth_multiplier"], 1)
        self.assertLess(state["attachment"]["cultivation_efficiency_multiplier"], 1)
        left = self.engine.ghost_attachment_action(game.id, "leave")
        self.assertEqual(left["ghost_system"]["phase_two"]["state"], "free")

    def test_possession_freezes_core_and_active_souls_then_restores_exact_core(self):
        player = Player("无常", "mutated_yin", path="ghost", realm_index=4, layer=5, opportunity=321)
        ensure_ghost_cultivation_state(player)
        player.ghost_wangsheng_energy = 9
        player.ghost_reincarnation_imprints = {"3": 7}
        player.ghost_bound_souls = [self._soul()]
        player.ghost_soul_slots = {"伏矢": "soul-a"}
        rate = player.ghost_soul_erosion_rate_pp = 0.25
        target = {"id": "host-a", "name": "沈青", "race": "human", "path": "dao", "spirit_root": "supreme_metal", "realm_index": 3, "layer": 2, "combat_power": 2000}
        allowed, _ = can_possess(player, target)
        self.assertTrue(allowed)
        enter_host_body(player, target)
        self.assertTrue(is_possessed(player))
        self.assertEqual(player.name, "沈青（无常）")
        self.assertEqual(ghost_soul_effects(player)["might"], 0)
        self.assertFalse(apply_soul_erosion(player, 50)["active"])
        self.assertEqual(player.ghost_soul_erosion_rate_pp, rate)
        self.assertEqual(player.ghost_wangsheng_energy, 9)
        player.opportunity = 9999
        leave_host_body(player)
        self.assertEqual((player.name, player.path, player.realm_index, player.layer, player.opportunity), ("无常", "ghost", 4, 5, 321))
        self.assertEqual(player.possession_count, 1)
        self.assertEqual(player.ghost_reincarnation_imprints, {"3": 7})

    def test_default_possession_limit_and_body_death_returns_to_core(self):
        game = self._game()
        target = {"id": "host-b", "name": "陆归尘", "race": "human", "path": "dao", "spirit_root": "supreme_wood", "realm_index": 0, "layer": 1, "combat_power": 1}
        self.assertEqual(possession_limit(game.player), 1)
        enter_host_body(game.player, target)
        self.engine._die(game, "宿主寿尽", "SYS_LIFESPAN")
        self.assertTrue(game.player.alive)
        self.assertEqual(game.player.path, "ghost")
        self.assertFalse(is_possessed(game.player))
        self.assertEqual(game.player.possession_count, 1)
        allowed, reason = can_possess(game.player, target)
        self.assertFalse(allowed)
        self.assertIn("最多", reason)

    def test_advanced_techniques_extend_or_remove_possession_limit(self):
        player = Player("夺形", "mutated_yin", path="ghost", possession_count=1)
        player.known_techniques = [copy.deepcopy(TECHNIQUE_CATALOG["TECH_GHOST_BODY_THIEF"])]
        self.assertEqual(possession_limit(player), 2)
        player.known_techniques.append(copy.deepcopy(TECHNIQUE_CATALOG["TECH_GHOST_TEN_THOUSAND_HOSTS"]))
        self.assertIsNone(possession_limit(player))

    def test_controlled_ghost_cannot_use_free_actions_or_travel(self):
        game = self._game()
        game.player.ghost_captor = {"id": "c", "name": "拘魂者", "combat_power": combat_power(game.player) * 2, "location_id": game.player.location_id}
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "魂印受制"):
            self.engine.advance(game.id, "treasure")
        destination = next(row["id"] for row in self.engine.present(game)["map"]["locations"] if not row["current"])
        with self.assertRaisesRegex(ValueError, "拘魂者"):
            self.engine.travel_map(game.id, destination)

    def test_parade_announcement_marker_and_real_souls(self):
        game = self._game()
        game.ghost_parade["start_age"] = game.player.age + 1
        game.ghost_parade["end_age"] = game.player.age + 100
        rng = __import__("random").Random(4)
        game.player.age += 1
        self.engine._advance_ghost_phase_two_year(game, rng)
        self.assertEqual(game.ghost_parade["status"], "active")
        self.assertTrue(game.ghost_parade["souls"])
        self.assertTrue(all("soul_trait" in row and "soul_pressure" in row for row in game.ghost_parade["souls"]))
        public = self.engine.present(game)
        marker = next(row for row in public["map"]["locations"] if row["id"] == game.ghost_parade["location_id"])
        self.assertEqual(marker["ghost_parade"]["status"], "active")

    def test_new_state_round_trips_in_existing_save_object(self):
        game = self._game()
        game.player.ghost_bound_souls = [self._soul()]
        game.player.ghost_soul_slots = {"胎光": "soul-a"}
        game.player.ghost_attachment = {"item_id": "x", "name": "魂灯"}
        self.engine.store.save(game)
        loaded = self.engine.store.load(game.id)
        self.assertEqual(loaded.player.ghost_bound_souls[0]["name"], "顾忘川")
        self.assertEqual(loaded.player.ghost_soul_slots, {"胎光": "soul-a"})
        self.assertEqual(loaded.player.ghost_attachment["name"], "魂灯")
        self.assertTrue(loaded.ghost_parade)


if __name__ == "__main__":
    unittest.main()
