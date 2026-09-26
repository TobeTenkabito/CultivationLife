import copy
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import CONTENT, GUIXU_TIDE_CONTENT, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, opportunity_required
from cultivation_life.system.crafting_system import make_crafting_material_instance, store_crafted_artifact
from cultivation_life.system.formation_system import ensure_formation_state

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup_game(tmp_path):
    engine = GameEngine(ROOT, tmp_path / "saves")
    game_id = engine.create_game("更新验证", "heavenly", "dao", 1340, preset_id="core")["id"]
    return engine, engine.store.load(game_id)


def test_all_worlds_are_base_and_all_extensions_load():
    maps = json.loads((ROOT / "content/maps.json").read_text(encoding="utf8"))
    assert len(maps["worlds"]) == 11
    assert all(row["status"] == "loaded" for row in CONTENT.extension_report)
    assert {d["world"] for d in GUIXU_TIDE_CONTENT["dungeons"]} == set(maps["worlds"])


def test_all_exchange_venues_are_accessible_and_clock_is_two_units(setup_game):
    engine, game = setup_game
    for world in engine.maps.worlds:
        assert not engine._exchange_location(world).get("min_realm_index", 0)
    engine._schedule_exchange(game, random.Random(1))
    location = game.exchange_state["location_id"]
    engine._advance_exchange_clock(game, random.Random(2))
    assert game.exchange_state["actions_until_open"] == 1
    engine._advance_exchange_clock(game, random.Random(3))
    assert game.exchange_state["status"] == "open"
    assert len(game.exchange_state["offers"]) == 3
    engine._schedule_exchange(game, random.Random(999))
    assert game.exchange_state["location_id"] == location


def prepare_exchange(engine, game):
    engine._schedule_exchange(game, random.Random(1))
    engine._open_exchange(game, random.Random(2))
    game.player.location_id = game.exchange_state["location_id"]
    game.exchange_state["alias"] = "青笠客"
    return game.exchange_state["offers"][0]


def test_exact_material_exchange_preserves_stones_and_prevents_replay(setup_game):
    engine, game = setup_game
    offer = prepare_exchange(engine, game)
    demand = offer["demands"][0]
    definition = engine._crafting_material_defs()[demand["definition_id"]]
    selected = []
    for _ in range(demand["quantity"]):
        material = make_crafting_material_instance(definition, random.Random(2), source="测试", origin_world="human")
        game.player.crafting_materials.append(material)
        selected.append({"id": material["id"], "quantity": 1})
    stones = engine._spirit_stones(game.player)
    engine.store.save(game)
    payload = {"offer_id": offer["id"], "materials": selected}
    shown = engine.exchange_action(game.id, "trade", payload)
    saved = engine.store.load(game.id)
    assert shown["exchange_system"]["offers"][0]["completed"]
    assert engine._spirit_stones(saved.player) == stones
    assert any(x["id"] == offer["reward"]["id"] for x in saved.player.crafting_materials)
    with pytest.raises(ValueError, match="结束"):
        engine.exchange_action(game.id, "trade", payload)


def test_exchange_rejects_currency_and_refusal_keeps_materials(setup_game):
    engine, game = setup_game
    offer = prepare_exchange(engine, game)
    definition = next(d for d in engine._crafting_material_defs().values() if d["id"] != offer["demands"][0]["definition_id"])
    material = make_crafting_material_instance(definition, random.Random(3), source="测试", origin_world="human")
    material["material_value"] = offer["demand_value"]
    game.player.crafting_materials.append(material)
    engine.store.save(game)
    with pytest.raises(ValueError, match="灵石"):
        engine.exchange_action(game.id, "trade", {"offer_id": offer["id"], "materials": [{"id": "spirit_stone", "quantity": 1}]})
    with patch("cultivation_life.system.exchange_system.decode_rng", return_value=random.Random(0)):
        shown = engine.exchange_action(game.id, "trade", {"offer_id": offer["id"], "materials": [{"id": material["id"], "quantity": 1}]})
    assert not shown["exchange_system"]["offers"][0]["completed"]
    saved = engine.store.load(game.id)
    assert any(x["id"] == material["id"] for x in saved.player.crafting_materials)
    assert saved.exchange_state["offers"][0]["substitution_attempted"]


def test_black_market_batches_assign_independent_ids_and_repair_legacy(setup_game):
    engine, game = setup_game
    game.auction_state = {"id": "batch", "status": "black_market", "world": "human", "location_id": game.player.location_id}
    add_item(game.player, "spirit_stone", 10**8)
    engine.store.save(game)
    shown = engine.search_black_market(game.id, "阵法材料")
    offer = shown["auction_system"]["black_market_results"][0]
    before = engine._spirit_stones(engine.store.load(game.id).player)
    engine.buy_black_market_item(game.id, offer["id"], 9)
    engine.buy_black_market_item(game.id, offer["id"], 2)
    saved = engine.store.load(game.id)
    materials = saved.player.formation_materials
    assert len(materials) == 11 and len({m["id"] for m in materials}) == 11
    assert engine._spirit_stones(saved.player) == before - 11 * offer["price"]
    saved.player.formation_materials.append(copy.deepcopy(materials[0]))
    original_id = materials[0]["id"]
    ensure_formation_state(saved.player)
    assert saved.player.formation_materials[0]["id"] == original_id
    assert len({m["id"] for m in saved.player.formation_materials}) == 12
    with pytest.raises(ValueError):
        engine.buy_black_market_item(game.id, offer["id"], -1)


def test_natal_cost_scales_with_base_not_buffs_or_world(setup_game):
    engine, game = setup_game
    artifact = {"id": "powerful", "name": "大乘剑", "quality_name": "精制", "mold_name": "剑", "actual_stats": {"combat_power": 3000000}, "combat_effects": [], "anchor_value": 1, "description": "test", "is_natal": False}
    store_crafted_artifact(game.player, artifact)
    engine._bind_crafted_natal_artifact(game, artifact)
    cost = engine._natal_refine_cost(1, game)
    assert cost == 100000
    game.player.world = "celestial"
    artifact["combat_effects"] = [{"player_stat_multipliers": {"might": 100}}]
    assert engine._natal_refine_cost(1, game) == cost
    assert engine._natal_refine_cost(2, game) == 2 * cost


def test_unbind_returns_materials_and_next_breakthrough_consumes_penalty(setup_game):
    engine, game = setup_game
    engine.natal_artifact_action(game.id, "bind", "starfall_blade")
    game = engine.store.load(game.id)
    game.natal_artifact.update(level=10, slots=["star_pattern_copper"])
    engine.store.save(game)
    engine.natal_artifact_action(game.id, "unbind")
    saved = engine.store.load(game.id)
    assert saved.player.natal_origin_penalty == .10
    assert {"starfall_blade", "star_pattern_copper"} <= {x.id for x in saved.player.inventory}
    normal = copy.deepcopy(saved.player)
    normal.natal_origin_penalty = 0
    assert engine._breakthrough_chance(saved.player, False)["final"] == pytest.approx(max(.01, engine._breakthrough_chance(normal, False)["final"] - .1))
    saved.player.natal_origin_penalty = 100
    assert engine._breakthrough_chance(saved.player, True)["final"] == .01
    saved.player.natal_origin_penalty = .1
    saved.player.awaiting_minor_breakthrough = True
    saved.player.opportunity = opportunity_required(saved.player)
    engine.store.save(saved)
    engine.breakthrough(game.id)
    assert engine.store.load(game.id).player.natal_origin_penalty == 0


def test_player_artifact_enters_ranking_without_mutating_divine_definitions(setup_game):
    engine, game = setup_game
    original = copy.deepcopy(game.tianji_state["artifacts"])
    power = max(a["base_combat_power"] for a in original) + 100
    artifact = {"id": "ranked-player", "name": "自炼至宝", "quality_name": "传世", "mold_name": "剑", "actual_stats": {"combat_power": power}, "combat_effects": [], "anchor_value": 1, "description": "test", "is_natal": False}
    store_crafted_artifact(game.player, artifact)
    game.tianji_state["knowledge"] = {a["id"]: 4 for a in original}
    public = engine._public_tianji(game)
    assert public["artifacts"][0]["id"] == artifact["id"]
    assert len(public["artifacts"]) == 100
    assert len(public["targets"]) == 100  # Displaced divine recipes remain usable.
    assert game.tianji_state["artifacts"] == original
    assert {m["world"] for m in game.tianji_state["materials"]} == set(engine.maps.worlds)


def test_defensive_beast_rewards_have_no_sha_but_active_hunting_does(setup_game):
    engine, game = setup_game
    before = game.player.sha_qi
    engine._apply_combat_action_rewards(game, "hunt_beast", "killed", "", random.Random(1), player_defending=True)
    assert game.player.sha_qi == before
    engine._apply_combat_action_rewards(game, "hunt_beast", "killed", "", random.Random(1))
    assert game.player.sha_qi > before


@pytest.mark.parametrize("path", ["dao", "monster"])
def test_defensive_cultivator_kill_never_adds_karma_or_sha(setup_game, path):
    engine, game = setup_game
    game.player.path = path
    before = game.player.karma, game.player.sha_qi
    target = {"target_name": "来袭修士", "target_power": 1, "target_realm_index": 1,
              "target_layer": 1, "combat_type": "cultivator", "action": "slay",
              "player_defending": True, "kill_pursuit_threshold": 0, "pursuit_chance_bonus": 1}
    result, _ = engine._combat(game, target, True, random.Random(1))
    assert result == "killed"
    assert (game.player.karma, game.player.sha_qi) == before
    assert game.last_combat_report["player_defending"]


def test_plain_natal_artifact_can_join_dynamic_ranking(setup_game):
    engine, game = setup_game
    game.natal_artifact = {"item_id": "starfall_blade", "name": "温养千年的坠星刃",
                           "level": 5000, "experience": 0, "slots": [], "slot_rule_version": 2}
    engine._ensure_natal_artifact(game)
    public = engine._public_tianji(game)
    assert any(row["id"] == "natal:starfall_blade" for row in public["artifacts"])


def test_same_realm_threat_requires_live_team_and_combat_is_defensive(setup_game):
    engine, game = setup_game
    dungeon = next(d for d in GUIXU_TIDE_CONTENT["dungeons"] if d["world"] == "human")
    session = {"layer_id": "outer", "pending_threat": None, "remaining_days": 40}
    actor = {"actor_id": "a", "name": "索宝者", "status": "active", "layer_id": "outer", "realm_index": 3, "layer": 9, "power": 100}
    cycle = {"phase": "open", "roster": [actor]}
    treasure = ({"pool_entry_id": "test"}, {"name": "宝物", "value": 10})
    with patch.object(engine, "_guixu_transferable_player_entries", return_value=[treasure]), patch.object(engine, "_guixu_settings", return_value={"npc_threat_chance_per_action": 1}):
        engine._maybe_guixu_npc_threat(game, dungeon, cycle, session, random.Random(1))
        assert session["pending_threat"] is None
        actor["team_id"] = "team"
        cycle["roster"].append(dict(actor, actor_id="b", name="同伴"))
        engine._maybe_guixu_npc_threat(game, dungeon, cycle, session, random.Random(1))
        assert session["pending_threat"]
    with patch.object(engine, "_combat", return_value=("victory", "")) as combat, patch.object(engine, "_consume_guixu_days"):
        engine._guixu_fight(game, dungeon, cycle, session, actor, random.Random(1), player_defending=True)
    target = combat.call_args.args[1]
    assert target["player_defending"] and target["target_power"] == 200
    assert len(target["members"]) == 2
