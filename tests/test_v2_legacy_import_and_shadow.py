import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.migration import ShadowCharacterSpec, ShadowCommand, ShadowRunner
from cultivation_life.possession_system import enter_host_body
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
        self.assertEqual(len(result.game["faction"]["roster"]), 7)
        self.assertEqual(result.report["imported_counts"]["faction_npcs"], 6)
        self.assertTrue(result.game["governance"]["relations"])
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

    def test_import_translates_demonic_entities_and_active_imprisonment(self):
        source = self._legacy_save()
        document = json.loads(source.read_text(encoding="utf-8"))
        document["player"]["prisoners"] = [{
            "id": "legacy-prisoner",
            "name": "旧档战俘",
            "gender": "male",
            "age": 28,
            "lifespan": 100,
            "alive": True,
            "world": "human",
            "race": "human",
            "path": "dao",
            "spirit_root": "supreme_wood",
            "realm_index": 1,
            "layer": 1,
            "combat_power": 25,
        }]
        document["player"]["puppets"] = [{
            "id": "legacy-puppet",
            "name": "旧档机关傀儡",
            "type": "mechanical",
            "realm_index": 1,
            "layer": 1,
            "combat_power": 30,
            "original_power": 30,
            "control": 100,
            "alive": True,
        }]
        document["player"]["foreign_souls"] = [{
            "id": "legacy-soul",
            "name": "旧档元神",
            "realm_index": 1,
            "strength": 1.5,
            "combat_power": 20,
            "progress": 40,
            "required": 100,
            "remaining_bonus": 0.08,
            "refined": False,
        }]
        document["player"]["devouring_breakthrough_bonus"] = 0.12
        document["player"]["imprisonment"] = {
            "key": "sect:tianjian",
            "name": "天剑宗",
            "facility": "faction_prison",
            "remaining_years": 2,
            "sentence_years": 4,
            "captured_age": 23,
            "hostility": 20,
            "hostility_reduction_per_year": 5,
        }
        source.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )

        result = self.v2.import_v1_save(source)

        demonic = result.game["demonic_system"]
        self.assertEqual(len(demonic["prisoners"]), 1)
        self.assertEqual(demonic["prisoners"][0]["name"], "旧档战俘")
        self.assertEqual(len(demonic["puppets"]), 1)
        self.assertEqual(demonic["puppets"][0]["type"], "mechanical")
        self.assertEqual(len(demonic["foreign_souls"]), 1)
        self.assertEqual(demonic["breakthrough_bonus"], 0.12)
        self.assertEqual(demonic["imprisonment"]["remaining_years"], 2)
        self.assertEqual(result.report["imported_counts"]["prisoners"], 1)
        self.assertEqual(result.report["imported_counts"]["puppets"], 1)
        self.assertEqual(result.report["imported_counts"]["foreign_souls"], 1)
        self.assertEqual(result.report["imported_counts"]["active_imprisonments"], 1)

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
        document["player"]["concubine_rejection_aftermath"] = [{
            "owner_id": "legacy-owner",
            "owner_name": "玄明",
            "owner_world": "human",
            "owner_realm_index": 3,
            "owner_layer": 2,
            "declined_unit": 5,
            "expires_unit": 7,
            "last_checked_unit": 5,
        }]
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
        self.assertEqual(len(concubines["rejection_aftermath"]), 1)
        self.assertEqual(
            concubines["rejection_aftermath"][0]["owner_id"],
            concubines["status"]["owner"]["id"],
        )
        self.assertEqual(result.report["imported_counts"]["offspring"], 1)
        self.assertEqual(result.report["imported_counts"]["families"], 1)
        self.assertEqual(result.report["imported_counts"]["concubine_status"], 1)

    def test_import_preserves_party_active_war_and_bounties(self):
        source = self._legacy_save()
        document = json.loads(source.read_text(encoding="utf-8"))
        friend = document["player"]["dao_friends"][0]
        document["player"]["party"] = [{"id": friend["id"], "name": friend["name"]}]
        document["player"]["joint_friend_crossing"] = [
            {"id": friend["id"], "name": friend["name"]}
        ]
        defender_id = document["sects"]["wanmo"]["npcs"][0]["id"]
        document["wars"] = [{
            "id": "legacy-war",
            "kind": "sect",
            "world": "human",
            "attacker_id": "tianjian",
            "defender_id": "wanmo",
            "status": "active",
            "start_age": 23,
            "start_unit": 3,
            "morale": {"attacker": 88, "defender": 77},
            "exhaustion": {"attacker": 12, "defender": 19},
            "war_score": 6,
            "battles": 2,
            "roster": {
                "attacker": [friend["id"]],
                "defender": [defender_id],
            },
            "roster_owner": {
                friend["id"]: "tianjian",
                defender_id: "wanmo",
            },
            "coalitions": {
                "attacker": [{"id": "tianjian"}],
                "defender": [{"id": "wanmo"}],
            },
            "controller": "player",
        }]
        document["player_bounties"] = [{
            "id": "legacy-bounty",
            "target_id": defender_id,
            "name": "旧敌",
            "world": "human",
            "status": "active",
            "attempts": 2,
            "target_power": 123,
            "authority": "sect",
            "issuer_name": "天剑宗",
        }]
        source.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )

        result = self.v2.import_v1_save(source)

        self.assertEqual(len(result.game["party"]["members"]), 1)
        self.assertEqual(result.game["party"]["members"][0]["name"], "旧雨")
        self.assertTrue(result.game["party"]["members"][0]["crossing_selected"])
        self.assertEqual(len(result.game["war_system"]["wars"]), 1)
        war = result.game["war_system"]["wars"][0]
        self.assertEqual(war["kind"], "faction")
        self.assertEqual(war["battles"], 2)
        self.assertEqual(war["morale"], {"attacker": 88.0, "defender": 77.0})
        self.assertEqual(len(war["roster"]["attacker"]), 1)
        self.assertEqual(len(war["roster"]["defender"]), 1)
        self.assertEqual(len(result.game["war_system"]["bounties"]), 1)
        self.assertEqual(result.game["war_system"]["bounties"][0]["attempts"], 2)
        self.assertEqual(result.report["imported_counts"]["party_members"], 1)
        self.assertEqual(result.report["imported_counts"]["wars"], 1)
        self.assertEqual(result.report["imported_counts"]["bounties"], 1)

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
        ghost.player.ghost_intrinsic_hp_reference = 120.0
        ghost.player.ghost_intrinsic_mp_reference = 115.0
        ghost.player.ghost_bound_souls = [{
            "id": "old-soul-1",
            "name": "旧魂侍",
            "realm_index": 2,
            "layer": 3,
            "combat_power": 800.0,
            "soul_pressure": 1.25,
            "soul_trait": {"name": "宿慧"},
        }]
        ghost.player.ghost_soul_slots = {"胎光": "old-soul-1"}
        ghost.player.ghost_attachment = {
            "item_id": "spirit_sword", "name": "灵木剑",
            "erosion_growth_multiplier": 0.8,
            "cultivation_efficiency_multiplier": 0.9,
        }
        ghost.ghost_parade = {
            "status": "active",
            "world": "hell",
            "location_id": ghost.player.location_id,
            "start_age": ghost.player.age,
            "end_age": ghost.player.age + 2,
            "announced": True,
            "participated": False,
            "souls": [{
                "id": "old-parade-soul",
                "name": "夜行旧魂",
                "realm_index": 1,
                "layer": 2,
                "combat_power": 90.0,
                "soul_pressure": 0.7,
            }],
        }
        self.v1.store.save(ghost)
        ghost_result = self.v2.import_v1_save(
            self.v1_directory / f"{ghost.id}.json"
        )
        self.assertEqual(ghost_result.game["extensions"]["ghost"]["wangsheng"], 9)
        self.assertEqual(ghost_result.game["extensions"]["ghost"]["intrinsic_hp"], 73.0)
        self.assertEqual(
            ghost_result.game["extensions"]["ghost"]["intrinsic_hp_reference"],
            120.0,
        )
        self.assertEqual(len(ghost_result.game["ghost_system"]["bound_souls"]), 1)
        self.assertEqual(
            next(
                row for row in ghost_result.game["ghost_system"]["slots"]
                if row["id"] == "胎光"
            )["soul_id"],
            ghost_result.game["ghost_system"]["bound_souls"][0]["id"],
        )
        self.assertEqual(
            ghost_result.game["ghost_system"]["attachment"]["item_id"],
            "spirit_sword",
        )
        self.assertEqual(ghost_result.game["ghost_system"]["parade"]["status"], "active")
        self.assertEqual(len(ghost_result.game["ghost_system"]["parade"]["souls"]), 1)

        monster_created = self.v1.create_game(
            "旧妖", "supreme_wood", "monster", seed=72,
            start_world="monster_realm", monster_species_id="serpent",
        )
        monster = self.v1.store.load(monster_created["id"])
        monster.player.monster_adaptations = ["water"]
        monster.player.monster_adaptation_progress = {"water": 4}
        monster.player.monster_lineage_deeds = {"victory": 2}
        monster.player.monster_custom_lineage_id = "custom-lineage-legacy"
        monster.player.monster_custom_lineage = {
            "id": "custom-lineage-legacy",
            "name": "旧谱祖血",
            "finalized_stage": 1,
            "spent_points": 9,
            "rules": [{
                "phase": "round_start", "schedule": "every",
                "condition": "always", "target": "player",
                "effect": "might", "value": 0.03, "cost": 9,
            }],
        }
        self.v1.store.save(monster)
        monster_result = self.v2.import_v1_save(
            self.v1_directory / f"{monster.id}.json"
        )
        bloodline = monster_result.game["extensions"]["monster_bloodline"]
        self.assertEqual(bloodline["species_id"], "serpent")
        self.assertEqual(bloodline["adaptations"], ["water"])
        self.assertEqual(bloodline["adaptation_years"], {"water": 4})
        self.assertEqual(bloodline["lineage_deeds"], {"victory": 2})
        self.assertEqual(
            monster_result.game["monster_system"]["custom_lineage"]["name"],
            "旧谱祖血",
        )

    def test_active_ghost_captor_is_imported_instead_of_blocked(self):
        created = self.v1.create_game(
            "受拘旧魂", "supreme_water", "ghost", seed=73, start_world="hell"
        )
        game = self.v1.store.load(created["id"])
        game.player.ghost_captor = {
            "id": "legacy-captor-1",
            "npc_id": "legacy-captor-1",
            "name": "旧档拘魂者",
            "gender": "male",
            "age": 80,
            "lifespan": 180,
            "alive": True,
            "world": "hell",
            "location_id": game.player.location_id,
            "race": "human",
            "path": "dao",
            "spirit_root": "supreme_fire",
            "realm_index": 2,
            "layer": 3,
            "combat_power": 1200.0,
            "followed_years": 4,
        }
        self.v1.store.save(game)

        imported = self.v2.import_v1_save(
            self.v1_directory / f"{game.id}.json"
        )
        captor = imported.game["ghost_system"]["captor"]
        self.assertEqual(captor["name"], "旧档拘魂者")
        self.assertTrue(captor["entity_id"].startswith("character:"))
        self.assertFalse(any(
            issue["path"] == "player.ghost_captor"
            for issue in imported.report["issues"]
        ))

    def test_active_ghost_possession_import_can_leave_host_in_v2(self):
        created = self.v1.create_game(
            "夺舍旧魂", "supreme_water", "ghost", seed=74, start_world="hell"
        )
        game = self.v1.store.load(created["id"])
        enter_host_body(game.player, {
            "id": "legacy-host-1",
            "name": "旧档宿主",
            "gender": "male",
            "age": 30,
            "lifespan": 120,
            "race": "human",
            "path": "dao",
            "spirit_root": "supreme_fire",
            "realm_index": 0,
            "layer": 1,
        })
        self.v1.store.save(game)

        imported = self.v2.import_v1_save(
            self.v1_directory / f"{game.id}.json"
        )
        self.assertEqual(imported.game["ghost_system"]["state"], "possessed")
        left = self.v2.leave_possessed_body(imported.game["id"]).game
        self.assertEqual(left["ghost_system"]["state"], "free")
        self.assertEqual(left["player"]["cultivation"]["path"], "ghost")
        self.assertEqual(
            left["player"]["divine_sense"]["technique_id"],
            "TECH_SOUL_ECHO_SENSE",
        )
        self.assertEqual(left["ghost_system"]["possession_count"], 1)


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
