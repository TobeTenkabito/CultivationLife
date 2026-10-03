"""Composition boundary for the economy facade; callbacks resolve on use."""
from .dependencies import (
    ArtsDependencies,
    AuctionsDependencies,
    BlackMarketDependencies,
    MarketDependencies,
    PrivateTradeDependencies,
    SpiritFieldsDependencies,
    TreasureDependencies,
    EconomyDependencies,
)


def bind_arts(host) -> ArtsDependencies:
    return ArtsDependencies(
        _alchemy_targets=lambda *args, **kwargs: host._alchemy_targets(*args, **kwargs),
        _art_names=lambda *args, **kwargs: host._art_names(*args, **kwargs),
        _grant_art_experience=lambda *args, **kwargs: host._grant_art_experience(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _public_art_skills=lambda *args, **kwargs: host._public_art_skills(*args, **kwargs),
        _spirit_field_rules=lambda *args, **kwargs: host._spirit_field_rules(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_auctions(host) -> AuctionsDependencies:
    return AuctionsDependencies(
        _all_world_npcs=lambda *args, **kwargs: host._all_world_npcs(*args, **kwargs),
        _auction_bid_ceiling=lambda *args, **kwargs: host._auction_bid_ceiling(*args, **kwargs),
        _auction_content=lambda *args, **kwargs: host._auction_content(*args, **kwargs),
        _auction_good_weight=lambda *args, **kwargs: host._auction_good_weight(*args, **kwargs),
        _auction_goods_pool=lambda *args, **kwargs: host._auction_goods_pool(*args, **kwargs),
        _auction_increment=lambda *args, **kwargs: host._auction_increment(*args, **kwargs),
        _auction_location_matches=lambda *args, **kwargs: host._auction_location_matches(*args, **kwargs),
        _auction_rng=lambda *args, **kwargs: host._auction_rng(*args, **kwargs),
        _auction_rules=lambda *args, **kwargs: host._auction_rules(*args, **kwargs),
        _cancel_auction_for_world_change=lambda *args, **kwargs: host._cancel_auction_for_world_change(*args, **kwargs),
        _catalog_price=lambda *args, **kwargs: host._catalog_price(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _finish_auction=lambda *args, **kwargs: host._finish_auction(*args, **kwargs),
        _grant_auction_content=lambda *args, **kwargs: host._grant_auction_content(*args, **kwargs),
        _is_world_market_good=lambda *args, **kwargs: host._is_world_market_good(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _make_auction_lot=lambda *args, **kwargs: host._make_auction_lot(*args, **kwargs),
        _make_crafted_auction_lot=lambda *args, **kwargs: host._make_crafted_auction_lot(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: host._npc_realm_name(*args, **kwargs),
        _open_auction=lambda *args, **kwargs: host._open_auction(*args, **kwargs),
        _plant_item_value=lambda *args, **kwargs: host._plant_item_value(*args, **kwargs),
        _require_auction_access=lambda *args, **kwargs: host._require_auction_access(*args, **kwargs),
        _sage_affinity_gain=lambda *args, **kwargs: host._sage_affinity_gain(*args, **kwargs),
        _schedule_auction=lambda *args, **kwargs: host._schedule_auction(*args, **kwargs),
        _spirit_field_rules=lambda *args, **kwargs: host._spirit_field_rules(*args, **kwargs),
        _spirit_stones=lambda *args, **kwargs: host._spirit_stones(*args, **kwargs),
        _tianji_npc_conversation_clue=lambda *args, **kwargs: host._tianji_npc_conversation_clue(*args, **kwargs),
        _get_maps=lambda: host.maps,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_black_market(host) -> BlackMarketDependencies:
    return BlackMarketDependencies(
        _auction_rules=lambda *args, **kwargs: host._auction_rules(*args, **kwargs),
        _catalog_price=lambda *args, **kwargs: host._catalog_price(*args, **kwargs),
        _grant_auction_content=lambda *args, **kwargs: host._grant_auction_content(*args, **kwargs),
        _is_world_market_good=lambda *args, **kwargs: host._is_world_market_good(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _plant_item_value=lambda *args, **kwargs: host._plant_item_value(*args, **kwargs),
        _require_auction_access=lambda *args, **kwargs: host._require_auction_access(*args, **kwargs),
        _spirit_field_rules=lambda *args, **kwargs: host._spirit_field_rules(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_market(host) -> MarketDependencies:
    return MarketDependencies(
        _append_crafting_market_offers=lambda *args, **kwargs: host._append_crafting_market_offers(*args, **kwargs),
        _append_formation_market_offers=lambda *args, **kwargs: host._append_formation_market_offers(*args, **kwargs),
        _clear_market=lambda *args, **kwargs: host._clear_market(*args, **kwargs),
        _crafting_material_defs=lambda *args, **kwargs: host._crafting_material_defs(*args, **kwargs),
        _formation_maintenance_defs=lambda *args, **kwargs: host._formation_maintenance_defs(*args, **kwargs),
        _formation_material_defs=lambda *args, **kwargs: host._formation_material_defs(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _market_offer_group=lambda *args, **kwargs: host._market_offer_group(*args, **kwargs),
        _market_tier=lambda *args, **kwargs: host._market_tier(*args, **kwargs),
        _plant_item_value=lambda *args, **kwargs: host._plant_item_value(*args, **kwargs),
        _refresh_world_market=lambda *args, **kwargs: host._refresh_world_market(*args, **kwargs),
        _spirit_field_rules=lambda *args, **kwargs: host._spirit_field_rules(*args, **kwargs),
        _get_maps=lambda: host.maps,
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_private_trade(host) -> PrivateTradeDependencies:
    return PrivateTradeDependencies(
        _auction_rng=lambda *args, **kwargs: host._auction_rng(*args, **kwargs),
        _auction_rules=lambda *args, **kwargs: host._auction_rules(*args, **kwargs),
        _catalog_price=lambda *args, **kwargs: host._catalog_price(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: host._find_npc(*args, **kwargs),
        _grant_auction_content=lambda *args, **kwargs: host._grant_auction_content(*args, **kwargs),
        _is_world_market_good=lambda *args, **kwargs: host._is_world_market_good(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _plant_item_value=lambda *args, **kwargs: host._plant_item_value(*args, **kwargs),
        _private_trade_attendee=lambda *args, **kwargs: host._private_trade_attendee(*args, **kwargs),
        _require_auction_access=lambda *args, **kwargs: host._require_auction_access(*args, **kwargs),
        _sage_affinity_gain=lambda *args, **kwargs: host._sage_affinity_gain(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_spirit_fields(host) -> SpiritFieldsDependencies:
    return SpiritFieldsDependencies(
        _add_harvested_plant=lambda *args, **kwargs: host._add_harvested_plant(*args, **kwargs),
        _alchemy_targets=lambda *args, **kwargs: host._alchemy_targets(*args, **kwargs),
        _grant_art_experience=lambda *args, **kwargs: host._grant_art_experience(*args, **kwargs),
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        _plant_item_value=lambda *args, **kwargs: host._plant_item_value(*args, **kwargs),
        _plant_quality=lambda *args, **kwargs: host._plant_quality(*args, **kwargs),
        _public_art_skills=lambda *args, **kwargs: host._public_art_skills(*args, **kwargs),
        _require_auction_access=lambda *args, **kwargs: host._require_auction_access(*args, **kwargs),
        _rounded_plant_years=lambda *args, **kwargs: host._rounded_plant_years(*args, **kwargs),
        _spirit_field_rules=lambda *args, **kwargs: host._spirit_field_rules(*args, **kwargs),
        _spirit_stones=lambda *args, **kwargs: host._spirit_stones(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_treasure(host) -> TreasureDependencies:
    return TreasureDependencies(
        _die=lambda *args, **kwargs: host._die(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: host._instantiate_event(*args, **kwargs),
        _treasure_reward_pool=lambda *args, **kwargs: host._treasure_reward_pool(*args, **kwargs),
        _get_events_by_id=lambda: host.events_by_id,
        _get_maps=lambda: host.maps,
    )


def bind_economy(host) -> EconomyDependencies:
    return EconomyDependencies(
        arts=bind_arts(host),
        auctions=bind_auctions(host),
        black_market=bind_black_market(host),
        market=bind_market(host),
        private_trade=bind_private_trade(host),
        spirit_fields=bind_spirit_fields(host),
        treasure=bind_treasure(host),
    )
