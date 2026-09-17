import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.migration import ShadowCharacterSpec, ShadowCommand, ShadowRunner
from cultivation_life.v2 import V2GameEngine
from cultivation_life.v2.infrastructure import (
    LegacyImportBlockedError,
    LegacyImportError,
)


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V2LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.v1_directory = self.root / "v1"
        self.v2_database = self.root / "v2.sqlite3"
        self.v1 = GameEngine(SOURCE_ROOT, self.v1_directory)
        self.v2 = V2GameEngine(self.v2_database)

    def tearDown(self):
        self.temp.cleanup()

    def _legacy_save(self) -> Path:
        created = self.v1.create_game(
            "归档者", "supreme_wood", "dao", seed=2468, gender="female"
        )
        game = self.v1.store.load(created["id"])
        game.player.age = 24
        game.player.realm_index = 1
        game.player.layer = 2
        game.player.opportunity = 37.5
        game.player.heart_demon = 4.0
        game.player.qi_experience["spirit"] = 19.0
        game.player.faction_id = "tianjian"
        game.player.faction_join_age = 20
        game.player.faction_contribution = 73
        game.player.faction_reward_preference = "mana"
        game.player.faction_hp_bonus = 6
        game.player.faction_mp_bonus = 8
        game.player.faction_combat_bonus = 9
        game.player.story_flags = ["legacy_story_flag"]
        game.player.milestones = {"legacy_milestone": 22}
        game.player.karma = 7
        game.player.fame = 11
        game.player.sha_qi = 13
        game.player.body_training = 5
        game.player.body_progress = 42.0
        game.player.body_technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_BODY_MORTAL"])
        game.player.divine_sense_rank = 2
        game.player.divine_sense_experience = 17.0
        game.player.divine_sense_technique = copy.deepcopy(TECHNIQUE_CATALOG["TECH_SPIRIT_SENSE"])
        transformation_id = "TECH_MYRIAD_FORM_SPECTRUM"
        game.player.transformation_technique = copy.deepcopy(TECHNIQUE_CATALOG[transformation_id])
        game.player.known_transformations = ["FORM_PHOENIX"]
        game.player.transformation_mastery = {
            "FORM_PHOENIX": {"purity": 0.3, "source_type": "旧档测试"}
        }
        game.player.transformation_loadouts = {
            transformation_id: {"stored": ["FORM_PHOENIX"], "active": ["FORM_PHOENIX"]}
        }
        game.player.dao_friends = [{
            "id": "friend-old-1",
            "name": "旧雨",
            "gender": "male",
            "age": 31,
            "lifespan": 100,
            "alive": True,
            "world": "human",
            "race": "human",
            "path": "dao",
            "spirit_root": "supreme_water",
            "realm_index": 1,
            "layer": 3,
        }]
        self.v1.store.save(game)
        return self.v1_directory / f"{game.id}.json"

    def test_import_preserves_supported_state_and_never_changes_source(self):
        source = self._legacy_save()
        before = source.read_bytes()

        result = self.v2.import_v1_save(source)

        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(result.game["id"], json.loads(before)["id"])
        self.assertEqual(result.game["player"]["name"], "归档者")
        self.assertEqual(result.game["player"]["gender"], "female")
        self.assertEqual(result.game["player"]["age"], 24)
        self.assertEqual(result.game["player"]["cultivation"]["realm_id"], "qi")
        self.assertEqual(result.game["player"]["cultivation"]["layer"], 2)
        self.assertEqual(result.game["player"]["cultivation"]["opportunity"], 37.5)
        self.assertEqual(result.game["faction"]["external_id"], "tianjian")
        self.assertEqual(result.game["faction"]["contribution"], 73)
        self.assertEqual(result.game["faction"]["reward_preference"], "mana")
        self.assertEqual(
            result.game["faction"]["permanent_benefits"],
            {"hp": 6.0, "mp": 8.0, "combat": 9.0},
        )
        self.assertEqual(result.game["relationships"][0]["kind"], "friend")
        self.assertEqual(result.game["relationships"][0]["other"]["name"], "旧雨")
        self.assertEqual(
            {row["id"]: row["quantity"] for row in result.game["inventory"]},
            {"spirit_sword": 1},
        )
        self.assertIn("legacy_story_flag", result.game["story"]["flags"])
        self.assertEqual(result.game["story"]["milestones"]["legacy_milestone"], 22)
        self.assertEqual(
            result.game["story"]["attributes"],
            {"karma": 7.0, "fame": 11.0, "sha_qi": 13.0},
        )
        self.assertEqual(result.game["player"]["body"]["layer"], 5)
        self.assertEqual(result.game["player"]["body"]["progress"], 42.0)
        self.assertEqual(result.game["player"]["divine_sense"]["rank"], 2)
        self.assertEqual(result.game["player"]["divine_sense"]["experience"], 17.0)
        self.assertEqual(
            result.game["player"]["transformations"]["active"], ["FORM_PHOENIX"]
        )
        self.assertTrue(result.game["story"]["history"])
        self.assertEqual(result.report["source_version"], 5)
        self.assertEqual(result.report["imported_counts"]["relationships"], 1)
        self.assertTrue(result.report["source_sha256"])
        backup = Path(result.report["backup_path"])
        self.assertTrue(result.report["backup_created"])
        self.assertEqual(result.report["backup_sha256"], result.report["source_sha256"])
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(backup.parent, self.v2_database.parent / "legacy-v1-backups")
        self.assertEqual(self.v2.legacy_import_report(result.game["id"]), result.report)
        events = self.v2.event_journal(result.game["id"])
        self.assertTrue(any(row["event_type"] == "migration.v1.imported" for row in events))
        self.assertEqual(events[-1]["event_type"], "migration.v1.backup.verified")
        self.assertEqual(events[-1]["payload"]["backup_sha256"], result.report["source_sha256"])

    def test_duplicate_target_is_atomic_and_does_not_overwrite(self):
        source = self._legacy_save()
        first = self.v2.import_v1_save(source)
        with self.assertRaisesRegex(LegacyImportError, "已经导入"):
            self.v2.import_v1_save(source)
        self.assertEqual(len(self.v2.list_games()), 1)
        self.assertEqual(self.v2.get_game(first.game["id"])["revision"], 1)

    def test_import_preserves_family_and_concubine_lifecycle_state(self):
        source = self._legacy_save()
        document = json.loads(source.read_text(encoding="utf-8"))
        child = {
            "id": "legacy-heir",
            "name": "归宁",
            "gender": "female",
            "age": 9,
            "lifespan": 112,
            "alive": True,
            "world": "human",
            "race": "human",
            "path": "dao",
            "spirit_root": "supreme_wood",
            "realm_index": 1,
            "layer": 1,
            "cultivation_started": True,
        }
        document["player"]["offspring"] = [child]
        document["player"]["next_companion_conception_bonus"] = 0.16
        document["player"]["concubine_breakthrough_bonus"] = 0.01
        document["player"]["concubine_escape_reputation"] = 2
        document["player"]["concubine_status"] = {
            "owner_id": "legacy-owner",
            "owner_name": "玄明",
            "owner_world": "human",
            "owner_realm_index": 3,
            "owner_layer": 2,
            "turns": 4,
            "last_drain": 2.5,
            "dependent": True,
            "failed_escape_count": 1,
            "last_requests": {"stones": 2},
            "angered_until_unit": -1,
        }
        document["family"] = {
            "id": "legacy-family",
            "name": "归氏仙族",
            "world": "human",
            "path": "dao",
            "allegiance_race": "human",
            "founded_by_player": True,
            "extinct": False,
            "members": [{**child, "member_type": "本家"}],
        }
        source.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )

        result = self.v2.import_v1_save(source)

        self.assertEqual(result.game["family"]["offspring"][0]["name"], "归宁")
        self.assertEqual(result.game["family"]["pending_conception_bonus"], 0.16)
        self.assertEqual(result.game["family"]["name"], "归氏仙族")
        self.assertEqual(result.game["family"]["roster"][0]["name"], "归宁")
        concubines = result.game["concubine_system"]
        self.assertEqual(concubines["cauldron_breakthrough_bonus"], 0.01)
        self.assertEqual(concubines["escape_reputation"], 2)
        self.assertEqual(concubines["status"]["owner"]["name"], "玄明")
        self.assertTrue(concubines["status"]["dependent"])
        self.assertEqual(result.report["imported_counts"]["offspring"], 1)
        self.assertEqual(result.report["imported_counts"]["families"], 1)
        self.assertEqual(result.report["imported_counts"]["concubine_status"], 1)

    def test_live_workflows_and_frozen_auction_assets_block_import(self):
        source = self._legacy_save()
        document = json.loads(source.read_text(encoding="utf-8"))
        document["pending_event"] = {"id": "UNRESOLVED"}
        document["auction_state"] = {
            "lots": [{"id": "lot", "current_bidder": "player", "current_bid": 10}],
            "consignments": [{"content_id": "healing_pill"}],
        }
        source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(LegacyImportBlockedError) as raised:
            self.v2.import_v1_save(source)
        paths = {issue.path for issue in raised.exception.issues}
        self.assertEqual(paths, {"pending_event", "auction_state"})
        self.assertEqual(self.v2.list_games(), [])

    def test_backup_is_durable_even_if_target_database_write_fails(self):
        source = self._legacy_save()
        before = source.read_bytes()
        with mock.patch.object(self.v2.store, "create", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                self.v2.import_v1_save(source)
        backups = list((self.v2_database.parent / "legacy-v1-backups").glob("*.v1.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        self.assertEqual(self.v2.list_games(), [])

    def test_backup_failure_prevents_target_database_write(self):
        source = self._legacy_save()
        invalid_backup_directory = self.root / "not-a-directory"
        invalid_backup_directory.write_text("occupied", encoding="utf-8")
        engine = V2GameEngine(
            self.root / "other.sqlite3",
            legacy_backup_directory=invalid_backup_directory,
        )
        with self.assertRaises(OSError):
            engine.import_v1_save(source)
        self.assertEqual(engine.list_games(), [])

    def test_existing_identical_backup_is_reused_without_overwrite(self):
        source = self._legacy_save()
        backup_directory = self.root / "shared-backups"
        first_engine = V2GameEngine(
            self.root / "first.sqlite3", legacy_backup_directory=backup_directory
        )
        first = first_engine.import_v1_save(source, target_game_id="first-import")
        backup = Path(first.report["backup_path"])
        before_mtime = backup.stat().st_mtime_ns
        second_engine = V2GameEngine(
            self.root / "second.sqlite3", legacy_backup_directory=backup_directory
        )
        second = second_engine.import_v1_save(source, target_game_id="second-import")
        self.assertFalse(second.report["backup_created"])
        self.assertEqual(Path(second.report["backup_path"]), backup)
        self.assertEqual(backup.stat().st_mtime_ns, before_mtime)

    def test_duplicate_json_keys_are_rejected_before_write(self):
        source = self.root / "duplicate.json"
        source.write_text(
            '{"version":5,"version":4,"id":"x","seed":1,"player":{}}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LegacyImportError, "重复JSON键"):
            self.v2.import_v1_save(source)
        self.assertEqual(self.v2.list_games(), [])

    def test_non_finite_json_numbers_are_rejected_before_write(self):
        source = self.root / "nan.json"
        source.write_text(
            '{"version":5,"id":"x","seed":1,"created_at":"now",'
            '"player":{"name":"x","spirit_root":"supreme_wood","opportunity":NaN}}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LegacyImportError, "非法数值"):
            self.v2.import_v1_save(source)
        self.assertEqual(self.v2.list_games(), [])

    def test_supported_ghost_and_monster_state_is_mapped_to_separate_components(self):
        ghost_created = self.v1.create_game(
            "旧魂", "supreme_water", "ghost", seed=71, start_world="hell"
        )
        ghost = self.v1.store.load(ghost_created["id"])
        ghost.player.ghost_wangsheng_energy = 9
        ghost.player.ghost_intrinsic_hp_current = 73.0
        ghost.player.ghost_intrinsic_mp_current = 61.0
        self.v1.store.save(ghost)
        ghost_result = self.v2.import_v1_save(
            self.v1_directory / f"{ghost.id}.json"
        )
        self.assertEqual(ghost_result.game["extensions"]["ghost"]["wangsheng"], 9)
        self.assertEqual(ghost_result.game["extensions"]["ghost"]["intrinsic_hp"], 73.0)

        monster_created = self.v1.create_game(
            "旧妖", "supreme_wood", "monster", seed=72,
            start_world="monster_realm", monster_species_id="serpent",
        )
        monster = self.v1.store.load(monster_created["id"])
        monster.player.monster_adaptations = ["water"]
        monster.player.monster_adaptation_progress = {"water": 4}
        self.v1.store.save(monster)
        monster_result = self.v2.import_v1_save(
            self.v1_directory / f"{monster.id}.json"
        )
        bloodline = monster_result.game["extensions"]["monster_bloodline"]
        self.assertEqual(bloodline["species_id"], "serpent")
        self.assertEqual(bloodline["adaptations"], ["water"])
        self.assertEqual(bloodline["adaptation_years"], {"water": 4})


class V1V2ShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, suffix: str):
        runner = ShadowRunner(
            SOURCE_ROOT,
            v1_save_directory=self.root / f"v1-{suffix}",
            v2_database_path=self.root / f"v2-{suffix}.sqlite3",
        )
        return runner.run(
            ShadowCharacterSpec(name="同源", seed=123, spirit_root="supreme_wood"),
            [ShadowCommand("rest", 1)],
        )

    def test_same_seed_and_commands_produce_reproducible_comparison_report(self):
        first = self._run("a")
        second = self._run("b")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(len(first.steps), 2)
        self.assertEqual(first.steps[0].command, "create")
        self.assertFalse(first.steps[0].v1_error)
        self.assertFalse(first.steps[0].v2_error)

    def test_shadow_projection_ignores_ids_and_matches_initial_inventory(self):
        report = self._run("gap")
        create_differences = [row for row in report.differences if row.step == 0]
        self.assertFalse(any(row.severity == "error" for row in create_differences))
        self.assertFalse(any(row.path == "inventory" for row in create_differences))
        self.assertEqual(
            report.steps[0].v2["inventory"],
            {"spirit_sword": 1},
        )
        self.assertEqual(report.status, "matched")

    def test_creation_failure_is_reported_instead_of_crashing_harness(self):
        runner = ShadowRunner(
            SOURCE_ROOT,
            v1_save_directory=self.root / "v1-create-failure",
            v2_database_path=self.root / "v2-create-failure.sqlite3",
        )
        report = runner.run(ShadowCharacterSpec(name="", seed=9), [])
        self.assertEqual(report.status, "execution_error")
        self.assertIsNone(report.steps[0].v1_error)
        self.assertIn("角色名", report.steps[0].v2_error)
        self.assertEqual(report.differences[0].path, "execution")


if __name__ == "__main__":
    unittest.main()
