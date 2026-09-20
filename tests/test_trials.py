from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import FormRelationship, GrantItem, RegisterCharacter, GameEngine
from cultivation_life.domain.combat import CONDITION
from cultivation_life.domain.cultivation import CULTIVATION
from cultivation_life.domain.story import STORY_STATE
from cultivation_life.domain.trials import PERIODIC_THUNDER_DUE, TRIAL
from cultivation_life.domain.world import LOCATION
from cultivation_life.kernel.model import EventScope


class V2TrialRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.directory.name) / "v2.sqlite3")
        game = self.engine.create_game("渡劫者", seed=880055)
        self.game_id = game["id"]
        self.actor_id = game["player"]["id"]

    def tearDown(self):
        self.directory.cleanup()

    def _save(self, state) -> None:
        self.engine.store.save(
            state, [], player_name="渡劫者", expected_revision=state.revision
        )

    def _prepare_breakthrough(
        self, *, realm_id: str, layer: int, path: str = "dao",
        karma: float = 0.0, sha_qi: float = 0.0,
    ) -> None:
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(
            realm_id=realm_id,
            layer=layer,
            path=path,
            opportunity=10_000_000.0,
            bottleneck="major" if layer == 9 else "minor",
            heart_demon=0.0,
        )
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        story = state.entities.require(self.actor_id, STORY_STATE)
        story["attributes"].update(karma=karma, sha_qi=sha_qi)
        state.entities.put(self.actor_id, STORY_STATE, story)
        self._save(state)

    def _force_successful_roll(self, realm_index: int):
        table = self.engine.definitions.breakthrough["major_base"][str(realm_index)]
        previous = dict(table)
        for key in table:
            table[key] = 1.0
        return table, previous

    def test_nonlethal_trial_failure_is_persisted_and_releases_interaction(self):
        self._prepare_breakthrough(realm_id="nascent", layer=9, karma=1_000)
        table, previous = self._force_successful_roll(4)
        try:
            started = self.engine.attempt_breakthrough(self.game_id)
        finally:
            table.clear()
            table.update(previous)
        self.assertEqual(started.game["trial"]["active"]["kind"], "traditional")

        # Every choice is its own committed command, so this also proves that a
        # trial survives a save/load boundary between stages.
        self.engine.choose(self.game_id, "endure")
        failed = self.engine.choose(self.game_id, "face_karma")
        self.assertTrue(failed.game["player"]["alive"])
        self.assertIsNone(failed.game["pending_event"])
        self.assertIsNone(failed.game["trial"]["active"])
        self.assertEqual(failed.game["trial"]["history"][-1]["result"], "failed")
        self.assertEqual(failed.game["player"]["cultivation"]["realm_id"], "nascent")
        self.assertEqual(failed.game["player"]["cultivation"]["layer"], 9)
        self.assertEqual(failed.game["player"]["cultivation"]["heart_demon"], 8.0)

    def test_heavenly_and_heavenly_demon_trials_complete_all_stages(self):
        for path, expected_kind, choices in (
            ("dao", "heavenly", ("receive", "break", "karma", "sha", "heart")),
            ("demonic", "heavenly_demon", ("fight",) * 5),
        ):
            with self.subTest(path=path):
                # Use a fresh game for the second path so trial history and
                # condition drain cannot leak between scenarios.
                if path == "demonic":
                    other = self.engine.create_game("天魔修", seed=880056, path="demonic")
                    self.game_id = other["id"]
                    self.actor_id = other["player"]["id"]
                self._prepare_breakthrough(realm_id="void", layer=9, path=path)
                self.engine.execute(
                    self.game_id, GrantItem(self.actor_id, "chaos_dao_bell", 1)
                )
                table, previous = self._force_successful_roll(6)
                try:
                    started = self.engine.attempt_breakthrough(self.game_id)
                finally:
                    table.clear()
                    table.update(previous)
                self.assertEqual(started.game["trial"]["active"]["kind"], expected_kind)
                completed = started
                for choice in choices:
                    completed = self.engine.choose(self.game_id, choice)
                self.assertIsNone(completed.game["trial"]["active"])
                self.assertEqual(
                    completed.game["trial"]["history"][-1]["result"], "completed"
                )
                self.assertEqual(
                    completed.game["player"]["cultivation"]["realm_id"], "integration"
                )
                self.assertEqual(completed.game["combat"]["snapshot"]["hp_ratio"], 1.0)
                self.assertEqual(completed.game["combat"]["snapshot"]["mp_ratio"], 1.0)

    def test_lethal_trial_failure_clears_active_trial_when_character_dies(self):
        self._prepare_breakthrough(realm_id="void", layer=9, karma=10_000)
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "chaos_dao_bell", 1)
        )
        table, previous = self._force_successful_roll(6)
        try:
            self.engine.attempt_breakthrough(self.game_id)
        finally:
            table.clear()
            table.update(previous)
        self.engine.choose(self.game_id, "receive")
        self.engine.choose(self.game_id, "break")
        failed = self.engine.choose(self.game_id, "karma")
        self.assertFalse(failed.game["player"]["alive"])
        self.assertIsNone(failed.game["trial"]["active"])
        self.assertEqual(failed.game["trial"]["history"][-1]["result"], "failed")

    def test_periodic_thunder_is_scheduled_resolved_and_persisted(self):
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(realm_id="void", layer=1)
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        trial = state.entities.require(self.actor_id, TRIAL)
        trial["periodic"].update(
            count=0, power=1000.0, next_year=1,
        )
        state.scheduler.cancel(
            lambda event: event.event_type == PERIODIC_THUNDER_DUE
        )
        scheduled = state.scheduler.schedule(
            due_year=1,
            event_type=PERIODIC_THUNDER_DUE,
            source="test",
            scope=EventScope.entity(self.actor_id),
            payload={"entity_id": self.actor_id},
        )
        trial["periodic"]["schedule_sequence"] = scheduled.sequence
        state.entities.put(self.actor_id, TRIAL, trial)
        self._save(state)

        started = self.engine.perform_timed_action(self.game_id, "rest", 1)
        self.assertEqual(started.game["clock"]["year"], 1)
        self.assertEqual(
            started.game["pending_event"]["id"], "EVT_PERIODIC_THUNDER_001"
        )
        self.assertTrue(started.game["tribulation"]["active"])

        for event_id in (
            "EVT_PERIODIC_THUNDER_002", "EVT_PERIODIC_THUNDER_003",
        ):
            advanced = self.engine.choose(self.game_id, "strike")
            self.assertEqual(advanced.game["pending_event"]["id"], event_id)
        completed = self.engine.choose(self.game_id, "strike")
        self.assertTrue(completed.game["player"]["alive"])
        self.assertFalse(completed.game["tribulation"]["active"])
        self.assertEqual(completed.game["tribulation"]["count"], 1)
        self.assertEqual(completed.game["tribulation"]["power"], 2000.0)
        self.assertEqual(completed.game["tribulation"]["years_remaining"], 3000)

        restored = self.engine.get_game(self.game_id)
        self.assertEqual(restored["tribulation"], completed.game["tribulation"])


class V2AscensionTrialTests(unittest.TestCase):
    CELESTIAL_CHOICES = (
        "endure", "cross", "receive", "sever", "destroy",
        "receive", "anchor", "answer", "ascend",
    )
    ASURA_CHOICES = (
        "endure", "cross", "receive", "master", "devour",
        "receive", "command", "answer", "ascend",
    )

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.directory.cleanup()

    def _engine(self, *, path: str, start_world: str):
        engine = GameEngine(Path(self.directory.name) / f"{path}.sqlite3")
        game = engine.create_game(
            f"{path}飞升者", seed=99117, path=path, start_world=start_world
        )
        return engine, game["id"], game["player"]["id"]

    def _save(self, engine, game_id, state, name="飞升者") -> None:
        engine.store.save(state, [], player_name=name, expected_revision=state.revision)

    def _prepare_ascension(
        self, engine, game_id: str, actor_id: str, *, world_id: str,
        path: str, sha_qi: float = 0.0,
    ) -> None:
        state = engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation.update(
            realm_id="mahayana", layer=9, path=path,
            opportunity=10_000_000.0, bottleneck="major", heart_demon=0.0,
        )
        if path == "demonic":
            cultivation["qi_experience"]["demon"] = 25.0 * 30 * 30
        state.entities.put(actor_id, CULTIVATION, cultivation)
        location = state.entities.require(actor_id, LOCATION)
        location.update(
            world_id=world_id,
            location_id=engine.definitions.default_location(world_id),
        )
        state.entities.put(actor_id, LOCATION, location)
        story = state.entities.require(actor_id, STORY_STATE)
        story["attributes"].update(karma=0.0, sha_qi=sha_qi)
        state.entities.put(actor_id, STORY_STATE, story)
        self._save(engine, game_id, state)

    def _add_companion(
        self, engine, game_id: str, actor_id: str, *, world_id: str, path: str,
    ) -> str:
        engine.execute(game_id, RegisterCharacter(
            "同行道侣", 100, "female", "human", "otherworld", path,
            "mahayana", 9, world_id,
        ))
        state = engine.store.load(game_id)
        companion_id = next(
            entity_id for entity_id in state.entities.with_component("core.identity")
            if entity_id != actor_id
            and state.entities.require(entity_id, "core.identity")["name"] == "同行道侣"
        )
        engine.execute(
            game_id, FormRelationship(actor_id, companion_id, "dao_companion")
        )
        return companion_id

    def _complete(self, engine, game_id: str, choices: tuple[str, ...]):
        result = None
        for choice in choices:
            result = engine.choose(game_id, choice)
        return result

    def test_celestial_nine_stage_trial_commits_shared_cleanup_transaction(self):
        engine, game_id, actor_id = self._engine(path="dao", start_world="spirit")
        self._prepare_ascension(
            engine, game_id, actor_id, world_id="spirit", path="dao"
        )
        companion_id = self._add_companion(
            engine, game_id, actor_id, world_id="spirit", path="dao"
        )
        started = engine.begin_ascension_trial(
            game_id, "celestial", invited_ids=(companion_id,)
        )
        self.assertEqual(started.game["trial"]["active"]["kind"], "celestial_ascension")
        # Reload through the public read boundary before advancing the trial.
        self.assertEqual(engine.get_game(game_id)["pending_event"]["id"], "EVT_CELESTIAL_ASCENSION_001")
        completed = self._complete(engine, game_id, self.CELESTIAL_CHOICES)

        self.assertEqual(completed.game["world"]["world_id"], "celestial")
        self.assertEqual(completed.game["player"]["cultivation"]["realm_id"], "true_immortal")
        self.assertEqual(completed.game["combat"]["snapshot"]["mp_ratio"], 0.0)
        self.assertIsNone(completed.game["tribulation"]["next_age"])
        transaction = completed.game["world"]["transition"]["last_transaction"]
        self.assertEqual(transaction["status"], "committed")
        self.assertEqual(
            set(transaction["acknowledgements"]),
            {
                "relations", "factions", "economy", "assets", "auction",
                "artifacts", "combat", "party", "demonic",
            },
        )
        state = engine.store.load(game_id)
        self.assertEqual(
            state.entities.require(companion_id, LOCATION)["world_id"], "celestial"
        )

    def test_asura_nine_stage_trial_enforces_resources_then_ascends(self):
        engine, game_id, actor_id = self._engine(path="demonic", start_world="demon")
        self._prepare_ascension(
            engine, game_id, actor_id,
            world_id="true_demon", path="demonic", sha_qi=80.0,
        )
        started = engine.begin_ascension_trial(game_id, "asura")
        self.assertEqual(started.game["trial"]["active"]["kind"], "asura_ascension")
        completed = self._complete(engine, game_id, self.ASURA_CHOICES)
        self.assertEqual(completed.game["world"]["world_id"], "asura")
        self.assertEqual(completed.game["player"]["cultivation"]["realm_id"], "true_immortal")
        self.assertEqual(completed.game["combat"]["snapshot"]["hp_ratio"], 1.0)
        self.assertEqual(completed.game["combat"]["snapshot"]["mp_ratio"], 1.0)
        self.assertEqual(completed.game["trial"]["history"][-1]["result"], "completed")

    def test_failed_ascension_is_lethal_and_never_commits_world_transition(self):
        engine, game_id, actor_id = self._engine(path="dao", start_world="spirit")
        self._prepare_ascension(
            engine, game_id, actor_id, world_id="spirit", path="dao"
        )
        state = engine.store.load(game_id)
        condition = state.entities.require(actor_id, CONDITION)
        condition["hp_ratio"] = 0.5
        state.entities.put(actor_id, CONDITION, condition)
        self._save(engine, game_id, state)
        engine.begin_ascension_trial(game_id, "celestial")
        failed = engine.choose(game_id, "endure")
        self.assertFalse(failed.game["player"]["alive"])
        self.assertEqual(failed.game["world"]["world_id"], "spirit")
        self.assertIsNone(
            failed.game["world"]["transition"]["last_transaction"]
        )
        self.assertIsNone(failed.game["trial"]["active"])


if __name__ == "__main__":
    unittest.main()
