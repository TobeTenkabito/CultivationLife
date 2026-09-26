import math
import random
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from cultivation_life.content_registry import MARKET_GOODS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class AuctionUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def _open_local_auction(self, game_id: str):
        game = self.engine.store.load(game_id)
        game.auction_sequence += 1
        location_id = self.engine.maps.normalize_location(game.player.world, game.player.location_id)
        location_name = self.engine.maps.location(game.player.world, location_id)["name"]
        game.auction_state = {
            "id": f"auction-{game.auction_sequence}", "status": "open",
            "world": game.player.world, "location_id": location_id, "location_name": location_name,
            "announced_age": game.player.age, "actions_until_open": 0, "round": 0,
            "lots": [], "consignments": [], "attendees": [], "black_market_results": [],
        }
        self.engine._open_auction(game, random.Random(1001))
        self.engine.store.save(game)
        return game

    def test_lower_realm_return_hides_and_blocks_normal_ascension(self):
        made = self.engine.create_game("归界不误触", "none", "dao", 11001, preset_id="mahayana")
        shown = self.engine.cross_world(made["id"], "human")
        self.assertTrue(shown["world_travel"]["can_return_spirit"])
        self.assertFalse(shown["demonic_system"]["true_demon_ascension"]["available"])
        with self.assertRaisesRegex(ValueError, "只能重返原上界"):
            self.engine.begin_spirit_crossing(made["id"])

    def test_lower_demon_return_hides_and_blocks_demonic_ascension(self):
        made = self.engine.create_game("魔尊归界", "none", "dao", 11002, preset_id="mahayana")
        game = self.engine.store.load(made["id"])
        game.player.path = "demonic"
        game.player.world = "true_demon"
        self.engine.store.save(game)
        shown = self.engine.cross_world(made["id"], "demon")
        self.assertTrue(shown["world_travel"]["can_return_true_demon"])
        self.assertFalse(shown["demonic_system"]["true_demon_ascension"]["available"])
        with self.assertRaisesRegex(ValueError, "只能重返原上界"):
            self.engine.begin_spirit_crossing(made["id"])

    def test_notice_waits_two_timed_actions_and_survives_reload(self):
        made = self.engine.create_game("闻拍卖风声", "supreme_metal", "dao", 11003, preset_id="core")
        game = self.engine.store.load(made["id"])
        self.engine._schedule_auction(game, random.Random(3))
        scheduled_location = game.auction_state["location_id"]
        self.engine.store.save(game)
        reloaded = self.engine.store.load(made["id"])
        self.assertEqual(reloaded.auction_state["actions_until_open"], 2)
        self.assertEqual(reloaded.auction_state["location_id"], scheduled_location)
        self.engine._advance_auction_clock(reloaded, random.Random(999))
        self.assertEqual(reloaded.auction_state["actions_until_open"], 1)
        self.engine._advance_auction_clock(reloaded, random.Random(999))
        self.assertEqual(reloaded.auction_state["status"], "open")

    def test_bidding_uses_minimum_increment_and_consumes_no_time(self):
        made = self.engine.create_game("竞拍者", "supreme_metal", "dao", 11004, preset_id="core")
        game = self._open_local_auction(made["id"])
        add_item(game.player, "spirit_stone", 100000)
        lot = next(row for row in game.auction_state["lots"] if self.engine._auction_increment(row) > 1)
        lot["current_bidder"] = "npc"
        self.engine.store.save(game)
        before_age = game.player.age
        before_stones = self.engine._spirit_stones(game.player)
        expected_bid = int(lot["current_bid"]) + self.engine._auction_increment(lot)
        shown = self.engine.place_auction_bid(made["id"], lot["id"])
        actual = next(row for row in shown["auction_system"]["lots"] if row["id"] == lot["id"])
        self.assertEqual(actual["current_bid"], expected_bid)
        self.assertGreater(actual["minimum_increment"], 1)
        self.assertEqual(shown["player"]["age"], before_age)
        self.assertEqual(shown["auction_system"]["spirit_stones"], before_stones - expected_bid)

    def test_auction_and_private_trade_never_offer_goods_from_another_world(self):
        made = self.engine.create_game("界货禁行", "supreme_metal", "dao", 11040, preset_id="core")
        game = self._open_local_auction(made["id"])
        human_goods = {
            (str(row["kind"]), str(row["content_id"]))
            for row in MARKET_GOODS if row.get("world", "human") == "human"
        }
        foreign_goods = {
            (str(row["kind"]), str(row["content_id"]))
            for row in MARKET_GOODS if row.get("world", "human") != "human"
        }
        lots = {(row["kind"], row["content_id"]) for row in game.auction_state["lots"]}
        private = {
            (offer["kind"], offer["content_id"])
            for attendee in game.auction_state["attendees"]
            for offer in attendee["trade_offers"]
        }
        self.assertTrue(lots | private)
        self.assertTrue((lots | private) <= human_goods)
        self.assertFalse((lots | private) & (foreign_goods - human_goods))

        invalid = next(row for row in MARKET_GOODS if row.get("world") == "asura")
        injected = game.auction_state["lots"][0]
        injected.update(kind=invalid["kind"], content_id=invalid["content_id"])
        self.engine.store.save(game)
        with self.assertRaisesRegex(ValueError, "不属于当前世界"):
            self.engine.place_auction_bid(made["id"], injected["id"])

    def test_player_chooses_alias_and_bid_log_never_uses_real_name(self):
        made = self.engine.create_game("不可示人的真名", "supreme_metal", "dao", 11041, preset_id="core")
        game = self._open_local_auction(made["id"])
        add_item(game.player, "spirit_stone", 100000)
        game.auction_state["lots"][0]["current_bidder"] = "npc"
        self.engine.store.save(game)
        self.engine.choose_auction_identity(made["id"], "朱雀公主")
        shown = self.engine.place_auction_bid(made["id"], game.auction_state["lots"][0]["id"])
        lot = shown["auction_system"]["lots"][0]
        self.assertEqual(lot["current_bidder_name"], "朱雀公主")
        self.assertTrue(any("朱雀公主" in row for row in shown["auction_system"]["bid_logs"]))
        self.assertFalse(any("不可示人的真名" in row for row in shown["auction_system"]["bid_logs"]))

    def test_negotiation_unlocks_private_trade_and_bargaining(self):
        made = self.engine.create_game("密市客", "supreme_metal", "dao", 11042, preset_id="core")
        game = self._open_local_auction(made["id"])
        add_item(game.player, "spirit_stone", 5_000_000)
        add_item(game.player, "healing_pill", 1)
        attendee = game.auction_state["attendees"][0]
        before_affinity = attendee["affinity"]
        self.engine.store.save(game)
        with patch.object(
            self.engine, "_tianji_npc_conversation_clue",
            return_value=" 对方提及神机秘闻，情报提升至 Lv1。",
        ) as clue:
            shown = self.engine.negotiate_at_auction(made["id"], attendee["id"])
        clue.assert_called_once()
        self.assertTrue(any("情报提升至 Lv1" in row["summary"] for row in shown["history"]))
        public_attendee = shown["auction_system"]["attendees"][0]
        self.assertTrue(public_attendee["private_trade_unlocked"])
        self.assertGreaterEqual(public_attendee["affinity"] - before_affinity, 8)
        offer = public_attendee["trade_offers"][0]
        bargained = self.engine.bargain_private_trade(made["id"], attendee["id"], "buy", offer["id"])
        self.assertTrue(bargained["auction_system"]["attendees"][0]["trade_offers"][0]["bargained"])
        before_buy_affinity = bargained["auction_system"]["attendees"][0]["affinity"]
        bought = self.engine.buy_private_trade_item(made["id"], attendee["id"], offer["id"])
        self.assertGreater(bought["auction_system"]["attendees"][0]["affinity"], before_buy_affinity)
        before_age = bargained["player"]["age"]
        sold = self.engine.sell_private_trade_item(made["id"], attendee["id"], "healing_pill")
        self.assertEqual(sold["player"]["age"], before_age)

    def test_consignment_charges_thirty_percent_and_opens_black_market(self):
        made = self.engine.create_game("寄拍者", "supreme_metal", "dao", 11005, preset_id="core")
        game = self._open_local_auction(made["id"])
        add_item(game.player, "foundation_pill", 1)
        self.engine.store.save(game)
        before_age = game.player.age
        before_listing_stones = self.engine._spirit_stones(game.player)
        shown = self.engine.consign_auction_item(made["id"], "foundation_pill", 10)
        self.assertEqual(shown["player"]["age"], before_age)
        self.assertEqual(shown["auction_system"]["spirit_stones"], before_listing_stones - 1)
        persisted = self.engine.store.load(made["id"])
        lot = next(row for row in persisted.auction_state["lots"] if row.get("seller") == "player")
        lot["current_bid"] = 15
        before_stones = self.engine._spirit_stones(persisted.player)
        self.engine._finish_auction(persisted, random.Random(8))
        self.assertEqual(persisted.auction_state["status"], "black_market")
        self.assertEqual(self.engine._spirit_stones(persisted.player), before_stones + math.floor(15 * 0.7))
        self.assertEqual(persisted.player.age, before_age)

    def test_consignment_rejects_price_exploit_and_requires_listing_fee(self):
        made = self.engine.create_game("限价寄拍", "supreme_metal", "dao", 11051, preset_id="core")
        game = self._open_local_auction(made["id"])
        add_item(game.player, "healing_pill", 1)
        self.engine.store.save(game)
        before_stones = self.engine._spirit_stones(game.player)
        with self.assertRaisesRegex(ValueError, "25%至5倍"):
            self.engine.consign_auction_item(made["id"], "healing_pill", 80_000_000_000)
        unchanged = self.engine.store.load(made["id"])
        self.assertEqual(self.engine._spirit_stones(unchanged.player), before_stones)
        self.assertTrue(any(item.id == "healing_pill" for item in unchanged.player.inventory))
        public_item = next(row for row in self.engine.present(unchanged)["auction_system"]["consignable_items"] if row["id"] == "healing_pill")
        shown = self.engine.consign_auction_item(made["id"], "healing_pill", public_item["maximum_start_price"])
        self.assertEqual(shown["auction_system"]["spirit_stones"], before_stones - public_item["listing_fee"])
        legacy = self.engine.store.load(made["id"])
        lot = next(row for row in legacy.auction_state["lots"] if row.get("seller") == "player")
        lot["current_bid"] = 80_000_000_000
        before_settlement = self.engine._spirit_stones(legacy.player)
        self.engine._finish_auction(legacy, random.Random(2))
        self.assertEqual(lot["current_bid"], public_item["maximum_start_price"])
        self.assertEqual(
            self.engine._spirit_stones(legacy.player),
            before_settlement + math.floor(public_item["maximum_start_price"] * 0.7),
        )

    def test_black_market_regex_is_world_scoped_and_accepts_only_nonliving_puppets(self):
        made = self.engine.create_game("暗市补缺", "supreme_metal", "dao", 11006, preset_id="core")
        game = self._open_local_auction(made["id"])
        game.auction_state["status"] = "black_market"
        game.player.puppets = [
            {"id": "machine-1", "name": "玄铁机关犬", "type": "mechanical", "combat_power": 100},
            {"id": "corpse-1", "name": "无言炼尸", "type": "corpse", "combat_power": 100},
            {"id": "living-1", "name": "留魂活傀", "type": "living", "combat_power": 100},
        ]
        add_item(game.player, "spirit_stone", 100000)
        self.engine.store.save(game)
        before_age = game.player.age
        shown = self.engine.search_black_market(made["id"], ".*")
        self.assertTrue(shown["auction_system"]["black_market_results"])
        self.assertTrue(all(
            self.engine._is_world_market_good("human", row["kind"], row["content_id"])
            for row in shown["auction_system"]["black_market_results"]
        ))
        self.assertEqual(shown["player"]["age"], before_age)
        sold = self.engine.sell_black_market_asset(made["id"], "puppet", "machine-1")
        self.assertEqual(sold["player"]["age"], before_age)
        with self.assertRaisesRegex(ValueError, "不接收活傀"):
            self.engine.sell_black_market_asset(made["id"], "puppet", "living-1")

    def test_black_market_search_and_buy_supports_unique_crafting_and_formation_materials(self):
        made = self.engine.create_game("暗市寻材", "supreme_metal", "dao", 11061, preset_id="core")
        game = self._open_local_auction(made["id"])
        game.auction_state["status"] = "black_market"
        add_item(game.player, "spirit_stone", 1_000_000)
        self.engine.store.save(game)

        shown = self.engine.search_black_market(made["id"], "寒潭玄铁")
        result = next(row for row in shown["auction_system"]["black_market_results"] if row["kind"] == "crafting_material")
        bought = self.engine.buy_black_market_item(made["id"], result["id"])
        self.assertTrue(any(row["definition_id"] == "human_cold_iron" for row in bought["crafting_system"]["materials"]))

        formation_name = next(
            row["name"] for row in self.engine._formation_material_defs().values()
            if row.get("world") == "human"
        )
        shown = self.engine.search_black_market(made["id"], formation_name)
        result = next(row for row in shown["auction_system"]["black_market_results"] if row["kind"] == "formation_material")
        bought = self.engine.buy_black_market_item(made["id"], result["id"])
        self.assertTrue(any(row["definition_id"] == result["content_id"] and row["storage_id"] != result["formation_material_instance"]["id"] for row in bought["formation_system"]["materials"]))

        supply_name = next(
            row["name"] for row in self.engine._formation_maintenance_defs().values()
            if row.get("world") == "human"
        )
        shown = self.engine.search_black_market(made["id"], supply_name)
        result = next(row for row in shown["auction_system"]["black_market_results"] if row["kind"] == "formation_supply")
        bought = self.engine.buy_black_market_item(made["id"], result["id"])
        self.assertTrue(any(row["id"] == result["content_id"] for row in bought["formation_system"]["repair_supplies"]))

    def test_crossing_world_after_settlement_does_not_refund_closed_lots(self):
        made = self.engine.create_game("散场越界", "none", "dao", 11007, preset_id="mahayana")
        game = self._open_local_auction(made["id"])
        lot = game.auction_state["lots"][0]
        lot.update({"current_bidder": "player", "current_bidder_name": game.player.name})
        game.auction_state["consignments"] = [{"content_id": "mahayana_spirit_pill", "start_price": 100, "tier": 8}]
        self.engine._finish_auction(game, random.Random(9))
        stones_after_settlement = self.engine._spirit_stones(game.player)
        item_after_settlement = next(
            (item.quantity for item in game.player.inventory if item.id == "mahayana_spirit_pill"), 0
        )
        self.engine.store.save(game)
        self.engine.cross_world(made["id"], "human")
        crossed = self.engine.store.load(made["id"])
        self.assertEqual(self.engine._spirit_stones(crossed.player), stones_after_settlement)
        self.assertEqual(
            next((item.quantity for item in crossed.player.inventory if item.id == "mahayana_spirit_pill"), 0),
            item_after_settlement,
        )


if __name__ == "__main__":
    unittest.main()
