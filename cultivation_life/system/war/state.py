from __future__ import annotations
from typing import Any
from ...models import GameState
from ...content_registry import RACE_DEFINITIONS
from ...models import SectNpc
import copy
from ...world_state import race_pair
from ..faction_geography import war_site
from .dependencies import WarStateDependencies


def _war_player_identity(deps: WarStateDependencies, game, war):
    if war['kind'] == 'race':
        return deps._player_allegiance_race(game.player)
    if game.family and not game.family.extinct and deps._participant_side(war, game.family.id):
        return game.family.id
    return game.player.faction_id


def _war_relation(deps: WarStateDependencies, game: GameState, kind: str, first: str, second: str) -> dict[str, Any]:
    relations = game.race_relations if kind == "race" else game.sect_relations
    return relations.setdefault(race_pair(first, second), {
        "affinity": 0.0, "status": "neutral", "since_age": game.player.age,
    })


def _active_war(deps: WarStateDependencies, game: GameState, kind: str, first: str, second: str) -> dict[str, Any] | None:
    sides = {first, second}
    for war in game.wars:
        if war.get("status") not in {"active", "peace_ready"} or war.get("kind") != kind:
            continue
        deps._ensure_war_shape(game, war)
        participants = {row["id"] for side in ("attacker", "defender") for row in war["coalitions"][side]}
        if sides.issubset(participants):
            return war
    return None


def _war_world(deps: WarStateDependencies, game: GameState, kind: str, side_id: str) -> str:
    if kind == "sect" and deps._war_sect(game, side_id):
        return deps._war_sect(game, side_id).world
    worlds = list(RACE_DEFINITIONS.get(side_id, {}).get("worlds", []))
    if game.player.world in worlds:
        return game.player.world
    return next((world for world in worlds if world in {"spirit", "true_demon"}), game.player.world)


def _war_side_name(deps: WarStateDependencies, game: GameState, kind: str, side_id: str) -> str:
    if kind == "race":
        return str(RACE_DEFINITIONS.get(side_id, {}).get("name") or side_id or "未知势力")
    sect = deps._war_sect(game, side_id)
    return str(sect.name if sect and sect.name else side_id or "未知势力")


def _war_side_members(deps: WarStateDependencies, game: GameState, kind: str, side_id: str, world: str) -> list[SectNpc]:
    from ...person_assignments import research_assignment
    if kind == "sect":
        sect = deps._war_sect(game, side_id)
        people = deps._sect_members(game, sect) if sect and not sect.extinct else []
    else:
        people = [npc for npc in deps._all_world_npcs(game) if npc.race == side_id]
    # 战场只记录最强二十四人；这是可解释的参战名册，也是稳定的性能上限。
    unique = {
        npc.id: npc for npc in people
        if npc.alive and npc.world == world and not deps._intrigue_is_imprisoned(game, npc.id)
        and not research_assignment(game, npc.id)
    }
    return sorted(unique.values(), key=deps._npc_power, reverse=True)[:int(deps._war_rules().get("roster_cap", 24))]


def _ensure_war_shape(deps: WarStateDependencies, game: GameState, war: dict[str, Any]) -> bool:
    """Lazily migrate pre-coalition wars without invalidating existing saves."""
    changed = False
    if war.get("kind") == "sect" and war.get("world") in deps.maps.worlds:
        before = war.get("location_id")
        war_site(deps.maps, war)
        changed = before != war.get("location_id")
    raw_coalitions = war.get("coalitions") if isinstance(war.get("coalitions"), dict) else {}
    coalitions: dict[str, list[dict[str, Any]]] = {}
    for side in ("attacker", "defender"):
        leader = str(war.get(f"{side}_id", ""))
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        raw_rows = raw_coalitions.get(side, []) if isinstance(raw_coalitions.get(side, []), list) else []
        for raw in raw_rows:
            row = {"id": raw} if isinstance(raw, str) else dict(raw) if isinstance(raw, dict) else {}
            power_id = str(row.get("id") or "")
            if not power_id or power_id in seen:
                changed = True
                continue
            seen.add(power_id)
            normalized.append({
                "id": power_id, "role": "leader" if power_id == leader else "ally",
                "joined_unit": int(row.get("joined_unit", war.get("start_unit", 0))),
                "called_by": row.get("called_by"),
            })
        if leader and leader not in seen:
            normalized.insert(0, {"id": leader, "role": "leader", "joined_unit": int(war.get("start_unit", 0)), "called_by": None})
            changed = True
        normalized.sort(key=lambda row: (row["role"] != "leader", row["joined_unit"], row["id"]))
        coalitions[side] = normalized
    if coalitions != raw_coalitions:
        war["coalitions"] = coalitions
        changed = True
    if not isinstance(war.get("roster_owner"), dict):
        war["roster_owner"] = {}
        changed = True
    roster_owner = war["roster_owner"]
    for side in ("attacker", "defender"):
        leader = war.get(f"{side}_id", "")
        for npc_id in war.get("roster", {}).get(side, []):
            if npc_id not in roster_owner:
                roster_owner[npc_id] = leader
                changed = True
    for key, default, expected_type in (
        ("called_allies", {}, dict), ("call_log", [], list), ("peace_offer", None, (dict, type(None))),
    ):
        if key not in war or not isinstance(war.get(key), expected_type):
            war[key] = copy.deepcopy(default)
            changed = True
    return changed


def _coalition_ids(deps: WarStateDependencies, war: dict[str, Any], side: str) -> list[str]:
    return [str(row.get("id", "")) for row in war.get("coalitions", {}).get(side, []) if row.get("id")]


def _participant_side(deps: WarStateDependencies, war: dict[str, Any], power_id: str | None) -> str | None:
    if not power_id:
        return None
    for side in ("attacker", "defender"):
        if power_id in deps._coalition_ids(war, side):
            return side
    return None


def _power_exists_in_world(deps: WarStateDependencies, game: GameState, kind: str, power_id: str, world: str) -> bool:
    if kind == "sect":
        sect = deps._war_sect(game, power_id)
        return bool(sect and not sect.extinct and sect.world == world)
    return world in RACE_DEFINITIONS.get(power_id, {}).get("worlds", [])


def _append_war_log(deps: WarStateDependencies, game: GameState, war: dict[str, Any], title: str, text: str) -> None:
    war.setdefault("logs", []).append({"unit": game.diplomacy_unit, "age": game.player.age, "title": title, "text": text})
    # 单场战争仅保留最近八十条，避免长期战争令存档和渲染无限膨胀。
    war["logs"] = war["logs"][-80:]


def _war_npc(deps: WarStateDependencies, game: GameState, npc_id: str) -> SectNpc | None:
    return deps._find_npc(game, npc_id)


def _available_warriors(deps: WarStateDependencies, game: GameState, war: dict[str, Any], side: str, power_id: str = "") -> list[SectNpc]:
    deps._ensure_war_shape(game, war)
    escaped = set(war.get("escaped", {}).get(side, [])) | set(war.get("voisinage_suppressed", []))
    return [npc for npc_id in war.get("roster", {}).get(side, [])
            if npc_id not in escaped and (not power_id or war["roster_owner"].get(npc_id) == power_id)
            and (npc := deps._war_npc(game, npc_id)) and npc.alive
            and not deps._intrigue_is_imprisoned(game, npc.id)]


def _ensure_wars(deps: WarStateDependencies, game: GameState) -> bool:
    """Upgrade old saves whose diplomatic relation was already marked as war."""
    before = len(game.wars)
    changed = False
    for war in game.wars:
        changed = deps._ensure_war_shape(game, war) or changed
    for kind, relations in (("race", game.race_relations), ("sect", game.sect_relations)):
        for key, relation in relations.items():
            if relation.get("status") != "war":
                continue
            first, second = key.split("|") if "|" in key else key.split(":")
            if not deps._active_war(game, kind, first, second):
                deps._start_war(game, kind, first, second)
    return changed or len(game.wars) != before
