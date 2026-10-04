"""Load a current save, prepare its live session, then commit changes once.

Schema transformations happen in SaveStore before model construction. Preparation
is deliberately ordered: some stages settle state or consume RNG. It is not a
pure read and must run within the existing command/request lock.
"""
from __future__ import annotations
from ..models import GameState
from .dependencies import PersistenceDependencies
from .persistence import foundations, vitality, character, world, services, events


def _load(deps: PersistenceDependencies, game_id: str) -> GameState:
    game = deps.store.load(game_id)
    from ..system.spatial import SPECIAL_WORLDS, current
    if game.player.world in SPECIAL_WORLDS:
        if current(game) is None:
            raise ValueError('独立空间存档缺少当前实例')
        # Ordinary preparation can dispatch outside markets, contact updates and
        # events. A fully persisted spatial session has its own annual boundary.
        return game
    changed = foundations.prepare_foundations(deps.foundations, game)
    changed = vitality.prepare_vitality(deps.vitality, game) or changed
    changed = character.prepare_character(deps.character, game) or changed
    changed = world.prepare_world(deps.world, game) or changed
    changed = services.prepare_services(deps.services, game) or changed
    changed = events.prepare_events(deps.events, game) or changed
    if changed:
        deps.store.save(game)
    return game
