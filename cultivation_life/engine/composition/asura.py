"""Wire Asura actions and trials without exposing the engine to their algorithms."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..dependencies import AsuraActionDependencies, AsuraTrialDependencies
from ..progression import asura_trials

if TYPE_CHECKING:
    from .. import GameEngine


def bind_asura_trials(engine: GameEngine) -> AsuraTrialDependencies:
    return AsuraTrialDependencies(
        _get_events_by_id=lambda: engine.events_by_id,
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        _complete_major_breakthrough=lambda *args, **kwargs: engine._complete_major_breakthrough(*args, **kwargs),
    )


def bind_asura_actions(engine: GameEngine) -> AsuraActionDependencies:
    return AsuraActionDependencies(
        _load=lambda game_id: engine._load(game_id),
        present=lambda game: engine.present(game),
        _asura_cultivate=lambda *args, **kwargs: engine._asura_cultivate(*args, **kwargs),
        _spend_asura_souls=lambda state, cost: engine._spend_asura_souls(state, cost),
        queue_trial=lambda game: asura_trials.queue(bind_asura_trials(engine), game),
        start_trial=lambda *args, **kwargs: asura_trials.start(bind_asura_trials(engine), *args, **kwargs),
        _get_store=lambda: engine.store,
    )
