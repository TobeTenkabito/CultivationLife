from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import math
    import random
    from typing import Any
    from ...content_registry import ITEM_CATALOG, MARKET_GOODS, REALMS, TECHNIQUE_CATALOG, WORLD_SYSTEMS
    from ...models import GameState, HistoryRecord, Player
    from ...runtime import now_iso
    from ...rules import acquire_technique, add_item, remove_item


class EconomyAuctionMethods:
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
        state = game.auction_state
        return bool(
            state and state.get("world") == game.player.world
            and state.get("location_id") == self.maps.normalize_location(game.player.world, game.player.location_id)
        )

    def _require_auction_access(self, game: GameState, statuses: set[str]) -> dict[str, Any]:
        if not game.player.alive or game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法参加交易集会")
        state = game.auction_state
        if state.get("status") not in statuses:
            raise ValueError("当前没有可参与的拍卖或黑市")
        if not self._auction_location_matches(game):
            raise ValueError(f"交易集会位于{state.get('location_name', '另一处地图')}，你尚未抵达")
        return state

    def _schedule_auction(self, game: GameState, rng: Any) -> None:
        locations = list(self.maps.worlds[game.player.world]["locations"])
        location = rng.choice(locations)
        game.auction_sequence += 1
        notice = int(self._auction_rules()["notice_actions"])
        game.auction_state = {
            "id":f"auction-{game.auction_sequence}", "status":"scheduled",
            "world":game.player.world, "location_id":location["id"], "location_name":location["name"],
            "announced_age":game.player.age, "actions_until_open":notice,
            "round":0, "lots":[], "consignments":[], "attendees":[], "black_market_results":[],
        }
        game.history.append(HistoryRecord(
            "SYS_AUCTION_NOTICE", 1, game.player.age, "拍卖会预告", location["id"], "scheduled",
            f"{location['name']}将在两个有时间消耗的操作节点后举行拍卖会。主办方已提前放出消息，受地图境界禁制阻隔者仍无法强行入场。",
            {"location_id":location["id"], "actions_until_open":notice},
            ["system", "auction", f"world:{game.player.world}"],
        ))

    def _auction_goods_pool(self, world: str) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in MARKET_GOODS:
            if str(row.get("world", "human")) != world:
                continue
            key = (str(row["kind"]), str(row["content_id"]))
            current = unique.get(key)
            if current is None or int(row["tier"]) > int(current["tier"]):
                unique[key] = dict(row)
        return list(unique.values())

    def _auction_good_weight(self, world: str, tier: int) -> float:
        weight = 1.0 / max(1, tier)
        if world in {"human", "demon"}:
            if tier == 5:
                weight *= float(self._auction_rules()["lower_world_tier_five_weight"])
            elif tier > 5:
                weight *= float(self._auction_rules()["lower_world_higher_tier_weight"])
        return weight

    def _make_auction_lot(
        self, game: GameState, rng: Any, *, kind: str, content_id: str, tier: int,
        start_price: int, seller: str = "npc", suffix: str, rated_price: int | None = None,
    ) -> dict[str, Any]:
        name, description = self._auction_content(kind, content_id)
        bidder_names = list(self._auction_rules()["bidder_aliases"])
        rated_price = int(rated_price or self._catalog_price(kind, content_id))
        return {
            "id":f"{game.auction_state['id']}-{suffix}", "kind":kind, "content_id":content_id,
            "name":name, "description":description, "tier":tier,
            "tier_name":REALMS[max(0, min(len(REALMS) - 1, tier))].name,
            "start_price":int(start_price), "current_bid":int(start_price),
            "rated_price":rated_price,
            "maximum_bid":max(1, math.floor(rated_price * float(self._auction_rules()["consignment_max_price_ratio"]))),
            "current_bidder":"npc", "current_bidder_name":rng.choice(bidder_names),
            "seller":seller, "closed":False,
        }

    def _open_auction(self, game: GameState, rng: Any) -> None:
        state = game.auction_state
        pool = self._auction_goods_pool(game.player.world)
        lots: list[dict[str, Any]] = []
        count = min(int(self._auction_rules()["npc_lot_count"]), len(pool))
        for index in range(count):
            weights = [self._auction_good_weight(game.player.world, int(row["tier"])) for row in pool]
            selected = rng.choices(pool, weights=weights, k=1)[0]
            pool.remove(selected)
            base_price = self._catalog_price(str(selected["kind"]), str(selected["content_id"]))
            start = max(1, round(base_price * rng.uniform(*self._auction_rules()["starting_price_multiplier"])))
            lots.append(self._make_auction_lot(
                game, rng, kind=str(selected["kind"]), content_id=str(selected["content_id"]),
                tier=int(selected["tier"]), start_price=start, suffix=f"npc-{index}",
            ))
        for index, consignment in enumerate(state.get("consignments", [])):
            if consignment.get("kind") == "crafted_artifact" and isinstance(consignment.get("artifact"), dict):
                lots.append(self._make_crafted_auction_lot(game, rng, consignment, f"player-{index}"))
            else:
                lots.append(self._make_auction_lot(
                    game, rng, kind="item", content_id=str(consignment["content_id"]),
                    tier=int(consignment.get("tier", 1)), start_price=int(consignment["start_price"]),
                    seller="player", suffix=f"player-{index}", rated_price=int(consignment.get("rated_price", 0) or 0),
                ))
        candidates = [
            npc for npc in self._all_world_npcs(game)
            if npc.alive and npc.world == game.player.world
        ]
        rng.shuffle(candidates)
        trade_pool = self._auction_goods_pool(game.player.world)
        trade_count = int(self._auction_rules()["private_trade_offer_count"])
        state.update({
            "status":"open", "round":0, "lots":lots,
            "player_alias":state.get("player_alias") or self._auction_rules()["player_aliases"][0],
            "bid_logs":[],
            "attendees":[{
                "id":npc.id, "name":npc.name, "title":npc.title,
                "realm_name":self._npc_realm_name(npc), "affinity":round(float(npc.affinity or 0), 1),
                "interacted":False, "private_trade_unlocked":False,
                "trade_offers":[{
                    "id":f"private-{npc.id}-{trade_index}", "kind":good["kind"],
                    "content_id":good["content_id"], "name":self._auction_content(good["kind"], good["content_id"])[0],
                    "description":self._auction_content(good["kind"], good["content_id"])[1],
                    "price":max(1, round(self._catalog_price(good["kind"], good["content_id"]) * float(self._auction_rules()["private_trade_buy_multiplier"]))),
                    "sold":False, "bargained":False,
                } for trade_index, good in enumerate(rng.sample(trade_pool, min(trade_count, len(trade_pool))))],
                "sell_bargains":{},
            } for npc in candidates[:4]],
        })
        game.history.append(HistoryRecord(
            "SYS_AUCTION_OPEN", 1, game.player.age, "拍卖会开幕", state["location_id"], "open",
            f"{state['location_name']}拍卖会正式开幕，共有 {len(lots)} 件拍品登台。会内竞价与交涉不消耗时间。",
            {"lots":len(lots)}, ["system", "auction", f"world:{game.player.world}"],
        ))

    def _advance_auction_clock(self, game: GameState, rng: Any) -> None:
        rng = self._auction_rng(game, "clock")
        state = game.auction_state
        if not state:
            if game.player.realm_index > 0 and rng.random() < float(self._auction_rules()["trigger_chance_per_action"]):
                self._schedule_auction(game, rng)
            return
        status = state.get("status")
        if state.get("world") != game.player.world and status != "cooldown":
            self._cancel_auction_for_world_change(game)
            return
        if status == "scheduled":
            state["actions_until_open"] = max(0, int(state.get("actions_until_open", 1)) - 1)
            if state["actions_until_open"] == 0:
                self._open_auction(game, rng)
        elif status == "open":
            self._finish_auction(game, rng, reason="你选择继续消耗时间，拍卖会在此期间完成了结拍")
        elif status == "black_market":
            game.auction_state = {"status":"cooldown", "actions_remaining":int(self._auction_rules()["cooldown_actions"])}
        elif status == "cooldown":
            state["actions_remaining"] = max(0, int(state.get("actions_remaining", 1)) - 1)
            if state["actions_remaining"] == 0:
                game.auction_state = {}

    def _auction_increment(self, lot: dict[str, Any]) -> int:
        rules = self._auction_rules()
        return max(
            1,
            math.ceil(float(lot["start_price"]) * float(rules["minimum_increment_start_ratio"])),
            math.ceil(float(lot["current_bid"]) * float(rules["minimum_increment_current_ratio"])),
        )

    def _auction_bid_ceiling(self, lot: dict[str, Any]) -> int:
        rated = int(lot.get("rated_price", 0) or self._catalog_price(str(lot["kind"]), str(lot["content_id"])))
        return max(1, math.floor(rated * float(self._auction_rules()["consignment_max_price_ratio"])))

    def consign_auction_item(self, game_id: str, item_id: str, start_price: int = 0) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"scheduled", "open"})
        item = next((entry for entry in game.player.inventory if entry.id == item_id and entry.quantity > 0), None)
        if not item or item_id == "spirit_stone":
            raise ValueError("该物品无法送拍")
        if item.crafted_artifact_id:
            raise ValueError("组合炼器法宝请使用包裹内该物品自己的寄拍按钮")
        base_price = self._plant_item_value(item) or self._catalog_price("item", item_id)
        rules = self._auction_rules()
        minimum = max(1, math.ceil(base_price * float(rules["consignment_min_price_ratio"])))
        maximum = max(minimum, math.floor(base_price * float(rules["consignment_max_price_ratio"])))
        start_price = int(start_price or round(base_price * 0.8))
        if not minimum <= start_price <= maximum:
            raise ValueError(f"起拍价须在额定价的25%至5倍之间（{minimum}—{maximum}灵石）")
        listing_fee = max(1, math.ceil(base_price * float(rules["consignment_listing_fee_ratio"])))
        if not remove_item(game.player, "spirit_stone", listing_fee):
            raise ValueError(f"上拍前须支付 {listing_fee} 枚灵石占位费")
        if not remove_item(game.player, item_id):
            add_item(game.player, "spirit_stone", listing_fee)
            raise ValueError("行囊中没有该物品")
        tier = max((int(row["tier"]) for row in MARKET_GOODS if row["kind"] == "item" and row["content_id"] == item_id), default=1)
        consignment = {
            "content_id":item_id, "start_price":start_price, "tier":tier,
            "rated_price":base_price, "listing_fee":listing_fee,
        }
        state.setdefault("consignments", []).append(consignment)
        if state["status"] == "open":
            rng = self._auction_rng(game, "consignment")
            state["lots"].append(self._make_auction_lot(
                game, rng, kind="item", content_id=item_id, tier=tier, start_price=start_price,
                seller="player", suffix=f"player-{len(state['consignments']) - 1}", rated_price=base_price,
            ))
        game.history.append(HistoryRecord(
            "SYS_AUCTION_CONSIGN", 1, game.player.age, "寄送拍品", item_id, "consigned",
            f"你支付 {listing_fee} 枚灵石占位费，将{item.name}以 {start_price} 枚灵石起拍；成交服务费另计。",
            {"start_price":start_price, "rated_price":base_price, "listing_fee":-listing_fee},
            ["system", "auction"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def place_auction_bid(self, game_id: str, lot_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        lot = next((row for row in state.get("lots", []) if row["id"] == lot_id and not row.get("closed")), None)
        if not lot:
            raise ValueError("该拍品已经结拍或不存在")
        if lot.get("seller") == "player":
            raise ValueError("不能竞拍自己送拍的物品")
        if not self._is_world_market_good(
            game.player.world, str(lot.get("kind", "")), str(lot.get("content_id", "")),
        ):
            raise ValueError("该拍品不属于当前世界，已被交易会撤下")
        if lot.get("current_bidder") == "player":
            raise ValueError("你已经是当前最高出价者")
        bid = int(lot["current_bid"]) + self._auction_increment(lot)
        if bid > self._auction_bid_ceiling(lot):
            raise ValueError("该拍品已达到额定价五倍的竞价上限")
        if not remove_item(game.player, "spirit_stone", bid):
            raise ValueError(f"本次加价后需要冻结 {bid} 枚下品灵石")
        alias = str(state.get("player_alias") or self._auction_rules()["player_aliases"][0])
        lot.update({"current_bid":bid, "current_bidder":"player", "current_bidder_name":alias})
        state.setdefault("bid_logs", []).append(f"{alias}为{lot['name']}出价 {bid} 灵石。")
        state["bid_logs"] = state["bid_logs"][-18:]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def advance_auction_round(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        rng = self._auction_rng(game, "round")
        bidder_names = list(self._auction_rules()["bidder_aliases"])
        for lot in state.get("lots", []):
            if lot.get("closed"):
                continue
            increment = self._auction_increment(lot)
            next_bid = int(lot["current_bid"]) + increment
            if next_bid > self._auction_bid_ceiling(lot):
                continue
            if lot.get("current_bidder") == "player":
                if rng.random() < float(self._auction_rules()["npc_outbid_chance"]):
                    add_item(game.player, "spirit_stone", int(lot["current_bid"]))
                    lot.update({
                        "current_bid":next_bid,
                        "current_bidder":"npc", "current_bidder_name":rng.choice(bidder_names),
                    })
                    state.setdefault("bid_logs", []).append(
                        f"{lot['current_bidder_name']}压过{state.get('player_alias', '匿名修士')}，将{lot['name']}抬至 {lot['current_bid']} 灵石。"
                    )
            elif rng.random() < 0.68:
                lot["current_bid"] = next_bid
                lot["current_bidder_name"] = rng.choice(bidder_names)
                state.setdefault("bid_logs", []).append(
                    f"{lot['current_bidder_name']}为{lot['name']}出价 {lot['current_bid']} 灵石。"
                )
        state["bid_logs"] = state.get("bid_logs", [])[-18:]
        state["round"] = int(state.get("round", 0)) + 1
        if state["round"] >= int(self._auction_rules()["auction_rounds"]):
            self._finish_auction(game, rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _grant_auction_content(self, player: Player, kind: str, content_id: str) -> None:
        if kind == "item":
            add_item(player, content_id)
            return
        acquire_technique(player, TECHNIQUE_CATALOG[content_id])

    def _finish_auction(self, game: GameState, rng: Any, reason: str = "") -> None:
        state = game.auction_state
        purchased: list[str] = []
        sold: list[str] = []
        commission = float(self._auction_rules()["commission_rate"])
        for lot in state.get("lots", []):
            if lot.get("seller") != "player" and not self._is_world_market_good(
                game.player.world, str(lot.get("kind", "")), str(lot.get("content_id", "")),
            ):
                if lot.get("current_bidder") == "player":
                    add_item(game.player, "spirit_stone", int(lot.get("current_bid", 0)))
                lot["closed"] = True
                continue
            old_bid = int(lot.get("current_bid", 0))
            lot["current_bid"] = min(old_bid, self._auction_bid_ceiling(lot))
            if lot.get("current_bidder") == "player" and old_bid > int(lot["current_bid"]):
                add_item(game.player, "spirit_stone", old_bid - int(lot["current_bid"]))
            lot["closed"] = True
            if lot.get("current_bidder") == "player":
                self._grant_auction_content(game.player, str(lot["kind"]), str(lot["content_id"]))
                purchased.append(f"{lot['name']}（{lot['current_bid']}灵石）")
            if lot.get("seller") == "player":
                net = max(0, math.floor(int(lot["current_bid"]) * (1 - commission)))
                add_item(game.player, "spirit_stone", net)
                lot["seller_net"] = net
                sold.append(f"{lot['name']}（实得{net}灵石）")
        state.update({"status":"black_market", "black_market_results":[]})
        summary = reason or "拍卖会完成全部结拍"
        if purchased:
            summary += "；你拍得" + "、".join(purchased)
        if sold:
            summary += "；寄拍成交后扣除30%手续费，你获得" + "、".join(sold)
        summary += "。散场修士随即转入同地图黑市。"
        game.history.append(HistoryRecord(
            "SYS_AUCTION_FINISH", 1, game.player.age, "拍卖结清与黑市开启", state.get("location_id"),
            "black_market", summary, {"purchased":purchased, "sold":sold},
            ["system", "auction", "black_market", f"world:{game.player.world}"],
        ))

    def negotiate_at_auction(self, game_id: str, npc_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        attendee = next((row for row in state.get("attendees", []) if row["id"] == npc_id), None)
        if not attendee or attendee.get("interacted"):
            raise ValueError("本场已经没有新的交涉机会")
        npc = self._find_npc(game, npc_id)
        if not npc or not npc.alive:
            raise ValueError("对方已经离开拍卖会")
        rng = self._auction_rng(game, "negotiate")
        affinity_range = self._auction_rules()["negotiation_affinity_gain"]
        change = rng.randint(int(affinity_range[0]), int(affinity_range[1]))
        change = self._sage_affinity_gain(game.player, change)
        npc.affinity = float(npc.affinity or 0) + change
        attendee.update({
            "interacted":True, "affinity":round(npc.affinity, 1), "private_trade_unlocked":True,
        })
        clue = self._tianji_npc_conversation_clue(game, npc_id, rng)
        game.history.append(HistoryRecord(
            "SYS_AUCTION_NEGOTIATE", 1, game.player.age, "拍卖场交涉", npc_id, "negotiated",
            f"你借拍卖间隙与{npc.name}交换消息，好感 +{change}。{clue}", {"affinity":change},
            ["system", "auction", "relationship", f"world:{game.player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def choose_auction_identity(self, game_id: str, alias: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        if alias not in self._auction_rules()["player_aliases"]:
            raise ValueError("拍卖行不承认这个匿名身份")
        state["player_alias"] = alias
        state.setdefault("bid_logs", []).append(f"你以“{alias}”的身份入席。")
        state["bid_logs"] = state["bid_logs"][-18:]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_auction(self, game: GameState) -> dict[str, Any]:
        state = game.auction_state
        status = state.get("status")
        if status not in {"scheduled", "open", "black_market"} or state.get("world") != game.player.world:
            return {"available":False, "status":status or "none"}
        at_location = self._auction_location_matches(game)
        lots = []
        for row in state.get("lots", []):
            lot = dict(row)
            lot["rated_price"] = int(row.get("rated_price", 0) or self._catalog_price(str(row["kind"]), str(row["content_id"])))
            lot["maximum_bid"] = self._auction_bid_ceiling(row)
            lot["minimum_increment"] = self._auction_increment(row)
            lots.append(lot)
        inventory = [
            {"id":item.id, "name":item.name, "quantity":item.quantity,
             "rated_price":(rated := self._plant_item_value(item) or self._catalog_price("item", item.id)),
             "minimum_start_price":max(1, math.ceil(rated * float(self._auction_rules()["consignment_min_price_ratio"]))),
             "maximum_start_price":max(1, math.floor(rated * float(self._auction_rules()["consignment_max_price_ratio"]))),
             "listing_fee":max(1, math.ceil(rated * float(self._auction_rules()["consignment_listing_fee_ratio"]))),
             "suggested_start_price":max(1, round(rated * 0.8)),
             "private_base_price":max(1, round((self._plant_item_value(item) or self._catalog_price("item", item.id)) * float(self._auction_rules()["private_trade_sell_multiplier"]))),
             "black_market_price":max(1, round((self._plant_item_value(item) or self._catalog_price("item", item.id)) * (
                 float(self._spirit_field_rules()["black_market_sell_ratio"])
                 if self._plant_item_value(item) is not None else float(self._auction_rules()["black_market_sell_ratio"])
             ))) }
            for item in game.player.inventory
            if item.id != "spirit_stone" and item.quantity > 0 and not item.crafted_artifact_id
        ]
        consignable_inventory = [row for row in inventory if row["id"] in ITEM_CATALOG]
        sellable_puppets = [
            {"id":str(row.get("id")), "name":str(row.get("name", "无名傀儡")),
             "type":str(row.get("type")), "combat_power":round(float(row.get("combat_power", 0)), 1)}
            for row in game.player.puppets if row.get("type") in {"mechanical", "corpse"}
        ]
        return {
            **state, "available":True, "at_location":at_location,
            "spirit_stones":self._spirit_stones(game.player), "lots":lots,
            "consignable_items":consignable_inventory, "black_market_sellable_items":inventory,
            "private_sellable_items":inventory,
            "player_aliases":list(self._auction_rules()["player_aliases"]),
            "black_market_sellable_puppets":sellable_puppets,
            "commission_rate":float(self._auction_rules()["commission_rate"]),
            "listing_fee_rate":float(self._auction_rules()["consignment_listing_fee_ratio"]),
            "max_rounds":int(self._auction_rules()["auction_rounds"]),
            "black_market_buy_multiplier":float(self._auction_rules()["black_market_buy_multiplier"]),
        }
