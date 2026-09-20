from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import FormRelationship, GameEngine, RegisterCharacter
from cultivation_life.domain.character import IDENTITY, LIFE, LIFESPAN_DUE, WORLD_NPC_PROFILE
from cultivation_life.domain.cultivation import CULTIVATION
from cultivation_life.domain.combat import CONDITION
from cultivation_life.domain.factions import (
    FACTION_GOVERNANCE, FACTION_NPC, FACTION_PROFILE, MEMBERSHIP,
)
from cultivation_life.domain.npc_lifecycle import NPC_LIFECYCLE
from cultivation_life.kernel.model import EventScope


class WorldSimulationMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temporary.name) / "games.sqlite3")
        self.game = self.engine.create_game("观世", seed=20260920)
        self.game_id = self.game["id"]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _external_world_npc(self, state, external_id: str) -> str:
        return next(
            entity_id for entity_id in state.entities.with_component(WORLD_NPC_PROFILE)
            if state.entities.require(entity_id, WORLD_NPC_PROFILE).get("external_id")
            == external_id
        )

    def _make_due_next_year(self, state, entity_id: str) -> None:
        life = state.entities.require(entity_id, LIFE)
        age = state.clock.year - int(life["birth_year"])
        life["lifespan"] = age + 1
        state.entities.put(entity_id, LIFE, life)
        state.scheduler.cancel(lambda row: (
            row.event_type == LIFESPAN_DUE
            and str(row.payload.get("entity_id", "")) == entity_id
        ))
        state.scheduler.schedule(
            due_year=state.clock.year + 1,
            event_type=LIFESPAN_DUE,
            source="test",
            scope=EventScope.entity(entity_id),
            payload={"entity_id": entity_id},
        )

    def test_definition_factions_are_living_powers_from_game_start(self) -> None:
        state = self.engine.store.load(self.game_id)
        faction_ids = state.entities.with_component(FACTION_PROFILE)
        self.assertTrue(faction_ids)
        for faction_id in faction_ids:
            profile = state.entities.require(faction_id, FACTION_PROFILE)
            self.assertTrue(profile["roster_seeded"])
            members = state.relations.find(target_id=faction_id, kind=MEMBERSHIP)
            self.assertTrue(members, profile["name"])
            self.assertTrue(all(
                state.entities.get(edge.source_id, FACTION_NPC) is not None
                for edge in members
            ))

    def test_relation_only_npc_advances_once_and_uses_canonical_progress(self) -> None:
        before = set(self.engine.store.load(self.game_id).entities.with_component(IDENTITY))
        self.engine.execute(self.game_id, RegisterCharacter(
            name="清微",
            age=30,
            gender="female",
            race="human",
            spirit_root="supreme_wood",
            path="dao",
            realm_id="qi",
            layer=1,
            world_id="human",
            lifespan=110,
        ))
        state = self.engine.store.load(self.game_id)
        npc_id = (set(state.entities.with_component(IDENTITY)) - before).pop()
        self.engine.execute(
            self.game_id,
            FormRelationship(str(state.controlled_entity_id), npc_id, "friend"),
        )
        state = self.engine.store.load(self.game_id)
        lifecycle = state.entities.require(npc_id, NPC_LIFECYCLE)
        lifecycle["cultivation_progress"] = 0.0
        state.entities.put(npc_id, NPC_LIFECYCLE, lifecycle)
        self.engine.store.save(
            state, [], player_name="观世", expected_revision=state.revision
        )

        self.engine.perform_timed_action(self.game_id, "rest", 1)
        state = self.engine.store.load(self.game_id)
        progress = float(state.entities.require(
            npc_id, NPC_LIFECYCLE
        )["cultivation_progress"])
        # qi rate 7 * supreme-root efficiency 1.3 * [0.82, 1.18].  A
        # duplicated family/faction/relationship settlement would exceed it.
        self.assertGreaterEqual(progress, 7 * 1.3 * 0.82)
        self.assertLessEqual(progress, 7 * 1.3 * 1.18)
        self.assertEqual(
            state.entities.require(npc_id, NPC_LIFECYCLE)["last_advanced_year"],
            state.clock.year,
        )

    def test_npc_death_is_projected_and_cross_world_news_is_hidden(self) -> None:
        state = self.engine.store.load(self.game_id)
        human_id = self._external_world_npc(state, "yan_qingshuang")
        spirit_id = self._external_world_npc(state, "rank_taihao")
        self._make_due_next_year(state, human_id)
        self._make_due_next_year(state, spirit_id)
        self.engine.store.save(
            state, [], player_name="观世", expected_revision=state.revision
        )

        result = self.engine.perform_timed_action(self.game_id, "rest", 1).game
        summaries = [row["summary"] for row in result["world_news"]]
        self.assertTrue(any("晏清霜" in row for row in summaries))
        self.assertFalse(any("太皓道君" in row for row in summaries))
        debug = self.engine.set_world_news_debug(self.game_id, True).game
        self.assertTrue(any(
            "太皓道君" in row["summary"] for row in debug["world_news"]
        ))

    def test_long_action_restores_v1_era_summary(self) -> None:
        result = self.engine.perform_timed_action(
            self.game_id, "rest", 5
        ).game
        self.assertTrue(any(
            "era_summary" in row["tags"] for row in result["world_news"]
        ))

    def test_npc_wounds_recover_and_notorious_killing_returns_to_news(self) -> None:
        mortality = self.engine.definitions.systems.setdefault(
            "npc_mortality", {}
        )
        mortality["wound_recovery_chance_per_year"] = 1.0
        mortality["demonic_killing_chance_per_year"] = 1.0
        mortality["notorious_killing_chance_per_year"] = 1.0
        state = self.engine.store.load(self.game_id)
        villain_id = self._external_world_npc(state, "villain_bone_sage")
        condition = state.entities.require(villain_id, CONDITION)
        condition["hp_ratio"] = 0.4
        state.entities.put(villain_id, CONDITION, condition)
        self.engine.store.save(
            state, [], player_name="观世", expected_revision=state.revision
        )

        result = self.engine.perform_timed_action(
            self.game_id, "rest", 1
        ).game
        state = self.engine.store.load(self.game_id)
        self.assertGreater(
            float(state.entities.require(villain_id, CONDITION)["hp_ratio"]),
            0.4,
        )
        self.assertTrue(any(
            row["title"] == "凶名远播" for row in result["world_news"]
        ))

    def test_npc_power_can_rise_and_dissolve_under_v1_pressure_rules(self) -> None:
        rules = self.engine.definitions.systems["player_faction"]
        rules["npc_power_found_chance_per_unit"] = 1.0
        rules["pressure_chance_per_unit"] = 1.0
        rules["pressure_limit"] = 1
        founded = self.engine.perform_timed_action(
            self.game_id, "rest", 1
        ).game
        state = self.engine.store.load(self.game_id)
        npc_factions = [
            faction_id
            for faction_id in state.entities.with_component(FACTION_PROFILE)
            if state.entities.require(faction_id, FACTION_PROFILE).get(
                "founded_by_npc"
            )
        ]
        self.assertEqual(len(npc_factions), 1)
        faction_id = npc_factions[0]
        self.assertTrue(any(
            row["title"] == "新势力崛起" for row in founded["world_news"]
        ))
        for edge in state.relations.find(target_id=faction_id, kind=MEMBERSHIP):
            cultivation = state.entities.require(edge.source_id, CULTIVATION)
            cultivation.update(realm_id="mortal", layer=1)
            state.entities.put(edge.source_id, CULTIVATION, cultivation)
        story = state.entities.get(str(state.controlled_entity_id), "story.state")
        if story is not None:
            story["pending"] = None
            state.entities.put(str(state.controlled_entity_id), "story.state", story)
        self.engine.store.save(
            state, [], player_name="观世", expected_revision=state.revision
        )

        self.engine.perform_timed_action(self.game_id, "rest", 1)
        state = self.engine.store.load(self.game_id)
        self.assertFalse(
            state.entities.require(faction_id, FACTION_PROFILE)["active"]
        )
        self.assertGreaterEqual(
            state.entities.require(faction_id, FACTION_GOVERNANCE)["pressure"], 1
        )


if __name__ == "__main__":
    unittest.main()
