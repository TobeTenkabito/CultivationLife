from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
from ...content_registry import REALMS
from ...rules import expected_combat_power
import random
from .dependencies import GuixuNpcsDependencies


def _guixu_relation_ids(deps: GuixuNpcsDependencies, game: GameState) -> set[str]:
    player = game.player
    return {
        str(row.get("id")) for row in [
            player.master, player.dao_companion, *player.dao_friends,
            *player.disciples, *player.concubines,
        ] if row and row.get("id")
    }


def _generate_guixu_roster(
    deps: GuixuNpcsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
) -> list[dict[str, Any]]:
    maximum = tuple(map(int, dungeon["max_entry_rank"]))
    fixed_candidates = [
        npc for npc in deps._all_world_npcs(game)
        if npc.alive and npc.world == dungeon["world"]
        and (npc.realm_index, npc.layer) <= maximum
    ]
    rng.shuffle(fixed_candidates)
    used_fixed: set[str] = set()
    roster: list[dict[str, Any]] = []
    rank_bands = {
        "outer": (5, 11), "middle": (3, 8), "inner": (1, 5), "final": (0, 3),
    }
    for layer in dungeon["layers"]:
        layer_id = str(layer["id"])
        if layer_id == "secret":
            continue
        size = int(layer.get("roster_size", 0))
        fixed = [npc for npc in fixed_candidates if npc.id not in used_fixed][:min(2, size)]
        for npc in fixed:
            used_fixed.add(npc.id)
            power = deps._npc_power(npc)
            roster.append({
                "actor_id": f"fixed:{npc.id}", "actor_kind": "fixed", "npc_id": npc.id,
                "name": npc.name, "layer_id": layer_id, "realm_index": npc.realm_index,
                "layer": npc.layer, "power": round(power, 1), "status": "active",
                "protected": npc.id in deps._guixu_relation_ids(game),
            })
        low, high = rank_bands[layer_id]
        for index in range(size - len(fixed)):
            offset = rng.randint(low, high)
            realm_index, realm_layer = maximum
            realm_layer -= offset
            while realm_layer < 1 and realm_index > 1:
                realm_index -= 1
                realm_layer += REALMS[realm_index].layers
            realm_index = max(1, realm_index)
            realm_layer = max(1, min(REALMS[realm_index].layers, realm_layer))
            power = expected_combat_power(realm_index, realm_layer) * rng.uniform(.88, 1.16)
            actor_id = f"anon:{cycle['cycle_index']}:{layer_id}:{index}"
            roster.append({
                "actor_id": actor_id, "actor_kind": "anonymous", "npc_id": None,
                "name": f"{layer['name']}修士·{index + 1}", "layer_id": layer_id,
                "realm_index": realm_index, "layer": realm_layer,
                "power": round(power, 1), "status": "active", "protected": False,
            })
    return roster


def _form_guixu_npc_teams(
    deps: GuixuNpcsDependencies, cycle: dict[str, Any], rng: random.Random,
) -> None:
    """Create short-lived NPC teams without introducing a second party model."""
    cycle["npc_teams"] = []
    chance = float(deps._guixu_settings().get("npc_team_form_chance", .55))
    maximum = max(2, int(deps._guixu_settings().get("npc_team_max_size", 3)))
    serial = 0
    eligible_by_layer: dict[str, list[dict[str, Any]]] = {}
    for actor in cycle.get("roster", []):
        actor.pop("team_id", None)
        actor.pop("team_name", None)
        if actor.get("status") == "active":
            eligible_by_layer.setdefault(str(actor["layer_id"]), []).append(actor)
    for layer_id, candidates in eligible_by_layer.items():
        rng.shuffle(candidates)
        while len(candidates) >= 2:
            # Every expedition has at least one visible temporary alliance;
            # the configured chance controls additional teams.
            if cycle["npc_teams"] and rng.random() > chance:
                candidates.pop()
                continue
            size = min(len(candidates), rng.randint(2, maximum))
            members = [candidates.pop() for _ in range(size)]
            serial += 1
            team_id = f"npc-team:{cycle['cycle_index']}:{serial}"
            team_name = f"临潮盟·{serial}"
            for actor in members:
                actor["team_id"] = team_id
                actor["team_name"] = team_name
            cycle["npc_teams"].append({
                "id": team_id, "name": team_name, "layer_id": layer_id,
                "member_ids": [str(actor["actor_id"]) for actor in members],
                "status": "active", "break_reason": None,
            })
    if not cycle["npc_teams"]:
        fallback = next((rows for rows in eligible_by_layer.values() if len(rows) >= 2), None)
        if fallback:
            serial += 1
            team_id = f"npc-team:{cycle['cycle_index']}:{serial}"
            team_name = f"临潮盟·{serial}"
            members = fallback[:2]
            for actor in members:
                actor["team_id"] = team_id
                actor["team_name"] = team_name
            cycle["npc_teams"].append({
                "id": team_id, "name": team_name,
                "layer_id": str(members[0]["layer_id"]),
                "member_ids": [str(actor["actor_id"]) for actor in members],
                "status": "active", "break_reason": None,
            })


def _dissolve_guixu_npc_team(
    deps: GuixuNpcsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    team_id: str | None, reason: str,
) -> None:
    if not team_id:
        return
    team = next(
        (row for row in cycle.get("npc_teams", []) if row.get("id") == team_id), None,
    )
    if not team or team.get("status") != "active":
        return
    team["status"] = "dissolved"
    team["break_reason"] = reason
    for actor in cycle.get("roster", []):
        if actor.get("team_id") == team_id:
            actor.pop("team_id", None)
            actor.pop("team_name", None)
    game.history.append(HistoryRecord(
        "SYS_GUIXU_NPC_TEAM_BREAK", 1, game.player.age, "归墟临盟翻脸",
        str(team_id), "dissolved", f"{team['name']}{reason}，众修当场翻脸散伙。",
        {"dungeon_id": dungeon["id"], "team_id": team_id, "reason": reason},
        ["system", "guixu", "npc", "team"],
    ))


def _guixu_npc_claim_entry(
    deps: GuixuNpcsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    row: dict[str, Any], actor: dict[str, Any], source: str,
) -> None:
    row["holder_id"] = actor["actor_id"]
    row["resolution"] = "held"
    row["npc_claim_source"] = source
    team_id = actor.get("team_id")
    if team_id:
        treasure = deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
        deps._dissolve_guixu_npc_team(
            game, dungeon, cycle, str(team_id),
            f"因{actor['name']}取得{treasure['name']}而利益破裂",
        )


def _assign_due_guixu_entries(
    deps: GuixuNpcsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    elapsed_days: int, rng: random.Random,
) -> None:
    if cycle.get("phase") == "open" and cycle.get("roster") and not cycle.get("npc_teams"):
        deps._form_guixu_npc_teams(cycle, rng)
    last_day = max(0, int(cycle.get("npc_simulated_until_day", 0)))
    target_day = max(last_day, int(elapsed_days))
    for day in range(last_day + 1, target_day + 1):
        active_by_layer: dict[str, list[dict[str, Any]]] = {}
        for actor in cycle.get("roster", []):
            if actor.get("status") == "active":
                active_by_layer.setdefault(str(actor["layer_id"]), []).append(actor)
        for row in cycle.get("round_entries", []):
            if (
                row.get("resolution") != "unclaimed"
                or int(row.get("claim_at_day") or 10**9) > day
            ):
                continue
            candidates = active_by_layer.get(str(row.get("layer_id")), [])
            if candidates:
                deps._guixu_npc_claim_entry(
                    game, dungeon, cycle, row, rng.choice(candidates), "discovered",
                )
        deps._simulate_guixu_npc_conflict(game, dungeon, cycle, day, rng)
    cycle["npc_simulated_until_day"] = target_day


def _simulate_guixu_npc_conflict(
    deps: GuixuNpcsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    day: int, rng: random.Random,
) -> None:
    if rng.random() >= float(deps._guixu_settings().get("npc_conflict_chance_per_day", .22)):
        return
    roster = {str(actor["actor_id"]): actor for actor in cycle.get("roster", [])}
    held = [
        row for row in cycle.get("round_entries", [])
        if row.get("resolution") == "held"
        and (roster.get(str(row.get("holder_id"))) or {}).get("status") == "active"
    ]
    rng.shuffle(held)
    for treasure_row in held:
        defender = roster[str(treasure_row["holder_id"])]
        attackers = [
            actor for actor in cycle.get("roster", [])
            if actor.get("status") == "active"
            and actor.get("layer_id") == defender.get("layer_id")
            and actor.get("actor_id") != defender.get("actor_id")
            and not (
                actor.get("team_id")
                and actor.get("team_id") == defender.get("team_id")
            )
        ]
        if not attackers:
            continue
        attacker = rng.choice(attackers)
        attacker_power = max(1.0, float(attacker.get("power", 1)))
        defender_power = max(1.0, float(defender.get("power", 1)))
        attacker_wins = rng.random() < attacker_power / (attacker_power + defender_power)
        winner, loser = (attacker, defender) if attacker_wins else (defender, attacker)
        if rng.random() < float(deps._guixu_settings().get("npc_combat_kill_chance", .62)):
            deps._resolve_guixu_npc_kill(game, dungeon, cycle, winner, loser, day)
        return


def _resolve_guixu_npc_kill(
    deps: GuixuNpcsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    killer: dict[str, Any], victim: dict[str, Any], day: int,
) -> None:
    victim["status"] = "dead"
    victim_team = victim.get("team_id")
    if victim_team:
        deps._dissolve_guixu_npc_team(
            game, dungeon, cycle, str(victim_team), f"因{victim['name']}战死而崩解",
        )
    transferred = []
    killer_team = killer.get("team_id")
    for row in cycle.get("round_entries", []):
        if row.get("resolution") == "held" and row.get("holder_id") == victim.get("actor_id"):
            row["holder_id"] = killer["actor_id"]
            row["npc_claim_source"] = "npc_kill"
            transferred.append(
                deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))["name"]
            )
    if transferred and killer_team:
        deps._dissolve_guixu_npc_team(
            game, dungeon, cycle, str(killer_team),
            f"因{killer['name']}夺得{'、'.join(transferred)}而利益破裂",
        )
    if victim.get("npc_id"):
        npc = deps._find_npc(game, str(victim["npc_id"]))
        if npc:
            npc.alive = False
            npc.death_reason = f"在{dungeon['name']}被{killer['name']}击杀夺宝"
            game.player.party = [
                row for row in game.player.party if str(row.get("id")) != npc.id
            ]
            if game.player.dao_companion and game.player.dao_companion.get("id") == npc.id:
                game.player.dao_companion["alive"] = False
                game.player.dao_companion["death_reason"] = npc.death_reason
            for relation in [
                game.player.master, *game.player.dao_friends,
                *game.player.disciples, *game.player.concubines,
            ]:
                if relation and str(relation.get("id")) == npc.id:
                    relation["alive"] = False
                    relation["death_reason"] = npc.death_reason
    incident = {
        "day": day, "killer_id": killer["actor_id"], "killer_name": killer["name"],
        "victim_id": victim["actor_id"], "victim_name": victim["name"],
        "transferred": list(transferred),
    }
    cycle.setdefault("npc_incidents", []).append(incident)
    game.history.append(HistoryRecord(
        "SYS_GUIXU_NPC_KILL", 1, game.player.age, "归墟修士相残",
        str(victim["actor_id"]), "killed",
        f"{killer['name']}在{dungeon['name']}击杀{victim['name']}"
        + (f"，夺走{'、'.join(transferred)}。" if transferred else "。"),
        {"dungeon_id": dungeon["id"], **incident},
        ["system", "guixu", "npc", "combat", "death"],
    ))
