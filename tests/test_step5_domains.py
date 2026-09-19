import tempfile
import unittest
import json
import shutil
from pathlib import Path

from cultivation_life.v2 import (
    AssignFactionPosition,
    ConfigureMonsterBloodline,
    FoundFaction,
    GrantItem,
    GrantTechnique,
    JoinFaction,
    RegisterCharacter,
    ToggleMarketOfferLock,
    V2GameEngine,
)
from cultivation_life.v2.domain.character import LIFE
from cultivation_life.v2.domain.extensions import INTRIGUE_GOVERNANCE
from cultivation_life.v2.infrastructure import V2ContentLoader


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V2StepFiveDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.temp.name) / "v2.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _resolve_pending(engine: V2GameEngine, game_id: str) -> dict:
        game = engine.get_game(game_id)
        while game["pending_event"] is not None:
            choice = next(row for row in game["pending_event"]["choices"] if row["enabled"])
            game = engine.choose(game_id, choice["id"]).game
        return game

    def _reach_qi(self, game: dict) -> dict:
        actor_id = game["player"]["id"]
        self.engine.execute(
            game["id"],
            GrantTechnique(actor_id=actor_id, technique_id="TECH_BASIC_QI", equip_main=True),
        )
        self.engine.perform_action(game["id"], "cultivate", 3)
        self._resolve_pending(self.engine, game["id"])
        return self.engine.attempt_breakthrough(game["id"]).game

    def _register_character(
        self, game_id: str, name: str, *, realm_id: str = "mortal", layer: int = 1,
    ) -> str:
        execution = self.engine.execute(
            game_id,
            RegisterCharacter(
                name=name,
                age=20,
                gender="female",
                race="human",
                spirit_root="supreme_water",
                path="dao",
                realm_id=realm_id,
                layer=layer,
                world_id="human",
                lifespan=100,
            ),
        )
        return str(next(
            event["payload"]["entity_id"]
            for event in execution.events
            if event["event_type"] == "character.created"
        ))

    def test_enabled_dlc_content_is_merged_without_importing_v1_runtime(self):
        extensions = {row.id: row.status for row in self.engine.definitions.extensions}
        self.assertEqual(extensions, {
            "official.ghost-reincarnation": "loaded",
            "official.intrigue-coalitions": "loaded",
            "official.monster-bloodlines": "loaded",
        })
        self.assertTrue(self.engine.definitions.worlds["hell"].enabled)
        self.assertGreaterEqual(len(self.engine.definitions.worlds["hell"].locations), 12)
        self.assertTrue(self.engine.definitions.worlds["monster_realm"].enabled)
        self.assertIn("serpent", {
            row["id"]
            for row in self.engine.definitions.extension_documents["monster_bloodlines.json"]["species"]
        })
        game = self.engine.create_game("扩展索引", seed=800)
        self.assertEqual(
            self.engine.store.load(game["id"]).content_packages,
            {
                row.id: row.version
                for row in self.engine.definitions.extensions
                if row.status == "loaded"
            },
        )

    def test_invalid_extension_is_skipped_without_breaking_base_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            content = project / "content"
            content.mkdir()
            for name in V2ContentLoader.REQUIRED_FILES:
                shutil.copy2(SOURCE_ROOT / "content" / name, content / name)
            package = project / "dlc" / "broken-market"
            (package / "content").mkdir(parents=True)
            (package / "manifest.json").write_text(json.dumps({
                "schema_version": 1,
                "api_version": 1,
                "id": "test.broken-market",
                "name": "无效坊市包",
                "version": "1.0.0",
                "kind": "dlc",
                "enabled": True,
                "load_order": 10,
                "requires": [],
            }, ensure_ascii=False), encoding="utf-8")
            (package / "content" / "market.json").write_text(json.dumps({
                "schema_version": 1,
                "goods": [{
                    "world": "human",
                    "kind": "item",
                    "content_id": "missing_item",
                    "tier": 1,
                    "price": 1,
                }],
            }), encoding="utf-8")

            definitions = V2ContentLoader.load(content, project_root=project)
            extension = next(row for row in definitions.extensions if row.id == "test.broken-market")
            self.assertEqual(extension.status, "error")
            self.assertIn("spirit_stone", definitions.items)
            self.assertNotIn("missing_item", definitions.items)

    def test_market_purchase_and_lock_survive_refresh(self):
        game = self._reach_qi(self.engine.create_game("商途", seed=801))
        actor_id = game["player"]["id"]
        self.engine.execute(
            game["id"], GrantItem(actor_id=actor_id, item_id="spirit_stone", quantity=1_000)
        )
        market = self.engine.refresh_market(game["id"]).game["market"]
        self.assertTrue(market["offers"])
        locked_offer = market["offers"][0]
        locked = self.engine.execute(
            game["id"],
            ToggleMarketOfferLock(actor_id=actor_id, offer_id=locked_offer["id"]),
        ).game
        self.assertTrue(next(
            row for row in locked["market"]["offers"] if row["id"] == locked_offer["id"]
        )["locked"])
        refreshed = self.engine.refresh_market(game["id"], force=True).game
        retained = next(
            row for row in refreshed["market"]["offers"] if row["id"] == locked_offer["id"]
        )
        self.assertTrue(retained["locked"])

        item_offer = next(row for row in refreshed["market"]["offers"] if row["kind"] == "item")
        before_stones = refreshed["market"]["spirit_stones"]
        purchased = self.engine.buy_market_offer(game["id"], item_offer["id"]).game
        self.assertEqual(
            purchased["market"]["spirit_stones"], before_stones - int(item_offer["price"])
        )
        owned = {row["id"]: row["quantity"] for row in purchased["inventory"]}
        self.assertGreaterEqual(owned[item_offer["content_id"]], 1)

    def test_failed_market_purchase_is_atomic(self):
        game = self._reach_qi(self.engine.create_game("穷修", seed=802))
        refreshed = self.engine.refresh_market(game["id"]).game
        offer_id = refreshed["market"]["offers"][0]["id"]
        revision = refreshed["revision"]
        with self.assertRaisesRegex(ValueError, "灵石"):
            self.engine.buy_market_offer(game["id"], offer_id)
        unchanged = self.engine.get_game(game["id"])
        self.assertEqual(unchanged["revision"], revision)
        self.assertEqual(unchanged["market"]["spirit_stones"], 0)
        self.assertFalse(next(
            row for row in unchanged["market"]["offers"] if row["id"] == offer_id
        )["sold"])

    def test_combat_uses_canonical_characters_and_records_lethal_result(self):
        game = self.engine.create_game("剑试", seed=803)
        actor_id = game["player"]["id"]
        target_id = self._register_character(game["id"], "试剑傀儡")
        self.engine.execute(
            game["id"], GrantItem(actor_id=actor_id, item_id="spirit_sword", quantity=1)
        )
        result = self.engine.fight(game["id"], target_id, objective="kill")
        self.assertEqual(result.game["combat"]["last_report"]["outcome"], "victory")
        self.assertEqual(result.game["combat"]["last_report"]["target_id"], target_id)
        target_life = self.engine.store.load(game["id"]).entities.require(target_id, LIFE)
        self.assertFalse(target_life["alive"])
        self.assertTrue(any(event["event_type"] == "combat.resolved" for event in result.events))
        self.assertTrue(any(event["event_type"] == "character.died" for event in result.events))

    def test_ghost_and_monster_dlc_keep_separate_components(self):
        ghost = self.engine.create_game(
            "幽灯", seed=804, path="ghost", spirit_root="mutated_yin", start_world="hell"
        )
        self.assertIsNotNone(ghost["extensions"]["ghost"])
        advanced = self.engine.perform_timed_action(ghost["id"], "rest", 1).game
        self.assertGreater(advanced["extensions"]["ghost"]["erosion_rate_pp"], 0)
        self.assertIsNone(advanced["extensions"]["monster_bloodline"])

        monster_engine = V2GameEngine(Path(self.temp.name) / "monster.sqlite3")
        monster = monster_engine.create_game(
            "青蛇", seed=805, path="monster", spirit_root="supreme_wood",
            start_world="monster_realm",
        )
        self.assertEqual(
            monster["player"]["cultivation"]["main_technique"]["id"],
            "TECH_MONSTER_BREATHING",
        )
        cultivated = monster_engine.perform_action(monster["id"], "cultivate", 1).game
        self.assertGreater(cultivated["player"]["cultivation"]["opportunity"], 0)
        self._resolve_pending(monster_engine, monster["id"])
        actor_id = monster["player"]["id"]
        configured = monster_engine.execute(
            monster["id"], ConfigureMonsterBloodline(actor_id=actor_id, species_id="serpent")
        ).game
        self.assertEqual(
            configured["extensions"]["monster_bloodline"]["species_id"], "serpent"
        )
        self.assertIsNone(configured["extensions"]["ghost"])

    def test_intrigue_positions_reference_faction_members(self):
        game = self.engine.create_game("掌门", seed=806)
        actor_id = game["player"]["id"]
        faction = self.engine.execute(
            game["id"], FoundFaction(founder_id=actor_id, name="清微宗")
        ).game["faction"]
        npc_id = self._register_character(game["id"], "执事", realm_id="foundation", layer=3)
        self.engine.execute(
            game["id"], JoinFaction(character_id=npc_id, faction_id=faction["id"])
        )
        self.engine.execute(
            game["id"],
            AssignFactionPosition(
                actor_id=actor_id,
                faction_id=faction["id"],
                member_id=npc_id,
                position_id="affairs_elder",
            ),
        )
        state = self.engine.store.load(game["id"])
        intrigue = state.entities.require(faction["id"], INTRIGUE_GOVERNANCE)
        self.assertEqual(intrigue["positions"]["affairs_elder"], npc_id)


if __name__ == "__main__":
    unittest.main()
