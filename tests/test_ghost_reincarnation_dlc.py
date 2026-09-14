import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cultivation_life.content_registry import ITEM_CATALOG, REALMS, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.ghost_system import (
    accumulate_soul_erosion_time,
    apply_soul_erosion,
    can_reincarnate,
    ensure_ghost_cultivation_state,
    grant_intrinsic_progression_if_new_highwater,
    perform_reincarnation,
    reincarnation_breakthrough_bonus,
    spend_wangsheng_energy,
)
from cultivation_life.models import Item, Player
from cultivation_life.rules import add_item, max_hp, max_mp, opportunity_required, technique_scale


class GhostReincarnationDlcTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_dlc_config_is_loaded_under_official_name(self):
        config = WORLD_SYSTEMS["ghost_cultivation"]
        self.assertTrue(config["enabled"])
        self.assertEqual(config["erosion_growth_per_time_unit_pp"], 0.0002)
        self.assertEqual(config["reincarnation_final_probability_cap"], 0.98)
        self.assertEqual(
            next(row for row in self.engine.achievements.definitions if row["id"] == "ghost_first_reincarnation")["source"]["name"],
            "百鬼夜行:轮回往生",
        )

    def test_intrinsic_external_refactor_preserves_non_ghost_totals(self):
        player = Player("守常", "supreme_metal", realm_index=3, layer=5, body_training=7)
        player.support_technique = copy.deepcopy(next(
            technique for technique in TECHNIQUE_CATALOG.values()
            if technique.category == "spiritual" and technique.hp_bonus > 0 and technique.mp_bonus > 0
        ))
        player.inventory = [Item("test", "试器", quantity=2, hp_bonus=37, mp_bonus=29)]
        player.faction_hp_bonus, player.faction_mp_bonus = 41, 43
        player.natal_artifact_hp_bonus, player.natal_artifact_mp_bonus = 17, 19
        definition = REALMS[player.realm_index]
        old_hp_base = 100 + int(definition.base_power ** 0.5 * 16) + player.layer * 8 + player.body_training * 12
        old_mp_base = 40 + int(definition.base_power ** 0.5 * 20) + player.layer * 11
        expected_hp = round(
            old_hp_base * (1 + player.support_technique.hp_bonus * technique_scale(player.support_technique))
            + 2 * 37 + 41 + 17
        )
        expected_mp = round(
            old_mp_base * (1 + player.support_technique.mp_bonus * technique_scale(player.support_technique))
            + 2 * 29 + 43 + 19
        )
        self.assertEqual(max_hp(player), expected_hp)
        self.assertEqual(max_mp(player), expected_mp)

    def test_external_power_is_scaled_by_soul_carry_ratio(self):
        player = Player("残灯", "mutated_yin", path="ghost", realm_index=2, layer=1)
        ensure_ghost_cultivation_state(player)
        player.ghost_intrinsic_hp_reference = 1000.0
        player.ghost_intrinsic_hp_current = 600.0
        player.ghost_intrinsic_mp_reference = 800.0
        player.ghost_intrinsic_mp_current = 400.0
        player.inventory = [Item("test", "魂甲", hp_bonus=1000, mp_bonus=1000)]
        self.assertEqual(max_hp(player), 1200)
        self.assertEqual(max_mp(player), 900)

    def test_all_external_sources_can_change_without_mutating_intrinsic_state(self):
        player = Player("器外之魂", "mutated_yin", path="ghost", realm_index=3, layer=4)
        ensure_ghost_cultivation_state(player)
        intrinsic = (
            player.ghost_intrinsic_hp_reference, player.ghost_intrinsic_hp_current,
            player.ghost_intrinsic_mp_reference, player.ghost_intrinsic_mp_current,
        )
        support = copy.deepcopy(next(
            technique for technique in TECHNIQUE_CATALOG.values()
            if technique.category == "spiritual" and technique.hp_bonus > 0 and technique.mp_bonus > 0
        ))
        player.support_technique = support
        player.inventory = [Item("external", "外物", hp_bonus=300, mp_bonus=400)]
        player.faction_hp_bonus, player.faction_mp_bonus = 500, 600
        player.natal_artifact_hp_bonus, player.natal_artifact_mp_bonus = 700, 800
        max_hp(player), max_mp(player)
        player.support_technique = None
        player.inventory.clear()
        player.faction_hp_bonus = player.faction_mp_bonus = 0
        player.natal_artifact_hp_bonus = player.natal_artifact_mp_bonus = 0
        self.assertEqual(
            (
                player.ghost_intrinsic_hp_reference, player.ghost_intrinsic_hp_current,
                player.ghost_intrinsic_mp_reference, player.ghost_intrinsic_mp_current,
            ),
            intrinsic,
        )

    def test_external_power_cannot_prevent_soul_dispersal(self):
        shown = self.engine.create_game("灭魂", "mutated_yin", "ghost", 903, start_world="hell")
        game = self.engine.store.load(shown["id"])
        game.player.inventory = [Item("test", "万魂甲", hp_bonus=1_000_000, mp_bonus=1_000_000)]
        game.player.ghost_intrinsic_hp_current = 10.0
        game.player.ghost_intrinsic_mp_current = 10.0
        game.player.ghost_soul_erosion_rate_pp = 100.0
        self.assertFalse(self.engine._apply_soul_erosion_units(game, 1))
        self.assertFalse(game.player.alive)
        self.assertIn("魂飞魄散", game.player.death_reason)

    def test_batch_erosion_matches_unit_by_unit_and_first_unit_is_harmless(self):
        player = Player("长夜", "mutated_yin", path="ghost", realm_index=1, layer=1)
        ensure_ghost_cultivation_state(player)
        repeated = copy.deepcopy(player)
        initial_hp = player.ghost_intrinsic_hp_current
        apply_soul_erosion(player, 30)
        for _ in range(30):
            apply_soul_erosion(repeated, 1)
        self.assertAlmostEqual(player.ghost_intrinsic_hp_current, repeated.ghost_intrinsic_hp_current, places=10)
        self.assertAlmostEqual(player.ghost_intrinsic_mp_current, repeated.ghost_intrinsic_mp_current, places=10)
        self.assertAlmostEqual(player.ghost_soul_erosion_rate_pp, 0.006, places=10)
        first = copy.deepcopy(Player("初魂", "mutated_yin", path="ghost"))
        ensure_ghost_cultivation_state(first)
        first_hp = first.ghost_intrinsic_hp_current
        apply_soul_erosion(first, 1)
        self.assertEqual(first.ghost_intrinsic_hp_current, first_hp)
        self.assertEqual(initial_hp, repeated.ghost_intrinsic_hp_reference)

    def test_erosion_threshold_logs_only_once_and_clamps_combat_resources(self):
        shown = self.engine.create_game("界灯", "mutated_yin", "ghost", 911, start_world="hell")
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.ghost_intrinsic_hp_current = player.ghost_intrinsic_hp_reference * 0.89
        player.ghost_intrinsic_mp_current = player.ghost_intrinsic_mp_reference * 0.89
        player.hp = player.mp = 10**9
        self.assertTrue(self.engine._apply_soul_erosion_units(game, 1))
        self.assertLessEqual(player.hp, max_hp(player))
        self.assertLessEqual(player.mp, max_mp(player))
        self.assertEqual(
            sum(record.event_id == "SYS_GHOST_EROSION_90" for record in game.history), 1,
        )
        self.assertTrue(self.engine._apply_soul_erosion_units(game, 1))
        self.assertEqual(
            sum(record.event_id == "SYS_GHOST_EROSION_90" for record in game.history), 1,
        )

    def test_reincarnation_preserves_soul_and_highwater_but_clears_wangsheng(self):
        shown = self.engine.create_game("归途", "mutated_yin", "ghost", 901, start_world="hell")
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.realm_index, player.layer = 3, REALMS[3].layers
        grant_intrinsic_progression_if_new_highwater(player)
        player.opportunity = opportunity_required(player)
        player.ghost_wangsheng_energy = 7
        before = (
            player.ghost_intrinsic_hp_reference, player.ghost_intrinsic_hp_current,
            player.ghost_intrinsic_mp_reference, player.ghost_intrinsic_mp_current,
        )
        self.engine.store.save(game)

        reincarnated = self.engine.reincarnate_ghost(game.id)
        player = self.engine.store.load(game.id).player
        self.assertEqual((player.realm_index, player.layer, player.opportunity), (1, 1, 0))
        self.assertEqual(player.ghost_wangsheng_energy, 0)
        self.assertEqual(player.ghost_reincarnation_imprints, {"3": 1})
        self.assertEqual((player.ghost_intrinsic_highwater_realm, player.ghost_intrinsic_highwater_layer), (3, 9))
        self.assertEqual(
            (
                player.ghost_intrinsic_hp_reference, player.ghost_intrinsic_hp_current,
                player.ghost_intrinsic_mp_reference, player.ghost_intrinsic_mp_current,
            ),
            before,
        )
        self.assertEqual(reincarnated["ghost_system"]["last_anchor"]["realm_index"], 3)

        game = self.engine.store.load(game.id)
        player = game.player
        reference = (player.ghost_intrinsic_hp_reference, player.ghost_intrinsic_mp_reference)
        self.engine._complete_minor_breakthrough(game, random.Random(1), "练气一层")
        self.assertEqual((player.ghost_intrinsic_hp_reference, player.ghost_intrinsic_mp_reference), reference)
        self.assertEqual(player.ghost_wangsheng_energy, 1)

    def test_player_only_reincarnation_transition_preserves_unrelated_progress(self):
        player = Player("百业不忘", "mutated_yin", path="ghost", realm_index=4, layer=9, age=777)
        ensure_ghost_cultivation_state(player)
        player.opportunity = opportunity_required(player)
        player.body_training = 33
        player.divine_sense_rank = 12
        player.karma = 19
        player.sha_qi = 23
        player.inventory = [Item("keepsake", "旧世信物", quantity=2)]
        player.ghost_wangsheng_energy = 9
        player.ghost_soul_erosion_rate_pp = 0.1234
        player.ghost_soul_erosion_time_progress = 0.5
        self.assertTrue(can_reincarnate(player))
        transition = perform_reincarnation(player)
        self.assertEqual((player.realm_index, player.layer, player.opportunity), (1, 1, 0))
        self.assertEqual((player.age, player.body_training, player.divine_sense_rank), (777, 33, 12))
        self.assertEqual((player.karma, player.sha_qi, player.inventory[0].quantity), (19, 23, 2))
        self.assertEqual(player.ghost_soul_erosion_rate_pp, 0.1234)
        self.assertEqual(player.ghost_soul_erosion_time_progress, 0.5)
        self.assertEqual(transition["wangsheng_lost"], 9)

    def test_reincarnation_wangsheng_clearing_follows_dlc_config(self):
        player = Player("留息", "mutated_yin", path="ghost", realm_index=3, layer=9)
        ensure_ghost_cultivation_state(player)
        player.opportunity = opportunity_required(player)
        player.ghost_wangsheng_energy = 9
        config = WORLD_SYSTEMS["ghost_cultivation"]
        old_value = config["clear_wangsheng_on_reincarnation"]
        config["clear_wangsheng_on_reincarnation"] = False
        try:
            transition = perform_reincarnation(player)
        finally:
            config["clear_wangsheng_on_reincarnation"] = old_value
        self.assertEqual(player.ghost_wangsheng_energy, 9)
        self.assertEqual(transition["wangsheng_lost"], 0)

    def test_high_realm_imprints_cover_only_the_road_below_them(self):
        player = Player("照世", "mutated_yin", path="ghost", realm_index=3, layer=9)
        ensure_ghost_cultivation_state(player)
        player.ghost_reincarnation_imprints = {"1": 1, "2": 3, "3": 2}
        self.assertAlmostEqual(reincarnation_breakthrough_bonus(player, 1), 0.30)
        self.assertAlmostEqual(reincarnation_breakthrough_bonus(player, 2), 0.25)
        self.assertAlmostEqual(reincarnation_breakthrough_bonus(player, 3), 0.10)
        self.assertAlmostEqual(reincarnation_breakthrough_bonus(player, 4), 0.0)

    def test_v1_imprints_migrate_into_v2_achievement_milestone(self):
        player = Player("旧魂", "mutated_yin", path="ghost", realm_index=3, layer=9)
        player.ghost_reincarnation_imprints = {"1": 2, "2": 3, "3": 5}
        ensure_ghost_cultivation_state(player)
        self.assertEqual(player.milestones["ghost_reincarnations"], 10)

    def test_lower_reincarnation_anchor_never_lowers_intrinsic_highwater(self):
        player = Player("折返", "mutated_yin", path="ghost", realm_index=4, layer=9)
        ensure_ghost_cultivation_state(player)
        highwater = (player.ghost_intrinsic_highwater_realm, player.ghost_intrinsic_highwater_layer)
        player.realm_index, player.layer = 2, 9
        player.opportunity = opportunity_required(player)
        perform_reincarnation(player)
        self.assertEqual((player.ghost_last_reincarnation_realm, player.ghost_last_reincarnation_layer), (2, 9))
        self.assertEqual((player.ghost_intrinsic_highwater_realm, player.ghost_intrinsic_highwater_layer), highwater)

    def test_only_new_historical_height_adds_intrinsic_without_healing_old_loss(self):
        player = Player("越旧途", "mutated_yin", path="ghost", realm_index=3, layer=9)
        ensure_ghost_cultivation_state(player)
        player.ghost_intrinsic_hp_current -= 200
        player.ghost_intrinsic_mp_current -= 150
        loss_before = (
            player.ghost_intrinsic_hp_reference - player.ghost_intrinsic_hp_current,
            player.ghost_intrinsic_mp_reference - player.ghost_intrinsic_mp_current,
        )
        player.realm_index, player.layer = 4, 1
        hp_gain, mp_gain = grant_intrinsic_progression_if_new_highwater(player)
        self.assertGreater(hp_gain, 0)
        self.assertGreater(mp_gain, 0)
        self.assertEqual(
            (
                player.ghost_intrinsic_hp_reference - player.ghost_intrinsic_hp_current,
                player.ghost_intrinsic_mp_reference - player.ghost_intrinsic_mp_current,
            ),
            loss_before,
        )
        self.assertEqual((player.ghost_intrinsic_highwater_realm, player.ghost_intrinsic_highwater_layer), (4, 1))

    def test_permanent_intrinsic_consumable_adds_new_growth_without_healing_old_loss(self):
        item_id = "test_permanent_intrinsic_pill"
        ITEM_CATALOG[item_id] = Item(
            item_id, "本源试丹", permanent_intrinsic_hp_bonus=37,
            permanent_intrinsic_mp_bonus=29, tags=["pill", "permanent_intrinsic"],
        )
        try:
            shown = self.engine.create_game("新源", "mutated_yin", "ghost", 910, start_world="hell")
            game = self.engine.store.load(shown["id"])
            player = game.player
            player.inventory.append(copy.deepcopy(ITEM_CATALOG[item_id]))
            player.ghost_intrinsic_hp_current -= 20
            player.ghost_intrinsic_mp_current -= 10
            old = (
                player.ghost_intrinsic_hp_reference, player.ghost_intrinsic_hp_current,
                player.ghost_intrinsic_mp_reference, player.ghost_intrinsic_mp_current,
            )
            self.engine.store.save(game)
            self.engine.use_item(game.id, item_id)
            saved = self.engine.store.load(game.id).player
            self.assertEqual(saved.ghost_intrinsic_hp_reference, old[0] + 37)
            self.assertEqual(saved.ghost_intrinsic_hp_current, old[1] + 37)
            self.assertEqual(saved.ghost_intrinsic_mp_reference, old[2] + 29)
            self.assertEqual(saved.ghost_intrinsic_mp_current, old[3] + 29)
            self.assertEqual(
                saved.ghost_intrinsic_hp_reference - saved.ghost_intrinsic_hp_current,
                old[0] - old[1],
            )
        finally:
            ITEM_CATALOG.pop(item_id, None)

    def test_reincarnation_bonus_can_display_ten_thousand_percent_but_effective_chance_caps_at_98(self):
        player = Player("百炼", "mutated_yin", path="ghost", realm_index=3, layer=9)
        ensure_ghost_cultivation_state(player)
        player.ghost_reincarnation_imprints = {"3": 2000}
        chance = self.engine._breakthrough_chance(player, major=True)
        self.assertEqual(chance["reincarnation_bonus"], 100.0)
        self.assertEqual(chance["final"], 0.98)

    def test_wangsheng_reduces_future_rate_without_healing_existing_damage(self):
        player = Player("往生", "mutated_yin", path="ghost", realm_index=3, layer=1)
        ensure_ghost_cultivation_state(player)
        player.ghost_intrinsic_hp_current = 3000.0
        player.ghost_intrinsic_mp_current = 2500.0
        player.ghost_soul_erosion_rate_pp = 0.08
        player.ghost_wangsheng_energy = 2
        before = (player.ghost_intrinsic_hp_current, player.ghost_intrinsic_mp_current)
        cost, reduction = spend_wangsheng_energy(player)
        self.assertEqual(cost, 2)
        self.assertAlmostEqual(reduction, 0.02)
        self.assertAlmostEqual(player.ghost_soul_erosion_rate_pp, 0.06)
        self.assertEqual((player.ghost_intrinsic_hp_current, player.ghost_intrinsic_mp_current), before)

    def test_v2_spend_all_wangsheng_and_reincarnation_preview(self):
        shown = self.engine.create_game("万息", "mutated_yin", "ghost", 904, start_world="hell")
        game = self.engine.store.load(shown["id"])
        player = game.player
        player.realm_index, player.layer = 3, REALMS[3].layers
        grant_intrinsic_progression_if_new_highwater(player)
        player.opportunity = opportunity_required(player)
        player.ghost_soul_erosion_rate_pp = 0.05
        player.ghost_wangsheng_energy = 5
        self.engine.store.save(game)

        before = self.engine.get_game(game.id)["ghost_system"]
        self.assertEqual(before["wangsheng_available_uses"], 2)
        self.assertEqual(before["reincarnation_preview"]["source"], "结丹9层")
        self.assertEqual(before["reincarnation_preview"]["next_imprint_count"], 1)
        self.assertEqual(before["breakthrough_probability_cap"], 0.98)

        after = self.engine.spend_wangsheng(game.id, True)
        self.assertEqual(after["ghost_system"]["wangsheng"], 1)
        self.assertAlmostEqual(after["ghost_system"]["erosion_rate_pp"], 0.01)
        saved = self.engine.store.load(game.id)
        self.assertEqual(saved.player.milestones["ghost_wangsheng_spent"], 4)

    def test_every_main_action_unit_applies_exactly_one_erosion_step(self):
        shown = self.engine.create_game("时蚀", "mutated_yin", "ghost", 905, start_world="hell")
        game = self.engine.store.load(shown["id"])
        expected = copy.deepcopy(game.player)
        apply_soul_erosion(expected, 3)
        with (
            patch.object(self.engine, "_advance_world_year", return_value=True),
            patch.object(self.engine, "_select_event", return_value=None),
            patch.object(self.engine, "_maybe_probability_story_event", return_value=False),
        ):
            self.engine.advance(game.id, "rest", 3)
        saved = self.engine.store.load(game.id).player
        self.assertAlmostEqual(saved.ghost_soul_erosion_rate_pp, expected.ghost_soul_erosion_rate_pp)
        self.assertAlmostEqual(saved.ghost_intrinsic_hp_current, expected.ghost_intrinsic_hp_current)
        self.assertAlmostEqual(saved.ghost_intrinsic_mp_current, expected.ghost_intrinsic_mp_current)

    def test_all_time_sources_share_one_fractional_erosion_clock(self):
        shown = self.engine.create_game("百年一蚀", "mutated_yin", "ghost", 914, start_world="hell")
        game = self.engine.store.load(shown["id"])
        game.player.realm_index, game.player.layer = 8, 1
        grant_intrinsic_progression_if_new_highwater(game.player)
        original_hp = game.player.ghost_intrinsic_hp_current

        self.assertTrue(self.engine._advance_soul_erosion_time(game, 30))
        self.assertAlmostEqual(game.player.ghost_soul_erosion_time_progress, 0.30)
        self.assertEqual(game.player.ghost_soul_erosion_rate_pp, 0)
        self.assertTrue(self.engine._advance_soul_erosion_time(game, 20))
        self.assertAlmostEqual(game.player.ghost_soul_erosion_time_progress, 0.50)
        self.assertTrue(self.engine._advance_soul_erosion_time(game, 49))
        self.assertAlmostEqual(game.player.ghost_soul_erosion_time_progress, 0.99)
        self.assertEqual(game.player.ghost_soul_erosion_rate_pp, 0)
        self.assertTrue(self.engine._advance_soul_erosion_time(game, 1))
        self.assertEqual(game.player.ghost_soul_erosion_time_progress, 0)
        self.assertAlmostEqual(game.player.ghost_soul_erosion_rate_pp, 0.0002)
        self.assertEqual(game.player.ghost_intrinsic_hp_current, original_hp)

    def test_high_realm_travel_and_one_year_prison_accumulate_without_rounding_up(self):
        shown = self.engine.create_game("寸年不欺", "mutated_yin", "ghost", 915, start_world="hell")
        game = self.engine.store.load(shown["id"])
        game.player.realm_index, game.player.layer = 8, 1
        grant_intrinsic_progression_if_new_highwater(game.player)
        self.engine.store.save(game)
        travel_years = self.engine.maps.travel_plan(
            "hell", game.player.location_id, "forgetful_river", game.player.realm_index,
        ).years
        self.assertLess(travel_years, 100)
        with patch.object(self.engine, "_advance_world_year", return_value=True):
            self.engine.travel_map(game.id, "forgetful_river")
        after_travel = self.engine.store.load(game.id)
        self.assertEqual(after_travel.player.ghost_soul_erosion_rate_pp, 0)
        self.assertAlmostEqual(
            after_travel.player.ghost_soul_erosion_time_progress, travel_years / 100,
        )

        after_travel.player.hostility["sect:ghost"] = 10
        after_travel.player.imprisonment = {
            "key": "sect:ghost", "name": "幽狱", "remaining_years": 1,
            "captured_age": after_travel.player.age, "hostility": 10,
            "sentence_years": 1, "hostility_reduction_per_year": 10,
        }
        self.engine.store.save(after_travel)
        with patch.object(self.engine, "_check_tribulation", return_value=None):
            result = self.engine.prison_action(game.id, "endure")
        saved = self.engine.store.load(game.id).player
        self.assertTrue(saved.alive)
        self.assertEqual(saved.ghost_soul_erosion_rate_pp, 0)
        self.assertAlmostEqual(
            saved.ghost_soul_erosion_time_progress, (travel_years + 1) / 100,
        )
        self.assertEqual(result["ghost_system"]["erosion_time"]["time_unit_years"], 100)

    def test_travel_field_reclaim_and_prison_years_all_apply_erosion(self):
        travel = self.engine.create_game("远魂", "mutated_yin", "ghost", 906, start_world="hell")
        travel_game = self.engine.store.load(travel["id"])
        travel_years = self.engine.maps.travel_plan(
            "hell", travel_game.player.location_id, "forgetful_river", travel_game.player.realm_index,
        ).years
        with patch.object(self.engine, "_advance_world_year", return_value=True):
            self.engine.travel_map(travel_game.id, "forgetful_river")
        self.assertAlmostEqual(
            self.engine.store.load(travel_game.id).player.ghost_soul_erosion_rate_pp,
            travel_years * 0.0002,
        )

        field = self.engine.create_game(
            "田魂", "mutated_yin", "ghost", 907, preset_id="ghost_core", start_world="hell",
        )
        field_game = self.engine.store.load(field["id"])
        add_item(field_game.player, "spirit_stone", 100000)
        self.engine.store.save(field_game)
        with patch.object(self.engine, "_advance_world_year", return_value=True):
            result = self.engine.reclaim_spirit_field(field_game.id)
        self.assertGreater(result["player"]["age"], field_game.player.age)
        self.assertGreater(self.engine.store.load(field_game.id).player.ghost_soul_erosion_rate_pp, 0)

        prison = self.engine.create_game(
            "狱魂", "mutated_yin", "ghost", 908, preset_id="ghost_core", start_world="hell",
        )
        prison_game = self.engine.store.load(prison["id"])
        prison_game.player.hostility["sect:ghost"] = 10
        prison_game.player.imprisonment = {
            "key": "sect:ghost", "name": "幽狱", "remaining_years": 1,
            "captured_age": prison_game.player.age, "hostility": 10,
            "sentence_years": 1, "hostility_reduction_per_year": 10,
        }
        self.engine.store.save(prison_game)
        self.engine.prison_action(prison_game.id, "endure")
        self.assertAlmostEqual(
            self.engine.store.load(prison_game.id).player.ghost_soul_erosion_rate_pp, 0.0002,
        )

    def test_reenable_after_disabled_progress_reconciles_new_historical_height_once(self):
        shown = self.engine.create_game("续蚀", "mutated_yin", "ghost", 909, start_world="hell")
        game = self.engine.store.load(shown["id"])
        old_reference = game.player.ghost_intrinsic_hp_reference
        config = WORLD_SYSTEMS["ghost_cultivation"]
        config["enabled"] = False
        try:
            game.player.realm_index, game.player.layer = 4, 1
            game.player.body_training += 2
            game.player.permanent_intrinsic_hp_bonus += 17
            game.player.permanent_intrinsic_mp_bonus += 19
            self.engine.store.save(game)
        finally:
            config["enabled"] = True
        first = self.engine.get_game(game.id)
        migrated = self.engine.store.load(game.id).player
        self.assertEqual((migrated.ghost_intrinsic_highwater_realm, migrated.ghost_intrinsic_highwater_layer), (4, 1))
        self.assertGreater(migrated.ghost_intrinsic_hp_reference, old_reference)
        reference = migrated.ghost_intrinsic_hp_reference
        self.engine.get_game(game.id)
        self.assertEqual(self.engine.store.load(game.id).player.ghost_intrinsic_hp_reference, reference)
        self.assertEqual(first["ghost_system"]["highwater"]["realm_index"], 4)

    def test_reenable_persists_independent_growth_even_without_new_realm_highwater(self):
        shown = self.engine.create_game("同境新源", "mutated_yin", "ghost", 912, start_world="hell")
        game = self.engine.store.load(shown["id"])
        old_hp = game.player.ghost_intrinsic_hp_reference
        old_mp = game.player.ghost_intrinsic_mp_reference
        config = WORLD_SYSTEMS["ghost_cultivation"]
        config["enabled"] = False
        try:
            game.player.body_training += 2
            game.player.permanent_intrinsic_hp_bonus += 17
            game.player.permanent_intrinsic_mp_bonus += 19
            self.engine.store.save(game)
        finally:
            config["enabled"] = True
        self.engine.get_game(game.id)
        migrated = self.engine.store.load(game.id).player
        self.assertGreater(migrated.ghost_intrinsic_hp_reference, old_hp)
        self.assertGreater(migrated.ghost_intrinsic_mp_reference, old_mp)
        first = (
            migrated.ghost_intrinsic_hp_reference,
            migrated.ghost_intrinsic_mp_reference,
        )
        self.engine.get_game(game.id)
        migrated_again = self.engine.store.load(game.id).player
        self.assertEqual(
            (migrated_again.ghost_intrinsic_hp_reference, migrated_again.ghost_intrinsic_mp_reference),
            first,
        )

    def test_disabling_dlc_freezes_ghost_state_and_restores_base_stat_formula(self):
        player = Player("封印", "mutated_yin", path="ghost", realm_index=2, layer=4)
        ensure_ghost_cultivation_state(player)
        player.ghost_intrinsic_hp_current *= 0.5
        frozen = (
            player.ghost_intrinsic_hp_current,
            player.ghost_intrinsic_mp_current,
            player.ghost_soul_erosion_rate_pp,
            player.ghost_soul_erosion_time_progress,
        )
        config = WORLD_SYSTEMS["ghost_cultivation"]
        config["enabled"] = False
        try:
            definition = REALMS[player.realm_index]
            expected = 100 + int(definition.base_power ** 0.5 * 16) + player.layer * 8
            self.assertEqual(max_hp(player), expected)
            self.assertFalse(apply_soul_erosion(player, 10)["active"])
            self.assertEqual(accumulate_soul_erosion_time(player, 10), 0)
            self.assertEqual(
                (
                    player.ghost_intrinsic_hp_current,
                    player.ghost_intrinsic_mp_current,
                    player.ghost_soul_erosion_rate_pp,
                    player.ghost_soul_erosion_time_progress,
                ),
                frozen,
            )
        finally:
            config["enabled"] = True

    def test_ghost_breakthrough_medicine_is_blocked_in_use_and_probability_layers(self):
        shown = self.engine.create_game("无丹", "mutated_yin", "ghost", 902, preset_id="ghost_core")
        game = self.engine.store.load(shown["id"])
        aid = next(
            item for item in ITEM_CATALOG.values()
            if item.breakthrough_bonus > 0 and item.breakthrough_scope == f"minor:{game.player.realm_index}"
            and "ghost" in item.tags
        )
        game.player.inventory.append(copy.deepcopy(aid))
        game.player.active_breakthrough_aids = [aid.id]
        chance = self.engine._breakthrough_chance(game.player, major=False)
        self.assertEqual(chance["aid_bonus"], 0.0)
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "鬼修唯有自渡轮回"):
            self.engine.use_item(game.id, aid.id)

    def test_ghost_cannot_bypass_pill_ban_with_a_hybrid_permanent_item(self):
        item_id = "test_hybrid_breakthrough_pill"
        ITEM_CATALOG[item_id] = Item(
            item_id, "两用禁丹", breakthrough_bonus=0.5,
            breakthrough_scope="minor:3", permanent_intrinsic_hp_bonus=99,
            tags=["pill", "permanent_intrinsic", "breakthrough"],
        )
        try:
            shown = self.engine.create_game(
                "不饮禁丹", "mutated_yin", "ghost", 913,
                preset_id="ghost_core", start_world="hell",
            )
            game = self.engine.store.load(shown["id"])
            game.player.inventory.append(copy.deepcopy(ITEM_CATALOG[item_id]))
            old_reference = game.player.ghost_intrinsic_hp_reference
            self.engine.store.save(game)
            with self.assertRaisesRegex(ValueError, "鬼修唯有自渡轮回"):
                self.engine.use_item(game.id, item_id)
            saved = self.engine.store.load(game.id).player
            self.assertEqual(saved.ghost_intrinsic_hp_reference, old_reference)
            self.assertTrue(any(item.id == item_id for item in saved.inventory))
        finally:
            ITEM_CATALOG.pop(item_id, None)


if __name__ == "__main__":
    unittest.main()
