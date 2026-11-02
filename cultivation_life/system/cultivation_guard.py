"""Shared read-only cultivation eligibility, independent from action facades."""
from .possession_system import is_possessed


def cultivation_blocked(game):
    p=game.player
    return bool(not p.alive or game.pending_event or game.active_trial or p.imprisonment
                or p.ghost_captor or is_possessed(p)
                or (game.guixu_state.get('player_session') or {}).get('trapped'))
