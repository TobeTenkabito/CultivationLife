"""Explicit demonic refinement operations; callers own composition."""
from __future__ import annotations

from typing import Any

from ...models import HistoryRecord
from ...runtime import decode_rng, encode_rng, now_iso
from ..possession_system import advance_player_age
from .dependencies import DemonicRefinementDependencies


def secluded_refine_foreign_souls(deps: DemonicRefinementDependencies, game_id: str) -> dict[str, Any]:
    """以正常炼魂效率的 1/1.2 逐年闭关，免除主动炼化的机缘与 MP 消耗。"""
    game = deps._load(game_id)
    player = game.player
    if player.path != "demonic":
        raise ValueError("只有魔修能够闭关炼化外来元神")
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if player.imprisonment:
        raise ValueError("身陷大牢时无法闭关炼魂")
    souls = [entry for entry in player.foreign_souls if not entry.get("refined")]
    if not souls:
        raise ValueError("当前没有尚未炼化的外来元神")

    planned_years = deps._secluded_refining_years(player)
    time_multiplier = float(deps._demonic_rules().get("soul_seclusion_time_multiplier", 1.2))
    yearly_progress = deps._soul_refine_gain(player) / max(1.0, time_multiplier)
    rng = decode_rng(game.seed, game.rng_state)
    start_age = player.age
    era_news: list[str] = []
    completed_count = 0
    for _ in range(planned_years):
        advance_player_age(player)
        if not deps._advance_world_year(game, rng, era_news, encounters=False):
            break
        budget = yearly_progress
        for soul in souls:
            if soul.get("refined") or budget <= 0:
                continue
            remaining = max(0.0, float(soul["required"]) - float(soul.get("progress", 0)))
            applied = min(remaining, budget)
            soul["progress"] = float(soul.get("progress", 0)) + applied
            soul["last_refine_age"] = player.age
            budget -= applied
            if soul["progress"] >= float(soul["required"]):
                deps._complete_soul_refinement(player, soul)
                completed_count += 1
        if all(entry.get("refined") for entry in souls):
            break

    elapsed_years = player.age - start_age
    fully_completed = all(entry.get("refined") for entry in souls)
    result = "completed" if fully_completed else "dead" if not player.alive else "interrupted"
    summary = (
        f"你闭关 {elapsed_years} 年，将 {completed_count} 道外来元神尽数炼化；全程未消耗机缘与 MP，"
        f"耗时按正常炼化的 {time_multiplier:.0%} 计算。"
        if fully_completed else
        f"闭关炼魂在第 {elapsed_years} 年中断，已炼化 {completed_count}/{len(souls)} 道元神；期间未消耗机缘与 MP。"
    )
    game.history.append(HistoryRecord(
        "SYS_SOUL_SECLUDED_REFINING", 1, player.age, "闭关炼化", None, result, summary,
        {"age":[start_age, player.age], "souls_refined":completed_count, "souls_total":len(souls)},
        ["system", "demonic", "soul", "seclusion"],
    ))
    if elapsed_years >= 5:
        deps._record_era_summary(game, start_age, era_news)
    deps._ensure_market(game, rng)
    deps._compact_world_history(game)
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)
