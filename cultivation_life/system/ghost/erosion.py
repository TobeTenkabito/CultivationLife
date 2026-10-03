"""Explicit ghost erosion operations; callers own composition."""
from __future__ import annotations

from typing import Any

from ...models import GameState, HistoryRecord
from ...runtime import now_iso
from ..ghost_resources import ghost_cultivation_config as ghost_cultivation_config
from .dependencies import GhostErosionDependencies
from .progression import (
    accumulate_soul_erosion_time,
    apply_soul_erosion,
    spend_wangsheng_energy,
)


def _advance_soul_erosion_time(deps: GhostErosionDependencies, game: GameState, elapsed_years: int = 1) -> bool:
    completed_units = accumulate_soul_erosion_time(game.player, elapsed_years)
    return not completed_units or deps._apply_soul_erosion_units(game, completed_units)


def _apply_soul_erosion_units(deps: GhostErosionDependencies, game: GameState, units: int = 1) -> bool:
    from ...rules import max_hp, max_mp

    result = apply_soul_erosion(game.player, units)
    if not result["active"]:
        return True
    game.player.hp = min(game.player.hp, max_hp(game.player))
    game.player.mp = min(game.player.mp, max_mp(game.player))
    for threshold in result["thresholds"]:
        game.history.append(HistoryRecord(
            f"SYS_GHOST_EROSION_{threshold}", 1, game.player.age, "魂灯渐暗", None, "eroded",
            f"漫长岁月已经永久磨损魂魄本源，本体承载率首次跌破 {threshold}%。",
            {"carry_threshold": threshold, "erosion_rate_pp": game.player.ghost_soul_erosion_rate_pp},
            ["system", "ghost", "soul_erosion", "negative", "milestone"],
        ))
    if result["dead"]:
        deps._die(game, "魂蚀已将本体魂基磨灭，纵有外物亦无法阻止魂飞魄散", "SYS_GHOST_SOUL_DISPERSAL")
        return False
    return True


def spend_wangsheng(deps: GhostErosionDependencies, game_id: str, spend_all: bool = False) -> dict[str, Any]:
    game = deps._load(game_id)
    if not game.player.alive or game.pending_event or game.player.imprisonment:
        raise ValueError("当前状态无法行往生法")
    unit_cost = max(1, int(ghost_cultivation_config().get("wangsheng_cost", 2)))
    uses = max(1, game.player.ghost_wangsheng_energy // unit_cost) if spend_all else 1
    cost, reduction = spend_wangsheng_energy(game.player, uses)
    game.player.milestones["ghost_wangsheng_spent"] = (
        int(game.player.milestones.get("ghost_wangsheng_spent", 0)) + cost
    )
    game.history.append(HistoryRecord(
        "SYS_GHOST_WANGSHENG", 1, game.player.age, "往生息蚀", None, "spent",
        f"你施行 {uses} 次往生，消耗 {cost} 点往生，将魂蚀率降低 {reduction:.4f} 个百分点；既有魂伤并未复原。",
        {"cost": cost, "uses": uses, "erosion_reduction_pp": reduction},
        ["system", "ghost", "wangsheng"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
