"""Original lazy NPC doctrine settlement, shared by combat and explicit training."""
from ..combat.npc_lifecycle import read
from .generation import rng_for
from .state import config


def record(game, npc):
    state = read(npc, "transcendence")
    if state is None or not game.doctrine_state:
        return None
    record = state.get("doctrine")
    from ..cultivation_ranks import npc_voisinage_limit, ensure_npc
    ensure_npc(npc)
    limit = npc_voisinage_limit(npc)
    world, now = read(npc, "world"), game.player.age
    if record is None:
        # Respect scripted grants; old unconverted actors retain their legacy path.
        if (world != "celestial" or read(npc, "realm_index", 0) < 9 or state.get("conversion", 0) <= 0
                or state.get("voisinage_ids", state.get("domain_ids"))):
            return None
        rng = rng_for(game.seed, game.doctrine_state["version"], f"npc:{read(npc, 'id')}")
        definitions = game.doctrine_state["definitions"]
        # Personal foreign inheritances extend the shared lookup catalog, not
        # the seeded native traditions available to an uninitialized NPC.
        native = [key for key in definitions if key.startswith('celestial:')]
        if not native:
            return None
        key = rng.choice(native)
        level = min(9, max(1, (read(npc, "realm_index") - 9) * 2 + rng.choice([1, 2, 3, 4, 4, 5])))
        level = min(level, max(s["level"] for s in definitions[key]["stages"] if s["realm"] <= read(npc, "realm_index")))
        level = min(level, limit)
        book = definitions[key]["manuals"][0]["id"]
        record = state["doctrine"] = {"manuals": [book], "manual_level": level, "annotations": list(range(1, level + 1)),
                                      "progress": {key: {"level": level, "experience": 0}},
                                      "active": key, "origin": key if level >= 5 else None,
                                      "at": now, "world": world}
    for progress in record.get("progress", {}).values():
        if progress.get("level", 0) > limit:
            progress.update(level=limit, experience=0)
    if "manual_level" not in record:
        mastered = record.get("progress", {}).get(record.get("active"), {}).get("level", 0)
        record.update(manual_level=mastered, annotations=list(range(1, mastered + 1)))
    if world == "celestial" and record.get("world") == world and read(npc, "alive", True) and not record.get("mentor"):
        key = record.get("active")
        if key in game.doctrine_state["definitions"]:
            progress = record["progress"][key]
            definition = game.doctrine_state["definitions"][key]
            elapsed = max(0, now - record.get("at", now))
            # Compile each stage's finite attempts from a stable stream. Settling
            # the same interval in one call or many yields identical progress.
            remaining = elapsed
            rules = config()["cultivation"]
            for _ in range(9):
                level = progress.get("level", 0)
                if level >= min(9, limit) or definition["stages"][level]["realm"] > read(npc, "realm_index"):
                    break
                rng = rng_for(game.seed, game.doctrine_state["version"], f"npc-study:{read(npc, 'id')}:{key}:{level + 1}")
                failures = 0
                while rng.random() >= min(1, rules["success_rates"][level] + failures * rules["pity_steps"][level]):
                    failures += 1
                required = definition["stages"][level]["years"] * (failures + 1) + 80 * (level + 1)
                used = min(remaining, max(0, required - progress.get("experience", 0)))
                progress["experience"] = progress.get("experience", 0) + used
                remaining -= used
                if progress["experience"] < required:
                    break
                level += 1
                progress.update(level=level, experience=0)
                progress.setdefault("failures", {})[str(level)] = failures
                record.update(manual_level=max(record.get("manual_level", 0), level), annotations=list(range(1, level + 1)))
                if level >= 5:
                    record["origin"] = key
                if remaining <= 0:
                    break
    record.update(at=now, world=world)
    # The doctrine record is evidence of an actually learned manual. Do not
    # populate the independent combat artifact slot from the treasure slot.
    from ..combat.npc_lifecycle import _write
    if not read(npc, 'main_technique_id') and record.get('manuals'):
        _write(npc, 'main_technique_id', record['manuals'][0])
    if read(npc, 'main_technique_id') in record.get('manuals', ()):
        _write(npc, 'main_technique_level', record.get('manual_level', 1))
        from ..npc_techniques import levels
        _write(npc, 'technique_levels', levels(npc))
    return record

