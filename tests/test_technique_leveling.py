from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.models import Item, Technique
from cultivation_life.rules import (
    TECHNIQUE_MAX_LEVEL,
    acquire_technique,
    add_technique_copy,
    add_item,
    assign_technique,
    ensure_technique_set,
    merge_technique_copies,
    technique_copy_count,
    technique_scale,
    upgrade_known_technique,
)
from cultivation_life.system.transformation_system import transformation_technique_limits


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class TechniqueLevelingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_level_multiplier_is_exactly_defined_through_level_nine(self):
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        for level, expected in enumerate((1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 2.4, 3.0), start=1):
            technique.level = level
            self.assertAlmostEqual(technique_scale(technique), expected)
        self.assertEqual(Technique(level=99).level, TECHNIQUE_MAX_LEVEL)

    def test_duplicate_enters_inventory_and_upgrade_syncs_every_slot(self):
        made = self.engine.create_game("合参功法", "supreme_metal", "dao", 19001)
        game = self.engine.store.load(made["id"])
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        self.assertTrue(acquire_technique(game.player, technique))
        assign_technique(game.player, copy.deepcopy(technique), "main")
        assign_technique(game.player, copy.deepcopy(technique), "support")
        assign_technique(game.player, copy.deepcopy(technique), "combat")
        self.assertFalse(acquire_technique(game.player, technique))
        self.assertEqual(len([row for row in game.player.known_techniques if row.id == technique.id]), 1)
        self.assertEqual(technique_copy_count(game.player, technique.id), 1)
        self.engine.store.save(game)

        shown = self.engine.upgrade_technique(made["id"], technique.id)
        known = next(row for row in shown["player"]["known_techniques"] if row["id"] == technique.id)
        self.assertEqual(known["level"], 2)
        self.assertAlmostEqual(known["level_multiplier"], 1.1)
        self.assertAlmostEqual(known["opportunity_bonus"], technique.opportunity_bonus * 1.1)
        self.assertEqual(known["upgrade_copies"], 0)
        saved = self.engine.store.load(made["id"])
        equipped = [saved.player.technique, saved.player.support_technique, *saved.player.combat_techniques]
        self.assertTrue(all(row.level == 2 for row in equipped if row and row.id == technique.id))

    def test_known_market_technique_remains_purchasable_as_copy(self):
        made = self.engine.create_game("重购功法", "supreme_metal", "dao", 19002)
        game = self.engine.store.load(made["id"])
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        acquire_technique(game.player, technique)
        game.player.realm_index = 1
        add_item(game.player, "spirit_stone", 1000)
        game.market_realm_index = 1
        game.market_world = "human"
        game.market_location_id = game.player.location_id
        game.market_age = game.player.age
        game.market_offers = [{
            "id":"repeat-manual", "kind":"technique", "content_id":technique.id,
            "name":technique.name, "description":"测试功法", "element":technique.element,
            "price":50, "tier":1, "tier_name":"练气", "market_name":"测试坊市",
            "world":"human", "location_id":game.player.location_id,
            "rare_next_tier":False, "sold":False, "locked":False,
        }]
        self.engine.store.save(game)

        before = self.engine.get_game(made["id"])["market"]["offers"][0]
        self.assertTrue(before["known"])
        self.assertFalse(before["owned"])
        shown = self.engine.buy_market_offer(made["id"], "repeat-manual")
        self.assertEqual(len([row for row in shown["player"]["known_techniques"] if row["id"] == technique.id]), 1)
        manual = next(item for item in shown["player"]["inventory"] if item.get("technique_id") == technique.id)
        self.assertEqual(manual["quantity"], 1)
        self.assertEqual(manual["technique_level"], 1)

    def test_upgrade_requires_same_name_and_same_level_manual(self):
        made = self.engine.create_game("同级合参", "supreme_metal", "dao", 19003)
        game = self.engine.store.load(made["id"])
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        acquire_technique(game.player, technique)
        add_technique_copy(game.player, technique, level=1)
        self.assertEqual(upgrade_known_technique(game.player, technique.id), 2)
        add_technique_copy(game.player, technique, level=1)
        with self.assertRaisesRegex(ValueError, "同名 Lv.2"):
            upgrade_known_technique(game.player, technique.id)
        self.assertEqual(technique_copy_count(game.player, technique.id, 1), 1)

    def test_two_equal_manuals_merge_into_next_level_manual(self):
        made = self.engine.create_game("合炼玉简", "supreme_metal", "dao", 19004)
        game = self.engine.store.load(made["id"])
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        acquire_technique(game.player, technique)
        add_technique_copy(game.player, technique, 2, level=1)
        self.assertEqual(merge_technique_copies(game.player, technique.id, 1), 2)
        self.assertEqual(technique_copy_count(game.player, technique.id, 1), 0)
        self.assertEqual(technique_copy_count(game.player, technique.id, 2), 1)
        add_technique_copy(game.player, technique, level=1)
        upgrade_known_technique(game.player, technique.id)
        self.assertEqual(upgrade_known_technique(game.player, technique.id), 3)

    def test_legacy_unlevelled_manual_migrates_to_level_one(self):
        made = self.engine.create_game("旧简迁移", "supreme_metal", "dao", 19005)
        game = self.engine.store.load(made["id"])
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        acquire_technique(game.player, technique)
        game.player.inventory.append(Item(
            id=f"technique_manual::{technique.id}", name=f"《{technique.name}》传承玉简",
            quantity=2, technique_id=technique.id, tags=["technique_manual"],
        ))
        ensure_technique_set(game.player)
        manual = next(item for item in game.player.inventory if item.technique_id == technique.id)
        self.assertEqual(manual.technique_level, 1)
        self.assertTrue(manual.id.endswith("::lv1"))
        self.assertEqual(manual.quantity, 2)

    def test_transformation_slots_scale_to_whole_slots(self):
        technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BEAST_TRANSFORMATION"])
        base_capacity, base_space = transformation_technique_limits(technique)
        technique.level = 6
        capacity, space = transformation_technique_limits(technique)
        self.assertGreaterEqual(capacity, base_capacity)
        self.assertGreaterEqual(space, base_space)
        self.assertLessEqual(space, capacity)


if __name__ == "__main__":
    unittest.main()
