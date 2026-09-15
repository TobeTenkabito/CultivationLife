import copy
import math
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.combat_system import BattleUnit, PlayerCombatSystem
from cultivation_life.engine import GameEngine
from cultivation_life.formation_system import (
    active_formation_profile, adjacency_matrix, calculate_formation_profile,
    effect_matrix, formation_alpha, formation_battle_experience_gain,
    formation_material_definitions, formation_round_effects,
    make_formation_material_instance, qr_eigenvalues,
)
from cultivation_life.models import Player
from cultivation_life.rules import add_item, combat_power, max_hp, max_mp


SOURCE_ROOT = Path(__file__).resolve().parent.parent


def node(nature, value=5.0, **extra):
    return {"name": nature, "nature": nature, "formation_value": value, "relation_overrides": {}, **extra}


class FormationMathTests(unittest.TestCase):
    def test_empty_and_single_node_have_zero_effect_matrix(self):
        empty = [None] * 9
        self.assertTrue(all(value == 0 for row in effect_matrix(empty, adjacency_matrix(empty, .5)) for value in row))
        single = [node("wood"), *([None] * 8)]
        self.assertTrue(all(value == 0 for row in effect_matrix(single, adjacency_matrix(single, .5)) for value in row))
        self.assertFalse(calculate_formation_profile(single, alpha=.5)["active"])

    def test_directed_generation_and_clash_have_expected_signs(self):
        growing = [node("wood", 2), node("fire", 3), *([None] * 7)]
        growth_matrix = effect_matrix(growing, adjacency_matrix(growing, .5))
        self.assertGreater(growth_matrix[0][1], 0)
        clashing = [node("wood", 2), node("earth", 3), *([None] * 7)]
        clash_matrix = effect_matrix(clashing, adjacency_matrix(clashing, .5))
        self.assertLess(clash_matrix[0][1], 0)

    def test_distance_decay_and_mastery_are_monotone(self):
        nearby = [node("wood"), node("fire"), *([None] * 7)]
        distant = [node("wood"), None, node("fire"), *([None] * 6)]
        self.assertGreater(adjacency_matrix(nearby, .5)[0][1], adjacency_matrix(distant, .5)[0][2])
        self.assertGreater(adjacency_matrix(distant, .9)[0][2], adjacency_matrix(distant, .5)[0][2])
        novice = Player("初学", "supreme_wood")
        master = Player("阵师", "supreme_wood")
        master.art_experience["formation"] = 40000
        self.assertGreater(formation_alpha(master), formation_alpha(novice))
        self.assertLess(formation_alpha(master), 0.9)

    def test_metrics_and_qr_are_finite_and_repeatable(self):
        nodes = [node(value % 2 and "wood" or "fire", 4 + value / 2) for value in range(9)]
        first = calculate_formation_profile(nodes, alpha=.72, name="九宫压测")
        second = calculate_formation_profile(nodes, alpha=.72, name="九宫压测")
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["advanced"]["eigenvalues"], second["advanced"]["eigenvalues"])
        self.assertTrue(all(math.isfinite(value) and 0 <= value <= 100 for value in first["metrics"].values()))
        values = qr_eigenvalues([[0.0, -1.0], [1.0, 0.0]])
        self.assertAlmostEqual(max(abs(value) for value in values), 1.0, places=4)
        self.assertTrue(any(abs(value.imag) > .5 for value in values))

    def test_archetypes_trade_power_for_stability(self):
        growth = calculate_formation_profile([node("wood", 7)] * 9, alpha=.8, name="生阵")
        kill = calculate_formation_profile([node("wood", 7), node("earth", 7)] * 4 + [node("wood", 7)], alpha=.8, name="杀阵")
        self.assertGreater(growth["metrics"]["growth"], kill["metrics"]["growth"])
        self.assertGreater(kill["metrics"]["kill"], growth["metrics"]["kill"])
        self.assertGreater(growth["static_player_multipliers"]["sustain"], kill["static_player_multipliers"]["sustain"])
        self.assertGreater(kill["round_rules"]["integrity_kill_penalty"], growth["round_rules"]["integrity_kill_penalty"])

    def test_extreme_dual_side_broadcast_stays_bounded_and_non_recursive(self):
        natures = ["space", "star", "law", "soul", "yang", "yin", "thunder", "fire", "earth"]
        profile = calculate_formation_profile([node(nature, 10000) for nature in natures], alpha=.899999)
        self.assertTrue(profile["active"])
        self.assertLessEqual(max(profile["static_player_multipliers"].values()), 1.14 + 1e-9)
        self.assertGreaterEqual(min(profile["static_enemy_multipliers"].values()), .94 - 1e-9)
        for round_no in range(1, 9):
            effects = formation_round_effects(profile, round_no, 1.0)
            self.assertLessEqual(max(effects["player_stat_multipliers"].values()), 1.22)
            self.assertGreaterEqual(min(effects["enemy_stat_multipliers"].values()), .93)
            self.assertLessEqual(effects["state_restore"], .015)
            self.assertLessEqual(effects["enemy_morale_loss"], 2.4)
        # A formation broadcasts once to each aggregated side. Unit count is
        # deliberately absent from the round profile, preventing rebroadcast.
        self.assertEqual(formation_round_effects(profile, 3, .8), formation_round_effects(profile, 3, .8))

    def test_integrity_zero_disables_every_formation_effect(self):
        profile = calculate_formation_profile([node("wood", 8), node("fire", 8)] + [None] * 7, alpha=.8)
        effects = formation_round_effects(profile, 8, 0)
        self.assertTrue(all(value == 1 for value in effects["player_stat_multipliers"].values()))
        self.assertTrue(all(value == 1 for value in effects["enemy_stat_multipliers"].values()))
        self.assertEqual(effects["state_restore"], 0)
        self.assertEqual(effects["enemy_morale_loss"], 0)


class FormationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")
        self.game_id = self.engine.create_game("阵师", "supreme_wood", "dao", 55001, preset_id="core")["id"]

    def tearDown(self):
        self.temp.cleanup()

    def _give_array(self, ids=("human_greenwood_stake", "human_red_sun_sand", "human_xuanyin_stone")):
        game = self.engine.store.load(self.game_id)
        definitions = formation_material_definitions()
        instances = [
            make_formation_material_instance(definitions[material_id], source="测试", origin_world="human")
            for material_id in ids
        ]
        game.player.formation_materials.extend(instances)
        self.engine.store.save(game)
        return instances

    def _save_active(self, instances, name="青木炼阳阵"):
        slots = [entry["id"] for entry in instances] + [None] * (9 - len(instances))
        return self.engine.save_formation(self.game_id, {"name": name, "slots": slots, "activate": True})

    def test_save_occupies_real_instances_and_preset_keeps_types_only(self):
        instances = self._give_array()
        shown = self._save_active(instances)
        system = shown["formation_system"]
        self.assertEqual(len(system["materials"]), 3)
        self.assertTrue(all(row["occupied"] for row in system["materials"]))
        self.assertTrue(system["profile"]["active"])
        self.assertNotIn(instances[0]["id"], system["loadouts"][0]["slots"])
        self.assertEqual(system["loadouts"][0]["slots"][0], "human_greenwood_stake")
        loaded = self.engine.store.load(self.game_id)
        self.assertEqual(loaded.player.formation_materials, [])
        self.assertEqual(len([row for row in loaded.player.formation_active_bindings if row]), 3)

    def test_deactivate_returns_each_instance_unchanged(self):
        instances = self._give_array()
        self._save_active(instances)
        shown = self.engine.deactivate_formation(self.game_id)
        self.assertIsNone(shown["formation_system"]["active_formation_id"])
        restored = self.engine.store.load(self.game_id).player.formation_materials
        self.assertEqual({row["id"] for row in restored}, {row["id"] for row in instances})

    def test_switching_preset_cannot_clone_a_rare_instance(self):
        instances = self._give_array()
        first = self._save_active(instances, "第一阵")
        active_id = first["formation_system"]["active_formation_id"]
        game = self.engine.store.load(self.game_id)
        game.player.formation_loadouts.append({
            "id":"formation-second", "name":"第二阵",
            "slots":["human_greenwood_stake", "human_red_sun_sand", "human_xuanyin_stone", None, None, None, None, None, None],
            "created_year":game.player.age,
        })
        self.engine.store.save(game)
        switched = self.engine.activate_formation(self.game_id, "formation-second")
        self.assertEqual(switched["formation_system"]["active_formation_id"], "formation-second")
        self.assertEqual(len([row for row in switched["formation_system"]["materials"] if row["occupied"]]), 3)
        loaded = self.engine.store.load(self.game_id)
        all_ids = [row["source_snapshot"]["id"] for row in loaded.player.formation_active_bindings if row]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertNotEqual(active_id, "formation-second")

    def test_shared_legacy_item_is_removed_while_occupied_and_restored(self):
        instances = self._give_array(("human_greenwood_stake", "human_red_sun_sand"))
        game = self.engine.store.load(self.game_id)
        add_item(game.player, "formation_plate")
        self.engine.store.save(game)
        shown = self.engine.get_game(self.game_id)
        plate = next(row for row in shown["formation_system"]["materials"] if row["definition_id"] == "legacy_formation_plate")
        slots = [instances[0]["id"], instances[1]["id"], plate["id"], None, None, None, None, None, None]
        self.engine.save_formation(self.game_id, {"name":"兼容阵", "slots":slots, "activate":True})
        self.assertFalse(any(item.id == "formation_plate" for item in self.engine.store.load(self.game_id).player.inventory))
        self.engine.deactivate_formation(self.game_id)
        self.assertTrue(any(item.id == "formation_plate" for item in self.engine.store.load(self.game_id).player.inventory))

    def test_old_inventory_name_no_longer_enables_placeholder_formation(self):
        player = Player("旧档", "supreme_earth")
        add_item(player, "formation_plate")
        self.assertIsNone(PlayerCombatSystem._formation_name(player))
        resolution = PlayerCombatSystem.resolve(
            player, [BattleUnit("player", "旧档", "player", 1000, 1)],
            {"target_name":"试阵木人", "target_power":1000, "target_realm_index":1, "target_layer":1},
            False, random.Random(1), current_hp_ratio=1, current_mp_ratio=1,
        )
        self.assertNotIn("大阵", resolution.artificial_conditions)

    def test_real_combat_uses_profile_and_grants_experience_once(self):
        instances = self._give_array()
        self._save_active(instances)
        game = self.engine.store.load(self.game_id)
        before = game.player.art_experience["formation"]
        target = {
            "target_name":"试阵修士", "target_power":combat_power(game.player),
            "target_realm_index":game.player.realm_index, "target_layer":game.player.layer,
            "combat_type":"cultivator", "objective":"repel", "max_rounds":4,
        }
        self.engine._combat(game, target, False, random.Random(9))
        self.assertGreater(game.player.art_experience["formation"], before)
        self.assertIsNotNone(game.last_combat_report)
        self.assertEqual(game.last_combat_report["formation_profile"]["name"], "青木炼阳阵")
        self.assertGreater(game.last_combat_report["formation_experience_gain"], 0)

    def test_field_conditions_broadcast_to_both_sides(self):
        ids = ("human_void_lock_nail", "human_void_lock_nail", "human_void_lock_nail")
        instances = self._give_array(ids)
        shown = self._save_active(instances, "锁空阵")
        self.assertIn("禁空", shown["formation_system"]["profile"]["artificial_conditions"])
        game = self.engine.store.load(self.game_id)
        player = game.player
        resolution = PlayerCombatSystem.resolve(
            player, [BattleUnit("player", player.name, "player", 1000, player.realm_index)],
            {"target_name":"飞遁修士", "target_power":1000, "target_realm_index":player.realm_index, "target_layer":1},
            False, random.Random(3), current_hp_ratio=1, current_mp_ratio=1,
        )
        self.assertIn("禁空", resolution.artificial_conditions)
        self.assertLess(resolution.player_stats["mobility"], 1000)
        self.assertLess(resolution.enemy_stats["mobility"], 1000)

    def test_market_has_separate_formation_stock_and_purchase_keeps_instance(self):
        shown = self.engine.get_game(self.game_id)
        offers = shown["market"]["formation_material_offers"]
        self.assertEqual(len(offers), 3)
        game = self.engine.store.load(self.game_id)
        add_item(game.player, "spirit_stone", offers[0]["price"])
        self.engine.store.save(game)
        bought = self.engine.buy_market_offer(self.game_id, offers[0]["id"])
        material = next(row for row in bought["formation_system"]["materials"] if not row["occupied"])
        self.assertEqual(material["storage_id"], offers[0]["formation_material_instance"]["id"])

    def test_old_save_defaults_without_moving_save_schema(self):
        game = self.engine.store.load(self.game_id)
        raw = game.to_dict()
        for key in (
            "formation_materials", "formation_loadouts", "active_formation_id",
            "formation_active_bindings", "formation_profile_cache", "formation_sequence",
        ):
            raw["player"].pop(key, None)
        restored = type(game).from_dict(copy.deepcopy(raw))
        self.assertEqual(restored.player.formation_materials, [])
        self.assertEqual(restored.player.formation_loadouts, [])
        self.assertEqual(restored.version, game.version)

    def test_experience_formula_is_bounded(self):
        profile = calculate_formation_profile([node("wood", 7), node("fire", 7)] + [None] * 7, alpha=.7)
        self.assertEqual(formation_battle_experience_gain(profile, 0, 1), 0)
        self.assertLessEqual(formation_battle_experience_gain(profile, 8, .01), 45)


if __name__ == "__main__":
    unittest.main()
