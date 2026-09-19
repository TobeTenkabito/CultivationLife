from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from cultivation_life.application import GameEngine
from cultivation_life.domain.character import RegisterCharacter
from cultivation_life.domain.relations import FormRelationship


class FrontendDataCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.temporary.name) / "games.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_spirit_field_contract_drives_reclaim_plant_irrigate_and_harvest(self) -> None:
        game = self.engine.create_game("灵田验真", seed=4201, preset_id="core")
        field = game["production"]
        self.assertTrue(field["can_reclaim"])
        self.assertEqual(field["spirit_stones"], 120)
        self.assertGreater(field["irrigation_min_mp"], 0)

        game = self.engine.reclaim_spirit_field(game["id"]).game
        self.assertEqual(game["production"]["reclaimed_qing"], 1)
        self.assertEqual(game["production"]["spirit_stones"], 0)

        state = self.engine.store.load(game["id"])
        actor_id = str(state.controlled_entity_id)
        inventory = state.entities.require(actor_id, "economy.inventory")
        inventory["items"]["dew_grass_seed"] = 1
        state.entities.put(actor_id, "economy.inventory", inventory)
        self.engine.store.save(
            state, [], player_name="灵田验真", expected_revision=state.revision
        )
        game = self.engine.get_game(game["id"])
        self.assertEqual(game["production"]["seeds"][0]["plant_id"], "dew_grass")

        game = self.engine.plant_spirit_crop(game["id"], "dew_grass", 0).game
        plot_id = game["production"]["plots"][0]["id"]
        before_mp = game["production"]["mp"]
        amount = math.ceil(game["production"]["irrigation_min_mp"])
        game = self.engine.irrigate_spirit_crop(
            game["id"], plot_id, mp_amount=amount
        ).game
        self.assertGreater(game["production"]["plots"][0]["growth_years"], 0)
        self.assertAlmostEqual(before_mp - game["production"]["mp"], amount, places=1)

        game = self.engine.harvest_spirit_crop(game["id"], plot_id).game
        self.assertEqual(len(game["assets"]["instances"]), 1)
        material = game["production"]["alchemy"]["materials"][0]
        self.assertEqual(material["id"], game["assets"]["instances"][0]["id"])
        self.assertEqual(game["market"]["sellable_plants"][0]["id"], material["id"])

    def test_world_npcs_and_relationship_actions_use_canonical_entities(self) -> None:
        game = self.engine.create_game("人物验真", seed=4202, preset_id="core")
        actor_id = game["player"]["id"]
        self.assertGreaterEqual(len(game["characters"]), 8)
        fixed = next(row for row in game["characters"] if row["external_id"] == "xiang_zhili")
        for field in (
            "title", "gender_name", "realm_name", "path_name", "race_name",
            "spirit_root_name", "combat_power", "status",
        ):
            self.assertNotIn(fixed.get(field), (None, "", "undefined"))

        self.engine.execute(
            game["id"], FormRelationship(actor_id, fixed["id"], "friend", {"affinity": 30})
        )
        game = self.engine.manage_party(game["id"], fixed["id"], "invite").game
        self.assertEqual(game["party"]["members"][0]["id"], fixed["id"])

        self.engine.execute(game["id"], RegisterCharacter(
            name="试剑弟子", age=18, gender="female", race="human",
            spirit_root="supreme_metal", path="dao", realm_id="qi", layer=1,
            world_id="human", lifespan=100,
        ))
        state = self.engine.store.load(game["id"])
        disciple_id = next(
            entity_id for entity_id in state.entities.with_component("core.identity")
            if state.entities.require(entity_id, "core.identity")["name"] == "试剑弟子"
        )
        self.engine.execute(
            game["id"], FormRelationship(actor_id, disciple_id, "master_disciple")
        )
        game = self.engine.gift_disciple(
            game["id"], disciple_id, "item", "spirit_stone"
        ).game
        relation = next(
            row for row in game["relationships"]
            if row["other"]["id"] == disciple_id
        )
        self.assertEqual(relation["metadata"]["items"]["spirit_stone"], 1)
        self.assertEqual(relation["other"]["realm_name"], "练气1层")

        game = self.engine.gift_disciple(
            game["id"], disciple_id, "technique", "TECH_COMMON_CORE"
        ).game
        relation = next(
            row for row in game["relationships"]
            if row["other"]["id"] == disciple_id
        )
        self.assertIn("TECH_COMMON_CORE", relation["other"]["techniques"])


if __name__ == "__main__":
    unittest.main()
