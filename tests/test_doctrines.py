from dataclasses import replace
import copy
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.combat_capabilities import bind_capabilities
from cultivation_life.models import SectNpc, Technique
from cultivation_life.rules import (add_item, assign_technique, combat_power, learn_technique,
                                    max_hp, max_mp, technique_copy_count, upgrade_known_technique, validate_technique)
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities, VoisinageDefinition
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.npc_lifecycle import initialize_native
from cultivation_life.system.combat_system import BattleUnit
from cultivation_life.system.doctrine.generation import generate, validate_content
from cultivation_life.system.doctrine.progression import source
from cultivation_life.system.doctrine.cultivation import attempt
from cultivation_life.system.doctrine.provider import battle_sources, ensure

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = {r: 10 ** r for r in range(9, 13)}


@pytest.fixture(scope="module")
def catalog():
    return generate(7429, CONTENT_DOCUMENTS["doctrines.json"], CALIBRATION)


@pytest.fixture
def setup(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    made = engine.create_game("问道", "supreme_metal", "dao", seed=7429, preset_id="true_immortal")
    game = engine.store.load(made["id"])
    game.pending_event = None
    game.heavenly_court["open_election"] = None
    game.player.next_tribulation_age = None
    game.player.known_techniques = [t for t in game.player.known_techniques if not t.doctrine_id]
    game.doctrine_state['player']['annotations'] = {}
    add_item(game.player, "spirit_stone", 10**8)
    game.player.location_id = 'expanse_celestial_8'
    game.yaochi_state['merit'] = 10000
    engine.store.save(game)
    return engine, game


def learn(game, index=0):
    definition = list(game.doctrine_state["definitions"].values())[index]
    learn_technique(game.player, Technique(**copy.deepcopy(definition["manuals"][0])))
    game.doctrine_state["player"]["progress"][definition["id"]] = {"level": 0, "experience": 0}
    return definition


def test_generated_catalog_counts_identity_and_calibration(catalog):
    definitions = catalog["definitions"]
    assert len(definitions) == 25
    assert sum(d["fixed"] for d in definitions.values()) == 2
    assert all(3 <= len(d["manuals"]) <= 8 for d in definitions.values())
    manuals = [b for d in definitions.values() for b in d["manuals"]]
    assert len({b["id"] for b in manuals}) == len(manuals)
    assert len({b["name"] for b in manuals}) == len(manuals)
    for definition in definitions.values():
        assert len(definition["stages"]) == 9
        assert all(s["voisinage"] is None for s in definition["stages"][:3])
        assert all(s["voisinage"] is not None for s in definition["stages"][3:])
    for book in manuals:
        validate_technique(Technique(**book))
        assert .034 <= book["combat_bonus"] / CALIBRATION[book["grade"]] <= .066
        assert book["effective_worlds"] == ["celestial"]


def test_seed_defines_future_and_fixed_doctrines_are_identical(catalog):
    config = CONTENT_DOCUMENTS["doctrines.json"]
    assert generate(7429, config, CALIBRATION) == catalog
    other = generate(7430, config, CALIBRATION)
    for key, definition in catalog["definitions"].items():
        if definition["fixed"]:
            assert definition == other["definitions"][key]
        else:
            assert definition != other["definitions"][key]


def test_lexicon_is_rich_and_does_not_control_mechanics(catalog):
    config = copy.deepcopy(CONTENT_DOCUMENTS["doctrines.json"])
    validate_content(config)
    assert len(config["themes"]) >= 32
    assert sum(len(t["images"]) for t in config["themes"]) >= 192
    config["words"]["prefixes"] = ["异" + p for p in config["words"]["prefixes"]]
    renamed = generate(7429, config, CALIBRATION)
    for key, original in catalog["definitions"].items():
        for a, b in zip(original["stages"][3:], renamed["definitions"][key]["stages"][3:]):
            assert {k: v for k, v in a["voisinage"].items() if k != "name"} == {k: v for k, v in b["voisinage"].items() if k != "name"}
    config["words"]["manual_verbs"] = ["修炼"]
    with pytest.raises(ValueError, match="贫乏"):
        validate_content(config)


def test_no_registry_pollution_or_game_rng_consumption(setup):
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    _, game = setup
    prior = set(TECHNIQUE_CATALOG)
    game.doctrine_state = {}
    rng = game.rng_state
    assert ensure(game)
    assert game.rng_state == rng
    assert set(TECHNIQUE_CATALOG) == prior


def test_saved_future_is_not_regenerated_on_config_update(setup, monkeypatch):
    engine, game = setup
    original = copy.deepcopy(game.doctrine_state)
    monkeypatch.setitem(CONTENT_DOCUMENTS["doctrines.json"], "generation_version", 999)
    engine.store.save(game)
    loaded = engine._load(game.id)
    assert loaded.doctrine_state == original


def test_public_redaction_and_manual_requirement(setup):
    engine, game = setup
    first = next(iter(game.doctrine_state["definitions"]))
    with pytest.raises(ValueError, match="功法"):
        engine.doctrine_action(game.id, "study", doctrine_id=first)
    shown = engine._public_doctrines(game)
    assert all(row["stages"] == [] for row in shown["rows"])
    book = shown["offers"][0]
    acquired = engine.doctrine_action(game.id, "buy", manual_id=book["id"])
    row = next(row for row in acquired["doctrines"]["rows"] if row["learned"])
    assert [s["level"] for s in row["stages"]] == [1]
    assert "definitions" not in acquired["doctrines"]
    game = engine.store.load(game.id)
    game.doctrine_state["player"]["progress"][row["id"]] = {"level": 3, "experience": 0}
    row = next(r for r in engine._public_doctrines(game)["rows"] if r["id"] == row["id"])
    assert [s["level"] for s in row["stages"]] == [1, 2, 3, 4]
    assert row["stages"][-1]["voisinage"]
    hidden = game.doctrine_state["definitions"][row["id"]]["stages"][8]
    assert hidden["ability_name"] not in json.dumps(engine._public_doctrines(game), ensure_ascii=False)


def test_duplicate_generated_books_upgrade_without_losing_origin(setup):
    engine, game = setup
    book = engine._public_doctrines(game)["offers"][0]
    engine.doctrine_action(game.id, "buy", manual_id=book["id"])
    engine.doctrine_action(game.id, "buy", manual_id=book["id"])
    loaded = engine._load(game.id)
    assert technique_copy_count(loaded.player, book["id"], 1) == 1
    copy_item = next(i for i in loaded.player.inventory if i.technique_id == book["id"])
    assert copy_item.technique_origin_realm_index == 9
    assert upgrade_known_technique(loaded.player, book["id"]) == 2
    assert loaded.doctrine_state["player"]["progress"]


def test_origin_gate_allows_breadth_but_one_deep_path(catalog):
    a, b = list(catalog["definitions"].values())[:2]
    rules = CONTENT_DOCUMENTS["doctrines.json"]["cultivation"]
    record = {"progress": {}, "origin": None, "active": a["id"]}
    for d in (a, b):
        p = record["progress"][d["id"]] = {"level": 0, "experience": 0}
        for _ in range(4):
            assert attempt(p, d, 10**8, None, rules, 0) == "success"
        assert attempt(p, d, 10**8, None, rules, 0) == "origin_required"
        assert p["level"] == 4
    record["origin"] = a["id"]
    for _ in range(5):
        attempt(record["progress"][a["id"]], a, 10**8, a["id"], rules, 0)
    assert attempt(record["progress"][b["id"]], b, 10**8, a["id"], rules, 0) == "blocked"
    assert record["progress"][a["id"]]["level"] == 9
    assert source(record, catalog["definitions"], "celestial").voisinages
    record["origin"] = b["id"]
    with pytest.raises(ValueError, match="非本源"):
        source(record, catalog["definitions"], "celestial")


def test_training_advances_once_and_handles_partial_time(catalog):
    d = next(iter(catalog["definitions"].values()))
    progress = {"level": 0, "experience": 0}
    rules = CONTENT_DOCUMENTS["doctrines.json"]["cultivation"]
    assert attempt(progress, d, 30, None, rules, 0) == "training"
    assert progress["experience"] == 30
    assert attempt(progress, d, 10000, None, rules, 0) == "success"
    assert progress["level"] == 1 and progress["experience"] == 0


def test_origin_confirmation_is_enforced_by_backend(setup):
    engine, game = setup
    d = learn(game)
    game.doctrine_state["player"]["progress"][d["id"]] = {"level": 4, "experience": d["stages"][4]["years"]}
    game.player.known_techniques[-1].level = 5
    game.doctrine_state["player"]["annotations"][d["id"]] = [5]
    engine.store.save(game)
    with pytest.raises(ValueError, match="确认"):
        engine.doctrine_action(game.id, "origin", doctrine_id=d["id"])
    result = engine.doctrine_action(game.id, "origin", doctrine_id=d["id"], confirm_origin=True)
    row = next(r for r in result["doctrines"]["rows"] if r["id"] == d["id"])
    assert row["origin"] and row["level"] in (4, 5)


def test_book_stats_and_voisinage_do_not_apply_in_other_worlds(setup):
    engine, game = setup
    d = learn(game)
    book = game.player.known_techniques[-1]
    assign_technique(game.player, copy.deepcopy(book), "combat")
    assign_technique(game.player, copy.deepcopy(book), "support")
    game.doctrine_state["player"].update(active=d["id"])
    game.doctrine_state["player"]["progress"][d["id"]]["level"] = 4
    assert battle_sources(game, {"player": game.player})["player"].voisinages
    game.player.world = "asura"
    assert engine._public_doctrines(game) == {"available": False}
    assert not any(s.voisinages for s in battle_sources(game, {"player": game.player}).values())
    without = copy.deepcopy(game.player)
    without.support_technique = None
    without.combat_techniques = [t for t in without.combat_techniques if not t.doctrine_id]
    assert max_hp(game.player) == max_hp(without)
    assert max_mp(game.player) == max_mp(without)
    assert combat_power(game.player) == combat_power(without)
    with pytest.raises(ValueError, match="仙界"):
        assign_technique(game.player, copy.deepcopy(book), "main")


def test_active_voisinage_reaches_player_battle_adapter(setup):
    _, game = setup
    d = learn(game)
    game.doctrine_state["player"].update(active=d["id"])
    game.doctrine_state["player"]["progress"][d["id"]]["level"] = 4
    binding = bind_capabilities(game, [BattleUnit("player", "问道", "player", 100, 9)],
                                dict(target_name="敌人", target_power=100, target_realm_index=9), WORLD_SYSTEMS["transcendent_combat"])
    caps = binding.battle.units["player"].unit.capabilities
    assert caps.voisinages[0].id == d["stages"][3]["voisinage"]["id"]
    assert caps.resource_link == "independent"


def test_npc_training_is_lazy_shared_and_bounded(setup):
    _, game = setup
    npc = SectNpc("lazy", "仙修", "", 12, 1, 10000, None, world="celestial")
    initialize_native(npc, WORLD_SYSTEMS["transcendent_combat"], now=game.player.age)
    prior_rng = game.rng_state
    battle_sources(game, {npc.id: npc})
    saved = copy.deepcopy(npc.transcendence)
    game.player.age += 1000000
    assert npc.transcendence == saved  # No tick or observer mutation.
    result = battle_sources(game, {npc.id: npc})
    assert result[npc.id].voisinages
    assert game.rng_state == prior_rng
    record = npc.transcendence["doctrine"]
    assert record["progress"][record["active"]]["level"] == 9
    assert record["origin"] == record["active"]
    assert "definitions" not in record


def test_conversion_spends_opportunity_without_elapsed_time(setup, monkeypatch):
    engine, game = setup
    game.player.immortal_power_converted = False
    game.player.immortal_conversion_stage = 0
    game.player.mp = 0
    game.player.opportunity = 2000
    game.pending_event = None
    engine.store.save(game)
    engine.get_game(game.id)  # Complete ordinary initial-world preparation first.
    game = engine._load(game.id)
    age, rng = game.player.age, game.rng_state
    engine.doctrine_action(game.id, 'convert')
    game = engine._load(game.id)
    assert game.player.immortal_conversion_stage == 1
    assert game.player.opportunity == 1900 and game.player.age == age
    assert game.rng_state == rng and game.pending_event is None
    assert game.player.mp == pytest.approx(max_mp(game.player) * .2)
    assert not engine._maybe_immortal_conversion_event(game, random.Random(1))
    with pytest.raises(ValueError, match='机缘'):
        engine._begin_doctrine_action(game, 'immortal_conversion')
    engine._finish_doctrine_action(game, 'immortal_conversion', 100000)
    assert game.player.immortal_conversion_stage == 1
    for _ in range(4): engine.doctrine_action(game.id, 'convert')
    game = engine._load(game.id)
    assert game.player.immortal_power_converted and game.player.immortal_conversion_stage == 5
    assert game.player.opportunity == 420 and game.player.age == age
    assert game.player.mp == max_mp(game.player)
    assert game.doctrine_state['player']['conversion_progress'] == 0


def voisinage_battle(a, b):
    def actor(key, side, definition):
        c = CombatCapabilities(capacity=10000, current=10000, resource_tier=2,
                               voisinages=(definition,), attainments={"test": 4})
        return Combatant(key, key, side, 100, c)
    return VoisinageBattle([actor("a", "player", a), actor("b", "enemy", b)])


def definition(**changes):
    values = dict(id="field", name="仙域", attainment="test", required_level=4, strength=1,
                  stability=100, incursion=100, authority=100, opening_cost=10, upkeep_cost=10,
                  effect_cost=10, effect="strike", effect_power=.4)
    values.update(changes)
    return VoisinageDefinition(**values)


def begin(battle, n=1):
    return battle.begin_round(n, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)


def test_stability_and_incursion_are_directional_not_a_total_score():
    battle = voisinage_battle(definition(stability=200, incursion=10), definition(stability=20, incursion=100))
    phase = begin(battle)
    assert phase.relations["a"]["relation"] == "contested"
    assert phase.relations["b"]["relation"] == "contested"
    assert phase.ordinary


def test_mutual_breach_applies_both_powers_without_roster_order_advantage():
    battle = voisinage_battle(definition(stability=20, incursion=200), definition(stability=20, incursion=200))
    phase = begin(battle)
    assert not phase.ordinary
    assert battle.units["a"].vitality == pytest.approx(.6)
    assert battle.units["b"].vitality == pytest.approx(.6)


def test_sustained_features_reset_when_field_drops():
    battle = voisinage_battle(definition(features=({"kind": "fortify", "value": .2},)), definition())
    battle.units["b"].unit = replace(battle.units["b"].unit, capabilities=replace(battle.units["b"].unit.capabilities, stance="guard"))
    begin(battle)
    first = battle.fields[0].stability
    begin(battle, 2)
    assert battle.fields[0].stability == pytest.approx(first * 1.2)
    battle.units["a"].current = 0
    begin(battle, 3)
    battle.units["a"].current = 1000
    condition = battle.units["a"].vitality
    begin(battle, 4)
    assert battle.fields[0].stability == pytest.approx(first * condition)


def test_authority_limits_suppression_instead_of_always_one_shot():
    battle = voisinage_battle(definition(incursion=500, effect="suppress", authority=50), definition(incursion=1))
    begin(battle)
    assert not battle.units["b"].suppressed
    assert battle.units["b"].vitality == pytest.approx(.8)
    assert "镇压侵蚀" in "".join(battle.frame.events)


def test_generated_seal_accumulates_authority_to_nonlethal_control():
    battle = voisinage_battle(definition(incursion=500, effect="seal"), definition(incursion=1))
    begin(battle)
    assert battle.units["b"].escape_locked and not battle.units["b"].suppressed
    assert battle.units["b"].seal_progress == pytest.approx(.4)
    begin(battle, 2)
    begin(battle, 3)
    assert battle.units["b"].suppressed
    assert 0 < battle.units["b"].vitality < 1  # sustained domination erodes combat stance
    assert battle.verdict() == "victory"
    assert not battle.enemy_killed()


def test_npc_lazy_training_does_not_depend_on_number_of_observations(setup):
    _, game = setup
    npc = SectNpc("split", "仙修", "", 12, 1, 10000, None, world="celestial")
    initialize_native(npc, WORLD_SYSTEMS["transcendent_combat"], now=game.player.age)
    battle_sources(game, {npc.id: npc})
    record = npc.transcendence["doctrine"]
    record["origin"] = None
    record["progress"][record["active"]] = {"level": 2, "experience": 0}
    once = copy.deepcopy(npc)
    for _ in range(40):
        game.player.age += 100
        battle_sources(game, {npc.id: npc})
    battle_sources(game, {once.id: once})
    assert npc.transcendence == once.transcendence
