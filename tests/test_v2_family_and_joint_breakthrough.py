from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life.v2 import (
    AttemptBreakthrough,
    FormRelationship,
    GrantItem,
    InteractDaoCompanion,
    RegisterCharacter,
    UseItem,
    V2GameEngine,
)
from cultivation_life.v2.domain.cultivation import CULTIVATION, PRACTICE


class V2FamilyAndJointBreakthroughTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.temporary.name) / "v2.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _register(self, game_id: str, name: str) -> str:
        before = set(self.engine.store.load(game_id).entities.with_component("core.identity"))
        self.engine.execute(
            game_id,
            RegisterCharacter(
                name=name,
                age=18,
                gender="female",
                race="human",
                spirit_root="supreme_wood",
                path="dao",
                realm_id="mortal",
                layer=1,
                world_id="human",
            ),
        )
        after = set(self.engine.store.load(game_id).entities.with_component("core.identity"))
        return (after - before).pop()

    def test_same_realm_same_technique_companion_advances_with_player(self):
        game = self.engine.create_game("同道", seed=2)
        actor_id = game["player"]["id"]
        companion_id = self._register(game["id"], "清微")
        self.engine.execute(
            game["id"], FormRelationship(actor_id, companion_id, "dao_companion")
        )
        state = self.engine.store.load(game["id"])
        for entity_id, layer in ((actor_id, 2), (companion_id, 1)):
            cultivation = state.entities.require(entity_id, CULTIVATION)
            cultivation.update(
                realm_id="foundation",
                layer=layer,
                opportunity=1_000_000.0,
                bottleneck="minor" if entity_id == actor_id else None,
            )
            state.entities.put(entity_id, CULTIVATION, cultivation)
            practice = state.entities.require(entity_id, PRACTICE)
            practice.update(
                known_techniques=["TECH_BASIC_QI"],
                main_technique_id="TECH_BASIC_QI",
            )
            state.entities.put(entity_id, PRACTICE, practice)
        self.engine.store.save(
            state, [], player_name="同道", expected_revision=state.revision
        )

        result = self.engine.execute(game["id"], AttemptBreakthrough(actor_id))
        success = next(
            row for row in result.events
            if row["event_type"] == "cultivation.breakthrough.succeeded"
        )
        self.assertEqual(success["payload"]["joint_companion_id"], companion_id)
        companion = self.engine.store.load(game["id"]).entities.require(
            companion_id, CULTIVATION
        )
        self.assertEqual((companion["realm_id"], companion["layer"]), ("foundation", 3))
        self.assertTrue(any(
            row["event_type"] == "relationship.companion.joint_breakthrough.completed"
            for row in result.events
        ))

    def test_joint_companion_target_survives_persisted_trial(self):
        game = self.engine.create_game("同劫", seed=2)
        actor_id = game["player"]["id"]
        companion_id = self._register(game["id"], "守劫")
        self.engine.execute(
            game["id"], FormRelationship(actor_id, companion_id, "dao_companion")
        )
        state = self.engine.store.load(game["id"])
        for entity_id in (actor_id, companion_id):
            cultivation = state.entities.require(entity_id, CULTIVATION)
            cultivation.update(
                realm_id="nascent",
                layer=9,
                opportunity=10_000_000.0,
                bottleneck="major" if entity_id == actor_id else None,
                heart_demon=0.0,
            )
            state.entities.put(entity_id, CULTIVATION, cultivation)
            practice = state.entities.require(entity_id, PRACTICE)
            practice.update(
                known_techniques=["TECH_BASIC_QI"],
                main_technique_id="TECH_BASIC_QI",
            )
            state.entities.put(entity_id, PRACTICE, practice)
        self.engine.store.save(
            state, [], player_name="同劫", expected_revision=state.revision
        )
        table = self.engine.definitions.breakthrough["major_base"]["4"]
        previous = dict(table)
        for key in table:
            table[key] = 1.0
        try:
            started = self.engine.execute(
                game["id"], AttemptBreakthrough(actor_id)
            ).game
        finally:
            table.clear()
            table.update(previous)
        self.assertEqual(
            started["trial"]["active"]["joint_companion_id"], companion_id
        )
        self.engine.choose(game["id"], "endure")
        self.engine.choose(game["id"], "face_karma")
        completed = self.engine.choose(game["id"], "face_demon")
        self.assertIsNone(completed.game["trial"]["active"])
        companion = self.engine.store.load(game["id"]).entities.require(
            companion_id, CULTIVATION
        )
        self.assertEqual((companion["realm_id"], companion["layer"]), ("spirit", 1))

    def test_conception_item_child_lifecycle_and_family_founding(self):
        game = self.engine.create_game("林氏", seed=1)
        actor_id = game["player"]["id"]
        companion_id = self._register(game["id"], "云枝")
        self.engine.execute(
            game["id"], FormRelationship(actor_id, companion_id, "dao_companion")
        )
        self.engine.execute(
            game["id"], GrantItem(actor_id, "concord_birth_pill", 1, "test")
        )
        medicated = self.engine.execute(
            game["id"], UseItem(actor_id, "concord_birth_pill")
        ).game
        self.assertEqual(medicated["family"]["pending_conception_bonus"], 0.1)
        entwined = self.engine.execute(
            game["id"], InteractDaoCompanion(actor_id, "entwine")
        )
        conception = next(
            row for row in entwined.events
            if row["event_type"] == "family.conception.resolved"
        )
        self.assertTrue(conception["payload"]["conceived"])
        child_id = str(conception["payload"]["child_id"])
        self.assertEqual(entwined.game["family"]["pending_conception_bonus"], 0.0)
        self.assertEqual(entwined.game["family"]["offspring"][0]["id"], child_id)

        state = self.engine.store.load(game["id"])
        life = state.entities.require(child_id, "character.life")
        life["birth_year"] = state.clock.year - 7
        state.entities.put(child_id, "character.life", life)
        self.engine.store.save(
            state, [], player_name="林氏", expected_revision=state.revision
        )
        grown = self.engine.perform_timed_action(game["id"], "rest", 1).game
        child = next(row for row in grown["family"]["offspring"] if row["id"] == child_id)
        self.assertTrue(child["cultivation_started"])
        while grown["pending_event"] is not None:
            choice = next(
                row for row in grown["pending_event"]["choices"]
                if row["enabled"]
            )
            grown = self.engine.choose(game["id"], choice["id"]).game
        founded = self.engine.create_family(game["id"], "青林世家").game
        self.assertTrue(founded["family"]["exists"])
        self.assertEqual(founded["family"]["roster"][0]["id"], child_id)


if __name__ == "__main__":
    unittest.main()
