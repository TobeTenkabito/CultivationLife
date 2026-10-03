from __future__ import annotations

import copy
import math
import random
import re
from functools import cached_property
from typing import Any

from ..content_registry import (
    restricted_acquisition,
    ITEM_CATALOG, MARKET_GOODS, REALMS, TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from ..models import GameState, Item, Player
from ..rules import add_item
from ..runtime import now_iso
from .economy import arts as economy_arts
from .economy import auctions as economy_auctions
from .economy import black_market as economy_black_market
from .economy import market as economy_market
from .economy import private_trade as economy_private_trade
from .economy import spirit_fields as economy_spirit_fields
from .economy import treasure as economy_treasure
from .economy.wiring import bind_economy
from .exchange_system import ExchangeSystemMixin


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
        from .spirit_voisinage import offers
        for book in offers(game, 'black_market', state.get('id', game.player.age // 10)):
            description = '仙家传承的下界改本；合参至 Lv4 可修习灵域，无法通过道门修炼。'
            if matcher.search(book.name + ' ' + description):
                results.append(dict(id='black-' + book.id, kind='spirit_manual', content_id=book.id,
                    name=book.name, description=description, tier=book.grade,
                    tier_name=REALMS[book.grade].name, price=45000))
        results.sort(key=lambda row: (row['kind'] != 'spirit_manual', row["tier"], row["name"]))
        state["black_market_results"] = results[:int(self._auction_rules()["black_market_result_limit"])]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    @cached_property
    def _economy_dependencies(self):
        return bind_economy(self)

    @staticmethod
    def _alchemy_targets(player: Player) -> dict[str, dict[str, Any]]:
        """One recipe whitelist for both presentation and command validation."""
        tiers: dict[str, int] = {}
        for row in MARKET_GOODS:
            if row['kind'] == 'item':
                item_id, tier = str(row['content_id']), int(row['tier'])
                tiers[item_id] = min(tiers.get(item_id, tier), tier)
        # This basic recipe predates the market. Special-currency and DLC loot
        # without a generic recipe must not silently become tier-one recipes.
        tiers.setdefault('healing_pill', 1)
        return {
            item_id: {'id': item_id, 'name': item.name, 'tier': tier, 'description': item.description}
            for item_id, tier in tiers.items()
            if (item := ITEM_CATALOG.get(item_id)) and 'pill' in item.tags
            and not restricted_acquisition('item', item_id)
            and tier <= min(8, player.realm_index + 1)
        }

    @staticmethod
    def _art_names() -> dict[str, str]:
        return {
            "alchemy":"炼丹", "refining":"炼器", "formation":"阵法",
            "talisman":"制符", "spirit_control":"御灵",
        }

    def _grant_art_experience(self, player: Player, art_id: str, amount: float) -> None:
        return economy_arts._grant_art_experience(self._economy_dependencies.arts, player, art_id, amount)

    def _public_art_skills(self, player: Player) -> list[dict[str, Any]]:
        return economy_arts._public_art_skills(self._economy_dependencies.arts, player)

    def refine_pill(self, game_id: str, target_item_id: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
        return economy_arts.refine_pill(self._economy_dependencies.arts, game_id, target_item_id, materials)

    @staticmethod
    def _auction_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS["auction_system"]

    @staticmethod
    def _auction_rng(game: GameState, purpose: str) -> random.Random:
        """Use an isolated deterministic stream so auctions do not perturb story/combat RNG."""
        state = game.auction_state
        step = int(state.get("rng_step", 0)) if state else 0
        if state:
            state["rng_step"] = step + 1
        identity = state.get("id", f"pending-{game.auction_sequence}") if state else f"pending-{game.auction_sequence}"
        return random.Random(f"{game.seed}:auction:{identity}:{purpose}:{game.player.age}:{step}")

    @staticmethod
    def _auction_content(kind: str, content_id: str) -> tuple[str, str]:
        if kind == "technique":
            content = TECHNIQUE_CATALOG[content_id]
            return content.name, f"{content.grade}阶功法；战斗力 +{content.combat_bonus:.0f}"
        content = ITEM_CATALOG[content_id]
        return content.name, content.description

    def _auction_location_matches(self, game: GameState) -> bool:
        return economy_auctions._auction_location_matches(self._economy_dependencies.auctions, game)

    def _require_auction_access(self, game: GameState, statuses: set[str]) -> dict[str, Any]:
        return economy_auctions._require_auction_access(self._economy_dependencies.auctions, game, statuses)

    def _schedule_auction(self, game: GameState, rng: Any) -> None:
        return economy_auctions._schedule_auction(self._economy_dependencies.auctions, game, rng)

    def _auction_goods_pool(self, world: str) -> list[dict[str, Any]]:
        return economy_auctions._auction_goods_pool(self._economy_dependencies.auctions, world)

    def _auction_good_weight(self, world: str, tier: int) -> float:
        return economy_auctions._auction_good_weight(self._economy_dependencies.auctions, world, tier)

    def _make_auction_lot(self, game: GameState, rng: Any, *, kind: str, content_id: str, tier: int, start_price: int, seller: str='npc', suffix: str, rated_price: int | None=None) -> dict[str, Any]:
        return economy_auctions._make_auction_lot(self._economy_dependencies.auctions, game, rng, kind=kind, content_id=content_id, tier=tier, start_price=start_price, seller=seller, suffix=suffix, rated_price=rated_price)

    def _open_auction(self, game: GameState, rng: Any) -> None:
        return economy_auctions._open_auction(self._economy_dependencies.auctions, game, rng)

    def _advance_auction_clock(self, game: GameState, rng: Any) -> None:
        return economy_auctions._advance_auction_clock(self._economy_dependencies.auctions, game, rng)

    def _auction_increment(self, lot: dict[str, Any]) -> int:
        return economy_auctions._auction_increment(self._economy_dependencies.auctions, lot)

    def _auction_bid_ceiling(self, lot: dict[str, Any]) -> int:
        return economy_auctions._auction_bid_ceiling(self._economy_dependencies.auctions, lot)

    def consign_auction_item(self, game_id: str, item_id: str, start_price: int=0) -> dict[str, Any]:
        return economy_auctions.consign_auction_item(self._economy_dependencies.auctions, game_id, item_id, start_price)

    def place_auction_bid(self, game_id: str, lot_id: str) -> dict[str, Any]:
        return economy_auctions.place_auction_bid(self._economy_dependencies.auctions, game_id, lot_id)

    def advance_auction_round(self, game_id: str) -> dict[str, Any]:
        return economy_auctions.advance_auction_round(self._economy_dependencies.auctions, game_id)

    def _grant_auction_content(self, player: Player, kind: str, content_id: str) -> None:
        return economy_auctions._grant_auction_content(self._economy_dependencies.auctions, player, kind, content_id)

    def _finish_auction(self, game: GameState, rng: Any, reason: str='') -> None:
        return economy_auctions._finish_auction(self._economy_dependencies.auctions, game, rng, reason)

    def negotiate_at_auction(self, game_id: str, npc_id: str) -> dict[str, Any]:
        return economy_auctions.negotiate_at_auction(self._economy_dependencies.auctions, game_id, npc_id)

    def choose_auction_identity(self, game_id: str, alias: str) -> dict[str, Any]:
        return economy_auctions.choose_auction_identity(self._economy_dependencies.auctions, game_id, alias)

    def _public_auction(self, game: GameState) -> dict[str, Any]:
        return economy_auctions._public_auction(self._economy_dependencies.auctions, game)

    def buy_black_market_item(self, game_id: str, result_id: str, quantity: int=1) -> dict[str, Any]:
        return economy_black_market.buy_black_market_item(self._economy_dependencies.black_market, game_id, result_id, quantity)

    def sell_black_market_asset(self, game_id: str, kind: str, asset_id: str) -> dict[str, Any]:
        return economy_black_market.sell_black_market_asset(self._economy_dependencies.black_market, game_id, kind, asset_id)

    def leave_black_market(self, game_id: str) -> dict[str, Any]:
        return economy_black_market.leave_black_market(self._economy_dependencies.black_market, game_id)

    @staticmethod
    def _market_tier(player: Player) -> int:
        if player.world in {"celestial", "asura", "nether", "reincarnation"}:
            return max(9, min(12, player.realm_index))
        if player.world in {"spirit", "true_demon", "monster_realm", "phantom_underworld", "hell"}:
            return max(5, min(8, player.realm_index))
        return min(5, max(1, player.realm_index))

    @staticmethod
    def _clear_market(game: GameState) -> None:
        game.market_realm_index = None
        game.market_world = None
        game.market_location_id = None
        game.market_age = None
        game.market_offers = []

    @staticmethod
    def _market_offer_group(offer: dict[str, Any]) -> str:
        if offer.get("kind") == "puppet_material":
            return "puppet"
        return (
            "material"
            if offer.get("kind") in {"crafting_material", "formation_material", "formation_supply"}
            else "general"
        )

    def _ensure_market(self, game: GameState, rng: Any) -> bool:
        return economy_market._ensure_market(self._economy_dependencies.market, game, rng)

    def _refresh_world_market(self, game: GameState, rng: Any) -> bool:
        return economy_market._refresh_world_market(self._economy_dependencies.market, game, rng)

    def _public_market(self, game: GameState) -> dict[str, Any]:
        return economy_market._public_market(self._economy_dependencies.market, game)

    def toggle_market_offer_lock(self, game_id: str, offer_id: str) -> dict[str, Any]:
        return economy_market.toggle_market_offer_lock(self._economy_dependencies.market, game_id, offer_id)

    @staticmethod
    def _spirit_stones(player: Player) -> int:
        return next((int(item.quantity) for item in player.inventory if item.id == "spirit_stone"), 0)

    @staticmethod
    def _catalog_price(kind: str, content_id: str) -> int:
        if content_id == "heroic_progeny_elixir":
            return 985
        prices = sorted(
            int(row["price"]) for row in MARKET_GOODS
            if row["kind"] == kind and row["content_id"] == content_id
        )
        if prices:
            return prices[len(prices) // 2]
        if kind == "technique" and content_id in TECHNIQUE_CATALOG:
            technique = TECHNIQUE_CATALOG[content_id]
            return max(10, round(technique.combat_bonus * 0.35 + technique.grade * 20))
        item = ITEM_CATALOG.get(content_id)
        if item:
            return max(5, round(
                item.combat_bonus * 0.25 + item.hp_bonus * 0.12 + item.mp_bonus * 0.12
                + item.opportunity_bonus * 500 + 5
            ))
        return 5

    def _is_world_market_good(self, world: str, kind: str, content_id: str) -> bool:
        return economy_market._is_world_market_good(self._economy_dependencies.market, world, kind, content_id)

    def _private_trade_attendee(self, game: GameState, npc_id: str) -> dict[str, Any]:
        return economy_private_trade._private_trade_attendee(self._economy_dependencies.private_trade, game, npc_id)

    def buy_private_trade_item(self, game_id: str, npc_id: str, offer_id: str) -> dict[str, Any]:
        return economy_private_trade.buy_private_trade_item(self._economy_dependencies.private_trade, game_id, npc_id, offer_id)

    def sell_private_trade_item(self, game_id: str, npc_id: str, item_id: str) -> dict[str, Any]:
        return economy_private_trade.sell_private_trade_item(self._economy_dependencies.private_trade, game_id, npc_id, item_id)

    def bargain_private_trade(self, game_id: str, npc_id: str, side: str, asset_id: str) -> dict[str, Any]:
        return economy_private_trade.bargain_private_trade(self._economy_dependencies.private_trade, game_id, npc_id, side, asset_id)

    @staticmethod
    def _spirit_field_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS["spirit_field"]

    @staticmethod
    def _rounded_plant_years(years: float) -> int:
        years = max(0.0, float(years))
        if years <= 0:
            return 0
        if years < 10:
            return max(1, int(math.floor(years)))
        magnitude = 10 ** int(math.floor(math.log10(years)))
        unit = max(10, min(10000, magnitude))
        return int(math.floor(years / unit) * unit)

    @staticmethod
    def _plant_quality(years: int, optimal_years: int) -> float:
        if years <= 0 or optimal_years <= 0:
            return 0.0
        distance = abs(math.log10(years / optimal_years))
        return round(max(0.15, 1.0 - distance * 0.45), 4)

    def _plant_item_value(self, item_or_id: Item | str) -> int | None:
        return economy_spirit_fields._plant_item_value(self._economy_dependencies.spirit_fields, item_or_id)

    def _add_harvested_plant(self, player: Player, plant_id: str, actual_years: float) -> Item:
        return economy_spirit_fields._add_harvested_plant(self._economy_dependencies.spirit_fields, player, plant_id, actual_years)

    def _annual_spirit_field_update(self, player: Player) -> None:
        return economy_spirit_fields._annual_spirit_field_update(self._economy_dependencies.spirit_fields, player)

    def _public_spirit_field(self, player: Player) -> dict[str, Any]:
        return economy_spirit_fields._public_spirit_field(self._economy_dependencies.spirit_fields, player)

    def reclaim_spirit_field(self, game_id: str) -> dict[str, Any]:
        return economy_spirit_fields.reclaim_spirit_field(self._economy_dependencies.spirit_fields, game_id)

    def plant_spirit_crop(self, game_id: str, plant_id: str, slot: int | None=None) -> dict[str, Any]:
        return economy_spirit_fields.plant_spirit_crop(self._economy_dependencies.spirit_fields, game_id, plant_id, slot)

    def irrigate_spirit_crop(self, game_id: str, plot_id: str, mp_amount: float=0, booster_id: str='') -> dict[str, Any]:
        return economy_spirit_fields.irrigate_spirit_crop(self._economy_dependencies.spirit_fields, game_id, plot_id, mp_amount, booster_id)

    def harvest_spirit_crop(self, game_id: str, plot_id: str) -> dict[str, Any]:
        return economy_spirit_fields.harvest_spirit_crop(self._economy_dependencies.spirit_fields, game_id, plot_id)

    def use_harvested_plant(self, game_id: str, item_id: str) -> dict[str, Any]:
        return economy_spirit_fields.use_harvested_plant(self._economy_dependencies.spirit_fields, game_id, item_id)

    def sell_spirit_plant(self, game_id: str, item_id: str, *, black_market: bool=False) -> dict[str, Any]:
        return economy_spirit_fields.sell_spirit_plant(self._economy_dependencies.spirit_fields, game_id, item_id, black_market=black_market)

    def _treasure_reward_pool(self, game: GameState, category: str) -> list[dict[str, Any]]:
        return economy_treasure._treasure_reward_pool(self._economy_dependencies.treasure, game, category)

    def _treasure_step(self, game: GameState, rng: Any) -> str:
        return economy_treasure._treasure_step(self._economy_dependencies.treasure, game, rng)

    def _prepare_treasure_reward_event(self, game: GameState, rng: Any) -> dict[str, Any]:
        return economy_treasure._prepare_treasure_reward_event(self._economy_dependencies.treasure, game, rng)

    def _claim_treasure_reward(self, game: GameState, pending: dict[str, Any], category: str) -> tuple[str, str]:
        return economy_treasure._claim_treasure_reward(self._economy_dependencies.treasure, game, pending, category)
