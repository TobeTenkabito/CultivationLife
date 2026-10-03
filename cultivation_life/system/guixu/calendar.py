from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
import copy
import random
from .dependencies import GuixuCalendarDependencies


def _announce_guixu_cycle(
    deps: GuixuCalendarDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
) -> None:
    available = list(cycle["pool_remaining"])
    draw_count = min(int(deps._guixu_settings()["draw_per_cycle"]), len(available))
    selected = rng.sample(available, draw_count) if draw_count else []
    for entry_id in selected:
        cycle["pool_remaining"].remove(entry_id)
    cycle["cycle_index"] = int(cycle.get("cycle_index", 0)) + 1
    pool_exhausted = not cycle["pool_remaining"]
    cycle["round_entries"] = [{
        "pool_entry_id": entry_id, "layer_id": None, "claim_at_day": None,
        "holder_id": None, "resolution": "announced",
        "pool_last": bool(pool_exhausted and entry_id == selected[-1]),
    } for entry_id in selected]
    cycle["roster"] = []
    cycle["npc_teams"] = []
    cycle["npc_incidents"] = []
    cycle["npc_simulated_until_day"] = 0
    cycle["phase"] = "announced"
    majors = [
        deps._guixu_entry_definition(dungeon, entry_id)["name"]
        for entry_id in selected
        if deps._guixu_entry_definition(dungeon, entry_id).get("tier") == "major"
    ]
    if not majors and selected:
        ranked = sorted(
            (deps._guixu_entry_definition(dungeon, entry_id) for entry_id in selected),
            key=lambda row: float(row.get("value", 0)), reverse=True,
        )
        majors = [str(row["name"]) for row in ranked[:1]]
    game.history.append(HistoryRecord(
        "SYS_GUIXU_ANNOUNCE", 1, game.player.age, "归墟预告", dungeon["id"],
        "announced", f"{dungeon['name']}将在{dungeon['announce_lead_years']}年后开启；"
        + (f"本届重宝疑为{'、'.join(majors[:2])}。" if majors else "主宝物池已经搬空。"),
        {"cycle_index": cycle["cycle_index"], "entries": selected},
        ["system", "guixu", "announcement", f"world:{dungeon['world']}"],
    ))
    if (
        game.settings.get("guixu_event_popup", True) and not game.settings.get("silent_events", False)
        and game.player.world == dungeon["world"] and not game.pending_event
    ):
        event = deps._instantiate_event(deps.events_by_id["EVT_GUIXU_ANNOUNCE"], game, rng)
        event["body"] = (
            event["body"].replace("{dungeon_name}", str(dungeon["name"]))
            .replace("{lead_years}", str(dungeon["announce_lead_years"]))
            .replace("{major_treasures}", "、".join(majors[:2]) or "无")
        )
        event["runtime"] = {"dungeon_id": dungeon["id"], "cycle_index": cycle["cycle_index"]}
        game.pending_event = event


def _open_guixu_cycle(
    deps: GuixuCalendarDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
) -> None:
    if cycle["phase"] == "closed":
        deps._announce_guixu_cycle(game, dungeon, cycle, rng)
        if game.pending_event and game.pending_event.get("id") == "EVT_GUIXU_ANNOUNCE":
            game.pending_event = None
    cycle["roster"] = deps._generate_guixu_roster(game, dungeon, cycle, rng)
    deps._form_guixu_npc_teams(cycle, rng)
    cycle["npc_incidents"] = []
    cycle["npc_simulated_until_day"] = 0
    window = int(dungeon["window_days"])
    for row in cycle["round_entries"]:
        definition = deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
        row["layer_id"] = deps._guixu_weighted_key(definition["layer_weights"], rng)
        row["claim_at_day"] = rng.randint(3, max(3, window - 5))
        row["holder_id"] = None
        row["resolution"] = "unclaimed"
    cycle["phase"] = "open"
    cycle["opened_age"] = game.player.age
    session = game.guixu_state.get("player_session")
    if session and session.get("dungeon_id") == dungeon["id"] and session.get("trapped"):
        session["trapped"] = False
        session["remaining_days"] = window
        session["cycle_index"] = cycle["cycle_index"]
        session["carried_entry_ids"] = []
        session["recruited_actor_ids"] = []
        session["pending_threat"] = None
        session["threatened_actor_ids"] = []
    game.history.append(HistoryRecord(
        "SYS_GUIXU_OPEN", 1, game.player.age, "归墟开启", dungeon["id"], "opened",
        f"{dungeon['name']}开启，本届潮门可稳定{window}天。",
        {"cycle_index": cycle["cycle_index"]},
        ["system", "guixu", "open", f"world:{dungeon['world']}"],
    ))
    if (
        game.settings.get("guixu_event_popup", True) and not game.settings.get("silent_events", False)
        and game.player.world == dungeon["world"] and not game.pending_event
        and not (session and session.get("dungeon_id") == dungeon["id"])
    ):
        event = deps._instantiate_event(deps.events_by_id["EVT_GUIXU_OPEN"], game, rng)
        entry_name = deps.maps.location(dungeon["world"], dungeon["entry_location_id"])["name"]
        event["body"] = (
            event["body"].replace("{dungeon_name}", str(dungeon["name"]))
            .replace("{window_days}", str(window)).replace("{entry_name}", str(entry_name))
        )
        event["runtime"] = {"dungeon_id": dungeon["id"], "cycle_index": cycle["cycle_index"]}
        game.pending_event = event


def _close_guixu_cycle(
    deps: GuixuCalendarDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any], rng: random.Random,
) -> None:
    if cycle.get("phase") != "open":
        return
    deps._assign_due_guixu_entries(game, dungeon, cycle, int(dungeon["window_days"]), rng)
    roster = {row["actor_id"]: row for row in cycle.get("roster", [])}
    report = {"lost": [], "carried": [], "trapped": [], "returned": [], "player": []}
    for row in cycle.get("round_entries", []):
        definition = deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
        resolution = str(row.get("resolution", "unclaimed"))
        if resolution == "player":
            report["player"].append(definition["name"])
            continue
        holder = roster.get(str(row.get("holder_id")))
        if holder is None:
            cycle["pool_remaining"].append(row["pool_entry_id"])
            row["resolution"] = "returned"
            report["returned"].append(definition["name"])
            continue
        if holder["actor_kind"] == "anonymous":
            holder["status"] = "departed"
            row["resolution"] = "lost"
            report["lost"].append(definition["name"])
            continue
        outcome = rng.choices(["carried", "trapped", "lost"], weights=[.62, .25, .13], k=1)[0]
        row["resolution"] = outcome
        holder["status"] = "trapped" if outcome == "trapped" else "departed"
        report[outcome].append(definition["name"])
        if outcome in {"carried", "trapped"}:
            game.guixu_state["external_treasures"].append({
                "dungeon_id": dungeon["id"], "pool_entry_id": row["pool_entry_id"],
                "holder_npc_id": holder.get("npc_id"), "status": outcome,
            })
    session = game.guixu_state.get("player_session")
    if session and session.get("dungeon_id") == dungeon["id"] and not session.get("exited"):
        session["trapped"] = True
        session["remaining_days"] = 0
        session["pending_threat"] = None
    cycle["phase"] = "closed"
    # The closing tide ejects every other explorer.  Keep only the outcome
    # report and external treasure records; a trapped player must not keep
    # seeing stale actors from the finished expedition.
    cycle["roster"] = []
    cycle["last_report"] = report
    cycle["next_open_age"] = int(cycle["next_open_age"]) + int(dungeon["period_years"])
    cycle["next_announce_age"] = int(cycle["next_open_age"]) - int(dungeon["announce_lead_years"])
    game.history.append(HistoryRecord(
        "SYS_GUIXU_CLOSE", 1, game.player.age, "归墟闭合", dungeon["id"], "closed",
        f"{dungeon['name']}闭合：玩家取得{len(report['player'])}件，NPC携出{len(report['carried'])}件，"
        f"被困{len(report['trapped'])}件，永久失落{len(report['lost'])}件，回池{len(report['returned'])}件。",
        copy.deepcopy(report), ["system", "guixu", "report", f"world:{dungeon['world']}"],
    ))


def _advance_guixu_calendar(
    deps: GuixuCalendarDependencies, game: GameState, rng: random.Random, era_news: list[str],
) -> bool:
    """Advance yearly Guixu boundaries; return True when player input is required."""
    deps._ensure_guixu_state(game)
    definitions = deps._guixu_definitions()
    requires_input = False
    for dungeon_id, dungeon in definitions.items():
        cycle = game.guixu_state["cycles"][dungeon_id]
        if cycle.get("phase") == "open" and game.player.age > int(cycle.get("opened_age") or -1):
            session = game.guixu_state.get("player_session")
            if not session or session.get("dungeon_id") != dungeon_id or not session.get("trapped"):
                deps._close_guixu_cycle(game, dungeon, cycle, rng)
                era_news.append(f"{game.player.age}岁：{dungeon['name']}闭合。")
        if cycle.get("phase") == "closed" and game.player.age >= int(cycle["next_announce_age"]):
            deps._announce_guixu_cycle(game, dungeon, cycle, rng)
            era_news.append(f"{game.player.age}岁：收到{dungeon['name']}预告。")
            if game.pending_event:
                requires_input = True
        if cycle.get("phase") == "announced" and game.player.age >= int(cycle["next_open_age"]):
            deps._open_guixu_cycle(game, dungeon, cycle, rng)
            era_news.append(f"{game.player.age}岁：{dungeon['name']}开启。")
            if game.pending_event:
                requires_input = True
    return requires_input


def _guixu_elapsed_days(
    deps: GuixuCalendarDependencies, dungeon: dict[str, Any], session: dict[str, Any],
) -> int:
    return int(dungeon["window_days"]) - int(session.get("remaining_days", 0))


def _consume_guixu_days(
    deps: GuixuCalendarDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    session: dict[str, Any], days: int, rng: random.Random,
) -> None:
    session["remaining_days"] = max(0, int(session.get("remaining_days", 0)) - int(days))
    deps._assign_due_guixu_entries(
        game, dungeon, cycle, deps._guixu_elapsed_days(dungeon, session), rng,
    )
    if session["remaining_days"] <= 0:
        deps._close_guixu_cycle(game, dungeon, cycle, rng)
