import json
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import ContentRegistry
from cultivation_life.extension_system import write_extension_preference


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class ExtensionSystemTests(unittest.TestCase):
    def _package(self, root: Path, folder: str, manifest: dict, documents: dict[str, dict]) -> None:
        package = root / folder / manifest["id"]
        content = package / "content"
        content.mkdir(parents=True)
        (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        for name, document in documents.items():
            (content / name).write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _manifest(package_id: str, kind: str, **extra) -> dict:
        return {
            "schema_version": 1, "api_version": 1, "id": package_id,
            "name": package_id, "version": "1.0.0", "kind": kind,
            "enabled": True, "load_order": 100, "requires": [], **extra,
        }

    def test_no_extensions_loads_pristine_base(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ContentRegistry.load(SOURCE_ROOT / "content", Path(directory))
            self.assertIn("healing_pill", registry.items)
            self.assertEqual(ContentRegistry.extension_report, [])
            self.assertEqual(registry.monster_species, {})
            self.assertEqual(registry.monster_evolutions, {})
            monster_start = next(
                row for row in registry.world_systems["quick_start_presets"] if row["id"] == "monster_core"
            )
            self.assertEqual(monster_start["variant_label"], "本体兼容")
            self.assertEqual(monster_start["main_technique"], "TECH_COMMON_CORE")

    def test_dlc_loads_before_mod_and_mod_can_override_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._package(root, "dlc", self._manifest("official.test-relic", "dlc"), {
                "items.json": {"schema_version": 1, "items": [{
                    "id": "extension_test_relic", "name": "DLC遗物",
                    "description": "来自DLC", "tags": ["extension_test"],
                }]},
                "relic_events.json": {"schema_version": 1, "events": [{
                    "id": "EVT_DLC_RELIC", "title": "DLC遗物", "body": "取得扩展物品。",
                    "conditions": {}, "choices": [{
                        "id": "take", "text": "收下",
                        "effects": [{"type": "add_item", "item_id": "extension_test_relic"}],
                    }],
                }]},
            })
            self._package(root, "mods", self._manifest(
                "author.relic-rename", "mod", requires=["official.test-relic"],
            ), {
                "items.json": {"schema_version": 1, "items": [{
                    "id": "extension_test_relic", "name": "MOD改名遗物",
                }]},
            })
            registry = ContentRegistry.load(SOURCE_ROOT / "content", root)
            self.assertEqual(registry.items["extension_test_relic"].name, "MOD改名遗物")
            self.assertEqual([row["status"] for row in ContentRegistry.extension_report], ["loaded", "loaded"])

    def test_disabled_and_invalid_mods_do_not_damage_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._package(root, "mods", self._manifest("author.disabled", "mod", enabled=False), {
                "items.json": {"schema_version": 1, "items": [{"id": "should_not_load", "name": "禁用物品"}]},
            })
            self._package(root, "mods", self._manifest("author.broken", "mod"), {
                "market.json": {"schema_version": 1, "goods": [{
                    "world": "human", "kind": "item", "content_id": "missing_mod_item", "tier": 1, "price": 1,
                }]},
            })
            self._package(root, "mods", self._manifest("author.broken-event", "mod"), {
                "broken_events.json": {"schema_version": 1, "events": [{
                    "id": "EVT_BROKEN_MOD", "title": "坏事件", "body": "不会载入。",
                    "conditions": {}, "choices": [{
                        "id": "take", "text": "拿取",
                        "effects": [{"type": "add_item", "item_id": "missing_event_item"}],
                    }],
                }]},
            })
            self._package(root, "mods", self._manifest("author.broken-map", "mod"), {
                "maps.json": {"schema_version": 1, "settings": {"travel_speed_by_realm": {"0": -1}}},
            })
            registry = ContentRegistry.load(SOURCE_ROOT / "content", root)
            self.assertNotIn("should_not_load", registry.items)
            self.assertIn("healing_pill", registry.items)
            statuses = {row["id"]: row["status"] for row in ContentRegistry.extension_report}
            self.assertEqual(statuses["author.disabled"], "disabled")
            self.assertEqual(statuses["author.broken"], "error")
            self.assertEqual(statuses["author.broken-event"], "error")
            self.assertEqual(statuses["author.broken-map"], "error")

    def test_extension_event_file_is_recognized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._package(root, "dlc", self._manifest("official.event-test", "dlc"), {
                "extension_test_events.json": {"schema_version": 1, "events": [{
                    "id": "EVT_EXTENSION_TEST", "title": "扩展事件", "body": "来自扩展层。",
                    "conditions": {}, "choices": [{"id": "leave", "text": "离开", "effects": []}],
                }]},
            })
            ContentRegistry.load(SOURCE_ROOT / "content", root)
            self.assertIn("extension_test_events.json", ContentRegistry.loaded_documents)
            self.assertEqual(ContentRegistry.loaded_documents["extension_test_events.json"]["events"][0]["id"], "EVT_EXTENSION_TEST")

    def test_dlc_achievement_is_merged_with_its_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._package(root, "dlc", self._manifest("official.achievement-test", "dlc"), {
                "achievements.json": {"schema_version": 1, "achievements": [{
                    "id": "dlc_test_achievement", "name": "扩展功业", "description": "取得 DLC 遗物",
                    "category": "story",
                    "source": {"kind": "base", "id": "wrong-source", "name": "会被包清单覆盖"},
                    "condition": {"item": "extension_test_relic"},
                }]},
            })
            ContentRegistry.load(SOURCE_ROOT / "content", root)
            achievement = next(
                row for row in ContentRegistry.loaded_documents["achievements.json"]["achievements"]
                if row["id"] == "dlc_test_achievement"
            )
            self.assertEqual(achievement["source"]["kind"], "dlc")
            self.assertEqual(achievement["source"]["id"], "official.achievement-test")

    def test_user_preference_overrides_manifest_without_editing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest("official.switchable", "dlc")
            self._package(root, "dlc", manifest, {
                "items.json": {"schema_version": 1, "items": [{
                    "id": "switchable_relic", "name": "开关遗物", "tags": ["test"],
                }]},
            })
            write_extension_preference(root, "official.switchable", False)
            registry = ContentRegistry.load(SOURCE_ROOT / "content", root)
            self.assertNotIn("switchable_relic", registry.items)
            self.assertEqual(ContentRegistry.extension_report[0]["status"], "disabled")
            saved = json.loads((root / "data" / "extension_preferences.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["enabled"]["official.switchable"])
            package_manifest = json.loads(
                (root / "dlc" / "official.switchable" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(package_manifest["enabled"])


if __name__ == "__main__":
    unittest.main()
