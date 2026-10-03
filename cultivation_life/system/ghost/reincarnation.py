"""Explicit ghost reincarnation operations; callers own composition."""
from __future__ import annotations

import random
from typing import Any

from ...content_registry import REALMS
from ...models import GameState, HistoryRecord
from ...runtime import now_iso
from ..ghost_resources import GHOST_DLC_NAME as GHOST_DLC_NAME
from ..ghost_resources import ghost_cultivation_active as ghost_cultivation_active
from ..ghost_resources import ghost_cultivation_config as ghost_cultivation_config
from .dependencies import GhostReincarnationDependencies
from .progression import can_reincarnate, perform_reincarnation


def prepare_ghost_reincarnation(deps: GhostReincarnationDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not ghost_cultivation_active(player):
        raise ValueError(f"未启用【{GHOST_DLC_NAME}】或当前并非鬼修")
    if not player.alive or game.pending_event or game.active_trial or player.imprisonment or player.sealed_cultivation:
        raise ValueError("当前状态无法进入轮回")
    if not can_reincarnate(player):
        raise ValueError("只有抵达大境界最终瓶颈并将机缘修至圆满，方可入轮回")
    template = deps.events_by_id.get("SYS_GHOST_REINCARNATION")
    if template is None:
        raise ValueError("轮回事件内容未加载")
    event = deps._instantiate_event(
        template, game, random.Random(f"ghost-reincarnation:{game.seed}:{player.age}"),
    )
    source_count = int(player.ghost_reincarnation_imprints.get(str(player.realm_index), 0))
    highwater = (
        f"{REALMS[int(player.ghost_intrinsic_highwater_realm)].name}"
        f"{int(player.ghost_intrinsic_highwater_layer or 1)}层"
    )
    bonus = float(ghost_cultivation_config().get("reincarnation_bonus_per_mark", 0.05))
    event["body"] = (
        f"轮回门在你识海深处开启。继续后，你将舍去"
        f"{REALMS[player.realm_index].name}{player.layer}层修为并回到{REALMS[1].name}1层，"
        f"留下本境第 {source_count + 1} 枚轮回印记，使本境及以下道路的突破经验增加 {bonus:.0%}。\n\n"
        f"未用往生 {player.ghost_wangsheng_energy} 点将归零；魂蚀率保持 "
        f"{player.ghost_soul_erosion_rate_pp:.4f}%，既有魂伤不会恢复；"
        f"神识等级与已有神识经验将重置为初始的 1 级、0 经验；"
        f"本体成长最高水位仍为{highwater}，重新超过此前修为前不会再次获得境界来源的本源成长。"
        f"所有突破的最终有效概率仍封顶 98%。"
    )
    game.pending_event = event
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _complete_ghost_reincarnation(
    game: GameState, *, record_history: bool,
) -> dict[str, Any]:
    from ...rules import max_hp, max_mp

    player = game.player
    transition = perform_reincarnation(player)
    source_realm = int(transition["source_realm"])
    source_layer = int(transition["source_layer"])
    source_label = str(transition["source_label"])
    key = str(source_realm)
    lost_wangsheng = int(transition["wangsheng_lost"])
    player.hp = min(player.hp, max_hp(player))
    player.mp = min(player.mp, max_mp(player))
    wangsheng_summary = (
        f"未用往生 {lost_wangsheng} 点尽数散失"
        if lost_wangsheng else "未用往生依当前规则没有损失"
    )
    summary = (
        f"你舍去{source_label}修为，重归练气一层；留下第 {transition['imprint_count']} "
        f"道本境轮回印记，{wangsheng_summary}。神识重归 1 级且经验清零；魂蚀与既有魂伤均未复原。"
    )
    transition["summary"] = summary
    if record_history:
        game.history.append(HistoryRecord(
            "SYS_GHOST_REINCARNATION", 2, player.age, "舍世入轮回", key, "reincarnated",
            summary,
            {
                "source_realm": source_realm, "source_layer": source_layer,
                "imprints": dict(player.ghost_reincarnation_imprints), "wangsheng_lost": lost_wangsheng,
            },
            ["system", "ghost", "reincarnation", "milestone"],
        ))
    return transition


def reincarnate_ghost(deps: GhostReincarnationDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not ghost_cultivation_active(player):
        raise ValueError(f"未启用【{GHOST_DLC_NAME}】或当前并非鬼修")
    if not player.alive or game.pending_event or game.active_trial or player.imprisonment or player.sealed_cultivation:
        raise ValueError("当前状态无法进入轮回")
    deps._complete_ghost_reincarnation(game, record_history=True)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
