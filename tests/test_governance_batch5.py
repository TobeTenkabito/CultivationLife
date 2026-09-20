from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import FormRelationship, RegisterCharacter, GameEngine
from cultivation_life.domain.family import LINEAGE, PARENT_CHILD
from cultivation_life.v1_facade import game_view


class V2GovernanceBatchFiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temporary.name) / "v2.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _save(self, game_id: str, state, name: str) -> None:
        self.engine.store.save(
            state, [], player_name=name, expected_revision=state.revision
        )

    def _set_realm(self, game_id: str, entity_id: str, realm_id: str, layer: int) -> None:
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(entity_id, "cultivation.state")
        cultivation.update(realm_id=realm_id, layer=layer, bottleneck=None)
        state.entities.put(entity_id, "cultivation.state", cultivation)
        self._save(game_id, state, "test")

    def test_lazy_faction_roster_dispatch_and_interception_share_characters(self):
        game = self.engine.create_game("宗门行走", seed=5)
        actor_id = game["player"]["id"]
        faction_id = next(
            row["id"] for row in game["available_factions"]
            if row["external_id"] == "tianjian"
        )
        joined = self.engine.join_faction(game["id"], faction_id).game
        self.assertEqual(len(joined["faction"]["roster"]), 7)
        target_id = min(
            (row for row in joined["faction"]["roster"] if row["id"] != actor_id),
            key=lambda row: (row["realm_index"], row["layer"]),
        )["id"]
        target = next(
            row for row in joined["faction"]["roster"]
            if row["id"] == target_id
        )
        self.assertTrue(target["can_intercept"])
        self.assertFalse(next(
            row for row in joined["faction"]["roster"]
            if row["id"] == actor_id
        )["can_intercept"])
        self._set_realm(game["id"], actor_id, "nascent", 9)
        self._set_realm(game["id"], target_id, "qi", 1)
        state = self.engine.store.load(game["id"])
        membership = state.relations.find(
            source_id=actor_id, kind="faction_membership"
        )[0]
        metadata = dict(membership.metadata)
        metadata["contribution"] = 4
        state.relations.replace_metadata(membership.relation_id, metadata)
        self._save(game["id"], state, "宗门行走")

        dispatched = self.engine.dispatch_faction_member(game["id"], "item")
        self.assertEqual(dispatched.game["faction"]["contribution"], 2)
        self.assertTrue(dispatched.game["faction"]["dispatch_used"])
        reloaded = self.engine.get_game(game["id"])
        self.assertTrue(reloaded["faction"]["dispatch_used"])
        self.assertTrue(any(
            row["event_type"] == "faction.member.dispatched"
            for row in dispatched.events
        ))
        with self.assertRaisesRegex(ValueError, "本年度"):
            self.engine.dispatch_faction_member(game["id"], "item")

        intercepted = self.engine.intercept_faction_member(game["id"], target_id)
        self.assertTrue(any(
            row["event_type"] == "combat.resolved" for row in intercepted.events
        ))
        state = self.engine.store.load(game["id"])
        self.assertFalse(state.entities.require(target_id, "character.life")["alive"])
        self.assertFalse(state.relations.find(
            source_id=target_id, kind="faction_membership"
        ))

    def test_low_rank_same_faction_kill_expels_and_marks_real_hostility(self):
        game = self.engine.create_game("同门血案", seed=53)
        actor_id = game["player"]["id"]
        faction_id = next(
            row["id"] for row in game["available_factions"]
            if row["external_id"] == "tianjian"
        )
        joined = self.engine.join_faction(game["id"], faction_id).game
        target_id = min(
            (row for row in joined["faction"]["roster"] if row["id"] != actor_id),
            key=lambda row: (row["realm_index"], row["layer"]),
        )["id"]
        self._set_realm(game["id"], actor_id, "foundation", 9)
        self._set_realm(game["id"], target_id, "qi", 1)

        result = self.engine.intercept_faction_member(
            game["id"], target_id
        ).game
        self.assertIsNone(result["faction"])
        state = self.engine.store.load(game["id"])
        self.assertFalse(state.relations.find(
            source_id=actor_id, kind="faction_membership"
        ))
        hostility = state.entities.require(actor_id, "war.wanted_state")[
            "hostility"
        ]
        self.assertGreaterEqual(hostility[f"sect:{faction_id}"], 60)
        history = state.entities.require(actor_id, "story.state")[
            "system_history"
        ]
        self.assertEqual(history[-1]["result"], "expelled")

    def test_faction_war_story_choice_runs_combat_and_grants_contribution(self):
        game = self.engine.create_game("应召门人", seed=51)
        faction_id = next(
            row["id"] for row in game["available_factions"]
            if row["external_id"] == "tianjian"
        )
        joined = self.engine.join_faction(game["id"], faction_id).game
        before = joined["faction"]["contribution"]
        self.engine.queue_story_event(
            game["id"], "EVT_FACTION_COMMON_WAR_001"
        )
        resolved = self.engine.choose(game["id"], "front").game
        self.assertIsNotNone(resolved["combat"]["last_report"])
        self.assertGreater(resolved["faction"]["contribution"], before)
        self.assertIn(
            resolved["story"]["history"][-1]["result"],
            {"victory", "survived"},
        )

    def test_relationship_capture_keeps_runtime_across_both_story_stages(self):
        game = self.engine.create_game(
            "魔契", seed=4, path="demonic",
            spirit_root="supreme_fire", start_world="demon",
        )
        actor_id = game["player"]["id"]
        faction_id = next(
            row["id"] for row in game["available_factions"]
            if row["external_id"] == "blood_prison"
        )
        joined = self.engine.join_faction(game["id"], faction_id).game
        target_id = next(
            row["id"] for row in joined["faction"]["roster"]
            if row["id"] != actor_id
        )
        self._set_realm(game["id"], actor_id, "spirit", 9)
        self._set_realm(game["id"], target_id, "qi", 1)
        self.engine.execute(
            game["id"],
            FormRelationship(
                actor_id, target_id, "friend",
                {"affinity": 100.0, "last_interactions": {}},
            ),
        )
        opened = self.engine.begin_relationship_capture(
            game["id"], "friend", target_id
        ).game
        self.assertEqual(opened["pending_event"]["id"], "EVT_RELATION_CAPTURE_001")
        second = self.engine.choose(game["id"], "ambush").game
        self.assertEqual(second["pending_event"]["id"], "EVT_RELATION_CAPTURE_002")
        self.assertEqual(second["pending_event"]["runtime"]["target_id"], target_id)
        completed = self.engine.choose(game["id"], "blood_mark").game
        self.assertFalse(completed["relationships"])
        state = self.engine.store.load(game["id"])
        prisoners = state.relations.find(
            source_id=actor_id, target_id=target_id, kind="combat_prisoner"
        )
        self.assertEqual(len(prisoners), 1)
        self.assertTrue(state.entities.require(target_id, "character.life")["alive"])

    def test_arranged_ascension_handover_and_founder_return(self):
        game = self.engine.create_game("祖师", seed=1)
        actor_id = game["player"]["id"]
        founded = self.engine.create_faction(game["id"], "归真宗").game
        faction_id = founded["faction"]["id"]
        self.assertTrue(founded["faction"]["founded_by_player"])
        self.assertTrue(founded["faction"]["can_arrange_succession"])
        self.assertEqual(founded["faction"]["role"], "开山祖师")
        self.assertEqual(sum(
            row["is_player"] for row in founded["faction"]["roster"]
        ), 1)
        arranged = self.engine.arrange_faction_succession(game["id"]).game
        successor_id = arranged["faction"]["designated_successor_id"]
        self.assertIsNotNone(successor_id)
        self.assertEqual(
            arranged["faction"]["succession_plan"]["successor_id"],
            successor_id,
        )
        self.assertTrue(arranged["faction"]["succession_plan"]["arranged"])
        self.assertTrue(
            self.engine.get_game(game["id"])["faction"]["succession_plan"][
                "arranged"
            ]
        )
        self._set_realm(game["id"], actor_id, "spirit", 3)
        ascended = self.engine.ascend_world(game["id"], "spirit").game
        self.assertIsNone(ascended["faction"])
        state = self.engine.store.load(game["id"])
        governance = state.entities.require(faction_id, "faction.governance")
        self.assertEqual(governance["controller_id"], successor_id)
        self.assertTrue(governance["last_ascension_handover"]["return_eligible"])

        self._set_realm(game["id"], actor_id, "mahayana", 1)
        returned = self.engine.cross_world(game["id"], "human").game
        self.assertEqual(returned["pending_event"]["id"], "EVT_FOUNDER_RETURN_001")
        restored = self.engine.choose(game["id"], "return").game
        self.assertEqual(restored["faction"]["id"], faction_id)
        self.assertTrue(restored["faction"]["controlled_by_player"])

        unplanned = self.engine.create_game("未留后事", seed=2)
        unplanned_actor = unplanned["player"]["id"]
        unplanned = self.engine.create_faction(
            unplanned["id"], "散云宗"
        ).game
        unplanned_faction = unplanned["faction"]["id"]
        self._set_realm(unplanned["id"], unplanned_actor, "spirit", 3)
        left = self.engine.ascend_world(unplanned["id"], "spirit").game
        self.assertIsNone(left["faction"])
        state = self.engine.store.load(unplanned["id"])
        governance = state.entities.require(
            unplanned_faction, "faction.governance"
        )
        self.assertIsNone(governance["controller_id"])
        self.assertFalse(
            governance["last_ascension_handover"]["return_eligible"]
        )

    def test_player_faction_defense_pressure_and_dissolution_are_real(self):
        game = self.engine.create_game("守山者", seed=12)
        founded = self.engine.create_faction(game["id"], "孤峰宗").game
        faction_id = founded["faction"]["id"]
        for expected_pressure in (1, 2):
            queued = self.engine.queue_story_event(
                game["id"], "EVT_PLAYER_SECT_DEFENSE_001"
            ).game
            self.assertEqual(
                queued["pending_event"]["id"],
                "EVT_PLAYER_SECT_DEFENSE_001",
            )
            failed = self.engine.choose(game["id"], "appease").game
            self.assertEqual(failed["faction"]["pressure"], expected_pressure)
            self.assertIsNotNone(self.engine.get_game(game["id"])["faction"])
        self.engine.queue_story_event(
            game["id"], "EVT_PLAYER_SECT_DEFENSE_001"
        )
        dissolved = self.engine.choose(game["id"], "appease").game
        self.assertIsNone(dissolved["faction"])
        state = self.engine.store.load(game["id"])
        self.assertFalse(
            state.entities.require(faction_id, "faction.profile")["active"]
        )
        self.assertFalse(state.relations.find(
            target_id=faction_id, kind="faction_membership"
        ))

        abandoned = self.engine.create_game("退隐者", seed=14)
        abandoned = self.engine.create_faction(
            abandoned["id"], "归林宗"
        ).game
        self.engine.queue_story_event(
            abandoned["id"], "EVT_PLAYER_SECT_DEFENSE_001"
        )
        left = self.engine.choose(abandoned["id"], "abandon").game
        self.assertIsNone(left["faction"])

        fighter = self.engine.create_game("迎战者", seed=15)
        fighter = self.engine.create_faction(fighter["id"], "战庐").game
        self.engine.queue_story_event(
            fighter["id"], "EVT_PLAYER_SECT_DEFENSE_001"
        )
        fought = self.engine.choose(fighter["id"], "fight")
        self.assertIsNotNone(fought.game["combat"]["last_report"])
        self.assertTrue(any(
            row["event_type"] == "combat.resolved" for row in fought.events
        ))

    def test_faction_and_race_diplomacy_and_vassal_transfer(self):
        game = self.engine.create_game("盟主", seed=5)
        actor_id = game["player"]["id"]
        own = self.engine.create_faction(game["id"], "盟宗").game
        own_id = own["faction"]["id"]
        target_id = next(
            row["id"] for row in own["available_factions"]
            if row["external_id"] == "tianjian"
        )
        self._set_realm(game["id"], actor_id, "nascent", 9)
        voted = self.engine.propose_diplomacy(
            game["id"], "sect", target_id, "vassal"
        ).game
        relation = voted["faction"]["diplomacy"][0]
        self.assertEqual(relation["status"], "vassal")
        target_member = next(
            row.source_id for row in self.engine.store.load(game["id"]).relations.find(
                target_id=target_id, kind="faction_membership"
            )
            if self.engine.definitions.realm_index(str(
                self.engine.store.load(game["id"]).entities.require(
                    row.source_id, "cultivation.state"
                )["realm_id"]
            )) <= 4
        )
        transferred = self.engine.transfer_vassal_personnel(
            game["id"], "sect", target_id, target_member
        ).game
        self.assertTrue(any(
            row["id"] == target_member and row["role"] == "guest"
            for row in transferred["faction"]["roster"]
        ))
        state = self.engine.store.load(game["id"])
        self.assertEqual(
            state.relations.find(
                source_id=target_member, kind="faction_membership"
            )[0].target_id,
            own_id,
        )

        upper = self.engine.create_game(
            "人族议员", seed=9, start_world="spirit"
        )
        upper_actor = upper["player"]["id"]
        self._set_realm(upper["id"], upper_actor, "mahayana", 1)
        race_vote = self.engine.propose_diplomacy(
            upper["id"], "race", "monster", "vassal"
        ).game
        self.assertIsNone(race_vote["faction"])
        self.assertEqual(race_vote["governance"]["relations"][0]["status"], "vassal")
        before = set(self.engine.store.load(upper["id"]).entities.with_component("core.identity"))
        self.engine.execute(upper["id"], RegisterCharacter(
            "青角", 80, "male", "monster", "supreme_wood", "monster",
            "core", 1, "spirit",
        ))
        state = self.engine.store.load(upper["id"])
        candidate_id = (set(state.entities.with_component("core.identity")) - before).pop()
        legacy = game_view(self.engine.get_game(upper["id"]), {
            "race_details": {
                key: dict(value)
                for key, value in self.engine.definitions.races.items()
            },
            "faction_details": {
                key: {
                    "id": value.id, "name": value.name,
                    "world": value.world_id,
                    "allegiance_race": value.allegiance_race,
                }
                for key, value in self.engine.definitions.factions.items()
            },
        })
        transfer = next(
            row for row in legacy["race_system"]["vassal_transfers"]
            if row["target_id"] == "monster"
        )
        self.assertIn(candidate_id, {
            row["id"] for row in transfer["candidates"]
        })
        supported = self.engine.transfer_vassal_personnel(
            upper["id"], "race", "monster", candidate_id
        ).game
        self.assertEqual(
            supported["governance"]["race_support"][0]["character"]["id"],
            candidate_id,
        )

    def test_lineage_and_faction_allegiance_remain_distinct_in_v1_ui(self):
        game = self.engine.create_game(
            "异族客卿", seed=31, start_world="spirit"
        )
        faction_id = next(
            row["id"] for row in game["available_factions"]
            if row["external_id"] == "wanlingshan"
        )
        joined = self.engine.join_faction(game["id"], faction_id).game
        self.assertEqual(joined["player"]["lineage_race"], "human")
        self.assertEqual(joined["player"]["allegiance_race"], "monster")
        legacy = game_view(joined, {
            "races": {
                key: value.get("name", key)
                for key, value in self.engine.definitions.races.items()
            },
            "race_details": self.engine.definitions.races,
            "faction_details": {
                key: {
                    "id": value.id, "name": value.name,
                    "world": value.world_id,
                    "allegiance_race": value.allegiance_race,
                }
                for key, value in self.engine.definitions.factions.items()
            },
            "worlds": {
                key: value.name
                for key, value in self.engine.definitions.worlds.items()
            },
        })
        self.assertEqual(legacy["player"]["lineage_race_name"], "人族")
        self.assertEqual(legacy["player"]["allegiance_race_name"], "妖族")
        self.assertEqual(legacy["race_system"]["player_race"], "monster")
        supported = legacy["race_system"]["races"]["monster"][
            "supported_factions"
        ]
        wanling = next(row for row in supported if row["id"] == "wanlingshan")
        self.assertTrue(wanling["active"])
        self.assertTrue(wanling["elders"])

    def test_family_recruits_offline_and_cross_world_removes_player_voice(self):
        game = self.engine.create_game("林祖", seed=3)
        actor_id = game["player"]["id"]
        before = set(self.engine.store.load(game["id"]).entities.with_component("core.identity"))
        self.engine.execute(game["id"], RegisterCharacter(
            "林青", 18, "female", "human", "supreme_wood", "dao",
            "qi", 1, "human",
        ))
        state = self.engine.store.load(game["id"])
        child_id = (set(state.entities.with_component("core.identity")) - before).pop()
        lineage = state.entities.require(actor_id, LINEAGE)
        lineage["child_ids"] = [child_id]
        state.entities.put(actor_id, LINEAGE, lineage)
        state.relations.add(
            source_id=actor_id, target_id=child_id, kind=PARENT_CHILD,
            created_year=state.clock.year, metadata={"role": "parent"},
        )
        self._save(game["id"], state, "林祖")
        founded = self.engine.create_family(game["id"], "林氏").game
        self.assertEqual(len(founded["family"]["roster"]), 1)
        while self.engine.store.load(game["id"]).clock.year < 5:
            current = self.engine.get_game(game["id"])
            if current["pending_event"] is not None:
                choice = next(row for row in current["pending_event"]["choices"] if row["enabled"])
                self.engine.choose(game["id"], choice["id"])
            else:
                self.engine.perform_timed_action(game["id"], "rest", 1)
        family = self.engine.get_game(game["id"])["family"]
        self.assertGreaterEqual(len(family["roster"]), 2)
        self.assertTrue(family["has_voice"])
        state = self.engine.store.load(game["id"])
        location = state.entities.require(actor_id, "world.location")
        location.update(world_id="spirit", location_id="tianyuan_realm")
        state.entities.put(actor_id, "world.location", location)
        self._save(game["id"], state, "林祖")
        remote = self.engine.get_game(game["id"])["family"]
        self.assertFalse(remote["same_world"])
        self.assertFalse(remote["has_voice"])
        self.assertEqual(remote["roster"], [])


if __name__ == "__main__":
    unittest.main()
