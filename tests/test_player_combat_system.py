import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cultivation_life.combat_system import PlayerCombatSystem
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import assign_technique, combat_power, max_hp, max_mp


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class PlayerCombatSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8",
            )
        self.engine = GameEngine(root)

    def tearDown(self):
        self.temp.cleanup()

    def _game(self):
        made = self.engine.create_game(
            "观战者", "none", "dao", 811, preset_id="core",
        )
        game = self.engine.store.load(made["id"])
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        return game

    def test_player_fight_is_fully_automatic_and_exposes_six_stat_report(self):
        game = self._game()
        own = self.engine._player_battle_power(game)
        result, summary = self.engine._combat(game, {
            "target_name": "试剑修士", "target_power": own * 0.92,
            "target_realm_index": game.player.realm_index,
            "target_layer": game.player.layer, "combat_type": "cultivator",
            "path": "dao", "action": "spar",
        }, False, random.Random(17))

        self.assertIn(result, {"victory", "defeat"})
        self.assertIn("自动交战", summary)
        report = game.last_combat_report
        self.assertIsNotNone(report)
        self.assertEqual(report["mode"], "标准自动战斗")
        self.assertLessEqual(len(report["rounds"]), 5)
        self.assertEqual(
            {row["name"] for row in report["stat_comparison"]},
            {"威能", "防护", "身法", "神识", "续航", "破法"},
        )
        self.assertIsNone(game.pending_event)

    def test_true_dragon_forces_first_two_rounds_and_suppresses_equal_realm_morale(self):
        game = self._game()
        assign_technique(game.player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_BEAST_TRANSFORMATION"]), "transformation")
        game.player.known_transformations = ["FORM_TRUE_DRAGON"]
        game.player.transformation_mastery = {"FORM_TRUE_DRAGON": {
            "purity": 1.0,
            "stats": {stat: 1.0 for stat in ("might", "guard", "mobility", "sense", "sustain", "breach")},
            "material_id": "test", "source_type": "元神",
        }}
        technique_id = game.player.transformation_technique.id
        game.player.transformation_loadouts[technique_id] = {
            "stored": ["FORM_TRUE_DRAGON"], "active": ["FORM_TRUE_DRAGON"],
        }
        own = self.engine._player_battle_power(game)
        self.engine._combat(game, {
            "target_name": "同境强敌", "target_power": own,
            "target_realm_index": game.player.realm_index, "target_layer": game.player.layer,
            "combat_type": "cultivator", "max_rounds": 4,
        }, False, random.Random(44))
        report = game.last_combat_report
        self.assertGreaterEqual(len(report["rounds"]), 2)
        self.assertEqual([row["initiative"] for row in report["rounds"][:2]], ["player", "player"])
        self.assertTrue(all("强制取得先手" in row["events"][-2] or any("强制取得先手" in event for event in row["events"]) for row in report["rounds"][:2]))
        self.assertTrue(any("初始战意削弱 15%" in event for event in report["key_events"]))

    def test_combat_report_and_support_damage_survive_save_reload(self):
        game = self._game()
        player_power = combat_power(game.player)
        game.player.puppets = [{
            "id": "guard-corpse", "name": "玄阴尸卫", "type": "corpse",
            "realm_index": game.player.realm_index, "combat_power": player_power,
            "corpse_integrity": 100.0, "alive": True,
        }]
        own = self.engine._player_battle_power(game)
        self.engine._combat(game, {
            "target_name": "破阵强敌", "target_power": own * 1.7,
            "target_realm_index": game.player.realm_index + 1,
            "target_layer": 1, "combat_type": "cultivator", "path": "demonic",
        }, True, random.Random(8))
        corpse = game.player.puppets[0]
        self.assertLess(corpse["corpse_integrity"], 100.0)
        self.assertAlmostEqual(game.last_combat_report["player_combat_state_max"], player_power * 2, delta=0.2)
        self.engine.store.save(game)
        shown = self.engine.get_game(game.id)
        self.assertEqual(shown["last_combat_report"]["target_name"], "破阵强敌")
        self.assertTrue(shown["last_combat_report"]["support_updates"])

    def test_qi_concentration_is_not_a_combat_modifier(self):
        game = self._game()
        target = {
            "target_name": "同一幻影", "target_power": self.engine._player_battle_power(game),
            "target_realm_index": game.player.realm_index,
            "target_layer": game.player.layer, "combat_type": "cultivator", "path": "dao",
            "natural_terrain": "开阔",
        }
        first = copy.deepcopy(game)
        first.player.location_id = "whisper_archipelago"
        self.engine._combat(first, copy.deepcopy(target), False, random.Random(32))
        second = copy.deepcopy(game)
        second.player.location_id = "lancang_sea"
        self.engine._combat(second, copy.deepcopy(target), False, random.Random(32))
        self.assertNotEqual(
            self.engine.maps.qi_gain_efficiencies(first.player.world, first.player.location_id),
            self.engine.maps.qi_gain_efficiencies(second.player.world, second.player.location_id),
        )
        self.assertEqual(first.last_combat_report["player_stats"], second.last_combat_report["player_stats"])
        self.assertEqual(first.last_combat_report["rounds"], second.last_combat_report["rounds"])

    def test_natal_artifact_start_modifiers_change_real_six_stat_combat(self):
        game = self._game()
        game.natal_artifact = {
            "item_id":"starfall_blade", "name":"坠星刃", "level":12, "experience":0,
            "slots":["jumang_feather", "rushou_scale", "gonggong_water", "zhurong_flame",
                     "xuanming_rain", "feilian_wind", "houtu_clay"],
        }
        self.engine._ensure_natal_artifact(game)
        own = self.engine._player_battle_power(game)
        target = {
            "target_name":"属性木偶", "target_power":own, "target_realm_index":game.player.realm_index,
            "target_layer":game.player.layer, "combat_type":"cultivator", "max_rounds":3,
        }
        enhanced = copy.deepcopy(game)
        self.engine._combat(enhanced, copy.deepcopy(target), False, random.Random(71))
        baseline = copy.deepcopy(game)
        baseline.natal_artifact["slots"] = [None] * 7
        self.engine._ensure_natal_artifact(baseline)
        self.engine._combat(baseline, copy.deepcopy(target), False, random.Random(71))
        self.assertAlmostEqual(enhanced.last_combat_report["player_stats"]["sense"] / baseline.last_combat_report["player_stats"]["sense"], 1.2, delta=0.01)
        self.assertAlmostEqual(enhanced.last_combat_report["player_stats"]["guard"] / baseline.last_combat_report["player_stats"]["guard"], 1.2, delta=0.01)
        self.assertAlmostEqual(enhanced.last_combat_report["enemy_stats"]["might"] / baseline.last_combat_report["enemy_stats"]["might"], 0.8, delta=0.01)
        self.assertAlmostEqual(enhanced.last_combat_report["enemy_stats"]["mobility"] / baseline.last_combat_report["enemy_stats"]["mobility"], 0.8, delta=0.01)

    def test_natal_artifact_round_traits_and_debuff_immunity_are_executed(self):
        game = self._game()
        game.natal_artifact = {
            "item_id":"starfall_blade", "name":"坠星刃", "level":12, "experience":0,
            "slots":["dijiang_tear", "zhulong_breath", "qiangliang_thunder", "xizi_lightning",
                     "shebishi_orb", None, None],
        }
        self.engine._ensure_natal_artifact(game)
        own = self.engine._player_battle_power(game)
        self.engine._combat(game, {
            "target_name":"法则木偶", "target_power":own, "target_realm_index":game.player.realm_index,
            "target_layer":game.player.layer, "combat_type":"cultivator", "max_rounds":4,
            "player_debuffs":[{"name":"蚀神咒", "stat":"sense", "multiplier":0.5}],
            "enemy_buffs":[{"name":"战神祝福", "stat":"might", "multiplier":1.5}],
        }, True, random.Random(72))
        report = game.last_combat_report
        events = [event for row in report["rounds"] for event in row["events"]]
        self.assertTrue(any("烛龙之息" in event for event in report["key_events"]))
        self.assertTrue(any("奢比尸珠" in event for event in events))
        self.assertTrue(any("翕兹之电" in event for event in events))
        if len(report["rounds"]) >= 2:
            self.assertTrue(any("强良之雷" in event for event in events))
        if report["outcome"] == "victory":
            self.assertTrue(report["kill_ready"])

    def test_battlefield_has_one_natural_property_and_only_arranged_artificial_conditions(self):
        allowed_natural = {"狭窄", "开阔", "险要"}
        for world in self.engine.maps.worlds.values():
            for location in world["locations"]:
                self.assertIn(location["combat_terrain"], allowed_natural)
                self.assertEqual(location["combat_conditions"], [])

        game = self._game()
        target = {
            "target_name": "封锁修士", "target_power": self.engine._player_battle_power(game),
            "target_realm_index": game.player.realm_index, "target_layer": game.player.layer,
            "combat_type": "cultivator", "natural_terrain": "狭窄",
            "artificial_conditions": ["禁空", "禁神识"],
        }
        self.engine._combat(game, target, False, random.Random(22))
        report = game.last_combat_report
        self.assertEqual(report["natural_terrain"], "狭窄")
        self.assertEqual(report["artificial_conditions"], ["禁空", "禁神识"])
        self.assertEqual(report["battlefield_tags"], ["狭窄", "禁空", "禁神识"])

    def test_npc_field_battle_keeps_legacy_resolver(self):
        made = self.engine.create_game("旁观战局", "none", "dao", 9902, preset_id="nascent")
        game = self.engine.store.load(made["id"])
        game.player.faction_id = "tianjian"
        relation = self.engine._war_relation(game, "sect", "tianjian", "wanmo")
        self.engine._set_diplomatic_relation(game, relation, "war", "tianjian", "wanmo", "sect", -75)
        war = game.wars[0]
        with patch.object(PlayerCombatSystem, "resolve", side_effect=AssertionError("player resolver used")):
            text = self.engine._resolve_field_attack(game, war, "attacker", random.Random(3))
        self.assertIsInstance(text, str)
        self.assertIsNone(game.last_combat_report)

    def test_named_story_power_gate_runs_player_combat_resolver(self):
        game = self._game()
        game.player.faction_combat_bonus = 1_000_000
        event = self.engine.events_by_id["EVT_XUTIAN_004"]
        game.pending_event = self.engine._instantiate_event(event, game, random.Random(4))
        self.assertNotIn("新版自动战斗", game.pending_event["choices"][0]["text"])
        self.assertNotIn("原数值作为敌方战力", game.pending_event["choices"][0]["text"])
        self.engine.store.save(game)
        shown = self.engine.choose(game.id, "fight")
        report = shown["last_combat_report"]
        self.assertEqual(report["target_name"], "沧海宫主残魂与夺宝群修")
        self.assertEqual(report["natural_terrain"], "狭窄")
        self.assertEqual(report["artificial_conditions"], ["禁空", "大阵"])
        self.assertIn("沧溟遗魂", [unit["name"] for unit in report["enemy_roster"]])
        self.assertIn("铁臂翁", [unit["name"] for unit in report["player_roster"]])
        man_huzi = next(unit for unit in report["player_roster"] if unit["name"] == "铁臂翁")
        qing_yi = next(unit for unit in report["player_roster"] if unit["name"] == "青崖客")
        self.assertGreater(man_huzi["power"], 40_000)
        self.assertGreater(qing_yi["power"], 20_000)
        self.assertLess(man_huzi["engaged_power"], man_huzi["power"])
        self.assertTrue(report["rounds"][0]["events"][0].startswith("剧情推进："))
        self.assertIn(report["result"], {"victory", "dead", "defeat_survived"})

    def test_ma_liang_final_battle_has_four_authored_enemy_units(self):
        made = self.engine.create_game("破律者", "none", "dao", 918, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        game.player.faction_combat_bonus = 100_000_000
        game.player.story_flags.append("ma_liang_lamp_guarded")
        event = self.engine.events_by_id["EVT_MA_LIANG_008"]
        game.pending_event = self.engine._instantiate_event(event, game, random.Random(2))
        self.engine.store.save(game)
        shown = self.engine.choose(game.id, "advantages")
        report = shown["last_combat_report"]
        self.assertEqual(
            [unit["name"] for unit in report["enemy_roster"]],
            ["重伤真仙洛天衡", "负山神猿", "离火童子", "幽泉魔影"],
        )
        ma_liang = report["enemy_roster"][0]
        self.assertGreater(ma_liang["power"], 90_000_000)
        self.assertLess(ma_liang["engaged_power"], ma_liang["power"])
        self.assertIn("云海老人", [unit["name"] for unit in report["player_roster"]])

    def test_baohua_keeps_top_mahayana_full_power_while_fighting_another_front(self):
        made = self.engine.create_game("封虫者", "none", "dao", 921, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        game.player.faction_combat_bonus = 100_000_000
        game.player.hp = max_hp(game.player)
        game.pending_event = self.engine._instantiate_event(
            self.engine.events_by_id["EVT_MOTHER_BORER_005"], game, random.Random(5),
        )
        self.engine.store.save(game)
        shown = self.engine.choose(game.id, "overpower")
        baohua = next(unit for unit in shown["last_combat_report"]["player_roster"] if unit["name"] == "绯月圣祖")
        self.assertGreater(baohua["power"], 55_000_000)
        self.assertLess(baohua["engaged_power"], baohua["power"])

    def test_solo_ma_liang_choice_excludes_scripted_allies_but_not_enemy_team(self):
        made = self.engine.create_game("独战者", "none", "dao", 919, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        game.player.faction_combat_bonus = 100_000_000
        event = self.engine.events_by_id["EVT_MA_LIANG_008"]
        game.pending_event = self.engine._instantiate_event(event, game, random.Random(3))
        self.engine.store.save(game)
        shown = self.engine.choose(game.id, "solo_finish")
        report = shown["last_combat_report"]
        self.assertNotIn("剧情盟友", [unit["kind_name"] for unit in report["player_roster"]])
        self.assertEqual(len(report["enemy_roster"]), 4)

    def test_demon_and_true_demon_have_distinct_sacred_realm_story_chains(self):
        demon_opening = self.engine.events_by_id["EVT_DEMON_SACRED_001"]
        true_demon_opening = self.engine.events_by_id["EVT_TRUE_DEMON_SACRED_001"]
        self.assertIn("world:demon", demon_opening["tags"])
        self.assertIn("world:true_demon", true_demon_opening["tags"])
        self.assertIn("上层魔域", demon_opening["body"])

        made = self.engine.create_game(
            "真魔行者", "supreme_fire", "demonic", 920, start_world="demon",
        )
        game = self.engine.store.load(made["id"])
        game.player.world = "true_demon"
        game.player.realm_index = 7
        game.player.layer = 5
        game.player.faction_combat_bonus = 20_000_000
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        game.pending_event = self.engine._instantiate_event(true_demon_opening, game, random.Random(4))
        self.engine.store.save(game)
        shown = self.engine.choose(game.id, "counter_hunt")
        self.assertEqual(shown["pending_event"]["id"], "EVT_TRUE_DEMON_SACRED_002")
        self.assertIn("赤霄天君化身", [unit["name"] for unit in shown["last_combat_report"]["enemy_roster"]])
        self.assertIn("绯月盟斥候", [unit["name"] for unit in shown["last_combat_report"]["player_roster"]])


if __name__ == "__main__":
    unittest.main()
