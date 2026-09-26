from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from ...models import GameState, HistoryRecord
    from ...runtime import now_iso
    from ...rules import add_item, remove_item


class EconomyPrivateTradeMethods:
    def _private_trade_attendee(self, game: GameState, npc_id: str) -> dict[str, Any]:
        state = self._require_auction_access(game, {"open"})
        attendee = next((row for row in state.get("attendees", []) if row["id"] == npc_id), None)
        if not attendee or not attendee.get("private_trade_unlocked"):
            raise ValueError("须先与对方交谈，取得信任后才能私下交易")
        return attendee

    def buy_private_trade_item(self, game_id: str, npc_id: str, offer_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        attendee = self._private_trade_attendee(game, npc_id)
        offer = next((row for row in attendee.get("trade_offers", []) if row["id"] == offer_id and not row.get("sold")), None)
        if not offer:
            raise ValueError("这件私人物品已经易主")
        if not self._is_world_market_good(
            game.player.world, str(offer.get("kind", "")), str(offer.get("content_id", "")),
        ):
            raise ValueError("这件货物不属于当前世界的流通范围")
        if not remove_item(game.player, "spirit_stone", int(offer["price"])):
            raise ValueError(f"私下交易需要 {offer['price']} 枚下品灵石")
        self._grant_auction_content(game.player, str(offer["kind"]), str(offer["content_id"]))
        offer["sold"] = True
        npc = self._find_npc(game, npc_id)
        affinity_range = self._auction_rules()["private_trade_buy_affinity_gain"]
        rng = self._auction_rng(game, f"private-buy:{npc_id}:{offer_id}")
        affinity_gain = rng.randint(int(affinity_range[0]), int(affinity_range[1]))
        if npc:
            affinity_gain = self._sage_affinity_gain(game.player, affinity_gain)
            npc.affinity = float(npc.affinity or 0) + affinity_gain
            attendee["affinity"] = round(npc.affinity, 1)
        else:
            attendee["affinity"] = round(float(attendee.get("affinity", 0)) + affinity_gain, 1)
        game.history.append(HistoryRecord(
            "SYS_AUCTION_PRIVATE_BUY", 1, game.player.age, "拍卖场私下交易", npc_id, "purchased",
            f"你以匿名身份向{attendee['name']}支付 {offer['price']} 枚灵石，购得{offer['name']}，好感 +{affinity_gain}。",
            {"content_id":offer["content_id"], "spirit_stone":-int(offer["price"]), "affinity":affinity_gain},
            ["system", "auction", "private_trade", "relationship"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def sell_private_trade_item(self, game_id: str, npc_id: str, item_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        attendee = self._private_trade_attendee(game, npc_id)
        item = next((row for row in game.player.inventory if row.id == item_id and row.quantity > 0), None)
        if not item or item_id == "spirit_stone":
            raise ValueError("这件物品无法私下出售")
        if item.crafted_artifact_id:
            raise ValueError("组合炼器法宝须按其唯一实例价值出售或寄拍")
        base = self._plant_item_value(item) or self._catalog_price("item", item_id)
        multiplier = float(self._auction_rules()["private_trade_sell_multiplier"])
        multiplier *= float(attendee.get("sell_bargains", {}).get(item_id, 1.0))
        price = max(1, round(base * multiplier))
        if not remove_item(game.player, item_id):
            raise ValueError("行囊中已没有这件物品")
        add_item(game.player, "spirit_stone", price)
        game.history.append(HistoryRecord(
            "SYS_AUCTION_PRIVATE_SELL", 1, game.player.age, "拍卖场私下交易", npc_id, "sold",
            f"{attendee['name']}私下收购{item.name}，向你支付 {price} 枚灵石。",
            {"content_id":item_id, "spirit_stone":price}, ["system", "auction", "private_trade"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def bargain_private_trade(self, game_id: str, npc_id: str, side: str, asset_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        attendee = self._private_trade_attendee(game, npc_id)
        rng = self._auction_rng(game, f"bargain:{npc_id}:{side}:{asset_id}")
        rules = self._auction_rules()
        chance = min(0.85, float(rules["bargain_success_base"]) + max(0.0, float(attendee.get("affinity", 0))) * float(rules["bargain_affinity_factor"]))
        success = rng.random() < chance
        if side == "buy":
            offer = next((row for row in attendee.get("trade_offers", []) if row["id"] == asset_id and not row.get("sold")), None)
            if not offer or offer.get("bargained"):
                raise ValueError("这件商品已经没有继续还价的余地")
            offer["bargained"] = True
            if success:
                discount = rng.uniform(*rules["bargain_buy_discount"])
                offer["price"] = max(1, round(int(offer["price"]) * (1 - discount)))
        elif side == "sell":
            item = next((row for row in game.player.inventory if row.id == asset_id and row.quantity > 0), None)
            attempts = attendee.setdefault("sell_bargain_attempts", [])
            if not item or item.crafted_artifact_id or asset_id in attempts:
                raise ValueError("这件物品已经没有继续还价的余地")
            attempts.append(asset_id)
            if success:
                bonus = rng.uniform(*rules["bargain_sell_bonus"])
                attendee.setdefault("sell_bargains", {})[asset_id] = 1 + bonus
        else:
            raise ValueError("未知还价方向")
        state = game.auction_state
        state.setdefault("bid_logs", []).append(
            f"你与{attendee['name']}私下还价，{'对方最终松口' if success else '对方不肯让步'}。"
        )
        state["bid_logs"] = state["bid_logs"][-18:]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
