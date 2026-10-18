"""Load a current save, prepare its live session, then commit changes once.

Schema transformations happen in SaveStore before model construction. Preparation
is deliberately ordered: some stages settle state or consume RNG. It is not a
pure read and must run within the existing command/request lock.
"""
from __future__ import annotations
import copy
from ..models import GameState
from .dependencies import PersistenceDependencies, SessionPreparationDependencies
from .persistence import foundations, vitality, character, world, services, events, reconciliation


def prepare_session(deps: SessionPreparationDependencies, game: GameState) -> bool:
    """Prepare the caller's original working state; no loading or saving ports."""
    from ..system.spatial import SPECIAL_WORLDS, current
    if game.player.world in SPECIAL_WORLDS:
        if current(game) is None:
            raise ValueError('独立空间存档缺少当前实例')
        # Prepare personal state while keeping external calendars and markets out.
        changed = character.prepare_character(deps.character, game)
        changed = deps.world._sync_relationship_records(game) or changed
        changed = deps.world._ensure_sage_state(game) or changed
        before_sage_effects = game.player.sage_effects.copy()
        deps.world._refresh_sage_effects(game)
        changed = before_sage_effects != game.player.sage_effects or changed
        before_buddhist = copy.deepcopy(game.buddhist_state)
        deps.services._ensure_buddhist_state(game)
        changed = before_buddhist != game.buddhist_state or changed
        changed = deps.services._ensure_natal_artifact(game) or changed
        changed = vitality.prepare_vitality(deps.vitality, game) or changed
        changed = events.prepare_events(deps.events, game) or changed
    else:
        changed = foundations.prepare_foundations(deps.foundations, game)
        changed = vitality.prepare_vitality(deps.vitality, game) or changed
        changed = character.prepare_character(deps.character, game) or changed
        changed = world.prepare_world(deps.world, game) or changed
        changed = services.prepare_services(deps.services, game) or changed
        changed = events.prepare_events(deps.events, game) or changed
    changed = reconciliation.prepare_reconciliation(game) or changed
    return bool(changed)


def _load(deps: PersistenceDependencies, game_id: str) -> GameState:
    game = deps.store.load(game_id)
    changed = prepare_session(deps.preparation, game)
    if changed:
        deps.store.save(game)
    return game
