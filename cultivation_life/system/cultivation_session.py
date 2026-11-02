"""Explicit operations for cultivation session."""

from __future__ import annotations

from ..models import HistoryRecord
from ..runtime import now_iso
from .cultivation_dependencies import (
    CultivationCommitDependencies,
    CultivationSessionDependencies,
)
from .doctrine.provider import ensure
from .possession_system import is_possessed
from .cultivation_guard import cultivation_blocked


def _cultivation_game(deps: CultivationSessionDependencies, game_id):
    game = deps._load(game_id)
    p = game.player
    if p.world != "celestial" or p.realm_index < 9:
        raise ValueError("须在仙界达到真仙境界")
    if is_possessed(p):
        raise ValueError('寄身期间本魂仙道修持冻结，请先离舍')
    if cultivation_blocked(game):
        raise ValueError("当前状态无法修持，请先处理事件或脱离拘束")
    ensure(game)
    return game


def _save_cultivation(deps: CultivationCommitDependencies, game, summary):
    game.history.append(HistoryRecord("SYS_IMMORTAL_CULTIVATION", 1, game.player.age,
                                     "仙道修持", None, "completed", summary, {}, ["system", "cultivation"]))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
