from __future__ import annotations

import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.system.crafting_system import active_crafted_artifacts


@pytest.fixture()
def tianji_game(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(Path(__file__).parents[1], tmp_path / "saves")
    created = engine.create_game("神机试锋", "supreme_metal", "dao", seed=86420)
    return engine, created["id"]


def test_generation_is_exact_sorted_deterministic_and_base_world_only(tmp_path: Path) -> None:
    first = GameEngine(Path(__file__).parents[1], tmp_path / "first")
    second = GameEngine(Path(__file__).parents[1], tmp_path / "second")
    first_id = first.create_game("甲", "supreme_metal", "dao", seed=99117)["id"]
    second_id = second.create_game("乙", "supreme_metal", "dao", seed=99117)["id"]
    a = first.store.load(first_id).tianji_state
    b = second.store.load(second_id).tianji_state
    assert len(a["artifacts"]) == 100
    assert len(a["materials"]) == 48
    assert len({row["name"] for row in a["artifacts"]}) == 100
    assert len({row["name"] for row in a["materials"]}) == 48
    assert [row["base_combat_power"] for row in a["artifacts"]] == sorted(
        (row["base_combat_power"] for row in a["artifacts"]), reverse=True,
    )
    assert a["artifacts"] == b["artifacts"]
    assert a["materials"] == b["materials"]
    assert {row["origin_world"] for row in a["artifacts"]} <= {
        "human", "demon", "spirit", "true_demon", "hell", "celestial", "asura",
    }


def test_generated_definitions_freeze_and_public_redaction(tianji_game: tuple[GameEngine, str]) -> None:
    engine, game_id = tianji_game
    game = engine.store.load(game_id)
    frozen = copy.deepcopy(game.tianji_state["artifacts"])
    public = engine.get_game(game_id)["tianji_artifacts"]
    assert len(public["artifacts"]) == 100
    assert all(row["name"] == "???" and row["effects"] is None and row["recipe"] is None for row in public["artifacts"])
    engine.get_game(game_id)
    assert engine.store.load(game_id).tianji_state["artifacts"] == frozen


def _grant_exact_recipe(engine: GameEngine, game_id: str, artifact: dict) -> dict:
    game = engine.store.load(game_id)
    game.tianji_state["knowledge"][artifact["id"]] = 4
    game.player.realm_index = 8
    game.player.layer = 9
    game.player.world = "spirit"
    definitions = {row["id"]: row for row in game.tianji_state["materials"]}
    instance_ids = []
    for material_id in artifact["recipe"]:
        instance = engine._tianji_material_instance(
            game, definitions[material_id], random.Random(material_id), "测试真方",
        )
        game.player.crafting_materials.append(instance)
        instance_ids.append(instance["id"])
    engine.store.save(game)
    return {
        "target_artifact_id": artifact["id"], "mold_id": artifact["mold_id"],
        "primary_id": instance_ids[0], "secondary_a_id": instance_ids[1],
        "secondary_b_id": instance_ids[2], "quench_id": instance_ids[3],
        "forge_kind": "true_body",
    }


def test_target_forging_true_body_and_single_active_slot(tianji_game: tuple[GameEngine, str]) -> None:
    engine, game_id = tianji_game
    game = engine.store.load(game_id)
    artifact = next(row for row in game.tianji_state["artifacts"] if row["rank"] > 40)
    payload = _grant_exact_recipe(engine, game_id, artifact)
    preview = engine.preview_tianji_forge(game_id, payload)
    assert preview["recipe_closeness"] == 1.0
    assert preview["replica_ratio"] == 1.0
    engine.forge_tianji_artifact(game_id, payload)
    engine.tianji_action(game_id, "activate", artifact["id"])
    game = engine.store.load(game_id)
    instance = next(row for row in game.player.crafted_artifacts if row.get("tianji", {}).get("definition_id") == artifact["id"])
    assert instance["actual_stats"]["combat_power"] == artifact["base_combat_power"]
    assert game.tianji_state["true_body_states"][artifact["id"]]["status"] == "player"
    assert [row["id"] for row in active_crafted_artifacts(game.player) if row.get("tianji")] == [instance["id"]]


def test_wrong_mold_never_consumes_materials(tianji_game: tuple[GameEngine, str]) -> None:
    engine, game_id = tianji_game
    game = engine.store.load(game_id)
    artifact = next(row for row in game.tianji_state["artifacts"] if row["rank"] > 40)
    payload = _grant_exact_recipe(engine, game_id, artifact)
    payload["mold_id"] = next(key for key in engine._crafting_molds() if key != artifact["mold_id"])
    before = len(engine.store.load(game_id).player.crafting_materials)
    with pytest.raises(ValueError, match="胎模错误"):
        engine.forge_tianji_artifact(game_id, payload)
    assert len(engine.store.load(game_id).player.crafting_materials) == before


def test_npc_holder_combat_injection_and_drop(tianji_game: tuple[GameEngine, str]) -> None:
    engine, game_id = tianji_game
    game = engine.store.load(game_id)
    assert game.tianji_state["holders"]
    artifact_id, holder = next(iter(game.tianji_state["holders"].items()))
    target = {"npc_id": holder["npc_id"], "target_power": 1_000.0, "members": []}
    engine._inject_tianji_npc_artifacts(game, target)
    assert target["target_power"] > 1_000
    assert game.tianji_state["knowledge"][artifact_id] >= 2
    text = engine._tianji_handle_npc_kill(game, holder["npc_id"])
    assert "天工神机" in text
    assert artifact_id not in game.tianji_state["holders"]
    assert any(row.get("tianji", {}).get("definition_id") == artifact_id for row in game.player.crafted_artifacts)
