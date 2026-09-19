from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import (
    FoundFaction,
    IntriguePersonnelAction,
    JoinFaction,
    RegisterCharacter,
    GameEngine,
)
from cultivation_life.domain.extensions import INTRIGUE_GOVERNANCE
from cultivation_life.domain.character import IDENTITY
from cultivation_life.domain.factions import FACTION_NPC
from cultivation_life.domain.family import FAMILY_MEMBERSHIP, FAMILY_PROFILE, LINEAGE
from cultivation_life.domain.intrigue import INTRIGUE_PRISONER
from cultivation_life.domain.relations import relationship_affinity
from cultivation_life.domain.war import _power_members
from cultivation_life.infrastructure.migrations import migrate_snapshot


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V2IntriguePersonnelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temporary.name) / "v2.sqlite3")
        self.game = self.engine.create_game("执掌山门", seed=2619)
        self.game_id = str(self.game["id"])
        self.actor_id = str(self.game["player"]["id"])
        founded = self.engine.execute(
            self.game_id,
            FoundFaction(founder_id=self.actor_id, name="归一宗"),
        ).game
        self.faction_id = str(founded["faction"]["id"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _register_member(
        self, name: str, *, realm_id: str = "foundation", layer: int = 3,
    ) -> str:
        result = self.engine.execute(
            self.game_id,
            RegisterCharacter(
                name=name,
                age=30,
                gender="female",
                race="human",
                spirit_root="supreme_water",
                path="dao",
                realm_id=realm_id,
                layer=layer,
                world_id="human",
                lifespan=500,
            ),
        )
        member_id = str(next(
            event["payload"]["entity_id"]
            for event in result.events
            if event["event_type"] == "character.created"
        ))
        self.engine.execute(
            self.game_id,
            JoinFaction(character_id=member_id, faction_id=self.faction_id),
        )
        return member_id

    def _act(
        self,
        action: str,
        member_id: str,
        *,
        position_id: str = "",
        years: int = 1,
        reason: str = "",
        kind: str = "sect",
    ):
        return self.engine.execute(
            self.game_id,
            IntriguePersonnelAction(
                actor_id=self.actor_id,
                kind=kind,
                action=action,
                member_id=member_id,
                position_id=position_id,
                years=years,
                reason=reason,
            ),
        )

    def test_appointment_replacement_enforces_authority_and_consequences(self) -> None:
        first_id = self._register_member("前任庶务", realm_id="nascent")
        second_id = self._register_member("新任庶务")

        self._act("appoint", first_id, position_id="affairs_elder")
        replaced = self._act("appoint", second_id, position_id="affairs_elder").game
        state = self.engine.store.load(self.game_id)
        governance = state.entities.require(self.faction_id, INTRIGUE_GOVERNANCE)

        self.assertEqual(governance["positions"]["leader"], self.actor_id)
        self.assertEqual(governance["positions"]["affairs_elder"], second_id)
        self.assertEqual(relationship_affinity(state, first_id, self.actor_id), -3.0)
        self.assertEqual(relationship_affinity(state, second_id, self.actor_id), 5.0)
        self.assertEqual(governance["unrest"], 3.0)
        section = replaced["intrigue_system"]["sections"][0]
        self.assertEqual(
            next(row for row in section["positions"] if row["id"] == "affairs_elder")["holder_id"],
            second_id,
        )
        with self.assertRaisesRegex(ValueError, "不可由此处任命"):
            self._act("appoint", first_id, position_id="leader")
        self._act("appoint", first_id, position_id="guest_elder")
        governance = self.engine.store.load(self.game_id).entities.require(
            self.faction_id, INTRIGUE_GOVERNANCE
        )
        self.assertEqual(governance["positions"]["guest_elder"], first_id)

    def test_dismiss_reward_punish_and_expel_update_canonical_state(self) -> None:
        member_id = self._register_member("戒律执事")
        self._act("appoint", member_id, position_id="affairs_elder")
        self._act("reward", member_id)
        self._act("punish", member_id)
        self._act("dismiss", member_id)
        expelled = self._act("expel", member_id).game

        state = self.engine.store.load(self.game_id)
        governance = state.entities.require(self.faction_id, INTRIGUE_GOVERNANCE)
        self.assertEqual(governance["member_contribution"][member_id], 0)
        self.assertEqual(governance["fear"], 3.0)
        self.assertEqual(governance["unrest"], 17.0)
        self.assertNotIn(member_id, governance["positions"].values())
        self.assertFalse(state.relations.find(
            source_id=member_id, target_id=self.faction_id, kind="faction_membership"
        ))
        section = expelled["intrigue_system"]["sections"][0]
        self.assertNotIn(member_id, {row["id"] for row in section["members"]})

    def test_prison_sentence_ticks_by_action_unit_and_excludes_war_roster(self) -> None:
        member_id = self._register_member("受刑长老", realm_id="core")
        state = self.engine.store.load(self.game_id)
        state.entities.put(member_id, FACTION_NPC, {
            "title": "受刑长老", "cultivation_progress": 7.0,
        })
        player_name = str(state.entities.require(self.actor_id, IDENTITY)["name"])
        self.engine.store.save(
            state, [], player_name=player_name, expected_revision=state.revision
        )
        imprisoned = self._act(
            "imprison", member_id, years=2, reason="违抗掌门令"
        ).game
        prison = imprisoned["intrigue_system"]["sections"][0]["prison"]
        self.assertEqual(prison[0]["sentence_remaining"], 2)
        state = self.engine.store.load(self.game_id)
        self.assertNotIn(
            member_id,
            _power_members(
                state, self.engine.definitions, "faction", self.faction_id, "human"
            ),
        )
        with self.assertRaisesRegex(ValueError, "囚犯不能担任职位"):
            self._act("appoint", member_id, position_id="affairs_elder")

        after_one = self.engine.perform_action(self.game_id, "rest", 1).game
        remaining = after_one["intrigue_system"]["sections"][0]["prison"]
        self.assertEqual(remaining[0]["sentence_remaining"], 1)
        while self.engine.get_game(self.game_id)["pending_event"] is not None:
            pending = self.engine.get_game(self.game_id)["pending_event"]
            choice = next(row for row in pending["choices"] if row["enabled"])
            self.engine.choose(self.game_id, choice["id"])
        released = self.engine.perform_action(self.game_id, "rest", 1).game
        self.assertEqual(released["intrigue_system"]["sections"][0]["prison"], [])
        state = self.engine.store.load(self.game_id)
        self.assertEqual(
            state.entities.require(member_id, FACTION_NPC)["cultivation_progress"],
            7.0,
        )
        self.assertFalse(state.relations.find(
            source_id=self.faction_id,
            target_id=member_id,
            kind=INTRIGUE_PRISONER,
        ))

    def test_family_personnel_uses_same_authoritative_rules(self) -> None:
        heir_id = self._register_member("族中后辈", realm_id="qi")
        state = self.engine.store.load(self.game_id)
        family_id = state.entities.create("family")
        state.entities.put(family_id, FAMILY_PROFILE, {
            "name": "沈氏仙族",
            "world_id": "human",
            "path": "dao",
            "allegiance_race": "human",
            "creator_id": self.actor_id,
            "controller_id": self.actor_id,
            "active": True,
            "founded_year": state.clock.year,
            "last_recruitment_year": state.clock.year,
        })
        lineage = state.entities.require(self.actor_id, LINEAGE)
        lineage["family_id"] = family_id
        state.entities.put(self.actor_id, LINEAGE, lineage)
        state.relations.add(
            source_id=heir_id,
            target_id=family_id,
            kind=FAMILY_MEMBERSHIP,
            created_year=state.clock.year,
            metadata={"role": "lineal_heir", "cultivation_progress": 0.0},
        )
        player_name = str(state.entities.require(self.actor_id, IDENTITY)["name"])
        self.engine.store.save(
            state, [], player_name=player_name, expected_revision=state.revision
        )

        appointed = self._act(
            "appoint", heir_id, position_id="affairs_clan_elder", kind="family"
        ).game
        family_section = next(
            row for row in appointed["intrigue_system"]["sections"]
            if row["kind"] == "family"
        )
        self.assertEqual(
            next(
                row for row in family_section["positions"]
                if row["id"] == "affairs_clan_elder"
            )["holder_id"],
            heir_id,
        )
        with self.assertRaisesRegex(ValueError, "不可由此处任命"):
            self._act(
                "appoint", heir_id, position_id="family_head", kind="family"
            )

    def test_schema_eighteen_intrigue_scaffold_is_migrated(self) -> None:
        snapshot = self.engine.store.load(self.game_id).to_dict()
        snapshot["schema_version"] = 18
        snapshot["module_versions"].pop("intrigue", None)
        intrigue = snapshot["entities"]["entities"][self.faction_id][
            INTRIGUE_GOVERNANCE
        ]
        for key in (
            "member_contribution", "unrest", "fear", "time_progress",
            "personnel_history",
        ):
            intrigue.pop(key, None)

        migrated = migrate_snapshot(snapshot)
        migrated_intrigue = migrated["entities"]["entities"][self.faction_id][
            INTRIGUE_GOVERNANCE
        ]
        self.assertEqual(migrated["schema_version"], 19)
        self.assertEqual(migrated["module_versions"]["intrigue"], 2)
        self.assertEqual(migrated_intrigue["member_contribution"], {})
        self.assertEqual(migrated_intrigue["personnel_history"], [])
        self.assertEqual(migrated_intrigue["time_progress"], 0.0)


if __name__ == "__main__":
    unittest.main()
