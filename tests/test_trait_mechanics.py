"""Player, NPC and resumed ordinary exchanges share the new personal trait mechanics."""
import json
from dataclasses import replace

import pytest

from cultivation_life import traits
from cultivation_life.combat_attributes import components
from cultivation_life.models import GameState, Player, SectNpc
from cultivation_life.system.combat.contracts import Combatant, resolve_source
from cultivation_life.system.combat.trials import dump_battle, load_battle
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat_loadout import npc_attribute_sources, project_loadout


def fighter(identity, side, *keys):
    game = GameState("traits", 42, Player("沈宁", "supreme_water"), "created", "revision")
    owner = game.player if identity == "player" else SectNpc(identity, identity, "", 1, 1, 30, 150)
    for key in keys:
        source = next(book for book, trait in traits.MASTERY.items() if trait == key)
        assert traits.mastery(owner, source)
    if owner is game.player:
        source = project_loadout(game, owner, player=True)
    else:
        source = npc_attribute_sources([(owner, 100)], [], {}).get(identity)
    return Combatant(identity, identity, side, 100, resolve_source({}, {}, source))


def begin(battle, n, first=True):
    battle.begin_round(n, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)
    ordinary = battle.semantic_ordinary_start()
    initiative = battle.semantic_initiative(first)
    return ordinary, initiative


def end(battle):
    battle.finish_round(player_mp=1, enemy_mp=1)


def duel(*keys, enemy=()):
    return VoisinageBattle([fighter("player", "player", *keys), fighter("enemy", "enemy", *enemy)])


def test_charge_only_real_hits_then_consume_and_resume_on_same_round():
    battle = duel("river_banner")
    for n, damage in enumerate((.03, 0., .03), 1):
        begin(battle, n)
        assert battle.ordinary_damage(damage, 0)[0] == pytest.approx(damage)
        end(battle)
    resumed = load_battle(json.loads(json.dumps(dump_battle(battle))))
    for b in (battle, resumed):
        begin(b, 4)
        assert b.ordinary_damage(.03, 0)[0] == pytest.approx(.039)
        end(b)
        begin(b, 5)
        assert b.ordinary_damage(.03, 0)[0] == pytest.approx(.03)


def test_decoy_and_hook_bind_to_one_opponent_and_expire():
    battle = VoisinageBattle([fighter("player", "player", "willow_hook", "candle_shadow"),
                              fighter("a", "enemy"), fighter("b", "enemy")])
    begin(battle, 1)
    battle.ordinary_damage(.05, 0)
    assert battle.units["a"].vitality == pytest.approx(.96)
    assert battle.units["b"].vitality == pytest.approx(.95)
    end(battle)
    begin(battle, 2)
    battle.ordinary_damage(.05, 0)
    assert battle.units["a"].vitality == pytest.approx(.96 - .05 * 1.55)
    assert battle.units["b"].vitality == pytest.approx(.90)
    assert any("烛影" in text and "消耗一层" in text for text in battle.frame.events)
    end(battle)
    begin(battle, 3)
    battle.ordinary_damage(.05, 0)
    assert battle.units["a"].vitality == pytest.approx(.96 - .05 * 2.55)


def test_ally_can_spend_breach_after_its_creator_leaves():
    battle = VoisinageBattle([fighter("opener", "player", "stele_breaker"),
                              fighter("ally", "player"), fighter("foe", "enemy")])
    begin(battle, 1)
    assert battle.ordinary_damage(.04, 0)[0] == pytest.approx(.04)
    end(battle)
    battle.units["opener"].escaped = True
    begin(battle, 2)
    assert battle.ordinary_damage(.04, 0)[0] == pytest.approx(.02 * 1.25)


def test_vines_slow_actual_enemy_and_short_dispel_has_one_charge():
    for cleanse in (False, True):
        b = duel("vine_coil", enemy=("sun_duster",) if cleanse else ())
        for n in range(1, 6):
            factors, _ = begin(b, n)
            slowed = n == 5 or n == 2 and not cleanse
            assert factors["enemy"]["mobility"] == pytest.approx(.8 if slowed else 1.)
            b.ordinary_damage(.02, 0)
            end(b)


def test_heavy_hit_cap_and_recovery_after_a_quiet_round():
    b = duel("iron_shirt", "brook_breath")
    begin(b, 1)
    assert b.ordinary_damage(0, .08)[1] == pytest.approx(.08)
    end(b)
    begin(b, 2)
    assert b.ordinary_damage(0, .2)[1] == pytest.approx(.13)
    end(b)
    body = b.units["player"].body
    begin(b, 3)
    b.ordinary_damage(.02, 0)
    end(b)
    assert b.units["player"].body == pytest.approx(body + .02)
    begin(b, 4)
    assert b.ordinary_damage(0, .2)[1] == pytest.approx(.2)


def test_initiative_posture_and_morale_have_real_costs():
    b = duel("swallow_turn", "winter_current", enemy=("dawn_drum", "warm_jade"))
    b.units["enemy"].morale = 40
    _, opening = begin(b, 1, first=False)
    assert opening["player"]["might"] == pytest.approx(.9)
    assert b.ordinary_damage(0, .1)[1] == pytest.approx(.072)
    end(b)
    assert b.units["enemy"].morale == pytest.approx(60)
    assert b.units["enemy"].vitality == pytest.approx(.97)
    factors, opening = begin(b, 2)
    assert factors["player"]["mobility"] == pytest.approx(1.25)
    assert opening["player"]["might"] == pytest.approx(1.)
    end(b)
    factors, _ = begin(b, 3)
    assert factors["player"]["mobility"] == pytest.approx(1.)


def test_stances_redistribute_only_existing_damage_and_preserve_physical():
    profile = {"physical": .2, "earth": .3, "metal": .4, "fire": .1}
    keys = ("silver_shear", "red_sand")
    for ward, expected in [(None, profile), ("metal", {"physical": .2, "metal": .8}),
                           ("fire", {"physical": .2, "earth": .2, "metal": .4, "fire": .2})]:
        parts = components(profile, keys, "wood", [], ward)
        assert {k: v["share"] for k,v in parts.items()} == pytest.approx(expected)
        assert parts["physical"]["relation"] == 1
        if "earth" in parts:
            assert parts["earth"]["relation"] == .8
    assert profile == {"physical": .2, "earth": .3, "metal": .4, "fire": .1}
    assert components({"physical": 1.}, keys, "metal", [], "fire")["physical"]["share"] == 1.


def test_body_ward_and_fallback_respect_lost_or_restored_equipment():
    owned = fighter("enemy", "enemy", "moss_veil", "orchid_shade").capabilities
    assert owned.attributes["ward_sources"]["wood"] == ["body"]
    setup = dict(owned.attributes, ward="fire", wards=["wood", "fire"],
                 ward_sources={"wood": ["body"], "fire": ["artifact", "technique"]})
    b = VoisinageBattle([fighter("player", "player"),
                         Combatant("enemy", "enemy", "enemy", 100, replace(owned, attributes=setup))])
    owner = b.units["enemy"]
    owner.controls["artifact"] = "player"
    assert b.active_element_ward("enemy") == "fire"
    owner.controls["technique"] = "player"
    assert b.active_element_ward("enemy") == "yin"
    owner.controls.clear()
    assert b.active_element_ward("enemy") == "fire"


def test_forfeiting_or_failing_tier_does_not_spend_a_defenders_iron_shirt():
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    book = next(t for t in TECHNIQUE_CATALOG.values() if "forgo_attack" in t.combat_effect.get("clauses", ()))
    entry = dict(id=book.id, name=book.name, level=1, effect=book.combat_effect)
    left = fighter("player", "player")
    left = replace(left, capabilities=replace(left.capabilities, technique_effects=(entry,)))
    battle = VoisinageBattle([left, fighter("enemy", "enemy", "iron_shirt")])
    begin(battle, 1)
    record, = battle.techniques.catalog.records.values()
    record["forfeit_pending"] = True
    assert battle.ordinary_damage(.2, 0)[0] == 0
    end(battle)
    begin(battle, 2)
    assert battle.ordinary_damage(.2, 0)[0] == pytest.approx(.13)

    target = fighter("enemy", "enemy", "iron_shirt")
    shielded = replace(target, capabilities=replace(target.capabilities, ward_tier=2))
    ordinary = VoisinageBattle([fighter("player", "player"), shielded])
    begin(ordinary, 1)
    assert ordinary.ordinary_damage(.2, 0)[0] == 0
    assert not ordinary.semantics.usage


def test_npc_signature_supplements_existing_battle_rules():
    npc = SectNpc("peer", "沈衡", "", 1, 1, 24, 140)
    traits.mastery(npc, traits.LINEAGES["river_banner"].books[0])
    source = npc_attribute_sources([(npc, 100)], [], {})[npc.id]
    rule = dict(schema_version=3, id="prepared", source_id="scenario", trigger="round_start",
                actions=[dict(op="counter_add", key="turns", value=1)])
    caps = resolve_source({"semantic_rules": [rule]}, {}, source)
    assert {r["source_id"] for r in caps.semantic_rules} == {"scenario", "特质·沧波叠浪"}
