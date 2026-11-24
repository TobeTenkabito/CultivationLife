"""Elemental settlement and trait ownership across real content and save boundaries."""
import copy
import random
from pathlib import Path
from types import SimpleNamespace
import pytest

from cultivation_life import traits
from cultivation_life.combat_attributes import FIVE, PHYSICAL, components, relation, validate_profile
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.models import Item, SectNpc, Technique
from cultivation_life.technique_affinity import can_practice_technique
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle, load_battle


def test_all_attack_sources_and_generated_roundtrip():
    assert all(validate_profile(b.damage_profile) for b in TECHNIQUE_CATALOG.values())
    assert all(validate_profile(i.damage_profile) for i in ITEM_CATALOG.values()
               if set(i.tags) & {"equipment","artifact"})
    assert TECHNIQUE_CATALOG["TECH_BLOOD_RIVER"].element == "neutral"
    assert "water" in TECHNIQUE_CATALOG["TECH_BLOOD_RIVER"].damage_profile
    manual = Technique(id="recipe:1", name="凝潮诀")
    assert manual.damage_profile == {"water":1.}
    item = Item(id="recipe:2",name="镇岳印",tags=["artifact"])
    assert Item.from_dict(item.to_dict()).damage_profile == {"earth":1.}
    with pytest.raises(ValueError):
        Technique(id="invalid", damage_profile={"water": .6})


def test_relations_and_component_order():
    for index, element in enumerate(FIVE):
        target = FIVE[(index+1)%5]
        assert relation(element,target) == 1.2
        assert relation(target,element) == .8
    assert relation("yin","yang") == relation("yang","yin") == 1.2
    assert relation("wind","thunder") == relation("thunder","wind") == .8
    assert relation("wind","thunder",["wind_thunder"]) == .9
    result = components({"physical":.7,"water":.3}, ["strength"],"fire",["fish_scales","tide_ear"])
    assert result["physical"]["multiplier"] == pytest.approx(.7*1.05)
    assert result["water"]["multiplier"] == pytest.approx(.3*1.2*.82)


def test_shared_mastery_replacement_and_wash():
    owner = SectNpc("subject","甲","",3,1,30,200,trait_state={})
    first,second = "TECH_OPEN_HUANGZE_METAL_SUPPORT","light:kan"
    assert traits.mastery(owner,first) and traits.mastery(owner,second)
    assert traits.active(owner)["fish_scales"] == [first,second]
    assert traits.mastery(owner,"TECH_BODY_STARS")
    assert set(traits.active(owner)) == {"star_body"}
    assert not traits.mastery(owner,first)
    traits.wash(owner,"star_body")
    assert traits.mastery(owner,second)
    assert SectNpc.from_dict(owner.to_dict()).trait_state == owner.trait_state
    old = owner.to_dict()
    del old["trait_state"]
    assert SectNpc.from_dict(old).trait_state == {}


def test_birth_and_confluence_and_breakthrough():
    assert traits.birth(71,"npc:3") == traits.birth(71,"npc:3")
    assert {bool(traits.birth(i,"player")) for i in range(100)} == {False,True}
    p = SimpleNamespace(spirit_root="supreme_metal", additional_roots=["metal","water"],
                        trait_state={}, realm_index=2, layer=3)
    traits.grant(p.trait_state,"confluence","先天")
    book = Technique(element="fire",required_affinities=["wood"])
    assert can_practice_technique(p,book)
    book.required_affinities.append("earth")
    assert not can_practice_technique(p,book)
    book.required_affinities=["wind"]
    assert not can_practice_technique(p,book)
    traits.grant(p.trait_state,"heaven","先天")
    traits.grant(p.trait_state,"tenacity","先天")
    assert traits.breakthrough_bonus(p,True) == .25
    for _ in range(5): traits.record_roll(p,False)
    assert traits.breakthrough_bonus(p,True) == .37
    p.layer += 1
    assert traits.breakthrough_bonus(p,True) == .25


def test_ordinary_damage_and_resumed_attack_use_actor_snapshots():
    def actor(key,side,ward,profile,owned):
        attack = dict(name=key,id=key,tier=1,profile=profile)
        stats = dict(attacks={"technique":attack},traits=owned,ward=ward,wards=[ward],flame="fire")
        return Combatant(key,key,side,100,CombatCapabilities(attributes=stats))
    battle = VoisinageBattle([actor("player","player","water",{"physical":.7,"water":.3},["strength"]),
                              actor("enemy","enemy","fire",PHYSICAL,["fish_scales"])])
    restored = load_battle(copy.deepcopy(dump_battle(battle)))
    for b in (battle, restored):
        b.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
        dealt,_ = b.ordinary_damage(.1,0)
        assert dealt == pytest.approx(.1*(.7*1.05+.3*1.2*.88))
        assert b.report()["attribute_hits"][0]["components"]["water"]["resistance"] == .12


def test_single_hit_can_lose_its_only_ward_to_an_artifact_restriction():
    state = dict(attacks={}, traits=[], ward="fire", wards=["fire"], flame="fire",
                 ward_sources={"fire":["artifact"]})
    one = Combatant("one","甲","player",1)
    two = Combatant("two","乙","enemy",1,CombatCapabilities(attributes=state))
    battle = VoisinageBattle([one,two])
    assert battle.active_element_ward("two") == "fire"
    battle.units["two"].controls["artifact"] = "one"
    assert battle.active_element_ward("two") is None


def test_compatible_lower_body_survives_and_exclusive_body_requires_wash():
    state = {}
    assert traits.grant(state,"fish_scales","先天")
    assert traits.grant(state,"five_body","light:qian")
    assert set(state["owned"]) == {"fish_scales","five_body"}
    assert traits.grant(state,"red_bones","先天")
    assert not traits.grant(state,"star_body","TECH_BODY_STARS")
    assert set(state["owned"]) == {"five_body","red_bones"}


def test_expanded_seeded_pool_and_display():
    added = {"green_veins", "thunder_bone", "sun_eye", "sand_skin", "sheathed_edge",
             "stone_frame", "night_sense", "paired_poles", "steam_cycle", "sundering_edge"}
    drawn = set()
    for seed in range(12000):
        record = traits.birth(seed, "player")
        drawn.update(record.get("owned", {}))
    assert {key for key, row in traits.LINEAGES.items() if row.innate and row.rarity in {"绿", "蓝"}} <= drawn
    assert added <= drawn
    assert drawn.isdisjoint(traits.MASTERY_ONLY)
    for key in added | {"mountain_body", "storm_seal"}:
        record = {}
        source = next(s for s, trait in traits.MASTERY.items() if trait == key) if key in traits.MASTERY_ONLY else "先天"
        assert traits.grant(record, key, source)
        row, = traits.public({"trait_state": traits.validate(record)})
        assert row["effect"] and row["family"] and row["sources"] == [source]


def test_elemental_traits_follow_each_hit_and_live_ward():
    hit = components({"wood": .6, "earth": .4}, ["green_veins"], "earth",
                     ["mountain_body", "sand_skin"])
    assert hit["wood"]["multiplier"] == pytest.approx(.6 * 1.05 * 1.05)
    assert hit["earth"]["resistance"] == pytest.approx(.14)
    assert relation("earth", "wood", (), ["mountain_body"]) == .8
    hit = components({"yang": .7, "thunder": .3}, ["paired_poles", "sun_eye", "night_sense", "storm_seal"],
                     "yin", ["thunder_bone"], own_ward="wind")
    assert hit["yang"]["multiplier"] == pytest.approx(.7 * 1.13 * 1.32)
    assert hit["thunder"]["multiplier"] == pytest.approx(.3 * 1.16 * .94)
    assert components({"yin": 1}, ["paired_poles"], "yang", ["night_sense"])["yin"]["multiplier"] == pytest.approx(1.32 * .9)
    assert components({"wind": 1}, ["storm_seal"], None, [], "thunder")["wind"]["bonus"] == .16
    assert components({"wind": 1}, ["storm_seal"], None, [], None)["wind"]["bonus"] == 0
    assert components({"yang": 1}, ["night_sense"], None, [])["yang"]["bonus"] == 0
    for element in ("fire", "water"):
        assert components({element: 1}, ["steam_cycle"], None, [])[element]["bonus"] == 0
    mixed = components({"fire": .3, "water": .6, "physical": .1}, ["steam_cycle"], None, [])
    assert [mixed[k]["bonus"] for k in ("fire", "water", "physical")] == [.14, .14, 0]
    for key, resist in [("sheathed_edge", .1), ("sundering_edge", 0)]:
        pure = components({"metal": 1}, [key], None, ["five_body"])
        mixed = components({"physical": .5, "metal": .5}, [key], None, ["five_body"])
        assert pure["metal"]["multiplier"] == pytest.approx(1.08 * (1 - resist))
        assert mixed["metal"]["multiplier"] == pytest.approx(.5 * (1 - resist))
        assert mixed["physical"]["multiplier"] == .5


def test_mastered_traits_on_player_and_npc_and_body_projection():
    from cultivation_life.models import Player
    from cultivation_life.rules import learn_technique
    from cultivation_life.system.npc_techniques import learn
    from cultivation_life.system.combat_loadout import project_attributes

    player = Player("岳宁", "supreme_earth")
    npc = SectNpc("subject", "陆沉", "", 3, 1, 30, 200)
    for source in ("TECH_EARTH_SCRIPTURE", "TECH_MOUNTAIN_BEARING_BODY", "TECH_MYSTIC_MOUNTAIN",
                   "TECH_METAL_SCRIPTURE", "TECH_TIANJIAN", "TECH_THUNDER_ADVANCED", "TECH_WIND_ADVANCED"):
        book = copy.deepcopy(TECHNIQUE_CATALOG[source])
        book.level = 9
        assert learn_technique(player, book)
        learn(npc, book, level=8)
        assert source not in npc.trait_state.get("mastery", {})
        learn(npc, book, level=9)
    assert player.trait_state == npc.trait_state
    owned = traits.active(npc)
    assert set(owned) == {"mountain_body", "sundering_edge", "storm_seal"}
    assert len(owned["mountain_body"]) == len(owned["storm_seal"]) == 2
    for owner in (player, npc):
        loadout = project_attributes(owner, [], [], player=owner is player)
        assert loadout["ward"] == "earth" and loadout["ward_sources"] == {"earth": ["body"]}
    spirit = npc.to_dict() | {"spirit_state": {"mode": "wandering"}}
    assert "mountain_body" not in traits.active(spirit)
    assert project_attributes(spirit, [], [])["wards"] == []
    assert "storm_seal" in traits.active(spirit)


def test_seed_binds_player_fixed_people_and_generated_encounters(tmp_path):
    from cultivation_life.engine import GameEngine

    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path / "saves")
    seed = 5320

    def create(name, root, preset):
        view = engine.create_game(name, root, "dao", seed, preset_id=preset)
        return engine.store.load(view["id"])

    def encounter(game, rng_seed):
        target = {"combat_type": "cultivator", "members": [{"realm_index": 1, "layer": 1, "power": 10}]}
        engine._cache_encounter_target(game, target, random.Random(rng_seed))
        identity = target["npc_id"]
        person = engine._promote_cached_npc(game, identity, "留名")
        assert person is not None
        counts = game.npc_birth_counts.copy()
        engine._cache_encounter_target(game, target, random.Random(rng_seed + 1))
        assert game.npc_birth_counts == counts
        return person

    first = create("沈甲", "supreme_metal", None)
    second = create("陆乙", "supreme_water", "core")
    assert first.id != second.id
    assert first.player.trait_state == second.player.trait_state == traits.birth(seed, "player")
    assert traits.active(first.player)
    fixed = set(first.world_npcs) & set(second.world_npcs)
    assert any(traits.active(first.world_npcs[key]) for key in fixed)
    for key in fixed:
        assert first.world_npcs[key].trait_state == second.world_npcs[key].trait_state == traits.birth(seed, key)

    from cultivation_life.system.tutorial_mentorship import MENTOR_STEP, mentor_action
    first.player.tutorial_state.update(enabled=True, step=MENTOR_STEP)
    first.pending_event = None
    mentor_action(engine, first, "offer_mentor")
    mentor = first.notable_npcs[first.player.tutorial_state["mentor_id"]]
    assert mentor.trait_state == traits.birth(seed, "tutorial_mentor")
    engine._ensure_merchant(first)
    offices = [office["leader"] for alliance in first.merchant_state["worlds"]["human"]
               for office in alliance["offices"]]
    assert offices and all(npc["trait_state"] == traits.birth(seed, npc["id"]) for npc in offices)

    first_npc = encounter(first, 7)
    second_npc = encounter(second, 19)
    assert first_npc.id != second_npc.id
    assert first_npc.trait_state == second_npc.trait_state == traits.birth(seed, "generated/encounter/0")
    traits.wash(first_npc, next(iter(traits.active(first_npc))))
    traits.wash(first.player, next(iter(traits.active(first.player))))
    first.player.dao_companion = first.link_relationship({"id": "companion", "name": "青禾", "alive": True})
    first.player.guaranteed_progeny = True
    engine._try_conceive_child(first, random.Random(17))
    assert first.player.offspring[-1]["trait_state"] == traits.birth(seed, "generated/child/0")
    assert first.npc_birth_counts["child"] == 1
    engine.store.save(first)
    first = engine.store.load(first.id)
    assert not traits.active(first.player)
    assert not traits.active(first.notable_npcs[first_npc.id])
    assert first.npc_birth_counts["encounter"] == 1
    assert encounter(first, 31).trait_state == encounter(second, 41).trait_state == traits.birth(seed, "generated/encounter/1")

    fixed_key = next(key for key in fixed if traits.active(first.world_npcs[key]))
    fixed_person = first.world_npcs.pop(fixed_key)
    traits.wash(fixed_person, next(iter(traits.active(fixed_person))))
    first.inactive_npcs[fixed_key] = fixed_person
    engine._ensure_world_npcs(first)
    assert fixed_key not in first.world_npcs
    assert not traits.active(first.inactive_npcs[fixed_key])
