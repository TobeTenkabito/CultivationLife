import random
import copy
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from cultivation_life.content_registry import (
    CONTENT, CONTENT_DOCUMENTS, GUIXU_EXCLUSIVE_ITEM_IDS,
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS, GUIXU_TIDE_CONTENT, ITEM_CATALOG,
    MARKET_GOODS, TECHNIQUE_CATALOG, WORLD_SYSTEMS, ContentError, ContentRegistry,
    validate_guixu_catalog,
)
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.rules import has_item


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class GuixuTideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def _open_human_dungeon(self, seed=17):
        created = self.engine.create_game("潮生", "supreme_water", "dao", seed, "water")
        game = self.engine.store.load(created["id"])
        dungeon = next(row for row in GUIXU_TIDE_CONTENT["dungeons"] if row["world"] == "human")
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._open_guixu_cycle(game, dungeon, cycle, random.Random(seed))
        game.pending_event = None
        game.player.world = dungeon["world"]
        game.player.location_id = dungeon["entry_location_id"]
        game.player.realm_index = 3
        game.player.layer = 1
        self.engine.store.save(game)
        return created["id"], dungeon

    def test_content_has_six_rich_non_repeating_pools(self):
        manifest = json.loads(
            (SOURCE_ROOT / "dlc" / "guixu-tide" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], "2.1.0")
        dungeons = GUIXU_TIDE_CONTENT["dungeons"]
        self.assertEqual(
            {row["world"] for row in dungeons},
            {"human", "spirit", "demon", "true_demon", "phantom_underworld", "hell"},
        )
        self.assertEqual(
            {row["name"] for row in dungeons},
            {"葬海天渊", "诸界尾闾", "血河沉渊", "太古葬魔墟", "万兽祖涡", "黄泉无底狱"},
        )
        seen = set()
        expected = {
            "technique": 10, "equipment": 12, "consumable": 8,
            "plant": 10, "material": 10, "currency": 10,
        }
        for dungeon in dungeons:
            pool = dungeon["treasure_pool"]
            outside = WORLD_SYSTEMS["world_profiles"][dungeon["world"]]["qi_concentrations"]
            for layer in dungeon["layers"]:
                self.assertEqual(
                    set(layer["qi_concentrations"]),
                    {"spirit", "demon", "monster", "yin"},
                )
                self.assertTrue(all(
                    layer["qi_concentrations"][source] > outside[source]
                    for source in outside
                ))
            self.assertEqual(len(pool), 60)
            self.assertEqual(Counter(row["category"] for row in pool), expected)
            self.assertFalse(seen.intersection(row["id"] for row in pool))
            seen.update(row["id"] for row in pool)
            for row in pool:
                catalog = TECHNIQUE_CATALOG if row["kind"] == "technique" else ITEM_CATALOG
                self.assertIn(row["content_id"], catalog)

    def test_public_panel_only_exposes_the_current_world_dungeon(self):
        created = self.engine.create_game("观潮", "supreme_water", "dao", 19, "water")
        game_id = created["id"]
        human = self.engine.get_game(game_id)["guixu_tide"]
        self.assertTrue(human["available"])
        self.assertEqual([row["world"] for row in human["dungeons"]], ["human"])

        game = self.engine.store.load(game_id)
        game.player.world = "spirit"
        self.engine.store.save(game)
        spirit = self.engine.get_game(game_id)["guixu_tide"]
        self.assertEqual([row["world"] for row in spirit["dungeons"]], ["spirit"])

        for world in ("demon", "true_demon", "phantom_underworld", "hell"):
            game = self.engine.store.load(game_id)
            game.player.world = world
            game.player.location_id = self.engine.maps.default_location(world)
            self.engine.store.save(game)
            shown = self.engine.get_game(game_id)["guixu_tide"]
            self.assertEqual([row["world"] for row in shown["dungeons"]], [world])

        game = self.engine.store.load(game_id)
        game.player.world = "celestial"
        self.engine.store.save(game)
        celestial = self.engine.get_game(game_id)["guixu_tide"]
        self.assertFalse(celestial["available"])
        self.assertEqual(celestial["dungeons"], [])

    def test_dlc_loads_with_only_base_content_and_uses_base_map_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            extension_root = Path(directory)
            package_root = extension_root / "dlc" / "guixu-tide"
            shutil.copytree(SOURCE_ROOT / "dlc" / "guixu-tide", package_root)
            ContentRegistry.load(SOURCE_ROOT / "content", extension_root)

        report = {row["id"]: row for row in ContentRegistry.extension_report}
        self.assertEqual(report["official.guixu-tide"]["status"], "loaded")
        dungeons = ContentRegistry.loaded_documents["guixu_tide.json"]["dungeons"]
        entry_pairs = {(row["world"], row["entry_location_id"]) for row in dungeons}
        self.assertIn(("phantom_underworld", "phantom_tide"), entry_pairs)
        self.assertIn(("hell", "ninefold_prison"), entry_pairs)

    def test_popup_setting_keeps_cycles_running_without_blocking_event(self):
        created = self.engine.create_game("静潮", "supreme_water", "dao", 20, "water")
        game_id = created["id"]
        game = self.engine.store.load(game_id)
        dungeon = next(row for row in GUIXU_TIDE_CONTENT["dungeons"] if row["world"] == "human")
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        cycle["next_announce_age"] = game.player.age
        cycle["next_open_age"] = game.player.age + dungeon["announce_lead_years"]
        game.settings["guixu_event_popup"] = False
        requires_input = self.engine._advance_guixu_calendar(game, random.Random(20), [])
        self.assertFalse(requires_input)
        self.assertIsNone(game.pending_event)
        self.assertEqual(cycle["phase"], "announced")
        self.assertTrue(any(row.event_id == "SYS_GUIXU_ANNOUNCE" for row in game.history))

        game.settings["guixu_event_popup"] = True
        cycle["phase"] = "closed"
        self.engine._announce_guixu_cycle(game, dungeon, cycle, random.Random(21))
        self.assertEqual(game.pending_event["id"], "EVT_GUIXU_ANNOUNCE")
        self.engine.store.save(game)
        changed = self.engine.update_setting(game_id, "guixu_event_popup", False)
        self.assertIsNone(changed["pending_event"])

    def test_guixu_treasures_are_excluded_from_every_generic_acquisition_pool(self):
        market_ids = {str(row["content_id"]) for row in MARKET_GOODS}
        self.assertFalse(market_ids & GUIXU_EXCLUSIVE_ITEM_IDS)
        self.assertFalse(market_ids & GUIXU_EXCLUSIVE_TECHNIQUE_IDS)

        created = self.engine.create_game("守池", "supreme_metal", "dao", 13, "metal")
        game = self.engine.store.load(created["id"])
        npc = SectNpc(
            "pool-audit", "守池人", "", 8, 9, 1000, None,
            spirit_root="supreme_metal", path="dao", world="spirit",
        )
        npc_technique = self.engine._default_npc_main_technique(npc)
        self.assertNotIn(npc_technique, GUIXU_EXCLUSIVE_TECHNIQUE_IDS)
        self.assertFalse(
            set(self.engine._owner_technique_candidates(game.player, npc))
            & GUIXU_EXCLUSIVE_TECHNIQUE_IDS
        )
        alchemy_ids = {
            row["id"] for row in self.engine._public_spirit_field(game.player)["alchemy"]["targets"]
        }
        self.assertFalse(alchemy_ids & GUIXU_EXCLUSIVE_ITEM_IDS)

    def test_guixu_validator_rejects_any_declarative_side_channel(self):
        documents = copy.deepcopy(CONTENT_DOCUMENTS)
        leaked_id = next(iter(GUIXU_EXCLUSIVE_ITEM_IDS))
        documents["illegal_events.json"] = {
            "schema_version": 1,
            "events": [{"id": "LEAK", "choices": [{"effects": [{"item_id": leaked_id}]}]}],
        }
        with self.assertRaisesRegex(ContentError, "不得被其他内容表引用"):
            validate_guixu_catalog(GUIXU_TIDE_CONTENT, CONTENT, documents)

    def test_enter_search_and_close_permanently_depletes_pool(self):
        game_id, dungeon = self._open_human_dungeon()
        entered = self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        self.assertEqual(entered["guixu_tide"]["session"]["remaining_days"], dungeon["window_days"] - 1)

        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        target = cycle["round_entries"][0]
        for row in cycle["round_entries"][1:]:
            row["layer_id"] = "middle"
        target["layer_id"] = "outer"
        target["claim_at_day"] = dungeon["window_days"] - 2
        target_id = target["pool_entry_id"]
        self.engine.store.save(game)

        searched = self.engine.guixu_action(game_id, "search", {})
        self.assertEqual(searched["history"][0]["event_id"], "SYS_GUIXU_SEARCH")
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        target = next(row for row in cycle["round_entries"] if row["pool_entry_id"] == target_id)
        self.assertEqual(target["resolution"], "player")
        self.assertNotIn(target_id, cycle["pool_remaining"])

        self.engine._close_guixu_cycle(game, dungeon, cycle, random.Random(99))
        self.assertEqual(cycle["phase"], "closed")
        self.assertIn(
            self.engine._guixu_entry_definition(dungeon, target_id)["name"],
            cycle["last_report"]["player"],
        )
        self.assertNotIn(target_id, cycle["pool_remaining"])

    def test_failed_return_traps_player_until_next_cycle(self):
        game_id, dungeon = self._open_human_dungeon(seed=23)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        session = game.guixu_state["player_session"]
        session["layer_id"] = "inner"
        session["remaining_days"] = 2
        self.engine.store.save(game)

        trapped = self.engine.guixu_action(game_id, "return", {})
        self.assertTrue(trapped["guixu_tide"]["session"]["trapped"])
        self.assertEqual(trapped["guixu_tide"]["session"]["actors"], [])
        self.assertEqual(trapped["guixu_tide"]["session"]["treasures"], [])
        self.engine.assert_guixu_operation_allowed(game_id, "advance")
        with self.assertRaisesRegex(ValueError, "外界操作"):
            self.engine.assert_guixu_operation_allowed(game_id, "map-travel")

        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.assertEqual(cycle["roster"], [])
        self.engine._announce_guixu_cycle(game, dungeon, cycle, random.Random(24))
        game.pending_event = None
        self.engine._open_guixu_cycle(game, dungeon, cycle, random.Random(25))
        self.assertFalse(game.guixu_state["player_session"]["trapped"])
        self.assertEqual(game.guixu_state["player_session"]["remaining_days"], dungeon["window_days"])

    def test_guixu_rest_restores_resources_and_costs_expedition_time(self):
        game_id, dungeon = self._open_human_dungeon(seed=27)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        game.player.hp = 1
        game.player.mp = 1
        before_days = game.guixu_state["player_session"]["remaining_days"]
        self.engine.store.save(game)

        rested = self.engine.guixu_action(game_id, "rest", {})
        self.assertGreater(rested["player"]["hp"], 1)
        self.assertGreater(rested["player"]["mp"], 1)
        self.assertEqual(
            rested["guixu_tide"]["session"]["remaining_days"],
            before_days - GUIXU_TIDE_CONTENT["settings"]["action_days"]["rest"],
        )
        self.assertEqual(rested["history"][0]["event_id"], "SYS_GUIXU_REST")

    def test_trapped_main_training_reuses_body_and_sense_progression(self):
        game_id, dungeon = self._open_human_dungeon(seed=29)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        game.guixu_state["player_session"]["remaining_days"] = 0
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._close_guixu_cycle(game, dungeon, cycle, random.Random(29))
        game.player.body_technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BODY_MORTAL"])
        game.player.divine_sense_technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_SPIRIT_SENSE"])
        self.engine.store.save(game)

        body = self.engine.advance(game_id, "body_train")
        self.assertGreater(body["body_cultivation"]["progress"], 0)
        sense = self.engine.advance(game_id, "sense_train")
        self.assertGreater(sense["player"]["divine_sense"]["experience"], 0)
        self.assertTrue(sense["guixu_tide"]["session"]["trapped"])

        game = self.engine.store.load(game_id)
        game.player.hp = 1
        game.player.mp = 1
        game.player.cultivation_suppression = {
            "realm_index": game.player.realm_index,
            "layer": game.player.layer,
            "opportunity": game.player.opportunity,
            "awaiting_ascension": False,
            "awaiting_major_breakthrough": False,
            "awaiting_minor_breakthrough": False,
            "awaiting_spirit_realm_crossing": False,
            "active_breakthrough_aids": [],
            "tribulation_remaining": None,
        }
        age = game.player.age
        self.engine.store.save(game)

        cultivated = self.engine.advance(game_id, "cultivate")
        self.assertGreater(cultivated["player"]["age"], age)
        rested = self.engine.advance(game_id, "rest")
        self.assertGreater(rested["player"]["hp"], 1)
        self.assertGreater(rested["player"]["mp"], 1)
        self.assertTrue(rested["guixu_tide"]["session"]["trapped"])
        with self.assertRaisesRegex(ValueError, "只能修炼"):
            self.engine.advance(game_id, "befriend_neighbors")

    def test_active_layer_replaces_sidebar_qi_environment(self):
        game_id, dungeon = self._open_human_dungeon(seed=30)
        shown = self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        outer = next(layer for layer in dungeon["layers"] if layer["id"] == "outer")
        self.assertEqual(
            shown["player"]["qi_environment"]["concentrations"],
            outer["qi_concentrations"],
        )
        self.assertEqual(
            shown["player"]["qi_gain_efficiencies"],
            outer["qi_gain_efficiencies"],
        )

    def test_trapped_training_buttons_advance_time_without_specialized_techniques(self):
        game_id, dungeon = self._open_human_dungeon(seed=32)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        game.guixu_state["player_session"]["remaining_days"] = 0
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._close_guixu_cycle(game, dungeon, cycle, random.Random(32))
        game.player.body_technique = None
        game.player.divine_sense_technique = None
        age = game.player.age
        self.engine.store.save(game)

        body = self.engine.advance(game_id, "body_train")
        self.assertGreater(body["player"]["age"], age)
        sense = self.engine.advance(game_id, "sense_train")
        self.assertGreater(sense["player"]["age"], body["player"]["age"])
        self.assertTrue(sense["guixu_tide"]["session"]["trapped"])

    def test_guixu_combat_uses_cramped_pursuit_rules(self):
        game_id, dungeon = self._open_human_dungeon(seed=33)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        actor = next(row for row in cycle["roster"] if row["layer_id"] == "outer")
        with patch.object(self.engine, "_combat", return_value=("victory_escape", "test")) as combat:
            self.engine._guixu_fight(
                game, dungeon, cycle, game.guixu_state["player_session"], actor,
                random.Random(33),
            )
        target = combat.call_args.args[1]
        settings = GUIXU_TIDE_CONTENT["settings"]
        self.assertEqual(target["natural_terrain"], "狭窄")
        self.assertEqual(target["kill_pursuit_threshold"], settings["combat_kill_pursuit_threshold"])
        self.assertEqual(target["pursuit_chance_bonus"], settings["combat_pursuit_chance_bonus"])
        self.assertLess(settings["flee_base_chance"], .48)

    def test_npc_team_breaks_immediately_when_a_member_claims_treasure(self):
        game_id, dungeon = self._open_human_dungeon(seed=34)
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        team = next(row for row in cycle["npc_teams"] if row["status"] == "active")
        member = next(
            actor for actor in cycle["roster"] if actor["actor_id"] in team["member_ids"]
        )
        treasure = cycle["round_entries"][0]

        self.engine._guixu_npc_claim_entry(
            game, dungeon, cycle, treasure, member, "test",
        )

        self.assertEqual(treasure["holder_id"], member["actor_id"])
        self.assertEqual(treasure["resolution"], "held")
        self.assertEqual(team["status"], "dissolved")
        self.assertFalse(any(
            actor.get("team_id") == team["id"] for actor in cycle["roster"]
        ))
        self.assertTrue(any(
            row.event_id == "SYS_GUIXU_NPC_TEAM_BREAK" for row in game.history
        ))

    def test_npc_kill_transfers_treasure_and_persists_fixed_npc_death(self):
        game_id, dungeon = self._open_human_dungeon(seed=35)
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        victim = next(actor for actor in cycle["roster"] if actor["actor_kind"] == "fixed")
        killer = next(
            actor for actor in cycle["roster"]
            if actor["actor_id"] != victim["actor_id"] and actor["status"] == "active"
        )
        treasure = cycle["round_entries"][0]
        treasure["holder_id"] = victim["actor_id"]
        treasure["resolution"] = "held"

        self.engine._resolve_guixu_npc_kill(
            game, dungeon, cycle, killer, victim, 7,
        )

        self.assertEqual(victim["status"], "dead")
        self.assertEqual(treasure["holder_id"], killer["actor_id"])
        self.assertEqual(treasure["npc_claim_source"], "npc_kill")
        fixed_npc = self.engine._find_npc(game, victim["npc_id"])
        self.assertFalse(fixed_npc.alive)
        self.assertIn(dungeon["name"], fixed_npc.death_reason)
        self.assertEqual(cycle["npc_incidents"][-1]["transferred"], [
            self.engine._guixu_entry_definition(dungeon, treasure["pool_entry_id"])["name"],
        ])

    def test_npc_threat_uses_visible_suppressed_rank_and_can_take_treasure(self):
        game_id, dungeon = self._open_human_dungeon(seed=36)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        session = game.guixu_state["player_session"]
        actor = next(row for row in cycle["roster"] if row["layer_id"] == "outer")
        for other in cycle["roster"]:
            if other is not actor:
                other["status"] = "dead"
        actor["realm_index"], actor["layer"] = 3, 5
        physical = next(
            row for row in cycle["round_entries"]
            if self.engine._guixu_entry_definition(dungeon, row["pool_entry_id"])["kind"] == "item"
        )
        self.engine._guixu_grant_entry(game, dungeon, physical, "test")
        definition = self.engine._guixu_entry_definition(dungeon, physical["pool_entry_id"])
        game.player.cultivation_suppression = {"realm_index": 8, "layer": 9}
        settings = {**GUIXU_TIDE_CONTENT["settings"], "npc_threat_chance_per_action": 1.0}

        game.player.realm_index, game.player.layer = 4, 1
        with patch.object(self.engine, "_guixu_settings", return_value=settings):
            self.engine._maybe_guixu_npc_threat(
                game, dungeon, cycle, session, random.Random(36),
            )
        self.assertIsNone(session["pending_threat"])

        game.player.realm_index, game.player.layer = 2, 1
        with patch.object(self.engine, "_guixu_settings", return_value=settings):
            self.engine._maybe_guixu_npc_threat(
                game, dungeon, cycle, session, random.Random(37),
            )
        self.assertEqual(session["pending_threat"]["actor_id"], actor["actor_id"])
        self.assertEqual(session["pending_threat"]["player_visible_realm_index"], 2)
        self.assertEqual(game.player.cultivation_suppression["realm_index"], 8)
        self.engine.store.save(game)
        shown_threat = self.engine.get_game(game_id)["guixu_tide"]["session"]["pending_threat"]
        self.assertTrue(shown_threat["actor_realm_name"])
        self.assertTrue(shown_threat["player_visible_realm_name"])
        with self.assertRaisesRegex(ValueError, "必须先回应"):
            self.engine.guixu_action(game_id, "rest", {})

        surrendered = self.engine.guixu_action(game_id, "threat_surrender", {})
        self.assertIsNone(surrendered["guixu_tide"]["session"]["pending_threat"])
        game = self.engine.store.load(game_id)
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        physical = next(
            row for row in cycle["round_entries"]
            if row["pool_entry_id"] == physical["pool_entry_id"]
        )
        self.assertEqual(physical["holder_id"], actor["actor_id"])
        self.assertEqual(physical["resolution"], "held")
        self.assertNotIn(physical["pool_entry_id"], game.guixu_state["player_session"]["carried_entry_ids"])
        self.assertFalse(has_item(game.player, definition["content_id"], int(definition.get("quantity", 1))))

    def test_state_round_trips_in_save_file(self):
        game_id, dungeon = self._open_human_dungeon(seed=31)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        loaded = self.engine.store.load(game_id)
        self.assertEqual(loaded.guixu_state["player_session"]["dungeon_id"], dungeon["id"])
        self.assertEqual(len(loaded.guixu_state["cycles"][dungeon["id"]]["round_entries"]), 6)

    def test_one_pending_notice_does_not_delay_another_due_dungeon(self):
        created = self.engine.create_game("并潮", "supreme_water", "dao", 41, "water")
        game = self.engine.store.load(created["id"])
        for cycle in game.guixu_state["cycles"].values():
            cycle["next_announce_age"] = game.player.age
            cycle["next_open_age"] = game.player.age
        needs_input = self.engine._advance_guixu_calendar(game, random.Random(41), [])
        self.assertTrue(needs_input)
        self.assertTrue(game.pending_event["id"].startswith("EVT_GUIXU_"))
        self.assertTrue(all(
            cycle["phase"] == "open" for cycle in game.guixu_state["cycles"].values()
        ))

    def test_disabling_dlc_allows_safe_ejection_before_external_action(self):
        game_id, dungeon = self._open_human_dungeon(seed=37)
        self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        with patch.dict(GUIXU_TIDE_CONTENT, {"dungeons": []}):
            self.engine.assert_guixu_operation_allowed(game_id, "advance")
            loaded = self.engine._load(game_id)
        self.assertIsNone(loaded.guixu_state["player_session"])
        self.assertEqual(loaded.player.location_id, dungeon["entry_location_id"])
        self.assertTrue(any(row.event_id == "SYS_GUIXU_DISABLED_EJECT" for row in loaded.history))

    def test_suppression_grants_entry_but_concealment_does_not_and_release_ejects(self):
        created = self.engine.create_game("藏境入墟", "supreme_water", "dao", 47, "water")
        game_id = created["id"]
        game = self.engine.store.load(game_id)
        dungeon = next(row for row in GUIXU_TIDE_CONTENT["dungeons"] if row["world"] == "spirit")
        cycle = game.guixu_state["cycles"][dungeon["id"]]
        self.engine._open_guixu_cycle(game, dungeon, cycle, random.Random(47))
        game.pending_event = None
        game.player.world = dungeon["world"]
        game.player.location_id = dungeon["entry_location_id"]
        game.player.realm_index, game.player.layer = dungeon["eject_rank"]
        self.engine.store.save(game)

        concealed = self.engine.manage_secret_art(
            game_id, "conceal", "activate", *dungeon["max_entry_rank"],
        )
        public_dungeon = next(
            row for row in concealed["guixu_tide"]["dungeons"] if row["id"] == dungeon["id"]
        )
        self.assertFalse(public_dungeon["can_enter"])
        self.assertFalse(public_dungeon["entry_requirements"]["rank_matches"])
        self.assertFalse(public_dungeon["entry_requirements"]["suppression_active"])
        self.assertTrue(public_dungeon["entry_requirements"]["max_rank_name"])
        self.engine.manage_secret_art(game_id, "conceal", "cancel")

        suppressed = self.engine.manage_secret_art(
            game_id, "suppress", "activate", *dungeon["max_entry_rank"],
        )
        public_dungeon = next(
            row for row in suppressed["guixu_tide"]["dungeons"] if row["id"] == dungeon["id"]
        )
        self.assertTrue(public_dungeon["can_enter"])
        self.assertTrue(public_dungeon["entry_requirements"]["rank_matches"])
        self.assertTrue(public_dungeon["entry_requirements"]["suppression_active"])
        entered = self.engine.guixu_action(game_id, "enter", {"dungeon_id": dungeon["id"]})
        self.assertIsNotNone(entered["guixu_tide"]["session"])

        released = self.engine.manage_secret_art(game_id, "suppress", "cancel")
        self.assertIsNone(released["guixu_tide"]["session"])
        self.assertEqual(released["player"]["location_id"], dungeon["entry_location_id"])
        self.assertEqual(released["history"][0]["event_id"], "SYS_SECRET_ART")
        self.assertEqual(released["history"][1]["event_id"], "SYS_GUIXU_EJECT")


if __name__ == "__main__":
    unittest.main()
