import random
import copy
import unittest

from cultivation_life.models import Player, Technique
from cultivation_life.content_registry import GUIXU_TIDE_CONTENT, WORLD_SYSTEMS
from cultivation_life.rules import (
    KARMA_FACTORS,
    REALMS,
    ROOT_DEFINITIONS,
    TECHNIQUE_CATALOG,
    add_item,
    assign_technique,
    combat_power,
    can_practice_technique,
    can_player_practice_technique,
    effective_karma,
    expected_combat_power,
    standard_combat_power_dlc_bonus,
    recommended_combat_power,
    combat_power_assessment,
    max_hp,
    max_mp,
    opportunity_required,
    opportunity_multiplier,
    public_player,
    qi_environment_multiplier,
    roll_lifespan,
    technique_environment_multiplier,
    combat_requirement_display,
    combat_requirement_met,
    grant_qi_experience,
    qi_level,
    qi_level_threshold,
    valid_combat_requirement,
)


class RuleTests(unittest.TestCase):
    def test_requested_karma_factors_are_exact(self):
        self.assertEqual(KARMA_FACTORS, {
            "dao": 1.0,
            "demonic": 0.8,
            "ghost": 0.75,
            "monster": 0.9,
            "buddhist": 0.6,
            "confucian": 0.95,
        })

    def test_effective_karma_uses_main_technique(self):
        player = Player("测试", "supreme_metal", karma=100, technique=Technique(path="buddhist"))
        self.assertEqual(effective_karma(player), 60)

    def test_lifespan_ranges_match_realm_table(self):
        rng = random.Random(7)
        player = Player("测试", "supreme_wood")
        for index, definition in enumerate(REALMS):
            player.realm_index = index
            rolled = [roll_lifespan(player, rng) for _ in range(30)]
            if definition.lifespan is None:
                self.assertTrue(all(value is None for value in rolled))
            else:
                low, high = definition.lifespan
                self.assertTrue(all(low <= value <= high for value in rolled))

    def test_qi_has_thirteen_layers_and_later_realms_have_nine(self):
        self.assertEqual(REALMS[1].layers, 13)
        self.assertTrue(all(item.layers == 9 for item in REALMS[2:9]))
        self.assertTrue(all(item.layers == 1 for item in REALMS[9:]))

    def test_combat_power_reacts_to_all_live_resources(self):
        player = Player("测试", "supreme_metal", realm_index=2, layer=3)
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        full = combat_power(player)
        player.hp *= 0.2
        player.mp *= 0.2
        wounded = combat_power(player)
        self.assertGreater(full, wounded)

    def test_expected_combat_power_is_stage_based_and_monotonic(self):
        self.assertAlmostEqual(standard_combat_power_dlc_bonus(), 0.30)
        self.assertEqual(expected_combat_power(3, 2), 3250)
        self.assertEqual(expected_combat_power(3, 5), 7930)
        self.assertEqual(expected_combat_power(3, 8), 11440)
        self.assertEqual(expected_combat_power(4, 2), 26650)
        values = [expected_combat_power(index, 1) for index in range(len(REALMS))]
        self.assertTrue(all(left < right for left, right in zip(values, values[1:])))

    def test_npc_expectations_and_player_recommendations_share_the_content_benchmark(self):
        self.assertEqual(recommended_combat_power(1, 1), 130)
        self.assertEqual(recommended_combat_power(1, 13), 364)
        self.assertEqual(recommended_combat_power(4, 2), 26650)
        self.assertEqual(recommended_combat_power(8, 2), 42900000)
        self.assertEqual(recommended_combat_power(8, 9), 81900000)
        for realm_index, realm in enumerate(REALMS):
            for layer in range(1, realm.layers + 1):
                self.assertEqual(
                    recommended_combat_power(realm_index, layer),
                    expected_combat_power(realm_index, layer),
                )

    def test_dlc_standard_power_bonuses_add_before_one_multiplier(self):
        tianji = WORLD_SYSTEMS["tianji_artifacts"]
        guixu = GUIXU_TIDE_CONTENT["settings"]
        old_enabled = tianji.get("enabled")
        old_tianji = tianji.get("standard_combat_power_bonus")
        old_dungeons = GUIXU_TIDE_CONTENT.get("dungeons")
        old_guixu = guixu.get("standard_combat_power_bonus")
        try:
            tianji["enabled"] = True
            tianji["standard_combat_power_bonus"] = 0.20
            GUIXU_TIDE_CONTENT["dungeons"] = [{"id":"test"}]
            guixu["standard_combat_power_bonus"] = 0.10
            self.assertAlmostEqual(standard_combat_power_dlc_bonus(), 0.30)
            self.assertEqual(expected_combat_power(3, 1), 2500 * 1.30)
            tianji["enabled"] = False
            GUIXU_TIDE_CONTENT["dungeons"] = []
            self.assertEqual(standard_combat_power_dlc_bonus(), 0.0)
            self.assertEqual(expected_combat_power(3, 1), 2500)
        finally:
            tianji["enabled"] = old_enabled
            tianji["standard_combat_power_bonus"] = old_tianji
            GUIXU_TIDE_CONTENT["dungeons"] = old_dungeons
            guixu["standard_combat_power_bonus"] = old_guixu

    def test_combat_assessment_uses_requested_power_bands(self):
        player = Player("战评", "supreme_metal", realm_index=3, layer=2, hp=0, mp=0)
        expected = recommended_combat_power(3, 2)
        cases = [
            (0.4, "你的战力养成严重不足，尚未形成当前境界应有的护道体系"),
            (0.65, "你的战力明显低于当前境界推荐线"),
            (0.9, "你的战力已经接近当前境界推荐线"),
            (1.1, "你的完整养成略高于当前境界推荐线"),
            (1.4, "你的战力体系已经明显超过当前境界推荐线"),
            (1.8, "你的额外资产与特殊体系令战力远超当前境界推荐线"),
        ]
        for ratio, message in cases:
            player.faction_combat_bonus = 0
            base = combat_power(player)
            player.faction_combat_bonus = expected * ratio - base
            self.assertEqual(combat_power_assessment(player), message)

    def test_opportunity_threshold_increases_inside_realm(self):
        player = Player("测试", "supreme_metal", realm_index=2, layer=1)
        first = opportunity_required(player)
        player.layer = 9
        self.assertGreater(opportunity_required(player), first)

    def test_elemental_compatibility(self):
        self.assertTrue(can_practice_technique("heavenly_metal_wood", "metal"))
        self.assertTrue(can_practice_technique("heavenly_metal_wood", "wood"))
        self.assertFalse(can_practice_technique("heavenly_metal_wood", "fire"))
        self.assertTrue(can_practice_technique("none", "neutral"))

    def test_root_opportunity_efficiency_order(self):
        ordered = [
            "otherworld", "law_time", "mutated_wind", "supreme_metal",
            "heavenly_metal_wood", "pseudo_all", "none",
        ]
        efficiencies = [ROOT_DEFINITIONS[root]["efficiency"] for root in ordered]
        self.assertTrue(all(left > right for left, right in zip(efficiencies, efficiencies[1:])))

    def test_five_element_count_uses_linear_efficiency_with_three_as_one(self):
        efficiencies = [
            ROOT_DEFINITIONS["supreme_metal"]["efficiency"],
            ROOT_DEFINITIONS["heavenly_metal_wood"]["efficiency"],
            ROOT_DEFINITIONS["heavenly_metal_wood_water"]["efficiency"],
            ROOT_DEFINITIONS["pseudo_metal_wood_water_fire"]["efficiency"],
            ROOT_DEFINITIONS["pseudo_all"]["efficiency"],
        ]
        self.assertEqual(efficiencies, [1.30, 1.15, 1.00, 0.85, 0.70])
        self.assertTrue(all(round(left - right, 2) == 0.15 for left, right in zip(efficiencies, efficiencies[1:])))

    def test_mutated_roots_have_no_five_element_mapping(self):
        self.assertTrue(can_practice_technique("mutated_thunder", "thunder"))
        self.assertFalse(can_practice_technique("mutated_thunder", "metal"))
        self.assertFalse(can_practice_technique("mutated_thunder", "wood"))

    def test_root_efficiency_is_outermost_and_zero_cannot_be_compensated(self):
        technique = Technique(opportunity_bonus=9, hp_bonus=.1, mp_bonus=.1, combat_bonus=10)
        player = Player("无根", "none", technique=technique)
        add_item(player, "fortune_talisman", 10)
        self.assertEqual(opportunity_multiplier(player), 0)

    def test_every_technique_has_all_four_required_attributes(self):
        for technique in TECHNIQUE_CATALOG.values():
            with self.subTest(technique=technique.name):
                self.assertGreater(technique.opportunity_bonus, 0)
                self.assertGreater(technique.hp_bonus, 0)
                self.assertGreater(technique.mp_bonus, 0)
                self.assertGreater(technique.combat_bonus, 0)
                self.assertTrue(technique.sources)
                self.assertAlmostEqual(sum(technique.sources.values()), 1.0)

    def test_catalog_contains_every_element_and_multiple_neutral_arts(self):
        elements = {technique.element for technique in TECHNIQUE_CATALOG.values()}
        self.assertTrue({"metal", "wood", "water", "fire", "earth", "wind", "thunder", "yin", "yang", "neutral"} <= elements)
        self.assertGreaterEqual(sum(technique.element == "neutral" for technique in TECHNIQUE_CATALOG.values()), 8)

    def test_item_effects_modify_their_declared_stats(self):
        player = Player("宝物", "supreme_metal", technique=Technique(opportunity_bonus=0.1))
        base_hp = max_hp(player)
        base_efficiency = opportunity_multiplier(player)
        add_item(player, "blood_ginseng")
        add_item(player, "fortune_talisman")
        self.assertGreater(max_hp(player), base_hp)
        self.assertGreater(opportunity_multiplier(player), base_efficiency)

    def test_identical_passive_items_stack_linearly_by_quantity(self):
        player = Player("叠宝", "supreme_metal", technique=Technique(opportunity_bonus=0.1))
        base_hp = max_hp(player)
        add_item(player, "blood_ginseng", 2)
        self.assertEqual(next(item.quantity for item in player.inventory if item.id == "blood_ginseng"), 2)
        self.assertEqual(max_hp(player) - base_hp, 56)
        add_item(player, "fortune_talisman", 2)
        self.assertAlmostEqual(opportunity_multiplier(player), 1.3 * 1.1 * 1.24)

    def test_karma_modifier_only_activates_in_main_slot(self):
        player = Player("因果", "supreme_metal", karma=100, technique=Technique(opportunity_bonus=0.1))
        base = effective_karma(player)
        assign_technique(player, TECHNIQUE_CATALOG["TECH_KARMA_MIRROR"], "support")
        self.assertEqual(effective_karma(player), base)
        assign_technique(player, TECHNIQUE_CATALOG["TECH_KARMA_MIRROR"], "main")
        self.assertLess(effective_karma(player), base)

    def test_qi_environment_curve_matches_design_points_and_limit(self):
        expected = {0: 0.25, 0.25: 0.55, 0.5: 0.75, 1: 1.0, 2: 1.25, 4: 1.45}
        for concentration, multiplier in expected.items():
            with self.subTest(concentration=concentration):
                self.assertAlmostEqual(qi_environment_multiplier(concentration), multiplier)
        self.assertAlmostEqual(qi_environment_multiplier(1_000_000), 1.75, places=5)
        with self.assertRaises(ValueError):
            qi_environment_multiplier(-0.01)

    def test_technique_sources_default_by_path_and_multi_source_uses_weighted_average(self):
        self.assertEqual(Technique(path="dao").sources, {"spirit": 1.0})
        self.assertEqual(Technique(path="demonic").sources, {"demon": 1.0})
        self.assertEqual(Technique(path="monster").sources, {"monster": 1.0})
        self.assertEqual(Technique(path="ghost").sources, {"yin": 1.0})
        mixed = Technique(sources={"spirit": 0.5, "demon": 0.5})
        self.assertAlmostEqual(technique_environment_multiplier(mixed, "human"), 0.5 * 1.0 + 0.5 * 0.55)

    def test_environment_changes_training_efficiency_but_not_combat_power(self):
        technique = TECHNIQUE_CATALOG["TECH_BLOOD_RIVER"]
        player = Player("魔修", "supreme_fire", realm_index=2, technique=technique, world="human")
        player.hp = max_hp(player)
        player.mp = max_mp(player)
        human_efficiency = opportunity_multiplier(player)
        human_power = combat_power(player)
        player.world = "true_demon"
        self.assertGreater(opportunity_multiplier(player), human_efficiency)
        self.assertEqual(combat_power(player), human_power)

    def test_only_equipped_training_slots_expose_live_environment_multiplier(self):
        player = Player("槽位", "supreme_metal")
        art = TECHNIQUE_CATALOG["TECH_COMMON_QI"]
        assign_technique(player, art, "combat")
        shown = public_player(player)
        self.assertIsNone(shown["technique_slots"]["combat"][0]["environment_multiplier"])
        assign_technique(player, art, "support")
        shown = public_player(player)
        self.assertEqual(shown["technique_slots"]["support"]["environment_multiplier"], 1.0)

    def test_qi_experience_uses_main_support_sources_and_location_efficiency(self):
        player = Player("纳气", "supreme_metal")
        player.technique = Technique(sources={"spirit": 1.0})
        player.support_technique = Technique(sources={"spirit": 0.5, "demon": 0.5})
        gains = grant_qi_experience(player, 10, {"spirit": 2, "demon": 0.5, "monster": 1, "yin": 1})
        self.assertEqual(gains, {"spirit": 30, "demon": 2.5, "monster": 0.0, "yin": 0.0})
        self.assertEqual(player.qi_experience["spirit"], 30)
        self.assertEqual(qi_level(24.99), 0)
        self.assertEqual(qi_level(qi_level_threshold(3)), 3)

    def test_recursive_combat_requirement_supports_ranges_and_blocks_equip(self):
        requirement = {"all": [
            {"source": {"id": "spirit", "op": ">=", "level": 3}},
            {"source": {"id": "demon", "op": "<=", "level": 2}},
        ]}
        self.assertTrue(valid_combat_requirement(requirement))
        self.assertTrue(combat_requirement_met(requirement, {"spirit": 3, "demon": 2}))
        self.assertFalse(combat_requirement_met(requirement, {"spirit": 3, "demon": 3}))
        self.assertIn("且", combat_requirement_display(requirement))
        art = copy.deepcopy(TECHNIQUE_CATALOG["TECH_VOID_CYCLE"])
        art.combat_requirements = requirement
        player = Player("清修", "supreme_metal")
        player.qi_experience["spirit"] = qi_level_threshold(3)
        assign_technique(player, art, "combat")
        active_power = combat_power(player)
        player.qi_experience["demon"] = qi_level_threshold(3)
        self.assertLess(combat_power(player), active_power)
        blocked = Player("驳杂", "supreme_metal")
        blocked.qi_experience["spirit"] = qi_level_threshold(3)
        blocked.qi_experience["demon"] = qi_level_threshold(3)
        with self.assertRaisesRegex(ValueError, "气等级不足"):
            assign_technique(blocked, art, "combat")

    def test_every_catalog_technique_has_valid_combat_requirement(self):
        self.assertTrue(all(valid_combat_requirement(art.combat_requirements) for art in TECHNIQUE_CATALOG.values()))
        buddhist = TECHNIQUE_CATALOG["TECH_KARMA_MIRROR"]
        text = combat_requirement_display(buddhist.combat_requirements)
        self.assertIn("灵气 >= 3级", text)
        self.assertIn("魔气 <= 4级", text)


if __name__ == "__main__":
    unittest.main()
