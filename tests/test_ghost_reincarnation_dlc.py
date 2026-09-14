import copy
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import ITEM_CATALOG, REALMS, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.ghost_system import (
    apply_soul_erosion,
    ensure_ghost_cultivation_state,
    grant_intrinsic_progression_if_new_highwater,
    reincarnation_breakthrough_bonus,
    spend_wangsheng_energy,
)
from cultivation_life.models import Item, Player
from cultivation_life.rules import max_hp, max_mp, opportunity_required, technique_scale


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

    def test_disabling_dlc_freezes_ghost_state_and_restores_base_stat_formula(self):
        player = Player("封印", "mutated_yin", path="ghost", realm_index=2, layer=4)
        ensure_ghost_cultivation_state(player)
        player.ghost_intrinsic_hp_current *= 0.5
        frozen = (
            player.ghost_intrinsic_hp_current,
            player.ghost_intrinsic_mp_current,
            player.ghost_soul_erosion_rate_pp,
        )
        config = WORLD_SYSTEMS["ghost_cultivation"]
        config["enabled"] = False
        try:
            definition = REALMS[player.realm_index]
            expected = 100 + int(definition.base_power ** 0.5 * 16) + player.layer * 8
            self.assertEqual(max_hp(player), expected)
            self.assertFalse(apply_soul_erosion(player, 10)["active"])
            self.assertEqual(
                (
                    player.ghost_intrinsic_hp_current,
                    player.ghost_intrinsic_mp_current,
                    player.ghost_soul_erosion_rate_pp,
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


if __name__ == "__main__":
    unittest.main()
