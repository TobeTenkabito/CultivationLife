import json
import ast
import re
import tempfile
import unittest
from pathlib import Path

from cultivation_life.v2 import V2GameEngine
from cultivation_life.v2.infrastructure import ConcurrentWriteError, V2ContentLoader
from cultivation_life.v2.domain.character import BootstrapGame, register_character_domain
from cultivation_life.v2.kernel.bus import CommandBus, SimulationContext
from cultivation_life.v2.kernel.model import EntityStore, EventScope, WorldState
from cultivation_life.v2.kernel.services import TimeService


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V1BehaviorFreezeTests(unittest.TestCase):
    def test_v1_public_operation_inventory_is_frozen(self):
        inventory = json.loads(
            (SOURCE_ROOT / "docs" / "v2" / "v1_behavior_inventory.json").read_text(encoding="utf-8")
        )
        server_source = (SOURCE_ROOT / "cultivation_life" / "server.py").read_text(encoding="utf-8")
        implemented = sorted(set(re.findall(r'operation == "([^"]+)"', server_source)))
        self.assertEqual(implemented, inventory["public_operations"])

    def test_v2_does_not_import_legacy_runtime_or_models(self):
        forbidden = {
            "cultivation_life.engine",
            "cultivation_life.models",
            "cultivation_life.storage",
        }
        violations = []
        for path in (SOURCE_ROOT / "cultivation_life" / "v2").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    modules = {node.module or ""}
                else:
                    continue
                if modules & forbidden:
                    violations.append(f"{path.name}:{node.lineno}")
        self.assertEqual(violations, [])


class V2FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "v2" / "saves.sqlite3"
        self.engine = V2GameEngine(self.database)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _resolve_pending(engine: V2GameEngine, game_id: str) -> dict:
        game = engine.get_game(game_id)
        while game["pending_event"] is not None:
            choice = next(row for row in game["pending_event"]["choices"] if row["enabled"])
            game = engine.choose(game_id, choice["id"]).game
        return game

    def test_create_action_event_save_and_reload_vertical_slice(self):
        created = self.engine.create_game(
            "问心", seed=20260916, path="demonic", spirit_root="supreme_fire"
        )
        self.assertEqual(created["format"], "cultivation-life-v2")
        self.assertEqual(created["revision"], 1)
        self.assertEqual(created["clock"]["year"], 0)
        self.assertEqual(created["player"]["age"], 16)

        execution = self.engine.perform_timed_action(created["id"], "cultivate", 3)
        self.assertEqual(execution.game["revision"], 2)
        self.assertEqual(execution.game["clock"]["year"], 3)
        self.assertEqual(execution.game["player"]["age"], 19)
        self.assertEqual(execution.game["player"]["activity"]["actions_completed"], 1)
        self.assertGreater(execution.game["player"]["cultivation"]["opportunity"], 0)
        event_types = [event["event_type"] for event in execution.events]
        self.assertEqual(event_types.count("core.time.advanced"), 3)
        self.assertEqual(event_types.count("cultivation.action.tick"), 3)
        self.assertIn("core.action.completed", event_types)
        self.assertEqual(event_types[-1], "story.interaction.opened")
        self.assertIsNotNone(execution.game["pending_event"])

        reloaded_engine = V2GameEngine(self.database)
        self.assertEqual(reloaded_engine.get_game(created["id"]), execution.game)
        journal_types = [event["event_type"] for event in reloaded_engine.event_journal(created["id"])]
        self.assertEqual(journal_types[0], "character.created")
        self.assertIn("core.game.created", journal_types)
        self.assertEqual(journal_types[-1], "story.interaction.opened")

    def test_failed_command_does_not_change_snapshot_or_journal(self):
        created = self.engine.create_game("守界", seed=1)
        before = self.engine.get_game(created["id"])
        before_events = self.engine.event_journal(created["id"])
        with self.assertRaisesRegex(ValueError, "未知"):
            self.engine.perform_timed_action(created["id"], "ascend_without_domain", 1)
        self.assertEqual(self.engine.get_game(created["id"]), before)
        self.assertEqual(self.engine.event_journal(created["id"]), before_events)

    def test_rng_is_deterministic_across_reload_boundaries(self):
        other_database = Path(self.temp.name) / "other" / "saves.sqlite3"
        other = V2GameEngine(other_database)
        left = self.engine.create_game("甲", seed=99, path="demonic", spirit_root="supreme_fire")
        right = other.create_game("乙", seed=99, path="demonic", spirit_root="supreme_fire")

        self.engine.perform_timed_action(left["id"], "cultivate", 2)
        self._resolve_pending(self.engine, left["id"])
        reloaded = V2GameEngine(self.database)
        left_result = reloaded.perform_timed_action(left["id"], "cultivate", 3).game

        other.perform_timed_action(right["id"], "cultivate", 2)
        self._resolve_pending(other, right["id"])
        right_result = other.perform_timed_action(right["id"], "cultivate", 3).game
        self.assertEqual(
            left_result["player"]["cultivation"]["opportunity"],
            right_result["player"]["cultivation"]["opportunity"],
        )

    def test_stale_snapshot_cannot_overwrite_newer_revision(self):
        created = self.engine.create_game("并发", seed=7)
        first = self.engine.store.load(created["id"])
        stale = self.engine.store.load(created["id"])
        player_name = created["player"]["name"]
        self.engine.store.save(first, [], player_name=player_name, expected_revision=1)
        with self.assertRaises(ConcurrentWriteError):
            self.engine.store.save(stale, [], player_name=player_name, expected_revision=1)
        self.assertEqual(self.engine.get_game(created["id"])["revision"], 2)

    def test_event_journal_can_be_read_incrementally(self):
        created = self.engine.create_game("观史", seed=5)
        initial_last = self.engine.event_journal(created["id"])[-1]["sequence"]
        self.engine.perform_timed_action(created["id"], "rest", 1)
        tail = self.engine.event_journal(created["id"], after_sequence=initial_last)
        self.assertEqual(
            [event["sequence"] for event in tail],
            list(range(initial_last + 1, initial_last + 1 + len(tail))),
        )
        self.assertEqual(tail[-1]["event_type"], "story.interaction.opened")
        self.assertTrue(any(
            event["event_type"] == "cultivation.action.completed"
            and event["payload"]["action"] == "rest"
            for event in tail
        ))

    def test_scheduler_processes_events_in_chronological_order(self):
        bus = CommandBus()
        definitions = V2ContentLoader.load(SOURCE_ROOT / "content")
        register_character_domain(bus, definitions)
        state = WorldState.new(seed=10, created_at="2026-09-16T00:00:00+00:00")
        bus.execute(state, BootstrapGame(name="守时"))
        state.scheduler.schedule(
            due_year=2,
            event_type="test.later",
            source="test",
            scope=EventScope.global_scope(),
        )
        state.scheduler.schedule(
            due_year=1,
            event_type="test.sooner",
            source="test",
            scope=EventScope.global_scope(),
        )
        context = SimulationContext(state=state, event_bus=bus.event_bus)
        TimeService.advance(context, 2, source="test")
        self.assertEqual(
            [(event.event_type, event.occurred_at) for event in context.emitted_events],
            [
                ("core.time.advanced", 1),
                ("test.sooner", 1),
                ("core.time.advanced", 2),
                ("test.later", 2),
            ],
        )

    def test_entity_store_never_leaks_mutable_component_aliases(self):
        store = EntityStore()
        entity_id = store.create("npc")
        original = {"name": "照月", "traits": ["calm"]}
        store.put(entity_id, "core.identity", original)
        original["traits"].append("mutated-outside")
        loaded = store.require(entity_id, "core.identity")
        loaded["traits"].append("mutated-after-read")
        self.assertEqual(store.require(entity_id, "core.identity")["traits"], ["calm"])


if __name__ == "__main__":
    unittest.main()
