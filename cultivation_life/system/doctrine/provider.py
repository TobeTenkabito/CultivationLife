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
    return changed


def player_record(game):
    ensure(game)
    return game.doctrine_state.get("player", {})


def _npc_record(game, npc):
    state = read(npc, "transcendence")
    if state is None or not game.doctrine_state:
        return None
    record = state.get("doctrine")
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
        book = definitions[key]["manuals"][0]["id"]
        record = state["doctrine"] = {"manuals": [book], "manual_level": level, "annotations": list(range(1, level + 1)),
                                      "progress": {key: {"level": level, "experience": 0}},
                                      "active": key, "origin": key if level >= 5 else None,
                                      "at": now, "world": world}
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
                if level >= 9 or definition["stages"][level]["realm"] > read(npc, "realm_index"):
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
    return record


def battle_sources(game, owners) -> dict[str, CapabilitySource]:
    # Do not generate a celestial catalog for unrelated lower-world battles.
    ensure(game, celestial_context=any(read(owner, "world") == "celestial" and read(owner, "transcendence") for owner in owners.values()))
    if not game.doctrine_state:
        return {}
    definitions = game.doctrine_state["definitions"]
    results = {}
    for key, owner in owners.items():
        record = player_record(game) if key == "player" else _npc_record(game, owner)
        if record:
            value = source(record, definitions, read(owner, "world"), training_gain=config()["cultivation"]["voisinage_training_gain"])
            if value.voisinages:
                results[key] = value
    return results


def conversion_state(player):
    """Existing MP is the sole pool; partial conversion controls usable capacity."""
    if player.world != "celestial" or player.realm_index < 9:
        return None
    from ..immortal_cultivation import golden_light
    ratio = 1.0 if player.immortal_power_converted else max(0, min(5, player.immortal_conversion_stage)) / 5
    return dict(version=1, resource_link="legacy_mp", conversion=ratio,
                force_tier=2 if ratio else 1, ward_tier=2 if golden_light(player) and ratio else 1,
                attack_cost=10, ward_cost=100)
