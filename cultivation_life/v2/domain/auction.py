from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from typing import Any

from .assets import (
    ASSET_LEDGER,
    consume_asset,
    create_asset,
    release_reservation,
    reserve_asset,
    settle_reservation,
)
from .character import IDENTITY, LIFE
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions, MarketGoodDefinition
from .economy import CURRENCY_ID, change_inventory_item, inventory_quantity
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


AUCTION = "economy.auction"


@dataclass(frozen=True, slots=True)
class ScheduleAuction:
    actor_id: str
    location_id: str = ""


@dataclass(frozen=True, slots=True)
class ConsignAuctionAsset:
    actor_id: str
    asset_ref: str
    start_price: int = 0


@dataclass(frozen=True, slots=True)
class PlaceAuctionBid:
    actor_id: str
    lot_id: str


@dataclass(frozen=True, slots=True)
class AdvanceAuctionRound:
    actor_id: str


@dataclass(frozen=True, slots=True)
class NegotiateAuction:
    actor_id: str
    attendee_id: str


@dataclass(frozen=True, slots=True)
class ChooseAuctionIdentity:
    actor_id: str
    alias: str


@dataclass(frozen=True, slots=True)
class BuyPrivateTrade:
    actor_id: str
    attendee_id: str
    offer_id: str


@dataclass(frozen=True, slots=True)
class SellPrivateTrade:
    actor_id: str
    attendee_id: str
    asset_ref: str


@dataclass(frozen=True, slots=True)
class BargainPrivateTrade:
    actor_id: str
    attendee_id: str
    side: str
    asset_ref: str


@dataclass(frozen=True, slots=True)
class SearchBlackMarket:
    actor_id: str
    pattern: str


@dataclass(frozen=True, slots=True)
class BuyBlackMarket:
    actor_id: str
    result_id: str


@dataclass(frozen=True, slots=True)
class SellBlackMarketAsset:
    actor_id: str
    kind: str
    asset_ref: str


@dataclass(frozen=True, slots=True)
class LeaveBlackMarket:
    actor_id: str


def _new_state() -> dict[str, Any]:
    return {"next_sequence": 1, "session": None}


def reconcile_auction_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        if state.entities.get(entity_id, AUCTION) is None:
            state.entities.put(entity_id, AUCTION, _new_state())


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(str(event.payload["entity_id"]), AUCTION, _new_state())


def _rules(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems["auction_system"])


def _auction_rng(
    context: SimulationContext, identity: str, purpose: str, step: int = 0,
) -> random.Random:
    return random.Random(
        f"{context.state.seed}:auction:{identity}:{purpose}:"
        f"{context.state.clock.year}:{step}"
    )


def _component(context: SimulationContext, actor_id: str) -> dict[str, Any]:
    return context.state.entities.require(actor_id, AUCTION)


def _save_session(
    context: SimulationContext, actor_id: str, session: dict[str, Any] | None,
) -> None:
    component = _component(context, actor_id)
    component["session"] = session
    context.state.entities.put(actor_id, AUCTION, component)


def _ensure_actor(context: SimulationContext, actor_id: str) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能操作当前角色的交易会")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能参加交易会")
    if context.state.relations.find(target_id=actor_id, kind="combat_prisoner"):
        raise ValueError("服刑期间不能参加交易会")


def _location_matches(state: WorldState, actor_id: str, session: dict[str, Any]) -> bool:
    location = state.entities.require(actor_id, LOCATION)
    return (
        session.get("world_id") == location.get("world_id")
        and session.get("location_id") == location.get("location_id")
    )


def _require_session(
    context: SimulationContext, actor_id: str, statuses: set[str],
) -> dict[str, Any]:
    _ensure_actor(context, actor_id)
    session = _component(context, actor_id).get("session")
    if not isinstance(session, dict) or session.get("status") not in statuses:
        raise ValueError("当前没有可参与的拍卖或黑市")
    if not _location_matches(context.state, actor_id, session):
        raise ValueError(f"交易集会位于{session.get('location_name', '另一处地图')}，你尚未抵达")
    return session


def _world_goods(
    definitions: GameDefinitions, world_id: str,
) -> list[MarketGoodDefinition]:
    unique: dict[tuple[str, str], MarketGoodDefinition] = {}
    for good in definitions.market_goods:
        if good.world_id != world_id:
            continue
        key = (good.kind, good.content_id)
        current = unique.get(key)
        if current is None or good.tier > current.tier:
            unique[key] = good
    return list(unique.values())


def _actor_can_receive_good(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    good: MarketGoodDefinition,
) -> bool:
    if good.kind != "technique":
        return True
    practice = state.entities.require(actor_id, PRACTICE)
    if good.content_id in practice.get("known_techniques", []):
        return False
    cultivation = state.entities.require(actor_id, CULTIVATION)
    root = definitions.roots[str(cultivation["spirit_root"])]
    technique = definitions.techniques[good.content_id]
    if technique.element in {"neutral", "sex"}:
        return True
    elements = set(root.elements)
    if technique.element == "five_elements":
        return {"metal", "wood", "water", "fire", "earth"} <= elements
    return technique.element in elements


def _actor_world_goods(
    state: WorldState, definitions: GameDefinitions, actor_id: str, world_id: str,
) -> list[MarketGoodDefinition]:
    return [
        good for good in _world_goods(definitions, world_id)
        if _actor_can_receive_good(state, definitions, actor_id, good)
    ]


def _world_good(
    definitions: GameDefinitions, world_id: str, kind: str, content_id: str,
) -> MarketGoodDefinition | None:
    candidates = [
        good for good in definitions.market_goods
        if good.world_id == world_id and good.kind == kind
        and good.content_id == content_id
    ]
    return max(candidates, key=lambda row: row.tier, default=None)


def _content(
    definitions: GameDefinitions, kind: str, content_id: str,
) -> tuple[str, str]:
    if kind == "item" and content_id in definitions.items:
        item = definitions.items[content_id]
        return item.name, item.description
    if kind == "technique" and content_id in definitions.techniques:
        technique = definitions.techniques[content_id]
        return technique.name, f"{technique.grade}阶功法；战斗力 +{technique.combat_bonus:.0f}"
    raise ValueError("未知交易内容")


def _catalog_price(
    definitions: GameDefinitions, kind: str, content_id: str,
) -> int:
    prices = [
        good.price for good in definitions.market_goods
        if good.kind == kind and good.content_id == content_id
    ]
    if prices:
        return max(1, min(prices))
    if kind == "item" and content_id in definitions.items:
        item = definitions.items[content_id]
        return max(5, round(
            item.combat_bonus * 0.25 + item.hp_bonus * 0.12
            + item.mp_bonus * 0.12 + item.opportunity_bonus * 500 + 5
        ))
    raise ValueError("交易内容没有额定价格")


def _asset_info(
    state: WorldState, definitions: GameDefinitions, actor_id: str, asset_ref: str,
) -> dict[str, Any]:
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    instance = dict(ledger.get("instances", {})).get(asset_ref)
    if isinstance(instance, dict):
        metadata = dict(instance.get("metadata", {}))
        if metadata.get("is_natal"):
            raise ValueError("本命法宝不能交易或寄拍")
        value = max(1, round(float(
            metadata.get("value", metadata.get("material_value", metadata.get("base_value", 1)))
        )))
        return {
            "asset_kind": "instance", "asset_ref": asset_ref,
            "name": str(instance["name"]), "definition_id": str(instance["definition_id"]),
            "instance_kind": str(instance["kind"]), "rated_price": value,
            "tier": int(metadata.get("tier", 1)),
        }
    if asset_ref not in definitions.items or inventory_quantity(
        state, actor_id, asset_ref, spendable=True
    ) < 1:
        raise ValueError("交易资产不存在或已经托管")
    item = definitions.items[asset_ref]
    return {
        "asset_kind": "stack", "asset_ref": asset_ref,
        "name": item.name, "definition_id": asset_ref, "instance_kind": "item",
        "rated_price": _catalog_price(definitions, "item", asset_ref),
        "tier": max((
            good.tier for good in definitions.market_goods
            if good.kind == "item" and good.content_id == asset_ref
        ), default=1),
    }


def _reservation_exists(state: WorldState, actor_id: str, reservation_id: str) -> bool:
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    return reservation_id in dict(ledger.get("reservations", {}))


def _reserve_info(
    context: SimulationContext, actor_id: str, info: dict[str, Any], purpose: str,
) -> str:
    if info["asset_kind"] == "instance":
        return reserve_asset(
            context, actor_id, purpose=purpose, asset_id=str(info["asset_ref"])
        )
    return reserve_asset(
        context, actor_id, purpose=purpose, item_id=str(info["asset_ref"]), quantity=1
    )


def _schedule(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
    location_id: str = "",
) -> None:
    component = _component(context, actor_id)
    if component.get("session") is not None:
        raise ValueError("已有交易会正在筹备或举行")
    cultivation = context.state.entities.require(actor_id, CULTIVATION)
    if definitions.realm_index(str(cultivation["realm_id"])) == 0:
        raise ValueError("凡人无法参加修士拍卖会")
    location = context.state.entities.require(actor_id, LOCATION)
    world = definitions.worlds[str(location["world_id"])]
    sequence = int(component.get("next_sequence", 1))
    session_id = f"auction:{actor_id}:{sequence}"
    rng = _auction_rng(context, session_id, "schedule", sequence)
    if location_id:
        if location_id not in world.locations:
            raise ValueError("拍卖地点不属于当前世界")
        selected = world.locations[location_id]
    else:
        selected = rng.choice(list(world.locations.values()))
    component.update(
        next_sequence=sequence + 1,
        session={
            "id": session_id, "status": "scheduled",
            "world_id": world.id, "location_id": selected.id,
            "location_name": selected.name,
            "announced_year": context.state.clock.year,
            "actions_until_open": int(_rules(definitions)["notice_actions"]),
            "round": 0, "lots": [], "consignments": [], "attendees": [],
            "black_market_results": [], "bid_logs": [],
        },
    )
    context.state.entities.put(actor_id, AUCTION, component)
    context.emit(
        "economy.auction.scheduled", source="auction",
        scope=EventScope.entity(actor_id),
        payload={
            "entity_id": actor_id, "session_id": session_id,
            "world_id": world.id, "location_id": selected.id,
        },
    )


def _schedule_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ScheduleAuction):
            raise TypeError("命令类型错误")
        _ensure_actor(context, command.actor_id)
        _schedule(context, definitions, command.actor_id, command.location_id)

    return handler


def _good_weight(definitions: GameDefinitions, world_id: str, tier: int) -> float:
    weight = 1.0 / max(1, tier)
    rules = _rules(definitions)
    if world_id in {"human", "demon"}:
        if tier == 5:
            weight *= float(rules["lower_world_tier_five_weight"])
        elif tier > 5:
            weight *= float(rules["lower_world_higher_tier_weight"])
    return weight


def _increment(definitions: GameDefinitions, lot: dict[str, Any]) -> int:
    rules = _rules(definitions)
    return max(
        1,
        math.ceil(float(lot["start_price"]) * float(rules["minimum_increment_start_ratio"])),
        math.ceil(float(lot["current_bid"]) * float(rules["minimum_increment_current_ratio"])),
    )


def _ceiling(definitions: GameDefinitions, lot: dict[str, Any]) -> int:
    return max(
        1,
        math.floor(
            int(lot["rated_price"])
            * float(_rules(definitions)["consignment_max_price_ratio"])
        ),
    )


def _make_good_lot(
    rng: random.Random, definitions: GameDefinitions,
    session: dict[str, Any], good: MarketGoodDefinition, index: int,
) -> dict[str, Any]:
    name, description = _content(definitions, good.kind, good.content_id)
    start = max(
        1, round(good.price * rng.uniform(*_rules(definitions)["starting_price_multiplier"]))
    )
    return {
        "id": f"{session['id']}:npc:{index}", "kind": good.kind,
        "content_id": good.content_id, "name": name, "description": description,
        "tier": good.tier, "start_price": start, "current_bid": start,
        "rated_price": good.price, "current_bidder": "npc",
        "current_bidder_name": rng.choice(_rules(definitions)["bidder_aliases"]),
        "seller": "npc", "closed": False, "bid_reservation_id": None,
    }


def _make_consignment_lot(
    session: dict[str, Any], consignment: dict[str, Any], index: int,
) -> dict[str, Any]:
    return {
        "id": f"{session['id']}:player:{index}", "kind": "asset",
        "content_id": consignment["definition_id"], "name": consignment["name"],
        "description": "玩家寄拍资产", "tier": int(consignment["tier"]),
        "start_price": int(consignment["start_price"]),
        "current_bid": int(consignment["start_price"]),
        "rated_price": int(consignment["rated_price"]), "current_bidder": "npc",
        "current_bidder_name": "匿名买家", "seller": "player", "closed": False,
        "consignment_id": consignment["id"], "bid_reservation_id": None,
    }


def _open(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
    session: dict[str, Any],
) -> None:
    rng = _auction_rng(context, str(session["id"]), "open")
    pool = _actor_world_goods(
        context.state, definitions, actor_id, str(session["world_id"])
    )
    lots: list[dict[str, Any]] = []
    count = min(int(_rules(definitions)["npc_lot_count"]), len(pool))
    for index in range(count):
        weights = [
            _good_weight(definitions, str(session["world_id"]), good.tier)
            for good in pool
        ]
        selected = rng.choices(pool, weights=weights, k=1)[0]
        pool.remove(selected)
        lots.append(_make_good_lot(rng, definitions, session, selected, index))
    for index, consignment in enumerate(session.get("consignments", [])):
        lots.append(_make_consignment_lot(session, consignment, index))
    alias_names = list(_rules(definitions)["bidder_aliases"])
    rng.shuffle(alias_names)
    trade_count = int(_rules(definitions)["private_trade_offer_count"])
    attendees = []
    for index, attendee_name in enumerate(alias_names[:4]):
        trade_pool = pool or _actor_world_goods(
            context.state, definitions, actor_id, str(session["world_id"])
        )
        chosen = rng.sample(trade_pool, min(trade_count, len(trade_pool)))
        attendees.append({
            "id": f"{session['id']}:attendee:{index}", "name": attendee_name,
            "affinity": 0.0, "interacted": False, "private_trade_unlocked": False,
            "trade_offers": [{
                "id": f"{session['id']}:private:{index}:{offer_index}",
                "kind": good.kind, "content_id": good.content_id,
                "name": _content(definitions, good.kind, good.content_id)[0],
                "description": _content(definitions, good.kind, good.content_id)[1],
                "price": max(1, round(
                    good.price * float(_rules(definitions)["private_trade_buy_multiplier"])
                )),
                "sold": False, "bargained": False,
            } for offer_index, good in enumerate(chosen)],
            "sell_bargains": {}, "sell_bargain_attempts": [],
        })
    session.update(
        status="open", round=0, lots=lots, attendees=attendees,
        player_alias=session.get("player_alias") or _rules(definitions)["player_aliases"][0],
        bid_logs=[],
    )
    _save_session(context, actor_id, session)
    context.emit(
        "economy.auction.opened", source="auction", scope=EventScope.entity(actor_id),
        payload={"entity_id": actor_id, "session_id": session["id"], "lots": len(lots)},
    )


def _consign_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ConsignAuctionAsset):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"scheduled", "open"})
        info = _asset_info(context.state, definitions, command.actor_id, command.asset_ref)
        if command.asset_ref == CURRENCY_ID:
            raise ValueError("灵石不能作为普通拍品寄拍")
        rules = _rules(definitions)
        rated = int(info["rated_price"])
        minimum = max(1, math.ceil(rated * float(rules["consignment_min_price_ratio"])))
        maximum = max(minimum, math.floor(rated * float(rules["consignment_max_price_ratio"])))
        start = int(command.start_price or round(rated * 0.8))
        if not minimum <= start <= maximum:
            raise ValueError(f"起拍价须在额定价的25%至5倍之间（{minimum}—{maximum}灵石）")
        fee = max(1, math.ceil(rated * float(rules["consignment_listing_fee_ratio"])))
        if inventory_quantity(
            context.state, command.actor_id, CURRENCY_ID, spendable=True
        ) < fee:
            raise ValueError(f"上拍前须支付 {fee} 枚灵石占位费")
        change_inventory_item(
            context, definitions, command.actor_id, CURRENCY_ID, -fee,
            f"auction:listing:{session['id']}",
        )
        reservation_id = _reserve_info(
            context, command.actor_id, info, f"auction:consignment:{session['id']}"
        )
        consignments = [dict(row) for row in session.get("consignments", [])]
        consignment = {
            **info, "id": f"{session['id']}:consignment:{len(consignments)}",
            "start_price": start, "listing_fee": fee,
            "reservation_id": reservation_id,
        }
        consignments.append(consignment)
        session["consignments"] = consignments
        if session["status"] == "open":
            lots = [dict(row) for row in session.get("lots", [])]
            lots.append(_make_consignment_lot(session, consignment, len(consignments) - 1))
            session["lots"] = lots
        _save_session(context, command.actor_id, session)
        context.emit(
            "economy.auction.consigned", source="auction",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "asset_ref": command.asset_ref,
                "start_price": start, "listing_fee": fee,
            },
        )

    return handler


def _bid_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PlaceAuctionBid):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"open"})
        lots = [dict(row) for row in session.get("lots", [])]
        index = next((i for i, row in enumerate(lots) if row["id"] == command.lot_id), None)
        if index is None or lots[index].get("closed"):
            raise ValueError("该拍品已经结拍或不存在")
        lot = lots[index]
        if lot.get("seller") == "player":
            raise ValueError("不能竞拍自己送拍的物品")
        if lot.get("current_bidder") == "player":
            raise ValueError("你已经是当前最高出价者")
        if _world_good(
            definitions, str(session["world_id"]), str(lot["kind"]),
            str(lot["content_id"]),
        ) is None:
            raise ValueError("该拍品不属于当前世界，已被交易会撤下")
        if lot["kind"] == "technique":
            practice = context.state.entities.require(command.actor_id, PRACTICE)
            if lot["content_id"] in practice.get("known_techniques", []):
                raise ValueError("你已经掌握这部功法")
        bid = int(lot["current_bid"]) + _increment(definitions, lot)
        if bid > _ceiling(definitions, lot):
            raise ValueError("该拍品已达到额定价五倍的竞价上限")
        reservation_id = reserve_asset(
            context, command.actor_id, purpose=f"auction:bid:{lot['id']}",
            item_id=CURRENCY_ID, quantity=bid,
        )
        alias = str(session.get("player_alias") or _rules(definitions)["player_aliases"][0])
        lot.update(
            current_bid=bid, current_bidder="player", current_bidder_name=alias,
            bid_reservation_id=reservation_id,
        )
        lots[index] = lot
        session["lots"] = lots
        logs = list(map(str, session.get("bid_logs", [])))
        logs.append(f"{alias}为{lot['name']}出价 {bid} 灵石。")
        session["bid_logs"] = logs[-18:]
        _save_session(context, command.actor_id, session)

    return handler


def _grant_content(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
    kind: str, content_id: str, source_id: str,
) -> None:
    if kind == "item":
        change_inventory_item(
            context, definitions, actor_id, content_id, 1, f"auction:{source_id}"
        )
        return
    if kind == "technique":
        context.emit(
            "economy.technique.purchased", source="auction",
            scope=EventScope.entity(actor_id),
            payload={
                "entity_id": actor_id, "technique_id": content_id,
                "offer_id": source_id,
            },
        )
        return
    raise ValueError("拍卖交割内容类型无效")


def _finish(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
    session: dict[str, Any], reason: str = "",
) -> None:
    purchased: list[str] = []
    sold: list[str] = []
    commission = float(_rules(definitions)["commission_rate"])
    consignments = {
        str(row["id"]): row for row in session.get("consignments", [])
    }
    lots = [dict(row) for row in session.get("lots", [])]
    for lot in lots:
        if lot.get("closed"):
            continue
        lot["closed"] = True
        if lot.get("current_bidder") == "player":
            reservation_id = str(lot.get("bid_reservation_id", ""))
            if not reservation_id or not _reservation_exists(
                context.state, actor_id, reservation_id
            ):
                raise ValueError("竞价灵石托管已经失效")
            settle_reservation(context, actor_id, reservation_id)
            lot["bid_reservation_id"] = None
            _grant_content(
                context, definitions, actor_id, str(lot["kind"]),
                str(lot["content_id"]), str(lot["id"]),
            )
            purchased.append(str(lot["name"]))
        if lot.get("seller") == "player":
            consignment = consignments.get(str(lot.get("consignment_id")))
            if not consignment:
                raise ValueError("寄拍交割记录缺失")
            reservation_id = str(consignment["reservation_id"])
            if not _reservation_exists(context.state, actor_id, reservation_id):
                raise ValueError("寄拍资产托管已经失效")
            settle_reservation(context, actor_id, reservation_id)
            consignment["reservation_id"] = None
            net = max(0, math.floor(int(lot["current_bid"]) * (1 - commission)))
            change_inventory_item(
                context, definitions, actor_id, CURRENCY_ID, net,
                f"auction:sale:{lot['id']}",
            )
            lot["seller_net"] = net
            sold.append(str(lot["name"]))
    session.update(
        status="black_market", lots=lots, black_market_results=[],
        completed_reason=reason or "拍卖会完成全部结拍",
    )
    _save_session(context, actor_id, session)
    context.emit(
        "economy.auction.settled", source="auction",
        scope=EventScope.entity(actor_id),
        payload={
            "entity_id": actor_id, "session_id": session["id"],
            "purchased": purchased, "sold": sold,
        },
    )


def _advance_round_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, AdvanceAuctionRound):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"open"})
        rng = _auction_rng(
            context, str(session["id"]), "round", int(session.get("round", 0))
        )
        lots = [dict(row) for row in session.get("lots", [])]
        bidder_names = list(_rules(definitions)["bidder_aliases"])
        logs = list(map(str, session.get("bid_logs", [])))
        for lot in lots:
            if lot.get("closed"):
                continue
            next_bid = int(lot["current_bid"]) + _increment(definitions, lot)
            if next_bid > _ceiling(definitions, lot):
                continue
            if lot.get("current_bidder") == "player":
                if rng.random() < float(_rules(definitions)["npc_outbid_chance"]):
                    reservation_id = str(lot.get("bid_reservation_id", ""))
                    release_reservation(context, command.actor_id, reservation_id)
                    lot.update(
                        current_bid=next_bid, current_bidder="npc",
                        current_bidder_name=rng.choice(bidder_names),
                        bid_reservation_id=None,
                    )
                    logs.append(f"{lot['current_bidder_name']}将{lot['name']}抬至 {next_bid} 灵石。")
            elif rng.random() < 0.68:
                lot.update(
                    current_bid=next_bid,
                    current_bidder_name=rng.choice(bidder_names),
                )
                logs.append(f"{lot['current_bidder_name']}为{lot['name']}出价 {next_bid} 灵石。")
        session["lots"] = lots
        session["bid_logs"] = logs[-18:]
        session["round"] = int(session.get("round", 0)) + 1
        if int(session["round"]) >= int(_rules(definitions)["auction_rounds"]):
            _finish(context, definitions, command.actor_id, session)
        else:
            _save_session(context, command.actor_id, session)

    return handler


def _identity_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ChooseAuctionIdentity):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"open"})
        if command.alias not in _rules(definitions)["player_aliases"]:
            raise ValueError("拍卖行不承认这个匿名身份")
        session["player_alias"] = command.alias
        logs = list(map(str, session.get("bid_logs", [])))
        logs.append(f"你以“{command.alias}”的身份入席。")
        session["bid_logs"] = logs[-18:]
        _save_session(context, command.actor_id, session)

    return handler


def _attendee(session: dict[str, Any], attendee_id: str, *, unlocked: bool) -> dict[str, Any]:
    attendee = next(
        (row for row in session.get("attendees", []) if row.get("id") == attendee_id),
        None,
    )
    if not isinstance(attendee, dict):
        raise ValueError("对方不在本场拍卖会")
    if unlocked and not attendee.get("private_trade_unlocked"):
        raise ValueError("须先与对方交谈，取得信任后才能私下交易")
    return attendee


def _negotiate_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, NegotiateAuction):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"open"})
        attendee = _attendee(session, command.attendee_id, unlocked=False)
        if attendee.get("interacted"):
            raise ValueError("本场已经没有新的交涉机会")
        bounds = _rules(definitions)["negotiation_affinity_gain"]
        rng = _auction_rng(context, str(session["id"]), f"negotiate:{command.attendee_id}")
        gain = rng.randint(int(bounds[0]), int(bounds[1]))
        attendee.update(
            interacted=True, private_trade_unlocked=True,
            affinity=float(attendee.get("affinity", 0)) + gain,
        )
        _save_session(context, command.actor_id, session)

    return handler


def _buy_private_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BuyPrivateTrade):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"open"})
        attendee = _attendee(session, command.attendee_id, unlocked=True)
        offer = next(
            (row for row in attendee.get("trade_offers", [])
             if row.get("id") == command.offer_id and not row.get("sold")), None,
        )
        if not isinstance(offer, dict):
            raise ValueError("这件私人物品已经易主")
        if _world_good(
            definitions, str(session["world_id"]), str(offer["kind"]),
            str(offer["content_id"]),
        ) is None:
            raise ValueError("这件货物不属于当前世界的流通范围")
        if offer["kind"] == "technique":
            practice = context.state.entities.require(command.actor_id, PRACTICE)
            if offer["content_id"] in practice.get("known_techniques", []):
                raise ValueError("你已经掌握这部功法")
        price = int(offer["price"])
        if inventory_quantity(
            context.state, command.actor_id, CURRENCY_ID, spendable=True
        ) < price:
            raise ValueError(f"私下交易需要 {price} 枚下品灵石")
        change_inventory_item(
            context, definitions, command.actor_id, CURRENCY_ID, -price,
            f"auction:private-buy:{offer['id']}",
        )
        _grant_content(
            context, definitions, command.actor_id, str(offer["kind"]),
            str(offer["content_id"]), str(offer["id"]),
        )
        offer["sold"] = True
        bounds = _rules(definitions)["private_trade_buy_affinity_gain"]
        rng = _auction_rng(context, str(session["id"]), f"private-buy:{offer['id']}")
        attendee["affinity"] = float(attendee.get("affinity", 0)) + rng.randint(
            int(bounds[0]), int(bounds[1])
        )
        _save_session(context, command.actor_id, session)

    return handler


def _consume_immediate_asset(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
    asset_ref: str, reason: str,
) -> dict[str, Any]:
    info = _asset_info(context.state, definitions, actor_id, asset_ref)
    if info["asset_kind"] == "instance":
        consume_asset(context, actor_id, asset_ref)
    else:
        change_inventory_item(context, definitions, actor_id, asset_ref, -1, reason)
    return info


def _sell_private_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SellPrivateTrade):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"open"})
        attendee = _attendee(session, command.attendee_id, unlocked=True)
        info = _asset_info(context.state, definitions, command.actor_id, command.asset_ref)
        if command.asset_ref == CURRENCY_ID:
            raise ValueError("灵石不能作为普通货物出售")
        multiplier = float(_rules(definitions)["private_trade_sell_multiplier"])
        multiplier *= float(dict(attendee.get("sell_bargains", {})).get(command.asset_ref, 1))
        price = max(1, round(int(info["rated_price"]) * multiplier))
        _consume_immediate_asset(
            context, definitions, command.actor_id, command.asset_ref,
            f"auction:private-sell:{attendee['id']}",
        )
        change_inventory_item(
            context, definitions, command.actor_id, CURRENCY_ID, price,
            f"auction:private-sale:{attendee['id']}",
        )

    return handler


def _bargain_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BargainPrivateTrade):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"open"})
        attendee = _attendee(session, command.attendee_id, unlocked=True)
        rules = _rules(definitions)
        chance = min(
            0.85,
            float(rules["bargain_success_base"])
            + max(0.0, float(attendee.get("affinity", 0)))
            * float(rules["bargain_affinity_factor"]),
        )
        rng = _auction_rng(
            context, str(session["id"]),
            f"bargain:{command.attendee_id}:{command.side}:{command.asset_ref}",
        )
        success = rng.random() < chance
        if command.side == "buy":
            offer = next(
                (row for row in attendee.get("trade_offers", [])
                 if row.get("id") == command.asset_ref and not row.get("sold")), None,
            )
            if not isinstance(offer, dict) or offer.get("bargained"):
                raise ValueError("这件商品已经没有继续还价的余地")
            offer["bargained"] = True
            if success:
                discount = rng.uniform(*rules["bargain_buy_discount"])
                offer["price"] = max(1, round(int(offer["price"]) * (1 - discount)))
        elif command.side == "sell":
            _asset_info(context.state, definitions, command.actor_id, command.asset_ref)
            attempts = list(map(str, attendee.get("sell_bargain_attempts", [])))
            if command.asset_ref in attempts:
                raise ValueError("这件物品已经没有继续还价的余地")
            attempts.append(command.asset_ref)
            attendee["sell_bargain_attempts"] = attempts
            if success:
                bonus = rng.uniform(*rules["bargain_sell_bonus"])
                bargains = dict(attendee.get("sell_bargains", {}))
                bargains[command.asset_ref] = 1 + bonus
                attendee["sell_bargains"] = bargains
        else:
            raise ValueError("未知还价方向")
        logs = list(map(str, session.get("bid_logs", [])))
        logs.append(f"你与{attendee['name']}私下还价，{'对方最终松口' if success else '对方不肯让步'}。")
        session["bid_logs"] = logs[-18:]
        _save_session(context, command.actor_id, session)

    return handler


def _material_blueprints(
    context: SimulationContext, definitions: GameDefinitions, world_id: str,
    pattern: str,
) -> list[dict[str, Any]]:
    rng = random.Random(
        f"{context.state.seed}:black-market:{world_id}:{pattern}"
    )
    rows: list[dict[str, Any]] = []
    qualities = (("damaged", 0.4), ("rough", 0.7), ("normal", 1.0), ("excellent", 1.05))
    for definition in definitions.systems["crafting"]["materials"]:
        if str(definition.get("world")) != world_id:
            continue
        state_name, quality = rng.choice(qualities)
        value = max(1, round(float(definition.get("base_material_value", 1)) * quality))
        rows.append({
            "kind": "crafting_material", "definition_id": str(definition["id"]),
            "name": str(definition["name"]), "tier": int(definition.get("tier", 1)),
            "base_price": value,
            "metadata": {
                "tier": int(definition.get("tier", 1)), "world_id": world_id,
                "state": state_name, "quality_multiplier": quality,
                "material_value": value, "roles": list(definition.get("roles", [])),
                "tags": list(definition.get("tags", [])), "source": "black_market",
            },
        })
    for definition in definitions.systems["formations"]["materials"]:
        if str(definition.get("world")) != world_id:
            continue
        rows.append({
            "kind": "formation_material", "definition_id": str(definition["id"]),
            "name": str(definition["name"]), "tier": int(definition.get("tier", 1)),
            "base_price": int(definition.get("base_value", 1)),
            "metadata": {
                "tier": int(definition.get("tier", 1)), "world_id": world_id,
                "base_value": int(definition.get("base_value", 1)),
                "formation_value": float(definition.get("formation_value", 0)),
                "nature": str(definition.get("nature", "neutral")),
                "source": "black_market",
            },
        })
    for definition in definitions.systems["formations"]["maintenance_resources"]:
        if str(definition.get("world")) != world_id:
            continue
        rows.append({
            "kind": "formation_supply", "definition_id": str(definition["id"]),
            "name": str(definition["name"]), "tier": int(definition.get("tier", 1)),
            "base_price": int(definition.get("base_value", 1)),
            "metadata": {
                "tier": int(definition.get("tier", 1)), "world_id": world_id,
                "base_value": int(definition.get("base_value", 1)),
                "repair_value": float(definition.get("repair_value", 0)),
                "source": "black_market",
            },
        })
    return rows


def _search_black_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SearchBlackMarket):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"black_market"})
        pattern = command.pattern.strip()
        if not pattern or len(pattern) > 40:
            raise ValueError("请输入1至40个字符的检索表达式")
        try:
            matcher = re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"正则表达式无效：{error}") from error
        multiplier = float(_rules(definitions)["black_market_buy_multiplier"])
        results: list[dict[str, Any]] = []
        for good in _actor_world_goods(
            context.state, definitions, command.actor_id, str(session["world_id"])
        ):
            name, description = _content(definitions, good.kind, good.content_id)
            if matcher.search(f"{name} {description}"):
                results.append({
                    "id": f"black:{good.kind}:{good.content_id}", "kind": good.kind,
                    "content_id": good.content_id, "name": name,
                    "description": description, "tier": good.tier,
                    "price": max(1, round(good.price * multiplier)), "sold": False,
                })
        for row in _material_blueprints(
            context, definitions, str(session["world_id"]), pattern
        ):
            description = f"{row['kind']} · {row['metadata']}"
            if matcher.search(f"{row['name']} {description}"):
                results.append({
                    "id": f"black:{row['kind']}:{row['definition_id']}",
                    "kind": row["kind"], "content_id": row["definition_id"],
                    "name": row["name"], "description": description,
                    "tier": row["tier"],
                    "price": max(1, round(int(row["base_price"]) * multiplier)),
                    "asset_blueprint": row, "sold": False,
                })
        results.sort(key=lambda row: (int(row["tier"]), str(row["name"])))
        session["black_market_results"] = results[:int(
            _rules(definitions)["black_market_result_limit"]
        )]
        _save_session(context, command.actor_id, session)

    return handler


def _buy_black_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BuyBlackMarket):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"black_market"})
        result = next(
            (row for row in session.get("black_market_results", [])
             if row.get("id") == command.result_id and not row.get("sold")), None,
        )
        if not isinstance(result, dict):
            raise ValueError("请先检索并选择一件尚未售出的黑市商品")
        price = int(result["price"])
        if inventory_quantity(
            context.state, command.actor_id, CURRENCY_ID, spendable=True
        ) < price:
            raise ValueError(f"需要 {price} 枚下品灵石")
        kind = str(result["kind"])
        if kind == "technique":
            practice = context.state.entities.require(command.actor_id, PRACTICE)
            if result["content_id"] in practice.get("known_techniques", []):
                raise ValueError("你已经掌握这部功法")
        change_inventory_item(
            context, definitions, command.actor_id, CURRENCY_ID, -price,
            f"black-market:{result['id']}",
        )
        if kind in {"item", "technique"}:
            _grant_content(
                context, definitions, command.actor_id, kind,
                str(result["content_id"]), str(result["id"]),
            )
        else:
            blueprint = result.get("asset_blueprint")
            if not isinstance(blueprint, dict):
                raise ValueError("黑市实例货物蓝图已经失效")
            create_asset(
                context, command.actor_id, kind=kind,
                definition_id=str(blueprint["definition_id"]),
                name=str(blueprint["name"]), metadata=dict(blueprint["metadata"]),
            )
        result["sold"] = True
        _save_session(context, command.actor_id, session)
        context.emit(
            "economy.black_market.purchased", source="auction",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "result_id": result["id"],
                "kind": kind, "price": price,
            },
        )

    return handler


def _sell_black_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SellBlackMarketAsset):
            raise TypeError("命令类型错误")
        _require_session(context, command.actor_id, {"black_market"})
        if command.kind == "puppet":
            raise ValueError("傀儡销赃须等待魔道傀儡领域迁移")
        if command.asset_ref == CURRENCY_ID:
            raise ValueError("灵石不能在黑市出售")
        info = _asset_info(context.state, definitions, command.actor_id, command.asset_ref)
        ratio = float(_rules(definitions)["black_market_sell_ratio"])
        if info["asset_kind"] == "instance" and info["instance_kind"] == "harvested_spirit_plant":
            ratio = float(definitions.systems["spirit_field"]["black_market_sell_ratio"])
        price = max(1, round(int(info["rated_price"]) * ratio))
        _consume_immediate_asset(
            context, definitions, command.actor_id, command.asset_ref,
            f"black-market:sell:{command.kind}",
        )
        change_inventory_item(
            context, definitions, command.actor_id, CURRENCY_ID, price,
            f"black-market:sale:{command.kind}",
        )
        context.emit(
            "economy.black_market.sold", source="auction",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "asset_ref": command.asset_ref,
                "kind": command.kind, "price": price,
            },
        )

    return handler


def _leave_black_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, LeaveBlackMarket):
            raise TypeError("命令类型错误")
        session = _require_session(context, command.actor_id, {"black_market"})
        session.clear()
        session.update(
            status="cooldown",
            actions_remaining=int(_rules(definitions)["cooldown_actions"]),
        )
        _save_session(context, command.actor_id, session)

    return handler


def _cancel_session(
    context: SimulationContext, actor_id: str, *, cooldown: bool,
) -> None:
    component = context.state.entities.require(actor_id, AUCTION)
    session = component.get("session")
    if not isinstance(session, dict):
        return
    for reservation_id in list(dict(
        context.state.entities.require(actor_id, ASSET_LEDGER).get("reservations", {})
    )):
        reservation = context.state.entities.require(actor_id, ASSET_LEDGER)["reservations"].get(
            reservation_id, {}
        )
        if str(reservation.get("purpose", "")).startswith("auction:"):
            release_reservation(context, actor_id, reservation_id)
    component["session"] = (
        {"status": "cooldown", "actions_remaining": 1} if cooldown else None
    )
    context.state.entities.put(actor_id, AUCTION, component)


def _on_action_completed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        component = context.state.entities.require(actor_id, AUCTION)
        session = component.get("session")
        if not isinstance(session, dict):
            cultivation = context.state.entities.require(actor_id, CULTIVATION)
            trigger_rng = _auction_rng(
                context, f"pending:{actor_id}",
                f"clock:{event.payload.get('token', '')}",
            )
            if (
                definitions.realm_index(str(cultivation["realm_id"])) > 0
                and trigger_rng.random() < float(_rules(definitions)["trigger_chance_per_action"])
            ):
                _schedule(context, definitions, actor_id)
            return
        status = str(session.get("status"))
        location = context.state.entities.require(actor_id, LOCATION)
        if session.get("world_id") not in {None, location.get("world_id")}:
            _cancel_session(context, actor_id, cooldown=True)
        elif status == "scheduled":
            session["actions_until_open"] = max(
                0, int(session.get("actions_until_open", 1)) - 1
            )
            if int(session["actions_until_open"]) == 0:
                _open(context, definitions, actor_id, session)
            else:
                _save_session(context, actor_id, session)
        elif status == "open":
            _finish(
                context, definitions, actor_id, session,
                reason="你选择继续消耗时间，拍卖会在此期间完成结拍",
            )
        elif status == "black_market":
            session.clear()
            session.update(
                status="cooldown",
                actions_remaining=int(_rules(definitions)["cooldown_actions"]),
            )
            _save_session(context, actor_id, session)
        elif status == "cooldown":
            session["actions_remaining"] = max(
                0, int(session.get("actions_remaining", 1)) - 1
            )
            if int(session["actions_remaining"]) == 0:
                component["session"] = None
                context.state.entities.put(actor_id, AUCTION, component)
            else:
                _save_session(context, actor_id, session)

    return handler


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    _cancel_session(context, str(event.payload["entity_id"]), cooldown=False)


def _on_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    # Asset-domain cleanup runs first and releases every escrow reservation.  The
    # auction subscriber owns only its state-machine cleanup and acknowledgement.
    component = context.state.entities.require(actor_id, AUCTION)
    component["session"] = None
    context.state.entities.put(actor_id, AUCTION, component)
    if event.event_type == "world.permanent_transition.requested":
        context.emit(
            "world.transition.acknowledged", source="auction", scope=event.scope,
            payload={
                "transaction_id": event.payload["transaction_id"],
                "actor_id": actor_id, "domain": "auction",
            },
        )


def auction_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    for entity_id in state.entities.with_component(IDENTITY):
        component = state.entities.get(entity_id, AUCTION)
        if component is None:
            errors.append(f"角色 {entity_id} 缺少拍卖组件")
            continue
        session = component.get("session")
        ledger = state.entities.get(entity_id, ASSET_LEDGER) or {}
        reservations = dict(ledger.get("reservations", {}))
        auction_reservations = {
            reservation_id for reservation_id, reservation in reservations.items()
            if str(reservation.get("purpose", "")).startswith("auction:")
        }
        if session is None:
            if auction_reservations:
                errors.append(f"角色 {entity_id} 无拍卖会但仍有托管资产")
            continue
        if not isinstance(session, dict) or session.get("status") not in {
            "scheduled", "open", "black_market", "cooldown"
        }:
            errors.append(f"角色 {entity_id} 的拍卖状态无效")
            continue
        referenced: set[str] = set()
        lot_ids: set[str] = set()
        for lot in session.get("lots", []):
            lot_id = str(lot.get("id", ""))
            if not lot_id or lot_id in lot_ids:
                errors.append(f"角色 {entity_id} 的拍品ID重复")
            lot_ids.add(lot_id)
            reservation_id = lot.get("bid_reservation_id")
            if reservation_id:
                referenced.add(str(reservation_id))
                if lot.get("current_bidder") != "player":
                    errors.append(f"角色 {entity_id} 的非玩家最高价仍占用竞价托管")
        for consignment in session.get("consignments", []):
            reservation_id = consignment.get("reservation_id")
            if reservation_id:
                referenced.add(str(reservation_id))
        if referenced != auction_reservations:
            errors.append(f"角色 {entity_id} 的拍卖状态与资产托管账本不一致")
    return errors


def register_auction_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(ScheduleAuction, _schedule_handler(definitions))
    bus.register(ConsignAuctionAsset, _consign_handler(definitions))
    bus.register(PlaceAuctionBid, _bid_handler(definitions))
    bus.register(AdvanceAuctionRound, _advance_round_handler(definitions))
    bus.register(NegotiateAuction, _negotiate_handler(definitions))
    bus.register(ChooseAuctionIdentity, _identity_handler(definitions))
    bus.register(BuyPrivateTrade, _buy_private_handler(definitions))
    bus.register(SellPrivateTrade, _sell_private_handler(definitions))
    bus.register(BargainPrivateTrade, _bargain_handler(definitions))
    bus.register(SearchBlackMarket, _search_black_handler(definitions))
    bus.register(BuyBlackMarket, _buy_black_handler(definitions))
    bus.register(SellBlackMarketAsset, _sell_black_handler(definitions))
    bus.register(LeaveBlackMarket, _leave_black_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions))
    bus.event_bus.register("world.permanent_transition.requested", _on_world_transition)
    bus.event_bus.register("world.temporary_transition.committed", _on_world_transition)


def auction_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    component = state.entities.require(actor_id, AUCTION)
    session = component.get("session")
    if not isinstance(session, dict):
        return {"available": False, "status": "none"}
    status = str(session.get("status"))
    if status == "cooldown":
        return {
            "available": False, "status": status,
            "actions_remaining": int(session.get("actions_remaining", 0)),
        }
    lots = []
    for raw in session.get("lots", []):
        lot = dict(raw)
        lot["minimum_increment"] = _increment(definitions, lot)
        lot["maximum_bid"] = _ceiling(definitions, lot)
        lots.append(lot)
    consignable: list[dict[str, Any]] = []
    inventory = state.entities.require(actor_id, "economy.inventory")
    for item_id in sorted(dict(inventory.get("items", {}))):
        if item_id == CURRENCY_ID or inventory_quantity(
            state, actor_id, item_id, spendable=True
        ) <= 0:
            continue
        info = _asset_info(state, definitions, actor_id, item_id)
        consignable.append(info)
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    for asset_id, asset in sorted(dict(ledger.get("instances", {})).items()):
        if asset.get("reservation_id"):
            continue
        consignable.append(_asset_info(state, definitions, actor_id, asset_id))
    return {
        **dict(session), "available": status in {"scheduled", "open", "black_market"},
        "at_location": _location_matches(state, actor_id, session),
        "lots": lots, "consignable_assets": consignable,
        "spirit_stones": inventory_quantity(
            state, actor_id, CURRENCY_ID, spendable=True
        ),
        "player_aliases": list(_rules(definitions)["player_aliases"]),
        "commission_rate": float(_rules(definitions)["commission_rate"]),
        "listing_fee_rate": float(_rules(definitions)["consignment_listing_fee_ratio"]),
        "max_rounds": int(_rules(definitions)["auction_rounds"]),
        "black_market_buy_multiplier": float(
            _rules(definitions)["black_market_buy_multiplier"]
        ),
    }
