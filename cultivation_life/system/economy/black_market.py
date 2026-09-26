from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import copy
    from typing import Any
    from ...models import HistoryRecord
    from ...runtime import now_iso
    from ...rules import add_item, remove_item


class EconomyBlackMarketMethods:
    def buy_black_market_item(self, game_id: str, result_id: str, quantity: int = 1) -> dict[str, Any]:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 999:
            raise ValueError("购买数量必须为 1–999 的整数")
        game = self._load(game_id)
        state = self._require_auction_access(game, {"black_market"})
        result = next((row for row in state.get("black_market_results", []) if row["id"] == result_id), None)
        if not result:
            raise ValueError("请先检索并选择一件黑市商品")
        if not self._is_world_market_good(
            game.player.world, str(result.get("kind", "")), str(result.get("content_id", "")),
        ):
            raise ValueError("这件货物不属于当前世界的流通范围")
        kind = str(result["kind"])
        total_price = int(result["price"]) * quantity
        instance_key = {"crafting_material": "material_instance", "formation_material": "formation_material_instance"}.get(kind)
        if instance_key and not isinstance(result.get(instance_key), dict):
            raise ValueError("这份黑市材料已经失去灵性")
        if not remove_item(game.player, "spirit_stone", total_price):
            raise ValueError(f"需要 {total_price} 枚下品灵石")
        if kind == "crafting_material":
            instance = copy.deepcopy(result.get("material_instance"))
            if not isinstance(instance, dict):
                raise ValueError("这份黑市炼器材料已经失去灵性")
            import uuid
            for _ in range(quantity):
                purchased = copy.deepcopy(instance)
                purchased["id"] = f"material-{uuid.uuid4().hex}"
                game.player.crafting_materials.append(purchased)
        elif kind == "formation_material":
            instance = copy.deepcopy(result.get("formation_material_instance"))
            if not isinstance(instance, dict):
                raise ValueError("这份黑市阵材已经失去阵性")
            import uuid
            for _ in range(quantity):
                purchased = copy.deepcopy(instance)
                purchased["id"] = f"formation-material-{uuid.uuid4().hex}"
                game.player.formation_materials.append(purchased)
        elif kind == "formation_supply":
            supply_id = str(result["content_id"])
            game.player.formation_repair_supplies[supply_id] = (
                int(game.player.formation_repair_supplies.get(supply_id, 0)) + quantity
            )
        else:
            for _ in range(quantity):
                self._grant_auction_content(game.player, kind, str(result["content_id"]))
        game.history.append(HistoryRecord(
            "SYS_BLACK_MARKET_BUY", 1, game.player.age, "黑市补缺", result_id, "purchased",
            f"你以严重溢价支付 {total_price} 枚灵石，购得{result['name']} ×{quantity}。",
            {"spirit_stone":-total_price, "content_id":result["content_id"], "quantity":quantity},
            ["system", "black_market", f"world:{game.player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def sell_black_market_asset(self, game_id: str, kind: str, asset_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._require_auction_access(game, {"black_market"})
        ratio = float(self._auction_rules()["black_market_sell_ratio"])
        if kind == "item":
            item = next((row for row in game.player.inventory if row.id == asset_id and row.quantity > 0), None)
            if not item or item.crafted_artifact_id or asset_id == "spirit_stone" or not remove_item(game.player, asset_id):
                raise ValueError("该物品无法在黑市出手")
            name = item.name
            plant_value = self._plant_item_value(item)
            price = max(1, round(
                (plant_value or self._catalog_price("item", asset_id)) * (
                    float(self._spirit_field_rules()["black_market_sell_ratio"])
                    if plant_value is not None else ratio
                )
            ))
        elif kind == "puppet":
            puppet = next((row for row in game.player.puppets if str(row.get("id")) == asset_id), None)
            if not puppet or puppet.get("type") == "living":
                raise ValueError("黑市只接收机关傀儡与炼尸，不接收活傀")
            game.player.puppets.remove(puppet)
            name = str(puppet.get("name", "无名傀儡"))
            price = max(5, round(float(puppet.get("combat_power", 0)) * 0.08))
        else:
            raise ValueError("未知黑市资产类型")
        add_item(game.player, "spirit_stone", price)
        game.history.append(HistoryRecord(
            "SYS_BLACK_MARKET_SELL", 1, game.player.age, "黑市销赃", asset_id, "sold",
            f"你在黑市出手{name}，获得 {price} 枚下品灵石。", {"spirit_stone":price},
            ["system", "black_market", f"world:{game.player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def leave_black_market(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._require_auction_access(game, {"black_market"})
        game.auction_state = {"status":"cooldown", "actions_remaining":int(self._auction_rules()["cooldown_actions"])}
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
