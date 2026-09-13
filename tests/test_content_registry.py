import json
import copy
import shutil
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import ContentError, ContentRegistry
from cultivation_life.event_repository import EventRepository


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class ContentRegistryTests(unittest.TestCase):
    def test_content_reader_rejects_duplicate_json_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":1,"systems":{},"systems":{}}', encoding="utf-8")
            with self.assertRaisesRegex(ContentError, "重复字段：systems"):
                ContentRegistry._read(path)

    def test_all_game_catalogs_load_from_json(self):
        registry = ContentRegistry.load(SOURCE_ROOT / "content")
        self.assertGreaterEqual(len(registry.items), 36)
        self.assertGreaterEqual(len(registry.techniques), 25)
        self.assertGreaterEqual(len(registry.transformations), 3)
        self.assertEqual(len(registry.realms), 13)
        self.assertTrue(
            {
                "tianjian", "wanmo", "puti", "taixuan", "wanlingshan", "xinghe",
                "blood_prison", "corpse_hall", "heaven_demon_palace", "myriad_soul_abyss", "black_sun_temple",
                "cloud_immortal_palace", "taiyi_pill_sect", "law_sea_pavilion",
                "asura_war_court", "blood_moon_palace", "annihilation_sea_sect",
                "ghost_passage_court", "forgetful_river_archive", "iron_tree_prison_sect",
            } <= set(registry.faction_definitions),
        )
        self.assertIn("myriad_beast_court", registry.faction_definitions)
        self.assertEqual([entry["enabled"] for entry in registry.world_systems["quick_start_presets"]], [True] * 9)
        self.assertEqual(registry.root_definitions["pseudo_all"]["efficiency"], 0.7)
        self.assertNotIn("qi", registry.world_systems["stage_lifespan_bonus"])
        self.assertEqual(registry.world_systems["stage_lifespan_bonus"]["foundation"]["middle"], [12, 20])

    def test_breakthrough_medicine_catalog_has_every_requested_scope(self):
        registry = ContentRegistry.load(SOURCE_ROOT / "content")
        expected = {
            "筑基丹": "major:1", "真元丹": "minor:2",
            "凝神丹": "major:2", "洗髓丹": "minor:3",
            "抱婴参": "major:3", "天元丹": "minor:4",
            "回天草": "major:4", "生生造化丸": "minor:5",
            "昊天散": "major:5", "灵虚五散": "minor:6",
            "先天砂": "major:6", "明心多莲": "minor:7",
            "三七神果": "major:7",
        }
        actual = {
            item.name: item.breakthrough_scope
            for item in registry.items.values()
            if item.breakthrough_bonus > 0
        }
        for name, scope in expected.items():
            self.assertEqual(actual[name], scope)
        self.assertTrue(any(scope == "minor:8" for scope in actual.values()))
        self.assertGreater(registry.items["tribulation_vitality_pill"].trial_restore_hp, 0)
        self.assertGreater(registry.items["tribulation_mana_dew"].trial_restore_mp, 0)

    def test_every_breakthrough_aid_is_sold_in_its_source_realm_market(self):
        registry = ContentRegistry.load(SOURCE_ROOT / "content")
        sold = {
            (row["content_id"], row["tier"], row.get("world", "human"))
            for row in registry.market_goods if row["kind"] == "item"
        }
        for item in registry.items.values():
            if item.breakthrough_bonus <= 0:
                continue
            source = int(item.breakthrough_scope.split(":", 1)[1])
            if "monster" in item.tags:
                self.assertIn((item.id, source, "monster_realm"), sold, item.name)
                self.assertIn((item.id, source, "phantom_underworld"), sold, item.name)
                continue
            if "ghost" in item.tags:
                self.assertIn((item.id, source, "hell"), sold, item.name)
                continue
            world = "human" if source <= 4 else "spirit"
            self.assertIn((item.id, source, world), sold, item.name)

    def test_v41_custom_lineage_configuration_is_rejected_before_package_load(self):
        source = json.loads(
            (SOURCE_ROOT / "dlc" / "monster-bloodlines" / "content" / "monster_bloodlines.json").read_text(encoding="utf-8")
        )
        known_events = {
            deed["event_id"]
            for deed in source["settings"]["custom_lineage"]["deed_definitions"]
            if deed["kind"] == "history"
        }
        ContentRegistry._build_monster_bloodlines(copy.deepcopy(source), event_ids=known_events)

        def custom(document):
            return document["settings"]["custom_lineage"]

        cases = {
            "phase": lambda document: custom(document)["phases"].pop(),
            "schedule": lambda document: custom(document)["schedules"][0].__setitem__("id", "sometimes"),
            "condition": lambda document: custom(document)["conditions"][7].__setitem__("subject", "spectator"),
            "target": lambda document: custom(document)["targets"][0].__setitem__("cost", -1),
            "effect": lambda document: custom(document)["effects"][6].__setitem__("targets", ["enemy"]),
            "value_pool": lambda document: custom(document)["values"]["percent"][1].__setitem__("value", 0.03),
            "rule_slots": lambda document: custom(document)["rule_slots"].__setitem__("2", 2),
            "deed_definitions": lambda document: custom(document)["deed_definitions"][-1].__setitem__("event_id", "MISSING_EVENT"),
            "species_signature_traits": lambda document: document["settings"]["species_signature_traits"][0].__setitem__("trait_id", "missing_trait"),
            "species_trait_pools": lambda document: document["settings"]["species_trait_pools"]["serpent"].__setitem__(0, "bloodline_avian_pool_01"),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                broken = copy.deepcopy(source)
                mutate(broken)
                with self.assertRaises(ContentError):
                    ContentRegistry._build_monster_bloodlines(broken, event_ids=known_events)

    def test_each_core_world_sells_one_conception_medicine(self):
        registry = ContentRegistry.load(SOURCE_ROOT / "content")
        sold_worlds = {
            row["world"]
            for row in registry.market_goods
            if row["kind"] == "item" and registry.items[row["content_id"]].conception_bonus > 0
        }
        self.assertEqual(sold_worlds, {"human", "demon", "spirit", "true_demon", "hell", "celestial", "asura", "monster_realm", "phantom_underworld", "nether"})
        self.assertEqual(registry.world_systems["demonic_cultivation"]["divine_sense_training_base"], 40)
        self.assertEqual(registry.world_systems["family"]["conception_chance_by_realm"]["5"], 0.0)

    def test_market_rejects_dangling_content_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in ("items.json", "techniques.json", "transformations.json", "market.json", "world.json", "factions.json", "races.json", "world_npcs.json", "story_combat_scenarios.json"):
                shutil.copy2(SOURCE_ROOT / "content" / name, target / name)
            market_path = target / "market.json"
            market = json.loads(market_path.read_text(encoding="utf-8"))
            market["goods"][0]["content_id"] = "missing_item"
            market_path.write_text(json.dumps(market, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentError, "不存在的item"):
                ContentRegistry.load(target)

    def test_story_combat_scenarios_define_real_teams_and_round_beats(self):
        registry = ContentRegistry.load(SOURCE_ROOT / "content")
        ma_liang = registry.story_combat_scenarios["EVT_MA_LIANG_008"]
        self.assertEqual(
            [member["name"] for member in ma_liang["enemy_members"]],
            ["重伤真仙洛天衡", "负山神猿", "离火童子", "幽泉魔影"],
        )
        self.assertAlmostEqual(sum(member["share"] for member in ma_liang["enemy_members"]), 1.0)
        self.assertGreaterEqual(len(ma_liang["story_beats"]), 5)
        self.assertIn("EVT_TRUE_DEMON_SACRED_005", registry.story_combat_scenarios)

    def test_event_repository_rejects_dangling_item_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            document = {
                "schema_version": 1,
                "events": [{
                    "id": "BROKEN", "title": "断链", "body": "测试", "conditions": {},
                    "choices": [{"id": "take", "text": "取", "effects": [{"type": "add_item", "item_id": "missing_item"}]}],
                }],
            }
            (target / "events.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentError, "不存在的物品"):
                EventRepository.load(target)

    def test_event_repository_rejects_invalid_cultivator_power_distribution(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            document = {
                "schema_version": 1,
                "events": [{
                    "id": "BROKEN_COMBAT", "title": "断裂斗法", "body": "测试", "conditions": {},
                    "combat": {"target_name": "路人", "realm_offsets": [[0, 0]], "power_sigma": -1, "power_bounds": [2, 1]},
                    "choices": [{"id": "fight", "text": "战", "effects": []}],
                }],
            }
            (target / "events.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentError, "修士战斗分布不合法"):
                EventRepository.load(target)

    def test_rules_module_contains_logic_not_catalog_rows(self):
        source = (SOURCE_ROOT / "cultivation_life" / "rules.py").read_text(encoding="utf-8")
        self.assertNotIn('"qi_gathering_bead"', source)
        self.assertNotIn('"TECH_COMMON_NASCENT"', source)
        self.assertNotIn('"裴问锋"', source)


if __name__ == "__main__":
    unittest.main()
