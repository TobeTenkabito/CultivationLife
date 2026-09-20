import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from cultivation_life import (
    EndRelationship,
    FormRelationship,
    FoundFaction,
    JoinFaction,
    LeaveFaction,
    GameEngine,
)
from cultivation_life.domain.character import LIFE, RegisterCharacter
from cultivation_life.domain.cultivation import (
    EquipMainTechnique,
    GrantTechnique,
)
from cultivation_life.domain.factions import (
    ChangeContribution,
    TransferFactionControl,
)
from cultivation_life.domain.world import LOCATION
from cultivation_life.infrastructure import ContentLoader
from cultivation_life.kernel.model import EventScope


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V2CoreDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "v2.sqlite3"
        self.engine = GameEngine(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def _resolve_pending(self, game_id: str) -> dict:
        game = self.engine.get_game(game_id)
        while game["pending_event"] is not None:
            choice = next(row for row in game["pending_event"]["choices"] if row["enabled"])
            game = self.engine.choose(game_id, choice["id"]).game
        return game

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
        definitions = ContentLoader.load(SOURCE_ROOT / "content")
        self.assertEqual(definitions.realms[0].id, "mortal")
        self.assertEqual(definitions.realms[-1].id, "daluo")
        self.assertEqual(definitions.roots["supreme_wood"].elements, ("wood",))
        self.assertEqual(definitions.affinity_names["wood"], "木")
        self.assertEqual(definitions.techniques["TECH_DEMON_BREATHING"].karma_multiplier, 1.05)
        self.assertEqual(definitions.techniques["TECH_DEMON_BREATHING"].combat_requirement_level, 0)
        self.assertTrue(definitions.techniques["TECH_CELESTIAL_BREATHING"].requires_immortal_power)
        self.assertEqual(definitions.techniques["TECH_CELESTIAL_BREATHING"].immortal_power_cost, 0.08)
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
        self.assertEqual(game["schema_version"], 19)
        self.assertEqual(game["player"]["gender"], "female")
        self.assertEqual(game["player"]["cultivation"]["path"], "demonic")
        self.assertEqual(
            game["player"]["cultivation"]["main_technique"]["id"],
            "TECH_DEMON_BREATHING",
        )
        technique = game["player"]["cultivation"]["main_technique"]
        self.assertEqual(technique["category_name"], "修仙")
        self.assertEqual(technique["element_name"], "无属性")
        self.assertEqual(technique["source_display"], "魔源")
        self.assertEqual(technique["opportunity_bonus"], 0.10)
        self.assertEqual(technique["hp_bonus"], 0.08)
        self.assertEqual(technique["mp_bonus"], 0.11)
        self.assertEqual(technique["combat_bonus"], 18)
        self.assertIsInstance(technique["environment_multiplier"], float)
        self.assertNotIn(None, (
            technique["combat_requirement_display"],
            technique["combat_requirement_met"],
            technique["compatible"],
        ))
        self.assertEqual(game["player"]["cultivation"]["spirit_root_efficiency"], 1.3)
        self.assertEqual(game["player"]["cultivation"]["qi_mastery"][0]["next_level_experience"], 25)
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

        self._resolve_pending(game["id"])
        broken = self.engine.attempt_breakthrough(game["id"])
        self.assertEqual(broken.game["player"]["cultivation"]["realm_id"], "qi")
        self.assertEqual(broken.game["player"]["cultivation"]["layer"], 1)
        self.assertEqual(
            broken.game["player"]["cultivation"]["realm_name"], "练气1层"
        )
        self.assertTrue(
            any(event["event_type"] == "cultivation.breakthrough.succeeded" for event in broken.events)
        )

    def test_realm_stage_and_breakthrough_details_match_authoritative_state(self):
        game = self.engine.create_game("照鉴", seed=211)
        actor_id = game["player"]["id"]
        state = self.engine.store.load(game["id"])
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(
            realm_id="core", layer=1, opportunity=300.0, bottleneck="minor"
        )
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="照鉴", expected_revision=state.revision
        )

        projected = self.engine.get_game(game["id"])
        self.assertEqual(
            projected["player"]["cultivation"]["realm_name"], "结丹初期·1层"
        )
        self.assertEqual(projected["breakthrough"]["target_realm"], "结丹初期·2层")
        self.assertEqual(projected["breakthrough"]["chance"]["base"], 0.48)
        self.assertEqual(
            projected["breakthrough"]["chance"]["optimal_state_bonus"], 0.05
        )
        self.assertEqual(projected["breakthrough"]["chance"]["final"], 0.53)

    def test_quick_start_restores_preset_progression_and_loadout(self):
        game = self.engine.create_game("", seed=212, preset_id="core")
        cultivation = game["player"]["cultivation"]
        self.assertEqual(cultivation["realm_name"], "结丹初期·1层")
        self.assertEqual(cultivation["opportunity"], 75.0)
        self.assertEqual(cultivation["main_technique"]["id"], "TECH_COMMON_CORE")
        self.assertEqual(
            cultivation["support_technique"]["id"], "TECH_COMMON_FOUNDATION"
        )
        self.assertEqual(len(cultivation["combat_techniques"]), 3)
        self.assertEqual(game["story"]["attributes"]["karma"], 8.0)
        self.assertEqual(
            next(row for row in game["inventory"] if row["id"] == "spirit_stone")["quantity"],
            120,
        )

    def test_every_enabled_quick_start_matches_the_v1_preset_contract(self):
        qi_levels = {3: 5, 4: 8, 5: 12, 6: 17, 7: 23, 8: 30, 9: 30}
        v1_combat_totals = {
            "core": (664, 733, 2713.4),
            "ghost_core": (892, 956, 2300.2),
            "demonic_core": (400703, 500691, 3865.1),
            "nascent": (2005, 2360, 19732.8),
            "spirit": (4790, 5868, 129532.0),
            "void": (24890, 29548, 731282.0),
            "integration": (115557, 137282, 4887347.0),
            "mahayana": (577761, 701874, 32565422.0),
            "true_immortal": (1250683, 2778942, 420400022.0),
        }
        qi_sources = {
            "dao": "spirit", "demonic": "demon",
            "monster": "monster", "ghost": "yin",
        }
        presets = [
            dict(row)
            for row in self.engine.definitions.systems["quick_start_presets"]
            if bool(row.get("enabled", True))
        ]
        self.assertEqual(len(presets), 9)

        for index, preset in enumerate(presets):
            with self.subTest(preset=preset["id"]):
                game = self.engine.create_game(
                    "", seed=10_000 + index, preset_id=str(preset["id"])
                )
                player = game["player"]
                cultivation = player["cultivation"]
                realm = self.engine.definitions.realms[int(preset["realm_index"])]

                self.assertEqual(player["name"], "无名散修")
                self.assertEqual(player["age"], int(preset["age"]))
                self.assertEqual(player["race"], preset["race"])
                self.assertEqual(game["world"]["world_id"], preset["world"])
                self.assertEqual(cultivation["realm_id"], realm.id)
                self.assertEqual(cultivation["layer"], int(preset["layer"]))
                self.assertEqual(cultivation["path"], preset["path"])
                self.assertEqual(cultivation["spirit_root"], preset["spirit_root"])
                self.assertEqual(
                    cultivation["opportunity"],
                    round(
                        round(
                            realm.opportunity_base
                            * (1 + 0.12 * (int(preset["layer"]) - 1))
                        ) * float(preset.get("opportunity_fraction", 0.0)),
                        1,
                    ),
                )
                self.assertEqual(
                    cultivation["main_technique"]["id"],
                    preset["main_technique"],
                )
                self.assertEqual(
                    cultivation["support_technique"]["id"],
                    preset["support_technique"],
                )
                self.assertEqual(
                    [row["id"] for row in cultivation["combat_techniques"]],
                    list(preset.get("combat_techniques", [])),
                )
                known_ids = {
                    row["id"] for row in cultivation["known_techniques"]
                }
                self.assertTrue({
                    preset["main_technique"], preset["support_technique"],
                    *preset.get("combat_techniques", []),
                }.issubset(known_ids))
                if preset["path"] == "demonic":
                    self.assertTrue({
                        "TECH_DEMON_BREATHING", "TECH_BLOOD_SOUL_SENSE",
                    }.issubset(known_ids))
                if preset["path"] == "ghost":
                    self.assertTrue({
                        "TECH_GHOST_BREATHING", "TECH_SOUL_ECHO_SENSE",
                    }.issubset(known_ids))
                mastery = {
                    row["source"]: row for row in cultivation["qi_mastery"]
                }
                source = qi_sources[str(preset["path"])]
                self.assertEqual(
                    mastery[source]["level"], qi_levels[int(preset["realm_index"])]
                )
                self.assertEqual(
                    cultivation["immortal_power_converted"],
                    bool(preset.get("immortal_power_converted", False)),
                )
                self.assertEqual(
                    cultivation["immortal_conversion_stage"],
                    5 if preset.get("immortal_power_converted", False) else 0,
                )
                snapshot = game["combat"]["snapshot"]
                expected_hp, expected_mp, expected_power = v1_combat_totals[
                    str(preset["id"])
                ]
                self.assertEqual(snapshot["max_hp"], expected_hp)
                self.assertEqual(snapshot["max_mp"], expected_mp)
                self.assertEqual(snapshot["power"], expected_power)

                attributes = game["story"]["attributes"]
                self.assertEqual(attributes["karma"], float(preset.get("karma", 0)))
                self.assertEqual(attributes["fame"], float(preset.get("fame", 0)))
                self.assertEqual(attributes["sha_qi"], float(preset.get("sha_qi", 0)))
                self.assertEqual(
                    game["story"]["flags"], list(preset.get("story_flags", []))
                )
                inventory = {row["id"]: row["quantity"] for row in game["inventory"]}
                expected_items = {
                    str(row["id"]): int(row.get("quantity", 1))
                    for row in preset.get("inventory", [])
                }
                expected_items.setdefault("spirit_sword", 1)
                self.assertEqual(inventory, expected_items)

                birth = next(
                    row for row in game["story"]["history"]
                    if row["event_id"] == "SYS_BIRTH"
                )
                self.assertEqual(birth["age"], int(preset["age"]))
                if int(preset["realm_index"]) in {6, 7, 8}:
                    self.assertEqual(
                        game["tribulation"]["next_age"], int(preset["age"]) + 3000
                    )
                if preset["world"] == "celestial":
                    self.assertTrue(game["heavenly_court"]["visible"])
                    self.assertTrue(game["heavenly_court"]["initialized"])

    def test_blank_standard_name_and_long_names_follow_v1_creation_rules(self):
        unnamed = self.engine.create_game("", seed=20_001)
        self.assertEqual(unnamed["player"]["name"], "无名散修")
        long_name = self.engine.create_game("甲" * 30, seed=20_002)
        self.assertEqual(long_name["player"]["name"], "甲" * 16)

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
        self.assertTrue(any(
            event["event_type"] == "world.travel.arrived" for event in travelled.events
        ))
        self.assertEqual(travelled.events[-1]["event_type"], "story.interaction.opened")

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

    def test_only_master_companion_or_friend_can_be_invited_into_current_faction(self):
        game = self.engine.create_game("引路", seed=708)
        actor_id = game["player"]["id"]
        faction_id = next(
            row["id"] for row in game["available_factions"]
            if row["external_id"] == "tianjian"
        )
        self.engine.execute(
            game["id"], JoinFaction(character_id=actor_id, faction_id=faction_id)
        )
        friend_id = self._register_npc(game["id"], "故交")
        outsider_id = self._register_npc(game["id"], "路人")
        concubine_id = self._register_npc(game["id"], "侍者")
        formed = self.engine.execute(
            game["id"],
            FormRelationship(source_id=actor_id, target_id=friend_id, kind="friend"),
        ).game
        friend_relation_id = formed["relationships"][0]["relation_id"]
        self.engine.execute(
            game["id"],
            FormRelationship(source_id=actor_id, target_id=concubine_id, kind="concubine"),
        )

        invited = self.engine.invite_relationship_to_faction(game["id"], friend_id)
        state = self.engine.store.load(game["id"])
        membership = state.relations.find(
            source_id=friend_id, kind="faction_membership"
        )[0]
        self.assertEqual(membership.target_id, faction_id)
        self.assertEqual(
            state.relations.require(friend_relation_id).metadata["affinity"], 4.0
        )
        self.assertTrue(
            any(
                row["event_type"] == "faction.relationship.invited"
                for row in invited.events
            )
        )
        with self.assertRaisesRegex(ValueError, "师父、道侣或道友"):
            self.engine.invite_relationship_to_faction(game["id"], outsider_id)
        with self.assertRaisesRegex(ValueError, "师父、道侣或道友"):
            self.engine.invite_relationship_to_faction(game["id"], concubine_id)

    def test_faction_projection_and_control_are_isolated_by_world(self):
        game = self.engine.create_game("越界掌门", seed=709)
        actor_id = game["player"]["id"]
        founded = self.engine.execute(
            game["id"], FoundFaction(founder_id=actor_id, name="界下宗")
        ).game
        faction_id = founded["faction"]["id"]
        state = self.engine.store.load(game["id"])
        location = state.entities.require(actor_id, LOCATION)
        location.update(world_id="spirit", location_id="tianyuan_realm")
        state.entities.put(actor_id, LOCATION, location)
        self.engine.store.save(
            state, [], player_name="越界掌门", expected_revision=state.revision
        )

        self.assertIsNone(self.engine.get_game(game["id"])["faction"])
        with self.assertRaisesRegex(ValueError, "其他世界"):
            self.engine.execute(
                game["id"],
                TransferFactionControl(
                    actor_id=actor_id,
                    faction_id=faction_id,
                    successor_id=actor_id,
                ),
            )

    def test_faction_reward_preference_pays_annually_and_benefits_survive_leaving(self):
        game = self.engine.create_game("受禄长老", seed=710)
        actor_id = game["player"]["id"]
        state = self.engine.store.load(game["id"])
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="nascent", layer=1, opportunity=0.0, bottleneck=None)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="受禄长老", expected_revision=state.revision
        )
        current = self.engine.get_game(game["id"])
        faction_id = next(
            row["id"] for row in current["available_factions"]
            if row["external_id"] == "tianjian"
        )
        joined = self.engine.execute(
            game["id"], JoinFaction(character_id=actor_id, faction_id=faction_id)
        ).game
        before_power = joined["combat"]["snapshot"]["power"]
        selected = self.engine.set_faction_reward(game["id"], "combat").game
        self.assertEqual(selected["faction"]["reward_preference"], "combat")
        self.assertEqual(set(selected["faction"]["reward_options"]), {
            "opportunity", "vitality", "mana", "combat",
        })

        rewarded = self.engine.perform_action(game["id"], "rest", 1).game
        elapsed = rewarded["clock"]["year"] - selected["clock"]["year"]
        self.assertEqual(rewarded["faction"]["contribution"], elapsed)
        self.assertEqual(
            rewarded["faction"]["permanent_benefits"]["combat"],
            3 * elapsed,
        )
        self.assertEqual(
            rewarded["combat"]["snapshot"]["power"], before_power + 3 * elapsed
        )
        self._resolve_pending(game["id"])
        before_leave = self.engine.get_game(game["id"])["combat"]["snapshot"]["power"]
        left = self.engine.execute(
            game["id"], LeaveFaction(character_id=actor_id)
        ).game
        self.assertIsNone(left["faction"])
        self.assertEqual(
            left["combat"]["snapshot"]["power"], before_leave
        )


class V2SchemaMigrationTests(unittest.TestCase):
    def test_schema_one_snapshot_is_migrated_and_rewritten_as_current_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "old.sqlite3"
            engine = GameEngine(database)
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
            self.assertEqual(migrated["schema_version"], 19)
            self.assertEqual(migrated["player"]["gender"], "male")
            self.assertEqual(migrated["player"]["cultivation"]["opportunity"], 4)
            self.assertEqual(migrated["trial"], {"active": None, "history": []})
            self.assertEqual(migrated["assets"], {"instances": [], "reservations": []})
            engine.perform_timed_action(game_id, "rest", 1)
            with closing(sqlite3.connect(database)) as connection:
                stored_version = connection.execute(
                    "SELECT schema_version FROM games WHERE game_id = ?", (game_id,)
                ).fetchone()[0]
            self.assertEqual(stored_version, 19)


if __name__ == "__main__":
    unittest.main()
