from __future__ import annotations
from typing import Any
from ...models import GameState
from ...models import HistoryRecord
from ...content_registry import REALMS
from ...rules import add_item
import copy
import math
from ...runtime import now_iso
import random
from ...rules import remove_item
from .dependencies import CraftingArtifactsDependencies


def crafted_artifact_action(
    deps: CraftingArtifactsDependencies,
    game_id: str,
    artifact_id: str,
    action: str,
    start_price: int = 0,
) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    artifact = next(
        (row for row in player.crafted_artifacts if str(row.get("id")) == artifact_id),
        None,
    )
    if not artifact:
        raise ValueError("这件炼器法宝不存在")
    if action == "equip":
        if artifact.get("tianji"):
            tianji_ids = {
                str(row.get("id"))
                for row in player.crafted_artifacts
                if row.get("tianji")
            }
            player.equipped_crafted_artifact_ids = [
                value
                for value in player.equipped_crafted_artifact_ids
                if value not in tianji_ids
            ] + [artifact_id]
            game.tianji_state["activated_artifact_id"] = artifact_id
        else:
            raise ValueError("炼器法宝收入包裹后自动生效，无需另行装备")
    elif action == "unequip":
        if artifact.get("tianji"):
            player.equipped_crafted_artifact_ids = [
                value
                for value in player.equipped_crafted_artifact_ids
                if value != artifact_id
            ]
            if game.tianji_state.get("activated_artifact_id") == artifact_id:
                game.tianji_state["activated_artifact_id"] = None
        else:
            raise ValueError("炼器法宝与普通装备相同，留在包裹中即自动生效")
    elif action == "natal":
        if artifact.get("tianji"):
            tianji_ids = {
                str(row.get("id"))
                for row in player.crafted_artifacts
                if row.get("tianji")
            }
            player.equipped_crafted_artifact_ids = [
                value
                for value in player.equipped_crafted_artifact_ids
                if value not in tianji_ids
            ] + [artifact_id]
            game.tianji_state["activated_artifact_id"] = artifact_id
        deps._bind_crafted_natal_artifact(game, artifact)
    elif action == "unbind_natal":
        deps._unbind_crafted_natal_artifact(game, artifact_id)
    elif action == "sell":
        if artifact.get("tianji"):
            raise ValueError("神机法宝不能按普通成品出售")
        if artifact.get("is_natal"):
            raise ValueError("已设为本命的法宝不能出售")
        price = max(
            1,
            round(
                int(artifact["anchor_value"])
                * float(deps._crafting_rules()["ordinary_sell_ratio"])
            ),
        )
        deps.remove_crafted_artifact(player, artifact)
        from ..economy.local_market import legacy_sale
        legacy_sale(game, price, '独立法器收购')
        game.history.append(
            HistoryRecord(
                "SYS_ARTIFACT_SELL",
                1,
                player.age,
                "坊市出售法宝",
                artifact_id,
                "sold",
                f"你将{deps.name_or_artifact(artifact)}出售，获得 {price:,} 枚灵石；成品实例已离开存档，不会进入全局回收池。",
                {"spirit_stone": price},
                ["system", "crafting", "market"],
            )
        )
    elif action == "consign":
        if artifact.get("tianji"):
            raise ValueError("神机法宝不能进入普通拍卖寄售")
        deps._consign_crafted_artifact(game, artifact, int(start_price or 0))
    else:
        raise ValueError("未知炼器法宝操作")
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _consign_crafted_artifact(
    deps: CraftingArtifactsDependencies,
    game: GameState,
    artifact: dict[str, Any],
    start_price: int,
) -> None:
    state = deps._require_auction_access(game, {"scheduled", "open"})
    artifact_id = str(artifact["id"])
    if artifact.get("is_natal"):
        raise ValueError("已设为本命的法宝不能送拍")
    base_price = max(1, int(artifact["anchor_value"]))
    minimum = max(
        1,
        math.ceil(
            base_price * float(deps._auction_rules()["consignment_min_price_ratio"])
        ),
    )
    maximum = max(
        minimum,
        math.floor(
            base_price * float(deps._auction_rules()["consignment_max_price_ratio"])
        ),
    )
    start_price = int(start_price or round(base_price * 0.8))
    if not minimum <= start_price <= maximum:
        raise ValueError(f"起拍价须在 {minimum:,}—{maximum:,} 灵石之间")
    fee = max(
        1,
        math.ceil(
            base_price * float(deps._auction_rules()["consignment_listing_fee_ratio"])
        ),
    )
    if not remove_item(game.player, "spirit_stone", fee):
        raise ValueError(f"上拍前须支付 {fee:,} 枚灵石占位费")
    from ..economy.local_market import auction_fee
    auction_fee(game, fee, '拍卖占位费')
    snapshot = copy.deepcopy(artifact)
    deps.remove_crafted_artifact(game.player, artifact)
    consignment = {
        "kind": "crafted_artifact",
        "content_id": artifact_id,
        "artifact": snapshot,
        "start_price": start_price,
        "tier": game.player.realm_index,
        "rated_price": base_price,
        "listing_fee": fee,
    }
    state.setdefault("consignments", []).append(consignment)
    if state["status"] == "open":
        rng = deps._auction_rng(game, "crafted-consignment")
        state["lots"].append(
            deps._make_crafted_auction_lot(
                game,
                rng,
                consignment,
                f"player-{len(state['consignments']) - 1}",
            )
        )
    game.history.append(
        HistoryRecord(
            "SYS_ARTIFACT_CONSIGN",
            1,
            game.player.age,
            "法宝寄拍",
            artifact_id,
            "consigned",
            f"你支付 {fee:,} 枚占位费，将{deps.name_or_artifact(snapshot)}以 {start_price:,} 灵石起拍。",
            {"listing_fee": -fee, "start_price": start_price},
            ["system", "crafting", "auction"],
        )
    )


def _make_crafted_auction_lot(
    deps: CraftingArtifactsDependencies,
    game: GameState,
    rng: random.Random,
    consignment: dict[str, Any],
    suffix: str,
) -> dict[str, Any]:
    artifact = consignment["artifact"]
    rated = int(consignment["rated_price"])
    start = int(consignment["start_price"])
    return {
        "id": f"{game.auction_state['id']}-{suffix}",
        "kind": "crafted_artifact",
        "content_id": str(artifact["id"]),
        "artifact": copy.deepcopy(artifact),
        "name": str(artifact["name"]),
        "description": f"{artifact['quality_name']} · {artifact['mold_name']} · {deps.artifact_summary(artifact)}",
        "tier": int(consignment.get("tier", 1)),
        "tier_name": REALMS[max(0, min(12, int(consignment.get("tier", 1))))].name,
        "start_price": start,
        "current_bid": start,
        "rated_price": rated,
        "maximum_bid": max(
            1,
            math.floor(
                rated * float(deps._auction_rules()["consignment_max_price_ratio"])
            ),
        ),
        "current_bidder": "npc",
        "current_bidder_name": rng.choice(deps._auction_rules()["bidder_aliases"]),
        "seller": "player",
        "closed": False,
    }
