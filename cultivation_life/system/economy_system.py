from __future__ import annotations

import copy
import math
import random
import re
from typing import Any

# Moved methods still use this module's globals; retain the imports below.

from ..content_registry import (
    GUIXU_EXCLUSIVE_ITEM_IDS, ITEM_CATALOG, MARKET_GOODS, MARKET_SETTINGS,
    REALMS, TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES, WORLD_SYSTEMS,
)
from ..models import GameState, HistoryRecord, Item, Player
from ..runtime import decode_rng, encode_rng, now_iso
from .possession_system import advance_player_age
from .exchange_system import ExchangeSystemMixin
from ..rules import (
    QI_SOURCE_NAMES, acquire_technique, add_item, can_player_practice_technique,
    combat_requirement_display, max_hp, max_mp, remove_item,
)


from ._assembly import include_system_methods as _include_system_methods
from .economy.market import EconomyMarketMethods
from .economy.spirit_fields import EconomySpiritFieldMethods
from .economy.arts import EconomyArtMethods
from .economy.auctions import EconomyAuctionMethods
from .economy.private_trade import EconomyPrivateTradeMethods
from .economy.black_market import EconomyBlackMarketMethods
from .economy.treasure import EconomyTreasureMethods


@_include_system_methods(
    EconomyMarketMethods,
    EconomySpiritFieldMethods,
    EconomyArtMethods,
    EconomyAuctionMethods,
    EconomyPrivateTradeMethods,
    EconomyBlackMarketMethods,
    EconomyTreasureMethods,
    namespace=globals(),
)
class EconomySystemMixin(ExchangeSystemMixin):
    """坊市库存与探宝奖励的领域实现；主引擎只负责调用和持久化。"""

    def _cancel_auction_for_world_change(self, game: GameState) -> None:
        state = game.auction_state
        if not state or state.get("status") == "cooldown":
            return
        # Only an unfinished auction has frozen bids or unsold consignments. Once the
        # black market opens, lots have already been delivered and sellers paid.
        if state.get("status") in {"scheduled", "open"}:
            for lot in state.get("lots", []):
                if lot.get("current_bidder") == "player":
                    add_item(game.player, "spirit_stone", int(lot.get("current_bid", 0)))
            for consignment in state.get("consignments", []):
                if consignment.get("kind") == "crafted_artifact" and isinstance(consignment.get("artifact"), dict):
                    from .crafting_system import store_crafted_artifact
                    store_crafted_artifact(game.player, copy.deepcopy(consignment["artifact"]))
                else:
                    add_item(game.player, str(consignment["content_id"]))
        game.auction_state = {
            "status":"cooldown", "actions_remaining":int(self._auction_rules()["cooldown_actions"]),
        }

    def search_black_market(self, game_id: str, pattern: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"black_market"})
        pattern = str(pattern).strip()
        if not pattern or len(pattern) > 40:
            raise ValueError("请输入1至40个字符的检索表达式")
        try:
            matcher = re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"正则表达式无效：{error}") from error
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in MARKET_GOODS:
            if row.get("world", "human") == game.player.world:
                unique[(str(row["kind"]), str(row["content_id"]))] = dict(row)
        # Material stalls are generated outside MARKET_GOODS because each
        # crafting/formation piece is a real unique instance. Black-market
        # search still exposes the complete world-local catalog and freezes
        # the generated instance in the saved search result until purchase.
        material_rng = random.Random(
            f"{game.seed}:black-market-material:{state.get('id', '')}:{pattern}"
        )
        material_rows: list[dict[str, Any]] = []
        for definition in self._crafting_material_defs().values():
            if str(definition.get("world")) != game.player.world:
                continue
            from .crafting_system import make_crafting_material_instance
            instance = make_crafting_material_instance(
                definition, material_rng, source="黑市购得", origin_world=game.player.world,
            )
            material_rows.append({
                "kind":"crafting_material", "content_id":str(definition["id"]),
                "name":str(definition["name"]),
                "description":f"炼器材料 · {instance['state']} · 材料价值 {int(instance['material_value']):,}",
                "tier":int(definition.get("tier", 1)),
                "base_price":int(instance["material_value"]), "material_instance":instance,
            })
        for definition in self._formation_material_defs().values():
            if str(definition.get("world")) != game.player.world:
                continue
            from .formation_system import NATURE_NAMES, make_formation_material_instance
            instance = make_formation_material_instance(
                definition, source="黑市购得", origin_world=game.player.world,
            )
            material_rows.append({
                "kind":"formation_material", "content_id":str(definition["id"]),
                "name":str(definition["name"]),
                "description":f"阵法材料 · {NATURE_NAMES.get(str(definition.get('nature')), definition.get('nature'))}性 · 固有阵值 {float(definition.get('formation_value', 0)):g}",
                "tier":int(definition.get("tier", 1)),
                "base_price":int(definition.get("base_value", 1)), "formation_material_instance":instance,
            })
        for definition in self._formation_maintenance_defs().values():
            if str(definition.get("world")) != game.player.world:
                continue
            material_rows.append({
                "kind":"formation_supply", "content_id":str(definition["id"]),
                "name":str(definition["name"]),
                "description":f"修阵材料 · 恢复 {float(definition.get('repair_value', 0)):g}% 镇地阵完整度",
                "tier":int(definition.get("tier", 1)),
                "base_price":int(definition.get("base_value", 1)),
            })
        results = []
        multiplier = float(self._auction_rules()["black_market_buy_multiplier"])
        for (kind, content_id), row in unique.items():
            name, description = self._auction_content(kind, content_id)
            if not matcher.search(f"{name} {description}"):
                continue
            results.append({
                "id":f"black-{kind}-{content_id}", "kind":kind, "content_id":content_id,
                "name":name, "description":description, "tier":int(row["tier"]),
                "tier_name":REALMS[int(row["tier"])].name,
                "price":max(1, round(self._catalog_price(kind, content_id) * multiplier)),
            })
        for row in material_rows:
            if not matcher.search(f"{row['name']} {row['description']}"):
                continue
            tier = max(0, min(len(REALMS) - 1, int(row["tier"])))
            results.append({
                **row,
                "id":f"black-{row['kind']}-{row['content_id']}",
                "tier":tier, "tier_name":REALMS[tier].name,
                "price":max(1, round(int(row["base_price"]) * multiplier)),
            })
        results.sort(key=lambda row: (row["tier"], row["name"]))
        state["black_market_results"] = results[:int(self._auction_rules()["black_market_result_limit"])]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
