from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life.v2 import GrantItem, V2GameEngine
from cultivation_life.v2.domain.cultivation import CULTIVATION
from cultivation_life.v2.domain.world import LOCATION


class V2AuctionAndBlackMarketTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.directory.name) / "v2.sqlite3")
        game = self.engine.create_game("匿名竞拍者", seed=771122)
        self.game_id = game["id"]
        self.actor_id = game["player"]["id"]
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(realm_id="qi", layer=1)
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="匿名竞拍者", expected_revision=state.revision
        )

    def tearDown(self):
        self.directory.cleanup()

    def _resolve_pending(self) -> None:
        game = self.engine.get_game(self.game_id)
        while game["pending_event"] is not None:
            choice = next(
                row for row in game["pending_event"]["choices"] if row["enabled"]
            )
            game = self.engine.choose(self.game_id, choice["id"]).game

    def _open_auction(self) -> dict:
        state = self.engine.store.load(self.game_id)
        location_id = state.entities.require(self.actor_id, LOCATION)["location_id"]
        self.engine.schedule_auction(self.game_id, location_id)
        for _ in range(2):
            self.engine.perform_action(self.game_id, "rest", 1)
            self._resolve_pending()
        game = self.engine.get_game(self.game_id)
        self.assertEqual(game["auction"]["status"], "open")
        return game

    def _open_black_market(self) -> dict:
        game = self._open_auction()
        rules = self.engine.definitions.systems["auction_system"]
        previous = rules["auction_rounds"]
        try:
            rules["auction_rounds"] = 1
            game = self.engine.advance_auction_round(self.game_id).game
        finally:
            rules["auction_rounds"] = previous
        self.assertEqual(game["auction"]["status"], "black_market")
        return game

    def test_notice_opens_after_two_timed_actions_and_survives_reload(self):
        state = self.engine.store.load(self.game_id)
        location_id = state.entities.require(self.actor_id, LOCATION)["location_id"]
        rng_state = state.rng_state
        scheduled = self.engine.schedule_auction(self.game_id, location_id)
        self.assertEqual(self.engine.store.load(self.game_id).rng_state, rng_state)
        self.assertEqual(scheduled.game["auction"]["actions_until_open"], 2)
        self.engine.perform_action(self.game_id, "rest", 1)
        self._resolve_pending()
        self.assertEqual(
            self.engine.get_game(self.game_id)["auction"]["actions_until_open"], 1
        )
        self.engine.perform_action(self.game_id, "rest", 1)
        self._resolve_pending()
        opened = self.engine.get_game(self.game_id)["auction"]
        self.assertEqual(opened["status"], "open")
        self.assertEqual(opened["round"], 0)
        self.assertTrue(opened["lots"])

    def test_bid_is_escrowed_then_released_when_an_npc_outbids(self):
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 100_000)
        )
        opened = self._open_auction()
        lot = next(row for row in opened["auction"]["lots"] if row["seller"] == "npc")
        before = next(
            row for row in opened["inventory"] if row["id"] == "spirit_stone"
        )
        bid = self.engine.place_auction_bid(self.game_id, lot["id"])
        after_bid = next(
            row for row in bid.game["inventory"] if row["id"] == "spirit_stone"
        )
        self.assertEqual(after_bid["quantity"], before["quantity"])
        self.assertGreater(after_bid["reserved"], 0)
        rules = self.engine.definitions.systems["auction_system"]
        previous = rules["npc_outbid_chance"]
        try:
            rules["npc_outbid_chance"] = 1.0
            rng_state = self.engine.store.load(self.game_id).rng_state
            advanced = self.engine.advance_auction_round(self.game_id)
            self.assertEqual(self.engine.store.load(self.game_id).rng_state, rng_state)
        finally:
            rules["npc_outbid_chance"] = previous
        released = next(
            row for row in advanced.game["inventory"] if row["id"] == "spirit_stone"
        )
        self.assertEqual(released["reserved"], 0)
        self.assertEqual(released["available"], before["available"])

    def test_consignment_uses_asset_escrow_and_crossing_releases_it_immediately(self):
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 1_000)
        )
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "foundation_pill", 1)
        )
        state = self.engine.store.load(self.game_id)
        location_id = state.entities.require(self.actor_id, LOCATION)["location_id"]
        self.engine.schedule_auction(self.game_id, location_id)
        consigned = self.engine.consign_auction_asset(
            self.game_id, "foundation_pill", 10
        )
        item = next(
            row for row in consigned.game["inventory"] if row["id"] == "foundation_pill"
        )
        self.assertEqual((item["quantity"], item["reserved"], item["available"]), (1, 1, 0))

        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(realm_id="spirit", layer=1, path="dao")
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="匿名竞拍者", expected_revision=state.revision
        )
        crossed = self.engine.ascend_world(self.game_id, "spirit")
        self.assertEqual(crossed.game["auction"], {"available": False, "status": "none"})
        returned = next(
            row for row in crossed.game["inventory"] if row["id"] == "foundation_pill"
        )
        self.assertEqual((returned["quantity"], returned["reserved"]), (1, 0))
        self.assertEqual(crossed.game["assets"]["reservations"], [])
        self.assertIn(
            "auction",
            crossed.game["world"]["transition"]["last_transaction"]["acknowledgements"],
        )

    def test_winning_bid_settles_stones_and_delivers_exact_content(self):
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 100_000)
        )
        opened = self._open_auction()
        lot = next(
            row for row in opened["auction"]["lots"]
            if row["seller"] == "npc" and row["kind"] == "item"
        )
        before_quantity = next(
            (row["quantity"] for row in opened["inventory"] if row["id"] == lot["content_id"]),
            0,
        )
        stones_before_bid = next(
            row["quantity"] for row in opened["inventory"] if row["id"] == "spirit_stone"
        )
        bid = self.engine.place_auction_bid(self.game_id, lot["id"])
        reserved = next(
            row["reserved"] for row in bid.game["inventory"] if row["id"] == "spirit_stone"
        )
        rules = self.engine.definitions.systems["auction_system"]
        old_rounds, old_outbid = rules["auction_rounds"], rules["npc_outbid_chance"]
        try:
            rules["auction_rounds"] = 1
            rules["npc_outbid_chance"] = 0.0
            settled = self.engine.advance_auction_round(self.game_id)
        finally:
            rules["auction_rounds"], rules["npc_outbid_chance"] = old_rounds, old_outbid
        self.assertEqual(settled.game["auction"]["status"], "black_market")
        stones = next(
            row for row in settled.game["inventory"] if row["id"] == "spirit_stone"
        )
        self.assertEqual(stones["reserved"], 0)
        self.assertEqual(stones["quantity"], stones_before_bid - reserved)
        delivered = next(
            row for row in settled.game["inventory"] if row["id"] == lot["content_id"]
        )
        self.assertEqual(delivered["quantity"], before_quantity + 1)

    def test_consignment_settlement_consumes_escrow_and_pays_net_commission(self):
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 1_000)
        )
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "foundation_pill", 1)
        )
        state = self.engine.store.load(self.game_id)
        location_id = state.entities.require(self.actor_id, LOCATION)["location_id"]
        self.engine.schedule_auction(self.game_id, location_id)
        self.engine.consign_auction_item(self.game_id, "foundation_pill", 10)
        for _ in range(2):
            self.engine.perform_action(self.game_id, "rest", 1)
            self._resolve_pending()
        opened = self.engine.get_game(self.game_id)
        lot = next(row for row in opened["auction"]["lots"] if row["seller"] == "player")
        stones_before = next(
            row["quantity"] for row in opened["inventory"] if row["id"] == "spirit_stone"
        )
        rules = self.engine.definitions.systems["auction_system"]
        previous = rules["auction_rounds"]
        try:
            rules["auction_rounds"] = 1
            settled = self.engine.advance_auction_round(self.game_id)
        finally:
            rules["auction_rounds"] = previous
        self.assertNotIn(
            "foundation_pill", {row["id"] for row in settled.game["inventory"]}
        )
        self.assertEqual(settled.game["assets"]["reservations"], [])
        stones_after = next(
            row["quantity"] for row in settled.game["inventory"]
            if row["id"] == "spirit_stone"
        )
        self.assertEqual(stones_after, stones_before + int(lot["current_bid"] * 0.7))

    def test_private_trade_and_black_market_unique_material_round_trip(self):
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 1_000_000)
        )
        opened = self._open_auction()
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "healing_pill", 1)
        )
        identified = self.engine.choose_auction_identity(self.game_id, "朱雀公主")
        self.assertTrue(any(
            "朱雀公主" in row for row in identified.game["auction"]["bid_logs"]
        ))
        attendee = opened["auction"]["attendees"][0]
        negotiated = self.engine.negotiate_at_auction(
            self.game_id, attendee["id"]
        )
        public_attendee = negotiated.game["auction"]["attendees"][0]
        self.assertTrue(public_attendee["private_trade_unlocked"])
        offer = public_attendee["trade_offers"][0]
        self.engine.bargain_private_trade(
            self.game_id, attendee["id"], "buy", offer["id"]
        )
        bought = self.engine.buy_private_trade_item(
            self.game_id, attendee["id"], offer["id"]
        )
        self.assertTrue(bought.game["auction"]["attendees"][0]["trade_offers"][0]["sold"])
        stones_before_private_sale = bought.game["market"]["spirit_stones"]
        privately_sold = self.engine.sell_private_trade_item(
            self.game_id, attendee["id"], "healing_pill"
        )
        self.assertGreater(
            privately_sold.game["market"]["spirit_stones"], stones_before_private_sale
        )

        rules = self.engine.definitions.systems["auction_system"]
        previous = rules["auction_rounds"]
        try:
            rules["auction_rounds"] = 1
            black = self.engine.advance_auction_round(self.game_id)
        finally:
            rules["auction_rounds"] = previous
        self.assertEqual(black.game["auction"]["status"], "black_market")
        searched = self.engine.search_black_market(self.game_id, "寒潭玄铁")
        result = next(
            row for row in searched.game["auction"]["black_market_results"]
            if row["kind"] == "crafting_material"
        )
        purchased = self.engine.buy_black_market_item(self.game_id, result["id"])
        with self.assertRaisesRegex(ValueError, "尚未售出"):
            self.engine.buy_black_market_item(self.game_id, result["id"])
        asset = next(
            row for row in purchased.game["assets"]["instances"]
            if row["kind"] == "crafting_material"
        )
        before_sale = purchased.game["market"]["spirit_stones"]
        sold = self.engine.sell_black_market_asset(
            self.game_id, "asset", asset["id"]
        )
        self.assertFalse(any(
            row["id"] == asset["id"] for row in sold.game["assets"]["instances"]
        ))
        self.assertGreater(sold.game["market"]["spirit_stones"], before_sale)
        with self.assertRaisesRegex(ValueError, "傀儡资产不存在"):
            self.engine.sell_black_market_asset(self.game_id, "puppet", "not-migrated")
        left = self.engine.leave_black_market(self.game_id)
        self.assertEqual(left.game["auction"]["status"], "cooldown")


if __name__ == "__main__":
    unittest.main()
