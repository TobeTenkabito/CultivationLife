import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from cultivation_life.v2 import V2GameEngine
from cultivation_life.v2.domain.actions import begin_action, complete_action
from cultivation_life.v2.domain.story import queue_story_event
from cultivation_life.v2.kernel.bus import SimulationContext
from cultivation_life.v2.kernel.model import EventEnvelope, EventScope
from cultivation_life.v2.kernel.services import TimeService


class V2StoryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "v2.sqlite3"
        self.engine = V2GameEngine(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def test_content_is_typed_and_action_opens_persisted_interaction(self):
        self.assertGreaterEqual(len(self.engine.definitions.story_events), 331)
        created = self.engine.create_game("问心", seed=123)
        acted = self.engine.perform_action(created["id"], "rest", 1)
        self.assertIsNotNone(acted.game["pending_event"])
        self.assertEqual(acted.game["action"]["active"], None)
        self.assertTrue(any(
            row["event_type"] == "core.action.completed" for row in acted.events
        ))
        self.assertEqual(acted.events[-1]["event_type"], "story.interaction.opened")

        reloaded = V2GameEngine(self.database).get_game(created["id"])
        self.assertEqual(reloaded["pending_event"], acted.game["pending_event"])
        self.assertFalse(reloaded["capabilities"]["character.rest"]["enabled"])
        self.assertEqual(
            reloaded["capabilities"]["character.rest"]["reason"],
            "请先处理当前事件",
        )

    def test_pending_interaction_blocks_simulation_but_not_ui_settings(self):
        created = self.engine.create_game("止步", seed=9)
        queued = self.engine.queue_story_event(created["id"], "EVT_TRAVEL_HERB_001")
        revision = queued.game["revision"]
        with self.assertRaisesRegex(ValueError, "请先处理当前事件"):
            self.engine.perform_action(created["id"], "rest", 1)
        self.assertEqual(self.engine.get_game(created["id"])["revision"], revision)
        changed = self.engine.update_setting(
            created["id"], "combat_popup", False,
        ).game
        self.assertFalse(changed["settings"]["combat_popup"])
        self.assertIsNotNone(changed["pending_event"])

    def test_choice_effects_history_and_invalid_choice_are_atomic(self):
        created = self.engine.create_game("采药", seed=17)
        queued = self.engine.queue_story_event(created["id"], "EVT_TRAVEL_HERB_001")
        revision = queued.game["revision"]
        with self.assertRaisesRegex(ValueError, "选项不存在"):
            self.engine.choose(created["id"], "missing")
        self.assertEqual(self.engine.get_game(created["id"])["revision"], revision)

        before = queued.game["player"]["cultivation"]["opportunity"]
        resolved = self.engine.choose(created["id"], "wait")
        self.assertIsNone(resolved.game["pending_event"])
        self.assertGreater(
            resolved.game["player"]["cultivation"]["opportunity"], before,
        )
        history = resolved.game["story"]["history"]
        self.assertEqual(history[-1]["event_id"], "EVT_TRAVEL_HERB_001")
        self.assertEqual(history[-1]["choice_id"], "wait")
        self.assertEqual(resolved.events[-1]["event_type"], "story.interaction.resolved")

    def test_followup_chain_is_queued_and_survives_reload(self):
        created = self.engine.create_game(
            "渡魂", seed=21, path="ghost", spirit_root="mutated_yin", start_world="hell",
        )
        self.engine.queue_story_event(created["id"], "EVT_HELL_MEMORY_001")
        followed = self.engine.choose(created["id"], "board").game
        self.assertEqual(followed["pending_event"]["id"], "EVT_HELL_MEMORY_002")
        persisted = V2GameEngine(self.database).get_game(created["id"])
        self.assertEqual(persisted["pending_event"]["id"], "EVT_HELL_MEMORY_002")
        finished = self.engine.choose(created["id"], "burn").game
        self.assertIsNone(finished["pending_event"])
        self.assertEqual(
            [row["event_id"] for row in finished["story"]["history"][-2:]],
            ["EVT_HELL_MEMORY_001", "EVT_HELL_MEMORY_002"],
        )

    def test_interaction_can_pause_and_resume_an_active_timed_action(self):
        @dataclass(frozen=True, slots=True)
        class StartInterruptedAction:
            actor_id: str

        def start(context: SimulationContext, command: object) -> None:
            self.assertIsInstance(command, StartInterruptedAction)
            token = begin_action(
                context,
                actor_id=command.actor_id,
                action="test_journey",
                years=3,
                source="test.journey",
            )
            context.state.scheduler.schedule(
                due_year=1,
                event_type="test.story.pause",
                source="test",
                scope=EventScope.entity(command.actor_id),
                payload={"actor_id": command.actor_id},
            )
            context.state.scheduler.schedule(
                due_year=3,
                event_type="test.action.finish",
                source="test",
                scope=EventScope.entity(command.actor_id),
                payload={"actor_id": command.actor_id, "token": token},
            )
            TimeService.advance(context, 3, source="test.journey")

        def pause(context: SimulationContext, event: EventEnvelope) -> None:
            queue_story_event(
                context,
                self.engine.definitions,
                str(event.payload["actor_id"]),
                "EVT_TRAVEL_HERB_001",
                reason="test_mid_action",
            )

        def finish(context: SimulationContext, event: EventEnvelope) -> None:
            complete_action(
                context,
                actor_id=str(event.payload["actor_id"]),
                token=str(event.payload["token"]),
            )

        self.engine.commands.register(StartInterruptedAction, start)
        self.engine.commands.event_bus.register("test.story.pause", pause)
        self.engine.commands.event_bus.register("test.action.finish", finish)
        created = self.engine.create_game("行路", seed=31)
        actor_id = created["player"]["id"]
        paused = self.engine.execute(
            created["id"], StartInterruptedAction(actor_id),
        ).game
        self.assertEqual(paused["clock"]["year"], 1)
        self.assertEqual(paused["action"]["active"]["target_year"], 3)
        self.assertEqual(paused["pending_event"]["id"], "EVT_TRAVEL_HERB_001")

        resumed = self.engine.choose(created["id"], "leave").game
        self.assertEqual(resumed["clock"]["year"], 3)
        self.assertIsNone(resumed["action"]["active"])
        self.assertEqual(resumed["action"]["last_completed"]["result"], "completed")


if __name__ == "__main__":
    unittest.main()
