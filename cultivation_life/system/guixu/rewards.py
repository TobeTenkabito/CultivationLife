from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
from ...content_registry import TECHNIQUE_CATALOG
from ...rules import acquire_technique
from ...rules import add_item
from ...rules import has_item
from ...rules import remove_item
from .dependencies import GuixuRewardsDependencies


def _guixu_grant_entry(
    deps: GuixuRewardsDependencies, game: GameState, dungeon: dict[str, Any], row: dict[str, Any], source: str,
) -> str:
    definition = deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
    kind, content_id = str(definition["kind"]), str(definition["content_id"])
    if kind == "technique":
        acquire_technique(game.player, TECHNIQUE_CATALOG[content_id])
    else:
        add_item(game.player, content_id, int(definition.get("quantity", 1)))
    row["holder_id"] = "player"
    row["resolution"] = "player"
    session = game.guixu_state.get("player_session")
    if session is not None:
        session.setdefault("carried_entry_ids", []).append(row["pool_entry_id"])
        session["player_ever_claimed"] = True
    treasure_result = "last_treasure" if row.get("pool_last") else source
    game.history.append(HistoryRecord(
        "SYS_GUIXU_TREASURE", 1, game.player.age, "归墟得宝", row["pool_entry_id"], treasure_result,
        f"你取得了{definition['name']}。", {"dungeon_id": dungeon["id"], "entry_id": row["pool_entry_id"]},
        ["system", "guixu", "treasure"],
    ))
    return str(definition["name"])


def _guixu_transferable_player_entries(
    deps: GuixuRewardsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    session: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    carried = {str(entry_id) for entry_id in session.get("carried_entry_ids", [])}
    result = []
    for row in cycle.get("round_entries", []):
        if row.get("resolution") != "player" or str(row.get("pool_entry_id")) not in carried:
            continue
        definition = deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
        # The first technique copy is learned immediately and is no longer a
        # transferable object.  Physical treasures and spirit-stone bundles
        # can still be surrendered while they remain in the inventory.
        if definition.get("kind") == "technique":
            continue
        quantity = int(definition.get("quantity", 1))
        if has_item(game.player, str(definition["content_id"]), quantity):
            result.append((row, definition))
    return result


def _surrender_guixu_treasure(
    deps: GuixuRewardsDependencies, game: GameState, dungeon: dict[str, Any], cycle: dict[str, Any],
    session: dict[str, Any], threat: dict[str, Any], actor: dict[str, Any],
) -> str:
    row = next(
        (
            entry for entry in cycle.get("round_entries", [])
            if entry.get("pool_entry_id") == threat.get("pool_entry_id")
            and entry.get("resolution") == "player"
        ), None,
    )
    if row is None:
        raise ValueError("被索要的宝物已经不在你手中")
    definition = deps._guixu_entry_definition(dungeon, str(row["pool_entry_id"]))
    quantity = int(definition.get("quantity", 1))
    if definition.get("kind") == "technique" or not remove_item(
        game.player, str(definition["content_id"]), quantity,
    ):
        raise ValueError("被索要的宝物已经无法交出")
    row["holder_id"] = actor["actor_id"]
    row["resolution"] = "held"
    row["npc_claim_source"] = "player_surrender"
    session["carried_entry_ids"] = [
        entry_id for entry_id in session.get("carried_entry_ids", [])
        if str(entry_id) != str(row["pool_entry_id"])
    ]
    if actor.get("team_id"):
        deps._dissolve_guixu_npc_team(
            game, dungeon, cycle, str(actor["team_id"]),
            f"因{actor['name']}勒索取得{definition['name']}而利益破裂",
        )
    return str(definition["name"])
