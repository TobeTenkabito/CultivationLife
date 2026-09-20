from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cultivation_life import GrantItem, GameEngine
from cultivation_life.domain.artifacts import FORMATION
from cultivation_life.domain.assets import ASSET_LEDGER
from cultivation_life.domain.combat import combat_snapshot
from cultivation_life.domain.cultivation import CULTIVATION
from cultivation_life.server import HTTPCommandRegistry
from cultivation_life.v1_facade import game_view


class V2ArtifactsFormationsNatalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = GameEngine(Path(self.directory.name) / "v2.sqlite3")
        game = self.engine.create_game("百艺修士", seed=881177)
        self.game_id = game["id"]
        self.actor_id = game["player"]["id"]
        self._set_realm("qi")

    def tearDown(self):
        self.directory.cleanup()

    def _set_realm(self, realm_id: str) -> None:
        state = self.engine.store.load(self.game_id)
        cultivation = state.entities.require(self.actor_id, CULTIVATION)
        cultivation.update(realm_id=realm_id, layer=1)
        state.entities.put(self.actor_id, CULTIVATION, cultivation)
        self.engine.store.save(
            state, [], player_name="百艺修士", expected_revision=state.revision
        )

    def _add_asset(
        self, kind: str, definition_id: str, name: str, metadata: dict,
    ) -> str:
        state = self.engine.store.load(self.game_id)
        ledger = state.entities.require(self.actor_id, ASSET_LEDGER)
        sequence = int(ledger["next_sequence"])
        asset_id = f"asset:{self.actor_id}:{sequence}"
        instances = dict(ledger["instances"])
        instances[asset_id] = {
            "id": asset_id, "kind": kind, "definition_id": definition_id,
            "name": name, "created_year": state.clock.year,
            "metadata": dict(metadata), "reservation_id": None,
        }
        ledger.update(next_sequence=sequence + 1, instances=instances)
        state.entities.put(self.actor_id, ASSET_LEDGER, ledger)
        self.engine.store.save(
            state, [], player_name="百艺修士", expected_revision=state.revision
        )
        return asset_id

    def _crafting_payload(self) -> dict:
        materials = self.engine.definitions.systems["crafting"]["materials"]
        primary = next(row for row in materials if "primary" in row["roles"])
        secondaries = [row for row in materials if "secondary" in row["roles"]]
        secondary_a = secondaries[0]
        secondary_b = next(
            row for row in secondaries
            if row["id"] != secondary_a["id"] or row.get("allow_duplicate_type")
        )
        quench = next(row for row in materials if "quench" in row["roles"])

        def add(row: dict) -> str:
            return self._add_asset(
                "crafting_material", row["id"], row["name"],
                {
                    "tier": int(row.get("tier", 1)), "quality_multiplier": 1.0,
                    "material_value": int(row["base_material_value"]),
                },
            )

        return {
            "mold_id": "sword", "name": "测试灵剑",
            "primary_id": add(primary), "secondary_a_id": add(secondary_a),
            "secondary_b_id": add(secondary_b), "quench_id": add(quench),
            "allocations": {"combat_power": 1},
        }

    def test_crafting_preview_blueprint_forge_and_sale_use_exact_instances(self):
        payload = self._crafting_payload()
        source_ids = {
            payload[key] for key in (
                "primary_id", "secondary_a_id", "secondary_b_id", "quench_id"
            )
        }
        preview = self.engine.preview_crafting(self.game_id, payload)
        self.assertEqual(preview.game["crafting"]["last_preview"]["mold"]["id"], "sword")
        blueprint = self.engine.save_crafting_blueprint(
            self.game_id, {**payload, "blueprint_name": "试剑图谱"}
        )
        self.assertEqual(blueprint.game["crafting"]["blueprints"][0]["name"], "试剑图谱")
        before = combat_snapshot(
            self.engine.store.load(self.game_id), self.engine.definitions, self.actor_id
        )["power"]
        forged = self.engine.forge_crafted_artifact(self.game_id, payload)
        remaining = {row["id"] for row in forged.game["assets"]["instances"]}
        self.assertTrue(source_ids.isdisjoint(remaining))
        artifact = next(
            row for row in forged.game["assets"]["instances"]
            if row["kind"] == "crafted_artifact"
        )
        after = combat_snapshot(
            self.engine.store.load(self.game_id), self.engine.definitions, self.actor_id
        )["power"]
        self.assertGreater(after, before)
        stones_before = forged.game["market"]["spirit_stones"]
        sold = self.engine.crafted_artifact_action(
            self.game_id, artifact["id"], "sell"
        )
        self.assertFalse(any(
            row["id"] == artifact["id"] for row in sold.game["assets"]["instances"]
        ))
        self.assertGreater(sold.game["market"]["spirit_stones"], stones_before)

    def test_normal_market_delivers_unique_crafting_and_formation_assets(self):
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 100_000)
        )
        market = self.engine.refresh_market(self.game_id, force=True).game
        crafting = next(
            row for row in market["market"]["offers"]
            if row["kind"] == "crafting_material"
        )
        formation = next(
            row for row in market["market"]["offers"]
            if row["kind"] == "formation_material"
        )
        bought_crafting = self.engine.buy_market_offer(
            self.game_id, crafting["id"]
        ).game
        bought_formation = self.engine.buy_market_offer(
            self.game_id, formation["id"]
        ).game
        kinds = {row["kind"] for row in bought_formation["assets"]["instances"]}
        self.assertIn("crafting_material", kinds)
        self.assertIn("formation_material", kinds)
        self.assertTrue(next(
            row for row in bought_crafting["market"]["offers"]
            if row["id"] == crafting["id"]
        )["sold"])

    def test_formation_activation_ground_repair_and_withdraw_preserve_escrow(self):
        definition = self.engine.definitions.systems["formations"]["materials"][0]
        slots = [
            self._add_asset(
                "formation_material", definition["id"], definition["name"],
                {
                    "tier": definition["tier"], "base_value": definition["base_value"],
                    "formation_value": definition["formation_value"],
                    "nature": definition["nature"],
                },
            )
            for _ in range(9)
        ]
        saved = self.engine.save_formation(
            self.game_id, {"name": "九宫测试阵", "slots": slots, "activate": True}
        )
        loadout = saved.game["formation_system"]["loadouts"][0]
        self.assertEqual(saved.game["formation_system"]["active"]["loadout_id"], loadout["id"])
        self.assertEqual(len(saved.game["assets"]["reservations"]), 9)
        deployed = self.engine.deploy_ground_formation(self.game_id)
        ground = deployed.game["formation_system"]["ground_arrays"][0]
        self.assertIsNone(deployed.game["formation_system"]["active"])
        self.assertEqual(len(deployed.game["assets"]["reservations"]), 9)

        state = self.engine.store.load(self.game_id)
        formation = state.entities.require(self.actor_id, FORMATION)
        formation["ground_arrays"][0]["durability"] = 50.0
        state.entities.put(self.actor_id, FORMATION, formation)
        self.engine.store.save(
            state, [], player_name="百艺修士", expected_revision=state.revision
        )
        supply = next(
            row for row in self.engine.definitions.systems["formations"]["maintenance_resources"]
            if row["world"] == "human"
        )
        supply_id = self._add_asset(
            "formation_supply", supply["id"], supply["name"],
            {"tier": supply["tier"], "base_value": supply["base_value"], "repair_value": supply["repair_value"]},
        )
        repaired = self.engine.repair_ground_formation(
            self.game_id, ground["id"], supply_id
        )
        self.assertGreater(
            repaired.game["formation_system"]["ground_arrays"][0]["durability"], 50
        )
        withdrawn = self.engine.withdraw_ground_formation(self.game_id, ground["id"])
        self.assertEqual(withdrawn.game["formation_system"]["ground_arrays"], [])
        self.assertEqual(withdrawn.game["assets"]["reservations"], [])
        activated = self.engine.activate_formation(self.game_id, loadout["id"])
        self.assertIsNotNone(activated.game["formation_system"]["active"])
        deactivated = self.engine.deactivate_formation(self.game_id)
        self.assertIsNone(deactivated.game["formation_system"]["active"])
        deleted = self.engine.delete_formation(self.game_id, loadout["id"])
        self.assertEqual(deleted.game["formation_system"]["loadouts"], [])

    def test_crafted_natal_artifact_levels_and_sockets_without_duplication(self):
        payload = self._crafting_payload()
        forged = self.engine.forge_crafted_artifact(self.game_id, payload)
        artifact = next(
            row for row in forged.game["assets"]["instances"]
            if row["kind"] == "crafted_artifact"
        )
        self._set_realm("core")
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 10_000)
        )
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "star_pattern_copper", 1)
        )
        bound = self.engine.natal_artifact_action(
            self.game_id, "bind", artifact["id"]
        )
        self.assertEqual(bound.game["natal_artifact"]["level"], 1)
        with self.assertRaisesRegex(ValueError, "本命.*不能出售"):
            self.engine.crafted_artifact_action(
                self.game_id, artifact["id"], "sell"
            )
        socketed = self.engine.natal_artifact_action(
            self.game_id, "socket", "star_pattern_copper", 0
        )
        self.assertEqual(socketed.game["natal_artifact"]["slots"][0], "star_pattern_copper")
        self.engine.natal_artifact_action(self.game_id, "refine")
        self.engine.natal_artifact_action(self.game_id, "refine")
        refined = self.engine.natal_artifact_action(self.game_id, "refine")
        self.assertEqual(refined.game["natal_artifact"]["level"], 2)
        unbound = self.engine.crafted_artifact_action(
            self.game_id, artifact["id"], "unbind_natal"
        )
        self.assertFalse(unbound.game["natal_artifact"]["bound"])
        copper = next(row for row in unbound.game["inventory"] if row["id"] == "star_pattern_copper")
        self.assertEqual(copper["quantity"], 1)

    def test_frozen_v1_crafting_and_natal_controls_complete_real_http_flow(self):
        payload = self._crafting_payload()
        registry = HTTPCommandRegistry(self.engine)
        public = game_view(self.engine.get_game(self.game_id), {})
        crafting = public["crafting_system"]
        self.assertTrue(crafting["visible"])
        self.assertGreater(crafting["budget"], 0)
        self.assertTrue(crafting["stat_costs"])
        self.assertTrue(crafting["stat_names"])
        for material in crafting["materials"]:
            self.assertTrue(material["id"])
            self.assertTrue(material["state"])
            self.assertTrue(material["source"])
            self.assertTrue(material["roles"])
            self.assertIn("role_effects", material)

        preview = registry.dispatch(
            self.game_id, "crafting-preview", payload
        )
        self.assertEqual(preview["mold"]["id"], "sword")
        self.assertIn("theoretical_stats", preview)
        forged = registry.dispatch(
            self.game_id, "crafting-forge", payload
        )["game"]
        view = game_view(forged, {})
        artifact = view["crafting_system"]["artifacts"][0]
        inventory_artifact = next(
            row for row in view["player"]["inventory"]
            if row.get("crafted_artifact_id") == artifact["id"]
        )
        self.assertEqual(inventory_artifact["quantity"], 1)
        self.assertGreater(artifact["anchor_value"], 0)
        self.assertIn("actual_stats", artifact)

        self._set_realm("core")
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "spirit_stone", 10_000)
        )
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "star_pattern_copper", 1)
        )
        registry.dispatch(self.game_id, "crafted-artifact", {
            "artifact_id": artifact["id"], "action": "natal",
        })
        bound_view = game_view(self.engine.get_game(self.game_id), {})
        natal = bound_view["natal_artifact"]
        self.assertTrue(natal["bound"])
        self.assertTrue(natal["can_refine"])
        self.assertEqual(len(natal["slots"]), 7)
        self.assertTrue(natal["slots"][0]["unlocked"])
        self.assertIn("combat_bonus", natal["bonuses"])
        material = next(
            row for row in natal["materials"]
            if row["item_id"] == "star_pattern_copper"
        )
        self.assertTrue(material["available"])
        registry.dispatch(self.game_id, "natal-artifact", {
            "action": "socket", "item_id": material["item_id"],
            "slot_index": 0,
        })
        socketed_view = game_view(self.engine.get_game(self.game_id), {})
        self.assertEqual(
            socketed_view["natal_artifact"]["slots"][0]["material_id"],
            "star_pattern_copper",
        )
        state = self.engine.store.load(self.game_id)
        location_id = state.entities.require(
            self.actor_id, "world.location"
        )["location_id"]
        auction = self.engine.schedule_auction(
            self.game_id, location_id
        ).game["auction"]
        self.assertNotIn(
            artifact["id"],
            {row["asset_ref"] for row in auction["consignable_assets"]},
        )

    def test_frozen_v1_formation_controls_complete_real_http_flow(self):
        definition = self.engine.definitions.systems["formations"]["materials"][0]
        slots = [
            self._add_asset(
                "formation_material", definition["id"], definition["name"],
                {
                    "tier": definition["tier"],
                    "base_value": definition["base_value"],
                    "formation_value": definition["formation_value"],
                    "nature": definition["nature"], "source": "test",
                },
            )
            for _ in range(2)
        ]
        registry = HTTPCommandRegistry(self.engine)
        public = game_view(self.engine.get_game(self.game_id), {})
        formation = public["formation_system"]
        self.assertTrue(formation["visible"])
        self.assertEqual(formation["grid_size"], 9)
        self.assertEqual(formation["system_version"], 2)
        self.assertGreater(formation["alpha"], 0)
        self.assertEqual(
            {row["id"] for row in formation["materials"]}, set(slots)
        )
        self.assertTrue(all(
            row["nature_name"] and row["source_kind"]
            for row in formation["materials"]
        ))
        payload = {
            "name": "前端验真阵",
            "slots": [*slots, *([None] * 7)],
            "activate": True,
        }
        preview = registry.dispatch(
            self.game_id, "formation-preview", payload
        )
        self.assertTrue(preview["active"])
        registry.dispatch(self.game_id, "formation-save", payload)
        active_view = game_view(self.engine.get_game(self.game_id), {})[
            "formation_system"
        ]
        self.assertTrue(active_view["active_formation_id"])
        self.assertEqual(
            [row["id"] for row in active_view["active_bindings"] if row],
            slots,
        )
        # Frozen V1 immediately re-submits active reserved material IDs when
        # the player adjusts the name or previews the current formation.
        active_payload = {
            "name": "前端验真阵",
            "slots": [
                row["id"] if row else None
                for row in active_view["active_bindings"]
            ],
            "activate": False,
        }
        self.assertTrue(registry.dispatch(
            self.game_id, "formation-preview", active_payload
        )["active"])
        deployed = registry.dispatch(
            self.game_id, "formation-ground-deploy", {"owner_kind": "player"}
        )["game"]
        ground = game_view(deployed, {})["formation_system"]["ground_arrays"][0]
        self.assertTrue(ground["local"])
        self.assertEqual(ground["world"], "human")
        self.assertGreater(ground["defense_power"], 0)

    def test_shared_inventory_and_crafting_assets_remain_real_formation_materials(self):
        self.engine.execute(
            self.game_id, GrantItem(self.actor_id, "formation_plate", 2)
        )
        shared_crafting = next(
            row for row in self.engine.definitions.systems["crafting"]["materials"]
            if row["id"] == "spirit_bitter_bamboo"
        )
        crafting_asset_id = self._add_asset(
            "crafting_material", shared_crafting["id"],
            shared_crafting["name"],
            {
                "tier": shared_crafting["tier"],
                "quality_multiplier": 1.0,
                "material_value": shared_crafting["base_material_value"],
                "source": "shared-material-test",
            },
        )
        public = game_view(self.engine.get_game(self.game_id), {})[
            "formation_system"
        ]
        inventory_candidates = [
            row for row in public["materials"]
            if row.get("item_id") == "formation_plate"
        ]
        self.assertEqual(len(inventory_candidates), 2)
        shared_candidate = next(
            row for row in public["materials"]
            if row.get("asset_id") == crafting_asset_id
        )
        self.assertEqual(shared_candidate["source_kind"], "crafting_material")
        self.assertEqual(
            shared_candidate["definition_id"], "shared_spirit_bitter_bamboo"
        )

        saved = self.engine.save_formation(self.game_id, {
            "name": "行囊共用阵",
            "slots": [
                inventory_candidates[0]["id"],
                inventory_candidates[1]["id"],
                *([None] * 7),
            ],
            "activate": True,
        }).game
        item = next(
            row for row in saved["inventory"] if row["id"] == "formation_plate"
        )
        self.assertEqual(item["reserved"], 2)
        active = saved["formation_system"]["active"]
        self.assertTrue(all(
            row.get("item_id") == "formation_plate"
            for row in active["bindings"] if row
        ))
        returned = self.engine.deactivate_formation(self.game_id).game
        item = next(
            row for row in returned["inventory"] if row["id"] == "formation_plate"
        )
        self.assertEqual(item["reserved"], 0)
        self.assertEqual(item["available"], 2)


if __name__ == "__main__":
    unittest.main()
