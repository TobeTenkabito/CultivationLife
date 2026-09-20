from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cultivation_life import FormRelationship, GameEngine, RegisterCharacter
from cultivation_life.domain.cultivation import GrantTechnique
from cultivation_life.domain.economy import GrantItem, regional_market_goods
from cultivation_life.server import HTTPCommandRegistry
from cultivation_life.v1_facade import game_view


class V1FacadeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.directory.name) / "v2.sqlite3")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _enemy(self, game_id: str) -> str:
        before = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        self.engine.execute(
            game_id,
            RegisterCharacter(
                "契约敌手", 30, "male", "human", "supreme_wood", "dao",
                "qi", 1, "human",
            ),
        )
        after = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        return (after - before).pop()

    def test_seed_and_full_combat_history_are_real_v2_data(self) -> None:
        created = self.engine.create_game("契约校验", seed=987654321)
        target_id = self._enemy(created["id"])
        canonical = self.engine.fight(created["id"], target_id).game
        view = game_view(canonical, {})

        self.assertEqual(view["seed"], 987654321)
        report = view["last_combat_report"]
        self.assertTrue(report["player_roster"])
        self.assertTrue(report["enemy_roster"])
        self.assertTrue(report["stat_comparison"])
        self.assertTrue(report["rounds"])
        for battle_round in report["rounds"]:
            for field in (
                "player_combat_state", "player_combat_state_max",
                "enemy_combat_state", "enemy_combat_state_max",
                "player_mp_ratio", "player_morale", "enemy_morale",
            ):
                self.assertTrue(
                    math.isfinite(float(battle_round[field])),
                    f"{field} is not finite: {battle_round[field]!r}",
                )

    def test_pre_snapshot_v2_combat_reports_remain_renderable(self) -> None:
        created = self.engine.create_game("旧战报校验", seed=2468)
        target_id = self._enemy(created["id"])
        canonical = self.engine.fight(created["id"], target_id).game
        old_report = canonical["combat"]["last_report"]
        for battle_round in old_report["rounds"]:
            for field in ("initiative", "hp", "hp_ratios", "mp_ratios"):
                battle_round.pop(field, None)

        report = game_view(canonical, {})["last_combat_report"]
        self.assertTrue(report["rounds"])
        self._assert_no_non_finite(report)

    def test_all_creation_paths_have_finite_legacy_view_models(self) -> None:
        cases = (
            ("dao", "human"), ("demonic", "human"), ("ghost", "hell"),
            ("monster", "human"), ("buddhist", "human"),
            ("confucian", "human"),
        )
        required = {
            "player", "map", "market", "auction_system", "faction",
            "family", "governance", "world_npcs", "spirit_ranking",
            "race_system", "world_travel", "trial", "seed",
        }
        for index, (path, world) in enumerate(cases, 1):
            with self.subTest(path=path):
                canonical = self.engine.create_game(
                    f"路线{index}", seed=1000 + index, path=path,
                    start_world=world,
                )
                view = game_view(canonical, {})
                self.assertTrue(required <= set(view))
                self.assertEqual(view["seed"], 1000 + index)
                self._assert_no_non_finite(view)

    def test_party_crossing_and_intrigue_controls_use_v1_field_contracts(self) -> None:
        created = self.engine.create_game("门面联调", seed=1009)
        game_id = str(created["id"])
        actor_id = str(created["player"]["id"])
        self.engine.create_faction(game_id, "门面宗")
        state = self.engine.store.load(game_id)
        before = set(state.entities.with_component("core.identity"))
        self.engine.execute(
            game_id,
            RegisterCharacter(
                "同游客卿", 30, "female", "human", "supreme_water", "dao",
                "foundation", 1, "human", 500,
            ),
        )
        after = set(
            self.engine.store.load(game_id).entities.with_component("core.identity")
        )
        friend_id = (after - before).pop()
        self.engine.execute(
            game_id, FormRelationship(actor_id, friend_id, "friend")
        )
        self.engine.change_affinity(game_id, friend_id, 100)
        self.engine.manage_party(game_id, friend_id, "invite")
        selected = self.engine.manage_party(
            game_id, friend_id, "crossing_add"
        ).game
        view = game_view(selected, {})
        party_member = next(row for row in view["party"] if row["id"] == friend_id)
        self.assertTrue(party_member["can_cross_spirit"])
        self.assertTrue(party_member["selected_for_crossing"])

        section = next(
            row for row in view["intrigue_system"]["sections"]
            if row["kind"] == "sect"
        )
        self.assertTrue(section["control_authority"])
        self.assertTrue(section["disciple_recruitment"])
        self.assertTrue(section["disciple_recruitment"]["realm_options"])
        self.assertIn(friend_id, {
            row["id"] for row in section["guest_candidates"]
        })
        self.assertTrue(all(
            row.get("holder_name") is not None for row in section["positions"]
        ))
        self.assertTrue(next(
            row for row in view["world_npcs"] if row["id"] == friend_id
        )["can_invite_guest"])
        self.assertTrue(view["governance"]["can_issue_bounty"])
        self.assertTrue(view["governance"]["bounty_authorities"])
        self.assertIn(friend_id, {
            row["id"] for row in view["governance"]["bounty_candidates"]
        })

        state = self.engine.store.load(game_id)
        sect_id = next(
            section["id"] for section in view["intrigue_system"]["sections"]
            if section["kind"] == "sect"
        )
        governance = state.entities.require(sect_id, "dlc.intrigue.governance")
        governance["pending_guest_invitation"] = {
            "target_id": actor_id,
            "invited_by": actor_id,
            "title": "客卿长老",
            "world_id": "human",
        }
        state.entities.put(sect_id, "dlc.intrigue.governance", governance)
        self.engine.store.save(
            state, [], player_name="门面联调", expected_revision=state.revision
        )
        invited_view = game_view(self.engine.get_game(game_id), {})
        invitation = invited_view["intrigue_system"]["pending_guest_invitation"]
        self.assertEqual(invitation["faction_name"], "门面宗")
        self.assertEqual(invitation["title"], "客卿长老")

        registry = HTTPCommandRegistry(self.engine)
        issued = registry.dispatch(game_id, "issue-bounty", {
            "npc_id": friend_id,
            "authority": view["governance"]["bounty_authorities"][0]["id"],
        })["game"]
        issued_view = game_view(issued, {})
        self.assertEqual(
            issued_view["governance"]["bounties"][-1]["target_id"], friend_id
        )
        self.assertEqual(issued_view["wanted"], [])
        self.assertNotIn(friend_id, {
            row["id"] for row in issued_view["governance"]["bounty_candidates"]
        })

        invited = self.engine.intrigue_guest_action(
            game_id, "sect", "invite", friend_id
        ).game
        invited_section = next(
            row for row in invited["intrigue_system"]["sections"]
            if row["kind"] == "sect"
        )
        self.assertIn(friend_id, {
            row["npc_id"] for row in invited_section["guests"]
        })

        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="nascent", layer=1)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="门面联调", expected_revision=state.revision
        )
        proposed = self.engine.intrigue_recruitment_action(
            game_id,
            "propose",
            filters={
                "spirit_root": "any", "realm_index": "any",
                "path": "any", "combat": "any", "gender": "any",
            },
        ).game
        recruitment = next(
            row for row in proposed["intrigue_system"]["sections"]
            if row["kind"] == "sect"
        )["disciple_recruitment"]
        self.assertIsNotNone(recruitment["pending"])
        self.assertIn("filter_summary", recruitment["pending"])
        candidate_ids = [
            row["id"] for row in recruitment["pending"]["candidates"]
        ]
        confirmed = self.engine.intrigue_recruitment_action(
            game_id, "confirm", candidate_ids=tuple(candidate_ids[:1])
        ).game
        confirmed_section = next(
            row for row in confirmed["intrigue_system"]["sections"]
            if row["kind"] == "sect"
        )
        self.assertIsNone(
            confirmed_section["disciple_recruitment"]["pending"]
        )
        if candidate_ids:
            state = self.engine.store.load(game_id)
            membership = state.relations.find(
                source_id=candidate_ids[0], kind="faction_membership"
            )
            self.assertEqual(membership[0].metadata["role"], "member")

    def test_v1_technique_buttons_equip_main_support_and_combat_slots(self) -> None:
        created = self.engine.create_game("功法槽联调", seed=1010)
        game_id = str(created["id"])
        actor_id = str(created["player"]["id"])
        for technique_id in ("TECH_BASIC_QI", "TECH_VOID_CYCLE"):
            self.engine.execute(
                game_id, GrantTechnique(actor_id, technique_id)
            )
        state = self.engine.store.load(game_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation["qi_experience"] = {
            source: 10_000 for source in ("spirit", "demon", "monster", "yin")
        }
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="功法槽联调", expected_revision=state.revision
        )
        registry = HTTPCommandRegistry(self.engine)
        baseline = self.engine.get_game(game_id)["combat"]["snapshot"]
        main = registry.dispatch(game_id, "equip-technique", {
            "technique_id": "TECH_BASIC_QI", "slot": "main",
        })["game"]
        self.assertEqual(
            main["player"]["cultivation"]["main_technique"]["id"],
            "TECH_BASIC_QI",
        )
        support = registry.dispatch(game_id, "equip-technique", {
            "technique_id": "TECH_VOID_CYCLE", "slot": "support",
        })["game"]
        self.assertEqual(
            support["player"]["cultivation"]["support_technique"]["id"],
            "TECH_VOID_CYCLE",
        )
        self.assertGreater(
            support["combat"]["snapshot"]["max_hp"], baseline["max_hp"]
        )
        combat = registry.dispatch(game_id, "equip-technique", {
            "technique_id": "TECH_VOID_CYCLE", "slot": "combat",
        })["game"]
        self.assertIn("TECH_VOID_CYCLE", {
            row["id"] for row in combat["player"]["cultivation"]["combat_techniques"]
        })
        self.assertGreater(
            combat["combat"]["snapshot"]["power"],
            support["combat"]["snapshot"]["power"],
        )

    def test_upper_world_navigation_ranking_and_races_come_from_v2_state(self) -> None:
        created = self.engine.create_game("上界契约", seed=777)
        state = self.engine.store.load(created["id"])
        actor_id = str(state.controlled_entity_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="mahayana", layer=9, opportunity=10**9)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        location = state.entities.require(actor_id, "world.location")
        location.update(
            world_id="spirit",
            location_id=self.engine.definitions.default_location("spirit"),
        )
        state.entities.put(actor_id, "world.location", location)
        self.engine.store.save(
            state, [], player_name="上界契约", expected_revision=state.revision
        )
        canonical = self.engine.get_game(created["id"])
        config = {
            "world_travel_rules": {"required_realm": 8},
            "race_details": {
                key: dict(value)
                for key, value in self.engine.definitions.races.items()
            },
        }
        view = game_view(canonical, config)
        self.assertTrue(view["world_travel"]["can_ascend_celestial"])
        self.assertTrue(view["world_travel"]["can_return_human"])
        self.assertTrue(view["spirit_ranking"]["available"])
        self.assertTrue(view["spirit_ranking"]["entries"])
        self.assertTrue(view["race_system"]["available"])
        self.assertIn("human", view["race_system"]["races"])

    def test_market_contract_is_actionable_and_survives_action_and_reload(self) -> None:
        created = self.engine.create_game(
            "坊市契约", seed=778899, preset_id="core"
        )
        game_id = str(created["id"])
        market = game_view(created, {})["market"]
        self.assertEqual(len(market["offers"]), 6)
        self.assertEqual(len(market["material_offers"]), 6)
        self.assertIn(
            "seed",
            self.engine.definitions.items[
                market["offers"][0]["content_id"]
            ].tags,
        )
        self.assertEqual(market["next_tier_chance"], 0.02)
        self.assertTrue(market["name"].endswith("坊市"))
        for offer in [*market["offers"], *market["material_offers"]]:
            self.assertTrue({
                "id", "kind", "name", "description", "tier_name",
                "market_group", "owned", "compatible", "locked", "sold",
                "price",
            } <= set(offer))
            self.assertGreater(int(offer["price"]), 0)

        actor_id = str(created["player"]["id"])
        self.engine.execute(
            game_id, GrantItem(actor_id, "spirit_stone", 10**9, "contract")
        )
        registry = HTTPCommandRegistry(self.engine)
        first_material, second_material = market["material_offers"][:2]
        registry.dispatch(
            game_id, "market-lock", {"offer_id": first_material["id"]}
        )
        locked_result = registry.dispatch(
            game_id, "market-lock", {"offer_id": second_material["id"]}
        )
        locked_market = locked_result["game"]["market"]
        locked_materials = [
            row for row in locked_market["material_offers"] if row["locked"]
        ]
        self.assertEqual(
            [row["id"] for row in locked_materials], [second_material["id"]]
        )
        locked_snapshot = dict(locked_materials[0])

        purchasable = next(
            row for row in locked_market["offers"]
            if row["kind"] == "item" or not row["owned"]
        )
        bought = registry.dispatch(
            game_id, "market-buy", {"offer_id": purchasable["id"]}
        )["game"]["market"]
        self.assertTrue(next(
            row for row in bought["offers"] if row["id"] == purchasable["id"]
        )["sold"])

        before_ids = {
            row["id"] for row in bought["offers"] if not row["locked"]
        }
        advanced = registry.dispatch(
            game_id, "advance", {"action": "cultivate", "units": 1}
        )["game"]
        after_market = advanced["market"]
        retained = next(
            row for row in after_market["material_offers"]
            if row["id"] == second_material["id"]
        )
        self.assertTrue(retained["locked"])
        self.assertEqual(retained["price"], locked_snapshot["price"])
        self.assertNotEqual(
            before_ids,
            {row["id"] for row in after_market["offers"] if not row["locked"]},
        )
        reloaded = game_view(self.engine.get_game(game_id), {})["market"]
        self.assertEqual(
            next(
                row for row in reloaded["material_offers"]
                if row["id"] == second_material["id"]
            )["price"],
            locked_snapshot["price"],
        )

    def test_market_refresh_uses_the_v1_regional_goods_partition(self) -> None:
        created = self.engine.create_game(
            "异地坊市", seed=778900, preset_id="core"
        )
        game_id = str(created["id"])
        actor_id = str(created["player"]["id"])
        definitions = self.engine.definitions

        def localized(location_id: str) -> set[str]:
            return {
                good.content_id
                for good in regional_market_goods(
                    definitions,
                    list(definitions.market_goods),
                    "human",
                    location_id,
                    "market",
                )
            }

        plain_pool = localized("wudi_plain")
        desert_pool = localized("muling_desert")
        self.assertNotEqual(plain_pool, desert_pool)
        plain_offers = game_view(created, {})["market"]["offers"]
        self.assertTrue({row["content_id"] for row in plain_offers} <= plain_pool)

        state = self.engine.store.load(game_id)
        location = state.entities.require(actor_id, "world.location")
        location["location_id"] = "muling_desert"
        state.entities.put(actor_id, "world.location", location)
        self.engine.store.save(
            state, [], player_name="异地坊市", expected_revision=state.revision
        )
        refreshed = self.engine.refresh_market(game_id, force=True).game
        desert_offers = game_view(refreshed, {})["market"]["offers"]
        self.assertTrue({row["content_id"] for row in desert_offers} <= desert_pool)
        persisted = self.engine.store.load(game_id).entities.require(
            actor_id, "economy.market"
        )
        self.assertEqual(persisted["location_id"], "muling_desert")

    def test_empty_migrated_market_is_rebuilt_and_persisted_on_load(self) -> None:
        created = self.engine.create_game(
            "旧坊市恢复", seed=112233, preset_id="core"
        )
        state = self.engine.store.load(created["id"])
        actor_id = str(state.controlled_entity_id)
        market = state.entities.require(actor_id, "economy.market")
        market["offers"] = []
        state.entities.put(actor_id, "economy.market", market)
        self.engine.store.save(
            state, [], player_name="旧坊市恢复", expected_revision=state.revision
        )

        recovered = game_view(self.engine.get_game(created["id"]), {})["market"]
        self.assertEqual(len(recovered["offers"]), 6)
        self.assertEqual(len(recovered["material_offers"]), 6)
        persisted = self.engine.store.load(created["id"])
        self.assertEqual(
            len(persisted.entities.require(actor_id, "economy.market")["offers"]),
            12,
        )

    def test_market_can_buy_incompatible_manual_without_equipping_it(self) -> None:
        created = self.engine.create_game("异属功法", seed=1)
        game_id = str(created["id"])
        state = self.engine.store.load(game_id)
        actor_id = str(state.controlled_entity_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="core", layer=1)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        self.engine.store.save(
            state, [], player_name="异属功法", expected_revision=state.revision
        )
        current = self.engine.get_game(game_id)
        offer = None
        for _ in range(40):
            market = game_view(current, {})["market"]
            offer = next((
                row for row in market["offers"]
                if row["kind"] == "technique" and not row["compatible"]
            ), None)
            if offer is not None:
                break
            current = self.engine.refresh_market(game_id, force=True).game
        self.assertIsNotNone(offer)
        assert offer is not None
        self.engine.execute(
            game_id, GrantItem(actor_id, "spirit_stone", 10**6, "contract")
        )
        bought = self.engine.buy_market_offer(game_id, offer["id"]).game
        known = {
            row["id"] for row in bought["player"]["cultivation"]["known_techniques"]
        }
        self.assertIn(offer["content_id"], known)
        self.assertNotEqual(
            dict(
                bought["player"]["cultivation"].get("main_technique") or {}
            ).get("id"),
            offer["content_id"],
        )

    def test_nether_both_lower_world_buttons_round_trip_real_v2_state(self) -> None:
        created = self.engine.create_game("幽冥往返", seed=445566)
        game_id = str(created["id"])
        state = self.engine.store.load(game_id)
        actor_id = str(state.controlled_entity_id)
        cultivation = state.entities.require(actor_id, "cultivation.state")
        cultivation.update(realm_id="true_immortal", layer=1)
        state.entities.put(actor_id, "cultivation.state", cultivation)
        location = state.entities.require(actor_id, "world.location")
        location.update(
            world_id="nether",
            location_id=self.engine.definitions.default_location("nether"),
        )
        state.entities.put(actor_id, "world.location", location)
        self.engine.store.save(
            state, [], player_name="幽冥往返", expected_revision=state.revision
        )

        upper = game_view(self.engine.get_game(game_id), {})
        self.assertTrue(upper["world_travel"]["can_descend_monster"])
        self.assertTrue(upper["world_travel"]["can_descend_phantom"])
        for lower_world in ("monster_realm", "phantom_underworld"):
            descended = game_view(
                self.engine.cross_world(game_id, lower_world).game, {}
            )
            self.assertEqual(descended["player"]["world"], lower_world)
            self.assertTrue(descended["world_travel"]["can_return_nether"])
            returned = game_view(
                self.engine.cross_world(game_id, "nether").game, {}
            )
            self.assertEqual(returned["player"]["world"], "nether")
            self.assertEqual(returned["player"]["realm_index"], 9)

    def test_every_supported_world_has_two_complete_market_shelves(self) -> None:
        cases = {
            "human": "core", "demon": "core", "spirit": "spirit",
            "true_demon": "spirit", "monster_realm": "spirit",
            "phantom_underworld": "spirit", "hell": "spirit",
            "celestial": "true_immortal", "asura": "true_immortal",
            "nether": "true_immortal",
        }
        for index, (world_id, realm_id) in enumerate(cases.items(), 1):
            with self.subTest(world=world_id):
                created = self.engine.create_game(
                    f"坊市-{world_id}", seed=8100 + index
                )
                state = self.engine.store.load(created["id"])
                actor_id = str(state.controlled_entity_id)
                cultivation = state.entities.require(actor_id, "cultivation.state")
                cultivation.update(realm_id=realm_id, layer=1)
                state.entities.put(actor_id, "cultivation.state", cultivation)
                location = state.entities.require(actor_id, "world.location")
                location.update(
                    world_id=world_id,
                    location_id=self.engine.definitions.default_location(world_id),
                )
                state.entities.put(actor_id, "world.location", location)
                self.engine.store.save(
                    state, [], player_name=f"坊市-{world_id}",
                    expected_revision=state.revision,
                )
                market = game_view(
                    self.engine.get_game(created["id"]), {}
                )["market"]
                self.assertTrue(market["available"])
                self.assertEqual(len(market["offers"]), 6)
                self.assertEqual(len(market["material_offers"]), 6)
                self._assert_no_non_finite(market)

    def test_v1_combat_action_runs_after_travel_and_pays_real_rewards(self) -> None:
        created = self.engine.create_game(
            "异地猎妖", seed=991122, preset_id="core"
        )
        game_id = str(created["id"])
        actor_id = str(created["player"]["id"])
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
            state, [], player_name="异地猎妖", expected_revision=state.revision
        )
        before_stones = next(
            row["quantity"]
            for row in self.engine.get_game(game_id)["inventory"]
            if row["id"] == "spirit_stone"
        )

        result = HTTPCommandRegistry(self.engine).dispatch(
            game_id, "advance", {"action": "hunt_beast", "years": 1}
        )["game"]
        report = result["combat"]["last_report"]
        self.assertEqual(report["outcome"], "victory")
        persisted = self.engine.store.load(game_id)
        target_location = persisted.entities.require(
            report["target_id"], "world.location"
        )
        self.assertEqual(target_location["location_id"], destination)
        after_stones = next(
            row["quantity"]
            for row in result["inventory"]
            if row["id"] == "spirit_stone"
        )
        self.assertGreater(after_stones, before_stones)
        self.assertGreater(result["story"]["attributes"]["sha_qi"], 0)
        legacy = game_view(result, {})
        self.assertEqual(
            legacy["last_combat_report"]["enemy_roster"][0]["id"],
            report["target_id"],
        )

    def test_v1_commission_button_pays_the_configured_tier_reward(self) -> None:
        created = self.engine.create_game(
            "坊市跑腿", seed=991123, preset_id="core"
        )
        game_id = str(created["id"])
        before = next(
            row["quantity"] for row in created["inventory"]
            if row["id"] == "spirit_stone"
        )
        response = HTTPCommandRegistry(self.engine).dispatch(
            game_id, "advance", {"action": "commission", "years": 1}
        )["game"]
        after = next(
            row["quantity"] for row in response["inventory"]
            if row["id"] == "spirit_stone"
        )
        self.assertGreaterEqual(after - before, 28)
        self.assertLessEqual(after - before, 55)
        persisted = self.engine.get_game(game_id)
        self.assertEqual(
            next(
                row["quantity"] for row in persisted["inventory"]
                if row["id"] == "spirit_stone"
            ),
            after,
        )

    def _assert_no_non_finite(self, value: Any) -> None:
        if isinstance(value, float):
            self.assertTrue(math.isfinite(value), value)
        elif isinstance(value, dict):
            for child in value.values():
                self._assert_no_non_finite(child)
        elif isinstance(value, list):
            for child in value:
                self._assert_no_non_finite(child)


if __name__ == "__main__":
    unittest.main()
