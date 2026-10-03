from __future__ import annotations
from typing import Any
from ...models import GameState
from ...content_registry import REALMS
import copy
import random
from .dependencies import FormationMarketDependencies


def _append_formation_market_offers(
    deps: FormationMarketDependencies,
    game: GameState,
    rng: random.Random,
    offers: list[dict[str, Any]],
    *,
    tier: int,
    market_name: str,
    location_id: str,
) -> None:
    del rng
    definitions = [
        row
        for row in deps._formation_material_defs().values()
        if str(row.get("world")) == game.player.world
        and int(row.get("tier", 1)) <= max(tier, game.player.realm_index) + 1
    ]
    if not definitions:
        return
    local_rng = random.Random(
        f"{game.seed}:formation-market:{game.player.world}:{location_id}:{game.player.age}:{tier}"
    )
    count = min(
        int(deps._formation_rules().get("market_material_offers", 3)), len(definitions)
    )
    for index, definition in enumerate(local_rng.sample(definitions, count)):
        instance = deps.make_formation_material_instance(
            definition,
            source=f"{market_name}购得",
            origin_world=game.player.world,
        )
        price = max(
            1, round(int(definition["base_value"]) * local_rng.uniform(0.92, 1.08))
        )
        offer_tier = min(len(REALMS) - 1, max(tier, int(definition.get("tier", tier))))
        offers.append(
            {
                "id": f"{game.player.world}-{location_id}-{game.player.age}-{tier}-formation-{index}-{definition['id']}",
                "kind": "formation_material",
                "content_id": str(definition["id"]),
                "name": str(definition["name"]),
                "description": f"阵材 · {deps.NATURE_NAMES.get(str(definition['nature']), definition['nature'])}性 · 固有阵值 {float(definition['formation_value']):g}",
                "price": price,
                "tier": offer_tier,
                "tier_name": REALMS[offer_tier].name,
                "market_name": market_name,
                "world": game.player.world,
                "location_id": location_id,
                "rare_next_tier": offer_tier > tier,
                "sold": False,
                "formation_material_instance": instance,
            }
        )
    repairs = [
        row
        for row in deps._formation_maintenance_defs().values()
        if str(row.get("world")) == game.player.world
        and int(row.get("tier", 1)) <= max(tier, game.player.realm_index) + 1
    ]
    repair_count = min(
        int(deps._formation_rules().get("repair_market_offers", 1)), len(repairs)
    )
    for index, definition in enumerate(local_rng.sample(repairs, repair_count)):
        price = max(
            1, round(int(definition["base_value"]) * local_rng.uniform(0.94, 1.06))
        )
        offer_tier = min(len(REALMS) - 1, max(tier, int(definition.get("tier", tier))))
        offers.append(
            {
                "id": f"{game.player.world}-{location_id}-{game.player.age}-{tier}-formation-repair-{index}-{definition['id']}",
                "kind": "formation_supply",
                "content_id": str(definition["id"]),
                "name": str(definition["name"]),
                "description": f"镇地阵修复资源 · 恢复 {float(definition['repair_value']):g}% 永久完整度",
                "price": price,
                "tier": offer_tier,
                "tier_name": REALMS[offer_tier].name,
                "market_name": market_name,
                "world": game.player.world,
                "location_id": location_id,
                "rare_next_tier": False,
                "sold": False,
            }
        )


def _buy_formation_material_offer(
    deps: FormationMarketDependencies,
    game: GameState,
    offer: dict[str, Any],
    price: int,
) -> str:
    instance = copy.deepcopy(offer.get("formation_material_instance"))
    definition = deps._formation_material_defs().get(str(offer.get("content_id", "")))
    if not isinstance(instance, dict) and definition:
        instance = deps.make_formation_material_instance(
            definition,
            source=f"{offer.get('market_name', '坊市')}购得",
            origin_world=game.player.world,
        )
    if not isinstance(instance, dict):
        raise ValueError("这份阵材已经失去阵性")
    game.player.formation_materials.append(instance)
    return (
        f"你在{offer['market_name']}支付 {price} 枚灵石，购得阵材{instance['name']}。"
    )


def _buy_formation_supply_offer(
    deps: FormationMarketDependencies,
    game: GameState,
    offer: dict[str, Any],
    price: int,
) -> str:
    supply_id = str(offer.get("content_id", ""))
    definition = deps._formation_maintenance_defs().get(supply_id)
    if not definition:
        raise ValueError("这份修阵资源已经失效")
    game.player.formation_repair_supplies[supply_id] = (
        int(game.player.formation_repair_supplies.get(supply_id, 0)) + 1
    )
    return f"你在{offer['market_name']}支付 {price} 枚灵石，购得{definition['name']}，可修复镇地阵。"
