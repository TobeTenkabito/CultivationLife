"""Run against an archived release or current tree; compare business RNG footprints."""
import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.runtime import decode_rng


def snapshot(game, rng):
    player = game.player
    return {"rng": hashlib.sha256(repr(rng.getstate()).encode()).hexdigest(),
            "world": player.world, "realm": [player.realm_index, player.layer],
            "hp": player.hp, "mp": player.mp,
            "market": [(row.get("content_id"), row.get("price")) for row in game.market_offers],
            "friends": [(row["id"], row.get("world"), row.get("alive", True)) for row in player.dao_friends],
            "history": [row.event_id for row in game.history]}


with tempfile.TemporaryDirectory() as folder:
    engine = GameEngine(ROOT, Path(folder) / "saves")
    results = {}
    for case in ("spirit", "celestial", "asura", "demon", "true_demon"):
        gid = engine.create_game("RNG probe", "supreme_metal", "dao", 7190)["id"]
        game = engine.store.load(gid)
        player = game.player
        player.world = {"spirit": "human", "celestial": "spirit", "asura": "true_demon", "demon": "human", "true_demon": "demon"}[case]
        player.location_id = engine.maps.default_location(player.world)
        player.realm_index, player.layer = (8, 9) if case in {"celestial", "asura"} else (5, 3)
        player.hp, player.mp = max_hp(player), max_mp(player)
        player.qi_experience["demon"] = 10**12
        player.heart_demon = 0
        player.path = "demonic" if case in {"demon", "true_demon", "asura"} else "dao"
        rng = random.Random(7531)
        if case == "spirit":
            player.dao_friends = [{"id":"probe-friend", "name":"随行道友", "realm_index":5, "layer":1, "alive":True, "world":"human"}]
            player.joint_friend_crossing = [{"id":"probe-friend", "name":"随行道友"}]
            engine._effect({"type":"enter_spirit_realm"}, game, {"id":"PROBE"}, rng)
            engine._ensure_market(game, rng)
        elif case in {"celestial", "asura"}:
            game.active_trial = {"kind": f"{case}_ascension", "step_index":8, "event_ids":["unused"]*9}
            getattr(engine, f"_resolve_{case}_ascension_step")(game, "ascension_heart" if case == "celestial" else "asura_heart", rng)
            engine._ensure_market(game, rng)
        else:
            engine.store.save(game)
            engine._complete_demonic_ascension(game)
            game = engine.store.load(gid)
            rng = decode_rng(game.seed, game.rng_state)
        results[case] = snapshot(game, rng)
    for source, destination in [("spirit","human"),("true_demon","demon"),("celestial","spirit"),("asura","true_demon"),("nether","phantom_underworld"),("nether","monster_realm"),("hell","human")]:
        gid = engine.create_game("Return probe", "supreme_metal", "dao", 7290)["id"]
        game = engine.store.load(gid)
        player = game.player
        player.world, player.location_id = source, engine.maps.default_location(source)
        player.realm_index, player.layer = (9,1) if source in {"celestial","asura","nether"} else (8,9)
        player.immortal_power_converted = True
        player.hp, player.mp = max_hp(player)*.6, max_mp(player)*.4
        engine.store.save(game)
        engine.cross_world(gid, destination)
        engine.cross_world(gid, source)
        game = engine.store.load(gid)
        results[f"{source}:{destination}:roundtrip"] = snapshot(game, decode_rng(game.seed, game.rng_state))
Path(sys.argv[2]).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Captured {len(results)} transition RNG scenarios")
