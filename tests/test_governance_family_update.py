import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from cultivation_life.engine import GameEngine, encode_rng
from cultivation_life.models import SectNpc, SectState
from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, TECHNIQUE_CATALOG
from cultivation_life.rules import add_item, learn_technique, max_hp, max_mp


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class GovernanceFamilyUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def test_story_probability_increases_once_per_action_unit(self):
        created = self.engine.create_game("一念百年", "none", "dao", 901, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        event = self.engine.events_by_id["EVT_MOTHER_BORER_001"]
        rng = MagicMock()
        rng.random.return_value = 0.99
        self.assertFalse(self.engine._roll_escalating_event(game, event, rng))
        self.assertEqual(game.story_trigger_attempts["mother_borer_eligible"], 1)
        self.assertFalse(self.engine._roll_escalating_event(game, event, rng))
        self.assertEqual(game.story_trigger_attempts["mother_borer_eligible"], 2)

    def test_mahayana_cross_world_suppression_and_restoration(self):
        created = self.engine.create_game("往返两界", "none", "dao", 902, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        original_layer = game.player.layer
        game.player.hp = max_hp(game.player) * 0.63
        game.player.mp = max_mp(game.player) * 0.41
        self.engine.store.save(game)

        human = self.engine.cross_world(created["id"], "human")
        self.assertEqual((human["player"]["world"], human["player"]["realm_index"], human["player"]["layer"]), ("human", 5, 3))
        self.assertTrue(human["player"]["cultivation_suppressed"])
        spirit = self.engine.cross_world(created["id"], "spirit")
        self.assertEqual((spirit["player"]["world"], spirit["player"]["realm_index"], spirit["player"]["layer"]), ("spirit", 8, original_layer))
        self.assertFalse(spirit["player"]["cultivation_suppressed"])
        self.assertAlmostEqual(spirit["player"]["hp"] / spirit["player"]["max_hp"], 0.63, places=2)
        self.assertAlmostEqual(spirit["player"]["mp"] / spirit["player"]["max_mp"], 0.41, places=2)

    def test_child_can_enter_cultivation_and_found_family(self):
        created = self.engine.create_game("血脉开枝", "supreme_metal", "dao", 903, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.dao_companion = {
            "id":"companion_test", "name":"顾月", "alive":True, "world":"human",
            "spirit_root":"supreme_wood", "acquired_root":False,
        }
        rng = MagicMock()
        rng.random.side_effect = [0.0, 0.0]
        rng.choice.side_effect = lambda values: values[0]
        text = self.engine._try_conceive_child(game, rng)
        self.assertIn("诞下一名后代", text)
        child = game.player.offspring[0]
        child.update(age=8, cultivation_started=True, realm_index=1, layer=1, lifespan=110)
        self.engine.store.save(game)

        shown = self.engine.create_family(created["id"], "问道韩家")
        self.assertTrue(shown["family"]["exists"])
        self.assertEqual(shown["family"]["roster"][0]["member_type"], "本家")

    def test_child_root_inheritance_is_raised_to_ninety_percent(self):
        created = self.engine.create_game("灵根开枝", "supreme_metal", "dao", 913, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.dao_companion = {
            "id":"companion_root", "name":"木灵道侣", "alive":True, "world":"human",
            "realm_index":3, "spirit_root":"supreme_wood", "acquired_root":False,
        }
        rng = MagicMock()
        rng.random.side_effect = [0.0, 0.85]
        rng.choice.side_effect = lambda values: values[0]
        rng.randint.return_value = 90
        self.engine._try_conceive_child(game, rng)
        self.assertNotEqual(game.player.offspring[0]["spirit_root"], "none")

    def test_conception_medicine_works_after_natural_chance_reaches_zero(self):
        created = self.engine.create_game("仙凡蕴嗣", "supreme_metal", "dao", 923, preset_id="spirit")
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.dao_companion = {
            "id":"companion_medicine", "name":"顾月", "alive":True, "world":game.player.world,
            "realm_index":5, "spirit_root":"supreme_wood", "acquired_root":False,
        }
        add_item(game.player, "yin_yang_creation_dew")
        self.engine.store.save(game)
        used = self.engine.use_item(game.id, "yin_yang_creation_dew")
        self.assertAlmostEqual(used["player"]["next_companion_conception_bonus"], 0.16)
        game = self.engine.store.load(game.id)
        rng = MagicMock()
        rng.random.return_value = 0.0
        rng.choice.side_effect = lambda values: values[0]
        rng.randint.return_value = 90
        text = self.engine._try_conceive_child(game, rng)
        self.assertIn("诞下一名后代", text)
        self.assertEqual(game.player.next_companion_conception_bonus, 0.0)

    def test_unregistered_child_ages_dies_and_cultivates_normally(self):
        created = self.engine.create_game("血脉流转", "supreme_metal", "dao", 914, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.offspring = [
            {"id":"mortal_child","name":"韩凡","age":79,"alive":True,"world":"human","spirit_root":"none","cultivation_started":False,"realm_index":0,"layer":1,"lifespan":80,"path":"dao"},
            {"id":"cultivator_child","name":"韩真","age":20,"alive":True,"world":"human","spirit_root":"supreme_metal","cultivation_started":True,"realm_index":1,"layer":1,"lifespan":110,"path":"dao","cultivation_progress":10000},
        ]
        rng = MagicMock()
        rng.uniform.return_value = 1.0
        rng.random.return_value = 0.0
        self.engine._annual_offspring_and_family_update(game, rng)
        self.assertFalse(game.player.offspring[0]["alive"])
        self.assertEqual(game.player.offspring[0]["death_reason"], "寿元耗尽")
        self.assertEqual(game.player.offspring[1]["layer"], 2)

    def test_family_child_death_is_synchronized_back_to_genealogy(self):
        created = self.engine.create_game("族谱生灭", "supreme_metal", "dao", 915, preset_id="core")
        game = self.engine.store.load(created["id"])
        child = {"id":"heir_sync","name":"韩宁","age":109,"alive":True,"world":"human","spirit_root":"supreme_metal","cultivation_started":True,"realm_index":1,"layer":1,"lifespan":110,"path":"dao"}
        game.player.offspring = [child]
        game.family = SectState("family_sync","青藤韩家","human",[
            SectNpc("heir_sync","韩宁","嫡系后人",1,1,109,110,spirit_root="supreme_metal")
        ], founded_by_player=True)
        self.engine._annual_offspring_and_family_update(game, random.Random(1))
        self.assertFalse(child["alive"])
        self.assertIn("寿元耗尽", child["death_reason"])

    def test_player_founded_sect_extinguishes_when_last_npc_dies(self):
        created = self.engine.create_game("草创山门", "supreme_metal", "dao", 904, preset_id="core")
        founded = self.engine.create_faction(created["id"], "青竹门")
        game = self.engine.store.load(created["id"])
        sect = game.sects[founded["faction"]["id"]]
        for npc in sect.npcs:
            npc.alive = False
        self.assertTrue(self.engine._check_sect_extinction(game, sect))
        self.assertTrue(sect.extinct)
        self.assertIsNone(game.player.faction_id)

    def test_new_faction_followers_keep_safe_remaining_lifespan(self):
        created = self.engine.create_game("迟暮开宗", "supreme_metal", "dao", 1904)
        game = self.engine.store.load(created["id"])
        game.player.realm_index = 4
        game.player.layer = 1
        game.player.age = 980
        self.engine.store.save(game)
        founded = self.engine.create_faction(created["id"], "长青门")
        game = self.engine.store.load(created["id"])
        followers = game.sects[founded["faction"]["id"]].npcs
        self.assertTrue(followers)
        for npc in followers:
            self.assertEqual(npc.realm_index, 3)
            self.assertIsNotNone(npc.lifespan)
            self.assertGreaterEqual(npc.lifespan - npc.age, int(npc.lifespan * 0.25))

    def test_weak_player_sect_requires_three_failed_defense_events(self):
        created = self.engine.create_game("三守山门", "supreme_metal", "dao", 916, preset_id="core")
        self.engine.create_faction(created["id"], "三守门")
        for expected_failures in range(1, 4):
            game = self.engine.store.load(created["id"])
            game.player.inventory = [item for item in game.player.inventory if item.id != "formation_plate"]
            self.assertTrue(self.engine._maybe_founded_sect_pressure(game, random.Random(1)))
            self.engine.store.save(game)
            shown = self.engine.choose(created["id"], "formation")
            if expected_failures < 3:
                self.assertTrue(shown["faction"]["member"])
                self.assertEqual(shown["faction"]["pressure"], expected_failures)
            else:
                self.assertFalse(shown["faction"]["member"])

    def test_qualified_npc_member_ends_founded_sect_pressure(self):
        created = self.engine.create_game("得贤镇山", "supreme_metal", "dao", 926, preset_id="core")
        founded = self.engine.create_faction(created["id"], "得贤门")
        game = self.engine.store.load(created["id"])
        sect = game.sects[founded["faction"]["id"]]
        sect.pressure = 2
        sect.npcs[0].realm_index = 4
        sect.npcs[0].layer = 1
        sect.npcs[0].world = sect.world
        self.assertFalse(self.engine._maybe_founded_sect_pressure(game, random.Random(1)))
        self.assertEqual(sect.pressure, 0)

    def test_dao_friend_can_interact_join_party_and_survive_crossing(self):
        created = self.engine.create_game("携友飞升", "supreme_metal", "dao", 917, preset_id="core")
        game = self.engine.store.load(created["id"])
        npc = game.world_npcs["xiang_zhili"]
        npc.affinity = 100
        game.rng_state = encode_rng(random.Random(1))
        self.engine.store.save(game)
        shown = self.engine.manage_dao_friend(created["id"], npc.id, "befriend")
        self.assertEqual(shown["dao_friends"][0]["id"], npc.id)
        shown = self.engine.manage_dao_friend(created["id"], npc.id, "spar")
        self.assertGreater(shown["player"]["opportunity"], 0)
        shown = self.engine.manage_party(created["id"], npc.id, "invite")
        self.assertEqual(shown["party"][0]["id"], npc.id)

        game = self.engine.store.load(created["id"])
        game.player.realm_index = 5
        game.player.layer = 1
        game.player.joint_friend_crossing = [{"id": npc.id, "name": npc.name}]
        result, text = self.engine._effect(
            {"type":"enter_spirit_realm"}, game, {"id":"TEST_CROSS"}, random.Random(1)
        )
        self.assertEqual(result, "entered_spirit_realm")
        self.assertEqual(game.player.dao_friends[0]["world"], "spirit")
        self.assertIn("重聚", text)

    def test_non_companion_party_member_can_be_selected_for_spirit_crossing(self):
        created = self.engine.create_game("携队飞升", "supreme_metal", "dao", 918, preset_id="spirit")
        game = self.engine.store.load(created["id"])
        npc = game.world_npcs["xiang_zhili"]
        npc.realm_index, npc.layer, npc.world, npc.affinity = 5, 1, "human", 20
        game.player.party = [{"id":npc.id, "name":npc.name}]
        self.engine.store.save(game)

        selected = self.engine.manage_party(created["id"], npc.id, "crossing_add")
        self.assertTrue(selected["party"][0]["selected_for_crossing"])
        before = selected["party"][0]["affinity"]
        interacted = self.engine.manage_party(created["id"], npc.id, "interact")
        self.assertGreater(interacted["party"][0]["affinity"], before)
        started = self.engine.begin_spirit_crossing(created["id"])
        self.assertEqual(started["pending_event"]["id"], "EVT_SPIRIT_CROSSING_001")
        self.assertEqual(self.engine.store.load(created["id"]).player.joint_friend_crossing[0]["id"], npc.id)

    def test_same_or_lower_realm_only_increases_party_invitation_chance(self):
        created = self.engine.create_game("同行声望", "supreme_metal", "dao", 919, preset_id="nascent")
        game = self.engine.store.load(created["id"])
        npc = game.world_npcs["xiang_zhili"]
        npc.affinity = 0
        npc.realm_index = game.player.realm_index + 1
        harder = self.engine._party_invitation_chance(game.player, npc)
        npc.realm_index = game.player.realm_index
        same = self.engine._party_invitation_chance(game.player, npc)
        npc.realm_index = game.player.realm_index - 1
        lower = self.engine._party_invitation_chance(game.player, npc)
        self.assertGreater(same, harder)
        self.assertGreater(lower, same)

    def test_high_rank_npc_death_probabilities_are_protected(self):
        self.assertEqual(self.engine._npc_lethal_chance("human", 5, "war"), 0.00002)
        self.assertEqual(self.engine._npc_lethal_chance("human", 5, "duel"), 0.00005)
        self.assertEqual(self.engine._npc_lethal_chance("spirit", 8, "war"), 0.0002)
        self.assertEqual(self.engine._npc_lethal_chance("spirit", 8, "duel"), 0.0005)

    def test_world_route_keeps_upper_worlds_above_realms_and_heavens_as_system(self):
        created = self.engine.create_game("诸界层级", "none", "dao", 920, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        route = self.engine.present(game)["world_route"]
        self.assertEqual([stage.get("world") for stage in route["stages"][:3]], ["human", "spirit", "celestial"])
        self.assertEqual(route["stages"][3]["kind"], "system")
        self.assertEqual(route["stages"][3]["system"], "heavens")

    def test_joining_monster_sect_changes_allegiance_not_lineage(self):
        created = self.engine.create_game("人身妖宗", "none", "dao", 921, preset_id="void")
        game = self.engine.store.load(created["id"])
        result, _ = self.engine._effect(
            {"type":"join_faction", "faction_id":"wanlingshan"}, game, {"id":"TEST_JOIN"}, random.Random(1)
        )
        public = self.engine.present(game)
        self.assertEqual(result, "faction_joined")
        self.assertEqual(public["player"]["lineage_race_name"], "人族")
        self.assertEqual(public["player"]["allegiance_race_name"], "妖族")
        self.assertTrue(public["race_system"]["races"]["monster"]["supported_factions"])

    def test_sole_human_mahayana_controls_race_vote(self):
        created = self.engine.create_game("一言定盟", "none", "dao", 905, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        for npc in [*game.world_npcs.values(), *(member for sect in game.sects.values() for member in sect.npcs)]:
            if npc.world == "spirit" and npc.race == "human" and npc.realm_index >= 8:
                npc.alive = False
        self.engine.store.save(game)
        shown = self.engine.propose_race_diplomacy(created["id"], "starborn", "alliance")
        vote = shown["race_system"]["races"]["starborn"]["recent_events"][0]
        self.assertEqual(vote["result"], "passed")

    def test_bounty_can_promote_cached_npc_to_persistent_target(self):
        created = self.engine.create_game("三权追缉", "none", "dao", 906, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        spirit_sect = next(sect for sect in game.sects.values() if sect.world == "spirit")
        game.player.faction_id = spirit_sect.id
        game.player.faction_join_age = game.player.age
        game.family = SectState("family_test", "归元世家", "spirit", [], founded_by_player=True)
        target = {
            "target_name":"池中散修", "target_power":1000.0, "primary_power":1000.0,
            "target_realm_index":6, "target_layer":1, "combat_type":"cultivator",
            "race":"starborn", "world":"spirit",
            "members":[{"name":"池中散修", "power":1000.0, "realm_index":6, "layer":1, "race":"starborn"}],
        }
        self.engine._cache_encounter_target(game, target, random.Random(9))
        npc_id = target["members"][0]["npc_id"]
        self.engine.store.save(game)
        shown = self.engine.issue_bounty(created["id"], npc_id)
        self.assertEqual(shown["governance"]["bounties"][0]["target_id"], npc_id)
        self.assertIn(npc_id, self.engine.store.load(created["id"]).notable_npcs)

    def test_any_single_governing_authority_can_issue_bounty(self):
        created = self.engine.create_game("一权发令", "none", "dao", 907, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        self.assertTrue(self.engine._has_race_voice(game))
        self.assertFalse(self.engine._has_sect_voice(game))
        self.assertFalse(self.engine._has_family_voice(game))
        target = {
            "target_name":"星裔逃犯", "target_power":900.0, "primary_power":900.0,
            "target_realm_index":5, "target_layer":1, "combat_type":"cultivator",
            "race":"starborn", "world":"spirit",
            "members":[{"name":"星裔逃犯", "power":900.0, "realm_index":5, "layer":1, "race":"starborn"}],
        }
        self.engine._cache_encounter_target(game, target, random.Random(11))
        npc_id = target["members"][0]["npc_id"]
        self.engine.store.save(game)
        shown = self.engine.issue_bounty(created["id"], npc_id, "race")
        order = shown["governance"]["bounties"][0]
        self.assertEqual(order["authority"], "race")
        self.assertIn("大乘议会", order["issuer_name"])

    def test_qingyuan_legacy_progresses_through_all_three_realms(self):
        created = self.engine.create_game("青藤传人", "supreme_wood", "dao", 908)
        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 1, 1
        game.pending_event = self.engine._instantiate_event(self.engine.events_by_id["EVT_QINGYUAN_SWORD_LEGACY"], game, random.Random(1))
        self.engine.store.save(game)
        qi = self.engine.choose(created["id"], "study")
        self.assertIn("TECH_QINGYUAN_SWORD", {row["id"] for row in qi["player"]["known_techniques"]})

        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 4, 1
        event = self.engine.events_by_id["EVT_DAGENG_SWORD_ARRAY_INSIGHT"]
        self.assertTrue(self.engine._roll_escalating_event(game, event, MagicMock(random=MagicMock(return_value=0.0))))
        self.engine.store.save(game)
        nascent = self.engine.choose(created["id"], "steady")
        self.assertIn("TECH_DAGENG_SWORD_ARRAY", {row["id"] for row in nascent["player"]["known_techniques"]})

        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer, game.player.world = 7, 1, "spirit"
        event = self.engine.events_by_id["EVT_QINGYUANZI_SWORD_ARRAY"]
        self.assertTrue(self.engine._roll_escalating_event(game, event, MagicMock(random=MagicMock(return_value=0.0))))
        self.engine.store.save(game)
        final = self.engine.choose(created["id"], "observe")
        known = {row["id"] for row in final["player"]["known_techniques"]}
        self.assertTrue({"TECH_QINGPAN_SWORD_ARRAY", "TECH_CHUNLI_SWORD_ARRAY"} <= known)

    def test_new_catalog_content_covers_every_cultivation_tier(self):
        scopes = {item.breakthrough_scope for item in ITEM_CATALOG.values() if item.breakthrough_scope}
        for realm_index in range(1, 8):
            self.assertIn(f"major:{realm_index}", scopes)
        for realm_index in range(2, 9):
            self.assertIn(f"minor:{realm_index}", scopes)
        market_tiers = {int(row["tier"]) for row in MARKET_GOODS}
        technique_grades = {technique.grade for technique in TECHNIQUE_CATALOG.values()}
        self.assertTrue(set(range(1, 9)) <= market_tiers)
        self.assertTrue(set(range(1, 9)) <= technique_grades)
        realm_common = {int(event["conditions"]["value"]) for event in self.engine.events if event["id"].startswith("EVT_REALM_COMMON_")}
        self.assertEqual(realm_common, set(range(9)))

    def test_sect_title_follows_npc_cultivation(self):
        created = self.engine.create_game("职随境转", "supreme_metal", "dao", 920, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "tianjian"
        npc = next(row for row in game.sects["tianjian"].npcs if row.id == "tj_su")
        npc.realm_index, npc.layer = 4, 1
        self.engine.store.save(game)

        shown = self.engine.present(self.engine.store.load(created["id"]))
        row = next(entry for entry in shown["faction"]["roster"] if entry["id"] == npc.id)
        self.assertEqual(row["title"], "元婴长老")

    def test_unaffiliated_friend_can_be_invited_into_player_sect(self):
        created = self.engine.create_game("携友入门", "supreme_metal", "dao", 921, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "tianjian"
        friend = self.engine._generated_relationship(game.player, "friend", random.Random(3))
        game.player.dao_friends.append(friend)
        self.engine.store.save(game)

        shown = self.engine.invite_relationship_to_faction(created["id"], friend["id"])
        member = next(entry for entry in shown["faction"]["roster"] if entry["id"] == friend["id"])
        self.assertEqual(member["faction_id"], "tianjian")
        self.assertFalse(shown["dao_friends"][0]["can_invite_faction"])

    def test_world_npc_party_friend_sect_and_master_chain_uses_one_member_lookup(self):
        created = self.engine.create_game("携友拜师", "supreme_metal", "dao", 1921, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.realm_index, game.player.layer = 4, 3
        self.engine.store.save(game)
        founded = self.engine.create_faction(created["id"], "同游宗")
        game = self.engine.store.load(created["id"])
        npc = SectNpc(
            "world_friend_master", "闻道玄", "游方真人", 5, 2, 960, 2800,
            spirit_root="supreme_water", path="dao", race="human", world="human",
            affinity=100,
        )
        game.notable_npcs[npc.id] = npc
        game.rng_state = encode_rng(random.Random(1))
        self.engine.store.save(game)

        joined = self.engine.manage_party(created["id"], npc.id, "invite")
        self.assertEqual(joined["party"][0]["id"], npc.id)
        self.engine.manage_party(created["id"], npc.id, "interact")
        befriended = self.engine.manage_dao_friend(created["id"], npc.id, "befriend")
        self.assertEqual(befriended["dao_friends"][0]["id"], npc.id)
        invited = self.engine.invite_relationship_to_faction(created["id"], npc.id)
        self.assertIn(npc.id, {row["id"] for row in invited["faction"]["roster"]})
        self.assertEqual(self.engine.store.load(created["id"]).notable_npcs[npc.id].faction_id, founded["faction"]["id"])

        result = self.engine.manage_faction_relationship(created["id"], npc.id, "master")
        self.assertIn(f"master:{npc.id}", self.engine.store.load(created["id"]).player.relationship_attempts)
        self.assertIn(result["history"][0]["result"], {"master_accepted", "rejected"})

    def test_relationship_departures_reset_affinity_but_keep_other_consequences(self):
        created = self.engine.create_game("缘起缘灭", "supreme_metal", "dao", 922, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.dao_companion = self.engine._generated_relationship(game.player, "companion", random.Random(4))
        game.player.master = self.engine._generated_relationship(game.player, "master", random.Random(5))
        companion_id = game.player.dao_companion["id"]
        master_id = game.player.master["id"]
        initial_demon = game.player.heart_demon
        self.engine.store.save(game)

        self.engine.leave_relationship(created["id"], "companion")
        after_companion = self.engine.store.load(created["id"])
        self.assertEqual(after_companion.player.heart_demon, initial_demon + 25)
        self.assertIsNone(after_companion.player.dao_companion)
        self.assertEqual(after_companion.notable_npcs[companion_id].affinity, 0)

        shown = self.engine.leave_relationship(created["id"], "master")
        after_master = self.engine.store.load(created["id"])
        self.assertIsNone(after_master.player.master)
        self.assertEqual(after_master.notable_npcs[master_id].affinity, 0)
        hostile_ids = {entry["id"] for entry in shown["personal_relations"]["low"]}
        self.assertNotIn(master_id, hostile_ids)

    def test_leaving_sect_resets_every_members_affinity(self):
        created = self.engine.create_game("辞山而去", "supreme_metal", "dao", 923, preset_id="core")
        game = self.engine.store.load(created["id"])
        game.player.faction_id = "tianjian"
        for npc in game.sects["tianjian"].npcs:
            npc.affinity = 10
        self.engine.store.save(game)

        shown = self.engine.leave_faction(created["id"])
        saved = self.engine.store.load(created["id"])
        self.assertFalse(shown["faction"]["member"])
        self.assertTrue(all(npc.affinity == 0 for npc in saved.sects["tianjian"].npcs))

    def test_affinity_events_offer_gifts_and_allied_revenge_choices(self):
        created = self.engine.create_game("恩怨有报", "supreme_metal", "dao", 924, preset_id="core")
        game = self.engine.store.load(created["id"])
        ally = game.world_npcs["xiang_zhili"]
        enemy = next(npc for npc in game.world_npcs.values() if npc.id != ally.id and npc.world == game.player.world)
        ally.affinity, enemy.affinity = 90, -80
        roll = MagicMock()
        roll.random.return_value = 0.0
        roll.choices.side_effect = lambda population, **kwargs: [population[0]]

        self.assertTrue(self.engine._maybe_personal_revenge(game, roll))
        choices = {choice["id"]: choice for choice in game.pending_event["choices"]}
        self.assertTrue(choices["ally"]["enabled"])
        self.assertGreater(game.pending_event["runtime"]["protection"], 0)

        game.pending_event = None
        enemy.affinity = 0
        self.assertTrue(self.engine._maybe_affinity_gift(game, roll))
        self.assertEqual(game.pending_event["id"], "EVT_PERSONAL_AFFINITY_GIFT_001")
        self.assertIn(ally.name, game.pending_event["body"])


if __name__ == "__main__":
    unittest.main()
