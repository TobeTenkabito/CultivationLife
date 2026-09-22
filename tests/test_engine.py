import json
import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cultivation_life.content_registry import FACTION_DEFINITIONS, WORLD_SYSTEMS
from cultivation_life.combat_system import BattleUnit, PlayerCombatSystem
from cultivation_life.engine import GameEngine, encode_rng
from cultivation_life.models import HistoryRecord
from cultivation_life.rules import (
    TECHNIQUE_CATALOG, add_item, assign_technique, combat_power, create_technique,
    combat_root_mana_cost_multiplier, max_hp, max_mp, opportunity_multiplier,
    opportunity_required, root_definition, qi_level_threshold, spirit_root_mana_multiplier,
)


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.engine = GameEngine(root)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_advance_choose_and_reload(self):
        created = self.engine.create_game("青禾", "heavenly_metal_wood", "dao", 12345, "metal")
        advanced = self.engine.advance(created["id"], "cultivate")
        self.assertEqual(advanced["player"]["age"], 17)
        self.assertIsNotNone(advanced["pending_event"])
        choice = next(entry for entry in advanced["pending_event"]["choices"] if entry["enabled"])
        resolved = self.engine.choose(created["id"], choice["id"])
        self.assertIsNone(resolved["pending_event"])
        reloaded = self.engine.get_game(created["id"])
        self.assertEqual(reloaded["player"]["age"], 17)
        self.assertGreaterEqual(len(reloaded["history"]), 3)

    def test_settings_are_persisted_and_presented(self):
        created = self.engine.create_game("静默观战", "supreme_water", "dao", 12346, "water")
        self.assertTrue(created["settings"]["combat_popup"])
        self.assertTrue(created["settings"]["achievement_popup"])
        self.assertFalse(created["settings"]["auto_advance_player_wars"])
        self.assertTrue(created["settings"]["guixu_event_popup"])
        changed = self.engine.update_setting(created["id"], "combat_popup", False)
        self.assertFalse(changed["settings"]["combat_popup"])
        changed = self.engine.update_setting(created["id"], "auto_advance_player_wars", True)
        self.assertTrue(changed["settings"]["auto_advance_player_wars"])
        changed = self.engine.update_setting(created["id"], "guixu_event_popup", False)
        self.assertFalse(changed["settings"]["guixu_event_popup"])
        self.assertEqual(self.engine.get_game(created["id"])["settings"], changed["settings"])

    def test_choice_requirement_is_exposed_without_leaking_effects(self):
        created = self.engine.create_game("照影", "supreme_water", "dao", 2, "water")
        game = self.engine.store.load(created["id"])
        event = self.engine.events_by_id["EVT_ENCOUNTER_INJURED_001"]
        shown = self.engine._instantiate_event(event, game, random.Random(1))
        help_choice = next(choice for choice in shown["choices"] if choice["id"] == "help")
        self.assertFalse(help_choice["enabled"])
        self.assertNotIn("effects", help_choice)

    def test_equal_power_combat_never_kills(self):
        created = self.engine.create_game("平势", "supreme_earth", "demonic", 8, "earth")
        game = self.engine.store.load(created["id"])
        for seed in range(30):
            game.player.alive = True
            game.player.death_reason = None
            game.player.hp = max_hp(game.player)
            game.player.mp = max_mp(game.player)
            target = {"target_name": "同阶修士", "target_power": combat_power(game.player), "target_realm_index": 0}
            result, _ = self.engine._combat(game, target, True, random.Random(seed))
            self.assertNotEqual(result, "killed")

    def test_breakthrough_consumes_opportunity_and_changes_realm(self):
        created = self.engine.create_game("破境", "supreme_metal", "dao", 99, "metal")
        game = self.engine.store.load(created["id"])
        game.player.opportunity = 30
        self.engine._resolve_breakthroughs(game, random.Random(4))
        self.assertEqual(game.player.realm_index, 0)
        self.assertTrue(game.player.awaiting_major_breakthrough)
        self.engine.store.save(game)
        result = self.engine.breakthrough(created["id"])
        self.assertEqual(result["player"]["realm_index"], 1)
        self.assertTrue(any(record["event_id"] == "SYS_MAJOR_BREAKTHROUGH" for record in result["history"]))

    def test_saved_json_does_not_store_derived_combat_power(self):
        created = self.engine.create_game("守真", "supreme_fire", "confucian", 17, "fire")
        save_path = Path(self.temp.name) / "data" / "saves" / f"{created['id']}.json"
        raw = json.loads(save_path.read_text(encoding="utf-8"))
        self.assertNotIn("combat_power", raw["player"])

    def test_void_and_mahayana_tribulations_scale_as_designed(self):
        created = self.engine.create_game("渡劫", "heavenly_metal_water", "buddhist", 71, "water")
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 6
        game.player.layer = 1
        game.player.age = 4000
        game.player.next_tribulation_age = 4000
        game.player.tribulation_power = 0.001
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        self.engine._check_tribulation(game, random.Random(1))
        self.assertEqual(game.active_trial["kind"], "periodic_thunder")
        self.engine.store.save(game)
        for _ in range(3):
            self.engine.choose(created["id"], "strike")
        game = self.engine.store.load(created["id"])
        self.assertEqual(game.player.tribulation_count, 1)
        self.assertEqual(game.player.tribulation_power, 0.002)
        self.assertEqual(game.player.next_tribulation_age, 7000)

        game.player.realm_index = 8
        game.player.age = 10000
        game.player.next_tribulation_age = 10000
        game.player.tribulation_power = 0.002
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        self.engine._check_tribulation(game, random.Random(1))
        self.engine.store.save(game)
        for _ in range(3):
            self.engine.choose(created["id"], "strike")
        game = self.engine.store.load(created["id"])
        self.assertEqual(game.player.tribulation_count, 2)
        self.assertEqual(game.player.tribulation_power, 0.004)
        self.assertEqual(game.player.next_tribulation_age, 13000)

    def test_five_element_technique_requires_matching_root(self):
        created = self.engine.create_game("相合", "heavenly_metal_wood", "dao", 3)
        game = self.engine.store.load(created["id"])
        wood_art = create_technique("TEST_WOOD", "木行试法", "dao", "wood", 0.1, 0.1, 0.1, 10)
        water_art = create_technique("TEST_WATER", "水行试法", "dao", "water", 0.1, 0.1, 0.1, 10)
        assign_technique(game.player, wood_art, "main")
        self.assertEqual(game.player.technique.id, "TEST_WOOD")
        with self.assertRaisesRegex(ValueError, "灵根属性"):
            assign_technique(game.player, water_art, "main")

    def test_mismatched_technique_cannot_be_used_after_state_tampering(self):
        created = self.engine.create_game("守规", "supreme_fire", "dao", 4, "fire")
        game = self.engine.store.load(created["id"])
        game.player.technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        game.player.technique.element = "water"
        with self.assertRaisesRegex(ValueError, "无法修炼"):
            self.engine.store.save(game)
            self.engine.advance(created["id"], "cultivate")
        result, _ = self.engine._combat(
            game,
            {"target_name": "试剑傀儡", "target_power": 1, "target_realm_index": 0},
            False,
            random.Random(1),
        )
        self.assertEqual(result, "technique_blocked")

    def test_rootless_player_cannot_break_through_without_repair(self):
        created = self.engine.create_game("凡骨", "none", "dao", 12)
        game = self.engine.store.load(created["id"])
        game.player.opportunity = 999
        self.engine._resolve_breakthroughs(game, random.Random(4))
        self.assertEqual(game.player.realm_index, 0)
        self.assertEqual(game.player.opportunity, 0)

    def test_rootless_opening_enters_mortal_event_chain(self):
        created = self.engine.create_game("凡骨", "none", "dao", 42)
        advanced = self.engine.advance(created["id"], "cultivate")
        self.assertEqual(advanced["pending_event"]["id"], "EVT_MORTAL_BODY_BEGIN_001")

    def test_body_training_lifespan_is_capped_at_three_hundred(self):
        created = self.engine.create_game("武者", "none", "dao", 15)
        game = self.engine.store.load(created["id"])
        game.player.lifespan = 298
        outcome, _ = self.engine._effect(
            {"type": "extend_lifespan", "value": 20}, game, {"id": "TEST"}, random.Random(1)
        )
        self.assertIsNone(outcome)
        self.assertEqual(game.player.lifespan, 300)

    def test_repaired_root_is_weaker_than_innate_pseudo_root(self):
        created = self.engine.create_game("补天", "none", "dao", 18)
        game = self.engine.store.load(created["id"])
        self.engine._effect({"type": "acquire_root", "affinity": "metal"}, game, {"id": "TEST"}, random.Random(1))
        self.assertTrue(game.player.acquired_root)
        self.assertTrue(game.player.spirit_root.startswith("acquired_"))
        self.assertLess(root_definition(game.player.spirit_root)["efficiency"], root_definition("pseudo_all")["efficiency"])

    def test_treasure_costs_one_resource_then_offers_three_rewards(self):
        created = self.engine.create_game("探宝", "supreme_metal", "dao", 81, "metal")
        game = self.engine.store.load(created["id"])
        before_hp, before_mp = game.player.hp, game.player.mp
        before_items = sum(item.quantity for item in game.player.inventory)
        expected_gain = 2 * opportunity_multiplier(game.player)

        shown = self.engine.advance(created["id"], "treasure")
        hp_lost = shown["player"]["hp"] < before_hp
        mp_lost = shown["player"]["mp"] < before_mp
        self.assertNotEqual(hp_lost, mp_lost)
        self.assertAlmostEqual(shown["player"]["opportunity"], expected_gain)
        self.assertEqual(shown["pending_event"]["id"], "EVT_TREASURE_REWARD_SELECT_001")
        self.assertEqual({choice["id"] for choice in shown["pending_event"]["choices"]}, {"artifact", "technique", "pill"})

        claimed = self.engine.choose(created["id"], "artifact")
        self.assertGreater(sum(item["quantity"] for item in claimed["player"]["inventory"]), before_items)

    def test_treasure_reward_pool_keeps_lower_tiers_and_technique_does_not_auto_equip(self):
        created = self.engine.create_game("古卷择取", "supreme_metal", "dao", 82, "metal", preset_id="nascent")
        game = self.engine.store.load(created["id"])
        for category in ("artifact", "technique", "pill"):
            tiers = {int(row["tier"]) for row in self.engine._treasure_reward_pool(game, category)}
            self.assertIn(1, tiers)
            self.assertIn(4, tiers)
        original_main = game.player.technique.id if game.player.technique else None
        event = self.engine._prepare_treasure_reward_event(game, random.Random(8))
        game.pending_event = event
        chosen_id = event["runtime"]["rewards"]["technique"]["content_id"]
        self.engine.store.save(game)

        shown = self.engine.choose(created["id"], "technique")
        self.assertIn(chosen_id, {entry["id"] for entry in shown["player"]["known_techniques"]})
        self.assertEqual(shown["player"]["technique"]["id"] if shown["player"]["technique"] else None, original_main)

    def test_same_complete_technique_can_fill_any_slot(self):
        created = self.engine.create_game("万法", "supreme_metal", "dao", 91, "metal")
        game = self.engine.store.load(created["id"])
        event = self.engine.events_by_id["EVT_TECHNIQUE_STELE_001"]
        for slot in ("main", "support", "combat"):
            if slot == "combat":
                game.player.qi_experience["spirit"] = qi_level_threshold(3)
            game.pending_event = self.engine._instantiate_event(event, game, random.Random(2))
            # choose() reloads, so directly execute the declarative effect for this slot.
            self.engine._effect(
                {"type": "equip_technique", "technique_id": "TECH_VOID_CYCLE", "slot": slot},
                game, game.pending_event, random.Random(2),
            )
        self.assertEqual(game.player.technique.id, "TECH_VOID_CYCLE")
        self.assertEqual(game.player.support_technique.id, "TECH_VOID_CYCLE")
        self.assertTrue(any(entry.id == "TECH_VOID_CYCLE" for entry in game.player.combat_techniques))

    def test_new_character_starts_with_all_technique_slots_empty(self):
        created = self.engine.create_game("白身", "supreme_wood", "dao", 101)
        self.assertIsNone(created["player"]["technique_slots"]["main"])
        self.assertIsNone(created["player"]["technique_slots"]["support"])
        self.assertEqual(created["player"]["technique_slots"]["combat"], [])

    def test_body_training_lifespan_is_not_lost_on_entering_qi(self):
        created = self.engine.create_game("逆命", "none", "dao", 102)
        game = self.engine.store.load(created["id"])
        game.player.lifespan = 260
        game.player.spirit_root = "acquired_metal"
        game.player.acquired_root = True
        game.player.technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        game.player.opportunity = 30
        self.engine._resolve_breakthroughs(game, random.Random(3))
        self.engine.store.save(game)
        self.engine.breakthrough(created["id"])
        game = self.engine.store.load(created["id"])
        self.assertEqual(game.player.realm_index, 1)
        self.assertEqual(game.player.lifespan, 260)

    def test_mortal_and_cultivator_event_pools_are_strictly_separated(self):
        created = self.engine.create_game("凡人", "supreme_metal", "dao", 103)
        game = self.engine.store.load(created["id"])
        mortal_event = self.engine._select_event(game, "travel", random.Random(1))
        self.assertIn("mortal", mortal_event["tags"])
        game.player.realm_index = 1
        cultivator_event = self.engine._select_event(game, "travel", random.Random(1))
        self.assertNotIn("mortal", cultivator_event["tags"])
        self.assertNotEqual(mortal_event["id"], "EVT_COMBAT_ROBBER_001")

    def test_failed_early_body_training_forces_aspiration_at_twenty_five(self):
        created = self.engine.create_game("凡志", "none", "dao", 104)
        game = self.engine.store.load(created["id"])
        game.player.age = 24
        game.player.body_training = 2
        self.engine.store.save(game)
        advanced = self.engine.advance(created["id"], "travel")
        self.assertEqual(advanced["pending_event"]["id"], "EVT_MORTAL_ASPIRATION_001")

    def test_jinque_requires_nascent_realm_for_active_use_and_keeps_base_efficiency(self):
        created = self.engine.create_game("雷修", "mutated_thunder", "dao", 105)
        game = self.engine.store.load(created["id"])
        add_item(game.player, "jinque_wood")
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "上面记载的法门或者材料不是你现阶段能集齐的"):
            self.engine.use_item(created["id"], "jinque_wood")
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        base_efficiency = root_definition(game.player.spirit_root)["efficiency"]
        self.engine.store.save(game)
        result = self.engine.use_item(created["id"], "jinque_wood")
        self.assertIn("wood", result["player"]["additional_roots"])
        self.assertIn("木", result["player"]["additional_root_names"])
        self.assertIn("后天补全：木", result["player"]["spirit_root_display"])
        self.assertEqual(result["player"]["spirit_root_efficiency"], base_efficiency)

    def test_mortal_jinque_chain_repairs_the_specific_root(self):
        created = self.engine.create_game("残书", "none", "dao", 106)
        game = self.engine.store.load(created["id"])
        add_item(game.player, "jinque_wind")
        pending = self.engine._instantiate_event(self.engine.events_by_id["EVT_MORTAL_ROOT_COMPLETE_001"], game, random.Random(1))
        wind_choice = next(choice for choice in pending["choices"] if choice["id"] == "wind")
        thunder_choice = next(choice for choice in pending["choices"] if choice["id"] == "thunder")
        self.assertTrue(wind_choice["enabled"])
        self.assertFalse(thunder_choice["enabled"])
        self.engine._effect({"type": "acquire_root", "affinity": "wind"}, game, pending, random.Random(1))
        self.assertEqual(game.player.spirit_root, "acquired_wind")
        self.assertEqual(root_definition(game.player.spirit_root)["efficiency"], 0.70)

    def test_jinque_find_effect_can_access_item_catalog(self):
        created = self.engine.create_game("寻书", "none", "dao", 107)
        game = self.engine.store.load(created["id"])
        result, summary = self.engine._effect(
            {"type": "add_random_jinque"}, game, {"id": "EVT_MORTAL_JINQUE_FIND_001"}, random.Random(7)
        )
        self.assertEqual(result, "jinque_found")
        self.assertIn("金阙残书", summary)
        self.assertTrue(any(item.id.startswith("jinque_") for item in game.player.inventory))

    def test_mortal_root_completion_starts_at_one_percent_from_age_thirty_five(self):
        class ZeroRoll:
            @staticmethod
            def random():
                return 0.0

        created = self.engine.create_game("晚缘", "none", "dao", 108)
        game = self.engine.store.load(created["id"])
        add_item(game.player, "jinque_metal")
        game.player.age = 34
        self.assertEqual(self.engine._mortal_root_completion_chance(game.player), 0.0)
        self.assertFalse(self.engine._maybe_mortal_root_completion(game, ZeroRoll()))
        game.player.age = 35
        self.assertEqual(self.engine._mortal_root_completion_chance(game.player), 0.01)
        self.assertTrue(self.engine._maybe_mortal_root_completion(game, ZeroRoll()))
        self.assertEqual(game.pending_event["id"], "EVT_MORTAL_ROOT_COMPLETE_001")
        game.player.age = 36
        self.assertEqual(self.engine._mortal_root_completion_chance(game.player), 0.02)

    def test_every_game_initializes_three_sects_per_world_and_sorted_human_rosters(self):
        created = self.engine.create_game("观山", "supreme_metal", "dao", 109)
        game = self.engine.store.load(created["id"])
        self.assertEqual(set(game.sects), set(FACTION_DEFINITIONS))
        self.assertEqual(sum(sect.world == "human" for sect in game.sects.values()), 4)
        self.assertEqual(sum(sect.world == "spirit" for sect in game.sects.values()), 3)
        spirit_npcs = [
            npc for npc in [*(npc for sect in game.sects.values() for npc in sect.npcs), *game.world_npcs.values()]
            if npc.realm_index == 5 and npc.world == "human"
        ]
        self.assertEqual(len(spirit_npcs), 1)
        self.assertTrue(all(npc.layer <= 3 for npc in spirit_npcs))
        game.player.faction_id = "tianjian"
        faction = self.engine._public_faction(game)
        ranking = [(npc["realm_index"], npc["layer"]) for npc in faction["roster"]]
        self.assertEqual(ranking, sorted(ranking, reverse=True))
        self.assertEqual(sum(entry["is_player"] for entry in faction["roster"]), 1)
        self.assertTrue(any(entry["name"] == "观山" and entry["is_player"] for entry in faction["roster"]))

    def test_faction_event_catalog_has_ten_common_and_five_per_sect(self):
        common = [event for event in self.engine.events if "faction_common" in event.get("tags", [])]
        self.assertEqual(len(common), 10)
        for faction_id in ("tianjian", "wanmo", "puti"):
            unique = [
                event for event in self.engine.events
                if "faction_unique" in event.get("tags", []) and f"faction:{faction_id}" in event.get("tags", [])
            ]
            self.assertEqual(len(unique), 5)

    def test_nascent_member_can_fix_annual_faction_reward(self):
        created = self.engine.create_game("议事", "supreme_wood", "dao", 110)
        game = self.engine.store.load(created["id"])
        self.engine._effect(
            {"type": "join_faction", "faction_id": "tianjian"}, game, {"id": "TEST"}, random.Random(1)
        )
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "元婴初期"):
            self.engine.set_faction_reward(created["id"], "vitality")
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.layer = 1
        self.engine.store.save(game)
        selected = self.engine.set_faction_reward(created["id"], "vitality")
        self.assertEqual(selected["faction"]["reward_preference"], "vitality")
        game = self.engine.store.load(created["id"])
        before = game.player.faction_hp_bonus
        self.engine._annual_sect_update(game, random.Random(2))
        self.assertEqual(game.player.faction_hp_bonus, before + 2)

    def test_faction_war_with_player_uses_automatic_combat_report(self):
        created = self.engine.create_game("应战", "supreme_fire", "demonic", 111)
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "wanmo"
        game.player.realm_index = 1
        result, _ = self.engine._effect(
            {"type": "faction_war"}, game, {"id": "EVT_FACTION_COMMON_WAR_001"}, random.Random(111)
        )
        self.assertIn(result, {"victory", "survived", "dead"})
        self.assertIsNotNone(game.last_combat_report)
        self.assertEqual(game.last_combat_report["objective"], "repel")

        created = self.engine.create_game("镇阵", "supreme_fire", "demonic", 112)
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "wanmo"
        game.player.realm_index = 4
        game.player.layer = 1
        result, _ = self.engine._effect(
            {"type": "faction_war", "contribution": 9}, game,
            {"id": "EVT_FACTION_COMMON_WAR_001"}, random.Random(112)
        )
        self.assertIn(result, {"victory", "survived", "dead"})
        self.assertEqual(game.last_combat_report["artificial_conditions"], ["大阵"])

    def test_pre_nascent_member_receives_one_random_annual_welfare(self):
        created = self.engine.create_game("俸禄", "supreme_earth", "dao", 113)
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "tianjian"
        game.player.realm_index = 2
        before = (
            game.player.opportunity,
            game.player.faction_hp_bonus,
            game.player.faction_mp_bonus,
            game.player.faction_combat_bonus,
        )
        self.engine._annual_sect_update(game, random.Random(3))
        after = (
            game.player.opportunity,
            game.player.faction_hp_bonus,
            game.player.faction_mp_bonus,
            game.player.faction_combat_bonus,
        )
        self.assertNotEqual(after, before)
        self.assertTrue(any(record.event_id == "SYS_FACTION_WELFARE" for record in game.history))

    def test_legacy_save_without_sects_is_migrated_on_load(self):
        created = self.engine.create_game("旧卷", "supreme_water", "dao", 114)
        save_path = Path(self.temp.name) / "data" / "saves" / f"{created['id']}.json"
        raw = json.loads(save_path.read_text(encoding="utf-8"))
        raw.pop("sects")
        raw.pop("world_rules_version")
        raw["version"] = 2
        raw["player"].pop("qi_experience", None)
        for field in (
            "faction_id", "faction_join_age", "faction_contribution", "faction_reward_preference",
            "faction_hp_bonus", "faction_mp_bonus", "faction_combat_bonus",
        ):
            raw["player"].pop(field)
        save_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        loaded = self.engine.get_game(created["id"])
        self.assertFalse(loaded["faction"]["member"])
        self.assertTrue(all(entry["experience"] == 0 for entry in loaded["player"]["qi_mastery"]))
        migrated = json.loads(save_path.read_text(encoding="utf-8"))
        self.assertEqual(set(migrated["sects"]), set(FACTION_DEFINITIONS))

    def test_world_npc_template_age_change_preserves_elapsed_years(self):
        created = self.engine.create_game("故人年岁", "supreme_water", "dao", 115)
        save_path = Path(self.temp.name) / "data" / "saves" / f"{created['id']}.json"
        raw = json.loads(save_path.read_text(encoding="utf-8"))
        raw["world_rules_version"] = 6
        raw.pop("world_npc_template_ages", None)
        raw["world_npcs"]["xiang_zhili"]["age"] = 2834
        save_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        self.engine.get_game(created["id"])
        migrated = json.loads(save_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["world_npcs"]["xiang_zhili"]["age"], 1234)
        self.assertEqual(migrated["world_npc_template_ages"]["xiang_zhili"], 1210)

    def test_human_realm_stops_at_early_spirit_until_world_crossing_exists(self):
        created = self.engine.create_game("界壁", "otherworld", "dao", 116)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 3
        game.player.opportunity = 10**9
        self.engine._resolve_breakthroughs(game, random.Random(1))
        self.assertEqual((game.player.realm_index, game.player.layer), (5, 3))
        self.assertTrue(game.player.awaiting_spirit_realm_crossing)
        self.assertEqual(sum(record.event_id == "SYS_HUMAN_REALM_LIMIT" for record in game.history), 1)
        self.engine._resolve_breakthroughs(game, random.Random(3))
        self.assertEqual(sum(record.event_id == "SYS_HUMAN_REALM_LIMIT" for record in game.history), 1)

    def test_realm_exclusive_events_expire_outside_exact_realm(self):
        realm_tags = {1: "realm:qi", 2: "realm:foundation", 3: "realm:core", 4: "realm:nascent"}
        created = self.engine.create_game("四境", "supreme_metal", "dao", 117)
        game = self.engine.store.load(created["id"])
        exclusive = [event for event in self.engine.events if "realm_exclusive" in event.get("tags", [])]
        self.assertEqual(len(exclusive), 24)
        for realm_index, tag in realm_tags.items():
            events = [event for event in exclusive if tag in event["tags"]]
            self.assertEqual(len(events), 6)
            for event in events:
                game.player.realm_index = realm_index
                self.assertTrue(self.engine._condition(event["conditions"], game))
                game.player.realm_index = realm_index + 1
                self.assertFalse(self.engine._condition(event["conditions"], game))

    def test_jinque_acquisition_can_repeat_before_thirty_five_and_drops_after_first_trigger(self):
        created = self.engine.create_game("多卷", "none", "dao", 118)
        game = self.engine.store.load(created["id"])
        game.player.age = 20
        acquisition = [event for event in self.engine.events if "jinque_acquisition" in event.get("tags", [])]
        self.assertGreaterEqual(len(acquisition), 6)
        self.assertTrue(all(event.get("repeat") != "once" for event in acquisition))
        event = self.engine.events_by_id["EVT_MORTAL_JINQUE_FIND_001"]
        self.assertTrue(self.engine._condition(event["conditions"], game))
        before = self.engine._event_weight(event, game, "travel")
        game.history.append(HistoryRecord(
            "TEST_JINQUE", 1, 20, "得书", "take", "jinque_found", "获得残书。", {},
            ["mortal", "jinque_acquisition"],
        ))
        after = self.engine._event_weight(event, game, "travel")
        self.assertAlmostEqual(after, before * 0.20)

    def test_cultivator_jinque_discovery_expires_at_core_realm(self):
        created = self.engine.create_game("早得造化", "supreme_metal", "dao", 404)
        game = self.engine.store.load(created["id"])
        event = self.engine.events_by_id["EVT_CULTIVATOR_JINQUE_001"]
        self.assertIn("jinque_acquisition", event["tags"])
        game.player.realm_index = 2
        self.assertTrue(self.engine._condition(event["conditions"], game))
        game.player.realm_index = 3
        self.assertFalse(self.engine._condition(event["conditions"], game))

    def test_market_never_offers_lower_or_two_tiers_higher_goods(self):
        for realm_index in (1, 2, 3, 4):
            created = self.engine.create_game(f"坊市{realm_index}", "supreme_metal", "dao", 200 + realm_index)
            game = self.engine.store.load(created["id"])
            game.player.realm_index = realm_index
            game.player.age += 1
            self.engine._ensure_market(game, random.Random(realm_index))
            tiers = {offer["tier"] for offer in game.market_offers}
            self.assertTrue(tiers <= {realm_index, realm_index + 1})
            self.assertNotIn(realm_index - 1, tiers)
            if realm_index == 3:
                self.assertNotIn(5, tiers)

    def test_general_and_material_markets_have_six_slots_and_independent_locks(self):
        created = self.engine.create_game(
            "锁市", "supreme_metal", "dao", 219, preset_id="core",
        )
        shown = self.engine.get_game(created["id"])
        market = shown["market"]
        self.assertEqual(len(market["offers"]), 6)
        self.assertEqual(len(market["material_offers"]), 6)
        general = market["offers"][0]
        material = market["material_offers"][0]
        self.engine.toggle_market_offer_lock(created["id"], general["id"])
        locked = self.engine.toggle_market_offer_lock(created["id"], material["id"])
        self.assertEqual(sum(row["locked"] for row in locked["market"]["offers"]), 1)
        self.assertEqual(sum(row["locked"] for row in locked["market"]["material_offers"]), 1)

        old_general = next(row for row in locked["market"]["offers"] if row["locked"])
        old_material = next(row for row in locked["market"]["material_offers"] if row["locked"])
        game = self.engine.store.load(created["id"])
        game.player.age += 1
        self.engine._ensure_market(game, random.Random(220))
        self.engine.store.save(game)
        refreshed = self.engine.get_game(created["id"])["market"]
        self.assertEqual(len(refreshed["offers"]), 6)
        self.assertEqual(len(refreshed["material_offers"]), 6)
        self.assertEqual(
            next(row for row in refreshed["offers"] if row["locked"])["id"],
            old_general["id"],
        )
        retained_material = next(row for row in refreshed["material_offers"] if row["locked"])
        self.assertEqual(retained_material["id"], old_material["id"])
        self.assertEqual(retained_material["price"], old_material["price"])

    def test_each_market_shelf_allows_only_one_lock_and_purchase_releases_it(self):
        created = self.engine.create_game(
            "换锁", "supreme_fire", "dao", 220, preset_id="core",
        )
        market = self.engine.get_game(created["id"])["market"]
        first, second = [row for row in market["offers"] if not row["owned"]][:2]
        self.engine.toggle_market_offer_lock(created["id"], first["id"])
        switched = self.engine.toggle_market_offer_lock(created["id"], second["id"])
        locked_ids = {row["id"] for row in switched["market"]["offers"] if row["locked"]}
        self.assertEqual(locked_ids, {second["id"]})
        game = self.engine.store.load(created["id"])
        add_item(game.player, "spirit_stone", second["price"])
        self.engine.store.save(game)
        bought = self.engine.buy_market_offer(created["id"], second["id"])
        purchased = next(row for row in bought["market"]["offers"] if row["id"] == second["id"])
        self.assertTrue(purchased["sold"])
        self.assertFalse(purchased["locked"])

    def test_transformation_manuals_are_ordinary_random_market_goods(self):
        created = self.engine.create_game(
            "寻变化术", "supreme_water", "dao", 218, preset_id="core",
        )
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.age += 1
        self.engine._clear_market(game)
        self.engine._ensure_market(game, random.Random(218))
        self.engine.store.save(game)
        shown = self.engine.get_game(created["id"])
        self.assertTrue(all("featured" not in row for row in shown["market"]["offers"]))
        self.assertIn("随机流通", shown["transformation_system"]["acquisition_hint"])

    def test_market_purchase_deducts_stones_and_learns_technique(self):
        created = self.engine.create_game("买经", "supreme_metal", "dao", 221)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 1
        add_item(game.player, "spirit_stone", 20)
        game.market_realm_index = 1
        game.market_world = "human"
        game.market_age = game.player.age
        game.market_offers = [{
            "id": "test-art", "kind": "technique", "content_id": "TECH_COMMON_QI",
            "name": "周天纳气篇", "description": "test", "element": "neutral", "price": 8,
            "tier": 1, "tier_name": "练气期", "market_name": "练气期坊市",
            "rare_next_tier": False, "sold": False,
        }]
        self.engine.store.save(game)
        result = self.engine.buy_market_offer(created["id"], "test-art")
        self.assertEqual(result["market"]["spirit_stones"], 12)
        self.assertIn("TECH_COMMON_QI", {art["id"] for art in result["player"]["known_techniques"]})

    def test_commission_is_a_stable_spirit_stone_source(self):
        created = self.engine.create_game("跑腿", "supreme_fire", "dao", 222)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        self.engine.store.save(game)
        result = self.engine.advance(created["id"], "commission")
        stones = next(item["quantity"] for item in result["player"]["inventory"] if item["id"] == "spirit_stone")
        self.assertGreaterEqual(stones, 8)

    def test_nascent_can_decline_normal_sect_duty_but_not_war(self):
        created = self.engine.create_game("议席", "supreme_water", "dao", 223)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.faction_id = "tianjian"
        normal = next(event for event in self.engine.events if "faction" in event.get("tags", []) and "duty" in event.get("tags", []) and "war" not in event.get("tags", []))
        shown = self.engine._instantiate_event(normal, game, random.Random(1))
        self.assertIn("__decline_faction_task", {choice["id"] for choice in shown["choices"]})
        war = next(event for event in self.engine.events if "war" in event.get("tags", []))
        shown_war = self.engine._instantiate_event(war, game, random.Random(1))
        self.assertNotIn("__decline_faction_task", {choice["id"] for choice in shown_war["choices"]})

    def test_nascent_synthetic_faction_choice_survives_reload_and_resolves(self):
        created = self.engine.create_game("议事不失", "supreme_metal", "dao", 233)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.faction_id = "tianjian"
        game.player.faction_contribution = 10
        event = self.engine.events_by_id["EVT_FACTION_COMMON_PATROL_001"]
        game.pending_event = self.engine._instantiate_event(event, game, random.Random(1))
        self.engine.store.save(game)

        reloaded = self.engine.get_game(created["id"])
        self.assertIsNotNone(reloaded["pending_event"])
        resolved = self.engine.choose(created["id"], "__decline_faction_task")
        self.assertIsNone(resolved["pending_event"])
        self.assertEqual(resolved["history"][0]["choice_id"], "__decline_faction_task")

    def test_recruitment_distribution_boundaries_are_exact(self):
        self.assertEqual(self.engine._recruit_realm_index(0.0099), 4)
        self.assertEqual(self.engine._recruit_realm_index(0.01), 3)
        self.assertEqual(self.engine._recruit_realm_index(0.0999), 3)
        self.assertEqual(self.engine._recruit_realm_index(0.10), 2)
        self.assertEqual(self.engine._recruit_realm_index(0.4999), 2)
        self.assertEqual(self.engine._recruit_realm_index(0.50), 1)

    def test_nascent_never_meets_active_robber_event(self):
        created = self.engine.create_game("声名", "supreme_earth", "dao", 224)
        game = self.engine.store.load(created["id"])
        robber = self.engine.events_by_id["EVT_COMBAT_ROBBER_001"]
        game.player.realm_index = 3
        self.assertTrue(self.engine._condition(robber["conditions"], game))
        game.player.realm_index = 4
        self.assertFalse(self.engine._condition(robber["conditions"], game))

    def test_middle_and_late_stage_breakthroughs_extend_lifespan(self):
        created = self.engine.create_game("分段延寿", "supreme_wood", "dao", 225)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        game.player.layer = 3
        game.player.lifespan = 210
        game.player.opportunity = opportunity_required(game.player)
        self.engine._resolve_breakthroughs(game, random.Random(1))
        self.assertEqual(game.player.layer, 3)
        self.assertTrue(game.player.awaiting_minor_breakthrough)
        game.rng_state = encode_rng(random.Random(1))
        self.engine._ensure_market(game, random.Random(99))
        self.engine.store.save(game)
        shown = self.engine.get_game(created["id"])
        self.assertEqual(shown["breakthrough"]["kind"], "minor")
        self.assertEqual(shown["breakthrough"]["target_realm"], "筑基中期")
        self.engine.breakthrough(created["id"])
        game = self.engine.store.load(created["id"])
        middle_lifespan = game.player.lifespan
        self.assertEqual(game.player.layer, 4)
        self.assertGreater(middle_lifespan, 210)
        game.player.layer = 6
        game.player.opportunity = opportunity_required(game.player)
        self.engine._resolve_breakthroughs(game, random.Random(3))
        self.assertEqual(game.player.layer, 6)
        self.assertTrue(game.player.awaiting_minor_breakthrough)
        game.rng_state = encode_rng(random.Random(3))
        self.engine._ensure_market(game, random.Random(98))
        self.engine.store.save(game)
        self.engine.breakthrough(created["id"])
        game = self.engine.store.load(created["id"])
        self.assertEqual(game.player.layer, 7)
        self.assertGreater(game.player.lifespan, middle_lifespan)

    def test_internal_pill_is_used_at_manual_minor_stage_bottleneck(self):
        created = self.engine.create_game("丹破中期", "supreme_metal", "dao", 227)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        game.player.layer = 3
        game.player.opportunity = opportunity_required(game.player)
        add_item(game.player, "true_origin_pill")
        self.engine._resolve_breakthroughs(game, random.Random(9))
        self.engine.store.save(game)

        prepared = self.engine.use_item(created["id"], "true_origin_pill")
        self.assertEqual(prepared["breakthrough"]["chance"]["base"], 0.58)
        self.assertEqual(prepared["breakthrough"]["chance"]["aid_bonus"], 0.18)
        self.assertEqual(prepared["player"]["layer"], 3)

        game = self.engine.store.load(created["id"])
        game.rng_state = encode_rng(random.Random(1))
        self.engine.store.save(game)
        result = self.engine.breakthrough(created["id"])
        self.assertEqual(result["player"]["layer"], 4)
        self.assertFalse(result["player"]["awaiting_minor_breakthrough"])
        self.assertNotIn("true_origin_pill", result["player"]["active_breakthrough_aids"])

    def test_prepared_internal_pill_waits_for_manual_layer_breakthrough(self):
        created = self.engine.create_game("丹不误服", "supreme_metal", "dao", 228)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        game.player.layer = 1
        game.player.opportunity = opportunity_required(game.player)
        game.player.active_breakthrough_aids = ["true_origin_pill"]
        self.engine._resolve_breakthroughs(game, random.Random(1))
        self.assertEqual(game.player.layer, 1)
        self.assertTrue(game.player.awaiting_minor_breakthrough)
        self.assertIn("true_origin_pill", game.player.active_breakthrough_aids)

    def test_intermediate_minor_layer_failures_accumulate_pity_but_stage_gates_do_not(self):
        created = self.engine.create_game("层级保底", "supreme_metal", "dao", 229)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        game.player.layer = 1
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_minor_breakthrough = True
        game.market_realm_index = None
        game.market_world = None
        game.market_age = None
        self.engine._ensure_market(game, random.Random(9))
        game.rng_state = encode_rng(random.Random(2))
        self.engine.store.save(game)

        failed = self.engine.breakthrough(created["id"])
        self.assertEqual(failed["player"]["layer"], 1)
        self.assertEqual(failed["player"]["breakthrough_pity"]["minor:2:1"], 1)
        self.assertAlmostEqual(failed["breakthrough"]["chance"]["pity_bonus"], 0.04)

        game = self.engine.store.load(created["id"])
        game.player.layer = 3
        game.player.breakthrough_pity.clear()
        self.assertEqual(self.engine._record_minor_pity_failure(game.player), 0.0)
        self.assertFalse(game.player.breakthrough_pity)

    def test_joint_companion_major_breakthrough_updates_lifespan_and_void_is_infinite(self):
        created = self.engine.create_game("同心寿元", "supreme_metal", "dao", 230)
        game = self.engine.store.load(created["id"])
        companion = self.engine._relationship_snapshot("joint-life", "道侣", 3, 9, "event", 380, 480)
        game.player.dao_companion = companion
        game.player.realm_index = 3
        game.player.layer = 9
        game.player.joint_companion_breakthrough = {"id":"joint-life", "major":True}
        self.engine._complete_major_breakthrough(game, random.Random(1), "结丹后期")
        self.assertEqual(companion["realm_index"], 4)
        self.assertGreaterEqual(companion["lifespan"], 1000)

        game.player.realm_index = 5
        game.player.layer = 9
        companion.update(realm_index=5, layer=9, lifespan=3150, realm_name="化神后期")
        game.player.joint_companion_breakthrough = {"id":"joint-life", "major":True}
        self.engine._complete_major_breakthrough(game, random.Random(1), "化神后期")
        self.assertEqual(companion["realm_index"], 6)
        self.assertIsNone(companion["lifespan"])
        self.assertIsNotNone(companion["next_tribulation_age"])

    def test_spirit_early_companion_crosses_world_together(self):
        created = self.engine.create_game("携侣飞升", "supreme_metal", "dao", 231)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 1
        game.player.world = "human"
        game.player.dao_companion = self.engine._relationship_snapshot("cross-lover", "青萝", 5, 2, "event", 1800, 3100)
        game.pending_event = None
        self.engine.store.save(game)
        self.engine.begin_spirit_crossing(created["id"])
        game = self.engine.store.load(created["id"])
        self.assertEqual(game.player.joint_spirit_crossing["id"], "cross-lover")
        self.engine._effect({"type":"enter_spirit_realm"}, game, {"id":"test"}, random.Random(1))
        self.assertEqual(game.player.world, "spirit")
        self.assertEqual(game.player.dao_companion["world"], "spirit")

    def test_personal_hunt_and_slay_support_overwhelming_weaker_targets(self):
        class FavorableRng:
            random_calls = 0
            def choice(self, values): return values[0]
            def choices(self, values, weights=None, k=1): return [values[0]]
            def uniform(self, low, high): return low
            def gauss(self, mean, sigma): return mean
            def random(self):
                self.random_calls += 1
                return 0.99 if self.random_calls <= 2 else 0.0
            def randint(self, low, high): return low

        created = self.engine.create_game("以强凌弱", "supreme_fire", "dao", 226)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 3
        game.player.layer = 5
        add_item(game.player, "broken_god")
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        initial_karma = game.player.karma
        hunt_summary = self.engine._personal_combat_step(game, "hunt_beast", FavorableRng())
        self.assertIn("击杀", hunt_summary)
        self.assertEqual(game.player.karma, initial_karma)
        self.assertEqual(game.player.sha_qi, 2)
        slay_summary = self.engine._personal_combat_step(game, "slay", FavorableRng())
        self.assertIn("击杀", slay_summary)
        self.assertGreater(game.player.karma, initial_karma)

    def test_mutated_technique_event_learns_without_replacing_main(self):
        created = self.engine.create_game("守住主修", "mutated_thunder", "dao", 227)
        game = self.engine.store.load(created["id"])
        game.player.technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        before = game.player.technique.id
        result, _ = self.engine._effect(
            {"type": "learn_technique", "technique_id": "TECH_THUNDER"}, game,
            {"id": "EVT_MUTATED_TECHNIQUE_001"}, random.Random(1),
        )
        self.assertEqual(result, "technique_learned")
        self.assertEqual(game.player.technique.id, before)
        self.assertIn("TECH_THUNDER", {art.id for art in game.player.known_techniques})

    def test_generated_master_and_disciple_relationships_are_recorded(self):
        class AcceptingRng:
            def choice(self, values): return values[0]
            def randint(self, low, high): return low
            def randrange(self, *args): return 7
            def random(self): return 0.0

        created = self.engine.create_game("师门", "supreme_metal", "dao", 228)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        master_result, _ = self.engine._effect(
            {"type": "gain_generated_master", "accept_chance": 0.55}, game,
            {"id": "EVT_MASTER_ENCOUNTER_001"}, AcceptingRng(),
        )
        disciple_result, _ = self.engine._effect(
            {"type": "gain_generated_disciple"}, game,
            {"id": "EVT_DISCIPLE_ENCOUNTER_001"}, AcceptingRng(),
        )
        self.assertEqual(master_result, "master_accepted")
        self.assertGreater(game.player.master["realm_index"], game.player.realm_index)
        self.assertEqual(disciple_result, "disciple_requested")
        self.assertEqual(len(game.player.disciples), 0)
        self.assertEqual(len(game.player.disciple_requests), 1)
        self.assertGreater(game.player.master["lifespan"], game.player.master["age"])
        self.assertGreater(game.player.disciple_requests[0]["lifespan"], game.player.disciple_requests[0]["age"])
        request_id = game.player.disciple_requests[0]["id"]
        self.engine.store.save(game)
        accepted = self.engine.respond_disciple_request(created["id"], request_id, True)
        self.assertEqual(len(accepted["player"]["disciples"]), 1)
        self.assertEqual(len(accepted["player"]["disciple_requests"]), 0)

    def test_beast_hunt_uses_strict_one_point_two_power_threshold(self):
        class FixedRng:
            def uniform(self, low, high): return low

        created = self.engine.create_game("猎妖线", "supreme_fire", "dao", 231)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        own = combat_power(game.player)
        target = {"target_name": "试炼妖兽", "target_realm_index": 2, "combat_type": "beast", "success_threshold": 1.2}
        result, _ = self.engine._combat(game, target | {"target_power": own / 1.19}, True, FixedRng())
        self.assertEqual(result, "defeat")
        game.player.hp = max_hp(game.player)
        own = combat_power(game.player)
        result, _ = self.engine._combat(game, target | {"target_power": own / 1.21}, True, FixedRng())
        self.assertEqual(result, "killed")

    def test_cultivator_encounter_power_uses_world_expectation_not_player_power(self):
        created = self.engine.create_game("世间均值", "supreme_fire", "dao", 234)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 3
        game.player.layer = 8
        event = self.engine.events_by_id["EVT_COMBAT_WEAK_PREY_001"]
        first = self.engine._instantiate_event(event, game, random.Random(18))["runtime"]
        add_item(game.player, "starfall_blade", 40)
        game.player.faction_combat_bonus = 50000
        second = self.engine._instantiate_event(event, game, random.Random(18))["runtime"]
        self.assertEqual(first["target_power"], second["target_power"])
        self.assertEqual(first["target_realm_index"], second["target_realm_index"])

    def test_cultivator_target_power_is_bounded_normal_around_stage_expectation(self):
        created = self.engine.create_game("众生分布", "supreme_water", "dao", 235)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 3
        settings = {
            "realm_offsets": [[0, 1.0]], "expectation_multiplier": 1.0,
            "power_sigma": 0.14, "power_bounds": [0.65, 1.4],
        }
        rng = random.Random(19)
        targets = [self.engine._generate_cultivator_target(game.player, "路人修士", settings, rng) for _ in range(500)]
        ratios = [target["primary_power"] / target["target_expected_power"] for target in targets]
        self.assertTrue(all(0.65 <= ratio <= 1.4 for ratio in ratios))
        self.assertAlmostEqual(sum(ratios) / len(ratios), 1.0, delta=0.04)

    def test_opponent_realm_visibility_stops_beyond_one_major_realm(self):
        created = self.engine.create_game("观气", "supreme_wood", "dao", 236)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        nearby = self.engine._generate_cultivator_target(
            game.player, "近境修士", {"realm_offsets": [[1, 1.0]]}, random.Random(1),
        )
        distant = self.engine._generate_cultivator_target(
            game.player, "高境修士", {"realm_offsets": [[2, 1.0]]}, random.Random(1),
        )
        self.assertTrue(nearby["target_realm_visible"])
        self.assertNotEqual(nearby["target_realm_display"], "无法看清")
        self.assertFalse(distant["target_realm_visible"])
        self.assertEqual(distant["target_realm_display"], "无法看清")

    def test_relationship_age_lifespan_requests_and_gifts(self):
        created = self.engine.create_game("授受有礼", "supreme_metal", "dao", 232)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        game.player.master = self.engine._relationship_snapshot("master-x", "玄师", 3, 2, "event", 260, 450)
        game.player.disciples = [self.engine._relationship_snapshot("disciple-x", "小徒", 1, 2, "event", 28, 108)]
        add_item(game.player, "blood_ginseng", 2)
        game.player.known_techniques = [copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])]
        self.engine._ensure_market(game, random.Random(3))
        game.rng_state = repr(random.Random(1).getstate())
        self.engine.store.save(game)

        item_result = self.engine.request_from_master(created["id"], "item")
        self.assertEqual(item_result["history"][0]["result"], "master_gave_item")
        after_item = self.engine.gift_disciple(created["id"], "disciple-x", "item", "blood_ginseng")
        blood_count = next(item["quantity"] for item in after_item["player"]["inventory"] if item["id"] == "blood_ginseng")
        self.assertEqual(blood_count, 1)
        after_teaching = self.engine.gift_disciple(created["id"], "disciple-x", "technique", "TECH_BASIC_QI")
        disciple = next(entry for entry in after_teaching["player"]["disciples"] if entry["id"] == "disciple-x")
        self.assertIn("TECH_BASIC_QI", disciple["techniques"])

        saved = self.engine.store.load(created["id"])
        saved.player.age += 1
        saved.market_age = saved.player.age
        saved.rng_state = repr(random.Random(2).getstate())
        self.engine.store.save(saved)
        refused = self.engine.request_from_master(created["id"], "item")
        self.assertEqual(refused["history"][0]["result"], "master_refused")

        saved = self.engine.store.load(created["id"])
        saved.player.disciples[0]["age"] = 107
        saved.player.disciples[0]["lifespan"] = 108
        self.engine._annual_relationship_update(saved)
        self.assertFalse(saved.player.disciples[0]["alive"])

    def test_sect_roster_exposes_only_valid_master_or_disciple_requests(self):
        created = self.engine.create_game("宗门师徒", "supreme_water", "dao", 229)
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "tianjian"
        game.player.realm_index = 3
        game.player.layer = 1
        faction = self.engine._public_faction(game)
        higher = [entry for entry in faction["roster"] if entry.get("can_request_master")]
        lower = [entry for entry in faction["roster"] if entry.get("can_accept_disciple")]
        self.assertTrue(higher)
        self.assertTrue(lower)
        true_ranks = {
            npc.id: (npc.realm_index, npc.layer)
            for npc in game.sects["tianjian"].npcs
        }
        self.assertTrue(all(true_ranks[entry["id"]] > (3, 1) for entry in higher))
        self.assertTrue(all(true_ranks[entry["id"]] < (3, 1) for entry in lower))

    def test_direct_sect_relationship_request_is_persisted(self):
        created = self.engine.create_game("当面请益", "supreme_water", "dao", 230)
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "tianjian"
        game.player.realm_index = 2
        game.player.layer = 1
        candidate = next(
            entry for entry in self.engine._public_faction(game)["roster"]
            if entry.get("can_request_master")
        )
        self.engine.store.save(game)
        result = self.engine.manage_faction_relationship(created["id"], candidate["id"], "master")
        saved = self.engine.store.load(created["id"])
        self.assertIn(f"master:{candidate['id']}", saved.player.relationship_attempts)
        self.assertEqual(result["history"][0]["event_id"], "SYS_FACTION_RELATIONSHIP")
        self.assertIn(result["history"][0]["result"], {"master_accepted", "rejected"})

    def test_human_npc_roots_are_visible_and_high_realms_filter_pseudo_roots(self):
        created = self.engine.create_game("观根", "supreme_water", "dao", 240)
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "tianjian"
        faction = self.engine._public_faction(game)
        self.assertTrue(all(entry.get("spirit_root_name") for entry in faction["roster"]))
        self.assertTrue(all(
            not npc.spirit_root.startswith(("law_", "otherworld", "acquired_"))
            for sect in game.sects.values() if sect.world == "human" for npc in sect.npcs
        ))
        rng = random.Random(11)
        core_roots = [self.engine._random_npc_root(3, rng) for _ in range(2000)]
        nascent_roots = [self.engine._random_npc_root(4, rng) for _ in range(5000)]
        self.assertLess(sum(root.startswith("pseudo_") for root in core_roots) / len(core_roots), 0.08)
        self.assertLess(sum(root.startswith("pseudo_") for root in nascent_roots) / len(nascent_roots), 0.01)

    def test_npc_root_efficiency_changes_cultivation_progress(self):
        from cultivation_life.models import SectNpc

        fast = SectNpc("fast", "快", "", 2, 1, 80, 230, spirit_root="supreme_metal")
        slow = SectNpc("slow", "慢", "", 2, 1, 80, 230, spirit_root="pseudo_all")
        self.engine._advance_npc_cultivation(fast, random.Random(9))
        self.engine._advance_npc_cultivation(slow, random.Random(9))
        self.assertGreater(fast.cultivation_progress, slow.cultivation_progress)

    def test_wind_thunder_wings_chain_has_mp_escape_and_awards_exact_power(self):
        created = self.engine.create_game("夺翅", "mutated_thunder", "dao", 241)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 3
        game.player.layer = 5
        add_item(game.player, "broken_god")
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_WIND_WINGS_001"], game, random.Random(1))
        self.engine.store.save(game)
        self.assertEqual(self.engine.choose(created["id"], "trace")["pending_event"]["id"], "EVT_WIND_WINGS_002")
        self.assertEqual(self.engine.choose(created["id"], "refine")["pending_event"]["id"], "EVT_WIND_WINGS_003")
        result = self.engine.choose(created["id"], "escape")
        wings = next(item for item in result["player"]["inventory"] if item["id"] == "wind_thunder_wings")
        self.assertEqual(wings["combat_bonus"], 1024)

    def test_kunwu_chain_is_middle_nascent_and_awards_both_keys(self):
        created = self.engine.create_game("入山", "supreme_metal", "dao", 242)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.layer = 5
        game.player.faction_combat_bonus = 100000
        add_item(game.player, "broken_god", 2)
        add_item(game.player, "phoenix_marrow", 10)
        add_item(game.player, "void_soul_crystal", 9)
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        event = self.engine.events_by_id["EVT_KUNWU_001"]
        self.assertTrue(self.engine._condition(event["conditions"], game))
        game.pending_event = self.engine._instantiate_event(event, game, random.Random(2))
        self.engine.store.save(game)
        for choice_id, next_id in [
            ("enter", "EVT_KUNWU_002"), ("break_line", "EVT_KUNWU_003"),
            ("guard_soul", "EVT_KUNWU_004"), ("subdue", "EVT_KUNWU_005"),
        ]:
            result = self.engine.choose(created["id"], choice_id)
            self.assertEqual(result["pending_event"]["id"], next_id)
        result = self.engine.choose(created["id"], "escape")
        inventory = {item["id"]: item for item in result["player"]["inventory"]}
        self.assertEqual(inventory["eight_spirit_ruler"]["combat_bonus"], 8000)
        self.assertIn("spirit_node_info", inventory)

    def test_spirit_crossing_is_one_time_three_checks_and_clears_human_ties(self):
        created = self.engine.create_game("飞升", "supreme_fire", "dao", 243)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 1
        game.player.faction_combat_bonus = 500000
        game.player.faction_id = "wanmo"
        game.player.master = self.engine._relationship_snapshot("m", "旧师", 5, 2, "event", 1500, 2800, spirit_root="supreme_fire")
        game.player.disciples = [self.engine._relationship_snapshot("d", "旧徒", 3, 2, "event", 220, 480, spirit_root="heavenly_fire_earth")]
        game.player.puppets = [{"id":"crossing-puppet", "name":"越界机关", "type":"mechanical", "combat_power":100, "alive":True}]
        add_item(game.player, "spirit_node_info")
        add_item(game.player, "broken_god", 5)
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        self.engine.store.save(game)
        result = self.engine.begin_spirit_crossing(created["id"])
        self.assertTrue(result["player"]["spirit_realm_attempted"])
        self.assertEqual(result["pending_event"]["id"], "EVT_SPIRIT_CROSSING_001")
        self.assertEqual(self.engine.choose(created["id"], "locate")["pending_event"]["id"], "EVT_SPIRIT_CROSSING_002")
        self.assertEqual(self.engine.choose(created["id"], "endure")["pending_event"]["id"], "EVT_SPIRIT_CROSSING_003")
        result = self.engine.choose(created["id"], "break_boundary")
        self.assertEqual(result["player"]["world"], "spirit")
        self.assertIsNone(result["player"]["master"])
        self.assertEqual(result["player"]["disciples"], [])
        self.assertEqual(result["demonic_system"]["puppets"], [])
        self.assertTrue(result["faction"]["departed_human_world"])
        with self.assertRaisesRegex(ValueError, "已经脱离人界"):
            self.engine.begin_spirit_crossing(created["id"])

    def test_spirit_crossing_without_node_information_is_certain_death(self):
        created = self.engine.create_game("迷航", "supreme_wood", "dao", 244)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 1
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        self.engine.store.save(game)
        self.engine.begin_spirit_crossing(created["id"])
        result = self.engine.choose(created["id"], "locate")
        self.assertFalse(result["player"]["alive"])
        self.assertIn("没有空间节点信息", result["player"]["death_reason"])

    def test_story_checks_combine_ratios_with_fixed_floor_values(self):
        wind = self.engine.events_by_id["EVT_WIND_WINGS_002"]
        wind_checks = wind["choices"][0]["effects"][0]["checks"]
        self.assertIn({"stat": "combat_power", "op": "gte", "value": 8500}, wind_checks)
        for event_id in ("EVT_KUNWU_002", "EVT_KUNWU_004", "EVT_KUNWU_005"):
            checks = self.engine.events_by_id[event_id]["choices"][0]["effects"][0]["checks"]
            self.assertIn({"stat": "combat_power", "op": "gte", "value": 73000}, checks)
        hp_checks = self.engine.events_by_id["EVT_KUNWU_001"]["choices"][0]["effects"][1]["checks"]
        mp_checks = self.engine.events_by_id["EVT_KUNWU_003"]["choices"][0]["effects"][0]["checks"]
        self.assertIn({"stat": "hp", "op": "gte", "value": 4000}, hp_checks)
        self.assertIn({"stat": "mp", "op": "gte", "value": 4000}, mp_checks)

    def test_fixed_story_combat_floors_use_the_rebased_world_standard(self):
        expected = {
            ("EVT_XUTIAN_004", "fight"): 6100,
            ("EVT_NORTH_NIGHT_PALACE_001", "suppress"): 49000,
            ("EVT_GUANGHAN_004", "break_array"): 720000,
            ("EVT_TWO_REALMS_003", "fight_six"): 6750000,
            ("EVT_MOTHER_BORER_007", "solo"): 68500000,
            ("EVT_MA_LIANG_008", "solo_finish"): 73500000,
        }
        for (event_id, choice_id), floor in expected.items():
            event = self.engine.events_by_id[event_id]
            choice = next(row for row in event["choices"] if row["id"] == choice_id)
            checks = next(effect for effect in choice["effects"] if effect["type"] == "attribute_check")["checks"]
            self.assertIn({"stat": "combat_power", "op": "gte", "value": floor}, checks)

    def test_story_trigger_probability_escalates_by_two_percent_each_year(self):
        class Roll:
            def __init__(self, value): self.value = value
            def random(self): return self.value

        created = self.engine.create_game("等风来", "supreme_metal", "dao", 245)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 3
        game.player.layer = 4
        self.assertFalse(self.engine._maybe_probability_story_event(game, Roll(0.205)))
        game.player.age += 1
        self.assertTrue(self.engine._maybe_probability_story_event(game, Roll(0.205)))
        self.assertEqual(game.pending_event["id"], "EVT_WIND_WINGS_001")
        self.assertIn("22%", game.pending_event["body"])

    def test_kunwu_can_be_abandoned_through_tower_and_unlocks_xiang_event(self):
        class Roll:
            def __init__(self, value): self.value = value
            def random(self): return self.value

        created = self.engine.create_game("知难而退", "supreme_wood", "dao", 246)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.layer = 5
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_KUNWU_001"], game, random.Random(1))
        self.engine.store.save(game)
        result = self.engine.choose(created["id"], "withdraw")
        self.assertIn("kunwu_incomplete", result["player"]["story_flags"])
        self.assertNotIn("kunwu_completed", result["player"]["story_flags"])

        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 3
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        self.assertFalse(self.engine._maybe_xiang_node_event(game, Roll(0.105)))
        game.player.age += 1
        self.assertTrue(self.engine._maybe_xiang_node_event(game, Roll(0.105)))
        self.assertEqual(game.pending_event["id"], "EVT_XIANG_NODE_001")

    def test_xiang_event_requires_world_npc_to_remain_in_human_world(self):
        created = self.engine.create_game("迟来", "supreme_fire", "dao", 247)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 3
        game.player.story_flags.append("kunwu_incomplete")
        game.world_npcs["xiang_zhili"].world = "spirit"
        self.assertFalse(self.engine._condition(self.engine.events_by_id["EVT_XIANG_NODE_001"]["conditions"], game))

    def test_world_npc_departure_is_only_perceived_as_death_across_worlds(self):
        class CertainRng:
            def uniform(self, low, high): return 1.0
            def random(self): return 0.0
            def randint(self, low, high): return low

        created = self.engine.create_game("隔界观人", "supreme_metal", "dao", 248)
        game = self.engine.store.load(created["id"])
        npc = game.world_npcs["xiang_zhili"]
        npc.cultivation_progress = 999
        outcome = self.engine._advance_npc_cultivation(npc, CertainRng())
        self.assertEqual(outcome["type"], "departure")
        self.assertTrue(npc.alive)
        human_view = next(entry for entry in self.engine._public_world_npcs(game) if entry["id"] == npc.id)
        self.assertFalse(human_view["perceived_alive"])
        self.assertIsNone(human_view["world"])
        game.player.world = "spirit"
        spirit_view = next(entry for entry in self.engine._public_world_npcs(game) if entry["id"] == npc.id)
        self.assertTrue(spirit_view["perceived_alive"])

    def test_high_realms_use_multi_year_units_and_create_era_summary(self):
        created = self.engine.create_game("百年一瞬", "supreme_earth", "dao", 249)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 8
        game.player.layer = 1
        game.player.world = "spirit"
        game.player.lifespan = None
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        start_age = game.player.age
        xiang_age = game.world_npcs["xiang_zhili"].age
        self.engine.store.save(game)
        # 隔离主线剧情的逐年概率门，只验证百年单位本身的结算语义。
        with patch.object(self.engine, "_maybe_probability_story_event", return_value=False):
            result = self.engine.advance(created["id"], "rest")
        self.assertEqual(result["player"]["age"], start_age + 100)
        self.assertEqual(result["player"]["time_unit_years"], 100)
        saved = self.engine.store.load(created["id"])
        self.assertEqual(saved.world_npcs["xiang_zhili"].age, xiang_age + 100)
        self.assertTrue(any(record.event_id == "SYS_ERA_SUMMARY" for record in saved.history))

    def test_faction_events_are_world_scoped(self):
        faction_events = [event for event in self.engine.events if "faction" in event.get("tags", []) or "faction_join" in event.get("tags", [])]
        self.assertTrue(faction_events)
        self.assertTrue(all(len([tag for tag in event.get("tags", []) if tag.startswith("world:")]) == 1 for event in faction_events))
        self.assertTrue(any("world:spirit" in event.get("tags", []) and "faction_join" in event.get("tags", []) for event in faction_events))
        created = self.engine.create_game("灵界散人", "supreme_metal", "dao", 250)
        game = self.engine.store.load(created["id"])
        game.player.world = "spirit"
        game.player.realm_index = 5
        for seed in range(30):
            event = self.engine._select_event(game, "travel", random.Random(seed))
            if event:
                self.assertNotIn("world:human", event.get("tags", []))

    def test_spirit_races_and_human_monster_alliance_affect_kill_karma(self):
        created = self.engine.create_game("盟约", "supreme_fire", "dao", 251)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 1
        game.player.world = "spirit"
        add_item(game.player, "broken_god", 5)
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        own = combat_power(game.player)
        generated = self.engine._generate_cultivator_target(game.player, "巡界修士", {
            "realm_offsets": [[0, 1.0]], "expectation_multiplier": 1.0,
            "power_sigma": 0.1, "power_bounds": [0.8, 1.2],
        }, random.Random(3))
        self.assertTrue(generated["race_description"])
        result, summary = self.engine._combat(game, {
            "target_name": "妖族修士", "target_power": own / 4,
            "target_realm_index": 5, "combat_type": "cultivator", "race": "monster", "kill_karma": True,
        }, True, random.Random(4))
        self.assertEqual(result, "killed")
        self.assertGreaterEqual(game.player.karma, 200)
        self.assertIn("人妖两族盟约", summary)
        self.assertEqual(len(self.engine._public_race_system(game)["races"]), 20)

    def test_quick_start_presets_configure_realm_stats_techniques_and_inventory(self):
        for preset_id, realm_index in (("core", 3), ("nascent", 4), ("spirit", 5), ("void", 6), ("integration", 7), ("mahayana", 8)):
            result = self.engine.create_game("速启", "none", "demonic", 300 + realm_index, preset_id=preset_id)
            player = result["player"]
            self.assertEqual(player["realm_index"], realm_index)
            self.assertIsNotNone(player["technique_slots"]["main"])
            self.assertIsNotNone(player["technique_slots"]["support"])
            self.assertGreaterEqual(len(player["technique_slots"]["combat"]), 1)
            self.assertGreater(len(player["inventory"]), 1)
            self.assertEqual(player["hp"], player["max_hp"])
            self.assertEqual(player["mp"], player["max_mp"])
            power_ratio = player["combat_power"] / player["expected_combat_power"]
            self.assertGreaterEqual(power_ratio, 0.9, preset_id)
            self.assertLessEqual(power_ratio, 1.1, preset_id)
            rewarded_story_flags = {
                "wind_thunder_wings": "wind_wings_completed",
                "virtual_heaven_cauldron": "xutian_completed",
                "eight_spirit_ruler": "kunwu_completed",
                "north_pole_origin_mountain": "north_night_completed",
                "yuan_magnetic_divine_mountain": "star_palace_completed",
            }
            inventory_ids = {item["id"] for item in player["inventory"]}
            self.assertIn("spirit_sword", inventory_ids, preset_id)
            for item_id, story_flag in rewarded_story_flags.items():
                if item_id in inventory_ids and realm_index <= 5:
                    self.assertIn(story_flag, player["story_flags"], preset_id)
            if realm_index >= 6:
                self.assertEqual(player["world"], "spirit")
                self.assertTrue({"metal", "wood", "water", "fire", "earth"} <= set(player["additional_roots"]))
                self.assertIsNotNone(result["tribulation"]["next_age"])

    def test_mortal_start_begins_with_qingfeng_spirit_sword_equipped_in_inventory(self):
        result = self.engine.create_game("执剑凡人", "supreme_metal", "dao", 311)
        sword = next(row for row in result["player"]["inventory"] if row["id"] == "spirit_sword")
        self.assertEqual(sword["quantity"], 1)
        self.assertIn("equipment", sword["tags"])
        self.assertEqual(sword["combat_bonus"], 22)

    def test_every_enabled_quick_start_includes_qingfeng_spirit_sword(self):
        for index, preset in enumerate(WORLD_SYSTEMS["quick_start_presets"]):
            if not preset.get("enabled"):
                continue
            result = self.engine.create_game(
                f"速启持剑{index}", "none", "dao", 400 + index, preset_id=preset["id"],
            )
            self.assertIn(
                "spirit_sword", {row["id"] for row in result["player"]["inventory"]}, preset["id"],
            )

    def test_special_core_quick_starts_use_balanced_dlc_loadouts(self):
        for index, preset_id in enumerate(("monster_core", "ghost_core", "confucian_core")):
            result = self.engine.create_game(
                f"异道速启{index}", "none", "dao", 460 + index, preset_id=preset_id,
            )
            player = result["player"]
            self.assertEqual(player["realm_index"], 3)
            self.assertGreaterEqual(player["combat_power"] / player["expected_combat_power"], 0.9)
            self.assertLessEqual(player["combat_power"] / player["expected_combat_power"], 1.1)
        monster = self.engine.create_game("妖丹", "none", "dao", 470, preset_id="monster_core")["player"]
        self.assertIsNotNone(monster["technique_slots"]["body"])
        confucian = self.engine.create_game("鸿儒", "none", "dao", 471, preset_id="confucian_core")["player"]
        self.assertIn("confucian_jade_ruler", {row["id"] for row in confucian["inventory"]})

    def test_every_cultivation_path_has_a_void_refinement_quick_start(self):
        preset_ids = {
            "dao": "void", "demonic": "demonic_void", "monster": "monster_void",
            "ghost": "ghost_void", "confucian": "confucian_void", "buddhist": "buddhist_void",
        }
        for index, (path, preset_id) in enumerate(preset_ids.items()):
            with self.subTest(path=path):
                player = self.engine.create_game(
                    f"炼虚{path}", "none", "dao", 520 + index, preset_id=preset_id,
                )["player"]
                self.assertEqual(player["realm_index"], 6)
                self.assertEqual(player["path"], path)
                self.assertTrue({"metal", "wood", "water", "fire", "earth"} <= set(player["additional_roots"]))
                self.assertIsNotNone(player["technique_slots"]["main"])
                self.assertIsNotNone(player["technique_slots"]["support"])
                self.assertGreaterEqual(player["combat_power"] / player["expected_combat_power"], 0.9)
                self.assertLessEqual(player["combat_power"] / player["expected_combat_power"], 1.1)

    def test_spirit_world_exposes_three_joinable_sects_with_raced_rosters(self):
        created = self.engine.create_game("灵界门人", "supreme_metal", "dao", 310)
        game = self.engine.store.load(created["id"])
        game.player.world = "spirit"
        game.player.realm_index = 5
        public = self.engine._public_faction(game)
        self.assertEqual({entry["id"] for entry in public["available"]}, {"taixuan", "wanlingshan", "xinghe"})
        outcome, _ = self.engine._effect(
            {"type": "join_faction", "faction_id": "taixuan"}, game, {"id": "TEST"}, random.Random(1),
        )
        self.assertEqual(outcome, "faction_joined")
        faction = self.engine._public_faction(game)
        self.assertTrue(faction["member"])
        self.assertTrue(all(entry.get("race_name") for entry in faction["roster"]))
        self.assertTrue(any(entry["lifespan"] is None for entry in faction["roster"] if not entry["is_player"]))
        elder_age = game.sects["taixuan"].npcs[0].age
        self.engine._annual_sect_update(game, random.Random(2))
        self.assertEqual(game.sects["taixuan"].npcs[0].age, elder_age + 1)
        self.assertEqual(game.player.faction_contribution, 1)

    def test_five_year_unit_escalation_checks_each_year_then_reaches_thirty_percent(self):
        class Roll:
            def __init__(self, value): self.value = value
            def random(self): return self.value

        created = self.engine.create_game("五年一瞬", "supreme_metal", "dao", 311)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.layer = 4
        start_age = game.player.age
        for offset in range(5):
            game.player.age = start_age + offset
            self.assertFalse(self.engine._maybe_probability_story_event(game, Roll(0.99)))
        game.player.age = start_age + 5
        self.assertTrue(self.engine._maybe_probability_story_event(game, Roll(0.295)))
        self.assertIn("30%", game.pending_event["body"])

    def test_demonic_cultivator_first_crosses_to_demon_world_shell(self):
        created = self.engine.create_game("入魔界", "supreme_fire", "demonic", 252)
        game = self.engine.store.load(created["id"])
        result, _ = self.engine._effect({"type": "enter_spirit_realm"}, game, {"id": "TEST"}, random.Random(1))
        self.assertEqual(result, "entered_spirit_realm")
        self.assertEqual(game.player.world, "demon")
        self.assertFalse(self.engine._public_race_system(game)["available"])

    def test_each_path_can_start_in_human_or_its_native_world(self):
        native_worlds = {
            "dao": "spirit", "buddhist": "spirit", "confucian": "spirit",
            "demonic": "demon", "monster": "phantom_underworld", "ghost": "hell",
        }
        for path, native_world in native_worlds.items():
            with self.subTest(path=path, world=native_world):
                created = self.engine.create_game(
                    f"{path}本界", "supreme_metal", path, 8000 + len(path), start_world=native_world,
                )
                self.assertEqual(created["player"]["world"], native_world)
                self.assertEqual(created["map"]["world"], native_world)
                human = self.engine.create_game(f"{path}人界", "supreme_metal", path, 9000 + len(path))
                self.assertEqual(human["player"]["world"], "human")

    def test_start_world_must_belong_to_selected_path(self):
        with self.assertRaisesRegex(ValueError, "无法从所选界面开局"):
            self.engine.create_game("误入灵界", "supreme_fire", "demonic", 253, start_world="spirit")

    def test_world_news_projection_hides_other_world_until_debug_is_enabled(self):
        created = self.engine.create_game("界闻", "supreme_water", "dao", 401)
        game = self.engine.store.load(created["id"])
        game.history.extend([
            HistoryRecord("HUMAN", 1, 16, "人界大事", None, "ok", "人界可见", {}, ["world_news", "world:human"]),
            HistoryRecord("SPIRIT", 1, 16, "灵界大事", None, "ok", "灵界隐藏", {}, ["world_news", "world:spirit"]),
            HistoryRecord("GLOBAL", 1, 16, "全局大事", None, "ok", "全局可见", {}, ["world_news", "world:global"]),
        ])
        self.engine.store.save(game)
        normal_titles = {record["title"] for record in self.engine.present(game)["history"]}
        self.assertIn("人界大事", normal_titles)
        self.assertIn("全局大事", normal_titles)
        self.assertNotIn("灵界大事", normal_titles)
        debug = self.engine.set_world_news_debug(created["id"], True)
        self.assertIn("灵界大事", {record["title"] for record in debug["history"]})

    def test_markets_are_world_isolated_but_spirit_stones_cross_worlds(self):
        created = self.engine.create_game("跨界商旅", "supreme_fire", "dao", 402)
        game = self.engine.store.load(created["id"])
        add_item(game.player, "spirit_stone", 777)
        game.player.realm_index = 5
        game.player.world = "spirit"
        game.market_realm_index = None
        game.market_world = None
        game.market_offers = []
        self.engine._ensure_market(game, random.Random(4))
        self.assertEqual(game.market_world, "spirit")
        self.assertTrue(game.market_offers)
        self.assertTrue(all(offer["world"] == "spirit" and offer["tier"] in {5, 6} for offer in game.market_offers))
        self.assertEqual(self.engine._public_market(game)["spirit_stones"], 777)

    def test_spirit_to_void_requires_five_elements_and_zique_can_fill_them(self):
        created = self.engine.create_game("五行合道", "supreme_fire", "dao", 403)
        game = self.engine.store.load(created["id"])
        game.player.world = "spirit"
        game.player.realm_index = 5
        game.player.layer = 9
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_major_breakthrough = True
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "五行灵根"):
            self.engine.breakthrough(created["id"])
        for affinity in ("metal", "wood", "water", "earth"):
            game = self.engine.store.load(created["id"])
            add_item(game.player, f"zique_{affinity}")
            self.engine.store.save(game)
            self.engine.use_item(created["id"], f"zique_{affinity}")
        game = self.engine.store.load(created["id"])
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        game.rng_state = encode_rng(random.Random(139))
        self.engine.store.save(game)
        result = self.engine.breakthrough(created["id"])
        self.assertEqual(result["pending_event"]["id"], "EVT_BREAKTHROUGH_TRADITIONAL_001")
        for choice_id in ("endure", "face_karma", "face_demon"):
            result = self.engine.choose(created["id"], choice_id)
        self.assertEqual(result["player"]["realm_index"], 6)
        self.assertEqual(set(result["player"]["additional_roots"]), {"metal", "wood", "water", "earth"})

    def test_major_breakthrough_base_probabilities_follow_root_tiers(self):
        created = self.engine.create_game("概率谱", "pseudo_all", "dao", 405)
        game = self.engine.store.load(created["id"])
        samples = {
            1: {"pseudo_all": 0.10, "acquired_metal": 0.10, "otherworld": 0.80},
            2: {"acquired_metal": 0.06, "pseudo_all": 0.08,
                "heavenly_metal_wood": 0.35, "supreme_metal": 0.42,
                "mutated_thunder": 0.50, "law_time": 0.58, "otherworld": 0.66},
            3: {"pseudo_all": 0.01, "otherworld": 0.05},
            4: {"acquired_metal": 0.01, "pseudo_all": 0.02, "heavenly_metal_wood": 0.03,
                "supreme_metal": 0.04, "mutated_thunder": 0.04, "law_time": 0.05,
                "otherworld": 0.06},
        }
        for realm_index, roots in samples.items():
            game.player.realm_index = realm_index
            for root_id, expected in roots.items():
                game.player.spirit_root = root_id
                game.player.heart_demon = 0
                self.assertAlmostEqual(self.engine._breakthrough_chance(game.player, True)["base"], expected)

    def test_spirit_root_quality_controls_mana_capacity_and_combat_consumption(self):
        poor = self.engine.store.load(self.engine.create_game("杂灵根", "pseudo_all", "dao", 408)["id"]).player
        rare = self.engine.store.load(self.engine.create_game("异灵根", "otherworld", "dao", 409)["id"]).player
        poor.realm_index = rare.realm_index = 3
        poor.layer = rare.layer = 1
        self.assertLess(spirit_root_mana_multiplier(poor), 0.7)
        self.assertGreater(spirit_root_mana_multiplier(rare), 1.6)
        self.assertGreater(max_mp(rare), max_mp(poor) * 2)

        same_stage_cost = combat_root_mana_cost_multiplier(poor, 3, 1)
        middle_stage_cost = combat_root_mana_cost_multiplier(poor, 3, 4)
        late_stage_cost = combat_root_mana_cost_multiplier(poor, 3, 7)
        adjacent_realm_cost = combat_root_mana_cost_multiplier(poor, 4, 1)
        two_realm_gap_cost = combat_root_mana_cost_multiplier(poor, 5, 1)
        self.assertGreater(same_stage_cost, middle_stage_cost)
        self.assertGreater(middle_stage_cost, late_stage_cost)
        self.assertGreater(late_stage_cost, adjacent_realm_cost)
        self.assertGreater(adjacent_realm_cost, two_realm_gap_cost)
        self.assertEqual(middle_stage_cost, 1.15)
        self.assertEqual(late_stage_cost, 1.05)
        self.assertEqual(adjacent_realm_cost, 1.02)
        self.assertEqual(two_realm_gap_cost, 1.0)

        rare_same = combat_root_mana_cost_multiplier(rare, 3, 1)
        rare_middle = combat_root_mana_cost_multiplier(rare, 3, 4)
        self.assertLess(rare_same, rare_middle)
        self.assertLess(rare_middle, 1.0)
        self.assertEqual(rare_middle, 0.88)
        self.assertEqual(combat_root_mana_cost_multiplier(rare, 3, 7), 0.96)
        self.assertEqual(combat_root_mana_cost_multiplier(rare, 4, 1), 0.98)
        self.assertEqual(combat_root_mana_cost_multiplier(rare, 5, 1), 1.0)

        unit = BattleUnit("player", "试法", "player", 1000, 3)
        target = {
            "target_name": "试法傀儡", "target_power": 1100,
            "target_realm_index": 3, "target_layer": 1, "max_rounds": 5,
        }
        poor_result = PlayerCombatSystem.resolve(
            poor, [unit], target, False, random.Random(77),
            current_hp_ratio=1, current_mp_ratio=1,
            mana_cost_multiplier=same_stage_cost,
        )
        rare_result = PlayerCombatSystem.resolve(
            rare, [unit], target, False, random.Random(77),
            current_hp_ratio=1, current_mp_ratio=1,
            mana_cost_multiplier=rare_same,
        )
        self.assertGreater(poor_result.mp_loss_ratio, rare_result.mp_loss_ratio)
        self.assertTrue(any("灵根驭气艰涩" in event for event in poor_result.key_events))

    def test_breakthrough_pill_is_data_driven_and_activates_next_matching_attempt(self):
        created = self.engine.create_game("丹助筑基", "supreme_metal", "dao", 406)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 1
        game.player.layer = 13
        add_item(game.player, "foundation_pill")
        self.engine.store.save(game)
        result = self.engine.use_item(created["id"], "foundation_pill")
        self.assertEqual(result["breakthrough"]["chance"]["aid_bonus"], 0.20)
        self.assertIn("foundation_pill", result["player"]["active_breakthrough_aids"])
        self.assertNotIn("foundation_pill", {item["id"] for item in result["player"]["inventory"]})

    def test_heart_demon_is_hidden_normally_and_visible_in_debug(self):
        created = self.engine.create_game("道心暗流", "supreme_wood", "dao", 407)
        game = self.engine.store.load(created["id"])
        game.player.heart_demon = 12
        self.engine.store.save(game)
        self.assertNotIn("heart_demon", self.engine.get_game(created["id"])["player"])
        shown = self.engine.set_world_news_debug(created["id"], True)
        self.assertEqual(shown["player"]["heart_demon"], 12)

    def test_only_nascent_formation_trial_is_lethal_before_void(self):
        core = self.engine.create_game("结婴败", "supreme_fire", "dao", 408)
        game = self.engine.store.load(core["id"])
        game.player.realm_index, game.player.layer, game.player.opportunity = 3, 9, 0
        game.player.hp = game.player.mp = 1
        self.engine._start_breakthrough_trial(game, "traditional", 3, 4, "结丹后期", True, random.Random(1))
        self.engine.store.save(game)
        lethal = self.engine.choose(core["id"], "endure")
        self.assertFalse(lethal["player"]["alive"])

        spirit = self.engine.create_game("化神败", "supreme_fire", "dao", 409)
        game = self.engine.store.load(spirit["id"])
        game.player.realm_index, game.player.layer, game.player.opportunity = 4, 9, 0
        game.player.hp = game.player.mp = 1
        self.engine._start_breakthrough_trial(game, "traditional", 4, 5, "元婴后期", True, random.Random(1))
        self.engine.store.save(game)
        survived = self.engine.choose(spirit["id"], "endure")
        self.assertTrue(survived["player"]["alive"])
        debug = self.engine.set_world_news_debug(spirit["id"], True)
        self.assertEqual(debug["player"]["heart_demon"], 8)

    def test_periodic_thunder_allows_only_tagged_recovery_items_between_strikes(self):
        created = self.engine.create_game("劫中服丹", "supreme_water", "dao", 410)
        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 6, 1
        game.player.age = 5000
        game.player.next_tribulation_age = 5000
        game.player.tribulation_power = 1000
        game.player.hp = max_hp(game.player) * 0.5
        game.player.mp = max_mp(game.player) * 0.5
        add_item(game.player, "tribulation_vitality_pill")
        self.engine._check_tribulation(game, random.Random(1))
        before = game.player.hp
        self.engine.store.save(game)
        result = self.engine.use_item(created["id"], "tribulation_vitality_pill")
        self.assertGreater(result["player"]["hp"], before)
        self.assertEqual(result["pending_event"]["id"], "EVT_PERIODIC_THUNDER_001")


if __name__ == "__main__":
    unittest.main()
