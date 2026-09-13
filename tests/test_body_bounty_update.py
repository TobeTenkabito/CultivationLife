import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import MARKET_GOODS, TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine, encode_rng
from cultivation_life.event_repository import EventRepository
from cultivation_life.models import SectNpc
from cultivation_life.rules import assign_technique, max_hp, max_mp, technique_environment_multiplier


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class ScriptedRng:
    """Minimal deterministic RNG for resolving one pursuit skirmish."""

    def __init__(self, values):
        self.values = iter(values)

    def randint(self, low, high):
        return min(2, high)

    def sample(self, population, count):
        return list(population)[:count]

    def random(self):
        return next(self.values)


class BodyAndBountyUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def test_body_technique_is_root_agnostic_and_training_is_manual(self):
        created = self.engine.create_game("炼体修士", "supreme_fire", "dao", 1201, "fire")
        game = self.engine.store.load(created["id"])
        technique = TECHNIQUE_CATALOG["TECH_BODY_MORTAL"]
        self.assertEqual(technique.category, "body")
        self.assertEqual(technique.element, "neutral")
        assign_technique(game.player, technique, "body")
        self.engine.store.save(game)

        shown = self.engine.advance(created["id"], "body_train")
        self.assertGreater(shown["body_cultivation"]["progress"], 0)
        self.assertEqual(shown["player"]["body_training"], 0)
        self.assertEqual(shown["player"]["technique_slots"]["body"]["id"], "TECH_BODY_MORTAL")

    def test_body_training_applies_environment_only_to_new_progress(self):
        human = self.engine.create_game("人界炼体", "supreme_fire", "demonic", 1211)
        demon = self.engine.create_game(
            "魔界炼体", "supreme_fire", "demonic", 1211, start_world="demon",
        )
        for created in (human, demon):
            game = self.engine.store.load(created["id"])
            assign_technique(game.player, TECHNIQUE_CATALOG["TECH_BODY_MORTAL"], "body")
            self.engine.store.save(game)
        self.engine.advance(human["id"], "body_train")
        self.engine.advance(demon["id"], "body_train")
        human_progress = self.engine.store.load(human["id"]).player.body_progress
        demon_progress = self.engine.store.load(demon["id"]).player.body_progress
        expected_ratio = (
            technique_environment_multiplier(TECHNIQUE_CATALOG["TECH_BODY_MORTAL"], "demon")
            / technique_environment_multiplier(TECHNIQUE_CATALOG["TECH_BODY_MORTAL"], "human")
        )
        self.assertAlmostEqual(demon_progress / human_progress, expected_ratio)
        self.assertEqual(self.engine.get_game(human["id"])["player"]["body_training"], 0)
        self.assertEqual(self.engine.get_game(demon["id"])["player"]["body_training"], 0)

    def test_body_layer_twenty_one_failure_starts_low_rate_pity(self):
        created = self.engine.create_game("百炼冲层", "none", "dao", 1202)
        game = self.engine.store.load(created["id"])
        assign_technique(game.player, TECHNIQUE_CATALOG["TECH_BODY_MORTAL"], "body")
        game.player.body_training = 20
        game.player.body_progress = self.engine._body_progress_required(game.player)
        game.player.awaiting_body_breakthrough = True
        game.rng_state = encode_rng(random.Random(2))  # first roll ~= .956, above the 22% base
        self.engine.store.save(game)

        shown = self.engine.body_breakthrough(created["id"])
        self.assertEqual(shown["player"]["body_training"], 20)
        player = self.engine.store.load(created["id"]).player
        next_chance = self.engine._body_breakthrough_chance(player)
        self.assertEqual(next_chance["failures"], 1)
        self.assertAlmostEqual(next_chance["pity_bonus"], 0.025)

    def test_body_milestones_and_optimal_state_raise_normal_breakthrough(self):
        created = self.engine.create_game("内外兼修", "supreme_wood", "dao", 1203, "wood")
        player = self.engine.store.load(created["id"]).player
        player.realm_index, player.layer = 2, 1
        player.body_training = 0
        player.hp, player.mp = max_hp(player) * 0.79, max_mp(player) * 0.79
        unprepared = self.engine._breakthrough_chance(player, major=False)
        player.hp, player.mp = max_hp(player), max_mp(player)
        prepared = self.engine._breakthrough_chance(player, major=False)
        player.body_training = 40
        player.hp, player.mp = max_hp(player), max_mp(player)
        body_hardened = self.engine._breakthrough_chance(player, major=False)

        self.assertAlmostEqual(prepared["final"] - unprepared["final"], 0.05)
        self.assertAlmostEqual(body_hardened["body_training_bonus"], 0.02)
        self.assertAlmostEqual(body_hardened["final"] - prepared["final"], 0.02)
        player.body_training = 50
        self.assertAlmostEqual(self.engine._body_tribulation_damage_reduction(player), 0.001)
        player.body_training = 100
        self.assertAlmostEqual(self.engine._body_tribulation_damage_reduction(player), 0.011)

    def test_every_body_manual_is_sold_or_granted_by_an_event(self):
        sold = {row["content_id"] for row in MARKET_GOODS if row["kind"] == "technique"}
        body_manuals = {key for key, value in TECHNIQUE_CATALOG.items() if value.category == "body"}
        event_rewards = {
            effect["technique_id"]
            for event in EventRepository.load(SOURCE_ROOT / "content").events
            for choice in event.get("choices", [])
            for effect in choice.get("effects", [])
            if effect.get("type") == "learn_technique"
        }
        self.assertGreaterEqual(len(body_manuals), 6)
        self.assertTrue(body_manuals <= sold | event_rewards)

    def test_player_bounty_uses_real_hunters_and_can_cost_their_lives(self):
        created = self.engine.create_game("号令同族", "none", "dao", 1204, preset_id="mahayana")
        game = self.engine.store.load(created["id"])
        target = SectNpc(
            "bounty_target", "吞岳老魔", "通缉重犯", 8, 9, 18000, None,
            spirit_root="otherworld", path="demonic", race="stoneborn", world="spirit",
            combat_factor=30.0,
        )
        game.notable_npcs[target.id] = target
        order = {
            "id":"bounty_test", "target_id":target.id, "name":target.name,
            "world":"spirit", "status":"active", "authority":"race",
            "issuer_name":"人族大乘议会", "attempts":0,
        }
        game.player_bounties.append(order)
        living_before = {
            npc.id for npc in [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]
            if npc.alive and npc.world == "spirit" and npc.race == "human" and npc.id != target.id
        }

        # pursuit loses; target is overwhelmingly stronger, then both kill checks pass
        self.engine._advance_player_bounties(game, ScriptedRng([0.99, 0.0, 0.0]))
        living_after = {
            npc.id for npc in [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]
            if npc.alive and npc.world == "spirit" and npc.race == "human"
        }
        self.assertEqual(order["status"], "active")
        self.assertLess(len(living_after & living_before), len(living_before))
        record = game.history[-1]
        self.assertEqual(record.event_id, "SYS_PLAYER_BOUNTY_COUNTERED")
        self.assertTrue(record.state_diff["hunter_ids"])
        self.assertIn("通缉令仍然有效", record.summary)


if __name__ == "__main__":
    unittest.main()
