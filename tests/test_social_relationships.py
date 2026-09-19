from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import (
    ChangeAffinity,
    EndRelationship,
    FormRelationship,
    GiftDisciple,
    GrantItem,
    InteractDaoCompanion,
    InteractDaoFriend,
    OfferDiscipleRequest,
    RegisterCharacter,
    RequestFromMaster,
    RespondDiscipleRequest,
    GameEngine,
)
from cultivation_life.domain.cultivation import CULTIVATION


class V2SocialRelationshipTests(unittest.TestCase):
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
        realm_id: str = "mortal",
        layer: int = 1,
        spirit_root: str = "supreme_wood",
    ) -> str:
        before = set(self.engine.store.load(game_id).entities.with_component("core.identity"))
        self.engine.execute(
            game_id,
            RegisterCharacter(
                name=name,
                age=20,
                gender="female",
                race="human",
                spirit_root=spirit_root,
                path="dao",
                realm_id=realm_id,
                layer=layer,
                world_id="human",
            ),
        )
        after = set(self.engine.store.load(game_id).entities.with_component("core.identity"))
        return (after - before).pop()

    def test_companion_interactions_use_canonical_entities_and_lifecycle_rules(self):
        game = self.engine.create_game("同心", seed=1201)
        actor_id = game["player"]["id"]
        companion_id = self._register(game["id"], "照月")
        self.engine.execute(game["id"], ChangeAffinity(actor_id, companion_id, 30))
        formed = self.engine.execute(
            game["id"],
            FormRelationship(
                actor_id,
                companion_id,
                "dao_companion",
                {"last_interactions": {}},
            ),
        ).game
        self.assertGreater(
            formed["relationships"][0]["other"]["lifespan"],
            formed["relationships"][0]["other"]["age"],
        )

        state = self.engine.store.load(game["id"])
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation["heart_demon"] = 10.0
        state.entities.put(actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="同心", expected_revision=state.revision
        )
        intimate = self.engine.execute(
            game["id"], InteractDaoCompanion(actor_id, "intimacy")
        ).game
        self.assertLess(intimate["player"]["cultivation"]["heart_demon"], 10.0)
        with self.assertRaisesRegex(ValueError, "本年度"):
            self.engine.execute(
                game["id"], InteractDaoCompanion(actor_id, "intimacy")
            )

        self.engine.execute(game["id"], GrantItem(actor_id, "spirit_sword", 1, "test"))
        gifted = self.engine.execute(
            game["id"],
            InteractDaoCompanion(actor_id, "gift_item", "spirit_sword"),
        ).game
        self.assertEqual(
            gifted["relationships"][0]["metadata"]["items"]["spirit_sword"], 1
        )
        relation_id = gifted["relationships"][0]["relation_id"]
        before = gifted["player"]["cultivation"]["heart_demon"]
        ended = self.engine.execute(
            game["id"], EndRelationship(actor_id, relation_id, "separated")
        ).game
        self.assertEqual(ended["relationships"], [])
        self.assertEqual(
            ended["player"]["cultivation"]["heart_demon"], before + 25.0
        )

    def test_friend_interactions_award_opportunity_and_enforce_cooldown(self):
        game = self.engine.create_game("论道", seed=1202)
        actor_id = game["player"]["id"]
        friend_id = self._register(game["id"], "青简")
        self.engine.execute(
            game["id"], FormRelationship(actor_id, friend_id, "friend")
        )
        before = self.engine.get_game(game["id"])["player"]["cultivation"]["opportunity"]
        discussed = self.engine.execute(
            game["id"], InteractDaoFriend(actor_id, friend_id, "discuss")
        ).game
        self.assertGreater(
            discussed["player"]["cultivation"]["opportunity"], before
        )
        self.assertEqual(discussed["relationships"][0]["metadata"]["affinity"], 2.0)
        with self.assertRaisesRegex(ValueError, "本年度"):
            self.engine.execute(
                game["id"], InteractDaoFriend(actor_id, friend_id, "discuss")
            )

    def test_disciple_requests_master_requests_and_gifts_are_persistent(self):
        game = self.engine.create_game("传承", seed=1203)
        actor_id = game["player"]["id"]
        state = self.engine.store.load(game["id"])
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation.update({"realm_id": "foundation", "layer": 1})
        state.entities.put(actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="传承", expected_revision=state.revision
        )

        disciple_id = self._register(game["id"], "问心")
        offered = self.engine.execute(
            game["id"], OfferDiscipleRequest(disciple_id, actor_id)
        ).game
        request_id = offered["disciple_requests"][0]["request_id"]
        accepted = self.engine.execute(
            game["id"], RespondDiscipleRequest(actor_id, request_id, True)
        ).game
        self.assertEqual(accepted["disciple_requests"], [])
        self.assertEqual(accepted["relationships"][0]["role"], "master")

        self.engine.execute(game["id"], GrantItem(actor_id, "spirit_sword", 1, "test"))
        gifted = self.engine.execute(
            game["id"], GiftDisciple(actor_id, disciple_id, "item", "spirit_sword")
        ).game
        self.assertEqual(
            gifted["relationships"][0]["metadata"]["items"]["spirit_sword"], 1
        )

        master_id = self._register(game["id"], "玄师", realm_id="core")
        self.engine.execute(
            game["id"], FormRelationship(master_id, actor_id, "master_disciple")
        )
        requested = self.engine.execute(
            game["id"], RequestFromMaster(actor_id, "item")
        )
        event = next(
            row for row in requested.events
            if row["event_type"] == "relationship.master.requested"
        )
        self.assertEqual(event["payload"]["kind"], "item")
        with self.assertRaisesRegex(ValueError, "本年度"):
            self.engine.execute(game["id"], RequestFromMaster(actor_id, "item"))


if __name__ == "__main__":
    unittest.main()
