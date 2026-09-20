import tempfile
import unittest
import re
from dataclasses import dataclass
from pathlib import Path

from cultivation_life import GameEngine, GrantItem, RegisterCharacter
from cultivation_life.domain.actions import begin_action, complete_action
from cultivation_life.domain.cultivation import GrantTechnique
from cultivation_life.domain.relations import (
    _queue_personal_relationship_event,
    relationship_affinity,
    set_relationship_affinity,
)
from cultivation_life.domain.story import queue_story_event
from cultivation_life.domain.war import WANTED_STATE, _maybe_queue_wanted_encounter
from cultivation_life.kernel.bus import SimulationContext
from cultivation_life.kernel.model import EventEnvelope, EventScope
from cultivation_life.kernel.services import TimeService


class V2StoryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "v2.sqlite3"
        self.engine = GameEngine(self.database)

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

        reloaded = GameEngine(self.database).get_game(created["id"])
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

    def test_legacy_event_text_and_technique_level_are_projected_and_consumed(self):
        created = self.engine.create_game("悟法", seed=18)
        actor_id = created["player"]["id"]
        learned = self.engine.execute(
            created["id"],
            GrantTechnique(actor_id, "TECH_BASIC_QI", equip_main=True),
        ).game
        before = learned["player"]["cultivation"]["cultivation_efficiency"]
        self.engine.queue_story_event(created["id"], "EVT_CULTIVATE_INSIGHT_001")
        resolved = self.engine.choose(created["id"], "record").game
        technique = resolved["player"]["cultivation"]["main_technique"]
        self.assertEqual(technique["level"], 2)
        self.assertGreater(
            resolved["player"]["cultivation"]["cultivation_efficiency"], before
        )
        self.assertNotIn("undefined", resolved["story"]["history"][-1]["summary"])

        self.engine.queue_story_event(created["id"], "EVT_TRAVEL_HERB_001")
        picked = self.engine.choose(created["id"], "pick").game
        summary = picked["story"]["history"][-1]["summary"]
        self.assertIn("点伤害", summary)
        self.assertNotIn("hp_ratio", summary)
        self.assertIn("获得回春丹", summary)

    def test_acquired_affinity_unlocks_legacy_event_conditions_and_techniques(self):
        created = self.engine.create_game("补根", seed=19, spirit_root="none")
        actor_id = created["player"]["id"]
        self.engine.execute(created["id"], GrantItem(actor_id, "jinque_fire", 1))
        self.engine.queue_story_event(created["id"], "EVT_MORTAL_ROOT_COMPLETE_001")
        repaired = self.engine.choose(created["id"], "fire").game
        self.assertEqual(
            repaired["player"]["cultivation"]["spirit_root"], "acquired_fire"
        )
        self.assertEqual(
            repaired["player"]["cultivation"]["spirit_root_name"], "后天补灵根（火）"
        )
        learned = self.engine.execute(
            created["id"],
            GrantTechnique(actor_id, "TECH_FIRE_SCRIPTURE", equip_main=True),
        ).game
        self.assertEqual(
            learned["player"]["cultivation"]["main_technique"]["id"],
            "TECH_FIRE_SCRIPTURE",
        )

    def test_story_reward_can_teach_an_incompatible_manual_without_equipping_it(self):
        created = self.engine.create_game(
            "异法入册", seed=191, spirit_root="supreme_wood", path="dao"
        )
        self.engine.queue_story_event(
            created["id"], "EVT_DEMON_BLOOD_RIVER_004"
        )

        resolved = self.engine.choose(created["id"], "renew").game

        known = {
            row["id"]
            for row in resolved["player"]["cultivation"]["known_techniques"]
        }
        self.assertIn("TECH_BLOOD_RIVER_REVERSION", known)
        main = resolved["player"]["cultivation"]["main_technique"]
        self.assertTrue(
            main is None or main["id"] != "TECH_BLOOD_RIVER_REVERSION"
        )

    def test_followup_chain_is_queued_and_survives_reload(self):
        created = self.engine.create_game(
            "渡魂", seed=21, path="ghost", spirit_root="mutated_yin", start_world="hell",
        )
        self.engine.queue_story_event(created["id"], "EVT_HELL_MEMORY_001")
        followed = self.engine.choose(created["id"], "board").game
        self.assertEqual(followed["pending_event"]["id"], "EVT_HELL_MEMORY_002")
        persisted = GameEngine(self.database).get_game(created["id"])
        self.assertEqual(persisted["pending_event"]["id"], "EVT_HELL_MEMORY_002")
        finished = self.engine.choose(created["id"], "burn").game
        self.assertIsNone(finished["pending_event"])
        self.assertEqual(
            [row["event_id"] for row in finished["story"]["history"][-2:]],
            ["EVT_HELL_MEMORY_001", "EVT_HELL_MEMORY_002"],
        )

    def test_spirit_crossing_runs_three_stage_chain_and_clears_prison(self):
        created = self.engine.create_game("破界", seed=243)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="spirit", layer=1, bottleneck=None)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        inventory = state.entities.require(actor_id, "economy.inventory")
        inventory["items"] = {
            **dict(inventory.get("items", {})),
            "spirit_node_info": 1,
            "broken_god": 1,
        }
        state.entities.put(actor_id, "economy.inventory", inventory)
        captor_id = next(
            entity_id for entity_id in state.entities.with_component("core.identity")
            if entity_id != actor_id
        )
        state.relations.add(
            source_id=captor_id, target_id=actor_id,
            kind="combat_prisoner", created_year=state.clock.year,
        )
        self.engine.store.save(
            state, [], player_name="破界", expected_revision=state.revision
        )

        started = self.engine.begin_spirit_crossing(game_id).game
        self.assertEqual(started["world"]["world_id"], "human")
        self.assertEqual(started["pending_event"]["id"], "EVT_SPIRIT_CROSSING_001")
        self.assertTrue(started["story"]["spirit_crossing"]["attempted"])
        self.assertTrue(started["story"]["spirit_crossing"]["active"])
        with self.assertRaisesRegex(ValueError, "机会只有一次|请先处理当前事件"):
            self.engine.begin_spirit_crossing(game_id)

        located = self.engine.choose(game_id, "locate").game
        self.assertEqual(located["pending_event"]["id"], "EVT_SPIRIT_CROSSING_002")
        self.assertFalse(any(
            row["id"] == "spirit_node_info" for row in located["inventory"]
        ))
        reloaded = GameEngine(self.database).get_game(game_id)
        self.assertEqual(reloaded["pending_event"]["id"], "EVT_SPIRIT_CROSSING_002")

        endured = self.engine.choose(game_id, "endure").game
        self.assertEqual(endured["pending_event"]["id"], "EVT_SPIRIT_CROSSING_003")
        self.assertLess(endured["combat"]["snapshot"]["hp_ratio"], 0.5)
        crossed = self.engine.choose(game_id, "break_boundary").game
        self.assertEqual(crossed["world"]["world_id"], "spirit")
        self.assertFalse(crossed["story"]["spirit_crossing"]["active"])
        self.assertEqual(
            crossed["story"]["history"][-1]["result"],
            "entered_spirit_realm",
        )
        persisted = self.engine.store.load(game_id)
        self.assertFalse(persisted.relations.find(
            target_id=actor_id, kind="combat_prisoner"
        ))

    def test_failed_story_attribute_check_is_lethal_and_stops_crossing(self):
        created = self.engine.create_game("迷航", seed=244)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="spirit", layer=1, bottleneck=None)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="迷航", expected_revision=state.revision
        )
        self.engine.begin_spirit_crossing(game_id)
        failed = self.engine.choose(game_id, "locate").game
        self.assertFalse(failed["player"]["alive"])
        self.assertIn("没有空间节点信息", failed["player"]["death_reason"])
        self.assertEqual(failed["story"]["history"][-1]["result"], "dead")
        self.assertFalse(failed["story"]["spirit_crossing"]["active"])

    def test_monster_v1_crossing_button_reaches_monster_realm(self):
        created = self.engine.create_game(
            "妖渡", seed=246, path="monster", race="monster", start_world="human",
        )
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="spirit", layer=1, bottleneck=None)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        inventory = state.entities.require(actor_id, "economy.inventory")
        inventory["items"] = {
            **dict(inventory.get("items", {})),
            "spirit_node_info": 1,
            "broken_god": 1,
        }
        state.entities.put(actor_id, "economy.inventory", inventory)
        self.engine.store.save(
            state, [], player_name="妖渡", expected_revision=state.revision
        )

        started = self.engine.begin_spirit_crossing(game_id).game
        self.assertEqual(started["pending_event"]["title"], "偷渡妖界")
        self.assertEqual(
            started["story"]["spirit_crossing"]["destination"], "monster_realm"
        )
        self.engine.choose(game_id, "locate")
        self.engine.choose(game_id, "endure")
        crossed = self.engine.choose(game_id, "break_boundary").game
        self.assertEqual(crossed["world"]["world_id"], "monster_realm")
        self.assertIn("妖界", crossed["story"]["history"][-1]["summary"])

    def test_immortal_power_conversion_runs_v1_five_stage_loop(self):
        created = self.engine.create_game("仙元", seed=247)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        self.engine.execute(
            game_id, GrantTechnique(actor_id, "TECH_CELESTIAL_BREATHING")
        )
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(
            realm_id="true_immortal", layer=1,
            immortal_conversion_stage=0,
            immortal_conversion_last_year=state.clock.year - 5_000,
            immortal_conversion_checked_units=0,
            immortal_power_converted=False,
        )
        state.entities.put(actor_id, "cultivation.state", cultivation)
        life = state.entities.require(actor_id, "character.life")
        life["lifespan"] = None
        state.entities.put(actor_id, "character.life", life)
        location = state.entities.require(actor_id, "world.location")
        location.update(
            world_id="celestial",
            location_id=self.engine.definitions.default_location("celestial"),
        )
        state.entities.put(actor_id, "world.location", location)
        self.engine.store.save(
            state, [], player_name="仙元", expected_revision=state.revision
        )
        with self.assertRaisesRegex(ValueError, "仙灵力转化"):
            self.engine.equip_known_technique(
                game_id, "TECH_CELESTIAL_BREATHING", "main"
            )

        conversion = self.engine.definitions.systems["immortal_power_conversion"]
        old_base = conversion["base_chance"]
        conversion["base_chance"] = 1.0
        try:
            choices = ("sense", "wash", "condense", "rebuild", "ignite")
            for stage, choice in enumerate(choices, 1):
                if stage > 1:
                    state = self.engine.store.load(game_id)
                    cultivation = state.entities.require(
                        actor_id, "cultivation.state"
                    )
                    cultivation["immortal_conversion_last_year"] = (
                        state.clock.year - 5_000
                    )
                    cultivation["immortal_conversion_checked_units"] = 0
                    state.entities.put(
                        actor_id, "cultivation.state", cultivation
                    )
                    self.engine.store.save(
                        state, [], player_name="仙元",
                        expected_revision=state.revision,
                    )
                pending = self.engine.perform_action(
                    game_id, "cultivate", 1
                ).game["pending_event"]
                self.assertEqual(
                    pending["id"], f"EVT_IMMORTAL_CONVERSION_{stage:03d}"
                )
                resolved = self.engine.choose(game_id, choice).game
                self.assertEqual(
                    resolved["player"]["cultivation"]["immortal_power"][
                        "conversion_stage"
                    ],
                    stage,
                )
                if stage < 5 and resolved.get("pending_event") is not None:
                    state = self.engine.store.load(game_id)
                    story = state.entities.require(actor_id, "story.state")
                    story["pending"] = None
                    story["queue"] = []
                    state.entities.put(actor_id, "story.state", story)
                    self.engine.store.save(
                        state, [], player_name="仙元",
                        expected_revision=state.revision,
                    )
        finally:
            conversion["base_chance"] = old_base

        self.assertTrue(
            resolved["player"]["cultivation"]["immortal_power"]["converted"]
        )
        self.assertIn(
            "TECH_CELESTIAL_BREATHING",
            {
                row["id"]
                for row in resolved["player"]["cultivation"]["known_techniques"]
            },
        )
        self.assertEqual(
            next(
                row["quantity"] for row in resolved["inventory"]
                if row["id"] == "immortal_origin_stone"
            ),
            3,
        )
        if resolved.get("pending_event") is not None:
            state = self.engine.store.load(game_id)
            story = state.entities.require(actor_id, "story.state")
            story["pending"] = None
            story["queue"] = []
            state.entities.put(actor_id, "story.state", story)
            self.engine.store.save(
                state, [], player_name="仙元", expected_revision=state.revision
            )
        self.engine.equip_known_technique(
            game_id, "TECH_CELESTIAL_BREATHING", "main"
        )

    def test_wanted_hostility_queues_real_pursuer_and_surrender_enters_prison(self):
        @dataclass(frozen=True, slots=True)
        class TriggerWanted:
            actor_id: str

        def trigger(context: SimulationContext, command: object) -> None:
            self.assertIsInstance(command, TriggerWanted)
            for _ in range(50):
                _maybe_queue_wanted_encounter(
                    context, self.engine.definitions, command.actor_id
                )
                story = context.state.entities.require(
                    command.actor_id, "story.state"
                )
                if story.get("pending") is not None:
                    return
            self.fail("高敌意没有触发追杀事件")

        self.engine.commands.register(TriggerWanted, trigger)
        created = self.engine.create_game("缉令", seed=245)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        wanted = state.entities.require(actor_id, WANTED_STATE)
        wanted["hostility"] = {"world:human": 150.0}
        state.entities.put(actor_id, WANTED_STATE, wanted)
        self.engine.store.save(
            state, [], player_name="缉令", expected_revision=state.revision
        )

        pursued = self.engine.execute(game_id, TriggerWanted(actor_id)).game
        self.assertEqual(pursued["pending_event"]["id"], "EVT_WANTED_ENCOUNTER_001")
        target_id = pursued["pending_event"]["runtime"]["target_id"]
        self.assertTrue(self.engine.store.load(game_id).entities.exists(target_id))
        self.assertEqual(pursued["war_system"]["wanted_by"][0]["hostility"], 150.0)
        self.assertEqual(pursued["war_system"]["bounties"], [])
        self.assertEqual(
            pursued["story"]["milestones"]["became_wanted_target"], 1
        )

        surrendered = self.engine.choose(game_id, "surrender").game
        self.assertEqual(
            surrendered["story"]["history"][-1]["result"], "surrendered"
        )
        self.assertIsNotNone(surrendered["demonic_system"]["imprisonment"])
        self.assertEqual(
            surrendered["demonic_system"]["imprisonment"]["captor_id"],
            target_id,
        )

    def test_overpowered_wanted_faction_negotiates_and_can_give_hostage(self):
        @dataclass(frozen=True, slots=True)
        class TriggerWanted:
            actor_id: str

        def trigger(context: SimulationContext, command: object) -> None:
            self.assertIsInstance(command, TriggerWanted)
            _maybe_queue_wanted_encounter(
                context, self.engine.definitions, command.actor_id
            )

        self.engine.commands.register(TriggerWanted, trigger)
        created = self.engine.create_game("压服", seed=250)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        faction_id = next(
            entity_id for entity_id in state.entities.with_component("faction.profile")
            if state.entities.require(entity_id, "faction.profile")["world_id"] == "human"
        )
        before_ids = set(state.entities.with_component("core.identity"))
        self.engine.execute(game_id, RegisterCharacter(
            "求和长老", 50, "male", "human", "none", "dao",
            "mortal", 1, "human", 100,
        ))
        state = self.engine.store.load(game_id)
        hostage_id = (set(state.entities.with_component("core.identity")) - before_ids).pop()
        state.relations.add(
            source_id=hostage_id, target_id=faction_id,
            kind="faction_membership", created_year=state.clock.year,
            metadata={"role": "leader", "contribution": 0},
        )
        wanted = state.entities.require(actor_id, WANTED_STATE)
        wanted["hostility"] = {f"sect:{faction_id}": 150.0}
        state.entities.put(actor_id, WANTED_STATE, wanted)
        self.engine.store.save(
            state, [], player_name="压服", expected_revision=state.revision
        )

        negotiation = self.engine.execute(
            game_id, TriggerWanted(actor_id)
        ).game["pending_event"]
        self.assertEqual(negotiation["id"], "EVT_WANTED_NEGOTIATION_001")
        self.assertTrue(next(
            row for row in negotiation["choices"] if row["id"] == "dissolve"
        )["enabled"])
        self.assertFalse(next(
            row for row in negotiation["choices"] if row["id"] == "sect_vassal"
        )["enabled"])
        resolved = self.engine.choose(game_id, "hostages").game
        self.assertEqual(resolved["story"]["history"][-1]["result"], "hostages")
        persisted = self.engine.store.load(game_id)
        self.assertTrue(persisted.relations.find(
            source_id=actor_id, target_id=hostage_id, kind="combat_prisoner"
        ))
        self.assertEqual(
            persisted.entities.require(actor_id, WANTED_STATE)["hostility"][
                f"sect:{faction_id}"
            ],
            0,
        )

    def test_personal_affinity_event_triggers_and_grants_real_opportunity(self):
        @dataclass(frozen=True, slots=True)
        class TriggerRelationshipEvent:
            actor_id: str

        def trigger(context: SimulationContext, command: object) -> None:
            self.assertIsInstance(command, TriggerRelationshipEvent)
            for _ in range(100):
                _queue_personal_relationship_event(
                    context, self.engine.definitions, command.actor_id
                )
                story = context.state.entities.require(
                    command.actor_id, "story.state"
                )
                if story.get("pending") is not None:
                    return
            self.fail("高好感人物没有触发故人来访")

        self.engine.commands.register(TriggerRelationshipEvent, trigger)
        created = self.engine.create_game("故交", seed=248)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        before_ids = set(self.engine.store.load(game_id).entities.with_component(
            "core.identity"
        ))
        self.engine.execute(game_id, RegisterCharacter(
            "论道故人", 30, "female", "human", "supreme_water", "dao",
            "foundation", 1, "human", 500,
        ))
        state = self.engine.store.load(game_id)
        visitor_id = (set(state.entities.with_component("core.identity")) - before_ids).pop()
        set_relationship_affinity(state, visitor_id, actor_id, 100)
        before_opportunity = float(state.entities.require(
            actor_id, "cultivation.state"
        )["opportunity"])
        self.engine.store.save(
            state, [], player_name="故交", expected_revision=state.revision
        )

        pending = self.engine.execute(
            game_id, TriggerRelationshipEvent(actor_id)
        ).game["pending_event"]
        self.assertEqual(pending["id"], "EVT_PERSONAL_AFFINITY_GIFT_001")
        self.assertEqual(pending["runtime"]["target_id"], visitor_id)
        resolved = self.engine.choose(game_id, "discuss").game
        self.assertGreater(
            resolved["player"]["cultivation"]["opportunity"], before_opportunity
        )
        persisted = self.engine.store.load(game_id)
        self.assertEqual(
            relationship_affinity(persisted, visitor_id, actor_id),
            102,
        )
        self.assertEqual(resolved["story"]["history"][-1]["result"], "discussed")

    def test_personal_revenge_event_resolves_through_real_combat(self):
        @dataclass(frozen=True, slots=True)
        class TriggerRelationshipEvent:
            actor_id: str

        def trigger(context: SimulationContext, command: object) -> None:
            self.assertIsInstance(command, TriggerRelationshipEvent)
            for _ in range(100):
                _queue_personal_relationship_event(
                    context, self.engine.definitions, command.actor_id
                )
                story = context.state.entities.require(
                    command.actor_id, "story.state"
                )
                if story.get("pending") is not None:
                    return
            self.fail("深仇人物没有触发旧怨截杀")

        self.engine.commands.register(TriggerRelationshipEvent, trigger)
        created = self.engine.create_game("旧怨", seed=249)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        before_ids = set(self.engine.store.load(game_id).entities.with_component(
            "core.identity"
        ))
        self.engine.execute(game_id, RegisterCharacter(
            "寻仇者", 30, "male", "human", "none", "dao",
            "mortal", 1, "human", 100,
        ))
        state = self.engine.store.load(game_id)
        enemy_id = (set(state.entities.with_component("core.identity")) - before_ids).pop()
        set_relationship_affinity(state, enemy_id, actor_id, -100)
        self.engine.store.save(
            state, [], player_name="旧怨", expected_revision=state.revision
        )

        pending = self.engine.execute(
            game_id, TriggerRelationshipEvent(actor_id)
        ).game["pending_event"]
        self.assertEqual(pending["id"], "EVT_PERSONAL_REVENGE_001")
        self.assertEqual(pending["runtime"]["target_id"], enemy_id)
        resolved = self.engine.choose(game_id, "fight").game
        self.assertEqual(resolved["combat"]["last_report"]["target_id"], enemy_id)
        self.assertEqual(resolved["story"]["history"][-1]["result"], "killed")
        self.assertFalse(
            self.engine.store.load(game_id).entities.require(
                enemy_id, "character.life"
            )["alive"]
        )

    def test_probability_gate_story_chain_is_reachable_from_timed_action(self):
        created = self.engine.create_game("虚天", seed=251)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="core", layer=1)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="虚天", expected_revision=state.revision
        )
        trigger = self.engine.definitions.story_events[
            "EVT_XUTIAN_001"
        ].trigger
        old_chance = trigger["base_chance"]
        trigger["base_chance"] = 1.0
        try:
            acted = self.engine.perform_action(game_id, "rest", 1).game
        finally:
            trigger["base_chance"] = old_chance
        self.assertEqual(acted["pending_event"]["id"], "EVT_XUTIAN_001")
        self.assertIn("100%", acted["pending_event"]["body"])
        self.assertIn(
            "xutian_eligible", acted["story"]["milestones"]
        )

    def test_mortal_root_completion_uses_v1_age_scaled_annual_roll(self):
        created = self.engine.create_game(
            "百岁补根", seed=253, spirit_root="none"
        )
        game_id = created["id"]
        actor_id = created["player"]["id"]
        self.engine.execute(game_id, GrantItem(actor_id, "jinque_metal", 1))
        state = self.engine.store.load(game_id)
        life = state.entities.require(actor_id, "character.life")
        life["birth_year"] = state.clock.year - 134
        life["lifespan"] = 200
        state.entities.put(actor_id, "character.life", life)
        self.engine.store.save(
            state, [], player_name="百岁补根", expected_revision=state.revision
        )

        acted = self.engine.perform_action(game_id, "rest", 1).game
        self.assertEqual(
            acted["pending_event"]["id"], "EVT_MORTAL_ROOT_COMPLETE_001"
        )
        self.assertIn("100%", acted["pending_event"]["body"])
        self.assertEqual(
            acted["pending_event"]["runtime"]["trigger_chance"], 1.0
        )

    def test_three_mountain_materials_open_real_synthesis_event(self):
        created = self.engine.create_game("镇劫山", seed=252)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        for item_id in (
            "north_pole_origin_mountain",
            "yuan_magnetic_divine_mountain",
            "taiyi_green_mountain",
        ):
            self.engine.execute(game_id, GrantItem(actor_id, item_id, 1))
        opened = self.engine.perform_action(game_id, "rest", 1).game
        self.assertEqual(
            opened["pending_event"]["id"], "EVT_FIVE_POLES_CRAFT_001"
        )
        crafted = self.engine.choose(game_id, "craft").game
        quantities = {row["id"]: row["quantity"] for row in crafted["inventory"]}
        self.assertEqual(quantities.get("yuanhe_five_poles_mountain"), 1)
        for item_id in (
            "north_pole_origin_mountain",
            "yuan_magnetic_divine_mountain",
            "taiyi_green_mountain",
        ):
            self.assertEqual(quantities.get(item_id, 0), 0)

    def test_treasure_action_uses_v1_cost_and_world_scoped_fixed_choices(self):
        created = self.engine.create_game(
            "人界探宝", seed=254, preset_id="core"
        )
        game_id = created["id"]
        before_stones = next(
            row["quantity"] for row in created["inventory"]
            if row["id"] == "spirit_stone"
        )
        before_condition = dict(created["combat"]["snapshot"])
        opened = self.engine.perform_action(game_id, "treasure", 1).game
        pending = opened["pending_event"]
        self.assertEqual(pending["id"], "EVT_TREASURE_REWARD_SELECT_001")
        rewards = pending["runtime"]["rewards"]
        self.assertEqual(set(rewards), {"artifact", "technique", "pill"})
        self.assertTrue(all(
            row["world_id"] == "human" and int(row["tier"]) <= 3
            for row in rewards.values()
        ))
        self.assertTrue(all(
            "（" in row["text"] and "阶）" in row["text"]
            for row in pending["choices"]
        ))
        after_stones = next(
            row["quantity"] for row in opened["inventory"]
            if row["id"] == "spirit_stone"
        )
        self.assertEqual(after_stones, before_stones)
        condition = opened["combat"]["snapshot"]
        self.assertTrue(
            condition["hp_ratio"] < before_condition["hp_ratio"]
            or condition["mp_ratio"] < before_condition["mp_ratio"]
        )
        self.assertEqual(
            self.engine.get_game(game_id)["pending_event"]["runtime"],
            pending["runtime"],
        )
        artifact_id = rewards["artifact"]["content_id"]
        claimed = self.engine.choose(game_id, "artifact").game
        self.assertEqual(
            claimed["story"]["history"][-1]["result"],
            "treasure_claimed",
        )
        self.assertEqual(
            next(
                row["quantity"] for row in claimed["inventory"]
                if row["id"] == artifact_id
            ),
            1,
        )

    def test_combat_event_runtime_and_result_gated_reward_are_canonical(self):
        created = self.engine.create_game("截宝", seed=44)
        actor_id = created["player"]["id"]
        state = self.engine.store.load(created["id"])
        actor_cultivation = state.entities.require(
            actor_id, "cultivation.state"
        )
        actor_cultivation.update(realm_id="qi", layer=9)
        state.entities.put(
            actor_id, "cultivation.state", actor_cultivation
        )
        self.engine.store.save(
            state, [], player_name="截宝", expected_revision=state.revision
        )
        queued = self.engine.queue_story_event(
            created["id"], "EVT_COMBAT_WEAK_PREY_001"
        ).game
        pending = queued["pending_event"]
        self.assertNotIn("{target_realm}", pending["body"])
        self.assertNotIn("{target_power}", pending["body"])
        target_id = pending["runtime"]["target_id"]
        self.assertTrue(pending["runtime"]["generated_encounter"])

        state = self.engine.store.load(created["id"])
        target_cultivation = state.entities.require(
            target_id, "cultivation.state"
        )
        target_cultivation.update(realm_id="mortal", layer=1)
        state.entities.put(
            target_id, "cultivation.state", target_cultivation
        )
        self.engine.store.save(
            state, [], player_name="截宝", expected_revision=state.revision
        )
        before = int(dict(state.entities.require(
            actor_id, "economy.inventory"
        )["items"]).get("spirit_sword", 0))
        resolved = self.engine.choose(created["id"], "rob").game
        self.assertEqual(
            resolved["story"]["history"][-1]["result"], "killed"
        )
        persisted = self.engine.store.load(created["id"])
        self.assertEqual(int(dict(persisted.entities.require(
            actor_id, "economy.inventory"
        )["items"])["spirit_sword"]), before + 1)
        self.assertEqual(resolved["combat"]["last_report"]["outcome"], "victory")
        self.assertFalse(
            persisted.entities.require(target_id, "character.life")["alive"]
        )

    def test_legacy_pending_combat_snapshot_is_hydrated_on_load(self):
        created = self.engine.create_game("旧档遇劫", seed=256)
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        event = self.engine.definitions.story_events["EVT_COMBAT_ROBBER_001"]
        story = state.entities.require(actor_id, "story.state")
        story["pending"] = {
            "id": event.id,
            "version": event.version,
            "title": event.title,
            "body": event.body,
            "category": event.category,
            "choices": [
                {
                    "id": choice.id,
                    "text": choice.text,
                    "enabled": True,
                    "disabled_reason": choice.disabled_reason,
                }
                for choice in event.choices
            ],
            "queued_year": state.clock.year,
        }
        state.entities.put(actor_id, "story.state", story)
        self.engine.store.save(
            state, [], player_name="旧档遇劫", expected_revision=state.revision
        )

        repaired = self.engine.get_game(game_id)["pending_event"]
        self.assertNotRegex(repaired["body"], r"\{[A-Za-z_]\w*\}")
        self.assertIn("target_realm", repaired["runtime"])
        self.assertIn("target_power", repaired["runtime"])
        target_id = repaired["runtime"]["target_id"]
        persisted = self.engine.store.load(game_id)
        self.assertTrue(persisted.entities.exists(target_id))
        self.assertEqual(
            persisted.entities.require(target_id, "story.encounter")["event_id"],
            event.id,
        )
        self.assertEqual(
            self.engine.get_game(game_id)["pending_event"], repaired
        )

    def test_all_templated_combat_events_render_without_placeholders(self):
        pattern = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
        events = [
            event
            for event in self.engine.definitions.story_events.values()
            if event.combat and pattern.search(
                " ".join([
                    event.title,
                    event.body,
                    *(choice.text for choice in event.choices),
                ])
            )
        ]
        self.assertGreaterEqual(len(events), 10)
        for index, event in enumerate(events):
            created = self.engine.create_game(
                f"模板校验{index}", seed=300 + index
            )
            pending = self.engine.queue_story_event(
                created["id"], event.id
            ).game["pending_event"]
            visible = [
                pending["title"], pending["body"],
                *(choice["text"] for choice in pending["choices"]),
            ]
            self.assertFalse(
                any(pattern.search(text) for text in visible),
                event.id,
            )

    def test_story_combat_target_spawns_at_the_players_current_map_node(self):
        created = self.engine.create_game(
            "异地遇劫", seed=255, preset_id="core"
        )
        game_id = created["id"]
        actor_id = created["player"]["id"]
        state = self.engine.store.load(game_id)
        location = state.entities.require(actor_id, "world.location")
        destination = next(
            location_id
            for location_id in self.engine.definitions.worlds["human"].locations
            if location_id != location["location_id"]
        )
        location["location_id"] = destination
        state.entities.put(actor_id, "world.location", location)
        self.engine.store.save(
            state, [], player_name="异地遇劫", expected_revision=state.revision
        )

        queued = self.engine.queue_story_event(
            game_id, "EVT_COMBAT_ROBBER_001"
        ).game
        target_id = queued["pending_event"]["runtime"]["target_id"]
        target_location = self.engine.store.load(game_id).entities.require(
            target_id, "world.location"
        )
        self.assertEqual(target_location["location_id"], destination)
        resolved = self.engine.choose(game_id, "fight").game
        self.assertEqual(
            resolved["combat"]["last_report"]["target_id"], target_id
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
