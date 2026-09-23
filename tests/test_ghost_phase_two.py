import copy
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.system.combat_system import BattleUnit, PlayerCombatSystem
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.system.ghost_system import (
    SOUL_SLOTS, active_generated_soul_traits, apply_soul_erosion, ensure_ghost_cultivation_state,
    ghost_opportunity_multiplier, ghost_soul_effects, ghost_soul_pressure,
)
from cultivation_life.ghost_soul_traits import (
    describe_generated_soul_trait, generated_soul_trait_id, validate_generated_soul_trait,
)
from cultivation_life.models import Item, Player
from cultivation_life.system.possession_system import (
    advance_player_age, can_possess, current_body_age, enter_host_body, is_possessed,
    leave_host_body, migrate_possession_timeline, possession_limit,
)
from cultivation_life.rules import combat_power
from cultivation_life.version import BASE_GAME_VERSION


class GhostPhaseTwoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def _game(self):
        created = self.engine.create_game("照夜", "mutated_yin", "ghost", seed=731)
        return self.engine.store.load(created["id"])

    @staticmethod
    def _soul(soul_id="soul-a", power=4200, pressure=2.0):
        return {
            "id": soul_id, "npc_id": f"npc-{soul_id}", "name": "顾忘川", "path": "ghost",
            "race": "human", "realm_index": 3, "layer": 4, "combat_power": power,
            "affinity": 0, "defeated": True, "is_bound_soul": True,
            "soul_pressure": pressure,
            "soul_trait": {"name": "宿慧", "description": "前尘未泯", "stat": "opportunity"},
        }

    def test_release_versions_and_phase_two_config(self):
        self.assertEqual(BASE_GAME_VERSION, "1.26.0")
        manifest = (Path(__file__).parents[1] / "dlc/ghost-reincarnation/manifest.json").read_text("utf-8")
        self.assertIn('"version": "3.6.0"', manifest)

    def test_ten_fixed_slots_saturate_and_pressure_only_changes_future_growth(self):
        player = Player("魂主", "mutated_yin", path="ghost", realm_index=3, layer=2)
        ensure_ghost_cultivation_state(player)
        player.ghost_bound_souls = [self._soul()]
        player.ghost_soul_slots = {"胎光": "soul-a"}
        self.assertEqual(len(SOUL_SLOTS), 10)
        self.assertGreater(ghost_soul_effects(player)["opportunity"], 0)
        self.assertLess(ghost_soul_effects(player)["opportunity"], 0.34)
        self.assertGreater(ghost_opportunity_multiplier(player), 1)
        self.assertEqual(ghost_soul_pressure(player), (2.0, 0.02))
        hp_before = player.ghost_intrinsic_hp_current
        result = apply_soul_erosion(player, 1)
        self.assertEqual(player.ghost_intrinsic_hp_current, hp_before)
        self.assertAlmostEqual(result["rate_pp"], 0.0002 * 1.02)

    def test_three_souls_are_uncapped_while_seven_souls_keep_their_hard_cap(self):
        player = Player("魂主", "mutated_yin", path="ghost", realm_index=3, layer=2)
        ensure_ghost_cultivation_state(player)
        player.ghost_bound_souls = [self._soul(power=10**12)]
        player.ghost_soul_slots = {"胎光": "soul-a"}
        three_soul_gain = ghost_soul_effects(player)["opportunity"]
        self.assertGreater(three_soul_gain, 0.25)

        player.ghost_soul_slots = {"伏矢": "soul-a"}
        seven_soul_gain = ghost_soul_effects(player)["might"]
        self.assertGreater(seven_soul_gain, 0)
        self.assertLessEqual(seven_soul_gain, 0.25)
        self.assertEqual(ghost_soul_effects(player)["opportunity"], 0)
        self.assertAlmostEqual(ghost_opportunity_multiplier(player), 1.08)

    def test_seven_souls_feed_distinct_combat_rules_instead_of_average_power(self):
        player = Player("七魄", "mutated_yin", path="ghost", realm_index=3, layer=4)
        ensure_ghost_cultivation_state(player)
        player.ghost_bound_souls = [self._soul(power=10**9)]
        base_power = combat_power(player)
        unit = BattleUnit("player", player.name, "player", base_power, player.realm_index, player.path)
        player.ghost_soul_slots = {}
        base_stats = PlayerCombatSystem._aggregate_stats([unit], player=player, terrain_tags=["开阔"])
        stat_by_slot = {}
        for slot, stat in (("尸狗", "mobility"), ("伏矢", "might"), ("吞贼", "guard"),
                           ("非毒", "sense"), ("除秽", "breach"), ("臭肺", "sustain")):
            player.ghost_soul_slots = {slot: "soul-a"}
            self.assertEqual(combat_power(player), base_power)
            stats = PlayerCombatSystem._aggregate_stats([unit], player=player, terrain_tags=["开阔"])
            stat_by_slot[slot] = stats
            self.assertGreater(stats[stat], base_stats[stat])
        self.assertGreater(stat_by_slot["伏矢"]["might"], stat_by_slot["尸狗"]["might"])
        self.assertGreater(stat_by_slot["尸狗"]["mobility"], stat_by_slot["伏矢"]["mobility"])
        self.assertGreater(stat_by_slot["臭肺"]["sustain"], stat_by_slot["吞贼"]["sustain"])

        target = {
            "target_name": "试魂傀", "target_power": base_power * 1.15,
            "target_realm_index": 3, "target_layer": 4, "combat_type": "cultivator",
            "path": "dao", "max_rounds": 5,
        }
        player.ghost_soul_slots = {"雀阴": "soul-a"}
        resolved = PlayerCombatSystem.resolve(
            player, [unit], target, True, random.Random(44),
            current_hp_ratio=1.0, current_mp_ratio=1.0, battlefield_tags=["开阔"],
        )
        player.ghost_soul_slots = {}
        baseline = PlayerCombatSystem.resolve(
            player, [unit], target, True, random.Random(44),
            current_hp_ratio=1.0, current_mp_ratio=1.0, battlefield_tags=["开阔"],
        )
        self.assertGreaterEqual(resolved.player_morale, baseline.player_morale)

    def test_souls_can_be_swapped_while_an_event_is_pending(self):
        game = self._game()
        game.player.ghost_bound_souls = [self._soul()]
        game.pending_event = {"id": "TEST", "title": "战中", "body": "", "choices": []}
        self.engine.store.save(game)
        result = self.engine.ghost_soul_action(game.id, "soul-a", "equip", "伏矢")
        self.assertEqual(result["ghost_system"]["phase_two"]["slots"][4]["soul_id"], "soul-a")

    def test_attachment_keeps_free_control_and_changes_only_growth_and_efficiency(self):
        game = self._game()
        game.player.inventory.append(Item("test_sword", "照魂剑", combat_bonus=600))
        self.engine.store.save(game)
        attached = self.engine.ghost_attachment_action(game.id, "attach", "test_sword")
        state = attached["ghost_system"]["phase_two"]
        self.assertEqual(state["state"], "attached")
        self.assertLess(state["attachment"]["erosion_growth_multiplier"], 1)
        self.assertLess(state["attachment"]["cultivation_efficiency_multiplier"], 1)
        left = self.engine.ghost_attachment_action(game.id, "leave")
        self.assertEqual(left["ghost_system"]["phase_two"]["state"], "free")

    def test_possession_freezes_core_and_active_souls_then_restores_exact_core(self):
        player = Player("无常", "mutated_yin", path="ghost", realm_index=4, layer=5, opportunity=321)
        ensure_ghost_cultivation_state(player)
        player.ghost_wangsheng_energy = 9
        player.ghost_reincarnation_imprints = {"3": 7}
        player.ghost_bound_souls = [self._soul()]
        player.ghost_soul_slots = {"伏矢": "soul-a"}
        rate = player.ghost_soul_erosion_rate_pp = 0.25
        target = {"id": "host-a", "name": "沈青", "race": "human", "path": "dao", "spirit_root": "supreme_metal", "realm_index": 3, "layer": 2, "age": 214, "lifespan": 730, "combat_power": 2000}
        original_age = player.age
        allowed, _ = can_possess(player, target)
        self.assertTrue(allowed)
        enter_host_body(player, target)
        self.assertTrue(is_possessed(player))
        self.assertEqual(player.name, "沈青（无常）")
        self.assertEqual((player.age, current_body_age(player), player.lifespan), (original_age, 214, 730))
        self.assertEqual(ghost_soul_effects(player)["might"], 0)
        self.assertFalse(apply_soul_erosion(player, 50)["active"])
        self.assertEqual(player.ghost_soul_erosion_rate_pp, rate)
        self.assertEqual(player.ghost_wangsheng_energy, 9)
        player.opportunity = 9999
        advance_player_age(player, 10)
        leave_host_body(player)
        self.assertEqual((player.name, player.path, player.realm_index, player.layer, player.opportunity), ("无常", "ghost", 4, 5, 321))
        self.assertEqual(player.age, original_age + 10)
        self.assertEqual(player.possession_count, 1)
        self.assertEqual(player.ghost_reincarnation_imprints, {"3": 7})

    def test_default_possession_limit_and_body_death_returns_to_core(self):
        game = self._game()
        target = {"id": "host-b", "name": "陆归尘", "race": "human", "path": "dao", "spirit_root": "supreme_wood", "realm_index": 0, "layer": 1, "combat_power": 1}
        self.assertEqual(possession_limit(game.player), 1)
        enter_host_body(game.player, target)
        self.engine._die(game, "宿主寿尽", "SYS_LIFESPAN")
        self.assertTrue(game.player.alive)
        self.assertEqual(game.player.path, "ghost")
        self.assertFalse(is_possessed(game.player))
        self.assertEqual(game.player.possession_count, 1)
        allowed, reason = can_possess(game.player, target)
        self.assertFalse(allowed)
        self.assertIn("最多", reason)

    def test_advanced_techniques_extend_or_remove_possession_limit(self):
        player = Player("夺形", "mutated_yin", path="ghost", possession_count=1)
        player.known_techniques = [copy.deepcopy(TECHNIQUE_CATALOG["TECH_GHOST_BODY_THIEF"])]
        self.assertEqual(possession_limit(player), 2)
        player.known_techniques.append(copy.deepcopy(TECHNIQUE_CATALOG["TECH_GHOST_TEN_THOUSAND_HOSTS"]))
        self.assertIsNone(possession_limit(player))

    def test_controlled_ghost_cannot_use_free_actions_or_travel(self):
        game = self._game()
        game.player.ghost_captor = {"id": "c", "name": "拘魂者", "combat_power": combat_power(game.player) * 2, "location_id": game.player.location_id}
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "魂印受制"):
            self.engine.advance(game.id, "treasure")
        destination = next(row["id"] for row in self.engine.present(game)["map"]["locations"] if not row["current"])
        with self.assertRaisesRegex(ValueError, "拘魂者"):
            self.engine.travel_map(game.id, destination)

    def test_parade_announcement_marker_and_real_souls(self):
        game = self._game()
        game.ghost_parade["start_age"] = game.player.age + 1
        game.ghost_parade["end_age"] = game.player.age + 100
        rng = __import__("random").Random(4)
        game.player.age += 1
        self.engine._advance_ghost_phase_two_year(game, rng)
        self.assertEqual(game.ghost_parade["status"], "active")
        self.assertTrue(game.ghost_parade["souls"])
        self.assertTrue(all("soul_trait" in row and "soul_pressure" in row for row in game.ghost_parade["souls"]))
        traits = [row["soul_trait"] for row in game.ghost_parade["souls"]]
        self.assertTrue(all(trait.get("generated") and trait.get("origin") == "ghost_parade" for trait in traits))
        self.assertTrue(all(not validate_generated_soul_trait(trait) for trait in traits))
        self.assertGreaterEqual(len({trait["id"] for trait in traits}), 2)
        public = self.engine.present(game)
        marker = next(row for row in public["map"]["locations"] if row["id"] == game.ghost_parade["location_id"])
        self.assertEqual(marker["ghost_parade"]["status"], "active")

    def test_parade_trait_combinations_are_deterministic_and_persist_in_the_soul(self):
        game = self._game()
        first = self.engine._generate_parade_souls(game, random.Random(991))
        repeated = self.engine._generate_parade_souls(game, random.Random(991))
        self.assertEqual(first, repeated)
        trait = copy.deepcopy(first[0]["soul_trait"])
        self.assertEqual(
            set(("prefix", "trigger", "schedule", "conditions", "effect")) - set(trait),
            set(),
        )
        first[0].update(defeated=True, is_bound_soul=True)
        game.player.ghost_bound_souls = [first[0]]
        game.player.ghost_soul_slots = {"伏矢": first[0]["id"]}
        self.engine.store.save(game)
        loaded = self.engine.store.load(game.id)
        self.assertEqual(loaded.player.ghost_bound_souls[0]["soul_trait"], trait)
        self.assertEqual(active_generated_soul_traits(loaded.player), [trait])

    def test_generated_soul_trait_enters_round_combat_resolution(self):
        game = self._game()
        bare = {
            "schema_version": 1, "prefix": "守烛", "trigger": "round_start",
            "schedule": "odd", "conditions": ["enemy_same_or_lower"], "effect": "might_05",
        }
        trait = {
            **bare, "id": generated_soul_trait_id(bare), "name": "守烛·振威",
            "description": describe_generated_soul_trait(bare), "generated": True,
            "origin": "ghost_parade", "power": {"raw": 5.0},
        }
        self.assertEqual(validate_generated_soul_trait(trait), [])
        soul = self._soul()
        soul["soul_trait"] = trait
        game.player.ghost_bound_souls = [soul]
        game.player.ghost_soul_slots = {"伏矢": soul["id"]}
        power = combat_power(game.player)
        unit = BattleUnit("player", game.player.name, "player", power, game.player.realm_index, game.player.path)
        report = PlayerCombatSystem.resolve(
            game.player, [unit], {
                "target_name": "照魂傀", "target_power": power,
                "target_realm_index": game.player.realm_index, "target_layer": game.player.layer,
                "combat_type": "cultivator", "path": "dao", "max_rounds": 3,
            }, True, random.Random(52), current_hp_ratio=1.0, current_mp_ratio=1.0,
            battlefield_tags=["开阔"],
        )
        combat_text = "\n".join([
            *report.key_events,
            *(event for battle_round in report.rounds for event in battle_round["events"]),
        ])
        self.assertIn("百鬼夜行复合魂性", combat_text)
        self.assertIn("魂性共鸣【守烛·振威", combat_text)

    def test_each_parade_soul_can_only_be_befriended_once(self):
        game = self._game()
        soul = self._soul()
        soul.update(defeated=False, is_bound_soul=False, befriended=False, personality="温和")
        game.ghost_parade = {
            "status": "active", "world": game.player.world,
            "location_id": game.player.location_id, "announced": True,
            "participated": False, "souls": [soul],
            "start_age": game.player.age, "end_age": game.player.age + 100,
        }
        game.player.ghost_soul_erosion_rate_pp = 1.0
        self.engine.store.save(game)
        first = self.engine.ghost_parade_action(game.id, "soul-a", "befriend")
        befriended = first["ghost_system"]["phase_two"]["parade"]["souls"][0]
        self.assertTrue(befriended["befriended"])
        affinity = befriended["affinity"]
        erosion = first["ghost_system"]["erosion_rate_pp"]
        with self.assertRaisesRegex(ValueError, "已经与这道游魂结交过"):
            self.engine.ghost_parade_action(game.id, "soul-a", "befriend")
        unchanged = self.engine.get_game(game.id)
        self.assertEqual(unchanged["ghost_system"]["phase_two"]["parade"]["souls"][0]["affinity"], affinity)
        self.assertEqual(unchanged["ghost_system"]["erosion_rate_pp"], erosion)

    def test_possession_keeps_world_time_monotonic_and_migrates_legacy_timeline(self):
        player = Player("旧魂", "mutated_yin", age=800, path="ghost", realm_index=4, layer=5)
        ensure_ghost_cultivation_state(player)
        target = {
            "id": "young-host", "name": "年少宿主", "race": "human", "path": "dao",
            "spirit_root": "supreme_water", "realm_index": 3, "layer": 2,
            "age": 40, "lifespan": 500,
        }
        enter_host_body(player, target)
        self.assertEqual((player.age, current_body_age(player)), (800, 40))
        advance_player_age(player, 100)
        self.assertEqual((player.age, current_body_age(player)), (900, 140))
        leave_host_body(player)
        self.assertEqual(player.age, 900)

        legacy = Player("年少宿主（旧魂）", "supreme_water", age=140, path="dao", realm_index=3, layer=2)
        legacy.ghost_host_body = {
            "id": "legacy-host", "name": "年少宿主", "age": 40,
            "entered_age": 800, "lifespan": 500,
        }
        legacy.ghost_core_state = {"name": "旧魂", "age": 800}
        self.assertTrue(migrate_possession_timeline(legacy))
        self.assertEqual((legacy.age, current_body_age(legacy)), (900, 140))
        self.assertEqual(legacy.ghost_host_body["timeline_version"], 2)

    def test_new_state_round_trips_in_existing_save_object(self):
        game = self._game()
        game.player.ghost_bound_souls = [self._soul()]
        game.player.ghost_soul_slots = {"胎光": "soul-a"}
        game.player.ghost_attachment = {"item_id": "x", "name": "魂灯"}
        self.engine.store.save(game)
        loaded = self.engine.store.load(game.id)
        self.assertEqual(loaded.player.ghost_bound_souls[0]["name"], "顾忘川")
        self.assertEqual(loaded.player.ghost_soul_slots, {"胎光": "soul-a"})
        self.assertEqual(loaded.player.ghost_attachment["name"], "魂灯")
        self.assertTrue(loaded.ghost_parade)

    def test_routine_battle_death_offers_eligible_captive_and_uses_npc_life(self):
        game = self._game()
        game.player.realm_index = 3
        game.player.layer = 7
        game.player.age = 480
        game.player.prisoners = [
            {
                "id": "eligible", "name": "陆还真", "race": "human", "path": "dao",
                "spirit_root": "supreme_water", "realm_index": 3, "layer": 2,
                "age": 196, "lifespan": 812, "combat_power": 2800,
            },
            {
                "id": "too-high", "name": "越境者", "race": "human", "path": "dao",
                "spirit_root": "supreme_fire", "realm_index": 4, "layer": 1,
                "age": 620, "lifespan": 1350, "combat_power": 20000,
            },
        ]
        self.engine._die(
            game, "非剧情战陨落", "SYS_COMBAT", offer_captive_possession=True,
        )
        self.assertFalse(game.player.alive)
        self.assertEqual(game.pending_event["id"], "SYS_POST_BATTLE_POSSESSION")
        self.assertEqual([row["id"] for row in game.pending_event["choices"]], ["eligible"])

        self.engine.store.save(game)
        reloaded = self.engine._load(game.id)
        self.assertEqual(reloaded.pending_event["id"], "SYS_POST_BATTLE_POSSESSION")
        result = self.engine.post_battle_possess(game.id, "eligible")
        self.assertTrue(result["player"]["alive"])
        self.assertEqual((result["player"]["age"], result["player"]["lifespan"]), (196, 812))
        self.assertEqual(result["ghost_system"]["phase_two"]["possession_count"], 1)
        self.assertIsNone(result["pending_event"])

        restored = self.engine.leave_possessed_body(game.id)
        self.assertEqual(restored["player"]["age"], 480)

    def test_story_or_noncombat_death_does_not_offer_captive_possession(self):
        game = self._game()
        game.player.prisoners = [{
            "id": "body", "name": "顾青", "race": "human", "path": "dao",
            "realm_index": 0, "layer": 1, "age": 25, "lifespan": 82,
        }]
        self.engine._die(game, "剧情战陨落", "EVT_STORY_DEATH")
        self.assertFalse(game.player.alive)
        self.assertIsNone(game.pending_event)

    def test_becoming_an_npc_artifact_spirit_records_humiliation_milestone(self):
        game = self._game()

        class CapturingRng:
            @staticmethod
            def random():
                return 0.0

            @staticmethod
            def choice(_values):
                return "法器器灵"

        captured = self.engine._capture_defeated_ghost(game, {
            "target_name": "拘魂人", "target_power": 9999, "target_realm_index": 3,
            "target_layer": 4, "combat_type": "cultivator", "race": "human", "path": "ghost",
        }, CapturingRng())
        self.assertTrue(captured)
        self.assertEqual(game.player.ghost_captor["controlled_form"], "法器器灵")
        self.assertEqual(game.player.milestones["ghost_became_others_attachment"], 1)


if __name__ == "__main__":
    unittest.main()
