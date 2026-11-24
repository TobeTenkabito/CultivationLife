"""Personal lineage sources, conflict resolution and combat effects."""
import copy

import pytest

from cultivation_life import traits
from cultivation_life.combat_attributes import components, resistance, relation
from cultivation_life.content_registry import TECHNIQUE_CATALOG, ITEM_CATALOG
from cultivation_life.models import GameState, Player, SectNpc
from cultivation_life.rules import add_item, learn_technique, remove_item
from cultivation_life.system import trait_study
from cultivation_life.system.natal_binding import bind_standard
from cultivation_life.system.npc_development import service
from cultivation_life.system.npc_techniques import learn
from cultivation_life.trait_lineages import LINEAGES, ARTIFACT_TRAITS


def game_with_player():
    return GameState("lineages", 42, Player("沈宁", "supreme_water", realm_index=3), "created", "revision")


@pytest.mark.parametrize("key", LINEAGES)
def test_curated_sources_and_effects(key):
    row = LINEAGES[key]
    assert row.books or row.artifacts
    assert (key not in traits.MASTERY_ONLY) == row.innate
    assert traits.EFFECTS[key] and traits.TRAITS[key][0] == row.name
    owner = SectNpc("person", "林清", "", 3, 1, 30, 200)
    for identity in row.books:
        learn(owner, TECHNIQUE_CATALOG[identity], level=9)
        assert identity in traits.active(owner)[key]
    for identity in row.artifacts:
        assert set(ITEM_CATALOG[identity].tags) & {"artifact", "equipment"}
        assert ARTIFACT_TRAITS[identity] == key
    assert len(traits.active(owner)) == int(bool(row.books))
    unit = row.percent / 100
    element = row.element
    if row.rule == "signature":
        from cultivation_life.trait_mechanics import SIGNATURES, combat_rules
        from cultivation_life.combat_semantics import parse_rules
        assert traits.EFFECTS[key] == SIGNATURES[key].description
        assert len(parse_rules(combat_rules([key]))) == len(SIGNATURES[key].rules)
    elif row.rule == "resist":
        assert resistance(element, [key]) == pytest.approx(unit)
        assert resistance("physical", [key]) == 0
    elif row.rule == "guard":
        assert relation(element, row.other, (), [key]) == pytest.approx(1 + unit)
        assert relation(row.other, element, (), [key]) == .8
    elif row.rule == "pierce":
        defense = {"yin": ["moon_lamp", "night_sense"], "thunder": ["thunder_bone"],
                   "water": ["fish_scales", "tide_ear"]}[element]
        hit = components({element: 1}, [key], None, defense)[element]
        assert hit["resistance"] == pytest.approx(max(0, resistance(element, defense) - unit))
    elif row.rule == "foundation_practice":
        for realm in (0, 1, 2, 3):
            owner.realm_index = realm
            assert traits.practice_multiplier(owner) == pytest.approx(1 + (unit if realm in (1, 2) else 0))
    elif row.rule in {"practice", "balanced"}:
        owner.body_training = owner.divine_sense_rank = 3
        assert traits.practice_multiplier(owner) == pytest.approx(1 + unit)
        if row.rule == "balanced":
            owner.body_training = 2
            assert traits.practice_multiplier(owner) == 1
    else:
        profile = {element: .5, row.other: .5} if row.rule == "pair" else {element: 1}
        hit = components(profile, [key], None, [], row.other)
        assert all(part["bonus"] == pytest.approx(unit) for part in hit.values())
        if row.rule == "own":
            assert components(profile, [key], None, [])[element]["bonus"] == 0
        if row.rule == "pair":
            assert components({element: 1}, [key], None, [])[element]["bonus"] == 0
        if row.rule == "pure":
            other = "physical" if element != "physical" else "earth"
            mixed = components({element: .5, other: .5}, [key], None, [])
            assert mixed[element]["bonus"] == 0


def test_foundation_practice_upgrade_for_player_and_npc():
    player = game_with_player().player
    npc = SectNpc("student", "陆宁", "", 2, 1, 23, 180)
    for key, trait, gain in (("TECH_BASIC_QI", "first_circuit", .05),
                             ("TECH_HUMAN_HERITAGE_3", "clear_foundation", .09)):
        book = copy.deepcopy(TECHNIQUE_CATALOG[key])
        book.level = 9
        learn_technique(player, book)
        learn(npc, book, level=9)
        for owner in (player, npc):
            owner.realm_index = 2
            assert traits.active(owner) == {trait: [key]}
            assert traits.practice_multiplier(owner) == pytest.approx(1 + gain)
            owner.realm_index = 3
            assert traits.practice_multiplier(owner) == 1


def test_artifact_learning_and_duplicate_book_sources_survive_save_and_wash():
    game = game_with_player()
    p = game.player
    source = "artifact:green_bamboo_sword"
    add_item(p, "green_bamboo_sword")
    before = p.to_dict()
    assert trait_study.options(game, p)[0]["source"] == "青竹飞剑"
    assert p.to_dict() == before
    bind_standard(game, "green_bamboo_sword")
    trait_study.study(game, p, source)
    with pytest.raises(ValueError):
        trait_study.study(game, p, source)
    book = copy.deepcopy(TECHNIQUE_CATALOG["TECH_QINGYUAN_SWORD"])
    book.level = 9
    learn_technique(p, book)
    game.natal_artifact = {}
    game = GameState.from_dict(game.to_dict())
    p = game.player
    assert traits.active(p)["bamboo_edge"] == [source, book.id]
    traits.wash(p, "bamboo_edge")
    with pytest.raises(ValueError):
        trait_study.study(game, p, source)
    assert source not in p.trait_state["mastery"]
    assert traits.mastery(p, book.id)
    with pytest.raises(ValueError):
        traits.validate({"owned": {"bamboo_edge": ["artifact:spirit_sword"]}})


def test_npc_only_uses_actual_equipment_and_contacts():
    game = game_with_player()
    p = game.player
    npc = SectNpc("n", "林清", "", 2, 1, 30, 200, world=p.world, location_id="local")
    p.location_id = "local"
    game.world_npcs[npc.id] = npc
    p.disciples = [game.link_relationship({"id": npc.id})]
    source = "artifact:soul_lamp"
    add_item(p, "soul_lamp")
    npc.treasure_item_id = "soul_lamp"
    with pytest.raises(ValueError):
        service.configure_trait(game, "npc", npc.id, "study", source)
    npc.family_traits["equipment"] = [{"id": "soul_lamp", "name": "守命魂灯", "power": 1}]
    service.configure_trait(game, "npc", npc.id, "study", source)
    assert traits.active(npc)["moon_lamp"] == [source]
    assert p.disciples[0]["trait_state"] == npc.trait_state
    assert not traits.active(p)
    npc.combat_artifact_id = "green_bamboo_sword"
    npc.location_id = "distant"
    with pytest.raises(ValueError):
        service.configure_trait(game, "npc", npc.id, "study", "artifact:green_bamboo_sword")


def test_old_mastery_claim_conflicts_and_stale_inventory_are_rechecked():
    game = game_with_player()
    p = game.player
    book = copy.deepcopy(TECHNIQUE_CATALOG["TECH_METAL_SCRIPTURE"])
    p.known_techniques.append(book)
    book.level = 8
    with pytest.raises(ValueError):
        trait_study.study(game, p, book.id)
    book.level = 9
    trait_study.study(game, p, book.id)
    add_item(p, "guixu_celestial_equipment_03")
    source = "artifact:guixu_celestial_equipment_03"
    option, = trait_study.options(game, p)
    assert option["replaces"] == ["藏锋剑心"]
    remove_item(p, "guixu_celestial_equipment_03")
    with pytest.raises(ValueError):
        trait_study.study(game, p, source)
    assert set(traits.active(p)) == {"sheathed_edge"}
    add_item(p, "guixu_celestial_equipment_03")
    trait_study.study(game, p, source)
    add_item(p, "spirit_sword")
    assert not trait_study.options(game, p)[0]["allowed"]
    with pytest.raises(ValueError):
        trait_study.study(game, p, "artifact:spirit_sword")
    assert set(traits.active(p)) == {"sundering_edge"}


def test_concealment_also_applies_before_first_roster_visit():
    from cultivation_life.system.npc_trait_view import visible_traits
    game = game_with_player()
    game.player.location_id = "local"
    npc = SectNpc("student", "林清", "", 2, 1, 30, 200, world=game.player.world,
                  location_id=game.player.location_id, combat_artifact_id="soul_lamp")
    game.world_npcs[npc.id] = npc
    game.player.disciples = [game.link_relationship({"id": npc.id})]
    game.player.divine_sense_rank = 0
    assert visible_traits(game, npc) is None
    assert npc.concealed_realm_index is None
    with pytest.raises(ValueError, match="尚未探明"):
        service.configure_trait(game, "npc", npc.id, "study", "artifact:soul_lamp")
    assert not traits.active(npc)


def test_npc_trait_visibility_follows_current_person_across_views(tmp_path):
    from pathlib import Path
    from cultivation_life.engine import GameEngine

    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path / "saves")
    initial = engine.create_game("观相", "supreme_water", "dao", 19)
    game = engine.store.load(initial["id"])
    npc = SectNpc("hidden_disciple", "林澜", "", 3, 1, 32, 180, world="human",
                  concealed_realm_index=1, concealed_layer=1)
    game.world_npcs[npc.id] = npc
    game.player.disciples = [game.link_relationship({"id": npc.id})]
    game.player.offspring = [{"id": npc.id, "name": npc.name, "world": npc.world}]
    game.player.divine_sense_rank = 0
    traits.mastery(npc, "light:kan")
    def check(expected):
        data = engine.present(game)
        rows = [next(row for row in group if row["id"] == npc.id) for group in
                (data["world_npcs"], data["player"]["disciples"], data["family"]["offspring"],
                 data["mentorship"]["disciples"])]
        for row in [*rows, rows[-1]["portrait"]]:
            assert row.get("traits") == expected
            assert "trait_state" not in row
    check(None)
    game.player.divine_sense_rank = 99
    check([dict(traits.public(npc)[0], source_names=["坎道玄光"])])
    traits.wash(npc, "fish_scales")
    check([])
    traits.mastery(npc, "light:li")
    npc.world = "spirit"
    npc.departed_age = game.player.age
    check(None)
    assert traits.active(npc) == {traits.MASTERY["light:li"]: ["light:li"]}
