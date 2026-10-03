"""Explicit operations for passage."""

from __future__ import annotations

from ...content_registry import WORLD_SYSTEMS
from ...rules import expected_combat_power, has_item, remove_item
from .dependencies import MerchantPassageDependencies


def _merchant_passage(deps: MerchantPassageDependencies, game, alliance, destination):
    member = game.merchant_state["membership"]
    if member["site"] != "hq" or member["rank"] < 1 or deps._merchant_site(game, alliance) != "hq":
        raise ValueError("只有在任总部或分总部使节、特使，可从总部启用逆灵通道")
    if not alliance["cross_world"] or not deps._merchant_route_exists(game, alliance, destination) or destination == game.player.world:
        raise ValueError("商盟没有通往该界面的逆灵通道")
    if not WORLD_SYSTEMS["world_profiles"][destination].get("enabled", True):
        raise ValueError("该界面尚未开放")
    if game.player.cultivation_suppression:
        raise ValueError("请先解除秘法压制")
    price = deps._merchant_passage_cost(game, destination)
    if not has_item(game.player, "spirit_stone", price):
        raise ValueError(f"逆灵通道需支付 {price:,} 灵石")
    target_alliance = deps._merchant_alliance(game, destination, alliance["id"])
    player = game.player
    plan = deps._plan_world_transition(game, destination, "passage",
                                       arrival_location=target_alliance["hq"], reason="商盟逆灵通道")
    deps._apply_world_transition(game, plan)
    remove_item(player, "spirit_stone", price)
    # Credentials remain issued by the original regional HQ. Reciprocal
    # offices recognise the rank, but do not silently transfer local influence.
    deps._merchant_notice(game, f"支付 {price:,} 灵石，乘{alliance['name']}逆灵通道抵达{WORLD_SYSTEMS['world_names'][destination]}。" + ("修为已按当地界面法则压制。" if player.sealed_cultivation else ""))


def _merchant_passage_cost(game, destination):
    tier = WORLD_SYSTEMS["world_profiles"][destination]["tier"]
    original = game.player.sealed_cultivation or {}
    realm = int(original.get("realm_index", game.player.realm_index))
    return max(1000000, round(expected_combat_power(realm, int(original.get("layer", game.player.layer))) * 20)) * int(tier)
