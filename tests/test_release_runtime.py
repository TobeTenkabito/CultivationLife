from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from cultivation_life import GameEngine
from cultivation_life.server import build_handler


ROOT = Path(__file__).resolve().parent.parent


class ReleaseRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "games.db"
        self.engine = GameEngine(
            self.database,
            content_directory=ROOT / "content",
            extension_root=ROOT,
        )
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), build_handler(self.engine, ROOT / "web")
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request(
        self,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers or ({"Content-Type": "application/json"} if data else {}),
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)
        with response:
            return response.status, response.read(), dict(response.headers)

    def test_root_api_create_action_and_reload_use_official_routes(self) -> None:
        status, page, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b'/app.js', page)
        self.assertNotIn(b'/v2.js', page)
        self.assertIn("Content-Security-Policy", headers)
        policy = headers["Content-Security-Policy"]
        self.assertIn("style-src 'self' 'unsafe-inline'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", policy)

        status, config_body, _ = self.request("/api/config")
        self.assertEqual(status, 200)
        config = json.loads(config_body)
        self.assertIn("advance", config["operations"])
        self.assertIn("extensions", config)
        self.assertEqual(config["base_game"]["id"], "cultivation-life")
        self.assertEqual(config["root_details"]["supreme_wood"]["tier"], "极品灵根")
        self.assertEqual(config["root_details"]["supreme_wood"]["efficiency"], 1.3)
        self.assertEqual(config["technique_elements"]["wood"], "木")
        self.assertEqual(config["qi_sources"]["spirit"], "灵源")

        status, achievements_body, _ = self.request("/api/achievements")
        self.assertEqual(status, 200)
        achievements = json.loads(achievements_body)
        self.assertEqual(achievements["total"], 58)
        self.assertTrue(achievements["progress_available"])

        status, created_body, _ = self.request(
            "/api/games", payload={"name": "发布烟测", "seed": 20260919}
        )
        self.assertEqual(status, 201)
        created = json.loads(created_body)
        game_id = created["id"]
        status, advanced_body, _ = self.request(
            f"/api/games/{game_id}/advance",
            payload={"action": "rest", "units": 1},
        )
        self.assertEqual(status, 200)
        advanced = json.loads(advanced_body)
        self.assertEqual(advanced["clock"]["year"], 1)
        self.assertIn("spirit_field", advanced)
        self.assertIn("world_route", advanced)

        reloaded = GameEngine(
            self.database,
            content_directory=ROOT / "content",
            extension_root=ROOT,
        )
        self.assertEqual(reloaded.get_game(game_id)["clock"]["year"], 1)

    def test_write_api_rejects_cross_site_and_non_json_requests(self) -> None:
        status, _, _ = self.request(
            "/api/games",
            payload={"name": "跨站"},
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)

        request = urllib.request.Request(
            self.base_url + "/api/games",
            data=b"{}",
            headers={"Content-Type": "text/plain"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 415)


if __name__ == "__main__":
    unittest.main()
