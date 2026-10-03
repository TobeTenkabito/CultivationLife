from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import SectNpc
from ...content_registry import WORLD_SYSTEMS
import copy
from .dependencies import GuixuPresentationDependencies


def _public_guixu(deps: GuixuPresentationDependencies, game: GameState) -> dict[str, Any]:
    deps._ensure_guixu_state(game)
    if not deps.guixu_content_available():
        return {"available": False, "dungeons": [], "session": None}
    definitions = deps._guixu_definitions()
    rows = []
    for dungeon_id, dungeon in definitions.items():
        if dungeon["world"] != game.player.world:
            continue
        cycle = game.guixu_state["cycles"][dungeon_id]
        entry_key = f"{dungeon_id}:{cycle['cycle_index']}"
        location_matches = bool(
            game.player.world == dungeon["world"]
            and game.player.location_id == dungeon["entry_location_id"]
        )
        rank_matches = (
            game.player.realm_index, game.player.layer,
        ) <= tuple(dungeon["max_entry_rank"])
        not_entered = entry_key not in game.guixu_state["entered_cycles"]
        no_active_session = not game.guixu_state.get("player_session")
        phase_open = cycle["phase"] == "open"
        max_rank_name = deps._npc_realm_name(SectNpc(
            "guixu-entry-limit", "", "", *map(int, dungeon["max_entry_rank"]),
            game.player.age, None, path=game.player.path, world=dungeon["world"],
        ))
        current_rank_name = deps._npc_realm_name(SectNpc(
            "guixu-player-rank", game.player.name, "", game.player.realm_index,
            game.player.layer, game.player.age, game.player.lifespan,
            path=game.player.path, world=game.player.world,
        ))
        round_entries = []
        for row in cycle.get("round_entries", []):
            definition = deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
            holder = next((actor for actor in cycle.get("roster", []) if actor["actor_id"] == row.get("holder_id")), None)
            round_entries.append({
                **copy.deepcopy(row), "name": definition["name"], "tier": definition["tier"],
                "category": definition["category"], "value": definition.get("value", 0),
                "holder_name": holder.get("name") if holder else None,
            })
        rows.append({
            "id": dungeon_id, "name": dungeon["name"], "world": dungeon["world"],
            "world_name": WORLD_SYSTEMS.get("world_names", {}).get(dungeon["world"], dungeon["world"]),
            "entry_location_id": dungeon["entry_location_id"],
            "entry_location_name": deps.maps.location(dungeon["world"], dungeon["entry_location_id"])["name"],
            "max_entry_rank": dungeon["max_entry_rank"], "eject_rank": dungeon["eject_rank"],
            "window_days": dungeon["window_days"], "phase": cycle["phase"],
            "cycle_index": cycle["cycle_index"], "next_open_age": cycle["next_open_age"],
            "next_announce_age": cycle["next_announce_age"], "pool_remaining": len(cycle["pool_remaining"]),
            "round_entries": round_entries, "last_report": copy.deepcopy(cycle.get("last_report")),
            "entry_requirements": {
                "phase_open": phase_open, "location_matches": location_matches,
                "rank_matches": rank_matches, "not_entered": not_entered,
                "no_active_session": no_active_session,
                "player_available": bool(game.player.alive and not game.pending_event),
                "max_rank_name": max_rank_name, "current_rank_name": current_rank_name,
                "suppression_active": bool(game.player.cultivation_suppression),
            },
            "can_enter": bool(
                phase_open and location_matches and rank_matches and not_entered
                and no_active_session and game.player.alive and not game.pending_event
            ),
        })
    session = copy.deepcopy(game.guixu_state.get("player_session"))
    if session:
        dungeon, cycle = deps._guixu_cycle_and_definition(game, str(session["dungeon_id"]))
        session["transferable_treasures"] = [{"pool_entry_id":row["pool_entry_id"], "name":definition["name"]}
            for row, definition in deps._guixu_transferable_player_entries(game, dungeon, cycle, session)]
        session["companions"] = [{
            "actor_id":actor["actor_id"], "name":actor["name"],
            "has_treasure":any(row.get("holder_id") == actor["actor_id"] and row.get("resolution") == "held" for row in cycle.get("round_entries", [])),
            "empty_intervals": max(0, int(session.get("action_serial", 0)) - int(actor.get("empty_since_action", session.get("action_serial", 0)))),
        } for actor in cycle.get("roster", []) if actor["actor_id"] in session.get("recruited_actor_ids", []) and actor.get("status") == "recruited"]
        session["dungeon_name"] = dungeon["name"]
        session["return_days"] = deps._guixu_return_days(str(session["layer_id"]))
        session["layers"] = [{
            **copy.deepcopy(layer),
            "current": layer["id"] == session["layer_id"],
            "locked": layer["id"] == "secret" and not session.get("secret_unlocked"),
        } for layer in dungeon["layers"]]
        expedition_open = cycle.get("phase") == "open"
        session["actors"] = ([
            {
                **copy.deepcopy(actor),
                "realm_name": deps._npc_realm_name(SectNpc(
                    "guixu-public-actor", str(actor.get("name", "")), "",
                    int(actor.get("realm_index", 0)), int(actor.get("layer", 1)),
                    game.player.age, None, world=dungeon["world"],
                )),
            }
            for actor in cycle.get("roster", [])
            if actor.get("layer_id") == session["layer_id"] and actor.get("status") in {"active", "recruited"}
        ] if expedition_open else [])
        session["treasures"] = ([
            row for row in next(item for item in rows if item["id"] == dungeon["id"])["round_entries"]
            if row["layer_id"] == session["layer_id"] and row["resolution"] in {"unclaimed", "held"}
        ] if expedition_open else [])
        session["npc_teams"] = [
            copy.deepcopy(team) for team in cycle.get("npc_teams", [])
            if team.get("status") == "active" and team.get("layer_id") == session["layer_id"]
        ] if expedition_open else []
        session["npc_incidents"] = copy.deepcopy(cycle.get("npc_incidents", [])[-8:])
        threat = session.get("pending_threat")
        if threat:
            threat["actor_realm_name"] = deps._npc_realm_name(SectNpc(
                "guixu-threat-actor", str(threat.get("actor_name", "")), "",
                int(threat["actor_realm_index"]), int(threat["actor_layer"]),
                game.player.age, None, world=dungeon["world"],
            ))
            threat["player_visible_realm_name"] = deps._npc_realm_name(SectNpc(
                "guixu-threat-player", game.player.name, "", game.player.realm_index,
                game.player.layer, game.player.age, game.player.lifespan,
                path=game.player.path, world=game.player.world,
            ))
    return {"available": bool(rows or session), "dungeons": rows, "session": session}
