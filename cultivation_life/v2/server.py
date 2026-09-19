from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from .application import CommandExecution, V2GameEngine


SOURCE_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = SOURCE_ROOT / "web"


class V2HTTPCommandRegistry:
    """Explicit HTTP boundary; browser input never constructs domain commands."""

    def __init__(self, engine: V2GameEngine):
        self.engine = engine
        self._operations: dict[str, Callable[[str, dict[str, Any]], Any]] = {
            "advance": lambda game, p: engine.perform_action(game, str(p.get("action", "cultivate")), int(p.get("units", 1))),
            "choice": lambda game, p: engine.choose(game, str(p.get("choice_id", ""))),
            "breakthrough": lambda game, p: engine.attempt_breakthrough(game),
            "map-travel": lambda game, p: engine.travel(game, str(p.get("destination_id", ""))),
            "use-item": lambda game, p: engine.use_item(game, str(p.get("item_id", ""))),
            "market-refresh": lambda game, p: engine.refresh_market(
                game, force=bool(p.get("force", False))
            ),
            "market-buy": lambda game, p: engine.buy_market_offer(game, str(p.get("offer_id", ""))),
            "market-lock": lambda game, p: engine.toggle_market_offer_lock(game, str(p.get("offer_id", ""))),
            "fight": lambda game, p: engine.fight(game, str(p.get("target_id", "")), objective=str(p.get("objective", "duel"))),
            "create-faction": lambda game, p: engine.create_faction(game, str(p.get("name", ""))),
            "create-family": lambda game, p: engine.create_family(game, str(p.get("name", ""))),
            "leave-faction": lambda game, p: engine.leave_faction(game),
            "cross-world": lambda game, p: engine.cross_world(game, str(p.get("destination_world_id", ""))),
            "ascend-world": lambda game, p: engine.ascend_world(
                game, str(p.get("destination_world_id", "")),
                invited_ids=tuple(map(str, p.get("invited_ids", []))),
            ),
            "intrigue-personnel": lambda game, p: engine.intrigue_personnel_action(
                game, str(p.get("kind", "sect")), str(p.get("action", "")),
                str(p.get("member_id", "")), str(p.get("position_id", "")),
                int(p.get("years", 1)), str(p.get("reason", "")),
            ),
            "intrigue-guest": lambda game, p: engine.intrigue_guest_action(
                game, str(p.get("kind", "sect")), str(p.get("action", "")), str(p.get("target_id", "")),
            ),
            "intrigue-resolution": lambda game, p: engine.intrigue_propose_resolution(
                game, str(p.get("kind", "sect")), str(p.get("resolution_type", "")),
                str(p.get("target_id", "")), player_vote=bool(p.get("player_vote", True)),
            ),
            "intrigue-recruitment": lambda game, p: engine.intrigue_recruitment_action(
                game, str(p.get("action", "")), filters=p.get("filters"),
                candidate_ids=tuple(map(str, p.get("candidate_ids", []))),
                player_vote=bool(p.get("player_vote", True)),
            ),
            "war-action": lambda game, p: engine.war_action(
                game, str(p.get("war_id", "")), str(p.get("action", "")), ally_id=str(p.get("ally_id", "")),
            ),
            "settings": lambda game, p: engine.update_setting(game, str(p.get("setting", "")), bool(p.get("enabled", False))),
        }

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    def dispatch(self, game_id: str, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = self._operations.get(operation)
        if handler is None:
            raise KeyError(f"未知V2命令：{operation}")
        result = handler(game_id, payload)
        if isinstance(result, CommandExecution):
            return {"game": result.game, "events": list(result.events)}
        if isinstance(result, dict):
            return result
        raise TypeError("V2命令返回值无法公开")


def build_handler(engine: V2GameEngine, web_root: Path = WEB_ROOT) -> type[BaseHTTPRequestHandler]:
    registry = V2HTTPCommandRegistry(engine)

    class Handler(BaseHTTPRequestHandler):
        server_version = "CultivationLifeV2/2"

        def do_GET(self) -> None:  # noqa: N802
            try:
                path = urlparse(self.path).path
                if path == "/api/v2/config":
                    self._json({
                        "format": "cultivation-life-v2",
                        "actions": {key: value.get("name", key) for key, value in engine.definitions.actions.items()},
                        "roots": {key: value.name for key, value in engine.definitions.roots.items() if value.creation},
                        "paths": dict(engine.definitions.paths),
                        "worlds": {key: value.name for key, value in engine.definitions.worlds.items() if value.enabled},
                        "operations": registry.operations,
                    })
                elif path == "/api/v2/games":
                    self._json({"games": engine.list_games()})
                elif path.startswith("/api/v2/games/"):
                    game_id = unquote(path.removeprefix("/api/v2/games/").strip("/"))
                    self._json(engine.get_game(game_id))
                else:
                    self._static(path)
            except Exception as error:
                self._error(error)

        def do_POST(self) -> None:  # noqa: N802
            try:
                path = urlparse(self.path).path
                payload = self._body()
                if path == "/api/v2/games":
                    result = engine.create_game(
                        str(payload.get("name", "无名散修")),
                        seed=payload.get("seed"),
                        starting_age=int(payload.get("starting_age", 16)),
                        gender=str(payload.get("gender", "male")),
                        race=str(payload.get("race", "human")),
                        spirit_root=str(payload.get("spirit_root", "supreme_wood")),
                        path=str(payload.get("path", "dao")),
                        start_world=str(payload.get("start_world", "human")),
                    )
                    self._json(result, HTTPStatus.CREATED)
                    return
                parts = path.strip("/").split("/")
                if len(parts) != 5 or parts[:3] != ["api", "v2", "games"]:
                    raise KeyError("接口不存在")
                self._json(registry.dispatch(unquote(parts[3]), parts[4], payload))
            except Exception as error:
                self._error(error)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                raise ValueError("请求体过大")
            document = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(document, dict):
                raise ValueError("请求体必须是JSON对象")
            return document

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, error: Exception) -> None:
            status = HTTPStatus.NOT_FOUND if isinstance(error, KeyError) else HTTPStatus.BAD_REQUEST
            self._json({"error": str(error).strip("'"), "type": type(error).__name__}, status)

        def _static(self, path: str) -> None:
            relative = "v2.html" if path in {"/", "/v2", "/v2/"} else path.lstrip("/")
            target = (web_root / relative).resolve()
            if web_root.resolve() not in target.parents or not target.is_file():
                raise KeyError("页面不存在")
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="浮生问道 V2 本地服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--database", type=Path, default=SOURCE_ROOT / "data" / "v2" / "games.db")
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), build_handler(V2GameEngine(args.database)))
    print(f"V2 running at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
