from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cultivation_life.content_registry import ROOT_DEFINITIONS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.runtime import encode_rng


@pytest.fixture()
def intrigue_game(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(Path(__file__).parents[1], tmp_path / "saves")
    created = engine.create_game("议事测试", "supreme_metal", "dao", seed=24091)
    game = engine._load(created["id"])
    game.player.realm_index = 4
    game.player.layer = 3
    engine.store.save(game)
    engine.create_faction(created["id"], "衡议宗")
    return engine, created["id"]


def _sect_section(view: dict) -> dict:
    return next(row for row in view["intrigue_system"]["sections"] if row["kind"] == "sect")


def test_personality_authorities_and_roundtrip(intrigue_game: tuple[GameEngine, str]) -> None:
    engine, game_id = intrigue_game
    first = engine.get_game(game_id)
    section = _sect_section(first)
    assert first["intrigue_system"]["enabled"] is True
    assert section["control_authority"] is True
    assert section["decision_authority"] is True
    assert section["decision_threshold"] == 4
    assert section["members"][0]["primary"]

    persisted = engine._load(game_id)
    personality = engine._ensure_intrigue_personality(persisted, persisted.sects[persisted.player.faction_id].npcs[0])
    clone = type(persisted).from_dict(persisted.to_dict())
    assert clone.intrigue_state["npcs"]
    assert engine._ensure_intrigue_personality(clone, clone.sects[clone.player.faction_id].npcs[0]) == personality


def test_race_voter_list_includes_player_name_when_player_has_a_vote(
    intrigue_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = intrigue_game
    game = engine._load(game_id)
    game.player.world = "spirit"
    game.player.realm_index, game.player.layer = 8, 2
    game.player.race = "human"
    game.player.allegiance_race = "human"
    engine.store.save(game)

    shown = engine.get_game(game_id)
    race = next(row for row in shown["intrigue_system"]["sections"] if row["kind"] == "race")
    assert race["decision_authority"] is True
    player_row = next(row for row in race["members"] if row["id"] == "player")
    assert player_row["name"] == shown["player"]["name"]
    assert player_row["is_player"] is True
    assert player_row["decision_authority"] is True
    assert player_row["position"] == "种族议事成员"


def test_control_actions_have_consequences_and_prison_excludes_npc(intrigue_game: tuple[GameEngine, str]) -> None:
    engine, game_id = intrigue_game
    section = _sect_section(engine.get_game(game_id))
    member = section["members"][0]
    engine.intrigue_personnel_action(game_id, "sect", "appoint", member["id"], "affairs_elder")
    appointed = _sect_section(engine.get_game(game_id))
    assert next(row for row in appointed["positions"] if row["id"] == "affairs_elder")["holder_id"] == member["id"]

    engine.intrigue_personnel_action(game_id, "sect", "imprison", member["id"], years=8, reason="违抗掌门令")
    game = engine._load(game_id)
    assert engine._intrigue_is_imprisoned(game, member["id"])
    assert member["id"] not in [npc.id for npc in engine._war_side_members(game, "sect", game.player.faction_id, game.player.world)]
    section = _sect_section(engine.get_game(game_id))
    assert section["fear"] > 0 and section["unrest"] > 0
    engine.intrigue_personnel_action(game_id, "sect", "release", member["id"])
    assert not engine._intrigue_is_imprisoned(engine._load(game_id), member["id"])


def test_one_person_one_vote_and_defensive_guest(intrigue_game: tuple[GameEngine, str]) -> None:
    engine, game_id = intrigue_game
    result = engine.intrigue_propose_resolution(game_id, "sect", "investment", "", True)
    resolution = result["intrigue_system"]["resolutions"][0]
    voter_ids = [row["id"] for row in resolution["votes"]]
    assert len(voter_ids) == len(set(voter_ids))
    assert resolution["total"] == len(resolution["votes"])

    game = engine._load(game_id)
    own_id = game.player.faction_id
    target = next(sect for sect in game.sects.values() if sect.id != own_id and not sect.extinct and sect.world == game.player.world)
    guest_source = next(sect for sect in game.sects.values() if sect.id not in {own_id, target.id} and not sect.extinct and sect.world == game.player.world)
    guest = next(npc for npc in guest_source.npcs if npc.alive)
    target_record = engine._ensure_intrigue_faction(game, "sect", target.id)
    target_record["guests"].append({"npc_id": guest.id, "name": guest.name, "defense_required": True, "offense_opt_in": False})
    war = engine._start_war(game, "sect", own_id, target.id)
    assert guest.id in war["roster"]["defender"]
    assert guest.id not in war["roster"]["attacker"]


def test_controller_can_directly_invite_high_affinity_person_or_dao_friend_as_guest(
    intrigue_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = intrigue_game
    game = engine._load(game_id)
    friendly = SectNpc(
        "friendly_guest", "顾清衡", "散修", 3, 8, 260, 480,
        spirit_root="supreme_wood", path="dao", world=game.player.world, affinity=70,
    )
    friend = SectNpc(
        "dao_friend_guest", "苏照雪", "道友", 3, 6, 230, 470,
        spirit_root="supreme_water", path="dao", world=game.player.world, affinity=10,
    )
    game.notable_npcs[friendly.id] = friendly
    game.notable_npcs[friend.id] = friend
    game.player.dao_friends.append(engine._relationship_snapshot(
        friend.id, friend.name, friend.realm_index, friend.layer, "world",
        friend.age, friend.lifespan, True, None, friend.spirit_root,
        friend.cultivation_progress, friend.path, friend.race, friend.world,
        affinity=friend.affinity,
    ))
    game.rng_state = encode_rng(__import__("random").Random(1))
    engine.store.save(game)

    shown = engine.get_game(game_id)
    world_rows = {row["id"]: row for row in shown["world_npcs"]}
    assert world_rows[friendly.id]["can_invite_guest"] is True
    assert world_rows[friend.id]["can_invite_guest"] is True
    assert shown["dao_friends"][0]["can_invite_guest"] is True
    candidates = {row["id"]: row for row in _sect_section(shown)["guest_candidates"]}
    assert candidates[friendly.id]["relationship"] == "故交"
    assert candidates[friend.id]["relationship"] == "道友"

    invited = engine.intrigue_guest_action(game_id, "sect", "invite", friend.id)
    guest_ids = {row["npc_id"] for row in _sect_section(invited)["guests"]}
    assert friend.id in guest_ids
    assert next(row for row in invited["dao_friends"] if row["id"] == friend.id)["can_invite_guest"] is False


def test_disabled_dlc_freezes_state(intrigue_game: tuple[GameEngine, str], monkeypatch: pytest.MonkeyPatch) -> None:
    engine, game_id = intrigue_game
    game = engine._load(game_id)
    engine._public_intrigue_system(game)
    before = copy.deepcopy(game.intrigue_state)
    monkeypatch.setitem(WORLD_SYSTEMS["intrigue_dlc"], "enabled", False)
    assert engine._public_intrigue_system(game)["enabled"] is False
    assert engine._advance_intrigue_unit(game, __import__("random").Random(1)) == []
    assert game.intrigue_state == before


def test_founder_control_does_not_bypass_decision_realm(tmp_path: Path) -> None:
    engine = GameEngine(Path(__file__).parents[1], tmp_path / "saves")
    created = engine.create_game("凡俗掌门", "supreme_metal", "dao", seed=818)
    shown = engine.create_faction(created["id"], "凡心宗")
    section = _sect_section(shown)
    assert section["control_authority"] is True
    assert section["decision_authority"] is False
    with pytest.raises(ValueError, match="决策权"):
        engine.intrigue_propose_resolution(created["id"], "sect", "investment", "", True)


def test_top_seven_member_receives_office_without_decision_authority(
    intrigue_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = intrigue_game
    game = engine._load(game_id)
    sect = game.sects[game.player.faction_id]
    sect.founded_by_player = False
    sect.founder_player_id = None
    game.player.realm_index, game.player.layer = 3, 9
    for index, npc in enumerate(sect.npcs):
        npc.realm_index = 4 if index == 0 else 3 if index < 3 else 2
        npc.layer = 1 if index == 0 else max(1, 8 - index)
    game.intrigue_state = {}
    engine.store.save(game)

    section = _sect_section(engine.get_game(game_id))
    assert section["decision_authority"] is False
    assert section["player_power_rank"] <= 7
    assert section["player_office_id"] in {"enforcement_elder", "teaching_elder", "foreign_elder", "war_elder", "affairs_elder"}
    assert next(row for row in section["positions"] if row["id"] == section["player_office_id"])["holder_id"] == "player"


def test_filtered_disciple_recruitment_votes_then_lets_player_choose(
    intrigue_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = intrigue_game
    proposed = engine.intrigue_recruitment_action(game_id, "propose", {
        "spirit_root": "any", "realm_index": "any", "path": "any",
        "combat": "any", "gender": "any",
    })
    section = _sect_section(proposed)
    pending = section["disciple_recruitment"]["pending"]
    assert proposed["intrigue_system"]["resolutions"][0]["type"] == "disciple_recruitment"
    assert proposed["intrigue_system"]["resolutions"][0]["result"] == "passed"
    assert 0 <= len(pending["candidates"]) <= 5
    assert all(row["realm_index"] < section["decision_threshold"] for row in pending["candidates"])

    chosen = [row["id"] for row in pending["candidates"][:2]]
    before = len(section["members"])
    confirmed = engine.intrigue_recruitment_action(game_id, "confirm", candidate_ids=chosen)
    after = _sect_section(confirmed)
    assert len(after["members"]) == before + len(chosen)
    assert after["disciple_recruitment"]["pending"] is None
    assert set(chosen).issubset({row["id"] for row in after["members"]})


def test_disciple_filters_reject_decision_realm_and_enforce_strict_matches(
    intrigue_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = intrigue_game
    with pytest.raises(ValueError, match="决策权"):
        engine.intrigue_recruitment_action(game_id, "propose", {
            "spirit_root": "any", "realm_index": "4", "path": "any",
            "combat": "any", "gender": "any",
        })

    shown = engine.intrigue_recruitment_action(game_id, "propose", {
        "spirit_root": "heavenly", "realm_index": "3", "path": "ghost",
        "combat": "prodigy", "gender": "female",
    })
    pending = _sect_section(shown)["disciple_recruitment"]["pending"]
    assert len(pending["candidates"]) <= 5
    if not pending["candidates"]:
        assert "要求太苛刻" in pending["message"]
    for row in pending["candidates"]:
        assert row["realm_index"] == 3
        assert row["path"] == "ghost"
        assert row["gender"] == "female"
        assert row["combat_ratio"] >= 1.25
        assert ROOT_DEFINITIONS[row["spirit_root"]]["tier"] == "天灵根"
    closed = engine.intrigue_recruitment_action(game_id, "confirm", candidate_ids=[])
    assert _sect_section(closed)["disciple_recruitment"]["pending"] is None


def test_wanted_sentence_uses_real_faction_prison_and_limited_actions(intrigue_game: tuple[GameEngine, str]) -> None:
    engine, game_id = intrigue_game
    game = engine._load(game_id)
    faction_id = game.player.faction_id
    key = f"sect:{faction_id}"
    game.player.hostility[key] = 25.0
    text = engine._imprison_or_execute(game, key, __import__("random").Random(4), surrendered=True)
    assert "大牢" in text
    assert game.player.imprisonment["facility"] == "faction_prison"
    assert any(row["prisoner_id"] == "player" for row in engine._ensure_intrigue_faction(game, "sect", faction_id)["prison"])
    engine.store.save(game)
    before = int(game.player.imprisonment["remaining_years"])
    shown = engine.prison_action(game_id, "wait")
    if shown["imprisonment"]:
        assert shown["imprisonment"]["remaining_years"] == before - 1
    with pytest.raises(ValueError, match="不开放越狱"):
        engine.prison_action(game_id, "escape")
