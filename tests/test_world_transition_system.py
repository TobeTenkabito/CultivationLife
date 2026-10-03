import ast
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.content_registry import REALMS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.world_transition_system import (
    TransitionDirection, TransitionMode, WorldTransitionRequest, classify_transition,
    plan_world_transition, validate_transition_content,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine = GameEngine(ROOT, tmp_path / "saves")
    gid = engine.create_game("界壁验收", "supreme_metal", "dao", 1410)["id"]
    return engine, engine.store.load(gid)


@pytest.mark.parametrize("source,destination,direction", [
    ("human", "demon", "lateral"), ("human", "spirit", "ascend"),
    ("spirit", "human", "descend"), ("spirit", "true_demon", "lateral"),
    ("nether", "monster_realm", "descend"),
])
def test_direction_depends_only_on_tier(source, destination, direction):
    assert classify_transition(WORLD_SYSTEMS["world_profiles"], source, destination).value == direction


DESCENTS = [row for row in WORLD_SYSTEMS["world_transition_routes"] if row.get("generic_cross_world")]


@pytest.mark.parametrize("route", DESCENTS, ids=lambda r: r["id"])
def test_every_reversible_route_preserves_resources_ties_and_canonical_seal(setup, route):
    engine, game = setup
    player = game.player
    player.world = route["source"]
    player.location_id = engine.maps.default_location(player.world)
    rank = 9 if WORLD_SYSTEMS["world_profiles"][player.world]["tier"] == 3 else 8
    player.realm_index, player.layer = rank, REALMS[rank].layers
    player.lifespan, player.next_tribulation_age = 98765, player.age + 47
    player.immortal_power_converted = True
    player.hp, player.mp = max_hp(player) * .41, max_mp(player) * .63
    player.dao_friends = [{"id": "friend", "world": player.world, "alive": True}]
    original_friends = copy.deepcopy(player.dao_friends)
    before = copy.deepcopy(game.to_dict())
    plan = engine._plan_world_transition(game, route["destination"], "sealed_descent")
    assert game.to_dict() == before, "Planning must be pure"
    engine._apply_world_transition(game, plan)
    assert player.sealed_cultivation["return_world"] == route["source"]
    ceiling = WORLD_SYSTEMS["world_profiles"][route["destination"]]["cultivation_ceiling"]
    assert (player.realm_index, player.layer) == (ceiling["realm_index"], ceiling["layer"])
    assert player.hp / max_hp(player) == pytest.approx(.41)
    assert player.mp / max_mp(player) == pytest.approx(.63)
    assert player.dao_friends == original_friends
    assert game.to_dict()["player"]["dao_friends"] == before["player"]["dao_friends"]
    assert game.to_dict()["relationship_npcs"] == before["relationship_npcs"]
    player.age += 10
    player.hp, player.mp = max_hp(player) * .22, max_mp(player) * .19
    plan = engine._plan_world_transition(game, route["source"], "sealed_return")
    engine._apply_world_transition(game, plan)
    assert player.sealed_cultivation is None and player.realm_index == rank
    assert player.lifespan == 98765 and player.next_tribulation_age == player.age + 47
    assert player.hp / max_hp(player) == pytest.approx(.22)
    assert player.mp / max_mp(player) == pytest.approx(.19)
    assert player.dao_friends == original_friends
    assert game.to_dict()["player"]["dao_friends"] == before["player"]["dao_friends"]


def test_oldest_seal_returns_to_spirit_not_unrelated_hell(setup):
    engine, game = setup
    game.player.realm_index, game.player.layer = 5, 3
    game.player.sealed_cultivation = {"realm_index": 8, "layer": 9, "lifespan": 12345}
    engine._plan_world_transition(game, "spirit", "sealed_return")
    with pytest.raises(ValueError):
        engine._plan_world_transition(game, "hell", "sealed_return")


def test_public_route_cannot_bypass_progression_or_open_disabled_world(setup):
    engine, game = setup
    from cultivation_life.engine.actions.world_travel import plan_public_crossing
    for destination in ("spirit", "demon", "reincarnation", "celestial"):
        snapshot = copy.deepcopy(game.to_dict())
        with pytest.raises(ValueError):
            plan_public_crossing(game, destination, engine.maps)
        assert game.to_dict() == snapshot


def test_passage_same_tier_keeps_social_ties_and_native_rank(setup):
    engine, game = setup
    game.player.world, game.player.realm_index, game.player.layer = "spirit", 8, 9
    game.player.faction_id = "tianjian"
    game.player.puppets = [{"id": "kept"}]
    plan = engine._plan_world_transition(game, "true_demon", "passage")
    assert plan.direction == TransitionDirection.LATERAL
    engine._apply_world_transition(game, plan)
    assert game.player.faction_id == "tianjian" and game.player.puppets
    assert game.player.sealed_cultivation is None


def test_stale_plan_rejected_before_auction_or_cleanup(setup):
    engine, game = setup
    plan = engine._plan_world_transition(game, "spirit")
    game.player.realm_index += 1
    before = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError, match="失效"):
        engine._apply_world_transition(game, plan)
    assert game.to_dict() == before


def test_content_rejects_invalid_routes_and_profile_tiers():
    profiles = copy.deepcopy(WORLD_SYSTEMS["world_profiles"])
    routes = copy.deepcopy(WORLD_SYSTEMS["world_transition_routes"])
    profiles["human"]["tier"] = True
    with pytest.raises(ValueError):
        validate_transition_content(profiles, routes, REALMS)
    profiles = WORLD_SYSTEMS["world_profiles"]
    with pytest.raises(ValueError):
        validate_transition_content(profiles, routes + routes[:1], REALMS)
    routes[0]["destination"] = "celestial"
    with pytest.raises(ValueError):
        validate_transition_content(profiles, routes, REALMS)


def test_only_transition_commit_initialization_and_session_preparation_write_player_world():
    allowed = {"system/world_transition_system.py", "engine/orchestration/session.py", "engine/persistence/character.py"}
    violations = []
    for path in (ROOT / "cultivation_life").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) and node.attr == "world":
                base = ast.unparse(node.value)
                if base == "player" or base.endswith(".player"):
                    relative = path.relative_to(ROOT / "cultivation_life").as_posix()
                    if relative not in allowed:
                        violations.append(f"{relative}:{node.lineno}")
    assert not violations, violations
