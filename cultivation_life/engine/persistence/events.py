from __future__ import annotations
from ...models import GameState
from ...models import HistoryRecord
from .dependencies import EventsPreparationDependencies


def prepare_events(deps: EventsPreparationDependencies, game: GameState) -> bool:
    changed = False
    if game.pending_event:
        post_battle_possession = game.pending_event.get("id") == "SYS_POST_BATTLE_POSSESSION"
        event = deps.events_by_id.get(game.pending_event.get("id"))
        is_mortal_event = bool(event and "mortal" in event.get("tags", []))
        saved_choices = {choice.get("id") for choice in game.pending_event.get("choices", [])}
        current_choices = {choice.get("id") for choice in event.get("choices", [])} if event else set()
        if event:
            tags = event.get("tags", [])
            if "court_task" in tags and game.pending_event.get("runtime") and not game.pending_event["runtime"].get("court_authorized"):
                game.pending_event["runtime"]["court_authorized"] = True
                changed = True
            if game.player.realm_index >= 4 and "faction" in tags and "duty" in tags and "war" not in tags:
                current_choices.update({"__delegate_faction_task", "__decline_faction_task"})
        incompatible = not post_battle_possession and (
            event is None or ("all_realms" not in (event.get("tags", []) if event else []) and (game.player.realm_index == 0) != is_mortal_event)
            or not saved_choices <= current_choices
        )
        if incompatible:
            game.pending_event = None
            game.active_trial = None
            game.history.append(HistoryRecord(
                "SYS_CONTENT_MIGRATION", 1, game.player.age, "命途校正", None, "migrated",
                "旧版本中与当前境界不相容的待处理事件已移出事件池。", {}, ["system", "migration"],
            ))
            changed = True
    elif game.active_trial:
        game.active_trial = None
        game.history.append(HistoryRecord(
            "SYS_TRIAL_MIGRATION", 1, game.player.age, "劫数校正", None, "migrated",
            "旧存档中失去对应事件的突破或雷劫状态已经清理，可以继续行动。", {},
            ["system", "migration", "tribulation"],
        ))
        changed = True
    return bool(changed)
