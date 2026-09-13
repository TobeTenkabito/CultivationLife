import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.engine import GameEngine
from cultivation_life.models import HistoryRecord
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.simulation import ActionUnitLedger
from cultivation_life.world_state import choose_weighted_race, race_pair


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class WorldStateUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def test_action_unit_charges_negative_resources_once_but_keeps_annual_gains(self):
        created = self.engine.create_game("百年账本", "none", "dao", 701, preset_id="mahayana")
        player = self.engine.store.load(created["id"]).player
        player.hp = max_hp(player) * 0.5
        player.mp = max_mp(player) * 0.5
        hp_before, mp_before = player.hp, player.mp
        ledger = ActionUnitLedger("travel", 100)
        for _ in range(100):
            ledger.begin_year()
            self.engine._apply_action_resources(player, "travel", ledger.claim_resource_cost())
        self.assertAlmostEqual(player.hp, hp_before - max_hp(player) * 0.02)
        self.assertAlmostEqual(player.mp, mp_before - max_mp(player) * 0.04)

        player.hp = max_hp(player) * 0.2
        rest = ActionUnitLedger("rest", 5)
        for _ in range(5):
            rest.begin_year()
            self.engine._apply_action_resources(player, "rest", rest.claim_resource_cost())
        self.assertGreater(player.hp, max_hp(player) * 0.2)

    def test_disposable_encounters_use_bounded_fifo_but_ranking_candidate_is_promoted(self):
        created = self.engine.create_game("过客成名", "none", "dao", 702, preset_id="core")
        game = self.engine.store.load(created["id"])
        first_id = None
        for index in range(40):
            target = {
                "target_name": f"路人{index}", "target_power": 500.0, "primary_power": 500.0,
                "target_realm_index": 3, "target_layer": 1, "combat_type": "cultivator",
                "race": "human", "world": "human",
                "members": [{"name": f"路人{index}", "power": 500.0, "realm_index": 3, "layer": 1, "race": "human"}],
            }
            self.engine._cache_encounter_target(game, target, random.Random(index))
            if index == 0:
                first_id = target["members"][0]["npc_id"]
        self.assertEqual(len(game.encounter_npc_cache), 36)
        self.assertNotIn(first_id, {row["id"] for row in game.encounter_npc_cache})
        self.assertFalse(game.notable_npcs)

        spirit = self.engine.create_game("天榜见证", "none", "dao", 703, preset_id="mahayana")
        spirit_game = self.engine.store.load(spirit["id"])
        target = {
            "target_name": "无名绝巅", "target_power": 10**12, "primary_power": 10**12,
            "target_realm_index": 8, "target_layer": 9, "combat_type": "cultivator",
            "race": "starborn", "world": "spirit",
            "members": [{"name": "无名绝巅", "power": 10**12, "realm_index": 8, "layer": 9, "race": "starborn"}],
        }
        self.engine._cache_encounter_target(spirit_game, target, random.Random(9))
        npc_id = target["members"][0]["npc_id"]
        self.assertIn(npc_id, spirit_game.notable_npcs)
        ranking = self.engine._public_spirit_ranking(spirit_game)
        self.assertEqual(ranking["entries"][0]["id"], npc_id)

    def test_companion_has_combat_power_can_join_party_and_can_enter_ranking(self):
        created = self.engine.create_game("并肩问道", "none", "dao", 704, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        companion = self.engine._generated_relationship(game.player, "companion", random.Random(4))
        companion.update(world="spirit", race="human", realm_index=8, layer=9, affinity=80)
        game.player.dao_companion = companion
        self.engine.store.save(game)
        shown = self.engine.get_game(created["id"])
        self.assertGreater(shown["dao_companion"]["combat_power"], 0)
        self.assertTrue(any(row["id"] == companion["id"] for row in shown["spirit_ranking"]["entries"]))
        joined = self.engine.manage_party(created["id"], companion["id"], "invite")
        self.assertTrue(joined["dao_companion"]["in_party"])
        self.assertEqual(joined["party"][0]["id"], companion["id"])

    def test_race_diplomacy_is_visible_and_biases_wartime_encounters(self):
        created = self.engine.create_game("观万族", "none", "dao", 705, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        key = race_pair("human", "starborn")
        game.race_relations[key] = {"affinity": -70, "status": "war", "since_age": game.player.age}
        game.history.append(HistoryRecord(
            "SYS_RACE_DIPLOMACY", 1, game.player.age, "灵界族群大事", "宣战", "war",
            "人族与星裔族宣战。", {"races": ["human", "starborn"]},
            ["system", "diplomacy", "race", "world_news", "world:spirit"],
        ))
        public = self.engine._public_race_system(game)
        star_relation = next(row for row in public["races"]["human"]["relations"] if row["race"] == "starborn")
        self.assertEqual(star_relation["status"], "war")
        self.assertIn("宣战", public["races"]["human"]["recent_events"][0]["summary"])

        counts = {"starborn": 0, "moonfolk": 0}
        for seed in range(300):
            race = choose_weighted_race(counts, "human", game.race_relations, random.Random(seed))
            counts[race] += 1
        self.assertGreater(counts["starborn"], counts["moonfolk"] * 2)


if __name__ == "__main__":
    unittest.main()
