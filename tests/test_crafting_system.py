import copy
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.crafting_system import (
    crafted_artifact_bonuses, crafting_material_definitions, make_crafting_material_instance,
)
from cultivation_life.engine import GameEngine
from cultivation_life.models import Item, Player
from cultivation_life.rules import add_item


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class CraftingSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")
        self.game_id = self.engine.create_game(
            "器师", "supreme_metal", "dao", 44001, preset_id="core",
        )["id"]

    def tearDown(self):
        self.temp.cleanup()

    def _give_human_recipe(self):
        game = self.engine.store.load(self.game_id)
        definitions = crafting_material_definitions()
        rng = random.Random(17)
        instances = [
            make_crafting_material_instance(definitions[material_id], rng, source="测试", origin_world="human")
            for material_id in ("human_cold_iron", "human_cloud_silk", "human_cloud_silk", "human_sun_fire")
        ]
        game.player.crafting_materials.extend(instances)
        self.engine.store.save(game)
        return instances

    @staticmethod
    def _payload(instances):
        return {
            "mold_id":"umbrella", "primary_id":instances[0]["id"],
            "secondary_a_id":instances[1]["id"], "secondary_b_id":instances[2]["id"],
            "quench_id":instances[3]["id"], "name":"千机伞",
            "allocations":{"combat_power":20,"max_hp":10,"max_mp":10,"breakthrough_bonus":5},
        }

    def test_exact_five_slot_recipe_previews_and_never_fails(self):
        instances = self._give_human_recipe()
        preview = self.engine.preview_crafting(self.game_id, self._payload(instances))
        self.assertEqual(preview["mold"]["id"], "umbrella")
        self.assertEqual(len(preview["selected_materials"]), 4)
        self.assertAlmostEqual(sum(preview["quality_probabilities"].values()), 1.0, places=5)
        shown = self.engine.forge_crafted_artifact(self.game_id, self._payload(instances))
        artifact = shown["crafting_system"]["artifacts"][0]
        self.assertEqual(artifact["name"], "千机伞")
        self.assertIn(artifact["quality"], shown["crafting_system"]["quality_names"])
        self.assertLessEqual(artifact["actual_stats"]["breakthrough_bonus"], .05)
        self.assertEqual(len(shown["crafting_system"]["materials"]), 0)
        bag_item = next(row for row in shown["player"]["inventory"] if row.get("crafted_artifact_id") == artifact["id"])
        self.assertEqual(bag_item["description"], artifact["description"])
        self.assertIn("equipment", bag_item["tags"])

    def test_same_instance_cannot_fill_two_slots(self):
        instances = self._give_human_recipe()
        payload = self._payload(instances)
        payload["secondary_b_id"] = payload["secondary_a_id"]
        with self.assertRaisesRegex(ValueError, "不同实例"):
            self.engine.preview_crafting(self.game_id, payload)

    def test_all_bag_artifacts_stack_except_breakthrough_uses_highest_capped_value(self):
        player = Player("器师", "supreme_metal")
        player.crafted_artifacts = [
            {"id":"a", "actual_stats":{"combat_power":100,"max_hp":20,"breakthrough_bonus":.03}},
            {"id":"b", "actual_stats":{"combat_power":200,"max_hp":30,"breakthrough_bonus":.08}},
        ]
        player.inventory = [
            Item("a", "甲", crafted_artifact_id="a"),
            Item("b", "乙", crafted_artifact_id="b"),
        ]
        bonuses = crafted_artifact_bonuses(player)
        self.assertEqual(bonuses["combat_power"], 300)
        self.assertEqual(bonuses["max_hp"], 50)
        self.assertEqual(bonuses["breakthrough_bonus"], .05)

    def test_old_save_defaults_crafting_state_without_schema_move(self):
        game = self.engine.store.load(self.game_id)
        raw = game.to_dict()
        for key in (
            "crafting_materials", "crafted_artifacts", "equipped_crafted_artifact_ids",
            "crafting_blueprints", "crafting_sequence",
        ):
            raw["player"].pop(key, None)
        restored = type(game).from_dict(copy.deepcopy(raw))
        self.assertEqual(restored.player.crafted_artifacts, [])
        self.assertEqual(restored.player.crafting_materials, [])
        self.assertEqual(restored.version, game.version)

    def test_old_separate_artifact_is_migrated_into_bag_without_moving_save_schema(self):
        game = self.engine.store.load(self.game_id)
        raw = game.to_dict()
        raw["player"]["crafted_artifacts"] = [{
            "id":"old-forged-one", "name":"旧档玄钟", "quality_name":"精制",
            "mold_name":"钟器胎模", "actual_stats":{"combat_power":1234},
            "material_effects":[{"description":"旧器纹仍在"}],
        }]
        raw["player"]["inventory"] = [
            row for row in raw["player"]["inventory"] if not row.get("crafted_artifact_id")
        ]
        restored = type(game).from_dict(copy.deepcopy(raw))
        bag_item = next(row for row in restored.player.inventory if row.crafted_artifact_id == "old-forged-one")
        self.assertEqual(bag_item.id, "old-forged-one")
        self.assertIn("旧器纹仍在", bag_item.description)
        self.assertEqual(crafted_artifact_bonuses(restored.player)["combat_power"], 1234)

    def test_material_catalog_has_basic_five_slot_choices_in_every_world(self):
        definitions = crafting_material_definitions().values()
        required_worlds = {
            "human", "spirit", "celestial", "demon", "true_demon", "asura",
            "monster_realm", "phantom_underworld", "nether", "hell", "reincarnation",
        }
        for world in required_worlds:
            local = [row for row in definitions if row["world"] == world]
            self.assertGreaterEqual(len(local), 2, world)
            self.assertEqual(
                {"primary", "secondary", "quench"},
                {role for row in local for role in row["roles"]},
                world,
            )

        common_ids = {
            "human_refined_bronze", "spirit_cloud_iron", "celestial_cloud_jade",
            "demon_bone_steel", "true_demon_black_sinew", "asura_blood_steel",
            "monster_common_horn", "monster_shadow_hide", "nether_ancient_bone",
            "hell_yin_clay", "reincarnation_shore_stone",
        }
        common = [row for row in definitions if row["id"] in common_ids]
        self.assertEqual(len(common), len(required_worlds))
        self.assertTrue(all(row["allow_duplicate_type"] for row in common))

    def test_forge_is_immediately_active_in_bag_and_sell_removes_same_instance(self):
        instances = self._give_human_recipe()
        shown = self.engine.forge_crafted_artifact(self.game_id, self._payload(instances))
        artifact_id = shown["crafting_system"]["artifacts"][0]["id"]
        self.assertEqual(shown["crafting_system"]["active_count"], 1)
        self.assertTrue(any(row.get("crafted_artifact_id") == artifact_id for row in shown["player"]["inventory"]))
        with self.assertRaisesRegex(ValueError, "自动生效"):
            self.engine.crafted_artifact_action(self.game_id, artifact_id, "equip")
        sold = self.engine.crafted_artifact_action(self.game_id, artifact_id, "sell")
        self.assertEqual(sold["crafting_system"]["artifacts"], [])
        self.assertFalse(any(row.get("crafted_artifact_id") == artifact_id for row in sold["player"]["inventory"]))
        self.assertGreater(next(row["quantity"] for row in sold["player"]["inventory"] if row["id"] == "spirit_stone"), 0)

    def test_absolute_stats_scale_with_main_material_realm(self):
        definitions = crafting_material_definitions()
        rng = random.Random(81)
        low = [
            make_crafting_material_instance(definitions[mid], rng, source="测试", origin_world="human")
            for mid in ("human_cold_iron", "human_cold_spring_water", "human_cold_spring_water", "human_cold_spring_water")
        ]
        high = [
            make_crafting_material_instance(definitions[mid], rng, source="测试", origin_world="celestial")
            for mid in ("celestial_cloud_jade", "celestial_pure_yang_dew", "celestial_pure_yang_dew", "celestial_pure_yang_dew")
        ]
        low_player = Player("练气器师", "supreme_metal", realm_index=1, layer=1)
        high_player = Player("真仙器师", "supreme_metal", realm_index=9, layer=1)
        low_player.crafting_materials = copy.deepcopy(low)
        high_player.crafting_materials = copy.deepcopy(high)
        low_payload = {
            "mold_id":"sword", "primary_id":low[0]["id"], "secondary_a_id":low[1]["id"],
            "secondary_b_id":low[2]["id"], "quench_id":low[3]["id"],
            "allocations":{"combat_power":50},
        }
        high_payload = {
            "mold_id":"sword", "primary_id":high[0]["id"], "secondary_a_id":high[1]["id"],
            "secondary_b_id":high[2]["id"], "quench_id":high[3]["id"],
            "allocations":{"combat_power":216},
        }
        low_preview = self.engine._crafting_preview(low_player, low_payload)
        high_preview = self.engine._crafting_preview(high_player, high_payload)
        self.assertEqual(low_preview["scaling_realm_index"], 1)
        self.assertEqual(high_preview["scaling_realm_index"], 9)
        self.assertGreater(
            high_preview["theoretical_stats"]["normal"]["combat_power"],
            low_preview["theoretical_stats"]["normal"]["combat_power"] * 1000,
        )

    def test_market_material_stock_is_separate_and_purchase_keeps_offer_condition(self):
        shown = self.engine.get_game(self.game_id)
        self.assertEqual(len(shown["market"]["crafting_material_offers"]), 3)
        offer = shown["market"]["crafting_material_offers"][0]
        game = self.engine.store.load(self.game_id)
        add_item(game.player, "spirit_stone", offer["price"])
        self.engine.store.save(game)
        bought = self.engine.buy_market_offer(self.game_id, offer["id"])
        material = bought["crafting_system"]["materials"][0]
        self.assertEqual(material["quality"], offer["material_instance"]["quality"])
        self.assertEqual(material["material_value"], offer["material_instance"]["material_value"])

    def test_spirit_field_material_uses_real_harvest_year_quality_and_value(self):
        game = self.engine.store.load(self.game_id)
        plant = self.engine._add_harvested_plant(game.player, "golden_thunder_bamboo", 12345)
        self.engine.store.save(game)
        shown = self.engine.get_game(self.game_id)
        material = next(row for row in shown["crafting_system"]["materials"] if row["source_kind"] == "plant")
        self.assertEqual(material["quality"], plant.plant_quality)
        self.assertEqual(material["material_value"], plant.plant_value)
        self.assertIn("10,000", material["state"])

    def test_crafted_artifact_can_be_consigned_and_cancelled_back_as_same_instance(self):
        instances = self._give_human_recipe()
        shown = self.engine.forge_crafted_artifact(self.game_id, self._payload(instances))
        artifact = shown["crafting_system"]["artifacts"][0]
        game = self.engine.store.load(self.game_id)
        add_item(game.player, "spirit_stone", artifact["anchor_value"])
        location_id = self.engine.maps.normalize_location(game.player.world, game.player.location_id)
        game.auction_state = {
            "id":"auction-crafting", "status":"scheduled", "world":game.player.world,
            "location_id":location_id, "location_name":self.engine.maps.location(game.player.world, location_id)["name"],
            "announced_age":game.player.age, "actions_until_open":1, "round":0,
            "lots":[], "consignments":[], "attendees":[], "black_market_results":[],
        }
        self.engine.store.save(game)
        consigned = self.engine.crafted_artifact_action(self.game_id, artifact["id"], "consign")
        self.assertEqual(consigned["crafting_system"]["artifacts"], [])
        self.assertFalse(any(row.get("crafted_artifact_id") == artifact["id"] for row in consigned["player"]["inventory"]))
        loaded = self.engine.store.load(self.game_id)
        self.assertEqual(loaded.auction_state["consignments"][0]["artifact"]["id"], artifact["id"])
        self.engine._cancel_auction_for_world_change(loaded)
        self.assertEqual(loaded.player.crafted_artifacts[0]["id"], artifact["id"])
        restored_item = next(row for row in loaded.player.inventory if row.crafted_artifact_id == artifact["id"])
        self.assertEqual(restored_item.description, artifact["description"])


if __name__ == "__main__":
    unittest.main()
