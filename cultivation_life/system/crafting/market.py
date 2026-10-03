from __future__ import annotations
from typing import Any
from ...models import GameState
from ...content_registry import REALMS
import copy
from ...runtime import decode_rng
from ...runtime import encode_rng
import random
from .dependencies import CraftingMarketDependencies


def _append_crafting_market_offers(
    deps: CraftingMarketDependencies,
    game: GameState,
    rng: random.Random,
    offers: list[dict[str, Any]],
    *,
    tier: int,
    market_name: str,
    location_id: str,
) -> None:
    # New crafting stock must not move the story/combat RNG stream.  Its
    # condition remains deterministic for the same save, place and year.
    rng = random.Random(
        f"{game.seed}:crafting-market:{game.player.world}:{location_id}:{game.player.age}:{tier}"
    )
    definitions = [
        row
        for row in deps._crafting_material_defs().values()
        if str(row.get("world")) == game.player.world
        and int(row.get("tier", 1)) <= max(tier, game.player.realm_index) + 1
    ]
    if not definitions:
        append_tianji = deps._append_tianji_market_offers
        if append_tianji:
            append_tianji(
                game,
                offers,
                tier=tier,
                market_name=market_name,
                location_id=location_id,
            )
        return
    count = min(
        int(deps._crafting_rules().get("market_material_offers", 3)), len(definitions)
    )
    selected = rng.sample(definitions, count)
    for index, definition in enumerate(selected):
        # Keep the public market tier contract (current or rare +1) even in
        # route worlds whose legacy market tier helper still reports five.
        offer_tier = tier + 1 if int(definition.get("tier", tier)) > tier else tier
        instance = deps.make_crafting_material_instance(
            definition,
            rng,
            source=f"{market_name}购得",
            origin_world=game.player.world,
        )
        base_price = int(definition["base_material_value"])
        price = max(1, round(base_price * instance["quality"] * rng.uniform(0.9, 1.1)))
        offers.append(
            {
                "id": f"{game.player.world}-{location_id}-{game.player.age}-{tier}-craft-{index}-{definition['id']}",
                "kind": "crafting_material",
                "content_id": str(definition["id"]),
                "name": str(definition["name"]),
                "description": f"炼器材料 · {instance['state']} · 材料价值 {instance['material_value']:,}；可用位置："
                + "、".join(
                    {"primary": "主材", "secondary": "辅材", "quench": "淬火"}[role]
                    for role in definition.get("roles", [])
                ),
                "price": price,
                "tier": offer_tier,
                "tier_name": REALMS[max(0, min(len(REALMS) - 1, offer_tier))].name,
                "market_name": market_name,
                "world": game.player.world,
                "location_id": location_id,
                "rare_next_tier": offer_tier > tier,
                "sold": False,
                "material_instance": instance,
            }
        )
    append_tianji = deps._append_tianji_market_offers
    if append_tianji:
        append_tianji(
            game,
            offers,
            tier=tier,
            market_name=market_name,
            location_id=location_id,
        )


def _buy_crafting_material_offer(
    deps: CraftingMarketDependencies, game: GameState, offer: dict[str, Any], price: int
) -> str:
    instance = copy.deepcopy(offer.get("material_instance"))
    if not isinstance(instance, dict):
        definition = deps._crafting_material_defs().get(
            str(offer.get("content_id", ""))
        )
        if not definition:
            raise ValueError("这份炼器材料已经失去灵性")
        rng = decode_rng(game.seed, game.rng_state)
        instance = deps.make_crafting_material_instance(
            definition,
            rng,
            source=f"{offer.get('market_name', '坊市')}购得",
            origin_world=game.player.world,
        )
        game.rng_state = encode_rng(rng)
    game.player.crafting_materials.append(instance)
    bought_hook = deps._tianji_material_bought
    if bought_hook:
        bought_hook(game, instance)
    return f"你在{offer['market_name']}支付 {price} 枚灵石，购得{instance['state']}的{instance['name']}。"
