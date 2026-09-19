import json
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cultivation_life.v2.application import V2GameEngine
from cultivation_life.v2.release_audit import assess_release_surface
from cultivation_life.v2.server import (
    V2HTTPCommandRegistry,
    _legacy_save_path,
    _legacy_saves,
    resolve_runtime_paths,
)


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V2ReleaseSurfaceTests(unittest.TestCase):
    def test_release_audit_confirms_all_frozen_operations_reach_http_and_ui(self) -> None:
        report = assess_release_surface(SOURCE_ROOT)
        self.assertTrue(report.ready)
        self.assertEqual(len(report.frozen_operations), 101)
        self.assertEqual(report.missing_from_http, ())
        self.assertEqual(report.missing_from_client, ())
        self.assertEqual(
            set(report.v2_only_client_operations),
            {"ascend-world", "fight", "market-refresh"},
        )

    def test_formal_ui_uses_typed_forms_instead_of_raw_json_input(self) -> None:
        script = (SOURCE_ROOT / "web" / "v2.js").read_text(encoding="utf-8")
        page = (SOURCE_ROOT / "web" / "v2.html").read_text(encoding="utf-8")
        self.assertIn("function collectPayload(form)", script)
        self.assertIn("type:'materials'", script)
        self.assertIn("type:'lineageRules'", script)
        self.assertIn('id="operation-list"', page)
        self.assertNotIn("<textarea", page)

    def test_every_frozen_operation_dispatches_through_an_application_method(self) -> None:
        class RecordingEngine:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

            def __getattr__(self, name: str):
                def call(*args: object, **kwargs: object) -> dict[str, object]:
                    self.calls.append((name, args, kwargs))
                    return {"method": name}

                return call

        inventory = json.loads(
            (SOURCE_ROOT / "docs" / "v2" / "v1_behavior_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        engine = RecordingEngine()
        registry = V2HTTPCommandRegistry(engine)  # type: ignore[arg-type]
        for operation in inventory["public_operations"]:
            with self.subTest(operation=operation):
                before = len(engine.calls)
                result = registry.dispatch("game", operation, {})
                self.assertEqual(len(engine.calls), before + 1)
                self.assertIn("method", result)
                method_name, args, kwargs = engine.calls[-1]
                method = getattr(V2GameEngine, method_name)
                inspect.signature(method).bind(None, *args, **kwargs)

    def test_frozen_runtime_uses_writable_staging_root_and_bundled_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "build").mkdir()
            (root / "build" / "launcher.spec").write_text("", encoding="utf-8")
            (root / "launcher.py").write_text("", encoding="utf-8")
            (root / "content").mkdir()
            app_root = root / "dist"
            app_root.mkdir()
            bundle = root / "bundle"
            (bundle / "content").mkdir(parents=True)
            (bundle / "web").mkdir()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(app_root / "launcher.exe")),
                patch.object(sys, "_MEIPASS", str(bundle), create=True),
            ):
                paths = resolve_runtime_paths()
            self.assertEqual(paths.persistence_root, root)
            self.assertEqual(paths.database_path, root / "data" / "v2" / "games.db")
            self.assertEqual(paths.content_root, bundle / "content")
            self.assertEqual(paths.web_root, bundle / "web")

    def test_legacy_save_discovery_ignores_metadata_and_blocks_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save = root / "hero.json"
            save.write_text(json.dumps({
                "version": 5,
                "id": "hero",
                "player": {"name": "旧世修士"},
                "updated_at": "2026-09-19T00:00:00Z",
            }, ensure_ascii=False), encoding="utf-8")
            (root / "global_metadata.json").write_text("{}", encoding="utf-8")
            self.assertEqual([row["file_name"] for row in _legacy_saves(root)], ["hero.json"])
            self.assertEqual(_legacy_save_path(root, "hero.json"), save)
            with self.assertRaises(ValueError):
                _legacy_save_path(root, "../hero.json")

    def test_engine_can_separate_bundled_content_from_external_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = V2GameEngine(
                root / "games.db",
                content_directory=SOURCE_ROOT / "content",
                extension_root=root,
            )
            self.assertEqual(engine.list_games(), [])


if __name__ == "__main__":
    unittest.main()
