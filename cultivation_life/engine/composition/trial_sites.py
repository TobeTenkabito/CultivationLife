"""Late-bound, explicit trial-site ports, with the normal save transaction."""
from ...system.trial_sites import TrialDependencies
from ..transactions import accept_committed_game


def bind(engine):
    return TrialDependencies(
        load=lambda game_id: engine._load(game_id),
        save=lambda game: engine.store.save(game),
        present=lambda game: engine.present(game),
        commit=lambda game: accept_committed_game(engine, game),
        combat=lambda *args: engine._combat(*args),
        effect=lambda *args: engine._effect(*args),
        reward_pool=lambda *args: engine._trial_site_reward_pool(*args),
        maps=engine.maps,
    )
