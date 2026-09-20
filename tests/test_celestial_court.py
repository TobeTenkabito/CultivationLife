import tempfile
import unittest
from pathlib import Path

from cultivation_life import RegisterCharacter, ResolveCombat, GameEngine
from cultivation_life.domain.celestial import (
    CELESTIAL_COURT,
    reconcile_celestial_state,
)
from cultivation_life.domain.character import LIFE
from cultivation_life.domain.cultivation import CULTIVATION
from cultivation_life.domain.definitions import StoryEffectDefinition
from cultivation_life.domain.world import LOCATION
from cultivation_life.domain.story import STORY_STATE
from cultivation_life.kernel.bus import SimulationContext
from cultivation_life.v1_facade import game_view


class V2CelestialCourtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temp.name) / "v2.sqlite3")
        self.game = self.engine.create_game("巡天者", seed=20260919)
        self.game_id = self.game["id"]
        self.actor_id = self.game["player"]["id"]

    def tearDown(self):
        self.temp.cleanup()

    def _enter_celestial(self):
        state = self.engine.store.load(self.game_id)
        location = state.entities.require(self.actor_id, LOCATION)
        location.update(
            world_id="celestial",
            location_id=self.engine.definitions.default_location("celestial"),
        )
        state.entities.put(self.actor_id, LOCATION, location)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(realm_id=self.engine.definitions.realms[9].id, layer=1)
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        life = state.entities.require(self.actor_id, LIFE)
        life["lifespan"] = None
        state.entities.put(self.actor_id, LIFE, life)
        reconcile_celestial_state(state, self.engine.definitions)
        self.engine.store.save(
            state, [], player_name="巡天者", expected_revision=state.revision,
        )

    def _mutate_court(self, callback):
        state = self.engine.store.load(self.game_id)
        court_id = state.entities.with_component(CELESTIAL_COURT)[0]
        court = state.entities.require(court_id, CELESTIAL_COURT)
        callback(court)
        state.entities.put(court_id, CELESTIAL_COURT, court)
        self.engine.store.save(
            state, [], player_name="巡天者", expected_revision=state.revision,
        )

    def test_court_is_world_isolated_and_initializes_with_49_seats(self):
        self.assertEqual(self.game["heavenly_court"], {"visible": False})
        self._enter_celestial()

        shown = self.engine.get_game(self.game_id)["heavenly_court"]

        self.assertTrue(shown["visible"])
        self.assertTrue(shown["initialized"])
        self.assertEqual(shown["seat_count"], 49)
        self.assertEqual(len(shown["offices"]), 7)
        self.assertTrue(shown["target_npcs"])
        self.assertTrue(all(row["realm_name"] for row in shown["target_npcs"]))

    def test_interactive_election_halts_and_resumes_timed_action(self):
        self._enter_celestial()
        self._mutate_court(lambda court: court.update(player_grade=4))
        years = self.engine.definitions.action_time(
            self.engine.definitions.realms[9].id, 1
        ) * 2

        paused = self.engine.perform_timed_action(self.game_id, "rest", years).game

        self.assertIsNotNone(paused["heavenly_court"]["election"])
        public = game_view(paused, {})["heavenly_court"]["election"]
        if paused["heavenly_court"]["election"]["player_candidate"]:
            self.assertIn("player", {
                candidate["id"] for candidate in public["candidates"]
            })
        self.assertIsNotNone(paused["action"]["active"])
        for _ in range(50):
            paused = self.engine.resolve_heavenly_election(
                self.game_id, "relationship"
            ).game
            if paused["heavenly_court"]["election"] is None:
                break
        self.assertIsNone(paused["heavenly_court"]["election"])
        self.assertIsNone(paused["action"]["active"])
        self.assertEqual(paused["heavenly_court"]["unit"], 2)

    def test_four_player_controlled_offices_guarantee_law_vote(self):
        self._enter_celestial()

        def control(court):
            for index, office_id in enumerate(court["offices"]):
                holder_id = self.actor_id if index < 4 else next(
                    key for key in court["officials"] if key != self.actor_id
                )
                court["offices"][office_id] = {
                    "holder_id": holder_id,
                    "holder_name": court["officials"][holder_id]["name"],
                    "start_unit": 0,
                    "end_unit": 7,
                    "votes": 13,
                }

        self._mutate_court(control)
        shown = self.engine.heavenly_court_action(
            self.game_id, "law:martial_gods", enact=True
        ).game["heavenly_court"]

        law = next(row for row in shown["laws"] if row["id"] == "martial_gods")
        self.assertTrue(law["active"])
        self.assertTrue(shown["last_vote"]["passed"])
        controlled = [
            office for office in shown["offices"]
            if office["holder"] and office["holder"]["holder_id"] == self.actor_id
        ]
        self.assertEqual(len(controlled), 4)
        self.assertTrue(all(row["holder"]["holder_name"] for row in controlled))
        public = game_view(self.engine.get_game(self.game_id), {})[
            "heavenly_court"
        ]
        self.assertEqual(sum(
            office["holder"]["holder_id"] == "player"
            for office in public["offices"] if office["holder"]
        ), 4)

    def test_celestial_combat_laws_apply_wanted_and_karma_rules(self):
        self._enter_celestial()
        state = self.engine.store.load(self.game_id)
        before = set(state.entities.with_component("core.identity"))
        self.engine.execute(self.game_id, RegisterCharacter(
            name="试法仙官", age=80, gender="male", race="human",
            spirit_root="supreme_fire", path="dao",
            realm_id=self.engine.definitions.realms[9].id,
            layer=1, world_id="celestial", lifespan=None,
        ))
        state = self.engine.store.load(self.game_id)
        target_id = next(iter(set(state.entities.with_component("core.identity")) - before))
        story = state.entities.require(self.actor_id, STORY_STATE)
        story["attributes"]["karma"] = 25.0
        state.entities.put(self.actor_id, STORY_STATE, story)
        court_id = state.entities.with_component(CELESTIAL_COURT)[0]
        court = state.entities.require(court_id, CELESTIAL_COURT)
        court["laws"]["universal_protection"] = True
        court["laws"]["immortal_slaughter"] = True
        court["laws"]["martial_gods"] = True
        state.entities.put(court_id, CELESTIAL_COURT, court)
        self.engine.store.save(
            state, [], player_name="巡天者", expected_revision=state.revision,
        )

        resolved = self.engine.execute(
            self.game_id, ResolveCombat(self.actor_id, target_id, "duel")
        ).game

        self.assertIn(self.actor_id, resolved["heavenly_court"]["wanted_ids"])
        self.assertEqual(resolved["story"]["attributes"]["karma"], 15.0)
        report = resolved["combat"]["last_report"]
        self.assertEqual(report["attacker"]["court_damage_multiplier"], 1.1)

    def test_story_court_merit_effect_uses_authoritative_court_state(self):
        self._enter_celestial()
        state = self.engine.store.load(self.game_id)
        context = SimulationContext(state, self.engine.commands.event_bus)

        outcome = self.engine.story_effects.execute(
            context,
            self.actor_id,
            StoryEffectDefinition("add_court_merit", {"value": 17}),
            {},
        )

        court_id = state.entities.with_component(CELESTIAL_COURT)[0]
        court = state.entities.require(court_id, CELESTIAL_COURT)
        self.assertEqual(court["player_merit"], 17)
        self.assertIn("+17", outcome.summary)


if __name__ == "__main__":
    unittest.main()
