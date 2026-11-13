"""Distinct inherited mechanics and a bounded, non-random fusion advantage."""
import copy
import json
from pathlib import Path

import pytest

from cultivation_life.content_registry import CONTENT_DOCUMENTS, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.technique_effect_generation import generate_effect, concordance_effect, upper_effect, attach_effect
from cultivation_life.technique_effect_profiles import PROFILES, THEME_NAMES, GENERATED_BRANCHES
from cultivation_life.technique_effect_schema import validate_effect
from cultivation_life.system.doctrine.generation import generate
from cultivation_life.system.doctrine.fusion import compile_manual, eligible
from cultivation_life.system.combat.trials import dump_battle, load_battle
from test_technique_effect_foundation import battle, begin, manual


def recipe(trigger='opening', kind='guard', **changes):
    base = manual(kind)['effect']
    return validate_effect(base | dict(version=2, generator_version=2, lineage='mountain',
                                      mastery=False, trigger=trigger) | changes)


def book(trigger='opening', kind='guard', **changes):
    return dict(id='lineage-test', name='传承试验', level=1, effect=recipe(trigger, kind, **changes))


@pytest.mark.parametrize('theme', PROFILES)
def test_each_theme_keeps_authored_mechanics_across_seeds(theme):
    for role, index in [('main', 0), ('support', 1), ('combat', 2)]:
        for seed in (1, 17, 910):
            e = generate_effect(seed, 'celestial:test', 'celestial:test:manual:1',
                                feature='frugal', preference=role, theme=theme)
            assert (e['kind'], e['trigger'], e['delivery']) == tuple(PROFILES[theme][index].split(':'))
            assert e['lineage'] == theme and not e['mastery']
            assert e == generate_effect(seed, 'celestial:test', 'celestial:test:manual:1',
                                        feature='frugal', preference=role, theme=THEME_NAMES[theme])


def test_all_theme_suites_are_mechanically_distinct():
    assert len(PROFILES) == len(set(PROFILES.values())) == 32
    assert len(set(PROFILES.values()) | set(GENERATED_BRANCHES.values())) == 34


@pytest.mark.parametrize('seed', [1, 14, 73, 931])
def test_same_world_all_25_doctrines_have_different_mechanical_suites(seed):
    definitions = generate(seed, CONTENT_DOCUMENTS['doctrines.json'], {r: 10**r for r in range(9, 13)})['definitions']
    suites = {tuple((b['combat_effect']['kind'], b['combat_effect']['trigger'], b['combat_effect']['delivery'])
                    for b in d['manuals'][:3]) for d in definitions.values()}
    assert len(suites) == 25


def test_fusion_inherits_main_mechanism_and_strictly_beats_ordinary_budget():
    config = CONTENT_DOCUMENTS['doctrines.json']
    for seed in (14, 73, 931):
        for d in generate(seed, config, {r: 10 ** r for r in range(9, 13)})['definitions'].values():
            if not eligible(d):
                continue
            before = copy.deepcopy(d)
            fused = compile_manual(seed, d, config['words'])['combat_effect']
            first = d['manuals'][0]['combat_effect']
            assert fused['mastery'] and fused['lineage'] == first['lineage']
            assert all(fused[k] == first[k] for k in ('kind', 'trigger', 'delivery'))
            assert fused['strength_bp'] == (180 if first['kind'] in {'guard', 'frugal', 'recover'} else 1200)
            assert fused['cost_bp'] < min(b['combat_effect']['cost_bp'] for b in d['manuals'])
            assert fused['cooldown'] < min(b['combat_effect']['cooldown'] for b in d['manuals'])
            assert d == before


def test_fusion_from_legacy_recipe_preserves_signature_and_does_not_reroll_it():
    old = manual('strike', trigger='after_hurt', delivery='split')['effect']
    books = [dict(growth_preference='main', combat_effect=old)]
    e = concordance_effect(books, seed=1, doctrine_id='celestial:test', feature='frugal', theme='混元')
    assert all(e[k] == old[k] for k in ('kind', 'trigger', 'delivery'))
    row = dict(combat_effect=copy.deepcopy(old), description='原冻结文本')
    assert not attach_effect(row, 333, feature='frugal', theme='origin')
    assert row['combat_effect'] == old and row['description'] == '原冻结文本'


@pytest.mark.parametrize('level', range(1, 10))
def test_fused_guard_really_prevents_more_and_spends_less_at_equal_level(level):
    original = recipe(strength_bp=150, cost_bp=200, cooldown=1)
    fused = concordance_effect([dict(growth_preference='main', combat_effect=original)],
        seed=1, doctrine_id='celestial:test', feature='fortify', theme='mountain')
    ordinary = battle(dict(id='ordinary', name='普通', level=level, effect=original))
    mastery = battle(dict(id='mastery', name='真传', level=level, effect=fused))
    begin(ordinary, 1)
    begin(mastery, 1)
    assert ordinary.ordinary_damage(0, .1)[1] == pytest.approx(.085)
    assert mastery.ordinary_damage(0, .1)[1] == pytest.approx(.082)
    assert mastery.units['player'].current > ordinary.units['player'].current
    assert 100 - mastery.units['player'].current == pytest.approx((100 - ordinary.units['player'].current) * .8)


@pytest.mark.parametrize('world', ['asura', 'nether', 'reincarnation'])
def test_three_world_original_catalog_has_frozen_effects_and_preserves_identity(world):
    for grade in range(9, 13):
        for role in ('MAIN', 'COMBAT', 'BODY', 'SENSE'):
            t = TECHNIQUE_CATALOG[f'TECH_{world.upper()}_{grade}_{role}']
            assert t.combat_effect['version'] == 3
            assert t.combat_effect['identity'] == t.id and t.combat_effect['resource'] == 'energy'
            assert t.description and t.grade == grade
            assert not t.requires_immortal_power
            assert not t.effective_worlds  # Retain original portability; no new world gate.
    other = [upper_effect(w, 'COMBAT', 9) for w in ('asura', 'nether', 'reincarnation')]
    assert len({(e['trigger'], e['delivery']) for e in other}) == 3


@pytest.mark.parametrize('trigger,expected', [('odd_round', [1, 3, 5]), ('even_round', [2, 4, 6]),
    ('first_exchange', [1]), ('steady', [3, 4, 5])])
def test_new_timing_uses_real_rounds_and_paid_receipts(trigger, expected):
    b = battle(book(trigger, kind='breach', cooldown=0, duration=1))
    paid_at = []
    for n in range(1, 7):
        before = b.units['player'].current
        begin(b, n)
        if b.units['player'].current < before:
            paid_at.append(n)
    assert paid_at == expected


def test_low_state_checks_original_owner_not_side_average():
    b = battle(book('low_state'))
    begin(b, 1)
    assert b.units['player'].current == 100
    b.ordinary_damage(0, .51)
    begin(b, 2)
    assert b.units['player'].current == 98


def test_target_wounded_does_not_grant_tier_or_reach():
    from dataclasses import replace
    b = battle(book('target_wounded', 'strike'))
    begin(b, 1)
    assert b.units['player'].current == 100
    b.ordinary_damage(.51, 0)
    enemy = b.units['enemy-0']
    enemy.unit = replace(enemy.unit, capabilities=replace(enemy.unit.capabilities, ward_tier=2))
    begin(b, 2)
    assert b.units['player'].current == 100
    enemy.unit = replace(enemy.unit, capabilities=replace(enemy.unit.capabilities, ward_tier=1))
    begin(b, 3)
    assert b.units['player'].current == 98


def test_first_exchange_survives_json_resume_and_cannot_be_reintroduced():
    b = battle(book('first_exchange', 'strike'))
    begin(b, 1)
    b.ordinary_damage(.1, 0)
    snapshot = json.loads(json.dumps(dump_battle(b)))
    resumed = load_battle(snapshot)
    begin(resumed, 2)
    assert resumed.units['player'].current == 98
    assert load_battle(dump_battle(resumed)).units['player'].current == 98
    snapshot['technique_runtime']['first_exchanges'] = {}
    with pytest.raises(ValueError):
        load_battle(snapshot)


def test_version_one_snapshot_still_resumes_without_rewriting_its_recipe():
    b = battle(manual())
    begin(b, 1)
    snapshot = dump_battle(b)
    snapshot['technique_runtime']['version'] = 1
    snapshot['technique_runtime'].pop('first_exchanges')
    resumed = load_battle(snapshot)
    assert next(iter(resumed.techniques.books.values()))[1]['effect']['version'] == 1
    begin(resumed, 2)
    assert resumed.units['player'].current == 98
    assert load_battle(dump_battle(resumed)).units['player'].current == 98


def test_mastery_caps_are_not_available_to_ordinary_books():
    with pytest.raises(ValueError):
        recipe(strength_bp=180)
    assert recipe(strength_bp=180, mastery=True)['strength_bp'] == 180
    with pytest.raises(ValueError):
        recipe(strength_bp=181, mastery=True)
    with pytest.raises(ValueError):
        recipe(mastery=True, lineage='asura')


def test_upper_content_generator_is_idempotent():
    from tools.generate_upper_technique_effects import build, render
    original = (Path(__file__).resolve().parents[1] / 'content/techniques.json').read_text(encoding='utf-8')
    document = json.loads(original)
    assert build(document) == 0
    assert render(original, document) == original


def test_original_technique_card_and_catalog_text_show_frozen_mechanics():
    from cultivation_life.rules import technique_special_effect, public_catalog_entry
    from cultivation_life.models import Technique
    t = TECHNIQUE_CATALOG['TECH_ASURA_9_MAIN']
    assert t.description in technique_special_effect(t)
    listing = dict(kind='technique', content_id=t.id, name=t.name, description='原货单', price=500)
    once = public_catalog_entry(listing)
    assert t.description in once['description'] and once['price'] == 500
    assert public_catalog_entry(once) == once and listing['description'] == '原货单'
    assert technique_special_effect(Technique()) == ''
    assert technique_special_effect(Technique(ignore_possession_limit=True)).startswith('习得后不受成功夺舍次数上限限制')


@pytest.mark.parametrize('world,path', [('asura', 'demonic'), ('nether', 'monster'), ('reincarnation', 'ghost')])
def test_three_world_acquisition_projection_and_save_use_original_player_and_npc(tmp_path, world, path):
    from cultivation_life.engine import GameEngine
    from cultivation_life.models import SectNpc
    from cultivation_life.rules import learn_technique, assign_technique
    from cultivation_life.system.technique_effect_provider import project
    from cultivation_life.system.npc_techniques import learn
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    species = next(iter(WORLD_SYSTEMS['monster_species'])) if path == 'monster' else None
    made = engine.create_game('传承验收', 'supreme_metal', path, seed=700, preset_id=world + '_upper',
                              monster_species_id=species)
    game = engine.store.load(made['id'])
    original = copy.deepcopy(TECHNIQUE_CATALOG[f'TECH_{world.upper()}_9_MAIN'])
    learn_technique(game.player, original)
    assign_technique(game.player, original, 'main')
    from cultivation_life.system.duel_techniques import select
    assign_technique(game.player, copy.deepcopy(original), 'combat')
    select(game.player, original.id)
    projected = project(game, game.player, player=True)
    assert any(r['id'] == original.id and r['effect'] == original.combat_effect for r in projected)
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    assert project(loaded, loaded.player, player=True) == projected
    npc = SectNpc('lineage-npc', '传承人物', '', 9, 1, 1000, None, world=world, path=path, spirit_root='supreme_metal')
    learn(npc, original, level=3, slot='main')
    npc.duel_technique_ids = [original.id]
    npc_effects = project(game, npc)
    assert npc_effects[0]['effect'] == original.combat_effect and npc_effects[0]['level'] == 3
    assert npc.world == world and npc.technique_levels[original.id] == 3
