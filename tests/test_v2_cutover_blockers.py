from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life.migration.shadow import SHARED_ACTIONS, ShadowCommand, ShadowRunner
from cultivation_life.v2 import (
    FoundFaction,
    IntrigueRecruitmentAction,
    IntrigueResolutionAction,
    RegisterCharacter,
    V2GameEngine,
)
from cultivation_life.v2.domain.advanced_cultivation import BODY, DIVINE_SENSE
from cultivation_life.v2.domain.character import IDENTITY, LIFE
from cultivation_life.v2.domain.cultivation import CULTIVATION, PRACTICE
from cultivation_life.v2.domain.extensions import INTRIGUE_GOVERNANCE
from cultivation_life.v2.domain.intrigue import INTRIGUE_GUEST
from cultivation_life.v2.domain.relations import set_relationship_affinity
from cultivation_life.v2.server import V2HTTPCommandRegistry


class V2CutoverBlockerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _promote_for_actions(engine: V2GameEngine, game_id: str) -> None:
        state = engine.store.load(game_id)
        actor_id = str(state.controlled_entity_id)
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation.update(realm_id="nascent", layer=3)
        state.entities.put(actor_id, CULTIVATION, cultivation)
        practice = state.entities.require(actor_id, PRACTICE)
        practice.update(
            known_techniques=[
                "TECH_BODY_MORTAL", "TECH_SPIRIT_SENSE",
            ],
        )
        state.entities.put(actor_id, PRACTICE, practice)
        body = state.entities.require(actor_id, BODY)
        body["technique_id"] = "TECH_BODY_MORTAL"
        state.entities.put(actor_id, BODY, body)
        sense = state.entities.require(actor_id, DIVINE_SENSE)
        sense["technique_id"] = "TECH_SPIRIT_SENSE"
        state.entities.put(actor_id, DIVINE_SENSE, sense)
        life = state.entities.require(actor_id, LIFE)
        life["lifespan"] = 10_000
        state.entities.put(actor_id, LIFE, life)
        player_name = str(state.entities.require(actor_id, IDENTITY)["name"])
        engine.store.save(state, [], player_name=player_name, expected_revision=state.revision)

    def test_every_frozen_action_kind_runs_through_v2_and_shadow_adapter(self) -> None:
        self.assertEqual(ShadowRunner.supported_actions, SHARED_ACTIONS)
        self.assertEqual(len(SHARED_ACTIONS), 12)
        for index, action in enumerate(sorted(SHARED_ACTIONS), start=1):
            with self.subTest(action=action):
                ShadowCommand(action, 1)
                engine = V2GameEngine(self.root / f"action-{index}.sqlite3")
                game = engine.create_game(f"行动{index}", seed=8000 + index)
                self._promote_for_actions(engine, str(game["id"]))
                result = engine.perform_action(str(game["id"]), action, 1)
                self.assertGreaterEqual(result.game["clock"]["year"], 1)
                self.assertIsNone(result.game["action"]["active"])

    def test_all_loaded_story_events_have_executable_effect_chains(self) -> None:
        engine = V2GameEngine(self.root / "story.sqlite3")
        all_kinds = {
            effect.kind
            for event in engine.definitions.story_events.values()
            for choice in event.choices
            for effect in choice.effects
        }
        self.assertTrue(all_kinds.issubset(engine.story_effects.supported_kinds))
        self.assertEqual(
            engine.story_effects.compatible_event_ids(),
            frozenset(engine.definitions.story_events),
        )
        self.assertEqual(len(engine.definitions.story_events), 363)

    def test_guest_decision_and_recruitment_share_canonical_state(self) -> None:
        engine = V2GameEngine(self.root / "intrigue.sqlite3")
        game = engine.create_game("议政者", seed=9201)
        game_id = str(game["id"])
        actor_id = str(game["player"]["id"])
        faction_id = str(engine.execute(
            game_id, FoundFaction(actor_id, "衡议宗")
        ).game["faction"]["id"])
        self._promote_for_actions(engine, game_id)
        created = engine.execute(
            game_id,
            RegisterCharacter(
                name="客卿顾氏", age=40, gender="female", race="human",
                spirit_root="supreme_water", path="dao", realm_id="core",
                layer=4, world_id="human", lifespan=800,
            ),
        )
        guest_id = str(next(
            event["payload"]["entity_id"] for event in created.events
            if event["event_type"] == "character.created"
        ))
        state = engine.store.load(game_id)
        set_relationship_affinity(state, guest_id, actor_id, 100)
        state.relations.add(
            source_id=faction_id, target_id=guest_id, kind=INTRIGUE_GUEST,
            created_year=state.clock.year,
            metadata={"defense_required": True, "offense_opt_in": False},
        )
        player_name = str(state.entities.require(actor_id, IDENTITY)["name"])
        engine.store.save(state, [], player_name=player_name, expected_revision=state.revision)

        decided = engine.execute(
            game_id, IntrigueResolutionAction(actor_id, "sect", "investment")
        ).game
        section = next(row for row in decided["intrigue_system"]["sections"] if row["kind"] == "sect")
        self.assertEqual(section["resources"], 25)
        self.assertEqual(section["guests"][0]["guest_id"], guest_id)
        proposed = engine.execute(
            game_id,
            IntrigueRecruitmentAction(
                actor_id, "propose",
                {"spirit_root": "any", "realm_index": "any", "path": "any", "combat": "any", "gender": "any"},
            ),
        ).game
        section = next(row for row in proposed["intrigue_system"]["sections"] if row["kind"] == "sect")
        self.assertIsNotNone(section["pending_recruitment"])
        self.assertTrue(engine.store.load(game_id).entities.require(
            faction_id, INTRIGUE_GOVERNANCE
        )["resolutions"])

    def test_http_registry_drives_persisted_v2_game(self) -> None:
        engine = V2GameEngine(self.root / "http.sqlite3")
        registry = V2HTTPCommandRegistry(engine)
        game = engine.create_game("网页修士", seed=44)
        result = registry.dispatch(str(game["id"]), "advance", {"action": "rest", "units": 1})
        self.assertEqual(result["game"]["format"], "cultivation-life-v2")
        self.assertIn("intrigue-resolution", registry.operations)
        self.assertIn("advance", registry.operations)


if __name__ == "__main__":
    unittest.main()
