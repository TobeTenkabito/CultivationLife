import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.system.npc_system import npc_team_combat_power, party_combat_power
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item, max_hp, max_mp, opportunity_required


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class NpcSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def test_party_coefficients_match_design(self):
        self.assertEqual(party_combat_power(100, [60]), 130)
        self.assertEqual(party_combat_power(100, [60, 40]), 125)
        self.assertEqual(npc_team_combat_power([60, 40]), 80)
        self.assertEqual(npc_team_combat_power([100, 60, 40]), 125)

    def test_spirit_void_npc_tracks_and_faces_periodic_tribulation(self):
        created = self.engine.create_game("观劫", "supreme_metal", "dao", 500)
        game = self.engine.store.load(created["id"])
        npc = SectNpc(
            "void-test", "玄劫", "灵界散修", 6, 9, 9000, None,
            spirit_root="supreme_metal", world="spirit", combat_factor=2.0,
            next_tribulation_age=9000, tribulation_power=1000,
        )
        summary = self.engine._resolve_npc_periodic_tribulation(game, npc, random.Random(1))
        self.assertIn("大天劫", summary)
        self.assertTrue(npc.alive)
        self.assertEqual(npc.tribulation_count, 1)
        self.assertEqual(npc.next_tribulation_age, 12000)

    def test_faction_roster_exposes_npc_social_and_combat_fields(self):
        created = self.engine.create_game("观榜", "supreme_metal", "dao", 501)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.faction_id = "tianjian"
        game.player.faction_join_age = game.player.age
        self.engine.store.save(game)
        roster = self.engine.get_game(created["id"])["faction"]["roster"]
        npc = next(entry for entry in roster if not entry["is_player"])
        self.assertGreater(npc["combat_power"], 0)
        self.assertGreater(npc["breakthrough_chance"], 0)
        self.assertIn("attitude", npc)
        self.assertTrue(npc["treasure_name"])
        self.assertTrue(npc["can_intercept"])

    def test_explicit_faction_intercept_creates_a_dedicated_combat_record(self):
        created = self.engine.create_game("宗门伏杀", "supreme_fire", "demonic", 516, start_world="demon")
        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 5, 9
        game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
        game.player.faction_id = "blood_prison"
        target = next(npc for npc in game.sects["blood_prison"].npcs if npc.alive)
        self.engine.store.save(game)
        shown = self.engine.intercept_faction_npc(created["id"], target.id)
        self.assertEqual(shown["history"][0]["event_id"], "SYS_FACTION_INTERCEPT")
        self.assertEqual(shown["history"][0]["state_diff"]["npc_id"], target.id)

    def test_internal_aid_cannot_be_used_at_major_bottleneck(self):
        created = self.engine.create_game("丹界分明", "supreme_metal", "dao", 502)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 2
        game.player.layer = 9
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_major_breakthrough = True
        add_item(game.player, "true_origin_pill")
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "初期或中期"):
            self.engine.use_item(created["id"], "true_origin_pill")

    def test_killing_uncontrolled_sect_member_expelled_and_wanted(self):
        created = self.engine.create_game("同门血案", "supreme_fire", "dao", 503)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 3
        game.player.faction_id = "tianjian"
        victim = next(npc for npc in game.sects["tianjian"].npcs if npc.alive)
        self.engine._apply_cultivator_kill(game, {
            "name": victim.name, "power": 1, "realm_index": victim.realm_index,
            "npc_id": victim.id, "faction_id": "tianjian", "race": victim.race,
            "treasure_item_id": victim.treasure_item_id,
        }, random.Random(1))
        self.assertIsNone(game.player.faction_id)
        self.assertGreaterEqual(game.player.hostility["sect:tianjian"], 60)
        self.assertGreater(game.player.fame, 0)
        self.assertFalse(victim.alive)
        self.assertTrue(victim.treasure_looted)
        self.engine.store.save(game)
        reloaded = self.engine._load(created["id"])
        victim_after = next(npc for npc in reloaded.sects["tianjian"].npcs if npc.id == victim.id)
        self.assertIsNone(victim_after.treasure_item_id)

    def test_low_hostility_capture_creates_prison_sentence(self):
        created = self.engine.create_game("伏法", "supreme_earth", "dao", 504)
        game = self.engine.store.load(created["id"])
        game.player.hostility["sect:tianjian"] = 40
        summary = self.engine._imprison_or_execute(game, "sect:tianjian", random.Random(1), surrendered=True)
        self.assertIsNotNone(game.player.imprisonment)
        self.assertIn("大牢", summary)

    def test_served_sentence_clears_hostility_and_true_immortal_never_loses_realm(self):
        created = self.engine.create_game("仙人伏法", "otherworld", "dao", 523, preset_id="true_immortal")
        game = self.engine.store.load(created["id"])
        game.player.hostility["sect:cloud_immortal_palace"] = 80
        game.player.imprisonment = {
            "key":"sect:cloud_immortal_palace", "name":"云霄仙宫",
            "remaining_years":1, "captured_age":game.player.age, "hostility":80,
            "sentence_years":1, "hostility_reduction_per_year":80,
        }
        original_realm = game.player.realm_index
        self.engine.store.save(game)
        shown = self.engine.prison_action(created["id"], "endure")
        self.assertEqual(shown["player"]["realm_index"], original_realm)
        self.assertEqual(shown["player"]["hostility"]["sect:cloud_immortal_palace"], 0)
        self.assertIsNone(shown["imprisonment"])

    def test_world_coalition_sentence_creates_fame_amnesty_until_fame_rises(self):
        created = self.engine.create_game("服尽界刑", "supreme_earth", "dao", 524)
        game = self.engine.store.load(created["id"])
        game.player.fame = 900
        game.player.hostility["world:human"] = 600
        game.player.imprisonment = {
            "key":"world:human", "name":"人界修仙界", "remaining_years":1,
            "captured_age":game.player.age, "hostility":600, "sentence_years":1,
            "hostility_reduction_per_year":600,
        }
        self.engine.store.save(game)
        self.engine.prison_action(created["id"], "endure")
        game = self.engine.store.load(created["id"])
        self.assertFalse(self.engine._maybe_wanted_encounter(game, random.Random(99)))
        self.assertEqual(game.player.hostility["world:human"], 0)
        game.player.fame += 1
        self.engine._maybe_wanted_encounter(game, random.Random(99))
        self.assertGreater(game.player.hostility["world:human"], 100)

    def test_wanted_state_can_generate_scaled_pursuer_team(self):
        created = self.engine.create_game("追杀临身", "supreme_earth", "dao", 505)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 3
        game.player.hostility["sect:tianjian"] = 101
        triggered = self.engine._maybe_wanted_encounter(game, random.Random(1))
        self.assertTrue(triggered)
        self.assertEqual(game.pending_event["id"], "EVT_WANTED_ENCOUNTER_001")
        target = game.pending_event["runtime"]["target"]
        self.assertGreaterEqual(target["target_realm_index"], game.player.realm_index)
        self.assertLessEqual(len(target["members"]), 3)

    def test_wanted_order_negotiates_on_power_or_realm_and_ends_when_power_falls(self):
        created = self.engine.create_game("反压宗门", "supreme_earth", "dao", 517)
        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 1, 1
        game.player.puppets = [{
            "id":"war-machine", "type":"mechanical", "combat_power":100_000_000, "alive":True,
        }]
        game.player.hostility["sect:tianjian"] = 130
        self.assertTrue(self.engine._maybe_wanted_encounter(game, random.Random(1)))
        self.assertEqual(game.pending_event["id"], "EVT_WANTED_NEGOTIATION_001")
        self.engine.store.save(game)
        settled = self.engine.choose(created["id"], "compensation")
        self.assertEqual(settled["player"]["hostility"]["sect:tianjian"], 0)

        game = self.engine.store.load(created["id"])
        game.player.puppets = []
        game.player.realm_index = 1
        game.sects["tianjian"].extinct = True
        game.player.hostility["sect:tianjian"] = 130
        self.assertTrue(self.engine._maybe_wanted_encounter(game, random.Random(2)))
        self.assertEqual(game.pending_event["id"], "EVT_POWER_FALL_001")
        self.assertEqual(game.pending_event["title"], "宗门的陨落")

    def test_relationships_and_current_sect_are_never_selected_as_pursuers_or_random_prey(self):
        created = self.engine.create_game("不噬近人", "supreme_fire", "demonic", 518, start_world="demon")
        game = self.engine.store.load(created["id"])
        protected = game.sects["blood_prison"].npcs[0]
        game.player.dao_friends = [{
            "id":protected.id, "name":protected.name, "alive":True, "world":"demon",
            "realm_index":protected.realm_index, "layer":protected.layer,
        }]
        target = self.engine._wanted_target(game, "sect", "blood_prison", 150, random.Random(3))
        self.assertNotEqual(target.get("npc_id"), protected.id)
        game.player.faction_id = "blood_prison"
        protected_ids = self.engine._player_protected_npc_ids(game)
        known = self.engine._known_npc_encounter_target(game, {"realm_offsets":[[0,1.0]]}, random.Random(1))
        if known:
            self.assertNotIn(known.get("npc_id"), protected_ids)

    def test_world_coalition_fame_threshold_is_path_specific_and_strict(self):
        normal = self.engine.create_game("正道威名", "supreme_earth", "dao", 519)
        game = self.engine.store.load(normal["id"])
        game.player.fame = 400
        self.engine._maybe_wanted_encounter(game, random.Random(99))
        self.assertNotIn("world:human", game.player.hostility)
        game.player.fame = 401
        self.engine._maybe_wanted_encounter(game, random.Random(99))
        self.assertIn("world:human", game.player.hostility)

        demon = self.engine.create_game("魔道威名", "supreme_fire", "demonic", 520, start_world="demon")
        game = self.engine.store.load(demon["id"])
        game.player.fame = 1000
        self.engine._maybe_wanted_encounter(game, random.Random(99))
        self.assertNotIn("world:demon", game.player.hostility)
        game.player.fame = 1001
        self.engine._maybe_wanted_encounter(game, random.Random(99))
        self.assertIn("world:demon", game.player.hostility)

    def test_world_coalition_does_not_reissue_after_the_world_is_subdued(self):
        created = self.engine.create_game("威压一界", "supreme_earth", "dao", 522)
        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 1, 1
        game.player.fame = 900
        game.player.puppets = [{
            "id":"overwhelming-machine", "type":"mechanical",
            "combat_power":100_000_000, "alive":True,
        }]
        self.assertTrue(self.engine._maybe_wanted_encounter(game, random.Random(1)))
        self.assertEqual(game.pending_event["runtime"]["kind"], "world")
        self.engine.store.save(game)
        settled = self.engine.choose(created["id"], "compensation")
        self.assertIn("world_coalition_subdued:human", settled["player"]["story_flags"])

        game = self.engine.store.load(created["id"])
        self.assertFalse(self.engine._maybe_wanted_encounter(game, random.Random(1)))
        self.assertIsNone(game.pending_event)
        self.assertEqual(game.player.hostility["world:human"], 0)

    def test_demonic_ai_will_not_duel_a_member_of_its_own_sect(self):
        created = self.engine.create_game("同门不斗", "supreme_fire", "demonic", 521, start_world="demon")
        game = self.engine.store.load(created["id"])
        keep = {npc.id for npc in game.sects["blood_prison"].npcs[:2]}
        for npc in self.engine._all_world_npcs(game):
            npc.alive = npc.id in keep
        before = len(game.history)
        self.engine._simulate_cultivator_duel(game, random.Random(1), [])
        self.assertEqual(len(game.history), before)

    def test_low_rank_and_wartime_kills_do_not_create_hostility_and_wanted_is_strictly_over_100(self):
        created = self.engine.create_game("战时执法", "supreme_earth", "dao", 515)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 6
        game.player.world = "spirit"
        game.player.race = "human"
        game.player.faction_id = "taixuan"
        game.sect_relations["taixuan|wanlingshan"] = {"status":"war", "affinity":-80}
        game.race_relations["human|stoneborn"] = {"status":"war", "affinity":-80}

        self.assertFalse(self.engine._kill_generates_hostility(game, "race", "stoneborn", 3))
        self.assertFalse(self.engine._kill_generates_hostility(game, "race", "stoneborn", 6))
        self.assertFalse(self.engine._kill_generates_hostility(game, "sect", "wanlingshan", 6))
        self.assertTrue(self.engine._kill_generates_hostility(game, "race", "cloudkin", 5))

        game.player.hostility["race:cloudkin"] = 100
        self.assertEqual(self.engine._public_wanted(game), [])
        game.player.hostility["race:cloudkin"] = 101
        self.assertEqual(self.engine._public_wanted(game)[0]["hostility"], 101)

    def test_controlled_nonfirst_member_receives_one_warning_then_hunt(self):
        created = self.engine.create_game("掌门之争", "supreme_fire", "dao", 506)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.layer = 1
        game.player.faction_id = "tianjian"
        victim = next(npc for npc in game.sects["tianjian"].npcs if npc.realm_index == 2)
        self.engine._handle_same_sect_kill(game, "tianjian", victim.id)
        self.assertIn("same_sect_kill:tianjian", game.player.faction_warnings)
        self.assertEqual(game.pending_event["id"], "EVT_SECT_FIRST_WARNING_001")
        game.pending_event = None
        self.engine._handle_same_sect_kill(game, "tianjian", victim.id)
        self.assertIsNone(game.player.faction_id)
        self.assertGreaterEqual(game.player.hostility["sect:tianjian"], 90)

    def test_dead_party_reference_is_removed_on_load(self):
        created = self.engine.create_game("故友已逝", "supreme_fire", "dao", 507)
        game = self.engine.store.load(created["id"])
        companion = next(npc for npc in game.sects["tianjian"].npcs if npc.alive)
        game.player.party = [{"id": companion.id}]
        companion.alive = False
        companion.death_reason = "测试陨落"
        self.engine.store.save(game)
        reloaded = self.engine._load(created["id"])
        self.assertEqual(reloaded.player.party, [])

    def test_mahayana_ninth_layer_npc_has_no_breakthrough_chance(self):
        created = self.engine.create_game("道尽于此", "supreme_fire", "dao", 508)
        game = self.engine.store.load(created["id"])
        npc = next(iter(game.world_npcs.values()))
        npc.realm_index = 8
        npc.layer = 9
        npc.world = "spirit"
        self.assertEqual(self.engine._npc_breakthrough_probability(npc), 0.0)
        self.assertIsNone(self.engine._advance_npc_cultivation(npc, random.Random(1)))


if __name__ == "__main__":
    unittest.main()
