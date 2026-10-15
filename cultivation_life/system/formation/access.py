"""Shared, read-only actor boundary for formation writes."""


def operation_available(game):
    player = game.player
    return not (not player.alive or game.pending_event or game.active_trial or player.imprisonment
                or player.ghost_captor or game.guixu_state.get('player_session'))


def require_access(game):
    if not operation_available(game):
        raise ValueError('当前状态无法操持阵法，请先处理事件或脱离拘束')
