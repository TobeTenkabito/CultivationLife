import copy
import random
from unittest.mock import patch

import pytest

from test_buddhist_dharma import setup
from cultivation_life.content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp, opportunity_multiplier
from cultivation_life.system.buddhist_wish import ensure_wish, nirvana_target
from cultivation_life.system.path_modifiers import modifier
from cultivation_life.system.semantic_events import emit


def test_three_independent_quiet_clocks_and_fractional_years(setup):
    _, game, _ = setup
    wish = ensure_wish(game)
    for _ in range(25):
        emit(game, "time.elapsed", years=1, unit_years=5)
    assert wish["value"] == 0
    for _ in range(5):
        emit(game, "time.elapsed", years=1, unit_years=5)
    assert wish["value"] == 3
    emit(game, "concubine.recruited", target_id="new")
    emit(game, "time.elapsed", years=5, unit_years=5)
    assert wish["value"] == 5
    assert wish["quiet"]["concubine"] == 1
    emit(game, "cultivator.killed", in_combat=True, defending=True)
    assert wish["value"] == 5 and wish["quiet"]["kill"] == 0
    emit(game, "companion.entwined")
    assert wish["quiet"]["entwine"] == 0


@pytest.mark.parametrize("name,data,delta", [
    ("captive.released", {}, 1), ("disciple.recruited", {}, 2),
    ("captive.tortured", {}, -1), ("cultivator.killed", {"in_combat":True}, -2),
    ("cultivator.killed", {"defending":True,"in_combat":True}, 0),
    ("cultivator.killed", {"execution":True}, -5),
    ("cultivator.killed", {"in_combat":True,"penalty_handled":True}, 0),
    ("relationship.attacked", {"roles":["master","sect_member"]}, -30),
    ("relationship.attacked", {"roles":["companion"]}, -30),
    ("relationship.attacked", {"roles":["sect_member"]}, -10),
    ("relationship.attacked", {"kind":"party"}, -2),
    ("diplomacy.proposal_passed", {"status":"war"}, -5),
    ("diplomacy.proposal_passed", {"status":"alliance"}, 0),
])
def test_event_effects(setup, name, data, delta):
    _, game, _ = setup
    wish = ensure_wish(game); wish["value"] = 50
    emit(game, name, **data)
    assert wish["value"] == 50 + delta


def test_offline_dlc_and_other_paths_freeze_saved_wish(setup):
    _, game, _ = setup
    wish = ensure_wish(game); wish["value"] = 50
    before = copy.deepcopy(game.buddhist_state)
    with patch.dict(CONTENT_DOCUMENTS["buddhist_way.json"]["settings"], enabled=False):
        emit(game, "captive.released")
        emit(game, "time.elapsed", years=50, unit_years=1)
        assert modifier(game.player, "opportunity_efficiency") == 1
        assert before == game.buddhist_state
    game.player.path = "dao"
    emit(game, "disciple.recruited")
    assert wish["value"] == 50


def test_bonuses_roundtrip_and_no_player_resource_cache(setup):
    engine, game, _ = setup
    wish = ensure_wish(game); wish["value"] = 50
    assert modifier(game.player, "breakthrough_base_bonus", 0) == .025
    assert modifier(game.player, "opportunity_efficiency") == 1.1
    assert modifier(game.player, "thunder_damage_reduction", 0) == .05
    baseline = engine._tribulation_damage_reduction(game.player)
    wish["value"] = 100
    assert engine._tribulation_damage_reduction(game.player) == pytest.approx(baseline + .05)
    saved = game.to_dict()
    assert "_modifier_context" not in saved["player"]
    loaded = GameState.from_dict(saved); engine._ensure_buddhist_state(loaded)
    assert modifier(loaded.player, "breakthrough_base_bonus", 0) == .05
    cloned = copy.deepcopy(loaded); cloned.buddhist_state["wish"]["value"] = 0
    assert modifier(cloned.player, "opportunity_efficiency") == 1
    assert modifier(loaded.player, "opportunity_efficiency") == 1.2
    before = copy.deepcopy(loaded.buddhist_state)
    engine.present(loaded); engine.present(loaded)
    assert loaded.buddhist_state == before


def test_nirvana_one_layer_no_trial_and_three_units(setup):
    engine, game, _ = setup
    game.player.realm_index = 2; game.player.layer = 3
    ensure_wish(game)["value"] = 100
    engine.store.save(game)
    result = engine.buddhist_action(game.id, "nirvana")
    updated = engine._load(game.id)
    assert updated.player.realm_index == 2 and updated.player.layer == 4
    assert not updated.active_trial and not updated.pending_event
    assert updated.buddhist_state["wish"]["value"] == 0
    assert modifier(updated.player, "opportunity_efficiency") == 2
    for _ in range(3):
        emit(updated, "time.elapsed", years=5, unit_years=5)
    assert modifier(updated.player, "opportunity_efficiency") == 1
    assert result["buddhist_system"]["wish"]["nirvana_units"] == 3


@pytest.mark.parametrize("realm,layer", [(2,9),(5,3),(9,1)])
def test_nirvana_rejects_major_crossing_and_world_cap_without_spending(setup, realm, layer):
    engine, game, _ = setup
    game.player.realm_index = realm; game.player.layer = layer
    ensure_wish(game)["value"] = 100
    engine.store.save(game)
    with pytest.raises(ValueError):
        engine.buddhist_action(game.id, "nirvana")
    assert engine._load(game.id).buddhist_state["wish"]["value"] == 100


@pytest.mark.parametrize("kind", ["captive", "concubine"])
def test_execution_is_immediate_and_cannot_repeat(setup, kind):
    engine, game, _ = setup
    person = {"id":"held", "name":"被囚修士", "realm_index":2, "layer":1, "alive":True, "world":"human"}
    getattr(game.player, "prisoners" if kind == "captive" else "concubines").append(person)
    ensure_wish(game)["value"] = 50
    engine.store.save(game)
    with patch.object(engine, "_combat", side_effect=AssertionError("instant execution must not roll combat")):
        engine.relationship_violence(game.id, kind, "held")
    updated = engine._load(game.id)
    assert updated.buddhist_state["wish"]["value"] == 45
    with pytest.raises(ValueError):
        engine.relationship_violence(game.id, kind, "held")


def test_betrayed_target_cannot_fight_on_both_sides(setup):
    engine, game, _ = setup
    game.player.party = [{"id":"ally", "name":"同行者"}]
    game.player.dao_friends = [{"id":"ally", "name":"同行者", "world":"human", "alive":True,
                                "realm_index":1,"layer":1,"combat_power":100}]
    units = engine._player_combat_units(game, {"exclude_allied_ids":["ally"]})
    assert all(unit.id != "ally" for unit in units)


def test_high_cultivation_deterrence_does_not_create_license(setup):
    engine, game, _ = setup
    sect = next(s for s in game.sects.values() if s.world == "human" and not s.extinct)
    from cultivation_life.system.faction_geography import faction_site
    game.player.location_id = faction_site(sect)["id"]
    game.player.faction_id = None
    game.player.realm_index = 4
    rights = engine._buddhist_permissions(game)
    assert rights and all(row["intimidated"] for row in rights)
    assert any(not row["permitted"] for row in rights)
    game.player.realm_index = 3
    assert not any(row["intimidated"] for row in engine._buddhist_permissions(game))


@pytest.mark.parametrize("kind", ["disciple", "party", "master", "companion"])
def test_live_combat_relationship_penalties(setup, kind):
    engine, game, _ = setup
    game.player.realm_index = 5; game.player.layer = 3
    game.player.hp = max_hp(game.player); game.player.mp = max_mp(game.player)
    person = {"id":"betrayed", "name":"同行者", "world":"human", "alive":True,
              "realm_index":1,"layer":1,"combat_power":1,"path":"dao","age":20,"lifespan":100}
    if kind == "disciple": game.player.disciples.append(person)
    elif kind == "master": game.player.master = person
    elif kind == "companion": game.player.dao_companion = person
    else: game.player.dao_friends.append(person)
    game.player.party = [{"id":person["id"],"name":person["name"]}]
    ensure_wish(game)["value"] = 100
    engine.store.save(game)
    with patch.object(engine, "_combat", wraps=engine._combat) as fight:
        engine.relationship_violence(game.id, kind, person["id"])
        assert fight.call_count == 1
    saved = engine._load(game.id)
    assert saved.history[-1].result == "killed"
    assert not saved.player.party
    assert saved.buddhist_state["wish"]["value"] == {"disciple":95,"party":98,"master":70,"companion":70}[kind]


def test_release_torture_and_disciple_acceptance_api_events(setup):
    engine, game, _ = setup
    game.player.prisoners = [{"id":"held", "name":"被囚者", "world":"human", "realm_index":1, "layer":1}]
    ensure_wish(game)["value"] = 40
    engine.store.save(game)
    engine.captive_action(game.id, "held", "torture")
    assert engine._load(game.id).buddhist_state["wish"]["value"] == 39
    engine.captive_action(game.id, "held", "release")
    assert engine._load(game.id).buddhist_state["wish"]["value"] == 40
    with pytest.raises(ValueError):
        engine.captive_action(game.id, "held", "release")


def test_surviving_companion_attacked_through_party_loses_both_relationships(setup):
    engine, game, _ = setup
    game.player.dao_companion = {"id":"ally","name":"故侣","world":"human","alive":True,
                                 "realm_index":1,"layer":1,"combat_power":100,"affinity":80}
    game.player.party = [{"id":"ally","name":"故侣"}]
    engine.store.save(game)
    with patch.object(engine, "_combat", return_value=("victory_escape", "对方逃脱")):
        engine.relationship_violence(game.id, "party", "ally")
    saved = engine._load(game.id)
    assert saved.player.dao_companion is None and not saved.player.party
    assert saved.history[-1].result == "victory_escape"


def test_base_execution_without_dlc_does_not_create_wish_state(setup):
    engine, game, _ = setup
    game.player.path = "dao"
    game.buddhist_state.clear()
    game.player.prisoners = [{"id":"held","name":"俘虏","world":"human","realm_index":1,"layer":1}]
    engine.store.save(game)
    with patch.dict(CONTENT_DOCUMENTS["buddhist_way.json"]["settings"], enabled=False):
        engine.relationship_violence(game.id, "captive", "held")
        assert engine._load(game.id).buddhist_state == {}


def test_real_defensive_kill_resets_quiet_without_spending_wish(setup):
    engine, game, _ = setup
    game.player.realm_index = 5; game.player.layer = 3
    game.player.hp = max_hp(game.player); game.player.mp = max_mp(game.player)
    wish = ensure_wish(game); wish["value"] = 50; wish["quiet"]["kill"] = 7
    target = {"target_name":"来犯者","target_power":1,"primary_power":1,"combat_type":"cultivator",
              "target_realm_index":1,"target_layer":1,"world":"human","path":"dao","race":"human",
              "player_defending":True,"action":"slay","non_story_combat":True}
    result, _ = engine._combat(game, target, True, random.Random(1))
    assert result == "killed"
    assert wish["value"] == 50 and wish["quiet"]["kill"] == 0


@pytest.mark.parametrize("passes", [True, False])
def test_intrigue_war_vote_spends_wish_only_when_player_proposal_passes(setup, passes):
    engine, game, _ = setup
    game.player.realm_index = 4; game.player.layer = 3
    ensure_wish(game)["value"] = 50
    engine.store.save(game)
    engine.create_faction(game.id, "照尘宗")
    prepared = engine._load(game.id)
    for npc in prepared.sects[prepared.player.faction_id].npcs:
        npc.realm_index = 4
    engine.store.save(prepared)
    with patch.object(engine, "_intrigue_vote_chance", return_value=(1.0 if passes else 0.0, [])):
        view = engine.intrigue_propose_resolution(game.id, "sect", "declare_war", "wanmo", True)
    assert view["intrigue_system"]["resolutions"][0]["result"] == ("passed" if passes else "rejected")
    assert engine._load(game.id).buddhist_state["wish"]["value"] == (45 if passes else 50)


def test_captured_named_npc_concubine_remains_alive_until_execution(setup):
    engine, game, _ = setup
    npc = next(n for n in game.world_npcs.values() if n.world == "human")
    npc.realm_index = 1; npc.layer = 1; npc.gender = "female"
    game.player.realm_index = 4
    game.player.prisoners = [game.detain_person({"id":npc.id, "npc_id":npc.id,"name":npc.name,"gender":"female",
                             "world":"human","realm_index":1,"layer":1,"path":"dao","race":"human",
                             "spirit_root":"supreme_water","age":20,"lifespan":100,"combat_power":5})]
    ensure_wish(game)["value"] = 50
    engine.store.save(game)
    shown = engine.manage_concubine(game.id, npc.id, "recruit")
    assert shown["concubine_system"]["concubines"][0]["alive"]
    held = engine._load(game.id)
    engine._sync_relationship_records(held)
    assert held.player.concubines[0]["alive"]
    result = engine.relationship_violence(game.id, "concubine", npc.id)
    assert not result["concubine_system"]["concubines"][0]["alive"]
    assert engine._load(game.id).buddhist_state["wish"]["value"] == 45
    engine.manage_concubine(game.id, npc.id, "dismiss")
    assert not engine._load(game.id).inactive_npcs[npc.id].alive
