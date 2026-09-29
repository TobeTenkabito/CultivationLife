"""Lazy discovery of real peers. No complete NPC roster or annual simulation."""
from ...models import SectNpc
from ..combat.npc_lifecycle import initialize_native
from .generation import rng_for


def discover(game, key, definition, combat_config, words):
    record = game.doctrine_state["player"]
    known = record.setdefault("daomen", {}).setdefault(key, [])
    index = len(known)
    if index >= 9:
        raise ValueError("这处道门的九位传承引路人均已结识")
    level = index + 1
    npc_id = f"daomen:{key}:{index}"
    rng = rng_for(game.seed, game.doctrine_state["version"], npc_id)
    name = rng.choice(words["prefixes"]) + rng.choice(words["ability_verbs"]) + "道人"
    stage = definition["stages"][index]
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
