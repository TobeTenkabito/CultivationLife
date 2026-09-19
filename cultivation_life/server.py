from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from cultivation_life.runtime import persistence_root

from .application import CommandExecution, GameEngine


SOURCE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = SOURCE_ROOT / "web"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _text(payload: dict[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return default if value is None else str(value)


def _integer(payload: dict[str, Any], key: str, default: int = 0) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是整数")
    return int(value if value is not None else default)


def _number(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是数字")
    return float(value if value is not None else default)


def _boolean(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} 必须是布尔值")
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("列表参数格式错误")
    return tuple(map(str, value))


def _material_rows(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list):
        raise ValueError("materials 必须是列表")
    rows: list[tuple[str, int]] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("炼丹材料格式错误")
        quantity = row.get("quantity", 0)
        if isinstance(quantity, bool):
            raise ValueError("炼丹材料数量必须是整数")
        rows.append((str(row.get("item_id", "")), int(quantity)))
    return tuple(rows)


def _rule_rows(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("rules 必须是对象列表")
    return tuple(dict(row) for row in value)


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    app_root: Path
    bundled_root: Path
    persistence_root: Path
    content_root: Path
    web_root: Path
    database_path: Path


def resolve_runtime_paths() -> RuntimePaths:
    """Resolve writable and bundled paths for source and frozen launches."""
    app_root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else SOURCE_ROOT
    )
    bundled_root = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)).resolve()
    persistent = persistence_root(app_root)
    content_root = app_root / "content"
    if not content_root.is_dir():
        content_root = bundled_root / "content"
    web_root = app_root / "web"
    if not web_root.is_dir():
        web_root = bundled_root / "web"
    return RuntimePaths(
        app_root=app_root,
        bundled_root=bundled_root,
        persistence_root=persistent,
        content_root=content_root,
        web_root=web_root,
        database_path=persistent / "data" / "games.db",
    )


class HTTPCommandRegistry:
    """Explicit HTTP boundary; browser input never constructs domain commands."""

    def __init__(self, engine: GameEngine):
        self.engine = engine
        self._operations: dict[str, Callable[[str, dict[str, Any]], Any]] = {
            "advance": lambda game, p: engine.perform_action(
                game, _text(p, "action", "cultivate"),
                _integer(p, "units", 1) if "units" in p else _integer(p, "years", 1),
            ),
            "alchemy": lambda game, p: engine.refine_pill(
                game, _text(p, "target_item_id"), _material_rows(p.get("materials", [])),
            ),
            "asura-ascension": lambda game, p: engine.begin_ascension_trial(game, "asura"),
            "auction-advance": lambda game, p: engine.advance_auction_round(game),
            "auction-bid": lambda game, p: engine.place_auction_bid(game, _text(p, "lot_id")),
            "auction-consign": lambda game, p: engine.consign_auction_asset(
                game, _text(p, "asset_id", _text(p, "item_id")),
                _integer(p, "start_price", 0),
            ),
            "auction-identity": lambda game, p: engine.choose_auction_identity(
                game, _text(p, "alias")
            ),
            "auction-negotiate": lambda game, p: engine.negotiate_at_auction(
                game, _text(p, "npc_id")
            ),
            "auction-private-bargain": lambda game, p: engine.bargain_private_trade(
                game, _text(p, "npc_id"), _text(p, "side"), _text(p, "asset_id")
            ),
            "auction-private-buy": lambda game, p: engine.buy_private_trade_item(
                game, _text(p, "npc_id"), _text(p, "offer_id")
            ),
            "auction-private-sell": lambda game, p: engine.sell_private_trade_asset(
                game, _text(p, "npc_id"), _text(p, "asset_id", _text(p, "item_id"))
            ),
            "black-market-buy": lambda game, p: engine.buy_black_market_item(
                game, _text(p, "result_id")
            ),
            "black-market-leave": lambda game, p: engine.leave_black_market(game),
            "black-market-search": lambda game, p: engine.search_black_market(
                game, _text(p, "pattern")
            ),
            "black-market-sell": lambda game, p: engine.sell_black_market_asset(
                game, _text(p, "kind"), _text(p, "asset_id")
            ),
            "body-breakthrough": lambda game, p: engine.attempt_body_breakthrough(game),
            "breakthrough": lambda game, p: engine.attempt_breakthrough(game),
            "captive-action": lambda game, p: engine.captive_action(
                game, _text(p, "target_id"), _text(p, "action")
            ),
            "celestial-ascension": lambda game, p: engine.begin_ascension_trial(
                game, "celestial"
            ),
            "choice": lambda game, p: engine.choose(game, _text(p, "choice_id")),
            "concubine-action": lambda game, p: engine.manage_concubine(
                game, _text(p, "target_id"), _text(p, "action")
            ),
            "concubine-status": lambda game, p: engine.manage_concubine_status(
                game, _text(p, "action"), method=_text(p, "method")
            ),
            "craft-puppet": lambda game, p: engine.craft_mechanical_puppet(game),
            "crafted-artifact": lambda game, p: engine.crafted_artifact_action(
                game, _text(p, "artifact_id"), _text(p, "action"),
                _integer(p, "start_price", 0),
            ),
            "crafting-blueprint": lambda game, p: engine.save_crafting_blueprint(game, p),
            "crafting-forge": lambda game, p: engine.forge_crafted_artifact(game, p),
            "crafting-preview": lambda game, p: engine.preview_crafting(game, p),
            "create-faction": lambda game, p: engine.create_faction(game, _text(p, "name")),
            "create-family": lambda game, p: engine.create_family(game, _text(p, "name")),
            "cross-world": lambda game, p: engine.cross_world(
                game, _text(p, "destination", _text(p, "destination_world_id"))
            ),
            "custom-lineage-confirm": lambda game, p: engine.confirm_custom_lineage(
                game, _text(p, "evolution_id"), _text(p, "name"),
                _rule_rows(p.get("rules", [])),
            ),
            "custom-lineage-prepare": lambda game, p: engine.prepare_custom_lineage(
                game, _text(p, "evolution_id")
            ),
            "dao-companion": self._dao_companion,
            "dao-friend": self._dao_friend,
            "debug-world-news": lambda game, p: engine.set_world_news_debug(
                game, _boolean(p, "enabled")
            ),
            "disciple-gift": lambda game, p: engine.gift_disciple(
                game, _text(p, "disciple_id"), _text(p, "kind"), _text(p, "content_id")
            ),
            "disciple-request": lambda game, p: engine.respond_disciple_request(
                game, _text(p, "request_id"), _boolean(p, "accept")
            ),
            "equip-technique": lambda game, p: engine.equip_known_technique(
                game, _text(p, "technique_id"), _text(p, "slot", "main")
            ),
            "faction-diplomacy": lambda game, p: engine.propose_sect_diplomacy(
                game, _text(p, "target_id"), _text(p, "status")
            ),
            "faction-dispatch": lambda game, p: engine.dispatch_faction_member(
                game, _text(p, "target")
            ),
            "faction-intercept": lambda game, p: engine.intercept_faction_member(
                game, _text(p, "npc_id", _text(p, "target_id"))
            ),
            "faction-relationship": lambda game, p: engine.manage_faction_relationship(
                game, _text(p, "npc_id"), _text(p, "role")
            ),
            "faction-reward": lambda game, p: engine.set_faction_reward(
                game, _text(p, "reward_id")
            ),
            "faction-succession": lambda game, p: engine.arrange_faction_succession(game),
            "formation-activate": lambda game, p: engine.activate_formation(
                game, _text(p, "formation_id", _text(p, "loadout_id"))
            ),
            "formation-deactivate": lambda game, p: engine.deactivate_formation(game),
            "formation-delete": lambda game, p: engine.delete_formation(
                game, _text(p, "formation_id", _text(p, "loadout_id"))
            ),
            "formation-ground-deploy": lambda game, p: engine.deploy_ground_formation(
                game, _text(p, "owner_kind", "player")
            ),
            "formation-ground-repair": lambda game, p: engine.repair_ground_formation(
                game, _text(p, "ground_formation_id"), _text(p, "supply_id"),
                _integer(p, "quantity", 1),
            ),
            "formation-ground-withdraw": lambda game, p: engine.withdraw_ground_formation(
                game, _text(p, "ground_formation_id")
            ),
            "formation-preview": lambda game, p: engine.preview_formation(game, p),
            "formation-save": lambda game, p: engine.save_formation(game, p),
            "ghost-attachment": lambda game, p: engine.ghost_attachment_action(
                game, _text(p, "action"), _text(p, "item_id")
            ),
            "ghost-constraint": lambda game, p: engine.ghost_constraint_action(
                game, _text(p, "action")
            ),
            "ghost-leave-host": lambda game, p: engine.leave_possessed_body(game),
            "ghost-parade": lambda game, p: engine.ghost_parade_action(
                game, _text(p, "action"), _text(p, "soul_id")
            ),
            "ghost-reincarnate": lambda game, p: engine.reincarnate_ghost(game),
            "ghost-reincarnation-prompt": lambda game, p: engine.prepare_ghost_reincarnation(game),
            "ghost-soul": lambda game, p: engine.ghost_soul_action(
                game, _text(p, "soul_id"), _text(p, "action"), _text(p, "slot")
            ),
            "ghost-wangsheng": lambda game, p: engine.spend_wangsheng(
                game, all_available=_boolean(p, "all", False)
            ),
            "heavenly-court": lambda game, p: engine.heavenly_court_action(
                game, _text(p, "action"), _text(p, "target_id"), p.get("enact"),
                _integer(p, "influence_spend", 0),
            ),
            "heavenly-election": lambda game, p: engine.resolve_heavenly_election(
                game, _text(p, "method", "none"), _text(p, "pledge_id")
            ),
            "map-travel": lambda game, p: engine.travel(
                game, _text(p, "destination_id", _text(p, "destination"))
            ),
            "use-item": lambda game, p: engine.use_item(game, _text(p, "item_id")),
            "market-refresh": lambda game, p: engine.refresh_market(
                game, force=_boolean(p, "force", False)
            ),
            "market-buy": lambda game, p: engine.buy_market_offer(
                game, _text(p, "offer_id")
            ),
            "market-lock": lambda game, p: engine.toggle_market_offer_lock(
                game, _text(p, "offer_id")
            ),
            "fight": lambda game, p: engine.fight(
                game, _text(p, "target_id"), objective=_text(p, "objective", "duel")
            ),
            "intrigue-guest": lambda game, p: engine.intrigue_guest_action(
                game, _text(p, "kind", "sect"), _text(p, "action"),
                _text(p, "npc_id", _text(p, "target_id")),
            ),
            "intrigue-personnel": lambda game, p: engine.intrigue_personnel_action(
                game, _text(p, "kind", "sect"), _text(p, "action"),
                _text(p, "npc_id", _text(p, "member_id")), _text(p, "position_id"),
                _integer(p, "years", 1), _text(p, "reason"),
            ),
            "intrigue-recruitment": lambda game, p: engine.intrigue_recruitment_action(
                game, _text(p, "action"), filters=p.get("filters"),
                candidate_ids=_string_tuple(p.get("candidate_ids")),
                player_vote=_boolean(p, "player_vote", True),
            ),
            "intrigue-resolution": lambda game, p: engine.intrigue_propose_resolution(
                game, _text(p, "kind", "sect"), _text(p, "resolution_type"),
                _text(p, "target_id"), player_vote=_boolean(p, "player_vote", True),
            ),
            "issue-bounty": lambda game, p: engine.issue_bounty(
                game, _text(p, "npc_id", _text(p, "target_id")), _text(p, "authority")
            ),
            "leave-faction": lambda game, p: engine.leave_faction(game),
            "market-sell-plant": lambda game, p: engine.sell_spirit_plant(
                game, _text(p, "item_id", _text(p, "asset_id"))
            ),
            "master-request": lambda game, p: engine.request_from_master(
                game, _text(p, "kind")
            ),
            "monster-evolve": lambda game, p: engine.evolve_monster(
                game, _text(p, "evolution_id")
            ),
            "natal-artifact": lambda game, p: engine.natal_artifact_action(
                game, _text(p, "action"), _text(p, "item_id"),
                _integer(p, "slot_index", -1),
            ),
            "party": lambda game, p: engine.manage_party(
                game, _text(p, "npc_id", _text(p, "target_id")), _text(p, "action")
            ),
            "post-battle-possession": lambda game, p: engine.post_battle_possess(
                game, _text(p, "target_id")
            ),
            "prison-action": lambda game, p: engine.prison_action(game, _text(p, "action")),
            "puppet-action": lambda game, p: engine.puppet_action(
                game, _text(p, "puppet_id"), _text(p, "action"), _text(p, "content_id")
            ),
            "race-diplomacy": lambda game, p: engine.propose_race_diplomacy(
                game, _text(p, "target_id"), _text(p, "status")
            ),
            "refine-souls": lambda game, p: engine.refine_foreign_souls(game),
            "relationship-capture": lambda game, p: engine.begin_relationship_capture(
                game, _text(p, "kind"), _text(p, "target_id")
            ),
            "relationship-exit": lambda game, p: engine.end_relationship(
                game, _text(p, "kind"), _text(p, "npc_id", _text(p, "target_id"))
            ),
            "relationship-faction": lambda game, p: engine.invite_relationship_to_faction(
                game, _text(p, "npc_id", _text(p, "target_id"))
            ),
            "secluded-refine-souls": lambda game, p: engine.secluded_refine_foreign_souls(game),
            "sense-breakthrough": lambda game, p: engine.attempt_divine_sense_breakthrough(game),
            "spirit-crossing": lambda game, p: engine.begin_spirit_crossing(game),
            "spirit-field-harvest": lambda game, p: engine.harvest_spirit_crop(
                game, _text(p, "plot_id")
            ),
            "spirit-field-irrigate": lambda game, p: engine.irrigate_spirit_crop(
                game, _text(p, "plot_id"),
                _number(p, "mp_ratio") if "mp_ratio" in p else _number(p, "mp_amount"),
                _text(p, "booster_id"),
            ),
            "spirit-field-plant": lambda game, p: engine.plant_spirit_crop(
                game, _text(p, "plant_id"),
                None if p.get("slot") is None else _integer(p, "slot"),
            ),
            "spirit-field-reclaim": lambda game, p: engine.reclaim_spirit_field(game),
            "spirit-plant-use": lambda game, p: engine.use_harvested_plant(
                game, _text(p, "item_id", _text(p, "asset_id"))
            ),
            "transformation": lambda game, p: engine.manage_transformation(
                game, _text(p, "form_id"), _text(p, "action")
            ),
            "transformation-absorb": lambda game, p: engine.absorb_transformation_material(
                game, _text(p, "item_id"), mode="direct", stat_id=_text(p, "stat_id")
            ),
            "transformation-batch": lambda game, p: engine.batch_absorb_transformation_material(
                game, _text(p, "item_id"), _text(p, "mode", "direct"),
                _text(p, "stat_id"),
            ),
            "transformation-purify": lambda game, p: engine.absorb_transformation_material(
                game, _text(p, "item_id"), mode="purified", stat_id=_text(p, "stat_id")
            ),
            "vassal-transfer": lambda game, p: engine.transfer_vassal_personnel(
                game, _text(p, "kind"), _text(p, "target_id"),
                _text(p, "npc_id", _text(p, "character_id")),
            ),
            "ascend-world": lambda game, p: engine.ascend_world(
                game, _text(p, "destination_world_id"),
                invited_ids=_string_tuple(p.get("invited_ids")),
            ),
            "war-action": lambda game, p: engine.war_action(
                game, _text(p, "war_id"), _text(p, "action"),
                ally_id=_text(p, "ally_id"),
            ),
            "war-peace": lambda game, p: engine.war_peace(
                game, _text(p, "war_id"), _text(p, "term", "white_peace"),
                target_id=_text(p, "target_id"),
                target_power_id=_text(p, "target_power_id"),
                third_party_id=_text(p, "third_party_id"),
                third_status=_text(p, "third_status", "neutral"),
                concede=_boolean(p, "concede", False),
            ),
            "settings": lambda game, p: engine.update_setting(
                game, _text(p, "setting"), _boolean(p, "enabled")
            ),
        }

    def _dao_companion(self, game_id: str, payload: dict[str, Any]) -> Any:
        action = _text(payload, "action")
        if action == "propose":
            return self.engine.propose_dao_companion(game_id, _text(payload, "npc_id"))
        return self.engine.interact_dao_companion(
            game_id, action, content_id=_text(payload, "content_id")
        )

    def _dao_friend(self, game_id: str, payload: dict[str, Any]) -> Any:
        action = _text(payload, "action")
        target_id = _text(payload, "npc_id", _text(payload, "target_id"))
        if action == "befriend":
            return self.engine.befriend_daoist(game_id, target_id)
        return self.engine.interact_dao_friend(game_id, target_id, action)

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    def dispatch(self, game_id: str, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = self._operations.get(operation)
        if handler is None:
            raise KeyError(f"未知命令：{operation}")
        result = handler(game_id, payload)
        if isinstance(result, CommandExecution):
            return {"game": result.game, "events": list(result.events)}
        if isinstance(result, dict):
            return result
        raise TypeError("命令返回值无法公开")


def build_handler(
    engine: GameEngine,
    web_root: Path = WEB_ROOT,
) -> type[BaseHTTPRequestHandler]:
    registry = HTTPCommandRegistry(engine)

    class Handler(BaseHTTPRequestHandler):
        server_version = "CultivationLife/2"

        def do_GET(self) -> None:  # noqa: N802
            try:
                path = urlparse(self.path).path
                if path == "/api/config":
                    self._json({
                        "format": "cultivation-life-v2",
                        "actions": {key: value.get("name", key) for key, value in engine.definitions.actions.items()},
                        "roots": {key: value.name for key, value in engine.definitions.roots.items() if value.creation},
                        "paths": dict(engine.definitions.paths),
                        "races": {
                            key: str(value.get("name", key))
                            for key, value in engine.definitions.races.items()
                        },
                        "worlds": {key: value.name for key, value in engine.definitions.worlds.items() if value.enabled},
                        "start_worlds": {
                            key: list(value)
                            for key, value in engine.definitions.start_worlds.items()
                        },
                        "operations": registry.operations,
                    })
                elif path == "/api/games":
                    self._json({"games": engine.list_games()})
                elif path.startswith("/api/games/"):
                    game_id = unquote(path.removeprefix("/api/games/").strip("/"))
                    self._json(engine.get_game(game_id))
                else:
                    self._static(path)
            except Exception as error:
                self._error(error)

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._validate_local_write()
                path = urlparse(self.path).path
                payload = self._body()
                if path == "/api/games":
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
                if len(parts) != 4 or parts[:2] != ["api", "games"]:
                    raise KeyError("接口不存在")
                self._json(registry.dispatch(unquote(parts[2]), parts[3], payload))
            except Exception as error:
                self._error(error)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1_000_000:
                raise ValueError("请求体大小非法")
            if self.headers.get_content_type() != "application/json":
                raise TypeError("写入接口只接受 application/json")
            document = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(document, dict):
                raise ValueError("请求体必须是JSON对象")
            return document

        def _validate_local_write(self) -> None:
            host = self.headers.get("Host", "")
            if urlparse(f"//{host}").hostname not in LOOPBACK_HOSTS:
                raise PermissionError("本地游戏接口拒绝非回环 Host")
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlparse(origin)
                if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOOPBACK_HOSTS:
                    raise PermissionError("本地游戏接口拒绝跨站写入")

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, error: Exception) -> None:
            status = (
                HTTPStatus.FORBIDDEN if isinstance(error, PermissionError)
                else HTTPStatus.UNSUPPORTED_MEDIA_TYPE if isinstance(error, TypeError)
                else HTTPStatus.NOT_FOUND if isinstance(error, KeyError)
                else HTTPStatus.BAD_REQUEST
            )
            self._json({"error": str(error).strip("'"), "type": type(error).__name__}, status)

        def _static(self, path: str) -> None:
            relative = "index.html" if path == "/" else path.lstrip("/")
            target = (web_root / relative).resolve()
            if web_root.resolve() not in target.parents or not target.is_file():
                raise KeyError("页面不存在")
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main() -> None:
    paths = resolve_runtime_paths()
    parser = argparse.ArgumentParser(description="浮生问道本地服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--database", type=Path, default=paths.database_path)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    engine = GameEngine(
        args.database,
        content_directory=paths.content_root,
        extension_root=paths.app_root,
    )
    server = ThreadingHTTPServer(
        (args.host, args.port),
        build_handler(engine, paths.web_root),
    )
    print(f"Cultivation Life running at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
