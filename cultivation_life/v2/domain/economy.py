from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .character import IDENTITY, LIFE
from .cultivation import CULTIVATION, PRACTICE
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


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    # V1 gives the controlled character one starter spirit sword.  Keeping the
    # grant in the economy subscriber (rather than BootstrapGame) preserves a
    # single owner for inventory state while NPC creation remains unaffected.
    starting_items = {"spirit_sword": 1} if bool(event.payload.get("controlled")) else {}
    context.state.entities.put(
        entity_id,
        INVENTORY,
        {"items": starting_items, "reserved": {}},
    )
    context.state.entities.put(entity_id, MARKET, {"revision": 0, "offers": []})


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
            raise ValueError("孕育药力将在家族生命周期迁移后开放")
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
    if world_id == "celestial":
        return max(9, min(12, realm_index))
    if world_id in {"spirit", "true_demon", "monster_realm", "phantom_underworld", "hell"}:
        return max(5, min(8, realm_index))
    return min(5, max(1, realm_index))


def _offer_group(offer: dict[str, Any]) -> str:
    return str(offer.get("group", "general"))


def _eligible_goods(
    definitions: GameDefinitions, world_id: str, tier: int,
) -> list[MarketGoodDefinition]:
    exact = [
        good for good in definitions.market_goods
        if good.world_id == world_id and good.tier == tier
    ]
    if exact:
        return exact
    available_tiers = [
        good.tier for good in definitions.market_goods
        if good.world_id == world_id and good.tier <= tier
    ]
    if not available_tiers:
        return []
    fallback = max(available_tiers)
    return [
        good for good in definitions.market_goods
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
        retained: list[dict[str, Any]] = []
        if market.get("world_id") == world_id and market.get("location_id") == location_id:
            groups: set[str] = set()
            for old in market.get("offers", []):
                group = _offer_group(old)
                if bool(old.get("locked")) and not bool(old.get("sold")) and group not in groups:
                    retained.append(dict(old))
                    groups.add(group)
        pool = _eligible_goods(definitions, world_id, tier)
        if not pool and retained:
            pool = []
        elif not pool:
            raise ValueError("当前世界没有可用坊市货物")
        offer_limit = max(1, int(definitions.market_settings.get("offer_count", 6)))
        fresh_count = max(0, offer_limit - len(retained))
        candidates = list(pool)
        context.rng.shuffle(candidates)
        if fresh_count > len(candidates):
            candidates = [context.rng.choice(pool) for _ in range(fresh_count)] if pool else []
        else:
            candidates = candidates[:fresh_count]
        low, high = map(float, definitions.market_settings.get("price_multiplier", (0.9, 1.1)))
        revision = int(market.get("revision", 0)) + 1
        offers = list(retained)
        retained_keys = {(row["kind"], row["content_id"]) for row in retained}
        for index, good in enumerate(candidates):
            if (good.kind, good.content_id) in retained_keys:
                continue
            content = (
                definitions.items[good.content_id]
                if good.kind == "item" else definitions.techniques[good.content_id]
            )
            offers.append({
                "id": f"market:{command.actor_id}:{revision}:{index + 1}",
                "kind": good.kind,
                "content_id": good.content_id,
                "name": content.name,
                "price": max(1, round(good.price * context.rng.uniform(low, high))),
                "tier": good.tier,
                "group": "general",
                "locked": False,
                "sold": False,
            })
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
    bus.event_bus.register("character.created", _on_character_created)
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
    return {
        "available": _market_tier(definitions, cultivation, str(location["world_id"])) > 0,
        "current": current,
        "world_id": location["world_id"],
        "location_id": location["location_id"],
        "generated_year": market.get("generated_year") if current else None,
        "spirit_stones": _quantity(_inventory(state, actor_id), CURRENCY_ID),
        "offers": [dict(row) for row in market.get("offers", [])] if current else [],
    }
