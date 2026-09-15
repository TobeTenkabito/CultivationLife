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
    formation_config, formation_maintenance_definitions, formation_material_definitions,
    formation_round_effects, ground_formation_power,
    make_formation_material_instance, qr_eigenvalues,
)
from cultivation_life.models import Player
from cultivation_life.rules import add_item, combat_power, expected_combat_power, max_hp, max_mp


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
        materials = [row for row in offers if row["kind"] == "formation_material"]
        supplies = [row for row in offers if row["kind"] == "formation_supply"]
        self.assertEqual(len(materials), 2)
        self.assertEqual(len(supplies), 1)
        game = self.engine.store.load(self.game_id)
        add_item(game.player, "spirit_stone", materials[0]["price"])
        self.engine.store.save(game)
        bought = self.engine.buy_market_offer(self.game_id, materials[0]["id"])
        material = next(row for row in bought["formation_system"]["materials"] if not row["occupied"])
        self.assertEqual(material["storage_id"], materials[0]["formation_material_instance"]["id"])
        game = self.engine.store.load(self.game_id)
        add_item(game.player, "spirit_stone", supplies[0]["price"])
        self.engine.store.save(game)
        bought = self.engine.buy_market_offer(self.game_id, supplies[0]["id"])
        self.assertEqual(bought["formation_system"]["repair_supplies"][0]["quantity"], 1)

    def test_old_save_defaults_without_moving_save_schema(self):
        game = self.engine.store.load(self.game_id)
        raw = game.to_dict()
        for key in (
            "formation_materials", "formation_loadouts", "active_formation_id",
            "formation_active_bindings", "formation_profile_cache", "formation_sequence",
            "formation_ground_arrays", "formation_repair_supplies", "formation_ground_sequence",
        ):
            raw["player"].pop(key, None)
        raw.pop("npc_formations", None)
        restored = type(game).from_dict(copy.deepcopy(raw))
        self.assertEqual(restored.player.formation_materials, [])
        self.assertEqual(restored.player.formation_loadouts, [])
        self.assertEqual(restored.player.formation_ground_arrays, [])
        self.assertEqual(restored.player.formation_repair_supplies, {})
        self.assertEqual(restored.npc_formations, {})
        self.assertEqual(restored.version, game.version)

    def test_experience_formula_is_bounded(self):
        profile = calculate_formation_profile([node("wood", 7), node("fire", 7)] + [None] * 7, alpha=.7)
        self.assertEqual(formation_battle_experience_gain(profile, 0, 1), 0)
        self.assertLessEqual(formation_battle_experience_gain(profile, 8, .01), 45)

    def test_v2_content_covers_every_world_and_keeps_caps_tight(self):
        config = formation_config()
        self.assertEqual(config["system_version"], 2)
        worlds = set(config["world_names"]) if "world_names" in config else {
            "human", "spirit", "celestial", "demon", "true_demon", "asura",
            "monster_realm", "phantom_underworld", "nether", "hell", "reincarnation",
        }
        self.assertEqual({row["world"] for row in formation_maintenance_definitions().values()}, worlds)
        definitions = formation_material_definitions().values()
        for world in worlds:
            self.assertGreaterEqual(len([row for row in definitions if row["world"] == world]), 2, world)
        basic_ids = {
            "human_black_iron_flag", "spirit_greenwood_token", "celestial_white_gold_token",
            "demon_yin_bone_flag", "true_demon_blood_wood_stake", "asura_blood_iron_flag",
            "monster_bone_token", "phantom_mist_water_orb", "nether_primordial_iron_token",
            "hell_yin_earth_stake", "reincarnation_shore_wood_token",
        }
        basics = [row for row in definitions if row["id"] in basic_ids]
        self.assertEqual(len(basics), len(worlds))
        self.assertTrue(all(row["field_hook"] is None and not row["relation_overrides"] for row in basics))
        self.assertLessEqual(config["settings"]["ground_power_hard_cap_ratio"], .60)
        self.assertLessEqual(config["settings"]["npc_formation_bonus_cap"], .10)

    def test_every_target_world_stage_has_all_fourteen_basic_natures(self):
        definitions = list(formation_material_definitions().values())
        all_natures = set(formation_config()["nature_channels"])
        target_tiers = {
            "human":range(1, 6), "demon":range(1, 6),
            "spirit":range(1, 9), "true_demon":range(5, 9),
            "monster_realm":range(1, 9), "phantom_underworld":range(1, 9),
            "hell":range(1, 9),
        }
        for world, tiers in target_tiers.items():
            for tier in tiers:
                covered = {
                    row["nature"] for row in definitions
                    if row["world"] == world and int(row["tier"]) == tier
                }
                self.assertEqual(covered, all_natures, f"{world} tier {tier}")
        self.assertEqual(len(definitions), 663)

    def test_generated_progression_materials_are_monotone_and_rule_neutral(self):
        generated = [
            row for row in formation_material_definitions().values()
            if row["id"].startswith("progression_")
        ]
        self.assertTrue(generated)
        self.assertTrue(all(row["field_hook"] is None and not row["relation_overrides"] for row in generated))
        for world in {row["world"] for row in generated}:
            by_tier = {}
            for row in generated:
                if row["world"] == world:
                    by_tier.setdefault(int(row["tier"]), []).append(row)
            prices = [min(row["base_value"] for row in by_tier[tier]) for tier in sorted(by_tier)]
            values = [min(row["formation_value"] for row in by_tier[tier]) for tier in sorted(by_tier)]
            self.assertEqual(prices, sorted(prices))
            self.assertEqual(values, sorted(values))

    def test_excluded_upper_world_formation_catalogs_are_unchanged(self):
        definitions = list(formation_material_definitions().values())
        expected = {"celestial":5, "asura":4, "nether":5, "reincarnation":5}
        self.assertEqual(
            {world:sum(row["world"] == world for row in definitions) for world in expected},
            expected,
        )

    def test_ground_array_transfers_exact_instances_repairs_and_withdraws(self):
        instances = self._give_array()
        self._save_active(instances)
        shown = self.engine.deploy_ground_formation(self.game_id, "player")
        system = shown["formation_system"]
        self.assertIsNone(system["active_formation_id"])
        self.assertEqual(len(system["ground_arrays"]), 1)
        self.assertEqual(sum(row["locked"] for row in system["materials"]), 3)
        array = system["ground_arrays"][0]
        map_location = next(row for row in shown["map"]["locations"] if row["id"] == array["location_id"])
        self.assertEqual(map_location["ground_formations"][0]["id"], array["id"])

        game = self.engine.store.load(self.game_id)
        other_location = next(
            location_id for location_id in self.engine.maps.worlds["human"]["locations"]
            if location_id["id"] != game.player.location_id
        )["id"]
        game.player.location_id = other_location
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "亲临"):
            self.engine.withdraw_ground_formation(self.game_id, array["id"])

        game = self.engine.store.load(self.game_id)
        game.player.location_id = array["location_id"]
        game.player.formation_ground_arrays[0]["durability"] = 50.0
        game.player.formation_repair_supplies["human_array_marrow"] = 1
        self.engine.store.save(game)
        repaired = self.engine.repair_ground_formation(
            self.game_id, array["id"], "human_array_marrow", 1,
        )
        self.assertEqual(repaired["formation_system"]["ground_arrays"][0]["durability"], 68.0)
        self.assertEqual(repaired["formation_system"]["repair_supplies"], [])
        withdrawn = self.engine.withdraw_ground_formation(self.game_id, array["id"])
        self.assertEqual(withdrawn["formation_system"]["ground_arrays"], [])
        restored_ids = {row["storage_id"] for row in withdrawn["formation_system"]["materials"]}
        self.assertEqual(restored_ids, {row["id"] for row in instances})

    def test_creator_can_reclaim_sect_array_after_sect_falls_and_allegiance_changes(self):
        instances = self._give_array()
        self._save_active(instances, "覆宗归器阵")
        game = self.engine.store.load(self.game_id)
        game.player.faction_id = "tianjian"
        game.sects["tianjian"].founded_by_player = True
        game.sects["tianjian"].founder_player_id = game.id
        self.engine.store.save(game)
        shown = self.engine.deploy_ground_formation(self.game_id, "sect")
        array = shown["formation_system"]["ground_arrays"][0]
        game = self.engine.store.load(self.game_id)
        original_sect_id = str(array["owner_id"])
        game.sects[original_sect_id].extinct = True
        game.player.faction_id = next(
            sect_id for sect_id, sect in game.sects.items()
            if sect_id != original_sect_id and sect.world == game.player.world
        )
        self.engine.store.save(game)

        withdrawn = self.engine.withdraw_ground_formation(self.game_id, array["id"])
        self.assertEqual(withdrawn["formation_system"]["ground_arrays"], [])
        self.assertEqual(
            {row["storage_id"] for row in withdrawn["formation_system"]["materials"]},
            {row["id"] for row in instances},
        )

    def test_ground_power_and_persistent_combat_wear_are_bounded(self):
        instances = self._give_array()
        self._save_active(instances)
        self.engine.deploy_ground_formation(self.game_id, "player")
        game = self.engine.store.load(self.game_id)
        array = game.player.formation_ground_arrays[0]
        profile = self.engine._ground_profile(game.player, array)
        median_tier = sorted(binding["acquired_tier"] for binding in array["bindings"] if binding)[1]
        hard_cap = expected_combat_power(median_tier, 1) * formation_config()["settings"]["ground_power_hard_cap_ratio"]
        self.assertLessEqual(ground_formation_power(array, profile), hard_cap + .01)
        before = array["durability"]
        self.engine._combat(game, {
            "target_name":"镇地试阵者", "target_power":combat_power(game.player),
            "target_realm_index":game.player.realm_index, "target_layer":game.player.layer,
            "combat_type":"cultivator", "objective":"repel", "max_rounds":8,
        }, False, random.Random(112))
        array = next(row for row in game.player.formation_ground_arrays if row["id"] == array["id"])
        wear = before - array["durability"]
        self.assertGreaterEqual(wear, formation_config()["settings"]["ground_battle_min_wear"])
        self.assertLessEqual(wear, formation_config()["settings"]["ground_battle_max_wear"])
        self.assertEqual(array["battles"], 1)

    def test_npc_arrays_are_persistent_capped_and_maintained_by_world_time(self):
        game = self.engine.store.load(self.game_id)
        self.assertTrue(game.npc_formations)
        npc_id, entry = next(iter(game.npc_formations.items()))
        original = copy.deepcopy(entry)
        self.assertLessEqual(self.engine._npc_formation_power_multiplier(game, npc_id), 1.08 + 1e-9)
        entry["durability"] = 20.0
        entry["last_maintenance_year"] = game.player.age
        game.player.age += 100
        self.assertTrue(self.engine._ensure_npc_formations(game))
        self.assertEqual(entry["durability"], 32.0)
        self.assertEqual(entry["slots"], original["slots"])

    def test_offscreen_npc_profile_skips_full_spectrum_but_preserves_battle_rules(self):
        game = self.engine.store.load(self.game_id)
        npc_id = next(iter(game.npc_formations))
        fast = self.engine._npc_formation_profile(game, npc_id)
        detailed = self.engine._npc_formation_profile(game, npc_id, detailed_spectrum=True)
        self.assertEqual(fast["advanced"]["eigenvalues"], [])
        self.assertTrue(detailed["advanced"]["eigenvalues"])
        self.assertEqual(fast["static_player_multipliers"], detailed["static_player_multipliers"])
        self.assertEqual(fast["static_enemy_multipliers"], detailed["static_enemy_multipliers"])
        self.assertEqual(fast["round_rules"], detailed["round_rules"])

    def test_enemy_array_broadcasts_once_and_persists_its_wear(self):
        game = self.engine.store.load(self.game_id)
        npc_id = next(iter(game.npc_formations))
        npc = self.engine._find_npc(game, npc_id)
        before = float(game.npc_formations[npc_id]["durability"])
        self.engine._combat(game, {
            "target_name":npc.name, "target_power":self.engine._npc_power(npc),
            "target_realm_index":npc.realm_index, "target_layer":npc.layer,
            "npc_id":npc.id, "combat_type":"cultivator", "objective":"repel", "max_rounds":5,
        }, False, random.Random(902))
        report = game.last_combat_report
        self.assertIsNotNone(report["enemy_formation_profile"])
        self.assertTrue(any(
            "敌方" in event and "阵" in event
            for round_row in report["rounds"] for event in round_row["events"]
        ))
        wear = before - game.npc_formations[npc_id]["durability"]
        self.assertGreaterEqual(wear, 1.0)
        self.assertLessEqual(wear, 26.0)

    def test_real_sect_guard_adds_independent_war_power_and_wears(self):
        instances = self._give_array()
        self._save_active(instances, "天剑护山阵")
        game = self.engine.store.load(self.game_id)
        game.player.faction_id = "tianjian"
        game.sects["tianjian"].founded_by_player = True
        game.sects["tianjian"].founder_player_id = game.id
        self.engine.store.save(game)
        shown = self.engine.deploy_ground_formation(self.game_id, "sect")
        guard_id = shown["formation_system"]["ground_arrays"][0]["id"]
        game = self.engine.store.load(self.game_id)
        relation = self.engine._war_relation(game, "sect", "wanmo", "tianjian")
        self.engine._set_diplomatic_relation(game, relation, "war", "wanmo", "tianjian", "sect", -80)
        war = game.wars[-1]
        with_guard = self.engine._war_total_power(game, war, "defender")
        guard = next(row for row in game.player.formation_ground_arrays if row["id"] == guard_id)
        before = guard["durability"]
        guard_power = self.engine._sect_guard_power(game, "tianjian")
        self.assertGreater(guard_power, 0)
        self.engine._wear_war_guard_arrays(game, war)
        self.assertEqual(before - guard["durability"], 2.5)
        guard["durability"] = 0
        without_guard = self.engine._war_total_power(game, war, "defender")
        self.assertGreater(with_guard, without_guard)

    def test_random_ground_arrays_never_break_absolute_power_cap(self):
        definitions = list(formation_material_definitions().values())
        rng = random.Random(20260915)
        for _ in range(1200):
            selected = [copy.deepcopy(rng.choice(definitions)) for _ in range(rng.randint(2, 9))]
            slots = [None] * 9
            for position, definition in zip(rng.sample(range(9), len(selected)), selected):
                slots[position] = {
                    "name":definition["name"], "acquired_tier":definition["tier"],
                    "formation_profile":definition,
                }
            array = {"bindings":slots, "durability":rng.uniform(1, 100)}
            profile = calculate_formation_profile(
                [binding["formation_profile"] if binding else None for binding in slots],
                alpha=rng.uniform(.5, .9), name="压力阵",
            )
            median = sorted(definition["tier"] for definition in selected)[len(selected) // 2]
            cap = expected_combat_power(median, 1) * formation_config()["settings"]["ground_power_hard_cap_ratio"]
            self.assertLessEqual(ground_formation_power(array, profile), cap + .01)


if __name__ == "__main__":
    unittest.main()
