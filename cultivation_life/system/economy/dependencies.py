"""Explicit collaborator contracts for economy domain functions."""
from dataclasses import dataclass
from typing import Any, Callable
from ...ports import MapPort, SavePort


@dataclass(frozen=True, slots=True)
class ArtsDependencies:
    _alchemy_targets: Callable[..., Any]
    _art_names: Callable[..., Any]
    _grant_art_experience: Callable[..., Any]
    _load: Callable[..., Any]
    _public_art_skills: Callable[..., Any]
    _spirit_field_rules: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()

@dataclass(frozen=True, slots=True)
class AuctionsDependencies:
    _all_world_npcs: Callable[..., Any]
    _auction_bid_ceiling: Callable[..., Any]
    _auction_content: Callable[..., Any]
    _auction_good_weight: Callable[..., Any]
    _auction_goods_pool: Callable[..., Any]
    _auction_increment: Callable[..., Any]
    _auction_location_matches: Callable[..., Any]
    _auction_rng: Callable[..., Any]
    _auction_rules: Callable[..., Any]
    _cancel_auction_for_world_change: Callable[..., Any]
    _catalog_price: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _finish_auction: Callable[..., Any]
    _grant_auction_content: Callable[..., Any]
    _is_world_market_good: Callable[..., Any]
    _load: Callable[..., Any]
    _make_auction_lot: Callable[..., Any]
    _make_crafted_auction_lot: Callable[..., Any]
    _npc_realm_name: Callable[..., Any]
    _open_auction: Callable[..., Any]
    _plant_item_value: Callable[..., Any]
    _require_auction_access: Callable[..., Any]
    _sage_affinity_gain: Callable[..., Any]
    _schedule_auction: Callable[..., Any]
    _spirit_field_rules: Callable[..., Any]
    _spirit_stones: Callable[..., Any]
    _tianji_npc_conversation_clue: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()

@dataclass(frozen=True, slots=True)
class BlackMarketDependencies:
    _auction_rules: Callable[..., Any]
    _catalog_price: Callable[..., Any]
    _grant_auction_content: Callable[..., Any]
    _is_world_market_good: Callable[..., Any]
    _load: Callable[..., Any]
    _plant_item_value: Callable[..., Any]
    _require_auction_access: Callable[..., Any]
    _spirit_field_rules: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()

@dataclass(frozen=True, slots=True)
class MarketDependencies:
    _append_crafting_market_offers: Callable[..., Any]
    _append_formation_market_offers: Callable[..., Any]
    _clear_market: Callable[..., Any]
    _crafting_material_defs: Callable[..., Any]
    _formation_maintenance_defs: Callable[..., Any]
    _formation_material_defs: Callable[..., Any]
    _load: Callable[..., Any]
    _market_offer_group: Callable[..., Any]
    _market_tier: Callable[..., Any]
    _plant_item_value: Callable[..., Any]
    _refresh_world_market: Callable[..., Any]
    _spirit_field_rules: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()

@dataclass(frozen=True, slots=True)
class PrivateTradeDependencies:
    _auction_rng: Callable[..., Any]
    _auction_rules: Callable[..., Any]
    _catalog_price: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _grant_auction_content: Callable[..., Any]
    _is_world_market_good: Callable[..., Any]
    _load: Callable[..., Any]
    _plant_item_value: Callable[..., Any]
    _private_trade_attendee: Callable[..., Any]
    _require_auction_access: Callable[..., Any]
    _sage_affinity_gain: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()

@dataclass(frozen=True, slots=True)
class SpiritFieldsDependencies:
    _add_harvested_plant: Callable[..., Any]
    _alchemy_targets: Callable[..., Any]
    _grant_art_experience: Callable[..., Any]
    _load: Callable[..., Any]
    _plant_item_value: Callable[..., Any]
    _plant_quality: Callable[..., Any]
    _public_art_skills: Callable[..., Any]
    _require_auction_access: Callable[..., Any]
    _rounded_plant_years: Callable[..., Any]
    _spirit_field_rules: Callable[..., Any]
    _spirit_stones: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()

@dataclass(frozen=True, slots=True)
class TreasureDependencies:
    _die: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _treasure_reward_pool: Callable[..., Any]
    _get_events_by_id: Callable[[], dict[str, Any]]
    _get_maps: Callable[[], MapPort]

    @property
    def events_by_id(self) -> dict[str, Any]:
        return self._get_events_by_id()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

@dataclass(frozen=True, slots=True)
class EconomyDependencies:
    arts: ArtsDependencies
    auctions: AuctionsDependencies
    black_market: BlackMarketDependencies
    market: MarketDependencies
    private_trade: PrivateTradeDependencies
    spirit_fields: SpiritFieldsDependencies
    treasure: TreasureDependencies
