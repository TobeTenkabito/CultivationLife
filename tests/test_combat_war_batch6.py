from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import (
    FormRelationship,
    FoundFaction,
    IssueBounty,
    ManageParty,
    ProposeDiplomacy,
    RegisterCharacter,
    ResolveCombat,
    ResolveStoryChoice,
    GameEngine,
    WarAction,
    WarPeace,
)


class V2CombatWarBatchSixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temporary.name) / "v2.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _register(
        self,
        game_id: str,
        name: str,
        *,
        gender: str = "male",
        realm_id: str = "qi",
        layer: int = 1,
    ) -> str:
        before = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        self.engine.execute(
            game_id,
            RegisterCharacter(
                name=name,
                age=30,
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

    def test_party_relations_drive_combined_combat_and_context_report(self):
        game = self.engine.create_game("结阵", seed=601)
        actor_id = game["player"]["id"]
        friend_id = self._register(game["id"], "同游剑修", realm_id="foundation")
        enemy_id = self._register(game["id"], "山门宿敌", realm_id="foundation")
        self.engine.execute(
            game["id"], FormRelationship(actor_id, friend_id, "friend")
        )
        joined = self.engine.execute(
            game["id"], ManageParty(actor_id, friend_id, "invite")
        ).game
        self.assertEqual(len(joined["party"]["members"]), 1)
        self.assertGreater(
            joined["party"]["combined_combat_power"],
            joined["party"]["leader_combat_power"],
        )
        interacted = self.engine.execute(
            game["id"], ManageParty(actor_id, friend_id, "interact")
        ).game
        self.assertFalse(interacted["party"]["members"][0]["can_interact"])
        with self.assertRaisesRegex(ValueError, "本行动单位"):
            self.engine.execute(
                game["id"], ManageParty(actor_id, friend_id, "interact")
            )

        fought = self.engine.execute(
            game["id"], ResolveCombat(actor_id, enemy_id, "duel", "mountain")
        ).game
        report = fought["combat"]["last_report"]
        self.assertEqual(report["terrain"]["name"], "山岭")
        self.assertEqual(
            report["attacker"]["party_members"][0]["entity_id"], friend_id
        )
        self.assertIn("formations", report)

    def test_declared_faction_war_round_peace_and_bounty_are_canonical(self):
        game = self.engine.create_game("开战", seed=602)
        actor_id = game["player"]["id"]
        founded = self.engine.execute(
            game["id"], FoundFaction(actor_id, "归锋盟")
        ).game
        own_id = founded["faction"]["id"]
        self.assertTrue(founded["faction"]["has_diplomatic_voice"])
        self.assertTrue(founded["faction"]["diplomacy"])
        self.assertTrue(all(
            row["target_name"] and row["status_name"]
            for row in founded["faction"]["diplomacy"]
        ))
        self.assertEqual(
            founded["governance"]["diplomacy_statuses"]["war"], "战争"
        )
        target_id = next(
            row["id"] for row in founded["available_factions"]
            if row["external_id"] == "tianjian"
        )
        declared = self.engine.execute(
            game["id"], ProposeDiplomacy(actor_id, "faction", target_id, "war")
        ).game
        self.assertEqual(declared["governance"]["relations"][0]["status"], "war")
        self.assertEqual(declared["war_system"]["active_count"], 1)
        war = declared["war_system"]["wars"][0]
        self.assertEqual(war["attacker_id"], own_id)
        self.assertTrue(war["roster"]["attacker"])
        self.assertTrue(war["roster"]["defender"])
        self.assertEqual(war["controller"], "player")
        self.assertEqual(war["coalitions"]["attacker"][0]["role"], "leader")
        self.assertIn("effective_composite", war["power_summary"]["attacker"])
        self.assertIn("active", war["formation_summary"]["defender"])
        self.assertTrue(war["roster"]["attacker"][0]["realm_name"])
        self.assertTrue(war["roster"]["attacker"][0]["owner_name"])
        self.assertTrue(war["third_parties"])
        self.assertEqual(
            declared["war_system"]["terms"]["white_peace"]["name"],
            "无条件停战",
        )

        opened = self.engine.execute(
            game["id"], WarAction(actor_id, war["id"], "conquest")
        ).game
        self.assertEqual(opened["pending_event"]["id"], "EVT_WAR_VANGUARD_001")
        delayed = self.engine.execute(
            game["id"], ResolveStoryChoice(actor_id, "delay")
        ).game
        self.assertFalse(delayed["war_system"]["wars"][0]["preliminary_resolved"])
        self.engine.execute(
            game["id"], WarAction(actor_id, war["id"], "conquest")
        )
        vanguard = self.engine.execute(
            game["id"], ResolveStoryChoice(actor_id, "fight")
        ).game
        self.assertTrue(vanguard["war_system"]["wars"][0]["preliminary_resolved"])
        self.assertEqual(vanguard["combat"]["last_report"]["mode"], "team")

        first = self.engine.execute(
            game["id"], WarAction(actor_id, war["id"], "round")
        ).game
        self.assertEqual(first["war_system"]["wars"][0]["battles"], 1)
        second = self.engine.execute(
            game["id"], WarAction(actor_id, war["id"], "participate_round")
        ).game
        self.assertEqual(second["war_system"]["wars"][0]["battles"], 2)
        self.assertEqual(second["combat"]["last_report"]["mode"], "team")

        ended = self.engine.execute(
            game["id"], WarPeace(actor_id, war["id"], "white_peace")
        ).game
        self.assertEqual(ended["war_system"]["wars"][0]["status"], "ended")
        with self.assertRaisesRegex(ValueError, "停战期"):
            self.engine.execute(
                game["id"],
                ProposeDiplomacy(actor_id, "faction", target_id, "war"),
            )
        target_character = next(
            row["id"] for row in ended["faction"]["roster"]
            if row["id"] != actor_id
        )
        bounty = self.engine.execute(
            game["id"], IssueBounty(actor_id, target_character, "sect")
        ).game
        self.assertEqual(
            bounty["war_system"]["bounties"][0]["target_id"], target_character
        )


if __name__ == "__main__":
    unittest.main()
