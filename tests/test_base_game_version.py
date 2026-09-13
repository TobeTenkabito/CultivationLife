import json
import re
import tempfile
import unittest
from pathlib import Path

import cultivation_life
from cultivation_life.engine import GameEngine
from cultivation_life.storage import SaveStore
from cultivation_life.version import (
    BASE_GAME_ID,
    BASE_GAME_NAME,
    BASE_GAME_VERSION,
    BASE_GAME_VERSION_TUPLE,
    base_game_metadata,
)


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class BaseGameVersionTests(unittest.TestCase):
    def test_base_version_is_semantic_and_has_one_public_metadata_shape(self):
        self.assertRegex(BASE_GAME_VERSION, r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        self.assertEqual(tuple(map(int, BASE_GAME_VERSION.split("."))), BASE_GAME_VERSION_TUPLE)
        self.assertEqual(cultivation_life.__version__, BASE_GAME_VERSION)
        self.assertEqual(base_game_metadata(), {
            "id": BASE_GAME_ID,
            "name": BASE_GAME_NAME,
            "version": BASE_GAME_VERSION,
            "version_label": f"本体 v{BASE_GAME_VERSION}",
        })

    def test_new_saves_record_creation_and_last_saved_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            save_root = Path(directory) / "saves"
            engine = GameEngine(SOURCE_ROOT, save_root)
            created = engine.create_game("版本留痕", "supreme_wood", "dao", 7701)
            raw = json.loads((save_root / f"{created['id']}.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["created_with_game_version"], BASE_GAME_VERSION)
            self.assertEqual(raw["last_saved_with_game_version"], BASE_GAME_VERSION)
            self.assertEqual(engine.store.list_games()[0]["game_version"], BASE_GAME_VERSION)

    def test_legacy_saves_load_without_confusing_save_schema_and_release_version(self):
        with tempfile.TemporaryDirectory() as directory:
            save_root = Path(directory) / "saves"
            engine = GameEngine(SOURCE_ROOT, save_root)
            created = engine.create_game("旧档留痕", "supreme_fire", "dao", 7702)
            path = save_root / f"{created['id']}.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw.pop("created_with_game_version")
            raw.pop("last_saved_with_game_version")
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

            store = SaveStore(save_root)
            loaded = store.load(created["id"])
            self.assertEqual(loaded.version, 5)
            self.assertEqual(loaded.created_with_game_version, "pre-1.0.0")
            self.assertEqual(loaded.last_saved_with_game_version, "pre-1.0.0")
            store.save(loaded)
            updated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(updated["created_with_game_version"], "pre-1.0.0")
            self.assertEqual(updated["last_saved_with_game_version"], BASE_GAME_VERSION)

    def test_web_ui_reads_version_from_api_instead_of_hardcoding_it(self):
        html = (SOURCE_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (SOURCE_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="base-game-version"', html)
        self.assertIn('id="settings-base-version"', html)
        self.assertIn("config.base_game", script)
        self.assertIsNone(re.search(r"本体 v\d+\.\d+\.\d+", html))

    def test_windows_build_metadata_uses_the_same_version_source(self):
        spec = (SOURCE_ROOT / "build" / "launcher.spec").read_text(encoding="utf-8")
        self.assertIn('project_root / "cultivation_life" / "version.py"', spec)
        self.assertIn("BASE_GAME_VERSION = version_module.BASE_GAME_VERSION", spec)
        self.assertIn("version=launcher_version", spec)
        self.assertIsNone(re.search(r'StringStruct\("ProductVersion", "\d+\.\d+\.\d+"\)', spec))


if __name__ == "__main__":
    unittest.main()
