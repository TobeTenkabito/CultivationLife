import json
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import ContentRegistry
from cultivation_life.engine import GameEngine
from cultivation_life.event_repository import EventRepository


SOURCE_ROOT = Path(__file__).resolve().parent.parent
DEMON_CHAINS = {
    "demon_blood_river": 4,
    "demon_corpse_moon": 5,
    "demon_rift_beast": 5,
}
TRUE_DEMON_CHAINS = {
    "true_demon_black_sun": 5,
    "true_demon_fallen_star": 5,
    "true_demon_abyss_axis": 6,
}
STORY_REWARDS = {
    "blood_river_heart_scale", "corpse_moon_orb", "rift_demon_bone", "sky_devour_breath",
    "black_sun_origin_flame", "star_womb_breath", "fallen_star_marrow", "abyss_demon_heart",
}


class DemonWorldStoryExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(SOURCE_ROOT / "content")
        cls.events = EventRepository.load(SOURCE_ROOT / "content")

    def test_each_world_has_six_ambient_events_and_three_complete_chains(self):
        demon_common = [event for event in self.events.events if "demon_common" in event.get("tags", [])]
        true_common = [event for event in self.events.events if "true_demon_common" in event.get("tags", [])]
        self.assertEqual(len(demon_common), 6)
        self.assertEqual(len(true_common), 6)
        self.assertTrue(all("world:demon" in event["tags"] for event in demon_common))
        self.assertTrue(all("world:true_demon" in event["tags"] for event in true_common))

        for chain, expected_count in {**DEMON_CHAINS, **TRUE_DEMON_CHAINS}.items():
            members = [event for event in self.events.events if chain in event.get("tags", [])]
            self.assertEqual(len(members), expected_count, chain)
            self.assertEqual(sum("probability_gate" in event["tags"] for event in members), 1, chain)
            self.assertTrue(all(len(event["choices"]) >= 3 for event in members), chain)

    def test_new_events_are_strictly_scoped_to_their_own_world(self):
        for chain in DEMON_CHAINS:
            members = [event for event in self.events.events if chain in event.get("tags", [])]
            for event in members:
                self.assertIn("world:demon", event["tags"])
                self.assertNotIn("world:true_demon", event["tags"])
        for chain in TRUE_DEMON_CHAINS:
            members = [event for event in self.events.events if chain in event.get("tags", [])]
            for event in members:
                self.assertIn("world:true_demon", event["tags"])
                self.assertNotIn("world:demon", event["tags"])

    def test_each_chain_is_a_closed_reachable_graph(self):
        for chain, expected_count in {**DEMON_CHAINS, **TRUE_DEMON_CHAINS}.items():
            members = {event["id"]: event for event in self.events.events if chain in event.get("tags", [])}
            start = next(event for event in members.values() if "probability_gate" in event["tags"])
            reached = set()
            pending = [start["id"]]
            while pending:
                event_id = pending.pop()
                if event_id in reached:
                    continue
                reached.add(event_id)
                event = members[event_id]
                for choice in event["choices"]:
                    for effect in choice.get("effects", []):
                        queued = effect.get("event_id") if effect.get("type") == "queue_event" else None
                        if queued in members:
                            pending.append(queued)
            self.assertEqual(len(reached), expected_count, chain)

    def test_story_rewards_cannot_leak_into_any_market(self):
        market = json.loads((SOURCE_ROOT / "content" / "market.json").read_text(encoding="utf-8"))
        sold_ids = {row["content_id"] for row in market["goods"]}
        self.assertTrue(STORY_REWARDS <= set(self.registry.items))
        self.assertFalse(STORY_REWARDS & sold_ids)
        for item_id in STORY_REWARDS:
            self.assertIn("story", self.registry.items[item_id].tags)

    def test_every_new_fixed_combat_has_a_valid_story_scenario(self):
        new_chain_tags = set(DEMON_CHAINS) | set(TRUE_DEMON_CHAINS)
        combat_events = set()
        for event in self.events.events:
            if not (new_chain_tags & set(event.get("tags", []))):
                continue
            for choice in event["choices"]:
                if any(
                    effect.get("type") == "attribute_check"
                    and any(check.get("stat") == "combat_power" for check in effect.get("checks", []))
                    for effect in choice.get("effects", [])
                ):
                    combat_events.add(event["id"])
        self.assertTrue(combat_events)
        for event_id in combat_events:
            scenario = self.registry.story_combat_scenarios[event_id]
            self.assertAlmostEqual(sum(member["share"] for member in scenario["enemy_members"]), 1.0)
            self.assertGreaterEqual(len(scenario["story_beats"]), 4)

    def test_all_six_chains_can_reach_a_rewarding_completion(self):
        routes = {
            "EVT_DEMON_BLOOD_RIVER_001": ("upstream", "clear_beasts", "slay_brood", "renew"),
            "EVT_DEMON_CORPSE_MOON_001": ("follow", "read", "believe", "joint", "inherit"),
            "EVT_DEMON_RIFT_BEAST_001": ("listen", "warn", "turn_array", "open_path", "bone"),
            "EVT_TRUE_DEMON_BLACK_SUN_001": ("tribe", "negotiate", "rebind", "array", "pact"),
            "EVT_TRUE_DEMON_FALLEN_STAR_001": ("guard", "mark", "bargain", "bear", "guard"),
            "EVT_TRUE_DEMON_ABYSS_AXIS_001": ("records", "show", "map", "repair", "fight", "covenant"),
        }
        expected_flags = {
            "demon_blood_river_completed", "demon_corpse_moon_completed", "demon_rift_beast_completed",
            "true_demon_black_sun_completed", "true_demon_fallen_star_completed",
            "true_demon_abyss_axis_completed",
        }
        with tempfile.TemporaryDirectory() as directory:
            engine = GameEngine(SOURCE_ROOT, Path(directory) / "saves")
            created = engine.create_game("六境魔行", "supreme_fire", "demonic", 6601, start_world="demon")
            for offset, (start_id, choices) in enumerate(routes.items()):
                game = engine.store.load(created["id"])
                game.player.realm_index = 8
                game.player.layer = 9
                game.player.faction_combat_bonus = 100_000_000
                game.player.hp = 100_000_000
                game.player.mp = 100_000_000
                game.pending_event = engine._instantiate_event(
                    engine.events_by_id[start_id], game, random.Random(6601 + offset),
                )
                engine.store.save(game)
                for choice_id in choices:
                    result = engine.choose(created["id"], choice_id)
            self.assertTrue(expected_flags <= set(result["player"]["story_flags"]))
            inventory = {item["id"] for item in result["player"]["inventory"]}
            learned = {technique["id"] for technique in result["player"]["known_techniques"]}
            self.assertIn("rift_demon_bone", inventory)
            self.assertIn("abyss_demon_heart", inventory)
            self.assertIn("TECH_BLOOD_RIVER_REVERSION", learned)
            self.assertIn("TECH_CORPSE_MOON_SOUL", learned)
            self.assertIn("TECH_BLACK_SUN_TRUE_FLAME", learned)
            self.assertIn("TECH_STAR_DEVOURING_BODY", learned)


if __name__ == "__main__":
    unittest.main()
