from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life.v2 import (
    AttemptBreakthrough,
    ConfigureMonsterBloodline,
    ConfirmCustomLineage,
    EvolveMonster,
    PrepareCustomLineage,
    RegisterCharacter,
    ResolveCombat,
    V2GameEngine,
)
from cultivation_life.v2.domain.cultivation import CULTIVATION
from cultivation_life.v2.domain.extensions import MONSTER_BLOODLINE
from cultivation_life.v2.infrastructure.migrations import migrate_snapshot


class V2MonsterBatchNineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = V2GameEngine(Path(self.temporary.name) / "v2.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _create_monster(self) -> tuple[dict, str]:
        game = self.engine.create_game(
            "青鳞", seed=901, path="monster",
            spirit_root="supreme_wood", start_world="monster_realm",
        )
        actor_id = game["player"]["id"]
        game = self.engine.execute(
            game["id"],
            ConfigureMonsterBloodline(actor_id=actor_id, species_id="serpent"),
        ).game
        return game, actor_id

    def _save(self, game_id: str, state) -> None:
        self.engine.store.save(
            state, [], player_name="青鳞", expected_revision=state.revision
        )

    def _set_major_bottleneck(
        self, game_id: str, actor_id: str, *,
        realm_index: int, evolution_id: str, history: list[str],
    ) -> None:
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, CULTIVATION)
        realm = self.engine.definitions.realms[realm_index]
        cultivation.update(
            realm_id=realm.id,
            layer=realm.layers,
            opportunity=10**18,
            bottleneck="major",
        )
        state.entities.put(actor_id, CULTIVATION, cultivation)
        bloodline = state.entities.require(actor_id, MONSTER_BLOODLINE)
        bloodline.update(
            evolution_id=evolution_id,
            evolution_history=history,
        )
        state.entities.put(actor_id, MONSTER_BLOODLINE, bloodline)
        self._save(game_id, state)

    def test_major_breakthrough_requires_irreversible_evolution_choice(self):
        game, actor_id = self._create_monster()
        self._set_major_bottleneck(
            game["id"], actor_id,
            realm_index=0,
            evolution_id="SERPENT_BASE",
            history=["SERPENT_BASE"],
        )
        shown = self.engine.get_game(game["id"])
        self.assertTrue(shown["monster_system"]["awaiting_evolution"])
        self.assertEqual(
            [row["id"] for row in shown["monster_system"]["candidates"]],
            ["SERPENT_SPIRIT"],
        )
        with self.assertRaisesRegex(ValueError, "血脉进化"):
            self.engine.execute(game["id"], AttemptBreakthrough(actor_id))

        evolved = self.engine.execute(
            game["id"], EvolveMonster(actor_id, "SERPENT_SPIRIT")
        )
        self.assertEqual(evolved.game["player"]["cultivation"]["realm_index"], 1)
        self.assertEqual(
            evolved.game["monster_system"]["current"]["id"], "SERPENT_SPIRIT"
        )
        self.assertEqual(
            [row["id"] for row in evolved.game["monster_system"]["history"]],
            ["SERPENT_BASE", "SERPENT_SPIRIT"],
        )
        self.assertTrue(any(
            event["event_type"] == "dlc.monster.evolution.completed"
            for event in evolved.events
        ))

    def test_locked_branch_is_visible_but_cannot_be_selected(self):
        game, actor_id = self._create_monster()
        self._set_major_bottleneck(
            game["id"], actor_id,
            realm_index=1,
            evolution_id="SERPENT_SPIRIT",
            history=["SERPENT_BASE", "SERPENT_SPIRIT"],
        )
        candidates = {
            row["id"]: row for row in self.engine.get_game(game["id"])[
                "monster_system"
            ]["candidates"]
        }
        self.assertTrue(candidates["SERPENT_MYSTIC"]["enabled"])
        self.assertFalse(candidates["SERPENT_WATER"]["enabled"])
        with self.assertRaisesRegex(ValueError, "尚未满足"):
            self.engine.execute(
                game["id"], EvolveMonster(actor_id, "SERPENT_WATER")
            )

    def test_schema_16_monster_state_migrates_to_resumable_lineage_fields(self):
        game, actor_id = self._create_monster()
        snapshot = self.engine.store.load(game["id"]).to_dict()
        snapshot["schema_version"] = 16
        snapshot["module_versions"].pop("monster", None)
        bloodline = snapshot["entities"]["entities"][actor_id][MONSTER_BLOODLINE]
        for key in (
            "generated_traits", "lineage_deeds", "custom_lineage_id",
            "custom_lineage", "pending_lineage_editor",
        ):
            bloodline.pop(key, None)
        migrated = migrate_snapshot(snapshot)
        migrated_bloodline = migrated["entities"]["entities"][actor_id][MONSTER_BLOODLINE]
        self.assertEqual(migrated["schema_version"], 17)
        self.assertEqual(migrated["module_versions"]["monster"], 1)
        self.assertEqual(migrated_bloodline["lineage_deeds"], {})
        self.assertIsNone(migrated_bloodline["pending_lineage_editor"])

    def test_custom_lineage_is_resumable_and_affects_combat(self):
        game, actor_id = self._create_monster()
        self._set_major_bottleneck(
            game["id"], actor_id,
            realm_index=8,
            evolution_id="SERPENT_MAHAYANA_DRAGON",
            history=["SERPENT_BASE", "SERPENT_MAHAYANA_DRAGON"],
        )
        prepared = self.engine.execute(
            game["id"],
            PrepareCustomLineage(actor_id, "SERPENT_NETHER_SELF_1"),
        ).game
        editor = prepared["monster_system"]["custom_lineage_editor"]
        self.assertEqual(editor["stage"], 1)
        self.assertEqual(editor["deeds"]["total"], 24)

        rule = {
            "phase": "round_start",
            "schedule": "every",
            "condition": "always",
            "target": "player",
            "effect": "might",
            "value": 0.03,
        }
        completed = self.engine.execute(
            game["id"],
            ConfirmCustomLineage(
                actor_id, "SERPENT_NETHER_SELF_1", "万界自在脉", (rule,)
            ),
        ).game
        self.assertEqual(completed["world"]["world_id"], "nether")
        self.assertEqual(completed["player"]["cultivation"]["realm_index"], 9)
        self.assertEqual(
            completed["monster_system"]["custom_lineage"]["name"], "万界自在脉"
        )
        self.assertIsNone(completed["monster_system"]["custom_lineage_editor"])

        before = set(
            self.engine.store.load(game["id"]).entities.with_component("core.identity")
        )
        self.engine.execute(game["id"], RegisterCharacter(
            name="试脉石灵", age=20, gender="male", race="human",
            spirit_root="supreme_earth", path="dao", realm_id="mahayana",
            layer=1, world_id="nether", lifespan=None,
        ))
        after = set(
            self.engine.store.load(game["id"]).entities.with_component("core.identity")
        )
        target_id = (after - before).pop()
        fought = self.engine.execute(
            game["id"], ResolveCombat(actor_id, target_id, terrain="open")
        ).game
        report = fought["combat"]["last_report"]
        self.assertEqual(
            report["attacker"]["monster_contribution"]["evolution_id"],
            "SERPENT_NETHER_SELF_1",
        )
        self.assertTrue(report["rounds"][0]["lineage_events"])


if __name__ == "__main__":
    unittest.main()
