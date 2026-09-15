import copy
import json
import math
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from cultivation_life.engine import GameEngine
from cultivation_life.rules import (
    TECHNIQUE_CATALOG, add_item, assign_technique, divine_sense_level,
    combat_power, divine_sense_breakthrough_cost, effective_karma, max_hp, max_mp, puppet_capacity,
    opportunity_required, qi_level_threshold,
)
from cultivation_life.runtime import encode_rng
from cultivation_life.world_state import race_pair


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class DemonicSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.engine = GameEngine(root)

    def tearDown(self):
        self.temp.cleanup()

    def demonic_game(self):
        created = self.engine.create_game("血烬", "supreme_fire", "demonic", 4401, start_world="demon")
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.layer = 1
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        game.player.opportunity = 10000
        assign_technique(game.player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_BLOOD_RIVER"]), "main")
        self.engine.store.save(game)
        return created["id"], game

    def test_demonic_start_has_unique_realm_and_one_puppet_capacity(self):
        created = self.engine.create_game("初魔", "supreme_fire", "demonic", 4400, start_world="demon")
        shown = self.engine.get_game(created["id"])
        self.assertEqual(shown["player"]["world_name"], "魔界")
        self.assertEqual(shown["player"]["divine_sense"]["level"], 1)
        self.assertEqual(shown["player"]["divine_sense"]["capacity"], 1)
        self.assertEqual(shown["player"]["technique_slots"]["main"]["id"], "TECH_DEMON_BREATHING")
        self.assertEqual(shown["player"]["technique_slots"]["divine_sense"]["id"], "TECH_BLOOD_SOUL_SENSE")
        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 3, 1
        self.assertIn("魔丹", self.engine.present(game)["player"]["realm_name"])

    def test_demonic_ignores_karma_debuff_but_keeps_raw_karma(self):
        _, game = self.demonic_game()
        game.player.karma = 999
        self.assertEqual(effective_karma(game.player), 0)
        self.assertEqual(game.player.karma, 999)

    def test_capture_convert_capacity_and_devour_soul_loop(self):
        game_id, game = self.demonic_game()
        target = {
            "target_name": "陆玄", "target_power": 120, "target_realm_index": 1, "target_layer": 4,
            "members": [{"name": "陆玄", "power": 120, "realm_index": 1, "layer": 4, "path": "dao", "race": "human"}],
        }
        result, _ = self.engine._capture_cultivator(game, target, 10000, random.Random(1))
        self.assertEqual(result, "captured")
        self.engine.store.save(game)
        shown = self.engine.captive_action(game_id, game.player.prisoners[0]["id"], "corpse")
        self.assertEqual(len(shown["demonic_system"]["puppets"]), 1)
        self.assertAlmostEqual(shown["demonic_system"]["puppets"][0]["combat_power"], 96)

        reloaded = self.engine.store.load(game_id)
        reloaded.player.prisoners.append({
            "id": "second", "name": "第二人", "realm_index": 1, "layer": 1,
            "combat_power": 50, "affinity": 0, "path": "dao",
        })
        self.engine.store.save(reloaded)
        with self.assertRaisesRegex(ValueError, "神识"):
            self.engine.captive_action(game_id, "second", "corpse")

        puppet_id = shown["demonic_system"]["puppets"][0]["id"]
        devoured = self.engine.puppet_action(game_id, puppet_id, "devour")
        self.assertFalse(devoured["demonic_system"]["puppets"])
        self.assertEqual(len(devoured["demonic_system"]["foreign_souls"]), 1)
        self.assertGreater(devoured["demonic_system"]["breakthrough_bonus"], 0)

    def test_killing_cultivator_is_primary_demonic_opportunity_source(self):
        _, game = self.demonic_game()
        before = game.player.opportunity
        target = {
            "target_name":"弱修", "target_power":1, "target_realm_index":2, "target_layer":1,
            "combat_type":"cultivator", "kill_karma":True,
            "members":[{"name":"弱修", "power":1, "realm_index":2, "layer":1, "race":"human"}],
        }
        result, summary = self.engine._combat(game, target, True, random.Random(1))
        self.assertEqual(result, "killed")
        self.assertGreaterEqual(game.player.opportunity - before, 32)
        self.assertGreater(game.player.karma, 0)
        self.assertIn("杀戮炼化机缘", summary)

    def test_killing_beast_grants_the_same_demonic_kill_opportunity(self):
        _, game = self.demonic_game()
        before = game.player.opportunity
        target = {
            "target_name":"弱兽", "target_power":1, "target_realm_index":2,
            "combat_type":"beast", "success_threshold":1.2,
        }
        result, summary = self.engine._combat(game, target, True, random.Random(1))
        self.assertEqual(result, "killed")
        self.assertGreaterEqual(game.player.opportunity - before, 32)
        self.assertIn("杀戮炼化机缘", summary)

    def test_puppets_contribute_opportunity_and_only_living_loses_control(self):
        _, game = self.demonic_game()
        game.player.puppets = [
            {"id":"corpse", "name":"尸", "type":"corpse", "realm_index":2, "combat_power":100, "control":100, "alive":True},
            {"id":"living", "name":"傀", "type":"living", "realm_index":2, "combat_power":100, "control":80, "alive":True},
        ]
        before = game.player.opportunity
        self.engine._annual_demonic_update(game, random.Random(99))
        self.assertGreater(game.player.opportunity, before)
        self.assertEqual(game.player.puppets[0]["control"], 100)
        self.assertLess(game.player.puppets[1]["control"], 80)

    def test_fixed_puppets_add_to_body_while_living_puppet_joins_party(self):
        _, game = self.demonic_game()
        game.player.puppets = [
            {"type":"mechanical", "combat_power":100, "alive":True},
            {"type":"corpse", "combat_power":100, "alive":True},
            {"type":"living", "combat_power":100, "alive":True},
        ]
        base_power = combat_power(game.player)
        self.assertEqual(self.engine._puppet_intrinsic_contribution(game.player), 100)
        self.assertEqual(self.engine._player_intrinsic_combat_power(game.player), base_power + 100)
        self.assertEqual(self.engine._player_battle_power(game), base_power + 140)
        public = self.engine._public_demonic_system(game.player)
        self.assertEqual([row["battle_contribution"] for row in public["puppets"]], [40, 60, 80])

    def test_reinforce_living_puppet_control_costs_mp(self):
        game_id, game = self.demonic_game()
        game.player.puppets = [{
            "id":"living", "name":"傀", "type":"living", "realm_index":2, "layer":1,
            "combat_power":100, "control":50, "alive":True,
        }]
        before_mp = game.player.mp
        self.engine.store.save(game)
        shown = self.engine.puppet_action(game_id, "living", "reinforce_control")
        puppet = shown["demonic_system"]["puppets"][0]
        self.assertGreater(puppet["control"], 50)
        self.assertLess(shown["player"]["mp"], before_mp)

    def test_lower_realm_infusion_always_adds_power_but_same_realm_can_fail(self):
        class HighRoll:
            @staticmethod
            def random():
                return 0.99

        _, game = self.demonic_game()
        lower = {
            "id":"lower", "name":"低阶", "type":"living", "realm_index":3, "layer":1,
            "combat_power":100, "control":80, "main_technique_id":"TECH_BLOOD_RIVER",
            "cultivation_progress":0, "last_infusion_age":None, "alive":True,
        }
        self.engine._infuse_puppet(game, lower, HighRoll())
        self.assertGreater(lower["combat_power"], 100)
        game.player.mp = max_mp(game.player)
        same = lower | {
            "id":"same", "name":"同阶", "realm_index":4, "combat_power":100,
            "cultivation_progress":0, "last_infusion_age":None,
        }
        summary = self.engine._infuse_puppet(game, same, HighRoll())
        self.assertEqual(same["combat_power"], 100)
        self.assertIn("未转化为战力", summary)

    def test_soul_refining_consumes_cultivation_and_releases_remaining_bonus(self):
        game_id, game = self.demonic_game()
        game.player.foreign_souls = [{
            "id": "soul", "name": "试魂", "realm_index": 2, "strength": 1,
            "progress": 99.0, "required": 100.0, "remaining_bonus": 0.08,
            "refined": False, "last_refine_age": None,
        }]
        before = game.player.opportunity
        self.engine.store.save(game)
        shown = self.engine.refine_foreign_souls(game_id)
        soul = shown["demonic_system"]["foreign_souls"][0]
        self.assertTrue(soul["refined"])
        self.assertGreaterEqual(shown["demonic_system"]["breakthrough_bonus"], 0.08)
        self.assertLess(shown["player"]["opportunity"], before)

    def test_secluded_refining_finishes_all_souls_for_twenty_percent_more_time_without_costs(self):
        game_id, game = self.demonic_game()
        game.player.opportunity = 321
        game.player.mp = 77
        game.player.lifespan = 10000
        game.player.foreign_souls = [
            {
                "id":"soul-a", "name":"甲魂", "realm_index":1, "strength":0,
                "progress":20.0, "required":100.0, "remaining_bonus":0.03,
                "refined":False, "last_refine_age":None,
            },
            {
                "id":"soul-b", "name":"乙魂", "realm_index":2, "strength":0,
                "progress":40.0, "required":100.0, "remaining_bonus":0.04,
                "refined":False, "last_refine_age":None,
            },
        ]
        normal_gain = self.engine._soul_refine_gain(game.player)
        expected_years = math.ceil((80 + 60) * 1.2 / normal_gain)
        before_age = game.player.age
        self.engine.store.save(game)
        shown = self.engine.secluded_refine_foreign_souls(game_id)
        self.assertEqual(shown["player"]["age"] - before_age, expected_years)
        self.assertEqual(shown["player"]["opportunity"], 321)
        self.assertEqual(shown["player"]["mp"], 77)
        self.assertTrue(all(entry["refined"] for entry in shown["demonic_system"]["foreign_souls"]))
        self.assertAlmostEqual(shown["demonic_system"]["breakthrough_bonus"], 0.07)

    def test_mechanical_puppet_uses_recipe_and_capacity(self):
        game_id, game = self.demonic_game()
        add_item(game.player, "spirit_stone", 25)
        self.engine.store.save(game)
        shown = self.engine.craft_mechanical_puppet(game_id)
        self.assertEqual(shown["demonic_system"]["puppets"][0]["type"], "mechanical")
        inventory = {item["id"]: item["quantity"] for item in shown["player"]["inventory"]}
        self.assertNotIn("spirit_sword", inventory)

    def test_breakthrough_directly_raises_divine_sense_level(self):
        _, game = self.demonic_game()
        game.player.divine_sense_rank = 2
        game.player.divine_sense_experience = 13
        before = divine_sense_level(game.player)
        self.engine._complete_minor_breakthrough(game, random.Random(2), "魔婴初期")
        self.assertEqual(divine_sense_level(game.player), before + 1)
        self.assertEqual(game.player.divine_sense_experience, 13)
        self.assertEqual(puppet_capacity(game.player), 1)

    def test_divine_sense_capacity_increases_only_every_three_levels(self):
        _, game = self.demonic_game()
        expected = {1:1, 2:1, 3:1, 4:2, 6:2, 7:3}
        for level, capacity in expected.items():
            game.player.divine_sense_rank = level
            self.assertEqual(puppet_capacity(game.player), capacity)

    def test_manual_divine_sense_breakthrough_consumes_only_required_experience(self):
        game_id, game = self.demonic_game()
        cost = divine_sense_breakthrough_cost(game.player)
        game.player.divine_sense_experience = cost + 7
        self.engine.store.save(game)
        shown = self.engine.divine_sense_breakthrough(game_id)
        self.assertEqual(shown["player"]["divine_sense"]["level"], 2)
        self.assertEqual(shown["player"]["divine_sense"]["experience"], 7)

    def test_legacy_cumulative_sense_experience_migrates_to_rank_and_remainder(self):
        game_id, game = self.demonic_game()
        self.engine.store.save(game)
        save_path = self.engine.store._path(game_id)
        raw = json.loads(save_path.read_text(encoding="utf-8"))
        raw["version"] = 4
        raw["player"].pop("divine_sense_rank", None)
        raw["player"]["divine_sense_experience"] = 87
        save_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        shown = self.engine.get_game(game_id)
        self.assertEqual(shown["player"]["divine_sense"]["level"], 2)
        self.assertEqual(shown["player"]["divine_sense"]["experience"], 7)

    def test_demonic_ascension_to_true_demon_clears_puppets(self):
        game_id, game = self.demonic_game()
        game.player.realm_index, game.player.layer = 5, 1
        game.player.world = "demon"
        game.player.qi_experience["demon"] = qi_level_threshold(8)
        game.player.fame = 1234
        game.player.puppets = [{"id":"lost", "name":"遗傀", "type":"corpse", "combat_power":100, "alive":True}]
        self.engine.store.save(game)
        before = self.engine.get_game(game_id)
        self.assertTrue(before["demonic_system"]["true_demon_ascension"]["available"])
        shown = self.engine.begin_spirit_crossing(game_id)
        self.assertEqual(shown["player"]["world"], "true_demon")
        self.assertEqual(shown["player"]["fame"], 0)
        self.assertFalse(shown["demonic_system"]["puppets"])
        self.assertEqual(shown["history"][0]["state_diff"]["lost_puppets"], 1)

    def test_true_demon_ascension_below_demon_qi_requirement_is_fatal(self):
        game_id, game = self.demonic_game()
        game.player.realm_index, game.player.layer = 5, 1
        game.player.world = "demon"
        game.player.qi_experience["demon"] = qi_level_threshold(7)
        self.engine.store.save(game)
        shown = self.engine.begin_spirit_crossing(game_id)
        self.assertFalse(shown["player"]["alive"])
        self.assertEqual(shown["player"]["world"], "demon")
        self.assertIn("未达飞升真魔界所需的 8 级", shown["player"]["death_reason"])
        self.assertEqual(shown["history"][0]["event_id"], "SYS_TRUE_DEMON_ASCENSION_QI_DEATH")

    def test_demon_world_caps_generated_npcs_at_transformation_realm(self):
        _, game = self.demonic_game()
        game.player.realm_index, game.player.layer = 5, 9
        target = self.engine._generate_cultivator_target(
            game.player, "越界来敌", {"realm_offsets": [[3, 1.0]], "team_chance": 1.0},
            random.Random(12), game=game,
        )
        self.assertLessEqual(target["target_realm_index"], 5)
        self.assertTrue(all(member["realm_index"] <= 5 for member in target["members"]))
        self.assertTrue(all(
            npc.realm_index <= 5 for sect in game.sects.values() if sect.world == "demon"
            for npc in sect.npcs
        ))

    def test_true_demon_world_has_fixed_experts_factions_races_and_ranking(self):
        _, game = self.demonic_game()
        game.player.world = "true_demon"
        game.player.location_id = self.engine.maps.default_location("true_demon")
        shown = self.engine.present(game)
        experts = {row["name"]: row for row in shown["world_npcs"] if row["perceived_alive"]}
        self.assertEqual(experts["巫迟烟"]["realm_name"], "合体中期")
        self.assertEqual(experts["曾砺川"]["realm_name"], "合体中期")
        self.assertEqual(
            {row["name"] for row in shown["faction"]["available"]},
            {"天魔宫", "万魂渊", "黑日神殿"},
        )
        self.assertTrue(shown["spirit_ranking"]["available"])
        self.assertEqual(shown["spirit_ranking"]["title"], "真魔界天榜前二十")
        self.assertTrue(shown["race_system"]["available"])
        self.assertEqual(len(shown["race_system"]["races"]), 20)
        self.assertIn("heaven_demon", shown["race_system"]["races"])
        self.assertIn("ancient_demon", shown["race_system"]["races"])
        self.assertNotIn("monster", shown["race_system"]["races"])
        human_presets = shown["race_system"]["races"]["human"]["supported_factions"]
        self.assertIn("天外归墟城", {row["name"] for row in human_presets})
        self.assertNotIn("云霄剑宫", {row["name"] for row in human_presets})
        self.assertNotIn("人妖两族盟约", {row["name"] for row in shown["race_system"]["alliances"]})
        self.assertTrue(any(
            npc.realm_index == 8 for sect in game.sects.values() if sect.world == "true_demon"
            for npc in sect.npcs
        ))

    def test_v8_save_migrates_shared_true_demon_races_and_loads_new_roster(self):
        game_id, game = self.demonic_game()
        game.world_rules_version = 8
        game.player.world = "true_demon"
        game.player.race = "moonfolk"
        game.player.lineage_race = "moonfolk"
        game.player.allegiance_race = "moonfolk"
        game.sects["myriad_soul_abyss"].npcs[0].race = "moonfolk"
        legacy_npc = copy.deepcopy(game.world_npcs["rank_shuangdi"])
        legacy_npc.id = "legacy_true_demon_race"
        legacy_npc.world = "true_demon"
        legacy_npc.race = "stoneborn"
        game.notable_npcs[legacy_npc.id] = legacy_npc
        game.race_relations.pop("blood_demon|soul_demon", None)
        old_spirit_relation = copy.deepcopy(game.race_relations["human|monster"])
        self.engine.store.save(game)

        shown = self.engine.get_game(game_id)
        migrated = self.engine.store.load(game_id)

        self.assertEqual(migrated.world_rules_version, 9)
        self.assertEqual(migrated.player.race, "soul_demon")
        self.assertEqual(migrated.player.lineage_race, "soul_demon")
        self.assertEqual(migrated.player.allegiance_race, "soul_demon")
        self.assertEqual(migrated.sects["myriad_soul_abyss"].npcs[0].race, "soul_demon")
        self.assertEqual(migrated.notable_npcs[legacy_npc.id].race, "rock_demon")
        self.assertEqual(migrated.race_relations["human|monster"], old_spirit_relation)
        self.assertEqual(migrated.race_relations["blood_demon|soul_demon"]["status"], "alliance")
        self.assertEqual(len(shown["race_system"]["races"]), 20)
        self.assertNotIn("moonfolk", shown["race_system"]["races"])
        self.assertTrue(any(record.event_id == "SYS_TRUE_DEMON_RACE_MIGRATION" for record in migrated.history))

    def test_true_demon_diplomacy_ignores_spirit_race_relations(self):
        _, game = self.demonic_game()
        game.player.world = "true_demon"
        self.engine._ensure_race_relations(game)
        game.race_relations[race_pair("human", "heaven_demon")]["status"] = "neutral"
        game.race_relations[race_pair("human", "monster")]["status"] = "war"
        self.assertFalse(self.engine._maybe_race_war_ambush(game, random.Random(8302)))

        game.race_relations[race_pair("human", "monster")]["status"] = "alliance"
        before = game.player.opportunity
        self.engine._advance_diplomacy_unit(game, Mock(random=lambda: 0.99))
        self.assertEqual(game.player.opportunity, before)

        game.race_relations[race_pair("human", "monster")]["status"] = "neutral"
        game.race_relations[race_pair("human", "heaven_demon")]["status"] = "alliance"
        before = game.player.opportunity
        self.engine._advance_diplomacy_unit(game, Mock(random=lambda: 0.99))
        self.assertEqual(game.player.opportunity, before + 2)

    def test_v7_save_migrates_demon_world_upper_realm_npcs(self):
        game_id, game = self.demonic_game()
        game.world_rules_version = 7
        game.notable_npcs["legacy_upper"] = copy.deepcopy(game.world_npcs["rank_shuangdi"])
        game.notable_npcs["legacy_upper"].id = "legacy_upper"
        game.notable_npcs["legacy_upper"].name = "旧魔界合体"
        game.notable_npcs["legacy_upper"].world = "demon"
        game.notable_npcs["legacy_upper"].realm_index = 7
        self.engine.store.save(game)
        self.engine.get_game(game_id)
        migrated = self.engine.store.load(game_id)
        self.assertEqual(migrated.notable_npcs["legacy_upper"].world, "true_demon")
        self.assertEqual(migrated.world_npcs["wu_xingyun"].world, "true_demon")
        self.assertEqual(migrated.world_npcs["wu_xingyun"].realm_index, 7)
        self.assertEqual(migrated.world_rules_version, 9)

    def test_demon_world_market_and_treasure_include_new_demonic_content(self):
        _, game = self.demonic_game()
        game.player.realm_index = 3
        self.engine._ensure_market(game, random.Random(8))
        market = self.engine._public_market(game)
        self.assertTrue(market["available"])
        self.assertTrue(market["offers"])
        for category in ("technique", "pill", "artifact"):
            self.assertTrue(self.engine._treasure_reward_pool(game, category))
        self.assertGreaterEqual(
            len([entry for entry in TECHNIQUE_CATALOG.values() if entry.path == "demonic"]), 10,
        )

    def test_divine_sense_training_uses_equipped_manual(self):
        game_id, game = self.demonic_game()
        before = game.player.divine_sense_experience
        self.engine.store.save(game)
        shown = self.engine.advance(game_id, "sense_train")
        self.assertGreater(shown["player"]["divine_sense"]["experience"] - before, 20)

    def test_master_and_companion_can_start_relationship_capture_chain(self):
        for kind in ("master", "companion"):
            game_id, game = self.demonic_game()
            relation = self.engine._relationship_snapshot(
                f"weak-{kind}", f"弱{kind}", 1, 1, "event", 30, 100,
                spirit_root="heavenly_fire_earth", path="dao", world="demon", affinity=80,
            )
            if kind == "master":
                game.player.master = relation
            else:
                game.player.dao_companion = relation
            game.rng_state = encode_rng(random.Random(1))
            self.engine.store.save(game)
            started = self.engine.begin_relationship_capture(game_id, kind)
            self.assertEqual(started["pending_event"]["id"], "EVT_RELATION_CAPTURE_001")
            opened = self.engine.choose(game_id, "ambush")
            self.assertEqual(opened["pending_event"]["id"], "EVT_RELATION_CAPTURE_002")
            captured = self.engine.choose(game_id, "soul_seal")
            self.assertIsNone(captured["player"]["master"] if kind == "master" else captured["dao_companion"])
            self.assertTrue(any(row["id"] == f"weak-{kind}" for row in captured["demonic_system"]["prisoners"]))

    def test_demonic_friend_can_be_captured_through_relationship_event(self):
        game_id, game = self.demonic_game()
        friend = self.engine._relationship_snapshot(
            "weak-friend", "弱道友", 1, 1, "event", 30, 100,
            spirit_root="heavenly_fire_earth", path="dao", world="demon", affinity=80,
        )
        game.player.dao_friends = [friend]
        game.rng_state = encode_rng(random.Random(1))
        self.engine.store.save(game)
        started = self.engine.begin_relationship_capture(game_id, "friend", "weak-friend")
        self.assertEqual(started["pending_event"]["runtime"]["target_id"], "weak-friend")
        self.engine.choose(game_id, "ambush")
        captured = self.engine.choose(game_id, "soul_seal")
        self.assertFalse(captured["dao_friends"])
        self.assertTrue(any(row["id"] == "weak-friend" for row in captured["demonic_system"]["prisoners"]))

    def test_heavenly_demon_tribulation_has_five_base_fights_and_can_chain_souls(self):
        _, game = self.demonic_game()
        game.player.world = "true_demon"
        game.player.realm_index, game.player.layer = 6, 9
        game.player.puppets = [{
            "id":"overwhelming-corpse", "name":"魔尊尸", "type":"corpse",
            "realm_index":8, "layer":9, "combat_power":100_000_000, "alive":True,
        }]
        game.player.foreign_souls = []
        self.engine._start_breakthrough_trial(game, "heavenly_demon", 6, 7, "炼魔后期", True, random.Random(4))
        for _ in range(5):
            self.engine._resolve_heavenly_demon_battle(game, "heavenly_demon_combat", random.Random(4))
        self.assertEqual(game.player.realm_index, 7)
        self.assertIsNone(game.active_trial)

        class LureRoll:
            @staticmethod
            def random(): return 0.0
            @staticmethod
            def uniform(low, high): return low
            @staticmethod
            def choice(values): return values[0]

        game.player.realm_index, game.player.layer = 6, 9
        game.player.foreign_souls = [{
            "id":"soul-repeat", "name":"旧敌", "realm_index":6,
            "combat_power":1000, "refined":True,
        }]
        self.engine._start_breakthrough_trial(game, "heavenly_demon", 6, 7, "炼魔后期", True, LureRoll())
        before = game.player.opportunity
        self.engine._resolve_heavenly_demon_battle(game, "heavenly_demon_combat", LureRoll())
        self.assertEqual(game.pending_event["id"], "EVT_HEAVENLY_DEMON_SOUL_001")
        self.engine._resolve_heavenly_demon_battle(game, "heavenly_demon_soul", LureRoll())
        self.assertEqual(game.pending_event["id"], "EVT_HEAVENLY_DEMON_SOUL_001")
        self.assertEqual(game.active_trial["base_rounds_completed"], 1)
        self.assertEqual(game.active_trial["soul_battles"], 1)
        self.assertGreater(game.player.opportunity, before)

    def test_upper_demonic_major_breakthrough_selects_heavenly_demon_tribulation(self):
        game_id, game = self.demonic_game()
        game.player.world = "true_demon"
        game.player.realm_index, game.player.layer = 6, 9
        game.player.opportunity = opportunity_required(game.player)
        game.player.devouring_breakthrough_bonus = 0.55
        game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
        game.rng_state = encode_rng(random.Random(1))
        self.engine.store.save(game)
        shown = self.engine.breakthrough(game_id)
        self.assertEqual(shown["trial"]["kind"], "heavenly_demon")
        self.assertEqual(shown["trial"]["minimum_rounds"], 5)
        self.assertEqual(shown["pending_event"]["id"], "EVT_HEAVENLY_DEMON_TRIBULATION_001")

    def test_reaching_demonic_void_grants_infinite_life_and_three_strike_thunder(self):
        _, game = self.demonic_game()
        game.player.world = "true_demon"
        game.player.realm_index, game.player.layer = 5, 9
        game.player.age = 2000
        game.player.lifespan = 2500
        self.engine._complete_major_breakthrough(game, random.Random(3), "化魔后期")
        self.assertEqual(game.player.realm_index, 6)
        self.assertIsNone(game.player.lifespan)
        self.assertEqual(game.player.next_tribulation_age, 5000)
        game.player.age = 5000
        self.engine._check_tribulation(game, random.Random(3))
        self.assertEqual(game.active_trial["kind"], "periodic_thunder")
        self.assertEqual(len(game.active_trial["event_ids"]), 3)

    def test_demonic_periodic_thunder_deals_twenty_percent_more_damage(self):
        _, demon = self.demonic_game()
        demon.player.realm_index, demon.player.layer = 6, 1
        demon.player.hp, demon.player.mp = max_hp(demon.player), max_mp(demon.player)
        demon.active_trial = {
            "kind":"periodic_thunder", "source_realm":6, "target_realm":6, "target_layer":1,
            "major":False, "old_label":"炼魔初期", "step_index":0,
            "event_ids":["EVT_PERIODIC_THUNDER_001","EVT_PERIODIC_THUNDER_002","EVT_PERIODIC_THUNDER_003"],
            "lethal":True, "power":0.001,
        }
        normal = copy.deepcopy(demon)
        normal.player.path = "dao"
        demon_hp, normal_hp = demon.player.hp, normal.player.hp
        self.engine._resolve_trial_step(demon, "thunder_1", random.Random(11))
        self.engine._resolve_trial_step(normal, "thunder_1", random.Random(11))
        demon_loss, normal_loss = demon_hp - demon.player.hp, normal_hp - normal.player.hp
        self.assertAlmostEqual(demon_loss / normal_loss, 1.2)

    def test_demon_world_faction_diplomacy_unlocks_at_magic_infant_realm(self):
        game_id, game = self.demonic_game()
        game.player.realm_index, game.player.layer = 4, 1
        game.player.faction_id = "blood_prison"
        self.engine.store.save(game)
        self.assertTrue(self.engine.get_game(game_id)["faction"]["has_diplomatic_voice"])
        shown = self.engine.propose_sect_diplomacy(game_id, "corpse_hall", "neutral")
        self.assertTrue(any(row["event_id"] == "SYS_PLAYER_SECT_VOTE" for row in shown["history"]))

    def test_demon_world_starts_with_two_factions(self):
        created = self.engine.create_game("宗门魔", "supreme_fire", "demonic", 4420, start_world="demon")
        faction = self.engine.get_game(created["id"])["faction"]
        self.assertEqual({row["name"] for row in faction["available"]}, {"血狱魔宗", "阴尸殿"})

    def test_player_breakthrough_pill_is_blocked_for_demonic_path(self):
        game_id, game = self.demonic_game()
        game.player.realm_index, game.player.layer = 2, 9
        add_item(game.player, "golden_origin_pill")
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "魔修不能"):
            self.engine.use_item(game_id, "golden_origin_pill")


if __name__ == "__main__":
    unittest.main()
