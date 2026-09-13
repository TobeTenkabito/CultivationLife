import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cultivation_life.engine import GameEngine
from cultivation_life.event_repository import EventRepository
from cultivation_life.rules import (
    TECHNIQUE_CATALOG, add_item, assign_technique, can_player_practice_technique,
    combat_power, opportunity_required,
)


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class RelationshipStoryUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def test_cultivator_team_is_previewed_before_combat(self):
        created = self.engine.create_game("谨慎观阵", "supreme_metal", "dao", 601, preset_id="core")
        game = self.engine.store.load(created["id"])
        hp_before = game.player.hp
        target = {
            "target_name": "结伴修士", "target_power": 1600.0, "primary_power": 1000.0,
            "target_realm_index": 3, "target_layer": 2, "target_realm_display": "结丹初期",
            "combat_type": "cultivator", "race": "human", "race_name": "人族",
            "race_description": "测试", "members": [
                {"name": "甲", "power": 1000.0, "realm_index": 3, "layer": 2, "race": "human"},
                {"name": "乙", "power": 1200.0, "realm_index": 3, "layer": 2, "race": "human"},
            ],
        }
        with patch.object(self.engine, "_known_npc_encounter_target", return_value=target):
            summary = self.engine._personal_combat_step(game, "spar", random.Random(1))
        self.assertEqual(game.pending_event["id"], "EVT_TEAM_SPAR_PREVIEW_001")
        self.assertIn("2名修士", game.pending_event["body"])
        self.assertIn("合计战斗力", game.pending_event["body"])
        self.assertEqual(game.player.hp, hp_before)
        self.assertIn("尚未交手", summary)

    def test_spar_preview_resolves_nonlethally(self):
        created = self.engine.create_game("点到为止", "supreme_metal", "dao", 602, preset_id="core")
        game = self.engine.store.load(created["id"])
        own = combat_power(game.player)
        target = {
            "target_name": "切磋小队", "target_power": own / 3, "primary_power": own / 4,
            "target_realm_index": 2, "target_layer": 1, "target_realm_display": "筑基初期",
            "combat_type": "cultivator", "race": "human", "members": [
                {"name": "甲", "power": own / 4, "realm_index": 2, "layer": 1, "race": "human"},
                {"name": "乙", "power": own / 5, "realm_index": 2, "layer": 1, "race": "human"},
            ], "action": "spar", "kill_karma": False,
        }
        pending = self.engine._instantiate_event(self.engine.events_by_id["EVT_TEAM_SPAR_PREVIEW_001"], game, random.Random(1))
        pending["runtime"] = target
        result, _ = self.engine._effect({"type": "runtime_combat", "lethal": False}, game, pending, random.Random(2))
        self.assertEqual(result, "victory")
        self.assertEqual(game.player.karma, created["player"]["karma"])

        game.player.hp = 1
        result, text = self.engine._combat(game, {
            "target_name": "不可战胜的对手", "target_power": own * 100,
            "target_realm_index": 4, "combat_type": "cultivator", "race": "human",
        }, False, random.Random(3))
        self.assertEqual(result, "defeat")
        self.assertTrue(game.player.alive)
        self.assertEqual(game.player.hp, 1)
        self.assertIn("无人伤及性命", text)

    def test_team_generation_is_probabilistic_and_beasts_are_never_teamed(self):
        created = self.engine.create_game("众寡有别", "supreme_metal", "dao", 603, preset_id="core")
        player = self.engine.store.load(created["id"]).player
        sizes = {
            len(self.engine._generate_cultivator_target(player, "修士", self.engine.events_by_id["EVT_COMBAT_ROBBER_001"]["combat"], random.Random(seed))["members"])
            for seed in range(40)
        }
        self.assertIn(1, sizes)
        self.assertTrue(any(size > 1 for size in sizes))
        game = self.engine.store.load(created["id"])
        self.engine._personal_combat_step(game, "hunt_beast", random.Random(1))
        self.assertIsNone(game.pending_event)

    def test_high_realm_combat_action_rolls_only_one_encounter_per_click(self):
        created = self.engine.create_game("五年一战", "none", "dao", 612, preset_id="nascent")
        with patch.object(self.engine, "_personal_combat_step", return_value="只结算一次") as combat_step:
            self.engine.advance(created["id"], "spar", 1)
        combat_step.assert_called_once()

    def test_spirit_ranking_has_twenty_and_includes_player_in_calculation(self):
        result = self.engine.create_game("后来者", "none", "dao", 604, preset_id="mahayana")
        ranking = result["spirit_ranking"]
        self.assertTrue(ranking["available"])
        self.assertEqual(len(ranking["entries"]), 20)
        self.assertGreaterEqual(sum(entry["realm_index"] == 8 for entry in ranking["entries"]), 17)
        self.assertIsInstance(ranking["player_rank"], int)
        self.assertEqual(sum(entry["is_player"] for entry in ranking["entries"]), int(ranking["on_board"]))

    def test_high_fame_guarantees_no_ignored_encounter_ambush(self):
        created = self.engine.create_game("声震四方", "supreme_fire", "dao", 605, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.fame = 50
        result, text = self.engine._effect({"type": "cultivator_reaction", "chance": 1.0}, game, {"id": "TEST"}, random.Random(1))
        self.assertEqual(result, "deterred")
        self.assertIsNone(game.pending_event)
        self.assertIn("不敢", text)

    def test_every_spirit_stone_trade_choice_has_a_return(self):
        for event in self.engine.events:
            if "trade" not in event.get("tags", []):
                continue
            for choice in event["choices"]:
                effects = choice.get("effects", [])
                spends = any(effect.get("type") == "remove_item" and effect.get("item_id") == "spirit_stone" for effect in effects)
                if spends:
                    gains = any(effect.get("type") in {"add_item", "add_opportunity", "learn_technique"} for effect in effects)
                    self.assertTrue(gains, f"{event['id']}/{choice['id']} 花费灵石却没有回报")

    def test_sex_techniques_accept_any_root_and_entwine_grants_opportunity(self):
        created = self.engine.create_game("红尘同参", "mutated_thunder", "dao", 606, preset_id="core")
        game = self.engine.store.load(created["id"])
        sex_art = copy.deepcopy(TECHNIQUE_CATALOG["TECH_HEHUAN_SECRET"])
        self.assertTrue(can_player_practice_technique(game.player, sex_art.element))
        assign_technique(game.player, sex_art, "main")
        game.player.dao_companion = self.engine._generated_relationship(game.player, "companion", random.Random(4))
        game.player.dao_companion["main_technique_id"] = sex_art.id
        game.player.heart_demon = 10
        before = game.player.opportunity
        self.engine.store.save(game)
        result = self.engine.manage_dao_companion(created["id"], "entwine")
        self.assertLess(self.engine.store.load(created["id"]).player.heart_demon, 10)
        self.assertGreater(result["player"]["opportunity"], before)

    def test_same_main_art_and_realm_adds_five_percent_and_jointly_advances(self):
        created = self.engine.create_game("同心破境", "supreme_metal", "dao", 607, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.layer = 3
        companion = self.engine._generated_relationship(game.player, "companion", random.Random(2))
        companion["main_technique_id"] = game.player.technique.id
        game.player.dao_companion = companion
        chance = self.engine._breakthrough_chance(game.player, major=False)
        self.assertAlmostEqual(chance["companion_bonus"], 0.05)
        game.player.joint_companion_breakthrough = {"id": companion["id"], "source_realm": 3, "source_layer": 3, "major": False}
        self.engine._complete_minor_breakthrough(game, random.Random(3), "结丹初期·3层")
        self.assertEqual(game.player.dao_companion["layer"], 4)
        self.assertTrue(any(record.event_id == "SYS_COMPANION_JOINT_BREAKTHROUGH" for record in game.history))

    def test_three_mountains_craft_atomic_reward_and_passive_bonuses(self):
        created = self.engine.create_game("三衡合一", "none", "dao", 608, preset_id="void")
        game = self.engine.store.load(created["id"])
        for item_id in ("north_pole_origin_mountain", "yuan_magnetic_divine_mountain", "taiyi_green_mountain"):
            add_item(game.player, item_id)
        self.assertTrue(self.engine._maybe_artifact_synthesis(game, random.Random(1)))
        self.engine.store.save(game)
        resolved = self.engine.choose(created["id"], "craft")
        inventory = {item["id"]: item["quantity"] for item in resolved["player"]["inventory"]}
        self.assertIn("yuanhe_five_poles_mountain", inventory)
        self.assertFalse({"north_pole_origin_mountain", "yuan_magnetic_divine_mountain", "taiyi_green_mountain"} & set(inventory))
        loaded = self.engine.store.load(created["id"])
        self.assertAlmostEqual(self.engine._breakthrough_chance(loaded.player, False)["artifact_bonus"], 0.05)
        self.assertAlmostEqual(self.engine._tribulation_damage_reduction(loaded.player), 0.25)

    def test_required_new_story_rewards_are_registered(self):
        required_events = {
            "EVT_XUTIAN_001", "EVT_NORTH_NIGHT_PALACE_001", "EVT_STARPALACE_REQUEST_001",
            "EVT_GUANGHAN_001", "EVT_FIVE_POLES_CRAFT_001",
        }
        self.assertTrue(required_events <= set(self.engine.events_by_id))
        self.assertEqual(TECHNIQUE_CATALOG["TECH_YUAN_MAGNETIC_LIGHT"].element, "five_elements")
        result = self.engine.create_game("缺木少火", "supreme_metal", "dao", 609, preset_id="core")
        player = self.engine.store.load(result["id"]).player
        self.assertFalse(can_player_practice_technique(player, "five_elements"))
        player.additional_roots = ["wood", "water", "fire", "earth"]
        self.assertTrue(can_player_practice_technique(player, "five_elements"))

    def test_xutian_chain_reaches_both_rewards(self):
        created = self.engine.create_game("天仓取印", "supreme_water", "dao", 610, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.faction_combat_bonus = 10000
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_XUTIAN_001"], game, random.Random(1))
        self.engine.store.save(game)
        for choice in ("map", "ice", "banner", "fight"):
            result = self.engine.choose(created["id"], choice)
        inventory = {item["id"] for item in result["player"]["inventory"]}
        known = {art["id"] for art in result["player"]["known_techniques"]}
        self.assertIn("virtual_heaven_cauldron", inventory)
        self.assertIn("TECH_DRY_BLUE_ICE_FLAME", known)

    def test_guanghan_chain_reaches_spirit_art_and_taiyi_mountain(self):
        created = self.engine.create_game("回光归客", "none", "dao", 611, preset_id="void")
        game = self.engine.store.load(created["id"])
        game.player.faction_combat_bonus = 500000
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_GUANGHAN_001"], game, random.Random(1))
        self.engine.store.save(game)
        for choice in ("enter", "cooperate", "study", "negotiate", "return"):
            result = self.engine.choose(created["id"], choice)
        inventory = {item["id"] for item in result["player"]["inventory"]}
        known = {art["id"] for art in result["player"]["known_techniques"]}
        self.assertIn("taiyi_green_mountain", inventory)
        self.assertIn("TECH_SPIRIT_REFINING_ART", known)

    def test_spirit_epic_chains_have_requested_lengths_and_four_choices_each(self):
        expected = {
            "two_realms_war": 5,
            "bitter_spirit_island": 5,
            "mother_borer": 7,
            "ma_liang": 9,
        }
        for tag, count in expected.items():
            events = [event for event in self.engine.events if tag in event.get("tags", [])]
            self.assertEqual(len(events), count, tag)
            self.assertTrue(all(len(event["choices"]) >= 4 for event in events), tag)
            self.assertTrue(all("world:spirit" in event.get("tags", []) for event in events), tag)
        self.assertIn("天墟岛", self.engine.events_by_id["EVT_BITTER_ISLAND_001"]["title"])

    def test_integration_epic_chains_reach_baohua_and_cleansing_rewards(self):
        created = self.engine.create_game("两界归客", "none", "dao", 613, preset_id="integration")
        game = self.engine.store.load(created["id"])
        game.player.faction_combat_bonus = 20_000_000
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_TWO_REALMS_001"], game, random.Random(1))
        self.engine.store.save(game)
        for choice in ("rescue", "repair", "mislead", "neutral", "peace_clause"):
            result = self.engine.choose(created["id"], choice)
        self.assertIn("baohua_cooperation_completed", result["player"]["story_flags"])
        self.assertIn("baohua_covenant", {item["id"] for item in result["player"]["inventory"]})

        game = self.engine.store.load(created["id"])
        game.player.hp = 10_000_000
        game.player.mp = 10_000_000
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_BITTER_ISLAND_001"], game, random.Random(2))
        self.engine.store.save(game)
        for choice in ("covenant", "silent", "show_covenant", "lotus", "lotus_escape"):
            result = self.engine.choose(created["id"], choice)
        inventory = {item["id"] for item in result["player"]["inventory"]}
        self.assertIn("purifying_lotus", inventory)
        self.assertIn("bitter_island_completed", result["player"]["story_flags"])

    def test_original_nameless_city_chain_preserves_choices_and_reaches_its_own_reward(self):
        base_events = EventRepository.load(SOURCE_ROOT / "content")
        self.assertNotIn("EVT_NAMELESS_CITY_001", base_events.by_id)
        self.assertNotIn("EVT_NAMELESS_CITY_005", (SOURCE_ROOT / "content" / "story_combat_scenarios.json").read_text(encoding="utf-8"))
        self.assertNotIn("rain_archive_lamp", (SOURCE_ROOT / "content" / "items.json").read_text(encoding="utf-8"))

        events = [event for event in self.engine.events if "nameless_city" in event.get("tags", [])]
        self.assertEqual(len(events), 8)
        self.assertTrue(all("monster" in event.get("tags", []) for event in events))
        self.assertTrue(all(len(event["choices"]) >= 3 for event in events))
        self.assertEqual(
            self.engine.events_by_id["EVT_NAMELESS_CITY_001"]["conditions"]["all"][0],
            {"path": "player.path", "op": "eq", "value": "monster"},
        )
        created = self.engine.create_game(
            "雨中记名人", "none", "monster", 615,
            start_world="monster_realm", monster_species_id="fox",
        )
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 7
        game.player.layer = 9
        game.player.faction_combat_bonus = 20_000_000
        game.pending_event = self.engine._instantiate_event(
            self.engine.events_by_id["EVT_NAMELESS_CITY_001"], game, random.Random(5),
        )
        self.engine.store.save(game)
        for choice in ("escort", "preserve", "stop", "expose", "negotiate", "share", "break_seal", "keep_lamp"):
            result = self.engine.choose(created["id"], choice)
        inventory = {item["id"] for item in result["player"]["inventory"]}
        self.assertIn("rain_archive_lamp", inventory)
        self.assertIn("nameless_city_completed", result["player"]["story_flags"])
        self.assertNotIn("name_law_seal", inventory)

    def test_mahayana_epic_chains_defeat_borer_and_true_immortal(self):
        created = self.engine.create_game("屠虫诛仙", "none", "dao", 614, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        game.player.faction_combat_bonus = 100_000_000
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_MOTHER_BORER_001"], game, random.Random(3))
        self.engine.store.save(game)
        for choice in ("vanguard", "break_tide", "rescue_route", "bind", "exploit", "save_allies", "coordinated"):
            result = self.engine.choose(created["id"], choice)
        inventory = {item["id"] for item in result["player"]["inventory"]}
        self.assertIn("mother_borer_core", inventory)
        self.assertIn("punishment_thunder_mark", inventory)
        self.assertIn("mother_borer_completed", result["player"]["story_flags"])

        game = self.engine.store.load(created["id"])
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_MA_LIANG_001"], game, random.Random(4))
        self.engine.store.save(game)
        for choice in ("investigate", "join", "modify", "slay", "attack_bottle", "support_nine", "modified_exit", "advantages", "fire_only"):
            result = self.engine.choose(created["id"], choice)
        inventory = {item["id"] for item in result["player"]["inventory"]}
        known = {art["id"] for art in result["player"]["known_techniques"]}
        self.assertIn("TECH_ORIGIN_GANG_SHIELD", known)
        self.assertIn("true_soul_pill", inventory)
        self.assertIn("fire_beard_contract", inventory)
        self.assertIn("ma_liang_completed", result["player"]["story_flags"])


if __name__ == "__main__":
    unittest.main()
