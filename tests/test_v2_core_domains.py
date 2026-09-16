import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from cultivation_life.v2 import (
    EndRelationship,
    FormRelationship,
    FoundFaction,
    JoinFaction,
    LeaveFaction,
    V2GameEngine,
)
from cultivation_life.v2.domain.character import LIFE, RegisterCharacter
from cultivation_life.v2.domain.cultivation import (
    AttemptBreakthrough,
    EquipMainTechnique,
    GrantTechnique,
)
from cultivation_life.v2.domain.factions import (
    ChangeContribution,
    TransferFactionControl,
)
from cultivation_life.v2.domain.world import LOCATION
from cultivation_life.v2.infrastructure import V2ContentLoader
from cultivation_life.v2.kernel.model import EventScope


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V2CoreDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "v2.sqlite3"
        self.engine = V2GameEngine(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def _register_npc(
        self,
        game_id: str,
        name: str,
        *,
        world_id: str = "human",
        realm_id: str = "qi",
        layer: int = 3,
    ) -> str:
        execution = self.engine.execute(
            game_id,
            RegisterCharacter(
                name=name,
                age=30,
                gender="female",
                race="human",
                spirit_root="supreme_water",
                path="dao",
                realm_id=realm_id,
                layer=layer,
                world_id=world_id,
                lifespan=110,
            ),
        )
        created = next(event for event in execution.events if event["event_type"] == "character.created")
        return str(created["payload"]["entity_id"])

    def test_content_loader_builds_independent_domain_definitions(self):
        definitions = V2ContentLoader.load(SOURCE_ROOT / "content")
        self.assertEqual(definitions.realms[0].id, "mortal")
        self.assertEqual(definitions.realms[-1].id, "daluo")
        self.assertEqual(definitions.roots["supreme_wood"].elements, ("wood",))
        self.assertEqual(definitions.worlds["human"].default_location, "wudi_plain")
        self.assertEqual(definitions.factions["tianjian"].world_id, "human")

    def test_character_cultivation_world_and_base_factions_are_initialized(self):
        game = self.engine.create_game(
            "照夜",
            seed=101,
            gender="female",
            path="demonic",
            spirit_root="supreme_fire",
            start_world="demon",
        )
        self.assertEqual(game["schema_version"], 2)
        self.assertEqual(game["player"]["gender"], "female")
        self.assertEqual(game["player"]["cultivation"]["path"], "demonic")
        self.assertEqual(
            game["player"]["cultivation"]["main_technique"]["id"],
            "TECH_DEMON_BREATHING",
        )
        self.assertEqual(game["world"]["world_id"], "demon")
        self.assertEqual(game["world"]["location_id"], "gathering_baleful_plain")
        self.assertEqual(
            {faction["external_id"] for faction in game["available_factions"]},
            {"blood_prison", "corpse_hall"},
        )

    def test_action_units_cultivation_and_guaranteed_mortal_breakthrough(self):
        game = self.engine.create_game("青衡", seed=202, spirit_root="supreme_wood", path="dao")
        actor_id = game["player"]["id"]
        self.engine.execute(
            game["id"],
            GrantTechnique(actor_id=actor_id, technique_id="TECH_BASIC_QI", equip_main=True),
        )
        trained = self.engine.perform_action(game["id"], "cultivate", 3).game
        self.assertEqual(trained["clock"]["year"], 3)
        self.assertEqual(trained["player"]["cultivation"]["bottleneck"], "major")
        self.assertEqual(trained["player"]["cultivation"]["opportunity"], 30)

        broken = self.engine.attempt_breakthrough(game["id"])
        self.assertEqual(broken.game["player"]["cultivation"]["realm_id"], "qi")
        self.assertEqual(broken.game["player"]["cultivation"]["layer"], 1)
        self.assertTrue(
            any(event["event_type"] == "cultivation.breakthrough.succeeded" for event in broken.events)
        )

    def test_technique_affinity_is_checked_on_learning_and_equipping(self):
        game = self.engine.create_game("木心", seed=303, spirit_root="supreme_wood")
        actor_id = game["player"]["id"]
        with self.assertRaisesRegex(ValueError, "灵根属性"):
            self.engine.execute(
                game["id"],
                GrantTechnique(actor_id=actor_id, technique_id="TECH_FIRE_SCRIPTURE", equip_main=True),
            )
        self.engine.execute(
            game["id"],
            GrantTechnique(actor_id=actor_id, technique_id="TECH_BASIC_QI", equip_main=False),
        )
        equipped = self.engine.execute(
            game["id"],
            EquipMainTechnique(actor_id=actor_id, technique_id="TECH_BASIC_QI"),
        ).game
        self.assertEqual(equipped["player"]["cultivation"]["main_technique"]["id"], "TECH_BASIC_QI")

    def test_map_travel_uses_clock_and_updates_only_on_arrival(self):
        game = self.engine.create_game("远行", seed=404)
        travelled = self.engine.travel(game["id"], "lanjiang_steppe")
        self.assertEqual(travelled.game["clock"]["year"], 3)
        self.assertEqual(travelled.game["player"]["age"], 19)
        self.assertEqual(travelled.game["world"]["location_id"], "lanjiang_steppe")
        self.assertEqual(travelled.events[-1]["event_type"], "world.travel.arrived")

    def test_lifespan_stops_long_action_at_exact_year_and_cancels_remaining_ticks(self):
        game = self.engine.create_game("寿尽", seed=505)
        state = self.engine.store.load(game["id"])
        actor_id = str(state.controlled_entity_id)
        life = state.entities.require(actor_id, LIFE)
        life["lifespan"] = game["player"]["age"] + 2
        state.entities.put(actor_id, LIFE, life)
        state.scheduler.cancel(
            lambda event: event.event_type == "character.lifespan.due"
            and event.payload.get("entity_id") == actor_id
        )
        state.scheduler.schedule(
            due_year=2,
            event_type="character.lifespan.due",
            source="character",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id},
        )
        self.engine.store.save(state, [], player_name="寿尽", expected_revision=1)

        result = self.engine.perform_timed_action(game["id"], "rest", 10)
        self.assertEqual(result.game["clock"]["year"], 2)
        self.assertEqual(result.game["player"]["age"], 18)
        self.assertFalse(result.game["player"]["alive"])
        self.assertEqual(result.game["player"]["activity"]["actions_completed"], 0)
        self.assertTrue(
            any(event["event_type"] == "cultivation.action.interrupted" for event in result.events)
        )
        self.assertEqual(self.engine.store.load(game["id"]).scheduler.events, [])

    def test_relationships_reference_canonical_characters_and_enforce_role_exclusivity(self):
        game = self.engine.create_game("结缘", seed=606)
        actor_id = game["player"]["id"]
        npc_id = self._register_npc(game["id"], "照水")
        formed = self.engine.execute(
            game["id"],
            FormRelationship(source_id=actor_id, target_id=npc_id, kind="dao_companion"),
        ).game
        self.assertEqual(formed["relationships"][0]["kind"], "dao_companion")
        self.assertEqual(formed["relationships"][0]["other"]["id"], npc_id)
        with self.assertRaisesRegex(ValueError, "已有其他"):
            self.engine.execute(
                game["id"],
                FormRelationship(source_id=actor_id, target_id=npc_id, kind="concubine"),
            )
        npc_identity = self.engine.store.load(game["id"]).entities.require(npc_id, "core.identity")
        self.assertEqual(npc_identity["name"], "照水")

    def test_faction_contribution_is_scoped_to_membership_and_control_can_transfer(self):
        game = self.engine.create_game("立宗", seed=707)
        actor_id = game["player"]["id"]
        tianjian = next(
            faction["id"] for faction in game["available_factions"]
            if faction["external_id"] == "tianjian"
        )
        joined = self.engine.execute(
            game["id"], JoinFaction(character_id=actor_id, faction_id=tianjian)
        ).game
        self.assertEqual(joined["faction"]["contribution"], 0)
        self.assertEqual(joined["relationships"], [])
        membership_id = self.engine.store.load(game["id"]).relations.find(
            source_id=actor_id, kind="faction_membership"
        )[0].relation_id
        with self.assertRaisesRegex(ValueError, "不归人际关系"):
            self.engine.execute(
                game["id"],
                EndRelationship(actor_id=actor_id, relation_id=membership_id),
            )
        contributed = self.engine.execute(
            game["id"],
            ChangeContribution(
                character_id=actor_id,
                faction_id=tianjian,
                amount=12,
                reason="test",
            ),
        ).game
        self.assertEqual(contributed["faction"]["contribution"], 12)
        self.engine.execute(game["id"], LeaveFaction(character_id=actor_id))
        founded = self.engine.execute(game["id"], FoundFaction(founder_id=actor_id, name="问心宗")).game
        self.assertEqual(founded["faction"]["contribution"], 0)
        self.assertTrue(founded["faction"]["controlled_by_player"])

        npc_id = self._register_npc(game["id"], "承宗")
        faction_id = founded["faction"]["id"]
        self.engine.execute(
            game["id"], JoinFaction(character_id=npc_id, faction_id=faction_id, role="leader")
        )
        transferred = self.engine.execute(
            game["id"],
            TransferFactionControl(
                actor_id=actor_id,
                faction_id=faction_id,
                successor_id=npc_id,
            ),
        ).game
        self.assertEqual(transferred["faction"]["controller_id"], npc_id)
        self.assertFalse(transferred["faction"]["controlled_by_player"])


class V2SchemaMigrationTests(unittest.TestCase):
    def test_schema_one_snapshot_is_migrated_and_rewritten_as_schema_two(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "old.sqlite3"
            engine = V2GameEngine(database)
            game_id = "legacy-v2-step3"
            snapshot = {
                "format": "cultivation-life-v2",
                "schema_version": 1,
                "game_id": game_id,
                "seed": 8,
                "created_at": "2026-09-16T00:00:00+00:00",
                "updated_at": "2026-09-16T00:00:00+00:00",
                "revision": 1,
                "clock": {"year": 0},
                "rng_state": "",
                "controlled_entity_id": "character:1",
                "entities": {
                    "next_sequence": 2,
                    "entities": {
                        "character:1": {
                            "core.identity": {"name": "旧实验档"},
                            "character.life": {
                                "birth_year": -16,
                                "alive": True,
                                "death_reason": None,
                            },
                            "character.activity": {
                                "cultivation_progress": 4,
                                "rest_years": 0,
                                "actions_completed": 1,
                            },
                        }
                    },
                },
                "scheduler": {"next_sequence": 1, "events": []},
                "module_versions": {"core": 1, "character": 1},
                "next_event_sequence": 1,
            }
            with closing(sqlite3.connect(database)) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO games (
                            game_id, format_id, schema_version, revision, player_name,
                            created_at, updated_at, snapshot_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            game_id,
                            "cultivation-life-v2",
                            1,
                            1,
                            "旧实验档",
                            snapshot["created_at"],
                            snapshot["updated_at"],
                            json.dumps(snapshot, ensure_ascii=False),
                        ),
                    )
            migrated = engine.get_game(game_id)
            self.assertEqual(migrated["schema_version"], 2)
            self.assertEqual(migrated["player"]["gender"], "male")
            self.assertEqual(migrated["player"]["cultivation"]["opportunity"], 4)
            engine.perform_timed_action(game_id, "rest", 1)
            with closing(sqlite3.connect(database)) as connection:
                stored_version = connection.execute(
                    "SELECT schema_version FROM games WHERE game_id = ?", (game_id,)
                ).fetchone()[0]
            self.assertEqual(stored_version, 2)


if __name__ == "__main__":
    unittest.main()
