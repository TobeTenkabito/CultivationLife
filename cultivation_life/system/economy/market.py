from __future__ import annotations
from ..path_modifiers import adjusted_cost
import copy
from typing import Any
from ...content_registry import ITEM_CATALOG, MARKET_GOODS, MARKET_SETTINGS, REALMS, TECHNIQUE_CATALOG, TECHNIQUE_ELEMENT_NAMES
from ...models import GameState
from ...runtime import now_iso
from ...rules import QI_SOURCE_NAMES, can_player_practice_technique, combat_requirement_display
from .dependencies import MarketDependencies
from ...content_registry import restricted_acquisition


def _ensure_market(deps: MarketDependencies, game: GameState, rng: Any) -> bool:
    from cultivation_life.system.world_transition_system import finish_world_transition
    return finish_world_transition(game, rng, deps._refresh_world_market)


def _refresh_world_market(deps: MarketDependencies, game: GameState, rng: Any) -> bool:
    player = game.player
    if player.world in {"lost", "rift"}:
        changed = bool(game.market_offers or game.market_world)
        deps._clear_market(game)
        return changed
    # Drop stale/locked offers from saves made before source restrictions.
    previous_count = len(game.market_offers)
    repriced = False
    from ...talisman_content import local_catalog
    definitions = local_catalog(game)[0]
    for offer in game.market_offers:
        if offer.get('kind') == 'talisman_material' and offer.get('pricing_version', 1) < 2:
            material = definitions.get(offer.get('content_id'))
            if material:
                offer.update(price=material['base_value'], pricing_version=2)
                repriced = True
    game.market_offers[:] = [row for row in game.market_offers if not restricted_acquisition(
        str(row.get("kind", "")), str(row.get("content_id", "")))]
    if player.realm_index == 0:
        changed = bool(
            game.market_offers or game.market_realm_index is not None
            or game.market_world is not None or game.market_location_id is not None
        )
        deps._clear_market(game)
        return changed
    tier = deps._market_tier(player)
    location_id = deps.maps.normalize_location(player.world, player.location_id)
    current_material_offers = [
        row for row in game.market_offers if deps._market_offer_group(row) == "material"
    ]
    if (
        game.market_realm_index == tier and game.market_world == player.world
        and game.market_location_id == location_id
        and game.market_age == player.age and game.market_offers
        and (
            not current_material_offers
            or len(current_material_offers) == int(MARKET_SETTINGS.get("material_offer_count", 6))
        )
    ):
        if not any(row.get("kind") == "puppet_material" for row in game.market_offers):
            from cultivation_life.system.puppet_crafting import market_offers
            game.market_offers.extend(market_offers(game, tier, "傀儡材料坊市", location_id))
        if not any(row.get("kind") == "talisman_material" for row in game.market_offers):
            from ..talismans import market_offers as talisman_offers
            game.market_offers.extend(talisman_offers(game, tier, "符材坊市", location_id))
        return repriced or len(game.market_offers) != previous_count
    same_market = (
        game.market_realm_index == tier and game.market_world == player.world
        and game.market_location_id == location_id
    )
    retained: list[dict[str, Any]] = []
    retained_groups: set[str] = set()
    if same_market:
        # Lock state lives on the existing offer row.  This keeps old saves
        # compatible while allowing exactly one retained item per shelf.
        for old_offer in game.market_offers:
            group = deps._market_offer_group(old_offer)
            if (
                bool(old_offer.get("locked")) and not bool(old_offer.get("sold"))
                and group not in retained_groups
            ):
                retained.append(copy.deepcopy(old_offer) | {"locked": True})
                retained_groups.add(group)
    location_name = deps.maps.location(player.world, location_id)["name"]
    market_name = f"{location_name}·{REALMS[tier].name}坊市"
    world_goods = deps.maps.localize_goods(MARKET_GOODS, player.world, location_id, "market")
    general_locked = [row for row in retained if deps._market_offer_group(row) == "general"]
    material_locked = [row for row in retained if deps._market_offer_group(row) == "material"]
    offers: list[dict[str, Any]] = list(general_locked)
    general_count = int(MARKET_SETTINGS["offer_count"])
    fresh_general_count = max(0, general_count - len(general_locked))
    retained_content_ids = {str(row.get("content_id", "")) for row in retained}
    for index in range(fresh_general_count):
        seed_pool = [
            entry for entry in world_goods
            if entry["kind"] == "item" and "seed" in ITEM_CATALOG[entry["content_id"]].tags
            and str(entry["content_id"]) not in retained_content_ids
        ]
        if index == 0 and seed_pool:
            good = rng.choice(seed_pool)
            offer_tier = tier
            rare_next_tier = False
            price = max(1, round(good["price"] * rng.uniform(*MARKET_SETTINGS["price_multiplier"])))
            content = ITEM_CATALOG[good["content_id"]]
            offers.append({
                "id":f"{player.world}-{location_id}-{player.age}-{tier}-{index}-{good['content_id']}",
                "kind":"item", "content_id":good["content_id"], "name":content.name,
                "description":content.description, "element":None, "price":price, "tier":offer_tier,
                "tier_name":REALMS[offer_tier].name, "market_name":market_name,
                "world":player.world, "location_id":location_id,
                "rare_next_tier":False, "sold":False, "locked":False,
            })
            continue
        else:
            tier_cap = 12 if player.world in {"celestial", "asura", "nether", "reincarnation"} else 5 if player.world in {"human", "demon"} else 8
            rare_next_tier = tier < tier_cap and rng.random() < float(MARKET_SETTINGS["next_tier_chance"])
            offer_tier = tier + 1 if rare_next_tier else tier
            pool = [
                entry for entry in world_goods
                if entry["tier"] == offer_tier
                and str(entry["content_id"]) not in retained_content_ids
            ]
            if not pool:
                pool = [
                    entry for entry in world_goods
                    if entry["tier"] == tier
                    and str(entry["content_id"]) not in retained_content_ids
                ]
                offer_tier = tier
                rare_next_tier = False
            if not pool:
                break
            good = rng.choice(pool)
        price = max(1, round(good["price"] * rng.uniform(*MARKET_SETTINGS["price_multiplier"])))
        if good["kind"] == "item":
            content = ITEM_CATALOG[good["content_id"]]
            name, description, element = content.name, content.description, None
        else:
            content = TECHNIQUE_CATALOG[good["content_id"]]
            name = content.name
            source_display = "、".join(
                QI_SOURCE_NAMES[source] + (f" {weight:.0%}" if len(content.sources) > 1 else "")
                for source, weight in content.sources.items()
            )
            description = (
                f"{source_display} · 战斗门槛 {combat_requirement_display(content.combat_requirements)}；"
                f"{TECHNIQUE_ELEMENT_NAMES[content.element]}功法；机缘 +{content.opportunity_bonus:.0%}，"
                f"HP +{content.hp_bonus:.0%}，MP +{content.mp_bonus:.0%}，战力 +{content.combat_bonus:.0f}。"
            )
            if content.category == "transformation":
                description += (
                    f" 变身容量 {content.transformation_capacity}，"
                    f"同时启用 {content.transformation_space} 个形态。"
                )
            element = content.element
        offers.append({
            "id":f"{player.world}-{location_id}-{player.age}-{tier}-{index}-{good['content_id']}",
            "kind":good["kind"], "content_id":good["content_id"], "name":name,
            "description":description, "element":element, "price":price, "tier":offer_tier,
            "tier_name":REALMS[offer_tier].name, "market_name":market_name,
            "world":player.world, "location_id":location_id,
            "rare_next_tier":rare_next_tier, "sold":False, "locked":False,
        })
    material_candidates: list[dict[str, Any]] = []
    deps._append_crafting_market_offers(
        game, rng, material_candidates, tier=tier, market_name=market_name, location_id=location_id,
    )
    deps._append_formation_market_offers(
        game, rng, material_candidates, tier=tier, market_name=market_name, location_id=location_id,
    )
    for offer in material_candidates:
        offer["locked"] = False
    material_count = int(MARKET_SETTINGS.get("material_offer_count", 6))
    fresh_material_count = max(0, material_count - len(material_locked))
    locked_is_crafting = bool(material_locked and material_locked[0].get("kind") == "crafting_material")
    crafting_target = max(0, 3 - int(locked_is_crafting))
    formation_target = max(0, fresh_material_count - crafting_target)
    crafting_pool = [row for row in material_candidates if row.get("kind") == "crafting_material"]
    formation_materials = [row for row in material_candidates if row.get("kind") == "formation_material"]
    formation_supplies = [row for row in material_candidates if row.get("kind") == "formation_supply"]
    selected_materials = crafting_pool[:crafting_target]
    supply_count = min(1, formation_target, len(formation_supplies))
    selected_materials.extend(formation_materials[:max(0, formation_target - supply_count)])
    selected_materials.extend(formation_supplies[:supply_count])
    if len(selected_materials) < fresh_material_count:
        selected_ids = {row["id"] for row in selected_materials}
        selected_materials.extend(
            row for row in material_candidates
            if row["id"] not in selected_ids
        )
    offers.extend(material_locked)
    offers.extend(selected_materials[:fresh_material_count])
    from cultivation_life.system.puppet_crafting import market_offers
    offers.extend(market_offers(game, tier, market_name, location_id))
    from ..talismans import market_offers as talisman_offers
    offers.extend(talisman_offers(game, tier, market_name, location_id))
    game.market_realm_index = tier
    game.market_world = player.world
    game.market_location_id = location_id
    game.market_age = player.age
    game.market_offers = offers
    return True


def _public_market(deps: MarketDependencies, game: GameState) -> dict[str, Any]:
    player = game.player
    stones = next((item.quantity for item in player.inventory if item.id == "spirit_stone"), 0)
    if player.realm_index == 0:
        return {"available":False, "spirit_stones":stones, "offers":[]}
    location_id = deps.maps.normalize_location(player.world, player.location_id)
    offers = []
    crafting_offers = []
    formation_offers = []
    puppet_offers = []
    talisman_offers = []
    for offer in game.market_offers:
        if offer.get("world", "human") != player.world or offer.get("location_id", location_id) != location_id:
            continue
        shown = dict(offer)
        shown["locked"] = bool(offer.get("locked", False))
        shown["base_price"] = offer["price"]
        shown["price"] = adjusted_cost(game, offer["price"], "market")
        shown["affordable"] = stones >= shown["price"]
        shown["market_group"] = deps._market_offer_group(offer)
        shown["known"] = bool(
            offer["kind"] == "technique"
            and any(entry.id == offer["content_id"] for entry in player.known_techniques)
        )
        # Known techniques remain purchasable: every later copy becomes a
        # stackable inheritance manual used by the explicit upgrade action.
        shown["owned"] = False
        shown["compatible"] = (
            offer["kind"] != "technique"
            or can_player_practice_technique(player, TECHNIQUE_CATALOG[offer["content_id"]].element)
        )
        if offer.get("kind") == "talisman_material":
            talisman_offers.append(shown)
        elif offer.get("kind") == "puppet_material":
            puppet_offers.append(shown)
        elif offer.get("kind") == "crafting_material":
            crafting_offers.append(shown)
        elif offer.get("kind") in {"formation_material", "formation_supply"}:
            formation_offers.append(shown)
        else:
            offers.append(shown)
    location_name = deps.maps.location(player.world, location_id)["name"]
    from ..talismans import sale_rows
    return {
        "available":True, "name":f"{location_name}·{REALMS[deps._market_tier(player)].name}坊市",
        "realm_index":deps._market_tier(player), "world":player.world,
        "location_id":location_id, "location_name":location_name,
        "spirit_stones":stones, "offers":offers, "crafting_material_offers":crafting_offers,
        "formation_material_offers":formation_offers,
        "puppet_material_offers":puppet_offers,
        "talisman_material_offers":talisman_offers,
        "sellable_talismans":sale_rows(player),
        "material_offers":[*crafting_offers, *formation_offers],
        "general_offer_limit":int(MARKET_SETTINGS["offer_count"]),
        "material_offer_limit":int(MARKET_SETTINGS.get("material_offer_count", 6)),
        "sellable_plants":[
            {"id":item.id, "name":item.name, "quantity":item.quantity,
             "price":max(1, round(int(deps._plant_item_value(item) or 0) * float(deps._spirit_field_rules()["market_sell_ratio"]))) }
            for item in player.inventory if deps._plant_item_value(item) is not None and item.quantity > 0
        ],
        "next_tier_chance":float(MARKET_SETTINGS["next_tier_chance"]),
    }


def toggle_market_offer_lock(deps: MarketDependencies, game_id: str, offer_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    if game.pending_event or not game.player.alive or game.player.imprisonment:
        raise ValueError("当前状态无法锁定坊市货物")
    location_id = deps.maps.normalize_location(game.player.world, game.player.location_id)
    offer = next((entry for entry in game.market_offers if entry.get("id") == offer_id), None)
    if (
        not offer or offer.get("sold") or offer.get("world", "human") != game.player.world
        or offer.get("location_id", location_id) != location_id
    ):
        raise ValueError("该货物已经售出或不在当前坊市")
    group = deps._market_offer_group(offer)
    locking = not bool(offer.get("locked"))
    if locking:
        for row in game.market_offers:
            if deps._market_offer_group(row) == group:
                row["locked"] = False
    offer["locked"] = locking
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _is_world_market_good(deps: MarketDependencies, world: str, kind: str, content_id: str) -> bool:
    if restricted_acquisition(kind, content_id):
        return False
    if any(
        str(row.get("world", "human")) == world
        and str(row.get("kind")) == kind
        and str(row.get("content_id")) == content_id
        for row in MARKET_GOODS
    ):
        return True
    if kind == "puppet_material":
        from cultivation_life.puppet_content import definitions
        return definitions().get(content_id, {}).get("world") == world
    if kind in {"talisman_material", "talisman"}:
        from ...talisman_content import catalog
        return catalog()[0 if kind == 'talisman_material' else 1].get(content_id, {}).get("world") == world
    if kind == "crafting_material":
        return any(
            str(row.get("world")) == world and str(row.get("id")) == content_id
            for row in deps._crafting_material_defs().values()
        )
    if kind == "formation_material":
        return any(
            str(row.get("world")) == world and str(row.get("id")) == content_id
            for row in deps._formation_material_defs().values()
        )
    if kind == "formation_supply":
        return any(
            str(row.get("world")) == world and str(row.get("id")) == content_id
            for row in deps._formation_maintenance_defs().values()
        )
    return False
