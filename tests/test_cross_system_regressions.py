from __future__ import annotations

import random
import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.system.possession_system import enter_host_body, leave_host_body
from cultivation_life.rules import add_item, opportunity_required


@pytest.fixture()
def engine_game(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(Path(__file__).parents[1], tmp_path / "saves")
    created = engine.create_game("归墟", "supreme_metal", "dao", seed=24680)
    return engine, created["id"]


def test_successful_prison_smuggling_clears_all_non_invited_lower_world_ties(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    player = game.player
    player.realm_index, player.layer, player.world = 5, 1, "human"
    player.imprisonment = {"key": "sect:tianjian", "remaining_years": 12, "name": "天剑大牢"}
    player.concubines = [{"id": "old-concubine", "name": "旧妾", "alive": True, "world": "human"}]
    player.concubine_status = {"owner_id": "old-owner", "owner_world": "human"}
    player.master = {"id": "old-master", "name": "旧师", "alive": True, "world": "human"}
    player.dao_friends = [{"id": "old-friend", "name": "旧友", "alive": True, "world": "human"}]
    player.prisoners = [{"id": "captive", "name": "俘虏"}]
    player.puppets = [{"id": "puppet", "name": "傀儡"}]
    player.faction_contribution = 99

    engine._effect({"type": "enter_spirit_realm"}, game, {"id": "TEST"}, random.Random(1))

    assert player.world == "spirit"
    assert player.imprisonment is None
    assert player.concubines == [] and player.concubine_status is None
    assert player.master is None and player.dao_friends == []
    assert player.prisoners == [] and player.puppets == []
    assert player.faction_contribution == 0


def test_prison_blocks_normal_breakthrough_but_not_human_smuggling(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    game.player.realm_index, game.player.layer = 5, 1
    game.player.opportunity = opportunity_required(game.player)
    game.player.awaiting_minor_breakthrough = True
    game.player.imprisonment = {"key": "sect:tianjian", "remaining_years": 3, "name": "天剑大牢"}
    engine.store.save(game)

    with pytest.raises(ValueError, match="牢狱"):
        engine.breakthrough(game_id)
    shown = engine.begin_spirit_crossing(game_id)
    assert shown["pending_event"]["id"] == "EVT_SPIRIT_CROSSING_001"


def test_possession_uses_host_gender_and_restores_every_body_progress_field() -> None:
    from cultivation_life.models import Player

    player = Player("孤魂", "mutated_yin", path="ghost")
    player.realm_index = 1
    player.awaiting_body_breakthrough = True
    player.body_breakthrough_pity = {"body:3": 2}
    player.known_transformations = ["wolf"]
    player.transformation_mastery = {"wolf": {"level": 4}}
    player.transformation_loadouts = {"main": {"forms": ["wolf"]}}
    enter_host_body(player, {
        "id": "host", "name": "女宿主", "gender": "female", "race": "human",
        "realm_index": 1, "layer": 1, "age": 30, "lifespan": 100,
    })
    assert player.gender == "female"
    assert player.awaiting_body_breakthrough is False
    assert player.known_transformations == []
    leave_host_body(player)
    assert player.gender == "male"
    assert player.awaiting_body_breakthrough is True
    assert player.body_breakthrough_pity == {"body:3": 2}
    assert player.known_transformations == ["wolf"]
    assert player.transformation_mastery["wolf"]["level"] == 4


def test_field_reclaim_is_instant_and_does_not_advance_any_time_clock(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    game.player.realm_index = 3
    add_item(game.player, "spirit_stone", 100_000)
    age = game.player.age
    unit = game.diplomacy_unit
    engine.store.save(game)

    shown = engine.reclaim_spirit_field(game_id)
    assert shown["player"]["age"] == age
    assert engine._load(game_id).diplomacy_unit == unit
    assert shown["spirit_field"]["reclaimed_qing"] == 1


def test_map_travel_advances_every_action_unit_system(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    game.player.realm_index = 3
    engine.store.save(game)
    public_map = engine.get_game(game_id)["map"]
    destination = next(
        row["id"] for row in public_map["locations"]
        if not row["current"] and row["travel_status"] != "blocked"
    )
    with (
        patch.object(engine, "_advance_world_year", return_value=True),
        patch.object(engine, "_advance_diplomacy_unit", return_value=[]) as diplomacy,
        patch.object(engine, "_advance_heavenly_court_unit", return_value=[]) as court,
        patch.object(engine, "_advance_intrigue_unit", return_value=[]) as intrigue,
    ):
        engine.travel_map(game_id, destination)
    assert diplomacy.call_count >= 1
    assert court.call_count == diplomacy.call_count
    assert intrigue.call_count == diplomacy.call_count


def test_snapshot_only_concubine_uses_normal_lifespan_update(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    game.player.concubines = [{
        "id": "event-concubine", "npc_id": "event-concubine", "name": "旧梦",
        "source": "event", "age": 89, "lifespan": 90, "alive": True,
        "realm_index": 0, "layer": 1, "spirit_root": "none", "path": "dao",
        "race": "human", "world": "human",
    }]
    engine._annual_relationship_update(game, random.Random(3))
    assert game.player.concubines[0]["age"] == 90
    assert game.player.concubines[0]["alive"] is False
    assert "寿元耗尽" in game.player.concubines[0]["death_reason"]


def test_other_world_family_and_guest_invitation_are_isolated(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    family = copy.deepcopy(game.sects["tianjian"])
    family.id, family.name, family.world = "family-test", "归墟家", "human"
    family.founded_by_player = True
    family.founder_player_id = game.id
    game.family = family
    game.player.world = "spirit"
    game.intrigue_state["pending_guest_invitation"] = {
        "kind": "sect", "faction_id": "tianjian", "faction_name": "天剑宗",
        "title": "客卿长老", "world": "human",
    }
    engine.store.save(game)

    shown = engine.get_game(game_id)
    assert shown["family"]["same_world"] is False
    assert shown["family"]["has_voice"] is False
    assert shown["family"]["roster"] == []
    assert shown["intrigue_system"]["pending_guest_invitation"] is None
    with pytest.raises(ValueError, match="其他界面"):
        engine.intrigue_guest_action(game_id, "", "accept_invitation")
    assert engine._load(game_id).intrigue_state["pending_guest_invitation"] is None


def test_arranged_founded_sect_handover_can_trigger_founder_return(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    sect = game.sects["tianjian"]
    sect.founded_by_player = True
    sect.founder_player_id = game.id
    game.player.faction_id = sect.id
    engine.store.save(game)

    engine.arrange_faction_succession(game_id)
    game = engine._load(game_id)
    engine._prepare_permanent_world_transition(game)
    plan = game.intrigue_state["succession_plans"][sect.id]
    assert plan["eligible_return"] is True
    assert game.sects[sect.id].founded_by_player is False
    assert game.player.faction_id is None

    class AlwaysFind:
        @staticmethod
        def random() -> float:
            return 0.0

    assert engine._maybe_founder_return_event(game, AlwaysFind()) is True
    assert game.pending_event and game.pending_event["id"] == "EVT_FOUNDER_RETURN_001"
    engine.store.save(game)
    restored = engine.choose(game_id, "return")
    assert restored["faction"]["id"] == sect.id
    assert restored["faction"]["founded_by_player"] is True


def test_market_lock_endpoint_remains_backend_authoritative(
    engine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = engine_game
    game = engine._load(game_id)
    game.player.realm_index = 2
    engine._ensure_market(game, random.Random(2))
    engine.store.save(game)
    offer_id = engine.get_game(game_id)["market"]["offers"][0]["id"]
    shown = engine.toggle_market_offer_lock(game_id, offer_id)
    assert next(row for row in shown["market"]["offers"] if row["id"] == offer_id)["locked"] is True
