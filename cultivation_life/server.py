from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .content_registry import (
    FACTION_DEFINITIONS,
    EXTENSION_REPORT,
    PATH_NAMES,
    RACE_DEFINITIONS,
    ROOT_DEFINITIONS,
    ROOT_NAMES,
    TECHNIQUE_ELEMENT_NAMES,
    WORLD_SYSTEMS,
    MONSTER_SPECIES,
)
from .engine import GameEngine
from .extension_system import write_extension_preference
from .rules import QI_SOURCE_NAMES
from .runtime import persistence_root
from .version import BASE_GAME_VERSION, base_game_metadata


SOURCE_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT
PERSISTENCE_ROOT = persistence_root(APP_ROOT)
BUNDLED_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
ENGINE_ROOT = APP_ROOT if (APP_ROOT / "content").is_dir() else BUNDLED_ROOT
WEB_ROOT = (APP_ROOT / "web") if (APP_ROOT / "web").is_dir() else (BUNDLED_ROOT / "web")
ENGINE = GameEngine(ENGINE_ROOT, PERSISTENCE_ROOT / "data" / "saves")


class Handler(BaseHTTPRequestHandler):
    server_version = f"CultivationLife/{BASE_GAME_VERSION}"

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/config":
                self._json({
                    "base_game": base_game_metadata(),
                    "spirit_roots": ROOT_NAMES,
                    "spirit_root_details": {
                        key: value for key, value in ROOT_DEFINITIONS.items() if value["creation"]
                    },
                    "paths": {
                        path_id: name for path_id, name in PATH_NAMES.items()
                        if path_id != "monster" or MONSTER_SPECIES
                    },
                    "technique_elements": TECHNIQUE_ELEMENT_NAMES,
                    "factions": FACTION_DEFINITIONS,
                    "races": RACE_DEFINITIONS,
                    "worlds": WORLD_SYSTEMS.get("world_names", {}),
                    "start_worlds": WORLD_SYSTEMS.get("start_worlds", {}),
                    "qi_sources": QI_SOURCE_NAMES,
                    "quick_starts": WORLD_SYSTEMS.get("quick_start_presets", []),
                    "extensions": EXTENSION_REPORT,
                    "monster_species": MONSTER_SPECIES,
                })
            elif path == "/api/games":
                self._json({"games": ENGINE.list_games()})
            elif path == "/api/achievements":
                self._json(ENGINE.list_achievements())
            elif path.startswith("/api/games/"):
                game_id = path.removeprefix("/api/games/").strip("/")
                self._json(ENGINE.get_game(game_id))
            else:
                self._static(path)
        except Exception as error:  # boundary: translate domain errors to JSON
            self._error(error)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._body()
            if path.startswith("/api/extensions/"):
                package_id = unquote(path.removeprefix("/api/extensions/").strip("/"))
                if not isinstance(payload.get("enabled"), bool):
                    raise ValueError("enabled 必须是布尔值")
                write_extension_preference(PERSISTENCE_ROOT, package_id, payload["enabled"])
                self._json({
                    "id": package_id, "enabled": payload["enabled"], "restart_required": True,
                    "message": "扩展配置已保存，将在下次启动时生效。",
                })
                return
            if path == "/api/games":
                result = ENGINE.create_game(
                    payload.get("name", ""), payload.get("spirit_root", "supreme_metal"),
                    payload.get("path", "dao"), payload.get("seed"), payload.get("technique_element", "neutral"),
                    payload.get("preset_id"), payload.get("start_world"),
                    payload.get("monster_species_id"),
                )
                self._json(result, HTTPStatus.CREATED)
                return
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "games"]:
                raise KeyError("接口不存在")
            game_id, operation = parts[2], parts[3]
            ENGINE.assert_ghost_operation_allowed(game_id, operation)
            if operation == "advance":
                result = ENGINE.advance(game_id, payload.get("action", "cultivate"), payload.get("years", 1))
            elif operation == "choice":
                result = ENGINE.choose(game_id, payload.get("choice_id", ""))
            elif operation == "use-item":
                result = ENGINE.use_item(game_id, payload.get("item_id", ""))
            elif operation == "faction-reward":
                result = ENGINE.set_faction_reward(game_id, payload.get("reward_id", ""))
            elif operation == "market-buy":
                result = ENGINE.buy_market_offer(game_id, payload.get("offer_id", ""))
            elif operation == "market-lock":
                result = ENGINE.toggle_market_offer_lock(game_id, payload.get("offer_id", ""))
            elif operation == "market-sell-plant":
                result = ENGINE.sell_spirit_plant(game_id, payload.get("item_id", ""))
            elif operation == "auction-consign":
                result = ENGINE.consign_auction_item(
                    game_id, payload.get("item_id", ""), int(payload.get("start_price", 0) or 0)
                )
            elif operation == "auction-bid":
                result = ENGINE.place_auction_bid(game_id, payload.get("lot_id", ""))
            elif operation == "auction-advance":
                result = ENGINE.advance_auction_round(game_id)
            elif operation == "auction-negotiate":
                result = ENGINE.negotiate_at_auction(game_id, payload.get("npc_id", ""))
            elif operation == "auction-identity":
                result = ENGINE.choose_auction_identity(game_id, payload.get("alias", ""))
            elif operation == "auction-private-buy":
                result = ENGINE.buy_private_trade_item(
                    game_id, payload.get("npc_id", ""), payload.get("offer_id", "")
                )
            elif operation == "auction-private-sell":
                result = ENGINE.sell_private_trade_item(
                    game_id, payload.get("npc_id", ""), payload.get("item_id", "")
                )
            elif operation == "auction-private-bargain":
                result = ENGINE.bargain_private_trade(
                    game_id, payload.get("npc_id", ""), payload.get("side", ""), payload.get("asset_id", "")
                )
            elif operation == "transformation-absorb":
                result = ENGINE.absorb_transformation_material(
                    game_id, payload.get("item_id", ""), False, payload.get("stat_id", "")
                )
            elif operation == "transformation-purify":
                result = ENGINE.absorb_transformation_material(
                    game_id, payload.get("item_id", ""), True, payload.get("stat_id", "")
                )
            elif operation == "settings":
                result = ENGINE.update_setting(
                    game_id, payload.get("setting", ""), bool(payload.get("enabled", False))
                )
            elif operation == "black-market-search":
                result = ENGINE.search_black_market(game_id, payload.get("pattern", ""))
            elif operation == "black-market-buy":
                result = ENGINE.buy_black_market_item(game_id, payload.get("result_id", ""))
            elif operation == "black-market-sell":
                result = ENGINE.sell_black_market_asset(
                    game_id, payload.get("kind", ""), payload.get("asset_id", "")
                )
            elif operation == "spirit-field-reclaim":
                result = ENGINE.reclaim_spirit_field(game_id)
            elif operation == "spirit-field-plant":
                slot = payload.get("slot")
                result = ENGINE.plant_spirit_crop(
                    game_id, payload.get("plant_id", ""), int(slot) if slot is not None else None
                )
            elif operation == "spirit-field-irrigate":
                result = ENGINE.irrigate_spirit_crop(
                    game_id, payload.get("plot_id", ""), float(payload.get("mp_amount", 0) or 0),
                    payload.get("booster_id", ""),
                )
            elif operation == "spirit-field-harvest":
                result = ENGINE.harvest_spirit_crop(game_id, payload.get("plot_id", ""))
            elif operation == "alchemy":
                result = ENGINE.refine_pill(
                    game_id, payload.get("target_item_id", ""), payload.get("materials", [])
                )
            elif operation == "crafting-preview":
                result = ENGINE.preview_crafting(game_id, payload)
            elif operation == "crafting-forge":
                result = ENGINE.forge_crafted_artifact(game_id, payload)
            elif operation == "crafting-blueprint":
                result = ENGINE.save_crafting_blueprint(game_id, payload)
            elif operation == "crafted-artifact":
                result = ENGINE.crafted_artifact_action(
                    game_id, payload.get("artifact_id", ""), payload.get("action", ""),
                    int(payload.get("start_price", 0) or 0),
                )
            elif operation == "formation-preview":
                result = ENGINE.preview_formation(game_id, payload)
            elif operation == "formation-save":
                result = ENGINE.save_formation(game_id, payload)
            elif operation == "formation-activate":
                result = ENGINE.activate_formation(game_id, payload.get("formation_id", ""))
            elif operation == "formation-deactivate":
                result = ENGINE.deactivate_formation(game_id)
            elif operation == "formation-delete":
                result = ENGINE.delete_formation(game_id, payload.get("formation_id", ""))
            elif operation == "formation-ground-deploy":
                result = ENGINE.deploy_ground_formation(game_id, payload.get("owner_kind", "player"))
            elif operation == "formation-ground-withdraw":
                result = ENGINE.withdraw_ground_formation(game_id, payload.get("ground_formation_id", ""))
            elif operation == "formation-ground-repair":
                result = ENGINE.repair_ground_formation(
                    game_id, payload.get("ground_formation_id", ""), payload.get("supply_id", ""),
                    int(payload.get("quantity", 1) or 1),
                )
            elif operation == "spirit-plant-use":
                result = ENGINE.use_harvested_plant(game_id, payload.get("item_id", ""))
            elif operation == "black-market-leave":
                result = ENGINE.leave_black_market(game_id)
            elif operation == "map-travel":
                result = ENGINE.travel_map(game_id, payload.get("destination", ""))
            elif operation == "equip-technique":
                result = ENGINE.equip_known_technique(
                    game_id, payload.get("technique_id", ""), payload.get("slot", "")
                )
            elif operation == "transformation":
                result = ENGINE.manage_transformation(
                    game_id, payload.get("form_id", ""), payload.get("action", "")
                )
            elif operation == "body-breakthrough":
                result = ENGINE.body_breakthrough(game_id)
            elif operation == "sense-breakthrough":
                result = ENGINE.divine_sense_breakthrough(game_id)
            elif operation == "ghost-reincarnate":
                result = ENGINE.reincarnate_ghost(game_id)
            elif operation == "ghost-reincarnation-prompt":
                result = ENGINE.prepare_ghost_reincarnation(game_id)
            elif operation == "ghost-wangsheng":
                result = ENGINE.spend_wangsheng(game_id, bool(payload.get("all", False)))
            elif operation == "ghost-parade":
                result = ENGINE.ghost_parade_action(
                    game_id, payload.get("soul_id", ""), payload.get("action", "")
                )
            elif operation == "ghost-soul":
                result = ENGINE.ghost_soul_action(
                    game_id, payload.get("soul_id", ""), payload.get("action", ""), payload.get("slot", "")
                )
            elif operation == "ghost-attachment":
                result = ENGINE.ghost_attachment_action(
                    game_id, payload.get("action", ""), payload.get("item_id", "")
                )
            elif operation == "ghost-constraint":
                result = ENGINE.ghost_constraint_action(game_id, payload.get("action", ""))
            elif operation == "ghost-leave-host":
                result = ENGINE.leave_possessed_body(game_id)
            elif operation == "post-battle-possession":
                result = ENGINE.post_battle_possess(game_id, payload.get("target_id", ""))
            elif operation == "captive-action":
                result = ENGINE.captive_action(
                    game_id, payload.get("target_id", ""), payload.get("action", "")
                )
            elif operation == "relationship-capture":
                result = ENGINE.begin_relationship_capture(
                    game_id, payload.get("kind", ""), payload.get("target_id", "")
                )
            elif operation == "puppet-action":
                result = ENGINE.puppet_action(
                    game_id, payload.get("puppet_id", ""), payload.get("action", ""),
                    payload.get("content_id", ""),
                )
            elif operation == "craft-puppet":
                result = ENGINE.craft_mechanical_puppet(game_id)
            elif operation == "refine-souls":
                result = ENGINE.refine_foreign_souls(game_id)
            elif operation == "secluded-refine-souls":
                result = ENGINE.secluded_refine_foreign_souls(game_id)
            elif operation == "faction-dispatch":
                result = ENGINE.dispatch_disciple(game_id, payload.get("target", ""))
            elif operation == "faction-relationship":
                result = ENGINE.manage_faction_relationship(
                    game_id, payload.get("npc_id", ""), payload.get("role", "")
                )
            elif operation == "party":
                result = ENGINE.manage_party(
                    game_id, payload.get("npc_id", ""), payload.get("action", "")
                )
            elif operation == "dao-companion":
                result = ENGINE.manage_dao_companion(
                    game_id, payload.get("action", ""), payload.get("npc_id", ""),
                    payload.get("kind", ""), payload.get("content_id", ""),
                )
            elif operation == "dao-friend":
                result = ENGINE.manage_dao_friend(
                    game_id, payload.get("npc_id", ""), payload.get("action", "")
                )
            elif operation == "relationship-faction":
                result = ENGINE.invite_relationship_to_faction(game_id, payload.get("npc_id", ""))
            elif operation == "relationship-exit":
                result = ENGINE.leave_relationship(
                    game_id, payload.get("kind", ""), payload.get("npc_id", "")
                )
            elif operation == "leave-faction":
                result = ENGINE.leave_faction(game_id)
            elif operation == "prison-action":
                result = ENGINE.prison_action(game_id, payload.get("action", ""))
            elif operation == "disciple-request":
                result = ENGINE.respond_disciple_request(
                    game_id, payload.get("request_id", ""), bool(payload.get("accept", False))
                )
            elif operation == "master-request":
                result = ENGINE.request_from_master(game_id, payload.get("kind", ""))
            elif operation == "disciple-gift":
                result = ENGINE.gift_disciple(
                    game_id, payload.get("disciple_id", ""), payload.get("kind", ""),
                    payload.get("content_id", ""),
                )
            elif operation == "spirit-crossing":
                result = ENGINE.begin_spirit_crossing(game_id)
            elif operation == "celestial-ascension":
                result = ENGINE.begin_celestial_ascension(game_id)
            elif operation == "asura-ascension":
                result = ENGINE.begin_asura_ascension(game_id)
            elif operation == "heavenly-election":
                result = ENGINE.resolve_heavenly_election(
                    game_id, payload.get("method", "none"), payload.get("pledge_id", "")
                )
            elif operation == "heavenly-court":
                result = ENGINE.heavenly_court_action(
                    game_id, payload.get("action", ""), payload.get("target_id", ""),
                    payload.get("enact"), int(payload.get("influence_spend", 0) or 0),
                )
            elif operation == "natal-artifact":
                result = ENGINE.natal_artifact_action(
                    game_id, payload.get("action", ""), payload.get("item_id", ""),
                    int(payload.get("slot_index", -1)),
                )
            elif operation == "cross-world":
                result = ENGINE.cross_world(game_id, payload.get("destination", ""))
            elif operation == "create-faction":
                result = ENGINE.create_faction(game_id, payload.get("name", ""))
            elif operation == "create-family":
                result = ENGINE.create_family(game_id, payload.get("name", ""))
            elif operation == "race-diplomacy":
                result = ENGINE.propose_race_diplomacy(
                    game_id, payload.get("target_id", ""), payload.get("status", "")
                )
            elif operation == "faction-diplomacy":
                result = ENGINE.propose_sect_diplomacy(
                    game_id, payload.get("target_id", ""), payload.get("status", "")
                )
            elif operation == "vassal-transfer":
                result = ENGINE.transfer_vassal_personnel(
                    game_id, payload.get("kind", ""), payload.get("target_id", ""), payload.get("npc_id", "")
                )
            elif operation == "war-action":
                result = ENGINE.war_action(
                    game_id, payload.get("war_id", ""), payload.get("action", ""),
                    ally_id=payload.get("ally_id", ""),
                )
            elif operation == "war-peace":
                result = ENGINE.war_peace(
                    game_id, payload.get("war_id", ""), payload.get("term", "white_peace"),
                    target_id=payload.get("target_id", ""),
                    target_power_id=payload.get("target_power_id", ""),
                    third_party_id=payload.get("third_party_id", ""),
                    third_status=payload.get("third_status", "neutral"),
                    concede=bool(payload.get("concede", False)),
                )
            elif operation == "issue-bounty":
                result = ENGINE.issue_bounty(
                    game_id, payload.get("npc_id", ""), payload.get("authority", "")
                )
            elif operation == "faction-intercept":
                result = ENGINE.intercept_faction_npc(game_id, payload.get("npc_id", ""))
            elif operation == "breakthrough":
                result = ENGINE.breakthrough(game_id)
            elif operation == "monster-evolve":
                result = ENGINE.evolve_monster(game_id, payload.get("evolution_id", ""))
            elif operation == "custom-lineage-prepare":
                result = ENGINE.prepare_custom_lineage(game_id, payload.get("evolution_id", ""))
            elif operation == "custom-lineage-confirm":
                result = ENGINE.confirm_custom_lineage(
                    game_id, payload.get("evolution_id", ""), payload.get("name", ""), payload.get("rules", []),
                )
            elif operation == "debug-world-news":
                result = ENGINE.set_world_news_debug(game_id, bool(payload.get("enabled", False)))
            else:
                raise KeyError("接口不存在")
            self._json(result)
        except Exception as error:
            self._error(error)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length > 1_000_000:
            raise ValueError("请求体过大")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str) -> None:
        relative = "index.html" if path == "/" else unquote(path.lstrip("/"))
        target = (WEB_ROOT / relative).resolve()
        if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
            raise KeyError("文件不存在")
        if not target.is_file():
            raise KeyError("文件不存在")
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, error: Exception) -> None:
        status = HTTPStatus.NOT_FOUND if isinstance(error, KeyError) else HTTPStatus.BAD_REQUEST
        self._json({"error": str(error).strip("'\"")}, status)

    def log_message(self, format: str, *args: object) -> None:
        if sys.stdout is not None:
            print(f"[浮生问道] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行《浮生问道》本地服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    if sys.stdout is not None:
        print(f"《浮生问道》本体 v{BASE_GAME_VERSION} 已启动：http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if sys.stdout is not None:
            print("\n服务器已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
