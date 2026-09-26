from __future__ import annotations

from typing import Any
from ...content_registry import FACTION_SYSTEMS
from ...models import GameState, HistoryRecord
from ...runtime import decode_rng, encode_rng, now_iso
from ..dependencies import ChoiceDependencies


def choose(deps: ChoiceDependencies, game_id: str, choice_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    if not game.player.alive:
        raise ValueError("此生已经结束")
    pending = game.pending_event
    if not pending:
        raise ValueError("当前没有待处理事件")
    followup_event = pending.get("_followup_event")
    event = deps.events_by_id[pending["id"]]
    tags = event.get("tags", [])
    history_tags = pending.get("_history_tags", tags)
    shareholder_option = (
        game.player.realm_index >= 4 and "faction" in tags and "duty" in tags and "war" not in tags
    )
    synthetic_choices = {
        "__delegate_faction_task": {
            "id": "__delegate_faction_task",
            "effects": [{"type": "add_faction_contribution", "value": -int(FACTION_SYSTEMS["shareholder_delegate_cost"])}],
        },
        "__decline_faction_task": {
            "id": "__decline_faction_task",
            "effects": [{"type": "add_faction_contribution", "value": -int(FACTION_SYSTEMS["shareholder_decline_cost"])}],
        },
    }
    choice = synthetic_choices.get(choice_id) if shareholder_option else None
    choice = choice or next((entry for entry in event["choices"] if entry["id"] == choice_id), None)
    if choice is None:
        raise ValueError("事件选项不存在")
    if choice.get("conditions") and not deps._condition(choice["conditions"], game):
        raise ValueError(choice.get("disabled_reason", "当前条件不满足"))

    rng = decode_rng(game.seed, game.rng_state)
    pending["_choice_id"] = choice_id
    before = deps._snapshot(game.player)
    summaries: list[str] = []
    result = "resolved"
    # 先摘下旧事件，使通用 queue_event 效果可以安全接续剧情链。
    game.pending_event = None
    for effect in choice.get("effects", []):
        required_result = effect.get("if_result")
        if required_result and result not in required_result:
            continue
        outcome, text = deps._effect(effect, game, pending, rng)
        summaries.append(text)
        if outcome:
            result = outcome
        if not game.player.alive:
            break
    after = deps._snapshot(game.player)
    game.history.append(HistoryRecord(
        event["id"], event.get("version", 1), game.player.age, event["title"], choice_id, result,
        " ".join(filter(None, summaries)) or choice.get("result_text", "你做出了选择。"),
        deps._diff(before, after), history_tags,
    ))
    deps._resolve_breakthroughs(game, rng)
    deps._enforce_guixu_rank_boundary(game, "breakthrough")
    deps._ensure_market(game, rng)
    if game.pending_event is None:
        deps._maybe_artifact_synthesis(game, rng)
    if followup_event and game.player.alive:
        deps._queue_followup_event(game, followup_event)
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _queue_followup_event(game: GameState, event: dict[str, Any]) -> None:
    """将必得奖励接到当前事件链末端，避免被渡劫或剧情事件覆盖。"""
    if game.pending_event is None:
        game.pending_event = event
        return
    tail = game.pending_event
    while tail.get("_followup_event"):
        tail = tail["_followup_event"]
    tail["_followup_event"] = event
