"""Doctrine catalog initialization and save migration, independent of battle sources."""
from __future__ import annotations

from ...content_registry import CONTENT_DOCUMENTS
from .generation import generate


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
