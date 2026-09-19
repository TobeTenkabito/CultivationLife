from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life.v2 import FormRelationship, RegisterCharacter, V2GameEngine
from cultivation_life.v2.domain.family import LINEAGE, PARENT_CHILD


class V2GovernanceBatchFiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.temporary.name) / "v2.sqlite3")

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
        arranged = self.engine.arrange_faction_succession(game["id"]).game
        successor_id = arranged["faction"]["designated_successor_id"]
        self.assertIsNotNone(successor_id)
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
        supported = self.engine.transfer_vassal_personnel(
            upper["id"], "race", "monster", candidate_id
        ).game
        self.assertEqual(
            supported["governance"]["race_support"][0]["character"]["id"],
            candidate_id,
        )

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
