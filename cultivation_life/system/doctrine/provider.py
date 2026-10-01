"""Save-state adapter for celestial doctrine sources, shared by both battle callers."""
from __future__ import annotations

from ...content_registry import CONTENT_DOCUMENTS
from ..combat.contracts import CapabilitySource
from ..combat.npc_lifecycle import read
from .generation import generate, rng_for
from .progression import source


def config():
    return CONTENT_DOCUMENTS.get("doctrines.json", {})


def ensure(game, *, celestial_context=False) -> bool:
    if not config():
        return False
    changed = False
    if not game.doctrine_state:
        if game.player.world != "celestial" and not celestial_context:
            return False
        from ...rules import expected_combat_power
        game.doctrine_state = generate(game.seed, config(), {r: expected_combat_power(r, 1) for r in range(9, 13)})
        changed = True
    if game.doctrine_state.get("cultivation_schema") != 2:
        record = game.doctrine_state["player"]
        record.setdefault("annotations", {})
        record.setdefault("daomen", {})
        record.setdefault("voisinage_training", {})
        for key, progress in record["progress"].items():
            level = progress["level"]
            record["annotations"][key] = list(range(1, level + 1))
            books = [t for t in game.player.known_techniques if t.doctrine_id == key]
            if books:
                best = max(books, key=lambda t: t.level)
                best.level = max(best.level, level)
                for equipped in [game.player.technique, game.player.support_technique, *game.player.combat_techniques]:
                    if equipped and equipped.id == best.id:
                        equipped.level = max(equipped.level, best.level)
        game.doctrine_state["cultivation_schema"] = 2
        changed = True
    if game.doctrine_state.get('effects_schema') != 1:
        from .effects import enrich_effects
        enrich_effects(game.doctrine_state['definitions'])
        game.doctrine_state['effects_schema'] = 1
        changed = True
    if game.doctrine_state.get('offensive_schema') != 1:
        from .effects import ensure_offensive_doctrine
        ensure_offensive_doctrine(game.doctrine_state['definitions'], game.seed, game.doctrine_state['version'])
        game.doctrine_state['offensive_schema'] = 1
        changed = True
    return changed


def player_record(game):
    ensure(game)
    return game.doctrine_state.get("player", {})


def _npc_record(game, npc):
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
        key = rng.choice(list(definitions))
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
    return record


def battle_sources(game, owners) -> dict[str, CapabilitySource]:
    # Do not generate a celestial catalog for unrelated lower-world battles.
    ensure(game, celestial_context=any(read(owner, "world") == "celestial" and read(owner, "transcendence") for owner in owners.values()))
    from ..spirit_voisinage import player_source, npc_source, diminished
    from ..immortal_aperture import lower_world
    definitions = game.doctrine_state.get("definitions", {})
    results = {}
    for key, owner in owners.items():
        if key == 'player':
            from ..upper_voisinage import available, player_source as upper_source
            if available(game.player):
                results[key] = upper_source(game.player)
                continue
        if key == 'player' and lower_world(game.player):
            value = player_source(game)
            if value.voisinages:
                results[key] = value
            continue
        if key != 'player' and lower_world(game.player):
            spirit = npc_source(game, owner)
            if spirit.voisinages:
                results[key] = spirit
                continue
        record = player_record(game) if key == "player" else _npc_record(game, owner)
        if record:
            domain_world = 'celestial' if lower_world(game.player) else read(owner, 'world')
            value = source(record, definitions, domain_world, training_gain=config()["cultivation"]["voisinage_training_gain"])
            if lower_world(game.player):
                value = diminished(value)
            if value.voisinages:
                results[key] = value
    from ..combat_loadout import project_loadout
    from ..tianji_system import tianji_content_available
    held = {}
    if tianji_content_available():
        definitions_by_id = {d['id']: d for d in game.tianji_state.get('artifacts', ())}
        for artifact_id, holder in game.tianji_state.get('holders', {}).items():
            npc_id = holder.get('npc_id')
            if npc_id and artifact_id in definitions_by_id:
                held.setdefault(npc_id, []).append(definitions_by_id[artifact_id])
    for key, owner in owners.items():
        value = project_loadout(game, owner, results.get(key), player=key == 'player', tianji_artifacts=held.get(read(owner, 'id'), ()))
        if (value.voisinages or value.technique_tier > 1 or value.artifact_tier > 1
                or value.passive_ward_tier == 2 or value.interventions):
            results[key] = value
    return results


def conversion_state(player):
    from ..immortal_aperture import energy_state
    return energy_state(player)
