from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import (
    GhostAttachmentAction,
    GhostConstraintAction,
    GhostSoulAction,
    GrantItem,
    LeavePossessedBody,
    PostBattlePossession,
    PrepareGhostReincarnation,
    RegisterCharacter,
    ResolveCombat,
    GameEngine,
)
from cultivation_life.domain.character import LIFE
from cultivation_life.domain.cultivation import CULTIVATION, GrantTechnique
from cultivation_life.domain.demonic import DEMONIC_STATE
from cultivation_life.domain.extensions import GHOST_SOUL
from cultivation_life.domain.ghost import (
    BOUND_SOUL,
    GHOST_ECOLOGY,
    SOUL_CONTROL,
)
from cultivation_life.domain.world import LOCATION
from cultivation_life.v1_facade import game_view


class V2GhostBatchEightTests(unittest.TestCase):
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
        path: str = "dao",
        world_id: str = "hell",
    ) -> str:
        before = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        self.engine.execute(game_id, RegisterCharacter(
            name=name,
            age=25,
            gender="male",
            race="human",
            spirit_root="supreme_water" if path != "ghost" else "none",
            path=path,
            realm_id=realm_id,
            layer=layer,
            world_id=world_id,
        ))
        after = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        return (after - before).pop()

    def _save(self, game_id: str, state) -> None:
        self.engine.store.save(
            state, [], player_name="测试", expected_revision=state.revision
        )

    def _resolve_pending(self, game_id: str) -> None:
        game = self.engine.get_game(game_id)
        while game["pending_event"] is not None:
            choice = next(
                row for row in game["pending_event"]["choices"] if row["enabled"]
            )
            game = self.engine.choose(game_id, choice["id"]).game

    def test_possession_limit_uses_learned_ghost_techniques(self):
        game = self.engine.create_game(
            "夺舍上限", seed=805, path="ghost",
            spirit_root="mutated_yin", start_world="hell",
        )
        actor_id = game["player"]["id"]
        self.assertEqual(game["ghost_system"]["possession_limit"], 1)
        limited = self.engine.execute(
            game["id"], GrantTechnique(actor_id, "TECH_GHOST_BODY_THIEF")
        ).game
        self.assertEqual(limited["ghost_system"]["possession_limit"], 2)
        unlimited = self.engine.execute(
            game["id"], GrantTechnique(
                actor_id, "TECH_GHOST_TEN_THOUSAND_HOSTS"
            )
        ).game
        self.assertIsNone(unlimited["ghost_system"]["possession_limit"])

    def test_reincarnation_prompt_resets_progress_but_preserves_soul_damage(self):
        game = self.engine.create_game(
            "轮回客", seed=801, path="ghost", start_world="hell"
        )
        actor_id = game["player"]["id"]
        state = self.engine.store.load(game["id"])
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation.update(
            realm_id="qi",
            layer=self.engine.definitions.realm("qi").layers,
            opportunity=999_999.0,
            bottleneck="major",
        )
        state.entities.put(actor_id, CULTIVATION, cultivation)
        soul = state.entities.require(actor_id, GHOST_SOUL)
        soul.update(
            intrinsic_hp=62.0,
            intrinsic_mp=57.0,
            intrinsic_hp_reference=100.0,
            intrinsic_mp_reference=100.0,
            erosion_rate_pp=0.125,
            wangsheng=7,
        )
        state.entities.put(actor_id, GHOST_SOUL, soul)
        self._save(game["id"], state)

        prompted = self.engine.execute(
            game["id"], PrepareGhostReincarnation(actor_id)
        ).game
        self.assertEqual(prompted["pending_event"]["id"], "SYS_GHOST_REINCARNATION")
        completed = self.engine.choose(game["id"], "continue").game
        self.assertEqual(completed["player"]["cultivation"]["realm_id"], "qi")
        self.assertEqual(completed["player"]["cultivation"]["layer"], 1)
        self.assertEqual(completed["player"]["divine_sense"]["rank"], 1)
        soul_view = completed["ghost_system"]["soul"]
        self.assertEqual(soul_view["intrinsic_hp"], 62.0)
        self.assertEqual(soul_view["intrinsic_mp"], 57.0)
        self.assertEqual(soul_view["erosion_rate_pp"], 0.125)
        self.assertEqual(soul_view["wangsheng"], 0)
        self.assertEqual(soul_view["reincarnation_imprints"], {"qi": 1})
        self.assertEqual(completed["ghost_system"]["breakthrough_bonus"], 0.05)

    def test_parade_is_scheduled_spawned_and_exposed_as_canonical_souls(self):
        game = self.engine.create_game(
            "巡夜人", seed=802, path="ghost", start_world="hell"
        )
        actor_id = game["player"]["id"]
        self.engine.perform_timed_action(game["id"], "rest", 1)
        self._resolve_pending(game["id"])
        state = self.engine.store.load(game["id"])
        ecology = state.entities.require(actor_id, GHOST_ECOLOGY)
        parade = dict(ecology["parade"])
        location = state.entities.require(actor_id, LOCATION)
        parade.update(
            start_year=state.clock.year + 1,
            end_year=state.clock.year + 3,
            location_id=location["location_id"],
            world_id=location["world_id"],
        )
        ecology["parade"] = parade
        state.entities.put(actor_id, GHOST_ECOLOGY, ecology)
        self._save(game["id"], state)

        active = self.engine.perform_timed_action(game["id"], "rest", 1).game
        parade_view = active["ghost_system"]["parade"]
        self.assertEqual(parade_view["status"], "active")
        self.assertEqual(len(parade_view["souls"]), 6)
        self.assertTrue(all(
            row["realm_name"] and row["realm_index"] >= 0
            and row["soul_trait"]["name"]
            for row in parade_view["souls"]
        ))
        soul_id = parade_view["souls"][0]["id"]
        persisted = self.engine.store.load(game["id"])
        self.assertIsNotNone(persisted.entities.get(soul_id, BOUND_SOUL))
        self.assertTrue(persisted.entities.exists(soul_id))

    def test_bound_soul_slots_modify_real_combat_and_release_cleanly(self):
        game = self.engine.create_game(
            "御魂人", seed=803, path="ghost", start_world="hell"
        )
        actor_id = game["player"]["id"]
        soul_id = self._register(
            game["id"], "伏矢战魂", realm_id="nascent", layer=5, path="ghost"
        )
        state = self.engine.store.load(game["id"])
        state.entities.put(soul_id, BOUND_SOUL, {
            "name": "伏矢战魂",
            "origin": "test",
            "status": "bound",
            "combat_power": 20_000.0,
            "soul_pressure": 1.5,
            "affinity": 0,
            "defeated": True,
            "befriended": False,
            "trait": {"name": "凶魂", "description": ""},
        })
        state.relations.add(
            source_id=actor_id,
            target_id=soul_id,
            kind=SOUL_CONTROL,
            created_year=state.clock.year,
            metadata={"status": "bound"},
        )
        self._save(game["id"], state)

        before = self.engine.get_game(game["id"])["combat"]["snapshot"]["stats"]["might"]
        equipped = self.engine.execute(
            game["id"], GhostSoulAction(actor_id, soul_id, "equip", "伏矢")
        ).game
        after = equipped["combat"]["snapshot"]["stats"]["might"]
        self.assertGreater(after, before)
        self.assertGreater(equipped["ghost_system"]["pressure"], 0)
        released = self.engine.execute(
            game["id"], GhostSoulAction(actor_id, soul_id, "release")
        ).game
        self.assertEqual(released["ghost_system"]["bound_souls"], [])
        self.assertIsNone(next(
            row["soul_id"] for row in released["ghost_system"]["slots"]
            if row["id"] == "伏矢"
        ))

    def test_attachment_constraint_and_leave_possession_are_real_states(self):
        game = self.engine.create_game(
            "寄魂", seed=804, path="ghost", start_world="hell"
        )
        actor_id = game["player"]["id"]
        self.engine.execute(game["id"], GrantItem(actor_id, "spirit_sword", 1))
        attachable = self.engine.get_game(game["id"])["ghost_system"]
        self.assertEqual(attachable["state_name"], "自由魂体")
        self.assertFalse(attachable["souls_suspended"])
        self.assertIn("spirit_sword", {
            row["id"] for row in attachable["attachable_items"]
        })
        attached = self.engine.execute(
            game["id"], GhostAttachmentAction(actor_id, "attach", "spirit_sword")
        ).game
        self.assertEqual(attached["ghost_system"]["state"], "attached")
        self.assertEqual(
            attached["ghost_system"]["attachment"]["spirit_name"],
            "青锋灵剑器灵·寄魂",
        )
        detached = self.engine.execute(
            game["id"], GhostAttachmentAction(actor_id, "leave")
        ).game
        self.assertEqual(detached["ghost_system"]["state"], "free")

        target_id = self._register(game["id"], "备用肉身")
        self.engine.execute(game["id"], ResolveCombat(actor_id, target_id, "capture"))
        state = self.engine.store.load(game["id"])
        life = state.entities.require(actor_id, LIFE)
        life.update(alive=False, death_reason="测试战陨")
        state.entities.put(actor_id, LIFE, life)
        demonic = state.entities.require(actor_id, DEMONIC_STATE)
        demonic["pending_post_battle_possession"] = {
            "candidate_ids": [target_id], "year": state.clock.year
        }
        state.entities.put(actor_id, DEMONIC_STATE, demonic)
        self._save(game["id"], state)
        legacy = game_view(self.engine.get_game(game["id"]), {})
        self.assertEqual(
            legacy["pending_event"]["id"],
            "SYS_POST_BATTLE_POSSESSION",
        )
        self.assertEqual(
            legacy["pending_event"]["choices"][0]["id"], target_id
        )
        possessed = self.engine.execute(
            game["id"], PostBattlePossession(actor_id, target_id)
        ).game
        self.assertEqual(possessed["ghost_system"]["state"], "possessed")
        legacy_possessed = game_view(possessed, {})
        self.assertEqual(
            legacy_possessed["ghost_system"]["phase_two"]["state"],
            "possessed",
        )
        self.assertEqual(
            legacy_possessed["ghost_system"]["phase_two"]["host"]["name"],
            "备用肉身",
        )
        left = self.engine.execute(
            game["id"], LeavePossessedBody(actor_id)
        ).game
        self.assertEqual(left["ghost_system"]["state"], "free")
        self.assertEqual(left["player"]["cultivation"]["path"], "ghost")
        self.assertEqual(left["ghost_system"]["possession_count"], 1)

        captor_id = self._register(game["id"], "拘魂者")
        state = self.engine.store.load(game["id"])
        ecology = state.entities.require(actor_id, GHOST_ECOLOGY)
        ecology["captor"] = {
            "entity_id": captor_id,
            "name": "拘魂者",
            "combat_power": 100.0,
            "followed_years": 0,
        }
        state.entities.put(actor_id, GHOST_ECOLOGY, ecology)
        self._save(game["id"], state)
        with self.assertRaisesRegex(ValueError, "魂印受制"):
            self.engine.perform_action(game["id"], "cultivate", 1)
        waited = self.engine.execute(
            game["id"], GhostConstraintAction(actor_id, "wait")
        ).game
        self.assertEqual(waited["clock"]["year"], 1)
        self.assertEqual(waited["ghost_system"]["captor"]["followed_years"], 1)


if __name__ == "__main__":
    unittest.main()
