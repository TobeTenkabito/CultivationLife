import copy
import random
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, max_hp, max_mp


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class BaseV12UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = GameEngine(SOURCE_ROOT, Path(self.temp.name) / "saves")

    def tearDown(self):
        self.temp.cleanup()

    def test_reconcile_neighbors_reduces_fame_once_per_action_unit(self):
        made = self.engine.create_game("和事人", "none", "dao", 12001, preset_id="core")
        game = self.engine.store.load(made["id"])
        game.player.fame = 100
        self.engine.store.save(game)

        shown = self.engine.advance(made["id"], "befriend_neighbors")

        self.assertEqual(shown["player"]["fame"], 70)
        record = next(row for row in shown["history"] if row["event_id"] == "ACT_BEFRIEND_NEIGHBORS")
        self.assertEqual(record["state_diff"]["fame_reduction"], 30)

    def test_monster_kills_other_paths_without_karma_and_only_dao_grants_sha(self):
        made = self.engine.create_game(
            "山君", "supreme_earth", "monster", 12002, monster_species_id="fox",
        )
        original = self.engine.store.load(made["id"])
        original.player.realm_index = 3
        original.player.layer = 1
        original.player.hp = max_hp(original.player)
        original.player.mp = max_mp(original.player)
        for victim_path in ("dao", "buddhist", "confucian", "demonic", "ghost"):
            game = copy.deepcopy(original)
            target = {
                "target_name": victim_path, "target_power": 1,
                "target_realm_index": 1, "target_layer": 1,
                "combat_type": "cultivator", "kill_karma": True,
                "members": [{
                    "name": victim_path, "power": 1, "realm_index": 1,
                    "layer": 1, "race": "human", "path": victim_path,
                }],
            }
            result, summary = self.engine._combat(game, target, True, random.Random(1))
            self.assertEqual(result, "killed")
            self.assertEqual(game.player.karma, 0, victim_path)
            self.assertEqual(game.player.sha_qi > 0, victim_path == "dao")
            self.assertIn("不沾因果", summary)

    def test_root_manual_names_and_world_scoped_supplements(self):
        self.assertEqual(ITEM_CATALOG["jinque_metal"].name, "金阙残书·金")
        self.assertEqual(ITEM_CATALOG["zique_metal"].name, "紫阙玉书·金")
        self.assertEqual(ITEM_CATALOG["moque_metal"].name, "魔阙·金")
        monster_worlds = {
            row["world"] for row in MARKET_GOODS if row["content_id"] == "yaoque_metal"
        }
        ghost_worlds = {
            row["world"] for row in MARKET_GOODS if row["content_id"] == "mingque_metal"
        }
        self.assertEqual(monster_worlds, {"monster_realm", "phantom_underworld"})
        self.assertEqual(ghost_worlds, {"hell"})

        made = self.engine.create_game("归魂", "mutated_yin", "ghost", 12003, start_world="hell")
        game = self.engine.store.load(made["id"])
        game.player.realm_index = 5
        game.player.world = "hell"
        add_item(game.player, "mingque_metal")
        self.engine.store.save(game)
        shown = self.engine.use_item(made["id"], "mingque_metal")
        self.assertIn("metal", shown["player"]["additional_roots"])

    def test_new_achievement_conditions_cover_base_and_dlc_state(self):
        made = self.engine.create_game(
            "祖灵", "supreme_wood", "monster", 12004, monster_species_id="serpent",
        )
        game = self.engine.store.load(made["id"])
        matches = self.engine.achievements._matches

        game.player.puppets = [
            {"id": str(index), "type": "corpse", "alive": True} for index in range(16)
        ]
        self.assertTrue(matches({"puppet_count": {"type": "corpse", "minimum": 16}}, game, player_rank=None))
        game.player.milestones.update({
            "companion_turned_corpse": 1, "master_turned_corpse": 1,
            "became_wanted_target": 1, "dissolved_wanted_power": 1,
            "enemy_initiative_streak": 5, "annexed_faction": 1,
        })
        for milestone in (
            "companion_turned_corpse", "master_turned_corpse", "dissolved_wanted_power",
            "enemy_initiative_streak", "annexed_faction",
        ):
            self.assertTrue(matches({"milestone_at_least": {"id": milestone, "value": 1}}, game, player_rank=None))
        self.assertTrue(matches({"wanted_target": True}, game, player_rank=None))

        game.player.realm_index = 12
        game.player.monster_evolution_history.append("SERPENT_NETHER_TRUE_4")
        game.player.monster_custom_lineage_id = "custom-lineage-test"
        game.player.monster_custom_lineage = {"id": "custom-lineage-test", "name": "试祖"}
        self.assertTrue(matches({"monster_atavism_completed": True}, game, player_rank=None))
        self.assertTrue(matches({"monster_custom_lineage": True}, game, player_rank=None))

        game.heavenly_court = {"offices": {
            str(index): {"holder_id": "player"} for index in range(7)
        }}
        self.assertTrue(matches({"heavenly_court_controls": 7}, game, player_rank=None))
        game.natal_artifact = {"item_id": "spirit_sword"}
        game.player.natal_artifact_combat_bonus = 1_000_000
        self.assertTrue(matches({
            "natal_artifact": {"item_id": "spirit_sword", "minimum_combat_bonus": 1_000_000}
        }, game, player_rank=None))

    def test_relationship_corpse_conversion_records_permanent_achievement_milestones(self):
        made = self.engine.create_game("尸主", "supreme_fire", "demonic", 12005)
        game = self.engine.store.load(made["id"])

        class AlwaysSucceed:
            @staticmethod
            def random():
                return 0.0

        for kind in ("companion", "master"):
            target = {
                "id": kind, "name": kind, "realm_index": 1, "layer": 1,
                "combat_power": 1, "affinity": 0, "path": "dao",
                "source": f"relationship:{kind}",
            }
            game.player.prisoners.append(target)
            result, _ = self.engine._convert_to_puppet(game, target, "corpse", AlwaysSucceed(), False)
            self.assertEqual(result, "created")

        self.assertEqual(game.player.milestones["companion_turned_corpse"], 1)
        self.assertEqual(game.player.milestones["master_turned_corpse"], 1)
        self.assertEqual(
            {puppet["source"] for puppet in game.player.puppets},
            {"relationship:companion", "relationship:master"},
        )

    def test_achievement_catalog_contains_thirteen_base_and_three_dlc_additions(self):
        catalog = self.engine.list_achievements()["achievements"]
        names = {row["name"] for row in catalog}
        expected_base = {
            "秦始皇陵兵马俑", "生生世世爱", "欺师灭祖", "魔尊现世", "真灵之身",
            "无妄之灾", "见一个杀一个", "头晕目眩", "胃口真大", "全村最好的剑",
            "位列仙班", "说一不二", "共和国里当皇帝",
        }
        expected_dlc = {"返祖现象", "物种起源", "光耀门楣"}
        self.assertTrue(expected_base | expected_dlc <= names)
        for row in catalog:
            if row["name"] in expected_dlc:
                self.assertEqual(row["source"]["id"], "official.monster-bloodlines")


if __name__ == "__main__":
    unittest.main()
