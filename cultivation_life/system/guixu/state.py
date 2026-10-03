from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
import copy
from .dependencies import GuixuStateDependencies


def _ensure_guixu_state(deps: GuixuStateDependencies, game: GameState) -> bool:
    state = game.guixu_state
    changed = False
    if not isinstance(state, dict):
        game.guixu_state = state = {}
        changed = True
    defaults = {
        "schema_version": 1, "cycles": {}, "entered_cycles": {},
        "external_treasures": [], "player_session": None,
    }
    for key, default in defaults.items():
        if key not in state:
            state[key] = copy.deepcopy(default)
            changed = True
    definitions = deps._guixu_definitions()
    if not definitions:
        session = state.get("player_session")
        if session:
            game.player.location_id = str(session.get("entry_location_id") or game.player.location_id)
            state["player_session"] = None
            game.history.append(HistoryRecord(
                "SYS_GUIXU_DISABLED_EJECT", 1, game.player.age, "归墟规则冻结", None,
                "ejected", "归墟扩展未启用，你被安全送回原入口；既有周期状态保持冻结。",
                {}, ["system", "guixu", "migration"],
            ))
            changed = True
        return changed
    cycles = state["cycles"]
    for dungeon_id, definition in definitions.items():
        if dungeon_id not in cycles:
            next_open = deps._next_guixu_open(definition, game.player.age)
            cycles[dungeon_id] = {
                "phase": "closed", "cycle_index": 0,
                "next_open_age": next_open,
                "next_announce_age": next_open - int(definition["announce_lead_years"]),
                "pool_remaining": [str(row["id"]) for row in definition["treasure_pool"]],
                "round_entries": [], "roster": [], "last_report": None,
                "opened_age": None,
            }
            changed = True
        cycle = cycles[dungeon_id]
        for key, default in {
            "npc_teams": [], "npc_incidents": [], "npc_simulated_until_day": 0,
        }.items():
            if key not in cycle:
                cycle[key] = copy.deepcopy(default)
                changed = True
    return changed


def _guixu_entry_definition(
    deps: GuixuStateDependencies, dungeon: dict[str, Any], pool_entry_id: str,
) -> dict[str, Any]:
    entry = next(
        (row for row in dungeon["treasure_pool"] if row["id"] == pool_entry_id), None,
    )
    if entry is None:
        raise ValueError("归墟宝物定义已经不存在")
    return entry


def _guixu_cycle_and_definition(
    deps: GuixuStateDependencies, game: GameState, dungeon_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dungeon = deps._guixu_definitions().get(dungeon_id)
    if not dungeon:
        raise ValueError("未知归墟副本")
    return dungeon, game.guixu_state["cycles"][dungeon_id]


def _enforce_guixu_rank_boundary(deps: GuixuStateDependencies, game: GameState, reason: str) -> str:
    """Eject an explorer whose effective cultivation reaches the dungeon boundary."""
    session = game.guixu_state.get("player_session") if isinstance(game.guixu_state, dict) else None
    if not session:
        return ""
    dungeon = deps._guixu_definitions().get(str(session.get("dungeon_id", "")))
    if not dungeon or (game.player.realm_index, game.player.layer) < tuple(dungeon["eject_rank"]):
        return ""
    game.player.location_id = str(dungeon["entry_location_id"])
    game.guixu_state["player_session"] = None
    game.history.append(HistoryRecord(
        "SYS_GUIXU_EJECT", 1, game.player.age, "归墟界限传出", dungeon["id"], reason,
        f"你的当前修为达到{dungeon['name']}承载界限，被潮眼送回入口。",
        {"dungeon_id": dungeon["id"], "reason": reason},
        ["system", "guixu", "eject", f"world:{dungeon['world']}"],
    ))
    return f" 复原后的修为超过{dungeon['name']}承载界限，你随即被潮眼送回入口。"


def assert_guixu_operation_allowed(deps: GuixuStateDependencies, game_id: str, operation: str) -> None:
    # When the DLC is disabled, let the requested operation reach ``_load``;
    # its compatibility migration safely returns an active explorer first.
    if not deps.guixu_content_available():
        return
    game = deps._load(game_id)
    session = game.guixu_state.get("player_session") if isinstance(game.guixu_state, dict) else None
    if not session:
        return
    allowed = {
        "guixu-action", "choice", "use-item", "equip-technique", "technique-upgrade",
        "technique-manual-merge", "settings", "formation-save", "formation-activate",
        "formation-deactivate", "formation-delete", "secret-art",
    }
    if session.get("trapped"):
        allowed.update({"advance", "breakthrough", "body-breakthrough", "sense-breakthrough"})
    if operation not in allowed:
        raise ValueError("身在归墟时无法进行外界操作")
