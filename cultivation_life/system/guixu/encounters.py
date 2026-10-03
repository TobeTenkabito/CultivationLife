from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
import copy
import random
from .dependencies import GuixuEncountersDependencies


def _maybe_guixu_npc_threat(
    deps: GuixuEncountersDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    session: dict[str, Any], rng: random.Random,
) -> None:
    if (
        not game.player.alive or session.get("pending_threat")
        or session.get("pending_team_offer")
        or session.get("trapped") or cycle.get("phase") != "open"
    ):
        return
    if int(session.get("threat_cooldown", 0)) > 0:
        session["threat_cooldown"] -= 1
        return
    transferable = deps._guixu_transferable_player_entries(game, dungeon, cycle, session)
    if not transferable:
        return
    visible_rank = (int(game.player.realm_index), int(game.player.layer))
    already_threatened = {str(actor_id) for actor_id in session.get("threatened_actor_ids", [])}
    candidates = [
        actor for actor in cycle.get("roster", [])
        if actor.get("status") == "active"
        and actor.get("layer_id") == session.get("layer_id")
        and str(actor.get("actor_id")) not in already_threatened
        and (
            int(actor.get("realm_index", 0)) > visible_rank[0]
            or (int(actor.get("realm_index", 0)) == visible_rank[0]
                and len(deps._guixu_active_team(cycle, actor)) > 1)
        )
    ]
    if not candidates or rng.random() >= float(
        deps._guixu_settings().get("npc_threat_chance_per_action", .58)
    ):
        return
    actor = max(
        candidates, key=lambda row: (int(row.get("realm_index", 0)), int(row.get("layer", 1))),
    )
    row, definition = max(transferable, key=lambda pair: float(pair[1].get("value", 0)))
    session.setdefault("threatened_actor_ids", []).append(actor["actor_id"])
    session["pending_threat"] = {
        "actor_id": actor["actor_id"], "actor_name": actor["name"],
        "actor_realm_index": int(actor["realm_index"]), "actor_layer": int(actor["layer"]),
        "pool_entry_id": row["pool_entry_id"], "treasure_name": definition["name"],
        "player_visible_realm_index": visible_rank[0], "player_visible_layer": visible_rank[1],
    }
    game.history.append(HistoryRecord(
        "SYS_GUIXU_NPC_THREAT", 1, game.player.age, "归墟恃强索宝",
        str(actor["actor_id"]), "threatened",
        f"{actor['name']}只看见你显露的修为，倚仗境界或同伴，逼你交出{definition['name']}保命。",
        {"dungeon_id": dungeon["id"], **copy.deepcopy(session["pending_threat"])},
        ["system", "guixu", "npc", "threat"],
    ))


def _guixu_actor(deps: GuixuEncountersDependencies, cycle: dict[str, Any], actor_id: str) -> dict[str, Any]:
    actor = next((row for row in cycle.get("roster", []) if row["actor_id"] == actor_id), None)
    if not actor or actor.get("status") not in {"active", "trapped"}:
        raise ValueError("目标修士已经不在当前归墟")
    return actor


def _guixu_relationship_role(deps: GuixuEncountersDependencies, game: GameState, npc_id: str) -> str | None:
    player = game.player
    if player.master and str(player.master.get("id")) == npc_id:
        return "师父"
    if player.dao_companion and str(player.dao_companion.get("id")) == npc_id:
        return "道侣"
    if any(str(row.get("id")) == npc_id for row in player.dao_friends):
        return "道友"
    if any(str(row.get("id")) == npc_id for row in player.disciples):
        return "弟子"
    if any(str(row.get("id")) == npc_id for row in player.concubines):
        return "侍妾"
    return None


def _break_guixu_relationship(deps: GuixuEncountersDependencies, game: GameState, npc_id: str, *, player_defending: bool = False) -> None:
    player = game.player
    player.party = [row for row in player.party if str(row.get("id")) != npc_id]
    if player.master and str(player.master.get("id")) == npc_id:
        player.master = None
    if player.dao_companion and str(player.dao_companion.get("id")) == npc_id:
        player.dao_companion = None
    player.dao_friends = [row for row in player.dao_friends if str(row.get("id")) != npc_id]
    player.disciples = [row for row in player.disciples if str(row.get("id")) != npc_id]
    player.concubines = [row for row in player.concubines if str(row.get("id")) != npc_id]
    if not player_defending:
        player.karma += 60
    player.fame += 25


def _guixu_fight(
    deps: GuixuEncountersDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    session: dict[str, Any], actor: dict[str, Any], rng: random.Random,
    *, player_defending: bool = False, enemy_first_round: bool = False,
) -> tuple[str, str]:
    allies = []
    for ally_id in session.get("recruited_actor_ids", []):
        ally = next((row for row in cycle.get("roster", []) if row["actor_id"] == ally_id), None)
        if ally and ally.get("status") == "recruited":
            allies.append({
                "name": ally["name"], "power_ratio": float(ally["power"]) / max(1.0, float(actor["power"])),
                "realm_offset": int(ally["realm_index"]) - game.player.realm_index,
            })
    target = {
        "enemy_first_round": enemy_first_round,
        "player_defending": player_defending,
        "target_name": actor["name"], "target_power": float(actor["power"]),
        "primary_power": float(actor["power"]), "target_realm_index": int(actor["realm_index"]),
        "target_layer": int(actor["layer"]), "combat_type": "cultivator", "action": "slay",
        "npc_id": actor.get("npc_id") or actor["actor_id"], "kill_karma": True,
        "non_story_combat": True, "player_allies": allies,
        "natural_terrain": "狭窄", "artificial_conditions": [],
        "kill_pursuit_threshold": float(
            deps._guixu_settings().get("combat_kill_pursuit_threshold", .58)
        ),
        "pursuit_chance_bonus": float(
            deps._guixu_settings().get("combat_pursuit_chance_bonus", .22)
        ),
    }
    team = deps._guixu_active_team(cycle, actor)
    if len(team) > 1:
        target["members"] = [{"name": row["name"], "power": float(row["power"]),
                              "realm_index": int(row["realm_index"]), "layer": int(row["layer"]),
                              "npc_id": row.get("npc_id") or row["actor_id"], "actor_id": row["actor_id"]}
                             for row in team]
        target["target_power"] = sum(float(row["power"]) for row in team)
    result, summary = deps._combat(game, target, True, rng)
    if result == "killed":
        killed_id = target.get("killed_member", {}).get("actor_id")
        actor = next((row for row in team if row["actor_id"] == killed_id), actor)
        actor["status"] = "dead"
        if actor.get("team_id"):
            deps._dissolve_guixu_npc_team(
                game, dungeon, cycle, str(actor["team_id"]),
                f"因{actor['name']}被玩家击杀而崩解",
            )
        for row in cycle.get("round_entries", []):
            if row.get("holder_id") == actor["actor_id"]:
                deps._guixu_grant_entry(game, dungeon, row, "combat")
        if actor.get("npc_id") and deps._guixu_relationship_role(game, str(actor["npc_id"])):
            deps._break_guixu_relationship(game, str(actor["npc_id"]), player_defending=player_defending)
    deps._consume_guixu_days(
        game, dungeon, cycle, session,
        int(deps._guixu_settings()["action_days"]["combat"]), rng,
    )
    return result, summary


def _guixu_offer_team(deps: GuixuEncountersDependencies, game, cycle, session):
    if (not game.player.alive or cycle.get("phase") != "open"
            or session.get("team_offer_made") or session.get("trapped") or game.player.party
            or session.get("recruited_actor_ids") or session.get("pending_threat")):
        return
    candidates = [a for a in cycle.get("roster", []) if a.get("status") == "active"
                  and (int(a.get("realm_index", 0)), int(a.get("layer", 1)))
                      > (game.player.realm_index, game.player.layer)]
    if candidates:
        actor = min(candidates, key=lambda a: (a["realm_index"], a["layer"], a["actor_id"]))
        session["team_offer_made"] = True
        session["pending_team_offer"] = {"actor_id":actor["actor_id"], "name":actor["name"]}


def _guixu_team_tick(deps: GuixuEncountersDependencies, game, dungeon, cycle, session, rng):
    """One tick per time-consuming player action, never per repaint/response."""
    session["action_serial"] = int(session.get("action_serial", 0)) + 1
    serial = session["action_serial"]
    for actor in cycle.get("roster", []):
        if actor.get("actor_id") not in session.get("recruited_actor_ids", []) or actor.get("status") != "recruited":
            continue
        actor["layer_id"] = session["layer_id"]
        if not actor.get("temporary_invitation"):
            continue
        has_treasure = any(row.get("holder_id") == actor["actor_id"] and row.get("resolution") == "held"
                           for row in cycle.get("round_entries", []))
        if has_treasure:
            actor.pop("empty_since_action", None)
            continue
        if not session.get("player_ever_claimed"):
            continue
        since = actor.setdefault("empty_since_action", serial)
        if serial - since < 3:
            continue
        session["recruited_actor_ids"].remove(actor["actor_id"])
        actor["status"] = "active"
        actor.pop("team_id", None)
        session["pending_threat"] = None
        result, summary = deps._guixu_fight(game, dungeon, cycle, session, actor, rng,
                                           player_defending=True, enemy_first_round=True)
        session["threat_cooldown"] = 1
        game.history.append(HistoryRecord(
            "SYS_GUIXU_TEAM_BETRAYAL", 1, game.player.age, "临时队友背刺", actor["actor_id"], result,
            f"{actor['name']}见你得宝而自己迟迟空手，在第三个行动间隔突然背刺！{summary}",
            {"enemy_first_round":True, "player_defending":True}, ["guixu", "combat", "betrayal"],
        ))
        return True
    return False
