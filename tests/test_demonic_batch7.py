from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import (
    AttemptBreakthrough,
    CaptiveAction,
    CraftMechanicalPuppet,
    EnterImprisonment,
    FormRelationship,
    GrantItem,
    ManageConcubine,
    PostBattlePossession,
    PrisonAction,
    PuppetAction,
    RefineForeignSoul,
    RegisterCharacter,
    ResolveCombat,
    GameEngine,
)
from cultivation_life.domain.cultivation import CULTIVATION
from cultivation_life.domain.demonic import (
    FOREIGN_SOUL,
)
from cultivation_life.domain.world import LOCATION


class V2DemonicBatchSevenTests(unittest.TestCase):
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
        world_id: str = "human",
        realm_id: str = "mortal",
        layer: int = 1,
        gender: str = "male",
        path: str = "dao",
    ) -> str:
        before = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        self.engine.execute(game_id, RegisterCharacter(
            name=name,
            age=24,
            gender=gender,
            race="human",
            spirit_root="supreme_wood",
            path=path,
            realm_id=realm_id,
            layer=layer,
            world_id=world_id,
        ))
        after = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        return (after - before).pop()

    def _set_realm(
        self, game_id: str, actor_id: str, realm_id: str, layer: int = 1,
    ) -> None:
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation.update(realm_id=realm_id, layer=layer)
        state.entities.put(actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="test", expected_revision=state.revision
        )

    def _resolve_pending(self, game_id: str) -> None:
        game = self.engine.get_game(game_id)
        while game["pending_event"] is not None:
            choice = next(
                row for row in game["pending_event"]["choices"] if row["enabled"]
            )
            game = self.engine.choose(game_id, choice["id"]).game

    def _open_black_market(self, game_id: str, actor_id: str) -> dict:
        state = self.engine.store.load(game_id)
        location_id = state.entities.require(actor_id, LOCATION)["location_id"]
        self.engine.schedule_auction(game_id, location_id)
        for _ in range(2):
            self.engine.perform_action(game_id, "rest", 1)
            self._resolve_pending(game_id)
        rules = self.engine.definitions.systems["auction_system"]
        previous = rules["auction_rounds"]
        try:
            rules["auction_rounds"] = 1
            return self.engine.advance_auction_round(game_id).game
        finally:
            rules["auction_rounds"] = previous

    def test_imprisonment_uses_time_and_releases_canonical_relation(self):
        game = self.engine.create_game("囚徒", seed=701)
        actor_id = game["player"]["id"]
        captor_id = self._register(game["id"], "狱主")
        entered = self.engine.execute(
            game["id"],
            EnterImprisonment(
                actor_id, captor_id, 2, "刑堂", "faction_prison", 30.0
            ),
        ).game
        self.assertEqual(entered["demonic_system"]["imprisonment"]["remaining_years"], 2)
        with self.assertRaisesRegex(ValueError, "身陷大牢"):
            self.engine.perform_action(game["id"], "cultivate", 1)
        with self.assertRaisesRegex(ValueError, "暂不开放越狱"):
            self.engine.execute(game["id"], PrisonAction(actor_id, "escape"))
        first = self.engine.execute(
            game["id"], PrisonAction(actor_id, "cultivate")
        ).game
        self.assertEqual(first["clock"]["year"], 1)
        self.assertEqual(first["demonic_system"]["imprisonment"]["remaining_years"], 1)
        self._resolve_pending(game["id"])
        released = self.engine.execute(
            game["id"], PrisonAction(actor_id, "wait")
        ).game
        self.assertEqual(released["clock"]["year"], 2)
        self.assertIsNone(released["demonic_system"]["imprisonment"])
        state = self.engine.store.load(game["id"])
        self.assertFalse(state.relations.find(target_id=actor_id, kind="prisoner"))

        smuggler = self.engine.create_game("偷渡客", seed=7001)
        smuggler_id = smuggler["player"]["id"]
        self._set_realm(smuggler["id"], smuggler_id, "spirit", 1)
        smuggler_captor = self._register(smuggler["id"], "边狱狱卒")
        self.engine.execute(
            smuggler["id"],
            EnterImprisonment(smuggler_id, smuggler_captor, 5),
        )
        crossed = self.engine.ascend_world(smuggler["id"], "spirit").game
        self.assertEqual(crossed["world"]["world_id"], "spirit")
        self.assertIsNone(crossed["demonic_system"]["imprisonment"])

    def test_captive_living_puppet_soul_and_breakthrough_bonus_loop(self):
        game = self.engine.create_game("魔主", seed=702, path="demonic", start_world="demon")
        actor_id = game["player"]["id"]
        self._set_realm(game["id"], actor_id, "core", 3)
        target_id = self._register(
            game["id"], "战俘", world_id="demon", realm_id="mortal"
        )
        captured = self.engine.execute(
            game["id"], ResolveCombat(actor_id, target_id, "capture")
        ).game
        self.assertTrue(captured["combat"]["last_report"]["captured"])
        converted = self.engine.execute(
            game["id"], CaptiveAction(actor_id, target_id, "living")
        ).game
        self.assertEqual(converted["demonic_system"]["puppets"][0]["type"], "living")
        puppet_view = converted["demonic_system"]["puppets"][0]
        for field in (
            "main_technique_name", "battle_contribution_ratio",
            "battle_contribution_mode", "annual_opportunity",
        ):
            self.assertNotIn(puppet_view.get(field), (None, "", "undefined"))
        self.assertGreater(converted["demonic_system"]["control_mp_cost"], 0)
        self.assertTrue(converted["demonic_system"]["time_behavior"])
        self.assertIn("secluded_refine_years", converted["demonic_system"])
        reinforced = self.engine.execute(
            game["id"], PuppetAction(actor_id, target_id, "reinforce_control")
        ).game
        self.assertGreater(
            reinforced["demonic_system"]["puppets"][0]["control"], 55.0
        )
        devoured = self.engine.execute(
            game["id"], PuppetAction(actor_id, target_id, "devour")
        ).game
        self.assertEqual(devoured["demonic_system"]["puppets"], [])
        self.assertEqual(len(devoured["demonic_system"]["foreign_souls"]), 1)
        self.assertGreater(devoured["demonic_system"]["breakthrough_bonus"], 0.0)

        state = self.engine.store.load(game["id"])
        soul_id = next(iter(state.entities.with_component(FOREIGN_SOUL)))
        soul = state.entities.require(soul_id, FOREIGN_SOUL)
        soul["progress"] = float(soul["required"]) - 0.01
        state.entities.put(soul_id, FOREIGN_SOUL, soul)
        cultivation = state.entities.require(actor_id, CULTIVATION)
        cultivation.update(opportunity=1_000_000.0, bottleneck="minor")
        state.entities.put(actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="魔主", expected_revision=state.revision
        )
        year_before_refining = self.engine.get_game(game["id"])["clock"]["year"]
        refined = self.engine.execute(
            game["id"], RefineForeignSoul(actor_id, secluded=True)
        ).game
        self.assertGreater(refined["clock"]["year"], year_before_refining)
        self.assertIsNone(refined["action"]["active"])
        self.assertTrue(refined["demonic_system"]["foreign_souls"][0]["refined"])
        self.assertGreater(refined["demonic_system"]["breakthrough_bonus"], 0.0)
        self._resolve_pending(game["id"])
        attempted = self.engine.execute(
            game["id"], AttemptBreakthrough(actor_id)
        ).game
        self.assertEqual(attempted["demonic_system"]["breakthrough_bonus"], 0.0)

    def test_concubine_corpse_conversion_is_not_a_companion_relation(self):
        game = self.engine.create_game("尸主", seed=703, path="demonic", start_world="demon")
        actor_id = game["player"]["id"]
        self._set_realm(game["id"], actor_id, "spirit", 3)
        target_id = self._register(
            game["id"], "绯衣", world_id="demon", gender="female"
        )
        self.engine.execute(
            game["id"], FormRelationship(actor_id, target_id, "concubine")
        )
        converted = self.engine.execute(
            game["id"], ManageConcubine(actor_id, target_id, "corpse")
        ).game
        self.assertEqual(converted["concubine_system"]["concubines"], [])
        self.assertEqual(converted["demonic_system"]["puppets"][0]["type"], "corpse")
        self.assertFalse(any(
            row["kind"] == "dao_companion" for row in converted["relationships"]
        ))

    def test_mechanical_puppet_black_market_sale_and_ascension_cleanup(self):
        game = self.engine.create_game("机关师", seed=704)
        actor_id = game["player"]["id"]
        self._set_realm(game["id"], actor_id, "qi", 1)
        self.engine.execute(game["id"], GrantItem(actor_id, "spirit_stone", 1000))
        crafted = self.engine.execute(
            game["id"], CraftMechanicalPuppet(actor_id)
        ).game
        puppet_id = crafted["demonic_system"]["puppets"][0]["id"]
        market = self._open_black_market(game["id"], actor_id)
        self.assertEqual(
            market["auction"]["black_market_sellable_puppets"][0]["id"],
            puppet_id,
        )
        before = market["market"]["spirit_stones"]
        sold = self.engine.sell_black_market_asset(
            game["id"], "puppet", puppet_id
        ).game
        self.assertEqual(sold["demonic_system"]["puppets"], [])
        self.assertGreater(sold["market"]["spirit_stones"], before)

        game2 = self.engine.create_game("飞升机关师", seed=705)
        actor2 = game2["player"]["id"]
        self.engine.execute(game2["id"], GrantItem(actor2, "spirit_stone", 25))
        self.engine.execute(game2["id"], CraftMechanicalPuppet(actor2))
        self._set_realm(game2["id"], actor2, "spirit", 1)
        ascended = self.engine.ascend_world(game2["id"], "spirit").game
        self.assertEqual(ascended["demonic_system"]["puppets"], [])
        self.assertIn(
            "demonic",
            ascended["world"]["transition"]["last_transaction"]["acknowledgements"],
        )

    def test_invalid_post_battle_possession_is_rejected_without_state_change(self):
        game = self.engine.create_game("游魂", seed=706, path="ghost", start_world="hell")
        actor_id = game["player"]["id"]
        target_id = self._register(game["id"], "凡躯", world_id="hell")
        before = self.engine.store.load(game["id"]).to_dict()
        with self.assertRaisesRegex(ValueError, "没有可结算"):
            self.engine.execute(
                game["id"], PostBattlePossession(actor_id, target_id)
            )
        after = self.engine.store.load(game["id"]).to_dict()
        self.assertEqual(after, before)

    def test_lethal_defeat_preserves_captive_for_one_post_battle_possession(self):
        game = self.engine.create_game(
            "孤魂", seed=707, path="ghost", start_world="hell"
        )
        actor_id = game["player"]["id"]
        self._set_realm(game["id"], actor_id, "core", 3)
        captive_id = self._register(
            game["id"], "备用躯壳", world_id="hell", realm_id="mortal"
        )
        self.engine.execute(
            game["id"], ResolveCombat(actor_id, captive_id, "capture")
        )
        executioner_id = self._register(
            game["id"], "冥府判官", world_id="hell",
            realm_id="true_immortal", layer=1,
        )
        fallen = self.engine.execute(
            game["id"], ResolveCombat(actor_id, executioner_id, "kill")
        ).game
        self.assertFalse(fallen["player"]["alive"])
        self.assertEqual(
            fallen["demonic_system"]["pending_post_battle_possession"][
                "candidate_ids"
            ],
            [captive_id],
        )
        possessed = self.engine.execute(
            game["id"], PostBattlePossession(actor_id, captive_id)
        ).game
        self.assertTrue(possessed["player"]["alive"])
        self.assertEqual(possessed["demonic_system"]["possession"]["count"], 1)
        self.assertIsNone(
            possessed["demonic_system"]["pending_post_battle_possession"]
        )
        with self.assertRaisesRegex(ValueError, "没有可结算"):
            self.engine.execute(
                game["id"], PostBattlePossession(actor_id, captive_id)
            )

    def test_frozen_demonic_crossing_gate_and_qi_death_are_authoritative(self):
        doomed = self.engine.create_game(
            "破界魔修", seed=708, path="demonic", start_world="demon"
        )
        actor_id = doomed["player"]["id"]
        self._set_realm(doomed["id"], actor_id, "spirit", 1)
        gate = self.engine.get_game(doomed["id"])["demonic_system"][
            "true_demon_ascension"
        ]
        self.assertTrue(gate["available"])
        self.assertFalse(gate["satisfied"])
        failed = self.engine.begin_spirit_crossing(doomed["id"]).game
        self.assertFalse(failed["player"]["alive"])
        self.assertEqual(failed["world"]["world_id"], "demon")
        self.assertIn("魔气等级", failed["player"]["death_reason"])

        successful = self.engine.create_game(
            "炼魔破界", seed=709, path="demonic", start_world="demon"
        )
        successful_id = successful["player"]["id"]
        self._set_realm(successful["id"], successful_id, "spirit", 1)
        state = self.engine.store.load(successful["id"])
        cultivation = state.entities.require(successful_id, CULTIVATION)
        cultivation["qi_experience"]["demon"] = 25 * 8**2
        state.entities.put(successful_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="炼魔破界",
            expected_revision=state.revision,
        )
        gate = self.engine.get_game(successful["id"])["demonic_system"][
            "true_demon_ascension"
        ]
        self.assertTrue(gate["satisfied"])
        crossed = self.engine.begin_spirit_crossing(successful["id"]).game
        self.assertEqual(crossed["world"]["world_id"], "true_demon")
        self.assertTrue(crossed["player"]["alive"])


if __name__ == "__main__":
    unittest.main()
