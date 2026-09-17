from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life.v2 import (
    FormRelationship,
    GrantItem,
    GrantTechnique,
    JoinFaction,
    RegisterCharacter,
    V2GameEngine,
)
from cultivation_life.v2.domain.advanced_cultivation import BODY, DIVINE_SENSE
from cultivation_life.v2.domain.cultivation import CULTIVATION
from cultivation_life.v2.domain.factions import FACTION_PROFILE


class V2AdvancedCultivationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.directory.name) / "v2.sqlite3")
        self.game = self.engine.create_game("进阶修士", seed=112233)
        self.game_id = self.game["id"]
        self.actor_id = self.game["player"]["id"]

    def tearDown(self):
        self.directory.cleanup()

    def test_body_and_divine_sense_use_independent_state_and_unified_time(self):
        self.engine.execute(
            self.game_id, GrantTechnique(self.actor_id, "TECH_BODY_MORTAL")
        )
        self.engine.execute(
            self.game_id, GrantTechnique(self.actor_id, "TECH_SPIRIT_SENSE")
        )
        self.engine.equip_special_technique(
            self.game_id, "TECH_BODY_MORTAL", "body"
        )
        self.engine.equip_special_technique(
            self.game_id, "TECH_SPIRIT_SENSE", "divine_sense"
        )
        state = self.engine.store.load(self.game_id)
        sense = state.entities.require(self.actor_id, DIVINE_SENSE)
        sense["experience"] = 100
        state.entities.put(self.actor_id, DIVINE_SENSE, sense)
        self.engine.store.save(
            state, [], player_name="进阶修士", expected_revision=state.revision
        )
        broken = self.engine.attempt_divine_sense_breakthrough(self.game_id)
        self.assertEqual(broken.game["player"]["divine_sense"]["rank"], 1)
        self.assertEqual(broken.game["player"]["divine_sense"]["experience"], 80)
        trained = self.engine.perform_action(self.game_id, "body_train", 1)
        self.assertGreater(trained.game["player"]["body"]["progress"], 0)
        self.assertEqual(trained.game["clock"]["year"], 1)
        self.assertIsNone(trained.game["action"]["active"])

    def test_body_breakthrough_tracks_pity_and_intrinsic_growth(self):
        self.engine.execute(
            self.game_id, GrantTechnique(self.actor_id, "TECH_BODY_MORTAL")
        )
        self.engine.equip_special_technique(
            self.game_id, "TECH_BODY_MORTAL", "body"
        )
        state = self.engine.store.load(self.game_id)
        body = state.entities.require(self.actor_id, BODY)
        body.update(progress=70.0, ready=True)
        state.entities.put(self.actor_id, BODY, body)
        self.engine.store.save(
            state, [], player_name="进阶修士", expected_revision=state.revision
        )
        result = self.engine.attempt_body_breakthrough(self.game_id)
        self.assertTrue(any(
            event["event_type"].startswith("cultivation.body.breakthrough.")
            for event in result.events
        ))
        shown = result.game["player"]["body"]
        if shown["layer"] == 1:
            self.assertEqual(shown["intrinsic_hp_bonus"], 12.0)
            self.assertEqual(shown["progress"], 0.0)
        else:
            self.assertEqual(shown["progress"], 49.0)

    def test_transformation_material_consumption_and_loadout_are_atomic(self):
        technique_id = "TECH_MYRIAD_FORM_SPECTRUM"
        self.engine.execute(self.game_id, GrantTechnique(self.actor_id, technique_id))
        self.engine.equip_special_technique(
            self.game_id, technique_id, "transformation"
        )
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "phoenix_soul_flame", 2)
        )
        absorbed = self.engine.absorb_transformation_material(
            self.game_id, "phoenix_soul_flame", mode="purified", stat_id="sustain"
        )
        self.assertNotIn(
            "phoenix_soul_flame",
            {item["id"] for item in absorbed.game["inventory"]},
        )
        form = absorbed.game["player"]["transformations"]["forms"][0]
        self.assertEqual(form["id"], "FORM_PHOENIX")
        self.assertGreater(form["stats"]["sustain"], 0)
        self.engine.manage_transformation(self.game_id, "FORM_PHOENIX", "store")
        activated = self.engine.manage_transformation(
            self.game_id, "FORM_PHOENIX", "activate"
        )
        self.assertEqual(
            activated.game["player"]["transformations"]["active"],
            ["FORM_PHOENIX"],
        )

    def test_upper_realm_normal_layer_and_trial_breakthrough_both_complete(self):
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(
            realm_id="void", layer=2, opportunity=1_000_000.0, bottleneck="minor"
        )
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="进阶修士", expected_revision=state.revision
        )
        result = self.engine.attempt_breakthrough(self.game_id)
        self.assertTrue(any(
            event["event_type"].startswith("cultivation.breakthrough.")
            for event in result.events
        ))
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(
            realm_id="void", layer=3, opportunity=1_000_000.0, bottleneck="minor"
        )
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="进阶修士", expected_revision=state.revision
        )
        old_chance = self.engine.definitions.breakthrough["minor_base"]["6"]
        self.engine.definitions.breakthrough["minor_base"]["6"] = 1.0
        try:
            started = self.engine.attempt_breakthrough(self.game_id)
        finally:
            self.engine.definitions.breakthrough["minor_base"]["6"] = old_chance
        self.assertEqual(started.game["trial"]["active"]["kind"], "traditional")
        self.assertEqual(started.game["pending_event"]["id"], "EVT_BREAKTHROUGH_TRADITIONAL_001")
        self.engine.choose(self.game_id, "endure")
        self.engine.choose(self.game_id, "face_karma")
        completed = self.engine.choose(self.game_id, "face_demon")
        self.assertIsNone(completed.game["trial"]["active"])
        self.assertEqual(completed.game["player"]["cultivation"]["layer"], 4)


class V2WorldCrossingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.directory.name) / "v2.sqlite3")
        self.game = self.engine.create_game("破界者", seed=9988)
        self.game_id = self.game["id"]
        self.actor_id = self.game["player"]["id"]

    def tearDown(self):
        self.directory.cleanup()

    def _add_character(self, name: str) -> str:
        self.engine.execute(self.game_id, RegisterCharacter(
            name, 30, "female", "human", "supreme_wood", "dao",
            "spirit", 1, "human",
        ))
        state = self.engine.store.load(self.game_id)
        return next(
            entity_id for entity_id in state.entities.with_component("core.identity")
            if entity_id != self.actor_id
            and state.entities.require(entity_id, "core.identity")["name"] == name
        )

    def _set_spirit_realm(self, *entity_ids: str) -> None:
        state = self.engine.store.load(self.game_id)
        for entity_id in entity_ids:
            cultivation = state.entities.require(entity_id, CULTIVATION)
            cultivation.update(realm_id="spirit", layer=1)
            state.entities.put(entity_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="破界者", expected_revision=state.revision
        )

    def test_permanent_crossing_requires_all_domain_acks_and_cleans_relations(self):
        companion = self._add_character("道侣")
        concubine = self._add_character("侍妾")
        self._set_spirit_realm(self.actor_id, companion, concubine)
        self.engine.execute(
            self.game_id, FormRelationship(self.actor_id, companion, "dao_companion")
        )
        self.engine.execute(
            self.game_id, FormRelationship(self.actor_id, concubine, "concubine")
        )
        state = self.engine.store.load(self.game_id)
        faction_id = next(iter(state.entities.with_component(FACTION_PROFILE)))
        self.engine.execute(
            self.game_id, JoinFaction(self.actor_id, faction_id, "member")
        )
        crossed = self.engine.ascend_world(
            self.game_id, "spirit", invited_ids=(companion,)
        )
        transaction = crossed.game["world"]["transition"]["last_transaction"]
        self.assertEqual(transaction["status"], "committed")
        self.assertEqual(
            set(transaction["acknowledgements"]),
            {"relations", "factions", "economy", "assets", "auction", "combat"},
        )
        self.assertEqual(crossed.game["world"]["world_id"], "spirit")
        self.assertIsNone(crossed.game["faction"])
        self.assertEqual(
            [row["kind"] for row in crossed.game["relationships"]],
            ["dao_companion"],
        )

    def test_concubine_cannot_be_invited(self):
        concubine = self._add_character("侍妾")
        self._set_spirit_realm(self.actor_id, concubine)
        self.engine.execute(
            self.game_id, FormRelationship(self.actor_id, concubine, "concubine")
        )
        with self.assertRaisesRegex(ValueError, "只有道侣和好友"):
            self.engine.ascend_world(
                self.game_id, "spirit", invited_ids=(concubine,)
            )

    def test_human_smuggling_releases_player_from_prison(self):
        captor = self._add_character("狱卒")
        self._set_spirit_realm(self.actor_id, captor)
        state = self.engine.store.load(self.game_id)
        state.relations.add(
            source_id=captor, target_id=self.actor_id, kind="combat_prisoner",
            created_year=state.clock.year,
        )
        self.engine.store.save(
            state, [], player_name="破界者", expected_revision=state.revision
        )
        crossed = self.engine.ascend_world(self.game_id, "spirit")
        self.assertEqual(crossed.game["world"]["world_id"], "spirit")
        persisted = self.engine.store.load(self.game_id)
        self.assertFalse(
            persisted.relations.find(target_id=self.actor_id, kind="combat_prisoner")
        )

    def test_lower_world_return_suppresses_and_restores_cultivation(self):
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(realm_id="mahayana", layer=9, bottleneck=None)
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        location = state.entities.require(self.actor_id, "world.location")
        location.update(
            world_id="spirit",
            location_id=self.engine.definitions.default_location("spirit"),
        )
        state.entities.put(self.actor_id, "world.location", location)
        self.engine.store.save(
            state, [], player_name="破界者", expected_revision=state.revision
        )
        descended = self.engine.cross_world(self.game_id, "human")
        self.assertEqual(descended.game["world"]["world_id"], "human")
        self.assertEqual(descended.game["player"]["cultivation"]["realm_id"], "spirit")
        restored = self.engine.cross_world(self.game_id, "spirit")
        self.assertEqual(restored.game["player"]["cultivation"]["realm_id"], "mahayana")
        self.assertIsNone(
            restored.game["world"]["transition"]["sealed_cultivation"]
        )


if __name__ == "__main__":
    unittest.main()
