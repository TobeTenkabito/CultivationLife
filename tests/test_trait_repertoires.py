"""Coverage for new mastery and tactical interactions through the actual battle drivers."""

import json
import random
from copy import deepcopy
from dataclasses import replace

import pytest

from cultivation_life import traits
from cultivation_life.combat_attributes import FIVE, components
from cultivation_life.system.combat.trials import dump_battle, load_battle
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.trait_repertoires import BY_RARITY, REPERTOIRES
from test_trait_mechanics import begin, duel, end, fighter
from test_voisinage_effects import actor, caster, domain


def test_waning_sword_spread_is_simultaneous_once_per_enemy_and_fully_recoverable():
    key = "waning_sword_dao"
    battle = VoisinageBattle([
        fighter("player", "player", key), fighter("ally", "player", key),
        replace(fighter("duelist", "enemy", key), power=300, integrity=.70),
        replace(fighter("guard", "enemy"), integrity=.45),
    ])
    begin(battle, 1)
    for identity, remaining in {"player": .90, "ally": .90, "duelist": .60, "guard": .35}.items():
        assert battle.units[identity].vitality == pytest.approx(remaining)
        assert battle.units[identity].body == 1.
    assert battle.frame.player_loss == pytest.approx(.1)
    assert battle.frame.enemy_loss == pytest.approx(.1)
    assert battle.frame.primary_loss == 0.
    assert not battle.attribute_hits
    assert not battle._semantic_totals
    battle._restore_state("duelist", .8)
    assert battle.units["duelist"].vitality == 1.
    end(battle)
    resumed = load_battle(json.loads(json.dumps(dump_battle(battle))))
    begin(resumed, 2)
    assert resumed.units["duelist"].vitality == 1.
    assert resumed.units["guard"].vitality == pytest.approx(.35)
    assert resumed.frame.enemy_loss == 0.


def test_waning_sword_does_not_require_equipping_the_mastered_book_in_npc_combat():
    from cultivation_life.content_registry import TECHNIQUE_CATALOG, WORLD_SYSTEMS
    from cultivation_life.models import SectNpc
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    from cultivation_life.system.npc_techniques import learn

    owner, a, b = [SectNpc(i, i, "", 3, 1, 32, 150) for i in ("owner", "a", "b")]
    book = deepcopy(TECHNIQUE_CATALOG["TECH_COMMON_GUI"])
    learn(owner, book, level=8)
    assert "waning_sword_dao" not in traits.active(owner)
    learn(owner, book, level=9)
    assert traits.active(owner)["waning_sword_dao"] == [book.id]
    result = resolve_npc_engagement([(owner, 120)], [(a, 60), (b, 60)], WORLD_SYSTEMS["transcendent_combat"],
                                    random.Random(1), max_rounds=2)
    first, second = result.rounds
    assert sum("开战受压" in event for event in first["events"]) == 2
    assert not any("开战受压" in event for event in second["events"])


def test_waning_sword_precedes_a_field_only_round_in_player_combat():
    from test_domain_combat import capability, fight

    owner = fighter("player", "player", "waning_sword_dao")
    result, battle = fight(owner.capabilities, capability(), rounds=1)
    opening = result.rounds[0]
    assert opening["initiative"] == "voisinage"
    assert opening["enemy_hp_ratio"] == pytest.approx(.9)
    assert opening["enemy_combat_state"] == pytest.approx(.9 * opening["enemy_combat_state_max"])
    assert battle.units["enemy-0"].body == 1.


def test_all_sources_reachable_and_original_orange_birth_pool_preserved():
    assert {r: len(group) for r, group in BY_RARITY.items()} == {"绿": 42, "蓝": 36, "紫": 21, "橙": 2}
    assert len(REPERTOIRES) == len({v.name for v in REPERTOIRES.values()}) == 101
    assert {k for k, row in traits.TRAITS.items() if row[1] == "橙" and k not in traits.MASTERY_ONLY} == {
        "confluence",
        "heaven",
    }
    for key, entry in REPERTOIRES.items():
        owner = {}
        assert traits.mastery(owner, entry.book)
        assert traits.validate(owner["trait_state"])
        assert traits.public(owner)[0]["effect"] == entry.signature.description
        owner["spirit_state"] = {"mode": "wandering"}
        assert (key not in traits.active(owner)) == entry.bodily
        assert entry.signature.rules or entry.family == "weave"


@pytest.mark.parametrize(
    "key,profile,ward,own,expected",
    [
        (
            "washed_ingot",
            {"physical": 0.2, "water": 0.2, "metal": 0.6},
            None,
            None,
            {"physical": 0.2, "water": 0.4, "metal": 0.4},
        ),
        ("seed_flame", {"wood": 1.0}, None, None, {"wood": 0.75, "fire": 0.25}),
        (
            "echo_strings",
            {"yin": 0.7, "yang": 0.2, "thunder": 0.1},
            None,
            "yin",
            {"yin": 0.2, "yang": 0.7, "thunder": 0.1},
        ),
        ("storm_rod", {"wind": 0.2, "thunder": 0.6, "water": 0.2}, None, "water", {"water": 0.4, "thunder": 0.6}),
        ("split_prism", {"wood": 1.0}, "fire", None, {"wood": 0.8, "fire": 0.2}),
        (
            "hidden_clay",
            {"wood": 0.6, "earth": 0.3, "yin": 0.1},
            "metal",
            "earth",
            {"wood": 0.3, "earth": 0.3, "fire": 0.3, "yin": 0.1},
        ),
        (
            "estuary",
            {"water": 0.45, "metal": 0.15, "fire": 0.30, "wind": 0.1},
            "earth",
            None,
            {"metal": 0.375, "fire": 0.525, "wind": 0.1},
        ),
        (
            "balance_beam",
            {"metal": 0.1, "wood": 0.1, "earth": 0.4, "water": 0.4},
            None,
            "metal",
            {"metal": 0.25, "wood": 0.1, "earth": 0.4, "water": 0.25},
        ),
        (
            "river_chart",
            {"physical": 0.1, "water": 0.3, "metal": 0.4, "yang": 0.2},
            "fire",
            None,
            {"physical": 0.1, "water": 0.7, "yang": 0.2},
        ),
    ],
)
def test_woven_damage_uses_final_shares_and_preserves_source(key, profile, ward, own, expected):
    original = profile.copy()
    result = components(profile, [key], ward, ["five_body"], own)
    assert {k: p["share"] for k, p in result.items()} == pytest.approx(expected)
    assert profile == original
    assert sum(p["share"] for p in result.values()) == pytest.approx(1.0)
    assert all(p["resistance"] == (0.1 if k in FIVE else 0.0) for k, p in result.items())
    physical = components({"physical": 1.0}, [key], ward, ["five_body"], own)
    assert physical["physical"]["multiplier"] == 1.0


@pytest.mark.parametrize("i", range(5))
def test_river_chart_only_redirects_existing_reverse_share_in_live_battle(i):
    ward, strong, weak = FIVE[i], FIVE[i - 1], FIVE[(i + 1) % len(FIVE)]
    enemy = fighter("enemy", "enemy", "river_chart")
    target = fighter("player", "player")
    attrs = dict(target.capabilities.attributes, wards=[ward], ward=ward, ward_sources={ward: ["artifact"]})
    battle = VoisinageBattle([enemy, replace(target, capabilities=replace(target.capabilities, attributes=attrs))])
    begin(battle, 1)
    attack = dict(id="test", name="混元", damage_profile={strong: 0.3, weak: 0.4, "physical": 0.3})
    assert battle.attribute_damage("enemy", "player", 1.0, attack) == pytest.approx(0.7 * 1.2 + 0.3)
    battle.units["player"].controls["artifact"] = "enemy"
    assert battle.attribute_damage("enemy", "player", 1.0, attack) == pytest.approx(1.0)
    assert weak in battle.attribute_hits[-1]["components"]
    del battle.units["player"].controls["artifact"]
    attack["damage_profile"] = {weak: 1.0}
    assert battle.attribute_damage("enemy", "player", 1.0, attack) == pytest.approx(0.8)


@pytest.mark.parametrize("side", ["player", "enemy"])
def test_cicada_requires_three_traded_rounds_and_a_living_host_then_pays_for_two_rounds(side):
    battle = duel("cicada_vessel") if side == "player" else duel(enemy=("cicada_vessel",))
    index = int(side == "enemy")
    retaliation = [(0.0, 0.02), (0.02, 0.21), (0.02, 0.21), (0.02, 0.21)]
    for n, hits in enumerate(retaliation, start=1):
        begin(battle, n)
        battle.ordinary_damage(*(hits if side == "player" else reversed(hits)))
        end(battle)
    state, body = battle.units[side].vitality, battle.units[side].body
    assert state < 0.45
    resumed = load_battle(json.loads(json.dumps(dump_battle(battle))))
    for b in (battle, resumed):
        begin(b, 5)
        assert b.units[side].vitality == pytest.approx(state + 0.18)
        assert b.units[side].body == pytest.approx(min(1.0, body + 0.12))
        for n, outgoing in [(5, 0.035), (6, 0.035), (7, 0.05)]:
            if n > 5:
                begin(b, n)
            assert b.ordinary_damage(0.05, 0.05)[index] == pytest.approx(outgoing)
            end(b)
        before = b.units[side].vitality
        begin(b, 8)
        assert b.units[side].vitality == before


def test_whale_reserve_reduces_two_paid_upkeeps_then_returns_to_full_cost():
    source = fighter("player", "player", "whale_bellows")
    capabilities = caster(
        domain(opening_cost=2, upkeep_cost=10), stance="protect", semantic_rules=source.capabilities.semantic_rules
    )
    battle = VoisinageBattle([actor("player", "player", capabilities), actor("enemy", "enemy")])
    for n, remaining in enumerate((88.0, 80.0, 72.0, 62.0), start=1):
        stats, _ = begin(battle, n)
        assert battle.units["player"].current == pytest.approx(remaining)
        assert stats["player"]["sustain"] == pytest.approx(1.25 if n == 3 else 1.0)
        end(battle)
