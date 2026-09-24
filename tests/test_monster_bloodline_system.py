import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cultivation_life.system.combat_system import BattleUnit, PlayerCombatSystem
from cultivation_life.combat_traits import COMBAT_TRAIT_REGISTRY
from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, MONSTER_BLOODLINE_SETTINGS, MONSTER_EVOLUTIONS, REALMS, TECHNIQUE_CATALOG
from cultivation_life.system.custom_lineage_system import describe_rule, evaluate_custom_lineage_rules, lineage_deed_budget
from cultivation_life.engine import GameEngine
from cultivation_life.system.monster_bloodline_system import (
    acquired_species_bloodline_traits, grant_random_species_bloodline_trait,
    generated_species_bloodline_traits, grant_generated_species_bloodline_trait,
    resolved_bloodline_traits,
)
from cultivation_life.monster_bloodline_rules import (
    BLOODLINE_RULE_EFFECTS, BLOODLINE_RULE_SCHEDULES, evaluate_generated_traits,
    generate_species_bloodline_trait, prepare_generated_trait_schedules,
    validate_generated_collection, validate_generated_trait,
)
from cultivation_life.monster_bloodline_traits import BLOODLINE_TRAIT_REGISTRY, bloodline_stat_modifiers
from cultivation_life.monster_general_traits import (
    GENERAL_MONSTER_TRAIT_REGISTRY, active_general_monster_traits,
    general_monster_trait_modifiers, grant_random_general_monster_trait,
)
from cultivation_life.rules import add_item, assign_technique, opportunity_required, qi_level_threshold
from cultivation_life.system.transformation_system import active_transformation_profile


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class MonsterBloodlineSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def _monster(self, species: str = "serpent"):
        shown = self.engine.create_game(
            "山野小妖", "supreme_water", "monster", seed=7301,
            monster_species_id=species,
        )
        return self.engine.store.load(shown["id"])

    @staticmethod
    def _ready_major(game) -> None:
        game.player.layer = REALMS[game.player.realm_index].layers
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_major_breakthrough = True

    def test_creation_separates_political_race_from_biological_species(self):
        game = self._monster("avian")
        self.assertEqual(game.player.race, "monster")
        self.assertEqual(game.player.lineage_race, "monster")
        self.assertEqual(game.player.monster_species_id, "avian")
        self.assertEqual(game.player.monster_evolution_id, "AVIAN_BASE")
        self.assertEqual(game.player.technique.id, "TECH_MONSTER_BREATHING")
        self.assertGreaterEqual(game.player.lifespan, 240)
        self.assertLessEqual(game.player.lifespan, 300)

    def test_old_monster_lifespan_is_migrated_exactly_once(self):
        game = self._monster()
        game.player.lifespan = 100
        game.player.monster_lifespan_scaled = False
        self.engine.store.save(game)
        self.assertEqual(self.engine.get_game(game.id)["player"]["lifespan"], 300)
        self.assertEqual(self.engine.get_game(game.id)["player"]["lifespan"], 300)

    def test_monster_body_training_is_fifty_percent_faster(self):
        monster = self._monster()
        dao_shown = self.engine.create_game("人修对照", "supreme_water", "dao", seed=7301)
        dao = self.engine.store.load(dao_shown["id"])
        body_art = TECHNIQUE_CATALOG["TECH_BODY_MORTAL"]
        assign_technique(monster.player, body_art, "body")
        assign_technique(dao.player, body_art, "body")
        self.engine.store.save(monster)
        self.engine.store.save(dao)

        monster_after = self.engine.advance(monster.id, "body_train")
        dao_after = self.engine.advance(dao.id, "body_train")
        self.assertAlmostEqual(
            monster_after["body_cultivation"]["progress"],
            dao_after["body_cultivation"]["progress"] * 1.5,
            places=1,
        )
        self.assertEqual(monster_after["body_cultivation"]["training_speed_multiplier"], 1.5)

    def test_advanced_monster_technique_enforces_body_requirement(self):
        game = self._monster()
        art = TECHNIQUE_CATALOG["TECH_MONSTER_HEAVEN_BONE"]
        game.player.spirit_root = "supreme_earth"
        game.player.body_training = 44
        with self.assertRaisesRegex(ValueError, "炼体45层"):
            assign_technique(game.player, art, "main")
        game.player.body_training = 45
        assign_technique(game.player, art, "main")
        self.assertEqual(game.player.technique.id, art.id)

    def test_monster_worlds_have_races_factions_and_generic_events(self):
        shown = self.engine.create_game(
            "妖界新生", "supreme_earth", "monster", seed=7302,
            start_world="monster_realm", monster_species_id="ape",
        )
        game = self.engine.store.load(shown["id"])
        self.assertEqual(game.player.world, "monster_realm")
        self.assertEqual(game.player.location_id, "myriad_beast_city")
        self.assertIn("myriad_beast_court", game.sects)
        self.assertIn("moonbeast_divine_court", game.sects)
        self.assertIn("EVT_MONSTER_WORLD_BLOOD_MARKET_001", self.engine.events_by_id)
        self.assertIn("EVT_PHANTOM_MOON_TIDE_001", self.engine.events_by_id)

    def test_monster_worlds_support_treasure_action_from_mortal_tier(self):
        for index, world in enumerate(("monster_realm", "phantom_underworld")):
            shown = self.engine.create_game(
                f"{world}探宝", "supreme_earth", "monster", seed=7310 + index,
                start_world=world, monster_species_id="ape",
            )
            result = self.engine.advance(shown["id"], "treasure")
            self.assertEqual(result["pending_event"]["id"], "EVT_TREASURE_REWARD_SELECT_001")
            self.assertEqual({choice["id"] for choice in result["pending_event"]["choices"]}, {"artifact", "technique", "pill"})

    def test_monster_cannot_use_transformation_system_even_with_legacy_state(self):
        game = self._monster()
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BEAST_TRANSFORMATION"])
        add_item(game.player, "phoenix_soul_flame")
        game.player.transformation_technique = technique
        game.player.known_transformations = ["FORM_PHOENIX"]
        game.player.transformation_mastery = {
            "FORM_PHOENIX": {"purity": 1.0, "stats": {key: 1.0 for key in ("might", "guard", "mobility", "sense", "sustain", "breach")}},
        }
        game.player.transformation_loadouts = {
            technique.id: {"stored": ["FORM_PHOENIX"], "active": ["FORM_PHOENIX"]},
        }
        self.engine.store.save(game)

        with self.assertRaisesRegex(ValueError, "不能修炼或配置变化术"):
            assign_technique(game.player, technique, "transformation")
        with self.assertRaisesRegex(ValueError, "不能炼化真灵素材"):
            self.engine.absorb_transformation_material(game.id, "phoenix_soul_flame", stat_id="might")
        with self.assertRaisesRegex(ValueError, "不能使用变身系统"):
            self.engine.manage_transformation(game.id, "FORM_PHOENIX", "activate")
        self.assertEqual(active_transformation_profile(game.player)["forms"], [])
        self.assertFalse(self.engine.get_game(game.id)["transformation_system"]["available"])

    def test_without_bloodline_dlc_monster_uses_normal_major_breakthrough(self):
        game = self._monster()
        game.player.realm_index = 1
        game.player.layer = REALMS[1].layers
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_major_breakthrough = True
        add_item(game.player, "foundation_pill")
        self.engine.store.save(game)
        certain = {
            "base": 1.0, "aid_bonus": 0.0, "companion_bonus": 0.0,
            "artifact_bonus": 0.0, "pity_bonus": 0.0, "devouring_bonus": 0.0,
            "body_training_bonus": 0.0, "optimal_state_bonus": 0.0,
            "heart_demon_penalty": 0.0, "final": 1.0,
        }
        with patch("cultivation_life.engine.bloodline_content_available", return_value=False):
            prepared = self.engine.use_item(game.id, "foundation_pill")
            self.assertIn("foundation_pill", prepared["player"]["active_breakthrough_aids"])
            with patch.object(self.engine, "_breakthrough_chance", return_value=certain):
                result = self.engine.breakthrough(game.id)
        self.assertEqual(result["player"]["realm_index"], 2)
        self.assertEqual(len(result["player"]["monster_general_traits"]), 1)
        trait_id = result["player"]["monster_general_traits"][0]
        self.assertIn(trait_id, GENERAL_MONSTER_TRAIT_REGISTRY)
        self.assertTrue(any(
            row["event_id"] == "SYS_MONSTER_GENERAL_TRAIT" and row["state_diff"]["trait_id"] == trait_id
            for row in result["history"]
        ))

    def test_general_trait_pool_has_sixteen_weaker_non_repeating_traits(self):
        self.assertEqual(len(GENERAL_MONSTER_TRAIT_REGISTRY), 16)
        self.assertTrue(all(
            1.0 < multiplier <= 1.04
            for definition in GENERAL_MONSTER_TRAIT_REGISTRY.values()
            for multiplier in definition["multipliers"].values()
        ))
        game = self._monster()
        game.player.monster_general_traits = list(GENERAL_MONSTER_TRAIT_REGISTRY)[:3]
        self.assertEqual(
            active_general_monster_traits(game.player, bloodline_available=False),
            game.player.monster_general_traits,
        )
        self.assertEqual(active_general_monster_traits(game.player, bloodline_available=True), [])
        game.player.monster_general_traits = []
        granted = [
            grant_random_general_monster_trait(game.player, random.Random(seed), bloodline_available=False)
            for seed in range(20)
        ]
        self.assertEqual(len(game.player.monster_general_traits), 16)
        self.assertEqual(len(set(game.player.monster_general_traits)), 16)
        self.assertTrue(all(row is not None for row in granted[:16]))
        self.assertTrue(all(row is None for row in granted[16:]))

    def test_general_traits_apply_only_with_bloodline_dlc_disabled(self):
        game = self._monster()
        player = game.player
        player.technique = None
        player.known_techniques = []
        player.monster_general_traits = ["monster_common_stout_hide", "monster_common_open_stride"]
        unit = [BattleUnit("player", player.name, "player", 100.0, player.realm_index, "monster")]
        with (
            patch("cultivation_life.system.combat_system.bloodline_content_available", return_value=False),
            patch("cultivation_life.system.monster_bloodline_system.bloodline_content_available", return_value=False),
        ):
            enabled = PlayerCombatSystem._aggregate_stats(unit, player=player, terrain_tags=["开阔"])
        player.monster_general_traits = []
        with (
            patch("cultivation_life.system.combat_system.bloodline_content_available", return_value=False),
            patch("cultivation_life.system.monster_bloodline_system.bloodline_content_available", return_value=False),
        ):
            baseline = PlayerCombatSystem._aggregate_stats(unit, player=player, terrain_tags=["开阔"])
        self.assertAlmostEqual(enabled["guard"] / baseline["guard"], 1.03, places=6)
        self.assertAlmostEqual(enabled["mobility"] / baseline["mobility"], 1.04, places=6)

        factors, triggered = general_monster_trait_modifiers(
            ["monster_common_tight_footing", "monster_common_peril_awareness"],
            natural_terrain="开阔",
        )
        self.assertEqual(triggered, [])
        self.assertTrue(all(value == 1.0 for value in factors.values()))

    def test_pre_dlc_monster_save_migrates_along_the_stable_route(self):
        game = self._monster()
        game.player.realm_index = 2
        game.player.monster_species_id = None
        game.player.monster_evolution_id = None
        game.player.monster_evolution_history = []
        self.engine.store.save(game)

        shown = self.engine.get_game(game.id)
        self.assertEqual(shown["monster_bloodline"]["current"]["id"], "SERPENT_MYSTIC")
        self.assertEqual(
            [row["id"] for row in shown["monster_bloodline"]["history"]],
            ["SERPENT_BASE", "SERPENT_SPIRIT", "SERPENT_MYSTIC"],
        )

    def test_major_breakthrough_requires_an_irreversible_evolution_choice(self):
        game = self._monster()
        self._ready_major(game)
        self.engine.store.save(game)
        shown = self.engine.get_game(game.id)
        self.assertTrue(shown["monster_bloodline"]["awaiting_evolution"])
        self.assertEqual([row["id"] for row in shown["monster_bloodline"]["candidates"]], ["SERPENT_SPIRIT"])
        with self.assertRaisesRegex(ValueError, "血脉"):
            self.engine.breakthrough(game.id)

        evolved = self.engine.evolve_monster(game.id, "SERPENT_SPIRIT")
        self.assertEqual(evolved["player"]["realm_index"], 1)
        self.assertEqual(evolved["monster_bloodline"]["current"]["id"], "SERPENT_SPIRIT")
        self.assertEqual(
            [row["id"] for row in evolved["monster_bloodline"]["history"]],
            ["SERPENT_BASE", "SERPENT_SPIRIT"],
        )
        self.assertEqual(len(evolved["player"]["monster_acquired_bloodline_traits"]), 1)
        awakened = evolved["player"]["monster_acquired_bloodline_traits"][0]
        self.assertIn(awakened, MONSTER_BLOODLINE_SETTINGS["species_trait_pools"]["serpent"])
        self.assertEqual(evolved["monster_bloodline"]["species_trait_pool"], {"acquired": 1, "total": 16})

    def test_locked_branches_are_visible_for_planning_but_cannot_be_selected(self):
        game = self._monster()
        game.player.realm_index = 1
        game.player.layer = REALMS[1].layers
        game.player.monster_evolution_id = "SERPENT_SPIRIT"
        game.player.monster_evolution_history = ["SERPENT_BASE", "SERPENT_SPIRIT"]
        game.player.qi_experience["monster"] = qi_level_threshold(2)
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_major_breakthrough = True
        self.engine.store.save(game)
        shown = self.engine.get_game(game.id)
        enabled = {row["id"]: row["enabled"] for row in shown["monster_bloodline"]["candidates"]}
        self.assertEqual(enabled, {
            "SERPENT_MYSTIC": True, "SERPENT_WATER": False, "SERPENT_THUNDER": False,
        })
        with self.assertRaisesRegex(ValueError, "进化条件"):
            self.engine.evolve_monster(game.id, "SERPENT_WATER")

    def test_long_term_location_life_grants_a_hidden_adaptation_once(self):
        game = self._monster("ape")
        game.player.location_id = "lanjiang_steppe"
        for year in range(10):
            game.player.age += 1
            self.engine._advance_monster_bloodline_year(game)
        self.assertIn("ancient_forest", game.player.monster_adaptations)
        self.assertEqual(
            len([row for row in game.history if row.event_id == "SYS_MONSTER_ADAPT_ANCIENT_FOREST"]), 1,
        )
        self.engine.store.save(game)
        shown = self.engine.get_game(game.id)
        self.assertNotIn("monster_adaptation_progress", shown["player"])
        self.assertEqual(shown["monster_bloodline"]["adaptations"][0]["name"], "古林生灵")

    def test_current_node_profile_replaces_history_instead_of_multiplying_it(self):
        game = self._monster()
        player = game.player
        player.technique = None
        player.known_techniques = []
        unit = [BattleUnit("player", player.name, "player", 100.0, 3, "monster")]

        player.monster_evolution_id = "SERPENT_BASE"
        base = PlayerCombatSystem._aggregate_stats(unit, player=player, terrain_tags=[])
        player.monster_evolution_id = "SERPENT_GREAT_MYSTIC"
        player.monster_evolution_history = [
            "SERPENT_BASE", "SERPENT_SPIRIT", "SERPENT_MYSTIC", "SERPENT_GREAT_MYSTIC",
        ]
        evolved = PlayerCombatSystem._aggregate_stats(unit, player=player, terrain_tags=[])
        for stat, final_multiplier in MONSTER_EVOLUTIONS["SERPENT_GREAT_MYSTIC"]["profile"].items():
            base_multiplier = MONSTER_EVOLUTIONS["SERPENT_BASE"]["profile"][stat]
            self.assertAlmostEqual(evolved[stat] / base[stat], final_multiplier / base_multiplier, places=6)

    def test_bloodline_and_transformation_traits_are_separate(self):
        self.assertFalse(set(COMBAT_TRAIT_REGISTRY) & set(BLOODLINE_TRAIT_REGISTRY))
        self.assertFalse(
            set(COMBAT_TRAIT_REGISTRY)
            & {definition["combat_hook"] for definition in BLOODLINE_TRAIT_REGISTRY.values()}
        )
        self.assertTrue(all(
            set(node.get("traits", [])) <= set(BLOODLINE_TRAIT_REGISTRY)
            for node in MONSTER_EVOLUTIONS.values()
        ))
        configured_traits = {
            trait for node in MONSTER_EVOLUTIONS.values() for trait in node.get("traits", [])
        } | {
            row["trait_id"] for row in MONSTER_BLOODLINE_SETTINGS["species_signature_traits"]
        } | {
            trait for pool in MONSTER_BLOODLINE_SETTINGS["species_trait_pools"].values() for trait in pool
        }
        self.assertEqual(configured_traits, set(BLOODLINE_TRAIT_REGISTRY))
        game = self._monster("avian")
        game.player.monster_evolution_id = "AVIAN_VERMILION"
        game.player.monster_evolution_history = ["AVIAN_BASE", "AVIAN_SPIRIT", "AVIAN_FIRE", "AVIAN_VERMILION"]
        own = self.engine._player_battle_power(game)
        self.engine._combat(game, {
            "target_name": "试炼石像", "target_power": own,
            "target_realm_index": game.player.realm_index, "target_layer": game.player.layer,
            "combat_type": "cultivator", "max_rounds": 4,
        }, True, random.Random(19))
        report = game.last_combat_report
        self.assertIn("bloodline_vital_spark", report["bloodline_traits"])
        self.assertEqual(report["transformation_traits"], [])
        self.assertTrue(any("血脉本相" in text for text in report["key_events"]))
        combat_text = "\n".join(report["key_events"])
        self.assertNotIn("修罗战意", combat_text)
        self.assertNotIn("朱焰回生", combat_text)
        self.assertNotIn("涅槃", combat_text)

    def test_each_species_pool_has_sixteen_traits_and_four_remain_at_daluo(self):
        pools = MONSTER_BLOODLINE_SETTINGS["species_trait_pools"]
        self.assertEqual(set(pools), {"serpent", "avian", "ape", "fox", "turtle", "insect", "aquatic", "flora"})
        self.assertEqual(len({trait for pool in pools.values() for trait in pool}), 128)
        for species_id, pool in pools.items():
            with self.subTest(species=species_id):
                self.assertEqual(len(pool), 16)
                game = self._monster(species_id)
                rng = random.Random(8100)
                for _ in range(12):
                    self.assertIsNotNone(grant_random_species_bloodline_trait(game.player, rng))
                self.assertEqual(len(acquired_species_bloodline_traits(game.player)), 12)
                self.assertEqual(len(set(pool) - set(game.player.monster_acquired_bloodline_traits)), 4)

    def test_species_pool_traits_apply_data_driven_combat_modifiers(self):
        game = self._monster("fox")
        trait_id = "bloodline_fox_pool_01"
        game.player.monster_acquired_bloodline_traits = [trait_id]
        factors, triggered = bloodline_stat_modifiers(
            set(acquired_species_bloodline_traits(game.player)),
            natural_terrain="开阔", artificial_conditions=[],
        )
        self.assertEqual(triggered, [trait_id])
        self.assertAlmostEqual(factors["might"], 1.07)
        self.assertTrue(all(factors[stat] == 1.0 for stat in factors if stat != "might"))

    def test_finite_rule_generator_builds_sixteen_valid_unique_traits_per_species(self):
        for species_id in ("serpent", "avian", "ape", "fox", "turtle", "insect", "aquatic", "flora"):
            with self.subTest(species=species_id):
                rng = random.Random(f"rules-{species_id}")
                rules = []
                for _ in range(16):
                    rule = generate_species_bloodline_trait(species_id, rng, rules)
                    self.assertIsNotNone(rule)
                    rules.append(rule)
                self.assertEqual(len({rule["id"] for rule in rules}), 16)
                self.assertFalse(validate_generated_collection(rules))
                self.assertTrue(any(len(rule["conditions"]) == 2 for rule in rules))
                self.assertTrue(all(rule["description"].endswith("。") for rule in rules))

    def test_rule_validator_rejects_unavailable_causal_data_and_overpowered_effect(self):
        rule = generate_species_bloodline_trait("turtle", random.Random(7), [])
        self.assertIsNotNone(rule)
        invalid = dict(rule)
        invalid.update(trigger="round_start", conditions=["received_12"])
        invalid["id"] = "tampered"
        reasons = validate_generated_trait(invalid)
        self.assertTrue(any("尚无数据" in reason for reason in reasons))
        with patch.dict(BLOODLINE_RULE_EFFECTS[rule["effect"]], {"power": 99.0}):
            reasons = validate_generated_trait(rule)
        self.assertTrue(any("硬上限" in reason for reason in reasons))
        self.assertFalse(any(
            definition["kind"] in {"damage_self", "drain_state"}
            or definition["target"] == "enemy" and definition["kind"] in {"restore_state", "restore_mp"}
            for definition in BLOODLINE_RULE_EFFECTS.values()
        ))

    def test_generated_damage_cap_and_reclamation_execute_from_saved_rules(self):
        cap = {
            "schema_version":1, "species_id":"turtle", "trigger":"before_damage",
            "schedule":"every", "conditions":["enemy_higher"], "effect":"damage_cap_24",
        }
        from cultivation_life.monster_bloodline_rules import generated_trait_id, describe_generated_trait
        cap.update(id=generated_trait_id(cap), name="玄甲·锁命", description=describe_generated_trait(cap), power={"raw":13.0,"expected":4.16})
        result = evaluate_generated_traits(
            [cap], trigger="before_damage", context={"round_no":1, "realm_delta":-1},
        )
        self.assertEqual(result["received_cap"], 0.24)
        reclaim = {
            "schema_version":1, "species_id":"turtle", "trigger":"after_damage",
            "schedule":"every", "conditions":["received_12"], "effect":"reclaim_20",
        }
        reclaim.update(id=generated_trait_id(reclaim), name="玄甲·返生", description=describe_generated_trait(reclaim), power={"raw":11.5,"expected":4.83})
        result = evaluate_generated_traits(
            [reclaim], trigger="after_damage", context={"round_no":2, "received":0.18},
        )
        self.assertAlmostEqual(result["player_state_restore"], 0.036)

    def test_generated_round_windows_include_single_ranges_last_and_battle_random(self):
        from cultivation_life.monster_bloodline_rules import generated_trait_id, describe_generated_trait

        expected = {
            "first": {1}, "second": {2}, "third": {3}, "fourth": {4},
            "last": {5}, "first_two": {1, 2}, "first_three": {1, 2, 3},
            "last_two": {4, 5}, "after_third": {4, 5},
            "first_and_last": {1, 5}, "second_and_fourth": {2, 4},
        }
        self.assertTrue({"random", "random_two", *expected} <= set(BLOODLINE_RULE_SCHEDULES))
        for schedule, active_rounds in expected.items():
            rule = {
                "schema_version":1, "species_id":"serpent", "trigger":"round_start",
                "schedule":schedule, "conditions":["always"], "effect":"self_might_minor",
            }
            rule.update(
                id=generated_trait_id(rule), name="潜鳞·威能滋长",
                description=describe_generated_trait(rule),
            )
            triggered = {
                round_no for round_no in range(1, 6)
                if evaluate_generated_traits(
                    [rule], trigger="round_start", context={"round_no":round_no, "max_rounds":5},
                )["triggered_ids"]
            }
            self.assertEqual(triggered, active_rounds, schedule)

        eighth = {
            "schema_version":1, "species_id":"serpent", "trigger":"round_start",
            "schedule":"eighth", "conditions":["always"], "effect":"self_might_minor",
        }
        eighth.update(
            id=generated_trait_id(eighth), name="潜鳞·威能滋长",
            description=describe_generated_trait(eighth),
        )
        self.assertTrue(evaluate_generated_traits(
            [eighth], trigger="round_start", context={"round_no":8, "max_rounds":8},
        )["triggered_ids"])

        random_rules = []
        for schedule in ("random", "random_two"):
            rule = {
                "schema_version":1, "species_id":"serpent", "trigger":"round_start",
                "schedule":schedule, "conditions":["always"], "effect":"self_might_minor",
            }
            rule.update(
                id=generated_trait_id(rule), name="潜鳞·威能滋长",
                description=describe_generated_trait(rule),
            )
            random_rules.append(rule)
        prepared = prepare_generated_trait_schedules(random_rules, max_rounds=5, rng=random.Random(93))
        self.assertEqual(len(prepared[0]["_battle_random_rounds"]), 1)
        self.assertEqual(len(prepared[1]["_battle_random_rounds"]), 2)
        for rule in prepared:
            triggered = sum(bool(evaluate_generated_traits(
                [rule], trigger="round_start", context={"round_no":round_no},
            )["triggered_ids"]) for round_no in range(1, 6))
            self.assertEqual(triggered, 1 if rule["schedule"] == "random" else 2)

    def test_new_evolution_uses_generated_rule_while_legacy_slots_remain_compatible(self):
        game = self._monster("fox")
        trait = grant_generated_species_bloodline_trait(game.player, random.Random(81))
        self.assertIsNotNone(trait)
        self.assertTrue(trait["generated"])
        self.assertEqual(len(generated_species_bloodline_traits(game.player)), 1)
        self.assertIn(game.player.monster_acquired_bloodline_traits[0], MONSTER_BLOODLINE_SETTINGS["species_trait_pools"]["fox"])
        self.assertNotIn(game.player.monster_acquired_bloodline_traits[0], acquired_species_bloodline_traits(game.player))

    def test_every_bloodline_trait_executes_its_own_combat_mechanic(self):
        cases = [
            ("bloodline_skyborn", "御空吐纳", 1.0, 0, "开阔", {}),
            ("bloodline_savage_force", "撕伤追猎", 0.95, 0, "狭窄", {}),
            ("bloodline_ancestral_aura", "祖血蚀甲", 1.0, 0, "狭窄", {}),
            ("bloodline_carapace_guard", "厚甲卸力", 2.8, 0, "狭窄", {}),
            ("bloodline_giant_killer", "越阶适应", 1.0, 2, "狭窄", {}),
            ("bloodline_terror_aura", "妖煞惊惧", 0.9, 0, "狭窄", {}),
            ("bloodline_vital_spark", "本源激生", 2.8, 0, "狭窄", {}),
            ("bloodline_regeneration", "伤势回收", 1.3, 0, "狭窄", {}),
            ("bloodline_feral_resolve", "困兽护生", 1.7, 0, "狭窄", {}),
            ("bloodline_coiling_lock", "蟠身锁域", 1.0, 0, "狭窄", {}),
            ("bloodline_gale_feathers", "罡羽破界", 1.0, 0, "开阔", {}),
            ("bloodline_counterforce_sinew", "反震战筋", 1.7, 0, "狭窄", {"player_ambush":False}),
            ("bloodline_dream_pupil", "梦瞳摄魄", 1.0, 0, "狭窄", {}),
            ("bloodline_reactive_shell", "应击灵甲", 1.7, 0, "狭窄", {"player_ambush":False}),
            ("bloodline_faceted_sense", "万象复眼", 1.0, 0, "开阔", {"artificial_conditions":["禁神识"]}),
            ("bloodline_tidal_pulse", "潮脉回环", 1.0, 0, "狭窄", {}),
            ("bloodline_earthroot", "地脉扎根", 1.0, 0, "险要", {}),
        ]
        for trait_id, effect_name, power_scale, realm_gap, terrain, overrides in cases:
            with self.subTest(trait=trait_id):
                game = self._monster("serpent")
                own = self.engine._player_battle_power(game)
                with patch.dict(MONSTER_EVOLUTIONS["SERPENT_BASE"], {"traits": [trait_id]}):
                    target = {
                        "target_name": "血脉试炼木偶", "target_power": own * power_scale,
                        "target_realm_index": game.player.realm_index + realm_gap,
                        "target_layer": game.player.layer, "combat_type": "cultivator",
                        "max_rounds": 8, "natural_terrain": terrain, "player_ambush": True,
                    }
                    target.update(overrides)
                    self.engine._combat(game, target, False, random.Random(19))
                report = game.last_combat_report
                combat_text = "\n".join([
                    *report["key_events"],
                    *(event for row in report["rounds"] for event in row["events"]),
                ])
                self.assertIn(effect_name, combat_text)
                self.assertIn(trait_id, report["bloodline_traits"])
                self.assertFalse(report["death_prevented"])

    def test_species_signature_traits_unlock_at_configured_realm_and_persist(self):
        unlocks = MONSTER_BLOODLINE_SETTINGS["species_signature_traits"]
        self.assertEqual(len(unlocks), 8)
        self.assertEqual(
            {unlock["species_id"] for unlock in unlocks},
            {node["species"] for node in MONSTER_EVOLUTIONS.values()},
        )
        for unlock in unlocks:
            nodes = sorted(
                (node for node in MONSTER_EVOLUTIONS.values() if node["species"] == unlock["species_id"]),
                key=lambda node: int(node["realm_index"]),
            )
            before = next(node for node in nodes if int(node["realm_index"]) < unlock["minimum_realm"])
            at_or_after = next(node for node in nodes if int(node["realm_index"]) >= unlock["minimum_realm"])
            self.assertNotIn(unlock["trait_id"], resolved_bloodline_traits(before))
            self.assertIn(unlock["trait_id"], resolved_bloodline_traits(at_or_after))
            self.assertTrue(all(
                unlock["trait_id"] in resolved_bloodline_traits(node)
                for node in nodes if int(node["realm_index"]) >= unlock["minimum_realm"]
            ))

    def test_monster_worlds_sell_minor_breakthrough_pills_for_every_realm(self):
        expected = {
            "monster_meridian_pill":"minor:2", "blood_core_pill":"minor:3",
            "beast_infant_pill":"minor:4", "ancestral_soul_marrow":"minor:5",
            "void_molt_pill":"minor:6", "unity_blood_pill":"minor:7",
            "myriad_ancestor_pill":"minor:8",
        }
        for item_id, scope in expected.items():
            self.assertEqual(ITEM_CATALOG[item_id].breakthrough_scope, scope)
            sold_worlds = {
                good["world"] for good in MARKET_GOODS
                if good["kind"] == "item" and good["content_id"] == item_id
            }
            self.assertTrue({"monster_realm", "phantom_underworld"} <= sold_worlds)

    def test_human_probability_story_chains_do_not_trigger_in_monster_worlds(self):
        game = self._monster("fox")
        game.player.world = "phantom_underworld"
        game.player.realm_index = 7
        game.player.layer = 7
        story_events = [
            event for event in self.engine.events
            if event["id"] in {"EVT_WIND_WINGS_001", "EVT_KUNWU_OPEN_001"}
        ]
        self.assertTrue(story_events)
        self.assertTrue(all("world:human" in event.get("tags", []) for event in story_events))
        rng = unittest.mock.MagicMock()
        rng.random.return_value = 0.0
        original_events = self.engine.events
        self.engine.events = tuple(story_events)
        try:
            self.assertFalse(self.engine._maybe_probability_story_event(game, rng))
        finally:
            self.engine.events = original_events
        self.assertIsNone(game.pending_event)

    def test_both_monster_lower_worlds_ascend_to_nether_and_restore_after_descent(self):
        for lower_world in ("monster_realm", "phantom_underworld"):
            with self.subTest(lower_world=lower_world):
                game = self._monster("fox")
                game.player.world = lower_world
                game.player.location_id = self.engine.maps.default_location(lower_world)
                game.player.realm_index = 8
                game.player.layer = REALMS[8].layers
                game.player.monster_evolution_id = "FOX_MAHAYANA_HEAVENLY"
                game.player.monster_evolution_history = ["FOX_MAHAYANA_HEAVENLY"]
                game.player.monster_bloodline_imprints = ["nine_tail_ancestry"]
                game.player.qi_experience["monster"] = qi_level_threshold(20)
                game.player.opportunity = opportunity_required(game.player)
                game.player.awaiting_major_breakthrough = True
                self.engine.store.save(game)

                ascended = self.engine.evolve_monster(game.id, "FOX_NETHER_TRUE_1")
                self.assertEqual((ascended["player"]["world"], ascended["player"]["realm_index"]), ("nether", 9))
                self.assertTrue(ascended["world_travel"]["can_descend_monster"])
                self.assertTrue(ascended["world_travel"]["can_descend_phantom"])
                descended = self.engine.cross_world(game.id, lower_world)
                self.assertEqual((descended["player"]["world"], descended["player"]["realm_index"]), (lower_world, 8))
                self.assertTrue(descended["world_travel"]["can_return_nether"])
                with self.assertRaisesRegex(ValueError, "封印状态"):
                    self.engine.breakthrough(game.id)
                restored = self.engine.cross_world(game.id, "nether")
                self.assertEqual((restored["player"]["world"], restored["player"]["realm_index"]), ("nether", 9))
                self.assertFalse(restored["world_travel"]["suppressed"])

    def test_v4_self_lineage_requires_editor_and_can_be_expanded(self):
        game = self._monster("fox")
        game.player.world = "monster_realm"
        game.player.location_id = "myriad_beast_city"
        game.player.realm_index = 8
        game.player.layer = REALMS[8].layers
        game.player.monster_evolution_id = "FOX_MAHAYANA_HEAVENLY"
        game.player.monster_evolution_history = ["FOX_MAHAYANA_HEAVENLY"]
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_major_breakthrough = True
        self.engine.store.save(game)

        shown = self.engine.get_game(game.id)
        candidates = {row["id"]: row["enabled"] for row in shown["monster_bloodline"]["candidates"]}
        self.assertFalse(candidates["FOX_NETHER_TRUE_1"])
        self.assertTrue(candidates["FOX_NETHER_SELF_1"])
        with self.assertRaisesRegex(ValueError, "立祖界面"):
            self.engine.evolve_monster(game.id, "FOX_NETHER_SELF_1")
        prepared = self.engine.prepare_custom_lineage(game.id, "FOX_NETHER_SELF_1")
        editor = prepared["monster_bloodline"]["custom_lineage_editor"]
        self.assertEqual((editor["stage"], editor["slots"], editor["deeds"]["total"]), (1, 2, 24))
        rules = [{
            "phase":"round_start", "schedule":"every", "condition":"always",
            "target":"player", "effect":"might", "value":0.03,
        }]
        expensive = [
            {**rules[0], "target":"enemy", "value":0.12},
            {**rules[0], "target":"enemy", "effect":"guard", "value":0.12},
        ]
        with self.assertRaisesRegex(ValueError, "功业点不足"):
            self.engine.confirm_custom_lineage(game.id, "FOX_NETHER_SELF_1", "青丘自在脉", expensive)
        unchanged = self.engine.store.load(game.id)
        self.assertEqual(unchanged.player.realm_index, 8)
        self.assertIsNone(unchanged.player.monster_custom_lineage)
        ascended = self.engine.confirm_custom_lineage(game.id, "FOX_NETHER_SELF_1", "青丘自在脉", rules)
        self.assertEqual((ascended["player"]["world"], ascended["player"]["realm_index"]), ("nether", 9))
        lineage = ascended["monster_bloodline"]["custom_lineage"]
        self.assertEqual(lineage["name"], "青丘自在脉")
        self.assertTrue(lineage["id"].startswith("custom-lineage-"))
        self.assertNotIn("青丘自在脉", lineage["id"])
        self.assertIn("primordial_true_spirit_hall", self.engine.store.load(game.id).sects)
        descended = self.engine.cross_world(game.id, "phantom_underworld")
        self.assertEqual((descended["player"]["world"], descended["player"]["realm_index"]), ("phantom_underworld", 8))
        restored = self.engine.cross_world(game.id, "nether")
        self.assertEqual((restored["player"]["world"], restored["player"]["realm_index"]), ("nether", 9))

        game = self.engine.store.load(game.id)
        game.player.opportunity = opportunity_required(game.player)
        game.player.awaiting_major_breakthrough = True
        self.engine.store.save(game)
        expanded_rules = [*rules, {
            "phase":"round_end", "schedule":"round_2", "condition":"player_state_50",
            "target":"player", "effect":"combat_state", "value":0.05,
        }]
        with self.assertRaisesRegex(ValueError, "不能修改"):
            self.engine.confirm_custom_lineage(
                game.id, "FOX_NETHER_SELF_2", "青丘自在脉", [{**rules[0], "effect":"guard"}],
            )
        advanced = self.engine.confirm_custom_lineage(
            game.id, "FOX_NETHER_SELF_2", "青丘自在脉", expanded_rules,
        )
        self.assertEqual(advanced["player"]["realm_index"], 10)
        self.assertEqual(advanced["monster_bloodline"]["custom_lineage"]["finalized_stage"], 2)
        self.assertEqual(len(advanced["monster_bloodline"]["custom_lineage"]["rules"]), 2)

    def test_v4_deeds_ignore_age_wealth_marks_and_current_realm(self):
        game = self._monster("fox")
        config = MONSTER_BLOODLINE_SETTINGS["custom_lineage"]
        initial = lineage_deed_budget(game, config)
        game.player.age = 90000
        game.player.spirit_stones = 99999999
        game.player.fame = 99999
        game.player.realm_index = 12
        game.player.monster_adaptations = ["moonlit", "ancient_forest"]
        game.player.monster_bloodline_imprints = ["nine_tail_ancestry"]
        self.assertEqual(lineage_deed_budget(game, config)["total"], initial["total"])
        game.player.monster_evolution_history.append("FOX_NINE_TAIL")
        game.player.tribulation_count = 5
        self.assertEqual(lineage_deed_budget(game, config)["total"], initial["total"] + 9)

    def test_v4_old_self_lineage_save_gets_one_time_retroactive_inscription(self):
        game = self._monster("fox")
        game.player.realm_index = 11
        game.player.monster_evolution_id = "FOX_NETHER_SELF_3"
        game.player.monster_evolution_history = ["FOX_MAHAYANA_HEAVENLY", "FOX_NETHER_SELF_1", "FOX_NETHER_SELF_2", "FOX_NETHER_SELF_3"]
        self.engine.store.save(game)
        shown = self.engine.get_game(game.id)
        self.assertTrue(shown["monster_bloodline"]["custom_lineage_retroactive_available"])
        prepared = self.engine.prepare_custom_lineage(game.id, "__retroactive__")
        self.assertEqual(prepared["monster_bloodline"]["custom_lineage_editor"]["slots"], 4)
        rule = [{
            "phase":"round_start", "schedule":"round_1", "condition":"always",
            "target":"enemy", "effect":"guard", "value":0.03,
        }]
        completed = self.engine.confirm_custom_lineage(game.id, "__retroactive__", "补刻梦狐脉", rule)
        self.assertFalse(completed["monster_bloodline"]["custom_lineage_retroactive_available"])
        with self.assertRaisesRegex(ValueError, "不需要补刻"):
            self.engine.prepare_custom_lineage(game.id, "__retroactive__")

    def test_v4_rule_evaluator_is_finite_and_does_not_mutate_base_stats(self):
        game = self._monster("fox")
        game.player.monster_custom_lineage = {"name":"试脉", "rules":[{
            "phase":"round_start", "schedule":"every", "condition":"terrain_open",
            "target":"player", "effect":"might", "value":0.1, "description":"开阔增威",
        }]}
        config = MONSTER_BLOODLINE_SETTINGS["custom_lineage"]
        first = evaluate_custom_lineage_rules(
            game.player, config, phase="round_start", round_no=1, natural_terrain="开阔",
            artificial_conditions=[], player_state=1, enemy_state=1, player_morale=100, enemy_morale=100,
        )
        second = evaluate_custom_lineage_rules(
            game.player, config, phase="round_start", round_no=2, natural_terrain="开阔",
            artificial_conditions=[], player_state=1, enemy_state=1, player_morale=100, enemy_morale=100,
        )
        self.assertAlmostEqual(first["player_stat_multipliers"]["might"], 1.1)
        self.assertEqual(first["player_stat_multipliers"], second["player_stat_multipliers"])

    def test_custom_lineage_editor_and_evaluator_support_last_and_random_rounds(self):
        game = self._monster("fox")
        config = MONSTER_BLOODLINE_SETTINGS["custom_lineage"]
        schedule_ids = {row["id"] for row in config["schedules"]}
        self.assertTrue({
            "round_8", "first_four", "last", "penultimate", "last_two", "last_three",
            "after_second", "after_third", "first_and_last", "second_and_fourth",
            "random_one", "random_two",
        } <= schedule_ids)
        base_rule = {
            "phase":"round_start", "condition":"always", "target":"player",
            "effect":"might", "value":0.03,
        }
        for schedule, expected_rounds, random_rounds in (
            ("last", {5}, {}),
            ("first_and_last", {1, 5}, {}),
            ("random_one", {3}, {0: (3,)}),
        ):
            game.player.monster_custom_lineage = {
                "id":"schedule-test", "name":"轮转试脉",
                "rules":[base_rule | {"schedule":schedule}],
            }
            triggered = {
                round_no for round_no in range(1, 6)
                if evaluate_custom_lineage_rules(
                    game.player, config, phase="round_start", round_no=round_no,
                    natural_terrain="开阔", artificial_conditions=[], player_state=1,
                    enemy_state=1, player_morale=100, enemy_morale=100,
                    max_rounds=5, random_rounds=random_rounds,
                )["player_stat_multipliers"]
            }
            self.assertEqual(triggered, expected_rounds, schedule)

    def test_monster_offspring_inherits_species_and_can_inherit_imprints(self):
        game = self._monster("fox")
        game.player.monster_bloodline_imprints = ["nine_tail_ancestry"]
        game.player.dao_companion = {
            "id":"fox_companion", "name":"青丘月", "alive":True,
            "world":game.player.world, "realm_index":0,
            "spirit_root":"supreme_wood", "acquired_root":False,
        }
        rng = unittest.mock.MagicMock()
        rng.random.return_value = 0.0
        rng.choice.side_effect = lambda values: values[0]
        rng.randint.return_value = 90
        text = self.engine._try_conceive_child(game, rng)
        child = game.player.offspring[0]
        self.assertIn("本源血脉", text)
        self.assertEqual(child["path"], "monster")
        self.assertEqual(child["monster_species_id"], "fox")
        self.assertEqual(child["monster_evolution_id"], "FOX_BASE")
        self.assertEqual(child["monster_bloodline_imprints"], ["nine_tail_ancestry"])
        self.assertNotIn("monster_custom_lineage", child)
        self.assertEqual(child["lifespan"], 270)

    def test_v41_custom_lineage_has_stable_id_and_descendants_inherit_final_rules(self):
        game = self._monster("fox")
        lineage = {
            "id":"custom-lineage-stable-test", "name":"青丘自在脉", "finalized_stage":2,
            "spent_points":9, "rules":[{
                "phase":"round_start", "schedule":"even", "condition":"player_state_50",
                "target":"player", "effect":"might", "value":0.1, "cost":8,
            }],
        }
        lineage["rules"][0]["description"] = describe_rule(
            lineage["rules"][0], MONSTER_BLOODLINE_SETTINGS["custom_lineage"],
        )
        self.assertEqual(
            lineage["rules"][0]["description"],
            "偶数轮开始时，若己方态势不高于50%，自身威能提高10%。",
        )
        game.player.monster_custom_lineage_id = lineage["id"]
        game.player.monster_custom_lineage = lineage
        game.player.dao_companion = {
            "id":"fox_companion", "name":"青丘月", "alive":True,
            "world":game.player.world, "realm_index":0,
            "spirit_root":"supreme_wood", "acquired_root":False,
        }
        rng = unittest.mock.MagicMock()
        rng.random.return_value = 0.0
        rng.choice.side_effect = lambda values: values[0]
        rng.randint.return_value = 90
        self.engine._try_conceive_child(game, rng)
        child = game.player.offspring[0]
        self.assertEqual(child["monster_custom_lineage_id"], lineage["id"])
        self.assertEqual(child["monster_custom_lineage"]["rules"], lineage["rules"])
        self.assertIsNot(child["monster_custom_lineage"], lineage)
        self.assertEqual(game.player.monster_custom_lineage_id, lineage["id"])


if __name__ == "__main__":
    unittest.main()
