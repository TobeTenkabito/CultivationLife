from __future__ import annotations

import copy
import random
from pathlib import Path

import pytest

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.models import Player
from cultivation_life.rules import assign_technique, max_hp, max_mp, opportunity_multiplier, opportunity_required


@pytest.fixture()
def concubine_game(tmp_path: Path) -> tuple[GameEngine, str]:
    engine = GameEngine(Path(__file__).parents[1], tmp_path / "saves")
    created = engine.create_game("绛雪", "supreme_fire", "dao", seed=91371, gender="female")
    return engine, created["id"]


def test_gender_creation_and_legacy_defaults(concubine_game: tuple[GameEngine, str]) -> None:
    engine, game_id = concubine_game
    view = engine.get_game(game_id)
    assert view["player"]["gender"] == "female"
    assert view["player"]["gender_name"] == "女"
    assert all(npc["gender"] in {"male", "female"} for npc in view["world_npcs"])

    legacy = Player("旧档", "supreme_metal").to_dict()
    legacy.pop("gender")
    legacy.pop("concubines")
    legacy.pop("concubine_status")
    legacy.pop("concubine_breakthrough_bonus")
    legacy.pop("concubine_rejection_aftermath")
    legacy.pop("concubine_escape_reputation")
    loaded = Player.from_dict(legacy)
    assert loaded.gender == "male"
    assert loaded.concubines == []
    assert loaded.concubine_rejection_aftermath == []
    assert loaded.concubine_escape_reputation == 0


def test_recruitment_obeys_gender_and_realm_and_has_no_capacity(concubine_game: tuple[GameEngine, str]) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    game.player.realm_index = 3
    game.player.layer = 5
    women = list(game.world_npcs.values())[:3]
    for index, npc in enumerate(women):
        npc.gender = "female"
        npc.realm_index = 1
        npc.layer = 1
        npc.affinity = 100
        npc.name = f"女修{index}"
    stronger = list(game.world_npcs.values())[3]
    stronger.gender = "female"
    stronger.realm_index = 4
    stronger.layer = 1
    engine.store.save(game)

    for npc in women:
        engine.manage_concubine(game_id, npc.id, "recruit")
    assert len(engine.get_game(game_id)["concubine_system"]["concubines"]) == 3
    with pytest.raises(ValueError, match="必定拒绝"):
        engine.manage_concubine(game_id, stronger.id, "recruit")


def test_captive_cauldron_hehuan_cap_cooldown_and_next_attempt_consumption(
    concubine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    game.player.realm_index = 2
    game.player.layer = 1
    game.player.prisoners.extend([
        {"id":"c1","name":"青萝","gender":"female","realm_index":1,"layer":1,"combat_power":20,"path":"dao"},
        {"id":"c2","name":"红药","gender":"female","realm_index":1,"layer":1,"combat_power":20,"path":"dao"},
    ])
    assign_technique(game.player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_HEHUAN_SECRET"]), "main")
    game.player.hp = 1
    game.player.mp = 0
    engine.store.save(game)
    engine.manage_concubine(game_id, "c1", "recruit")
    engine.manage_concubine(game_id, "c2", "recruit")
    first = engine.manage_concubine(game_id, "c1", "cauldron")
    assert first["player"]["hp"] > 1 and first["player"]["mp"] > 0
    assert first["concubine_system"]["cauldron_breakthrough_bonus"] == pytest.approx(0.01)
    with pytest.raises(ValueError, match="本行动单位"):
        engine.manage_concubine(game_id, "c1", "cauldron")
    second = engine.manage_concubine(game_id, "c2", "cauldron")
    assert second["concubine_system"]["cauldron_breakthrough_bonus"] == pytest.approx(0.02)

    game = engine._load(game_id)
    game.player.opportunity = opportunity_required(game.player)
    game.player.awaiting_minor_breakthrough = True
    engine.store.save(game)
    before = engine._breakthrough_chance(game.player, False)
    assert before["concubine_base_bonus"] == pytest.approx(0.02)
    engine.breakthrough(game_id)
    assert engine._load(game_id).player.concubine_breakthrough_bonus == 0


def test_being_concubine_reduces_efficiency_drains_opportunity_and_adds_base_chance(
    concubine_game: tuple[GameEngine, str],
) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    assign_technique(game.player, copy.deepcopy(TECHNIQUE_CATALOG["TECH_COMMON_QI"]), "main")
    free_efficiency = opportunity_multiplier(game.player)
    game.player.realm_index = 1
    game.player.layer = 1
    game.player.opportunity = 100
    game.player.concubine_status = {
        "owner_id":"owner","owner_name":"上修","owner_realm_index":3,"owner_layer":1,
        "owner_realm_name":"结丹初期","owner_world":"human",
    }
    assert opportunity_multiplier(game.player) == pytest.approx(free_efficiency * 0.8)
    chance = engine._breakthrough_chance(game.player, False)
    assert chance["concubine_base_bonus"] == pytest.approx(0.02)
    drained = engine._advance_concubine_status(game, 1)
    assert drained > 0
    assert game.player.opportunity == pytest.approx(100 - drained)


class _AlwaysTrigger(random.Random):
    def random(self) -> float:
        return 0.0

    def choice(self, seq):
        return seq[0]


def test_female_low_realm_receives_in_game_proposal_event(concubine_game: tuple[GameEngine, str]) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    owner = next(iter(game.world_npcs.values()))
    owner.gender = "male"
    owner.realm_index = 3
    owner.layer = 1
    owner.world = game.player.world
    game.player.realm_index = 1
    game.player.layer = 1
    assert engine._maybe_concubine_proposal(game, _AlwaysTrigger())
    assert game.pending_event["id"] == "SYS_CONCUBINE_PROPOSAL"
    proposed_owner_id = game.pending_event["runtime"]["owner_id"]
    engine.store.save(game)
    accepted = engine.choose(game_id, "accept")
    assert accepted["concubine_system"]["status"]["owner_id"] == proposed_owner_id
    assert accepted["concubine_system"]["opportunity_efficiency_multiplier"] == pytest.approx(0.8)


def test_mortal_proposal_survives_reload_and_can_be_chosen(
    concubine_game: tuple[GameEngine, str],
) -> None:
    """Regression: realm compatibility migration used to discard this manual event."""
    engine, game_id = concubine_game
    game = engine._load(game_id)
    owner = next(iter(game.world_npcs.values()))
    owner.gender = "male"
    owner.realm_index = 2
    owner.world = game.player.world
    game.player.realm_index = 0
    assert engine._maybe_concubine_proposal(game, _AlwaysTrigger())
    engine.store.save(game)

    reloaded = engine.get_game(game_id)
    assert reloaded["pending_event"]["id"] == "SYS_CONCUBINE_PROPOSAL"
    refused = engine.choose(game_id, "refuse")
    assert refused["pending_event"] is None
    assert len(refused["concubine_system"]["rejection_aftermath"]) == 1


def test_rejected_suitor_only_has_two_units_to_take_revenge(
    concubine_game: tuple[GameEngine, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    owner = next(iter(game.world_npcs.values()))
    owner.gender = "male"
    owner.realm_index = 3
    owner.world = game.player.world
    runtime = {
        "owner_id": owner.id, "owner_name": owner.name,
        "owner_realm_index": owner.realm_index, "owner_layer": owner.layer,
        "owner_realm_name": engine._npc_realm_name(owner), "owner_world": owner.world,
    }
    engine._resolve_concubine_proposal(game, {"runtime": runtime}, False)
    declined = game.diplomacy_unit
    monkeypatch.setattr(engine, "_proposal_revenge_chance", lambda _game, _owner: 0.0)

    game.diplomacy_unit += 1
    assert not engine._advance_concubine_aftermath(game, _AlwaysTrigger())
    assert game.player.concubine_rejection_aftermath
    game.diplomacy_unit += 1
    assert not engine._advance_concubine_aftermath(game, _AlwaysTrigger())
    assert not game.player.concubine_rejection_aftermath
    game.diplomacy_unit = declined + 10
    assert not engine._advance_concubine_aftermath(game, _AlwaysTrigger())


def test_intrigue_personality_changes_revenge_probability(
    concubine_game: tuple[GameEngine, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    owner = next(iter(game.world_npcs.values()))
    owner.affinity = 0
    monkeypatch.setattr(engine, "_intrigue_enabled", lambda: True)
    game.intrigue_state = {"npcs": {owner.id: {"primary": "warlike", "secondary": None}}}
    warlike = engine._proposal_revenge_chance(game, owner)
    game.intrigue_state["npcs"][owner.id] = {"primary": "generous", "secondary": None}
    generous = engine._proposal_revenge_chance(game, owner)
    assert warlike > generous

    monkeypatch.setattr(engine, "_intrigue_enabled", lambda: False)
    assert engine._proposal_revenge_chance(game, owner) == pytest.approx(0.30)


def test_escape_success_grants_reputation_and_failure_angers_owner(
    concubine_game: tuple[GameEngine, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    owner = next(iter(game.world_npcs.values()))
    owner.gender = "male"
    runtime = {
        "owner_id": owner.id, "owner_name": owner.name,
        "owner_realm_index": owner.realm_index, "owner_layer": owner.layer,
        "owner_realm_name": engine._npc_realm_name(owner), "owner_world": owner.world,
    }
    engine._set_concubine_status(game, runtime)
    monkeypatch.setattr(engine, "_escape_chance", lambda *_args: 0.0)
    result, _ = engine._resolve_concubine_escape(game, {"runtime": runtime}, "covert", _AlwaysTrigger())
    assert result == "escape_failed"
    assert game.player.concubine_status["angered_until_unit"] == game.diplomacy_unit + 2
    assert game.player.concubine_status["failed_escape_count"] == 1

    monkeypatch.setattr(engine, "_escape_chance", lambda *_args: 1.0)
    result, _ = engine._resolve_concubine_escape(game, {"runtime": runtime}, "covert", _AlwaysTrigger())
    assert result == "escaped"
    assert game.player.concubine_status is None
    assert game.player.concubine_escape_reputation == 1
    assert engine._public_concubine_system(game)["future_proposal_multiplier"] == pytest.approx(0.2)


def test_depending_and_requesting_resources_from_owner(
    concubine_game: tuple[GameEngine, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, game_id = concubine_game
    game = engine._load(game_id)
    owner = next(iter(game.world_npcs.values()))
    owner.gender = "male"
    owner.realm_index = 3
    owner.world = game.player.world
    engine._set_concubine_status(game, {
        "owner_id": owner.id, "owner_name": owner.name,
        "owner_realm_index": owner.realm_index, "owner_layer": owner.layer,
        "owner_realm_name": engine._npc_realm_name(owner), "owner_world": owner.world,
    })
    engine.store.save(game)
    depended = engine.manage_concubine_status(game_id, "depend")
    assert depended["concubine_system"]["status"]["dependent"] is True

    monkeypatch.setattr(engine, "_owner_request_chance", lambda *_args: 1.0)
    rewarded = engine.manage_concubine_status(game_id, "request_stones")
    stones = next(item for item in rewarded["player"]["inventory"] if item["id"] == "spirit_stone")
    assert stones["quantity"] >= 3
    with pytest.raises(ValueError, match="本行动单位"):
        engine.manage_concubine_status(game_id, "request_stones")
