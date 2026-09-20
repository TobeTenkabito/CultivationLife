from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, ClassVar

from .character import IDENTITY, LIFE
from .assets import create_asset
from .cultivation import CULTIVATION, PRACTICE, _can_practice
from .definitions import GameDefinitions, MarketGoodDefinition
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


INVENTORY = "economy.inventory"
MARKET = "economy.market"
CURRENCY_ID = "spirit_stone"


@dataclass(frozen=True, slots=True)
class GrantItem:
    actor_id: str
    item_id: str
    quantity: int = 1
    reason: str = "reward"


@dataclass(frozen=True, slots=True)
class RefreshMarket:
    actor_id: str
    force: bool = False


@dataclass(frozen=True, slots=True)
class ToggleMarketOfferLock:
    actor_id: str
    offer_id: str


@dataclass(frozen=True, slots=True)
class BuyMarketOffer:
    actor_id: str
    offer_id: str


@dataclass(frozen=True, slots=True)
class UseItem:
    actor_id: str
    item_id: str
    allow_during_interaction: ClassVar[bool] = True


def _inventory(state: WorldState, actor_id: str) -> dict[str, Any]:
    return state.entities.require(actor_id, INVENTORY)


def _quantity(inventory: dict[str, Any], item_id: str, *, spendable: bool = False) -> int:
    owned = int(dict(inventory.get("items", {})).get(item_id, 0))
    if not spendable:
        return owned
    reserved = int(dict(inventory.get("reserved", {})).get(item_id, 0))
    return owned - reserved


def inventory_quantity(
    state: WorldState, actor_id: str, item_id: str, *, spendable: bool = False,
) -> int:
    return _quantity(_inventory(state, actor_id), item_id, spendable=spendable)


def _change_item(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    item_id: str,
    quantity: int,
    reason: str,
) -> None:
    if item_id not in definitions.items:
        raise ValueError("未知物品")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity == 0:
        raise ValueError("物品数量必须是非零整数")
    inventory = _inventory(context.state, actor_id)
    items = dict(inventory.get("items", {}))
    before = int(items.get(item_id, 0))
    after = before + quantity
    if after < int(dict(inventory.get("reserved", {})).get(item_id, 0)):
        raise ValueError("可用物品数量不足")
    if after:
        items[item_id] = after
    else:
        items.pop(item_id, None)
    inventory["items"] = items
    context.state.entities.put(actor_id, INVENTORY, inventory)
    context.emit(
        "economy.inventory.changed",
        source="economy",
        scope=EventScope.entity(actor_id),
        payload={
            "entity_id": actor_id,
            "item_id": item_id,
            "before": before,
            "after": after,
            "quantity": quantity,
            "reason": reason,
        },
    )


def change_inventory_item(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    item_id: str,
    quantity: int,
    reason: str,
) -> None:
    _change_item(context, definitions, actor_id, item_id, quantity, reason)


def _on_character_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        entity_id = str(event.payload["entity_id"])
        # V1 gives the controlled character one starter spirit sword.  Keeping
        # the grant here preserves a single owner for inventory state.
        controlled = bool(event.payload.get("controlled"))
        starting_items = {"spirit_sword": 1} if controlled else {}
        context.state.entities.put(
            entity_id,
            INVENTORY,
            {"items": starting_items, "reserved": {}},
        )
        context.state.entities.put(
            entity_id, MARKET, {"revision": 0, "offers": []}
        )
        # The V1 screen opens directly onto a populated market.  Initialising
        # it in the economy transaction also ensures every displayed offer is
        # immediately actionable by its persisted ID.
        if controlled:
            cultivation = context.state.entities.require(entity_id, CULTIVATION)
            location = context.state.entities.require(entity_id, LOCATION)
            world_id = str(location["world_id"])
            if (
                _market_tier(definitions, cultivation, world_id) > 0
                and any(good.world_id == world_id for good in definitions.market_goods)
            ):
                _refresh_market_handler(definitions)(
                    context, RefreshMarket(entity_id, force=True)
                )

    return handler


def _on_story_inventory_changed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        _change_item(
            context,
            definitions,
            str(event.payload["entity_id"]),
            str(event.payload["item_id"]),
            int(event.payload["quantity"]),
            str(event.payload.get("reason", "story")),
        )

    return handler


def _on_inventory_consume_requested(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        quantity = int(event.payload["quantity"])
        if quantity <= 0:
            raise ValueError("消耗数量必须为正数")
        _change_item(
            context,
            definitions,
            str(event.payload["entity_id"]),
            str(event.payload["item_id"]),
            -quantity,
            str(event.payload.get("reason", "consume")),
        )

    return handler


def _on_permanent_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    inventory = context.state.entities.require(actor_id, INVENTORY)
    released = dict(inventory.get("reserved", {}))
    inventory["reserved"] = {}
    context.state.entities.put(actor_id, INVENTORY, inventory)
    market = context.state.entities.require(actor_id, MARKET)
    market.update({"offers": [], "world_id": None, "location_id": None})
    context.state.entities.put(actor_id, MARKET, market)
    context.emit(
        "world.transition.acknowledged",
        source="economy",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": event.payload["transaction_id"],
            "actor_id": actor_id, "domain": "economy", "released": released,
        },
    )


def _on_temporary_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    inventory = context.state.entities.require(actor_id, INVENTORY)
    inventory["reserved"] = {}
    context.state.entities.put(actor_id, INVENTORY, inventory)
    market = context.state.entities.require(actor_id, MARKET)
    market.update({"offers": [], "world_id": None, "location_id": None})
    context.state.entities.put(actor_id, MARKET, market)


def _grant_item_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, GrantItem):
            raise TypeError("命令类型错误")
        if not context.state.entities.exists(command.actor_id):
            raise ValueError("角色不存在")
        _change_item(
            context, definitions, command.actor_id, command.item_id,
            command.quantity, command.reason,
        )

    return handler


def _use_item_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, UseItem):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能为当前角色使用物品")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("死亡角色不能使用物品")
        item = definitions.items.get(command.item_id)
        if item is None or inventory_quantity(
            context.state, command.actor_id, command.item_id, spendable=True
        ) < 1:
            raise ValueError("物品不存在")
        story = context.state.entities.get(command.actor_id, "story.state") or {}
        pending = story.get("pending")
        trial = context.state.entities.get(command.actor_id, "cultivation.trial") or {}
        active_trial = trial.get("active")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        result = ""
        if pending is not None:
            if (
                not isinstance(active_trial, dict)
                or (item.trial_restore_hp <= 0 and item.trial_restore_mp <= 0)
            ):
                raise ValueError("当前事件中只能使用渡劫恢复道具")
            change_inventory_item(
                context, definitions, command.actor_id, command.item_id, -1,
                "trial_recovery",
            )
            if item.trial_restore_hp:
                context.emit(
                    "story.effect.combat_condition.changed",
                    source="economy",
                    scope=EventScope.entity(command.actor_id),
                    payload={
                        "entity_id": command.actor_id, "kind": "restore_hp",
                        "amount": item.trial_restore_hp, "reason": "trial_recovery",
                    },
                )
            if item.trial_restore_mp:
                context.emit(
                    "story.effect.combat_condition.changed",
                    source="economy",
                    scope=EventScope.entity(command.actor_id),
                    payload={
                        "entity_id": command.actor_id, "kind": "restore_mp",
                        "amount": item.trial_restore_mp, "reason": "trial_recovery",
                    },
                )
            result = "trial_recovery"
        elif command.item_id == "healing_pill":
            change_inventory_item(
                context, definitions, command.actor_id, command.item_id, -1, "healing"
            )
            context.emit(
                "story.effect.combat_condition.changed",
                source="economy",
                scope=EventScope.entity(command.actor_id),
                payload={
                    "entity_id": command.actor_id, "kind": "restore_hp",
                    "amount": 0.35, "reason": "healing_pill",
                },
            )
            result = "healed"
        elif item.breakthrough_bonus > 0 and item.breakthrough_scope:
            if cultivation["path"] == "ghost":
                raise ValueError("阴魂不受血肉丹火重塑，此物无法助你破境")
            if cultivation["path"] == "demonic":
                raise ValueError("魔修不能依靠突破丹药提高自身突破率")
            scope, source = item.breakthrough_scope.split(":", 1)
            realm_index = definitions.realm_index(str(cultivation["realm_id"]))
            if cultivation["path"] == "monster" and scope == "major":
                raise ValueError("妖修大境界由血脉条件与生命经历决定")
            if cultivation.get("bottleneck") not in {"major", "minor"}:
                raise ValueError("尚未抵达可服用突破丹药的瓶颈")
            expected = "major" if cultivation.get("bottleneck") == "major" else "minor"
            if int(source) != realm_index or scope != expected:
                raise ValueError("这枚丹药不适用于当前突破瓶颈")
            aids = list(map(str, cultivation.get("active_breakthrough_aids", [])))
            if command.item_id in aids:
                raise ValueError("本次冲关已经服用过同一种丹药")
            change_inventory_item(
                context, definitions, command.actor_id, command.item_id, -1,
                "breakthrough_aid",
            )
            aids.append(command.item_id)
            cultivation["active_breakthrough_aids"] = aids
            context.state.entities.put(command.actor_id, CULTIVATION, cultivation)
            result = "breakthrough_aid"
        elif item.root_grant:
            location = context.state.entities.require(command.actor_id, LOCATION)
            realm_index = definitions.realm_index(str(cultivation["realm_id"]))
            prefix = command.item_id.split("_", 1)[0]
            requirements = {
                "zique": ("spirit", 5), "moque": ("true_demon", 5),
                "yaoque": ("monster_realm", 5), "mingque": ("hell", 5),
            }
            if prefix in requirements:
                world_id, minimum = requirements[prefix]
                valid_world = location["world_id"] == world_id or (
                    prefix == "yaoque" and location["world_id"] == "phantom_underworld"
                )
                if not valid_world or realm_index < minimum:
                    raise ValueError("当前界面或境界不足以参悟此法门")
            elif prefix == "jinque" and realm_index < 4:
                raise ValueError("当前境界不足以参悟此法门")
            roots = list(map(str, cultivation.get("additional_roots", [])))
            base_elements = definitions.roots[str(cultivation["spirit_root"])].elements
            if item.root_grant in roots or item.root_grant in base_elements:
                raise ValueError("你已经拥有对应灵根")
            change_inventory_item(
                context, definitions, command.actor_id, command.item_id, -1,
                "root_manual",
            )
            roots.append(item.root_grant)
            cultivation["additional_roots"] = roots
            context.state.entities.put(command.actor_id, CULTIVATION, cultivation)
            result = "root_added"
        elif item.permanent_intrinsic_hp_bonus > 0 or item.permanent_intrinsic_mp_bonus > 0:
            change_inventory_item(
                context, definitions, command.actor_id, command.item_id, -1,
                "intrinsic_growth",
            )
            cultivation["intrinsic_hp_bonus"] = float(
                cultivation.get("intrinsic_hp_bonus", 0)
            ) + item.permanent_intrinsic_hp_bonus
            cultivation["intrinsic_mp_bonus"] = float(
                cultivation.get("intrinsic_mp_bonus", 0)
            ) + item.permanent_intrinsic_mp_bonus
            context.state.entities.put(command.actor_id, CULTIVATION, cultivation)
            result = "intrinsic_growth"
        elif item.conception_bonus > 0:
            change_inventory_item(
                context, definitions, command.actor_id, command.item_id, -1,
                "conception_aid",
            )
            context.emit(
                "family.conception_bonus.granted",
                source="economy",
                scope=EventScope.entity(command.actor_id),
                payload={
                    "entity_id": command.actor_id,
                    "item_id": command.item_id,
                    "bonus": item.conception_bonus,
                },
            )
            result = "conception_aid"
        else:
            raise ValueError("该物品当前不能使用")
        context.emit(
            "economy.item.used",
            source="economy",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "item_id": command.item_id,
                "result": result,
            },
        )

    return handler


def _market_tier(definitions: GameDefinitions, cultivation: dict[str, Any], world_id: str) -> int:
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    if realm_index == 0:
        return 0
    if world_id in {"celestial", "asura", "nether"}:
        return max(9, min(12, realm_index))
    if world_id in {"spirit", "true_demon", "monster_realm", "phantom_underworld", "hell"}:
        return max(5, min(8, realm_index))
    return min(5, max(1, realm_index))


def _offer_group(offer: dict[str, Any]) -> str:
    return "general" if offer.get("group", "general") == "general" else "material"


def regional_market_goods(
    definitions: GameDefinitions,
    goods: list[MarketGoodDefinition],
    world_id: str,
    location_id: str,
    purpose: str,
) -> list[MarketGoodDefinition]:
    """Apply the stable V1 region/purpose partition without changing content."""
    coverage = float(
        definitions.systems.get("maps", {})
        .get("settings", {})
        .get("regional_coverage", 0.46)
    )
    groups: dict[tuple[int, str], list[MarketGoodDefinition]] = {}
    for good in goods:
        if good.world_id == world_id:
            groups.setdefault((good.tier, good.kind), []).append(good)
    result: list[MarketGoodDefinition] = []
    for rows in groups.values():
        ranked = sorted(
            rows,
            key=lambda good: _regional_score(
                world_id, location_id, purpose, good.content_id
            ),
        )
        selected = [
            good for good in ranked
            if _regional_score(
                world_id, location_id, purpose, good.content_id
            ) < coverage
        ]
        result.extend(selected or ranked[:1])
    return result


def _regional_score(
    world_id: str, location_id: str, purpose: str, content_id: str,
) -> float:
    digest = hashlib.blake2b(
        f"{world_id}:{location_id}:{purpose}:{content_id}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big") / float(2**64 - 1)


def _on_action_completed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload.get("actor_id", ""))
        if actor_id != context.state.controlled_entity_id:
            return
        if not context.state.entities.exists(actor_id):
            return
        if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
            return
        cultivation = context.state.entities.require(actor_id, CULTIVATION)
        location = context.state.entities.require(actor_id, LOCATION)
        world_id = str(location["world_id"])
        if (
            _market_tier(definitions, cultivation, world_id) == 0
            or not any(
                good.world_id == world_id for good in definitions.market_goods
            )
        ):
            return
        # A V1 market period is an action unit, not a calendar year.  Every
        # completed timed action therefore rerolls both shelves while the one
        # lock allowed on each shelf survives with its original instance data.
        _refresh_market_handler(definitions)(
            context, RefreshMarket(actor_id=actor_id, force=True)
        )

    return handler


def _eligible_goods(
    definitions: GameDefinitions, world_id: str, tier: int,
) -> list[MarketGoodDefinition]:
    return _eligible_goods_from(list(definitions.market_goods), world_id, tier)


def _eligible_goods_from(
    goods: list[MarketGoodDefinition], world_id: str, tier: int,
) -> list[MarketGoodDefinition]:
    exact = [
        good for good in goods
        if good.world_id == world_id and good.tier == tier
    ]
    if exact:
        return exact
    available_tiers = [
        good.tier for good in goods
        if good.world_id == world_id and good.tier <= tier
    ]
    if not available_tiers:
        return []
    fallback = max(available_tiers)
    return [
        good for good in goods
        if good.world_id == world_id and good.tier == fallback
    ]


def _refresh_market_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RefreshMarket):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能刷新当前角色所在坊市")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("死亡角色无法进入坊市")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        location = context.state.entities.require(command.actor_id, LOCATION)
        world_id = str(location["world_id"])
        location_id = str(location["location_id"])
        tier = _market_tier(definitions, cultivation, world_id)
        if tier == 0:
            raise ValueError("凡人无法进入修仙坊市")
        market = context.state.entities.require(command.actor_id, MARKET)
        same_period = (
            market.get("world_id") == world_id
            and market.get("location_id") == location_id
            and int(market.get("generated_year", -1)) == context.state.clock.year
        )
        if same_period and market.get("offers") and not command.force:
            return
        revision = int(market.get("revision", 0)) + 1
        market_rng = random.Random(
            f"{context.state.seed}:general-market:{command.actor_id}:{world_id}:"
            f"{location_id}:{context.state.clock.year}:{revision}"
        )
        retained: list[dict[str, Any]] = []
        if market.get("world_id") == world_id and market.get("location_id") == location_id:
            groups: set[str] = set()
            for old in market.get("offers", []):
                group = _offer_group(old)
                if bool(old.get("locked")) and not bool(old.get("sold")) and group not in groups:
                    retained.append(dict(old))
                    groups.add(group)
        regional_goods = regional_market_goods(
            definitions,
            list(definitions.market_goods),
            world_id,
            location_id,
            "market",
        )
        pool = _eligible_goods_from(regional_goods, world_id, tier)
        if not pool and retained:
            pool = []
        elif not pool:
            raise ValueError("当前世界没有可用坊市货物")
        offer_limit = max(1, int(definitions.market_settings.get("offer_count", 6)))
        retained_general = [
            row for row in retained if _offer_group(row) == "general"
        ]
        retained_material = [
            row for row in retained if _offer_group(row) == "material"
        ]
        fresh_count = max(0, offer_limit - len(retained_general))
        retained_keys = {
            (str(row.get("kind")), str(row.get("content_id")))
            for row in retained_general
        }
        candidates = [
            good for good in pool
            if (good.kind, good.content_id) not in retained_keys
        ]
        market_rng.shuffle(candidates)
        next_tier_pool = [
            good for good in regional_goods
            if good.world_id == world_id and good.tier == tier + 1
        ]
        market_rng.shuffle(next_tier_pool)
        next_tier_chance = float(
            definitions.market_settings.get("next_tier_chance", 0.0)
        )
        selected: list[tuple[MarketGoodDefinition, int]] = []
        # V1 reserves the first newly generated general slot for a locally
        # available spirit-plant seed.  Without this guarantee the spirit
        # field UI can be fully implemented yet become unreachable in normal
        # play because no seed ever enters the economy.
        seed_pool = [
            good for good in regional_goods
            if good.kind == "item"
            and good.content_id in definitions.items
            and "seed" in definitions.items[good.content_id].tags
            and (good.kind, good.content_id) not in retained_keys
        ]
        if fresh_count and seed_pool:
            seed_good = market_rng.choice(seed_pool)
            selected.append((seed_good, tier))
            candidates = [
                good for good in candidates
                if (good.kind, good.content_id)
                != (seed_good.kind, seed_good.content_id)
            ]
            next_tier_pool = [
                good for good in next_tier_pool
                if (good.kind, good.content_id)
                != (seed_good.kind, seed_good.content_id)
            ]
        for _index in range(len(selected), fresh_count):
            use_next = bool(
                next_tier_pool and market_rng.random() < next_tier_chance
            )
            source = next_tier_pool if use_next else candidates
            fallback = candidates if use_next else next_tier_pool
            if source:
                good = source.pop(0)
                selected.append((good, good.tier))
            elif fallback:
                good = fallback.pop(0)
                selected.append((good, good.tier))
            elif pool:
                good = market_rng.choice(pool)
                selected.append((good, good.tier))
        low, high = map(float, definitions.market_settings.get("price_multiplier", (0.9, 1.1)))
        offers = list(retained_general)
        for index, (good, offer_tier) in enumerate(selected):
            content = (
                definitions.items[good.content_id]
                if good.kind == "item" else definitions.techniques[good.content_id]
            )
            offers.append({
                "id": f"market:{command.actor_id}:{revision}:{index + 1}",
                "kind": good.kind,
                "content_id": good.content_id,
                "name": content.name,
                "price": max(1, round(good.price * market_rng.uniform(low, high))),
                "tier": offer_tier,
                "group": "general",
                "locked": False,
                "sold": False,
            })
        specialty_rng = random.Random(
            f"{context.state.seed}:specialty-market:{world_id}:{location_id}:"
            f"{context.state.clock.year}:{revision}"
        )
        crafting = definitions.systems["crafting"]
        crafting_pool = [
            dict(row) for row in crafting["materials"]
            if row.get("world") == world_id and int(row.get("tier", 1)) <= tier + 1
        ]
        specialty_rng.shuffle(crafting_pool)
        for index, definition in enumerate(crafting_pool[:int(crafting["settings"].get("market_material_offers", 3))]):
            quality = max(0.65, min(1.25, specialty_rng.triangular(0.65, 1.25, 1.0)))
            value = max(1, round(int(definition["base_material_value"]) * quality))
            offers.append({
                "id": f"market:{command.actor_id}:{revision}:crafting:{index + 1}",
                "kind": "crafting_material", "content_id": definition["id"],
                "name": definition["name"], "group": "crafting",
                "tier": min(len(definitions.realms) - 1, max(tier, int(definition["tier"]))),
                "price": max(1, round(value * specialty_rng.uniform(0.9, 1.1))),
                "asset_blueprint": {
                    "kind": "crafting_material", "definition_id": definition["id"],
                    "name": definition["name"],
                    "metadata": {
                        "tier": definition["tier"], "world_id": world_id,
                        "quality_multiplier": round(quality, 4), "material_value": value,
                        "roles": list(definition.get("roles", [])),
                        "tags": list(definition.get("tags", [])), "source": "market",
                    },
                },
                "locked": False, "sold": False,
            })
        formations = definitions.systems["formations"]
        formation_pool = [
            dict(row) for row in formations["materials"]
            if row.get("world") == world_id and int(row.get("tier", 1)) <= tier + 1
        ]
        specialty_rng.shuffle(formation_pool)
        for index, definition in enumerate(formation_pool[:int(formations["settings"].get("market_material_offers", 3))]):
            offers.append({
                "id": f"market:{command.actor_id}:{revision}:formation:{index + 1}",
                "kind": "formation_material", "content_id": definition["id"],
                "name": definition["name"], "group": "formation",
                "tier": min(len(definitions.realms) - 1, max(tier, int(definition["tier"]))),
                "price": max(1, round(int(definition["base_value"]) * specialty_rng.uniform(0.9, 1.1))),
                "asset_blueprint": {
                    "kind": "formation_material", "definition_id": definition["id"],
                    "name": definition["name"],
                    "metadata": {
                        "tier": definition["tier"], "world_id": world_id,
                        "base_value": definition["base_value"],
                        "formation_value": definition["formation_value"],
                        "nature": definition.get("nature", "neutral"), "source": "market",
                    },
                },
                "locked": False, "sold": False,
            })
        supply_pool = [
            dict(row) for row in formations["maintenance_resources"]
            if row.get("world") == world_id and int(row.get("tier", 1)) <= tier + 1
        ]
        specialty_rng.shuffle(supply_pool)
        for index, definition in enumerate(supply_pool[:int(formations["settings"].get("repair_market_offers", 1))]):
            offers.append({
                "id": f"market:{command.actor_id}:{revision}:formation-supply:{index + 1}",
                "kind": "formation_supply", "content_id": definition["id"],
                "name": definition["name"], "group": "formation_supply",
                "tier": min(len(definitions.realms) - 1, max(tier, int(definition["tier"]))),
                "price": int(definition["base_value"]),
                "asset_blueprint": {
                    "kind": "formation_supply", "definition_id": definition["id"],
                    "name": definition["name"],
                    "metadata": {
                        "tier": definition["tier"], "world_id": world_id,
                        "base_value": definition["base_value"],
                        "repair_value": definition["repair_value"], "source": "market",
                    },
                },
                "locked": False, "sold": False,
            })
        material_limit = max(
            1, int(definitions.market_settings.get("material_offer_count", 6))
        )
        general_offers = [row for row in offers if _offer_group(row) == "general"]
        material_offers = [row for row in offers if _offer_group(row) == "material"]
        fresh_material_count = max(0, material_limit - len(retained_material))
        crafting_target = max(
            0,
            int(crafting["settings"].get("market_material_offers", 3))
            - int(bool(
                retained_material
                and retained_material[0].get("kind") == "crafting_material"
            )),
        )
        formation_target = max(0, fresh_material_count - crafting_target)
        crafting_offers = [
            row for row in material_offers
            if row.get("kind") == "crafting_material"
        ]
        formation_offers = [
            row for row in material_offers
            if row.get("kind") == "formation_material"
        ]
        supply_offers = [
            row for row in material_offers
            if row.get("kind") == "formation_supply"
        ]
        supply_count = min(1, formation_target, len(supply_offers))
        selected_materials = [
            *crafting_offers[:crafting_target],
            *formation_offers[:max(0, formation_target - supply_count)],
            *supply_offers[:supply_count],
        ]
        if len(selected_materials) < fresh_material_count:
            selected_ids = {str(row["id"]) for row in selected_materials}
            selected_materials.extend(
                row for row in material_offers
                if str(row["id"]) not in selected_ids
            )
        offers = [
            *general_offers,
            *retained_material,
            *selected_materials[:fresh_material_count],
        ]
        market = {
            "revision": revision,
            "world_id": world_id,
            "location_id": location_id,
            "tier": tier,
            "generated_year": context.state.clock.year,
            "offers": offers,
        }
        context.state.entities.put(command.actor_id, MARKET, market)
        context.emit(
            "economy.market.refreshed",
            source="economy",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id,
                "world_id": world_id,
                "location_id": location_id,
                "revision": revision,
            },
        )

    return handler


def _require_current_offer(context: SimulationContext, actor_id: str, offer_id: str):
    market = context.state.entities.require(actor_id, MARKET)
    location = context.state.entities.require(actor_id, LOCATION)
    if (
        market.get("world_id") != location.get("world_id")
        or market.get("location_id") != location.get("location_id")
    ):
        raise ValueError("该货物不属于当前坊市")
    offers = [dict(row) for row in market.get("offers", [])]
    for index, offer in enumerate(offers):
        if offer.get("id") == offer_id:
            if bool(offer.get("sold")):
                raise ValueError("该货物已经售出")
            return market, offers, index, offer
    raise ValueError("该货物不在当前坊市")


def _toggle_lock(context: SimulationContext, command: object) -> None:
    if not isinstance(command, ToggleMarketOfferLock):
        raise TypeError("命令类型错误")
    if command.actor_id != context.state.controlled_entity_id:
        raise ValueError("只能操作当前角色的坊市")
    if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色无法操作坊市")
    market, offers, index, offer = _require_current_offer(
        context, command.actor_id, command.offer_id
    )
    locking = not bool(offer.get("locked"))
    if locking:
        group = _offer_group(offer)
        for row in offers:
            if _offer_group(row) == group:
                row["locked"] = False
    offers[index]["locked"] = locking
    market["offers"] = offers
    context.state.entities.put(command.actor_id, MARKET, market)
    context.emit(
        "economy.market.lock.changed",
        source="economy",
        scope=EventScope.entity(command.actor_id),
        payload={"offer_id": command.offer_id, "locked": locking},
    )


def _buy_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BuyMarketOffer):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能为当前角色购买")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("死亡角色无法购买")
        market, offers, index, offer = _require_current_offer(
            context, command.actor_id, command.offer_id
        )
        price = int(offer["price"])
        if _quantity(_inventory(context.state, command.actor_id), CURRENCY_ID, spendable=True) < price:
            raise ValueError(f"需要 {price} 枚下品灵石")
        _change_item(
            context, definitions, command.actor_id, CURRENCY_ID, -price,
            f"market:{command.offer_id}",
        )
        if offer["kind"] == "item":
            _change_item(
                context, definitions, command.actor_id, str(offer["content_id"]), 1,
                f"market:{command.offer_id}",
            )
        elif offer["kind"] == "technique":
            practice = context.state.entities.require(command.actor_id, PRACTICE)
            if offer["content_id"] in practice.get("known_techniques", []):
                raise ValueError("已经掌握这部功法")
            context.emit(
                "economy.technique.purchased",
                source="economy",
                scope=EventScope.entity(command.actor_id),
                payload={
                    "entity_id": command.actor_id,
                    "technique_id": offer["content_id"],
                    "offer_id": command.offer_id,
                },
            )
        elif offer["kind"] in {
            "crafting_material", "formation_material", "formation_supply"
        }:
            blueprint = offer.get("asset_blueprint")
            if not isinstance(blueprint, dict):
                raise ValueError("坊市实例货物蓝图已经失效")
            create_asset(
                context, command.actor_id, kind=str(blueprint["kind"]),
                definition_id=str(blueprint["definition_id"]),
                name=str(blueprint["name"]), metadata=dict(blueprint["metadata"]),
            )
        else:
            raise ValueError("坊市货物类型尚未迁移")
        offers[index]["sold"] = True
        offers[index]["locked"] = False
        market["offers"] = offers
        context.state.entities.put(command.actor_id, MARKET, market)
        context.emit(
            "economy.market.purchased",
            source="economy",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id,
                "offer_id": command.offer_id,
                "kind": offer["kind"],
                "content_id": offer["content_id"],
                "price": price,
            },
        )

    return handler


def economy_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for entity_id in state.entities.with_component(IDENTITY):
            inventory = state.entities.get(entity_id, INVENTORY)
            market = state.entities.get(entity_id, MARKET)
            if inventory is None or market is None:
                errors.append(f"角色 {entity_id} 缺少经济组件")
                continue
            items = dict(inventory.get("items", {}))
            reserved = dict(inventory.get("reserved", {}))
            for item_id, quantity in items.items():
                if item_id not in definitions.items or not isinstance(quantity, int) or quantity <= 0:
                    errors.append(f"角色 {entity_id} 行囊物品非法：{item_id}")
            for item_id, quantity in reserved.items():
                if not isinstance(quantity, int) or quantity < 0 or quantity > int(items.get(item_id, 0)):
                    errors.append(f"角色 {entity_id} 冻结物品非法：{item_id}")
            lock_counts: dict[str, int] = {}
            offer_ids: set[str] = set()
            for offer in market.get("offers", []):
                offer_id = str(offer.get("id", ""))
                if not offer_id or offer_id in offer_ids:
                    errors.append(f"角色 {entity_id} 坊市货物ID非法")
                offer_ids.add(offer_id)
                if bool(offer.get("locked")) and not bool(offer.get("sold")):
                    group = _offer_group(offer)
                    lock_counts[group] = lock_counts.get(group, 0) + 1
            if any(count > 1 for count in lock_counts.values()):
                errors.append(f"角色 {entity_id} 同类坊市货架锁定超过一件")
        return errors

    return validate


def register_economy_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(GrantItem, _grant_item_handler(definitions))
    bus.register(UseItem, _use_item_handler(definitions))
    bus.register(RefreshMarket, _refresh_market_handler(definitions))
    bus.register(ToggleMarketOfferLock, _toggle_lock)
    bus.register(BuyMarketOffer, _buy_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created(definitions))
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions))
    bus.event_bus.register(
        "story.effect.inventory.changed", _on_story_inventory_changed(definitions)
    )
    bus.event_bus.register(
        "economy.inventory.consume.requested", _on_inventory_consume_requested(definitions)
    )
    bus.event_bus.register("world.permanent_transition.requested", _on_permanent_world_transition)
    bus.event_bus.register("world.temporary_transition.committed", _on_temporary_world_transition)


def inventory_view(state: Any, definitions: GameDefinitions, entity_id: str | None = None):
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    inventory = state.entities.require(actor_id, INVENTORY)
    reserved = dict(inventory.get("reserved", {}))
    result = []
    for item_id, quantity in sorted(dict(inventory.get("items", {})).items()):
        definition = definitions.items[item_id]
        result.append({
            "id": item_id,
            "name": definition.name,
            "description": definition.description,
            "tags": list(definition.tags),
            "quantity": int(quantity),
            "reserved": int(reserved.get(item_id, 0)),
            "available": int(quantity) - int(reserved.get(item_id, 0)),
        })
    return result


def market_view(state: Any, definitions: GameDefinitions, entity_id: str | None = None):
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    location = state.entities.require(actor_id, LOCATION)
    cultivation = state.entities.require(actor_id, CULTIVATION)
    market = state.entities.require(actor_id, MARKET)
    current = (
        market.get("world_id") == location.get("world_id")
        and market.get("location_id") == location.get("location_id")
    )
    ledger = state.entities.get(actor_id, "economy.asset_ledger") or {}
    sell_ratio = float(definitions.systems.get("spirit_field", {}).get(
        "market_sell_ratio", 0.55
    ))
    sellable_plants = []
    for asset in dict(ledger.get("instances", {})).values():
        if asset.get("kind") != "harvested_spirit_plant" or asset.get("reservation_id"):
            continue
        metadata = dict(asset.get("metadata", {}))
        sellable_plants.append({
            "id": str(asset["id"]),
            "name": str(asset["name"]),
            "quantity": 1,
            "price": max(1, round(float(metadata.get("value", 1)) * sell_ratio)),
            "plant_id": metadata.get("plant_id"),
            "plant_years": int(metadata.get("years", 0)),
            "plant_quality": float(metadata.get("quality", 0.0)),
        })
    world_id = str(location["world_id"])
    location_id = str(location["location_id"])
    tier = _market_tier(definitions, cultivation, world_id)
    world = definitions.worlds[world_id]
    location_definition = world.locations[location_id]
    practice = state.entities.require(actor_id, PRACTICE)
    known = set(map(str, practice.get("known_techniques", [])))
    root = definitions.roots[str(cultivation["spirit_root"])]
    additional_roots = list(map(str, cultivation.get("additional_roots", [])))
    crafting_definitions = {
        str(row["id"]): row
        for row in definitions.systems["crafting"]["materials"]
    }
    formation_definitions = {
        str(row["id"]): row
        for row in definitions.systems["formations"]["materials"]
    }
    supply_definitions = {
        str(row["id"]): row
        for row in definitions.systems["formations"]["maintenance_resources"]
    }

    def public_offer(raw: dict[str, Any]) -> dict[str, Any]:
        offer = dict(raw)
        kind = str(offer.get("kind", ""))
        content_id = str(offer.get("content_id", ""))
        offer_tier = max(
            0, min(len(definitions.realms) - 1, int(offer.get("tier", tier)))
        )
        description = ""
        compatible = True
        owned = False
        if kind == "item":
            definition = definitions.items.get(content_id)
            description = definition.description if definition else "普通坊市货物"
        elif kind == "technique":
            definition = definitions.techniques.get(content_id)
            if definition is not None:
                path_name = definitions.paths.get(definition.path, definition.path)
                element_name = definitions.affinity_names.get(
                    definition.element, definition.element
                )
                description = f"{path_name}功法 · {element_name}属性"
                compatible = _can_practice(root, definition, additional_roots)
                owned = content_id in known
            else:
                description = "未知功法"
                compatible = False
        elif kind == "crafting_material":
            definition = crafting_definitions.get(content_id, {})
            metadata = dict(dict(offer.get("asset_blueprint", {})).get("metadata", {}))
            roles = {
                "primary": "主材", "secondary": "辅材", "quench": "淬火",
            }
            role_text = "、".join(
                roles.get(str(role), str(role)) for role in definition.get("roles", [])
            )
            value = int(metadata.get("material_value", definition.get("base_material_value", 0)))
            description = f"炼器材料 · 材料价值 {value:,}"
            if role_text:
                description += f" · 可用位置：{role_text}"
        elif kind == "formation_material":
            definition = formation_definitions.get(content_id, {})
            nature = str(definition.get("nature", "neutral"))
            nature_names = dict(
                definitions.systems["formations"].get("nature_channels", {})
            )
            nature_label = definitions.affinity_names.get(nature, nature)
            if nature in nature_names and nature_label == nature:
                nature_label = nature
            description = (
                f"阵材 · {nature_label}性 · 固有阵值 "
                f"{float(definition.get('formation_value', 0)):g}"
            )
        elif kind == "formation_supply":
            definition = supply_definitions.get(content_id, {})
            description = (
                "镇地阵修复资源 · 恢复 "
                f"{float(definition.get('repair_value', 0)):g}% 永久完整度"
            )
        else:
            description = "坊市货物"
        offer.update({
            "description": description,
            "tier_name": definitions.realms[offer_tier].name,
            "market_name": f"{location_definition.name}·{definitions.realms[tier].name}坊市",
            "market_group": _offer_group(offer),
            "owned": owned,
            "compatible": compatible,
            "rare_next_tier": offer_tier > tier,
        })
        return offer

    visible_offers = (
        [public_offer(dict(row)) for row in market.get("offers", [])]
        if current else []
    )
    crafting_offers = [
        row for row in visible_offers if row["kind"] == "crafting_material"
    ]
    formation_offers = [
        row for row in visible_offers
        if row["kind"] in {"formation_material", "formation_supply"}
    ]
    return {
        "available": tier > 0,
        "current": current,
        "name": f"{location_definition.name}·{definitions.realms[tier].name}坊市",
        "realm_index": tier,
        "world": world_id,
        "world_id": world_id,
        "location_id": location_id,
        "location_name": location_definition.name,
        "generated_year": market.get("generated_year") if current else None,
        "spirit_stones": _quantity(_inventory(state, actor_id), CURRENCY_ID),
        "offers": visible_offers,
        "crafting_material_offers": crafting_offers,
        "formation_material_offers": formation_offers,
        "material_offers": [*crafting_offers, *formation_offers],
        "general_offer_limit": int(definitions.market_settings.get("offer_count", 6)),
        "material_offer_limit": int(
            definitions.market_settings.get("material_offer_count", 6)
        ),
        "next_tier_chance": float(
            definitions.market_settings.get("next_tier_chance", 0.0)
        ),
        "sellable_plants": sellable_plants,
    }
