"""Lazy discovery of real peers. No complete NPC roster or annual simulation."""
from ...models import SectNpc
from ..combat.npc_lifecycle import initialize_native
from .generation import rng_for


def preview(game, key, definition, words):
    record = game.doctrine_state["player"]
    serial = record.get("peer_search_serial", 0) + 1
    record["peer_search_serial"] = serial
    rng = rng_for(game.seed, game.doctrine_state["version"], f"peer-preview:{key}:{serial}")
    level = rng.randint(1, 9)
    candidate = dict(id=f"daomen:{key}:visitor:{serial}", level=level,
                     name=rng.choice(words["prefixes"]) + rng.choice(words["ability_verbs"]) + "道人")
    record["peer_preview"] = dict(candidate, doctrine_id=key)
    return candidate


def discover(game, key, definition, combat_config, words, candidate=None):
    record = game.doctrine_state["player"]
    known = record.setdefault("daomen", {}).setdefault(key, [])
    index = len(known)
    if index >= 9:
        raise ValueError("这处道门的九位传承引路人均已结识")
    level = candidate["level"] if candidate else index + 1
    npc_id = candidate["id"] if candidate else f"daomen:{key}:{index}"
    rng = rng_for(game.seed, game.doctrine_state["version"], npc_id)
    name = rng.choice(words["prefixes"]) + rng.choice(words["ability_verbs"]) + "道人"
    if candidate:
        name = candidate["name"]
    stage = definition["stages"][level - 1]
    npc = game.notable_npcs.get(npc_id)
    if npc is None:
        realm = max(stage['realm'], 10 if level >= 4 else 9)
        npc = SectNpc(npc_id, name, "", realm, 1, 10000 + level * 1000, None, world="celestial")
        initialize_native(npc, combat_config, now=game.player.age)
        # They actually possess the manual/commentary mastery they can teach.
        npc.transcendence["doctrine"] = {
            "manuals": [definition["manuals"][0]["id"]], "manual_level": level,
            "annotations": list(range(1, level + 1)),
            "progress": {key: {"level": level, "experience": 0}},
            "active": key, "origin": key if level >= 5 else None,
            "at": game.player.age, "world": "celestial", "mentor": True,
        }
        game.notable_npcs[npc_id] = npc
    known.append(npc_id)
    return npc


def mentor(game, key, npc_id):
    if npc_id not in game.doctrine_state["player"].get("daomen", {}).get(key, []):
        raise ValueError("尚未结识这位同道")
    npc = game.notable_npcs.get(npc_id)
    if not npc or not npc.alive or npc.world != "celestial":
        raise ValueError("这位同道当前无法传授注解")
    return npc


def public_peers(game, key):
    rows = []
    for npc_id in game.doctrine_state["player"].get("daomen", {}).get(key, []):
        npc = game.notable_npcs.get(npc_id)
        if npc:
            level = npc.transcendence.get("doctrine", {}).get("progress", {}).get(key, {}).get("level", 0)
            rows.append({"id": npc_id, "name": npc.name, "level": level,
                         "available": npc.alive and npc.world == "celestial"})
    return rows
