from __future__ import annotations

import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from cultivation_life import GameEngine
from cultivation_life.server import HTTPCommandRegistry


ROOT = Path(__file__).resolve().parent.parent
V1_COMMIT = "83641711ef1e8f8d5f74dc0ad973d6a07c36932f"
FROZEN_FILES = {
    "web/app.js": "03bd01aebd3bd9fcb707571eac24dfc053e08ef7b8c07b388dd3b6b8d1b9986b",
    "web/index.html": "da1d42ffdd8c82dbf97feee8a9552e3a4a28f84d9a8a4c7b7bbf92a176b06830",
    "web/style.css": "9a92abcee0d1a9b303f897b32d5ce1c9a1e43fd2f1383635061c4eb01dd9e34a",
    "web/panels.css": "c1b48d49a70f08835c963fe237d6e84470c93aecba628cc7bfeeb341abc4e902",
    "web/ui-panels.js": "0150552b3fbee49e0a6a283556ff0b29ee81830734c36df939f16b64b7d75b04",
    "web/assets/natal-artifact-ancient-sword.png": "e45f68e5e586247ccada88d50391a4d0d01855841ba7522279bcce4750527eff",
}


class FrozenV1FrontendTests(unittest.TestCase):
    def test_frontend_is_byte_identical_to_v1_baseline(self) -> None:
        for relative, expected in FROZEN_FILES.items():
            with self.subTest(file=relative, baseline=V1_COMMIT):
                actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

    def test_every_literal_v1_game_route_is_registered_by_v2(self) -> None:
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        routes = set(re.findall(
            r"/api/games/\$\{game\.id\}/([a-z][a-z0-9-]+)", source
        ))
        with tempfile.TemporaryDirectory() as temporary:
            engine = GameEngine(
                Path(temporary) / "games.db",
                content_directory=ROOT / "content",
                extension_root=ROOT,
            )
            registered = set(HTTPCommandRegistry(engine).operations)
        self.assertGreaterEqual(len(routes), 96)
        self.assertEqual(routes - registered, set())


if __name__ == "__main__":
    unittest.main()
