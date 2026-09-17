from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life.v2 import (
    AttemptBreakthrough,
    EnterConcubineStatus,
    FormRelationship,
    GrantTechnique,
    ManageConcubine,
    ManageConcubineStatus,
    RegisterCharacter,
    V2GameEngine,
)
from cultivation_life.v2.domain.actions import ACTION_RUNTIME
from cultivation_life.v2.domain.combat import CONDITION
from cultivation_life.v2.domain.cultivation import CULTIVATION


class V2ConcubineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.temporary.name) / "v2.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _register(
        self,
        game_id: str,
        name: str,
        *,
        gender: str = "female",
        realm_id: str = "mortal",
        layer: int = 1,
    ) -> str:
        before = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        self.engine.execute(
            game_id,
            RegisterCharacter(
                name=name,
                age=20,
                gender=gender,
                race="human",
                spirit_root="supreme_wood",
                path="dao",
                realm_id=realm_id,
                layer=layer,
                world_id="human",
            ),
        )
        after = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        return (after - before).pop()

    def test_recruitment_creates_a_distinct_concubine_relationship(self):
        game = self.engine.create_game("名册", seed=2)
        actor_id = game["player"]["id"]
        target_id = self._register(game["id"], "青桃")

        recruited = self.engine.execute(
            game["id"], ManageConcubine(actor_id, target_id, "recruit")
        )
        event = next(
            row for row in recruited.events
            if row["event_type"] == "relationship.concubine.recruited"
        )
        self.assertTrue(event["payload"]["accepted"])
        self.assertEqual(len(recruited.game["concubine_system"]["concubines"]), 1)
        public = recruited.game["concubine_system"]["concubines"][0]
        self.assertEqual(public["realm_id"], "mortal")
        self.assertEqual(public["spirit_root"], "supreme_wood")
        self.assertIn("lifespan", public)
        self.assertIn("main_technique_id", public)
        self.assertFalse(any(
            row["kind"] == "dao_companion"
            for row in recruited.game["relationships"]
        ))

    def test_cauldron_cooldown_live_view_and_breakthrough_bonus_consumption(self):
        game = self.engine.create_game("合欢", seed=2202)
        actor_id = game["player"]["id"]
        target_id = self._register(game["id"], "红绡")
        self.engine.execute(
            game["id"], FormRelationship(actor_id, target_id, "concubine")
        )
        self.engine.execute(
            game["id"], GrantTechnique(actor_id, "TECH_HEHUAN_SECRET", True)
        )
        state = self.engine.store.load(game["id"])
        condition = state.entities.require(actor_id, CONDITION)
        condition.update(hp_ratio=0.5, mp_ratio=0.5)
        state.entities.put(actor_id, CONDITION, condition)
        self.engine.store.save(
            state, [], player_name="合欢", expected_revision=state.revision
        )

        used = self.engine.execute(
            game["id"], ManageConcubine(actor_id, target_id, "cauldron")
        ).game
        self.assertEqual(
            used["concubine_system"]["cauldron_breakthrough_bonus"], 0.01
        )
        self.assertFalse(
            used["concubine_system"]["concubines"][0]["can_use_cauldron"]
        )
        self.assertAlmostEqual(used["combat"]["snapshot"]["hp_ratio"], 0.74)
        with self.assertRaisesRegex(ValueError, "本行动单位"):
            self.engine.execute(
                game["id"], ManageConcubine(actor_id, target_id, "cauldron")
            )

        state = self.engine.store.load(game["id"])
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation.update(opportunity=1_000_000.0, bottleneck="major")
        state.entities.put(actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="合欢", expected_revision=state.revision
        )
        broken = self.engine.execute(
            game["id"], AttemptBreakthrough(actor_id)
        ).game
        self.assertEqual(
            broken["concubine_system"]["cauldron_breakthrough_bonus"], 0.0
        )

        state = self.engine.store.load(game["id"])
        runtime = state.entities.require(actor_id, ACTION_RUNTIME)
        runtime["next_sequence"] = int(runtime["next_sequence"]) + 1
        state.entities.put(actor_id, ACTION_RUNTIME, runtime)
        life = state.entities.require(target_id, "character.life")
        life["alive"] = False
        life["death_reason"] = "test"
        state.entities.put(target_id, "character.life", life)
        self.engine.store.save(
            state, [], player_name="合欢", expected_revision=state.revision
        )
        unavailable = self.engine.get_game(game["id"])
        self.assertFalse(
            unavailable["concubine_system"]["concubines"][0]["can_use_cauldron"]
        )
        dismissed = self.engine.execute(
            game["id"], ManageConcubine(actor_id, target_id, "dismiss")
        ).game
        self.assertEqual(dismissed["concubine_system"]["concubines"], [])

    def test_player_concubine_status_drains_and_manages_owner_dependency(self):
        game = self.engine.create_game("流萤", seed=2203, gender="female")
        actor_id = game["player"]["id"]
        owner_id = self._register(
            game["id"], "玄君", gender="male", realm_id="core", layer=2
        )
        entered = self.engine.execute(
            game["id"], EnterConcubineStatus(actor_id, owner_id)
        ).game
        self.assertEqual(
            entered["concubine_system"]["opportunity_efficiency_multiplier"], 0.8
        )

        dependent = self.engine.execute(
            game["id"], ManageConcubineStatus(actor_id, "depend")
        ).game
        self.assertTrue(dependent["concubine_system"]["status"]["dependent"])
        requested = self.engine.execute(
            game["id"], ManageConcubineStatus(actor_id, "request_stones")
        )
        self.assertTrue(any(
            row["event_type"] == "relationship.concubine.status_managed"
            for row in requested.events
        ))
        with self.assertRaisesRegex(ValueError, "本行动单位"):
            self.engine.execute(
                game["id"], ManageConcubineStatus(actor_id, "request_stones")
            )

        state = self.engine.store.load(game["id"])
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation["opportunity"] = 100.0
        state.entities.put(actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="流萤", expected_revision=state.revision
        )
        advanced = self.engine.perform_timed_action(game["id"], "rest", 1).game
        self.assertGreater(
            advanced["concubine_system"]["status"]["last_drain"], 0.0
        )


if __name__ == "__main__":
    unittest.main()
