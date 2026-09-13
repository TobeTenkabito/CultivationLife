import copy
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.rules import TECHNIQUE_CATALOG, add_item, assign_technique, max_hp, max_mp


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class WarPerformanceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "content").mkdir()
        for source in (SOURCE_ROOT / "content").glob("*.json"):
            (root / "content" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.engine = GameEngine(root)

    def tearDown(self):
        self.temp.cleanup()

    def _sect_war(self, *, voice=True):
        made = self.engine.create_game("战阵之主", "none", "dao", 9901, preset_id="nascent")
        game = self.engine.store.load(made["id"])
        game.player.faction_id = "tianjian"
        if not voice:
            game.player.realm_index = 3
        relation = self.engine._war_relation(game, "sect", "tianjian", "wanmo")
        self.engine._set_diplomatic_relation(game, relation, "war", "tianjian", "wanmo", "sect", -75)
        self.engine.store.save(game)
        return made["id"], game.wars[0]["id"]

    def test_declared_war_uses_vanguard_event_morale_and_collapsible_public_state(self):
        game_id, war_id = self._sect_war()
        shown = self.engine.war_action(game_id, war_id, "conquest")
        self.assertEqual(shown["pending_event"]["id"], "EVT_WAR_VANGUARD_001")
        shown = self.engine.choose(game_id, "fight")
        war = next(row for row in shown["war_system"]["wars"] if row["id"] == war_id)
        self.assertTrue(war["preliminary_resolved"])
        self.assertIn(war["morale"]["attacker"], {80.0, 130.0})
        self.assertLessEqual(len(war["roster"]["attacker"]), 24)
        self.assertLessEqual(len(war["roster"]["defender"]), 24)

    def test_ai_war_advances_by_unit_then_player_can_take_over(self):
        game_id, war_id = self._sect_war(voice=False)
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        self.assertEqual(war["controller"], "ai")
        self.engine._advance_wars_unit(game, random.Random(4))
        self.assertEqual(war["abstract_rounds"], 1)
        game.player.realm_index = 4
        self.engine._advance_wars_unit(game, random.Random(5))
        self.assertEqual(war["controller"], "player")
        self.assertTrue(any(row["title"] == "指挥权移交" for row in war["logs"]))

    def test_auto_advance_player_war_skips_vanguard_without_deploying_player(self):
        game_id, _ = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        before = war["battles"]
        game.settings["auto_advance_player_wars"] = True
        self.engine._advance_wars_unit(game, random.Random(41))
        self.assertEqual(war["battles"], before + 1)
        self.assertTrue(war["preliminary_resolved"])
        self.assertTrue(war["vanguard_skipped"])
        self.assertIsNone(game.pending_event)
        self.assertTrue(any(row["title"] == "自动略过先锋战" for row in war["logs"]))

    def test_peace_sets_system_truce_and_blocks_redeclaration(self):
        game_id, war_id = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        war["battles"] = 2
        self.engine.store.save(game)
        shown = self.engine.war_peace(game_id, war_id, "white_peace")
        self.assertEqual(next(row for row in shown["war_system"]["wars"] if row["id"] == war_id)["status"], "ended")
        loaded = self.engine.store.load(game_id)
        relation = self.engine._war_relation(loaded, "sect", "tianjian", "wanmo")
        with self.assertRaisesRegex(ValueError, "停战期"):
            self.engine._set_diplomatic_relation(loaded, relation, "war", "tianjian", "wanmo", "sect", -75)

    def test_decisive_result_still_cannot_buy_terms_above_war_score(self):
        game_id, war_id = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        war.update(status="peace_ready", winner="attacker", loser="defender", war_score=50.0, battles=4)
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "战争分数"):
            self.engine.war_peace(game_id, war_id, "dissolve")

    def test_dissolution_requires_winner_total_power_advantage(self):
        game_id, war_id = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        war.update(status="peace_ready", winner="attacker", loser="defender", war_score=100.0, battles=4)
        game.player.hp = 1
        game.player.mp = 1
        game.player.faction_combat_bonus = -100_000
        defender = self.engine._find_npc(game, war["roster"]["defender"][0])
        defender.combat_factor = 1000.0
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "总战力"):
            self.engine.war_peace(game_id, war_id, "dissolve")

    def test_allied_power_can_join_coalition_and_be_targeted_by_peace(self):
        game_id, war_id = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        alliance = self.engine._war_relation(game, "sect", "tianjian", "puti")
        alliance.update(status="alliance", affinity=100.0)
        outcomes = self.engine._call_war_allies(game, war, "attacker", random.Random(1))
        self.assertTrue(any("菩提" in line and "加入" in line for line in outcomes))
        self.assertIn("puti", self.engine._coalition_ids(war, "attacker"))
        self.assertTrue(any(owner == "puti" for owner in war["roster_owner"].values()))
        war["battles"] = 2
        war["war_score"] = -100.0
        war["controller"] = "player"
        game.player.faction_id = "wanmo"
        game.player.faction_combat_bonus = 100_000_000
        self.engine.store.save(game)
        shown = self.engine.war_peace(game_id, war_id, "dissolve", target_power_id="puti")
        self.assertEqual(next(row for row in shown["war_system"]["wars"] if row["id"] == war_id)["status"], "ended")
        self.assertTrue(self.engine.store.load(game_id).sects["puti"].extinct)

    def test_new_war_does_not_auto_call_allies_and_player_invites_one_manually(self):
        made = self.engine.create_game("合纵之主", "none", "dao", 9910, preset_id="nascent")
        game = self.engine.store.load(made["id"])
        game.player.faction_id = "tianjian"
        alliance = self.engine._war_relation(game, "sect", "tianjian", "puti")
        alliance.update(status="alliance", affinity=100.0)
        hostile = self.engine._war_relation(game, "sect", "tianjian", "wanmo")
        self.engine._set_diplomatic_relation(game, hostile, "war", "tianjian", "wanmo", "sect", -75)
        war = game.wars[0]
        self.assertEqual(self.engine._coalition_ids(war, "attacker"), ["tianjian"])
        self.engine.store.save(game)
        shown = self.engine.war_action(made["id"], war["id"], "call_allies", ally_id="puti")
        joined = next(row for row in shown["war_system"]["wars"] if row["id"] == war["id"])
        self.assertIn("puti", [row["id"] for row in joined["coalitions"]["attacker"]])

    def test_allied_power_may_refuse_a_call_to_arms(self):
        game_id, _ = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        alliance = self.engine._war_relation(game, "sect", "tianjian", "puti")
        alliance.update(status="alliance", affinity=100.0)
        outcomes = self.engine._call_war_allies(game, war, "attacker", random.Random(2))
        self.assertTrue(any("拒绝" in line for line in outcomes))
        self.assertNotIn("puti", self.engine._coalition_ids(war, "attacker"))
        self.assertFalse(war["called_allies"]["attacker:puti"]["accepted"])

    def test_player_defeat_receives_score_scaled_ai_peace_package(self):
        game_id, _ = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        war["war_score"] = -76.0
        war["morale"]["attacker"] = 0.0
        self.engine._finish_war_by_morale(game, war)
        offer = war["peace_offer"]
        self.assertEqual(offer["budget"], 76)
        self.assertLessEqual(offer["total_cost"], offer["budget"])
        self.assertEqual(offer["demands"][0]["term"], "vassal")
        self.assertNotEqual([row["term"] for row in offer["demands"]], ["execute"])
        self.engine.store.save(game)
        shown = self.engine.war_action(game_id, war["id"], "accept_ai_peace")
        ended = next(row for row in shown["war_system"]["wars"] if row["id"] == war["id"])
        self.assertEqual(ended["status"], "ended")
        self.assertEqual(ended["peace_terms"][0]["term"], "vassal")

    def test_ai_controlled_war_signs_score_scaled_peace_after_morale_collapse(self):
        game_id, _ = self._sect_war(voice=False)
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        war["war_score"] = 58.0
        war["morale"]["defender"] = 0.0
        self.engine._advance_wars_unit(game, random.Random(9))
        self.assertEqual(war["status"], "ended")
        self.assertEqual(war["winner"], "attacker")
        self.assertEqual(war["peace_terms"][0]["term"], "vassal")

    def test_old_war_save_is_lazily_upgraded_to_coalitions(self):
        game_id, _ = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        for key in ("coalitions", "roster_owner", "called_allies", "call_log", "peace_offer"):
            war.pop(key, None)
        self.assertTrue(self.engine._ensure_wars(game))
        self.assertEqual(war["coalitions"]["attacker"][0]["id"], "tianjian")
        self.assertTrue(all(owner in {"tianjian", "wanmo"} for owner in war["roster_owner"].values()))

    def test_old_or_malformed_coalition_rows_never_publish_undefined_names(self):
        game_id, _ = self._sect_war()
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        war["coalitions"] = {"attacker": ["tianjian", {"id":"tianjian"}, {}], "defender": ["wanmo"]}
        war.pop("roster_owner", None)
        shown = self.engine._public_war_system(game)
        public = shown["wars"][0]
        self.assertTrue(all(row["name"] for side in public["coalitions"].values() for row in side))
        self.assertTrue(all(row["owner_name"] for side in public["roster"].values() for row in side))

    def test_other_world_wars_are_not_visible(self):
        game_id, _ = self._sect_war()
        game = self.engine.store.load(game_id)
        game.wars.append({
            "id":"other_world", "kind":"race", "world":"true_demon", "attacker_id":"ancient_demon",
            "defender_id":"heaven_demon", "status":"active", "roster":{"attacker":[],"defender":[]},
            "morale":{"attacker":100,"defender":100}, "exhaustion":{"attacker":0,"defender":0},
        })
        shown = self.engine._public_war_system(game)
        self.assertNotIn("other_world", [row["id"] for row in shown["wars"]])
        self.assertEqual(shown["active_count"], 1)

    def test_player_can_skip_vanguard_and_advance_field_battle(self):
        game_id, war_id = self._sect_war()
        shown = self.engine.war_action(game_id, war_id, "round")
        war = next(row for row in shown["war_system"]["wars"] if row["id"] == war_id)
        self.assertTrue(war["preliminary_resolved"])
        self.assertTrue(war["vanguard_skipped"])
        self.assertEqual(war["battles"], 1)

    def test_ai_calls_one_ally_only_after_its_score_falls_below_minus_25(self):
        game_id, _ = self._sect_war(voice=False)
        game = self.engine.store.load(game_id)
        war = game.wars[0]
        alliance = self.engine._war_relation(game, "sect", "tianjian", "puti")
        alliance.update(status="alliance", affinity=100.0)
        war["war_score"] = -24.0
        self.engine._advance_wars_unit(game, random.Random(1))
        self.assertNotIn("puti", self.engine._coalition_ids(war, "attacker"))
        war["war_score"] = -26.0
        self.engine._advance_wars_unit(game, random.Random(1))
        self.assertIn("puti", self.engine._coalition_ids(war, "attacker"))

    def test_high_realm_defeat_favors_escape_over_death(self):
        low_death, low_escape = self.engine._war_defeat_probabilities(1)
        high_death, high_escape = self.engine._war_defeat_probabilities(8)
        self.assertLess(high_death, low_death)
        self.assertGreater(high_escape, low_escape)

    def test_true_demon_has_five_root_manuals_and_mozun_can_return_to_demon(self):
        made = self.engine.create_game("魔尊", "none", "dao", 9902, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        game.player.path = "demonic"
        game.player.world = "true_demon"
        game.player.location_id = self.engine.maps.default_location("true_demon")
        game.player.additional_roots = []
        for affinity in ("metal", "wood", "water", "fire", "earth"):
            add_item(game.player, f"moque_{affinity}")
        self.engine.store.save(game)
        shown = self.engine.use_item(made["id"], "moque_metal")
        self.assertIn("metal", shown["player"]["additional_roots"])
        shown = self.engine.cross_world(made["id"], "demon")
        self.assertEqual(shown["player"]["world"], "demon")
        self.assertTrue(shown["world_travel"]["can_return_true_demon"])
        shown = self.engine.cross_world(made["id"], "true_demon")
        self.assertEqual(shown["player"]["realm_index"], 8)

    def test_devouring_total_breakthrough_potential_gains_five_percentage_points(self):
        made = self.engine.create_game("吞魂", "supreme_fire", "demonic", 9903, start_world="demon")
        game = self.engine.store.load(made["id"])
        game.player.realm_index = 4
        game.player.hp = max_hp(game.player)
        game.player.mp = max_mp(game.player)
        assign_technique(game.player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_BLOOD_RIVER"]), "main")
        puppet = {"id":"test_puppet", "name":"试魂", "type":"living", "realm_index":2, "layer":1, "combat_power":100.0}
        game.player.puppets.append(puppet)
        base = self.engine._demonic_rules()["devour_bonus_per_realm"]["living"] * 2 * (1 + min(1.0, 100 / self.engine._player_intrinsic_combat_power(game.player)) * .3)
        self.engine._devour_puppet(game, puppet)
        soul = game.player.foreign_souls[-1]
        total = game.player.devouring_breakthrough_bonus + soul["remaining_bonus"]
        self.assertAlmostEqual(total, base + 0.05, places=3)

    def test_annual_core_no_longer_rebuilds_market_or_bootstrap_scans(self):
        made = self.engine.create_game("百年演算", "none", "dao", 9904, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        calls = {"market":0, "sects":0, "npcs":0}
        originals = self.engine._ensure_market, self.engine._ensure_sects, self.engine._ensure_world_npcs
        self.engine._ensure_market = lambda *args, **kwargs: calls.__setitem__("market", calls["market"] + 1)
        self.engine._ensure_sects = lambda *args, **kwargs: calls.__setitem__("sects", calls["sects"] + 1)
        self.engine._ensure_world_npcs = lambda *args, **kwargs: calls.__setitem__("npcs", calls["npcs"] + 1)
        try:
            for _ in range(100):
                game.player.age += 1
                self.engine._advance_world_year(game, random.Random(6), [], encounters=False)
        finally:
            self.engine._ensure_market, self.engine._ensure_sects, self.engine._ensure_world_npcs = originals
        self.assertEqual(calls, {"market":0, "sects":0, "npcs":0})


if __name__ == "__main__":
    unittest.main()
