"""Attained births and optional true forms through the shared domain contract."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from cultivation_life.models import Player
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import CONTENT_DOCUMENTS, MONSTER_SPECIES, MONSTER_EVOLUTIONS, MONSTER_BLOODLINE_SETTINGS, WORLD_SYSTEMS
from cultivation_life.engine.orchestration.dlc_birth import monster
from cultivation_life.system import monster_true_form as form
from cultivation_life.system.custom_lineage_system import normalize_rules
from cultivation_life.system.upper_voisinage import public_upper_voisinages, player_source, quote
from cultivation_life.system.upper_voisinage_rules import project
from cultivation_life.monster_true_form_content import validate as validate_catalog
from cultivation_life.rules import add_item, opportunity_required

ROOT = Path(__file__).resolve().parents[1]


def test_ninth_asura_birth_preserves_one_time_fusion_choice(tmp_path):
    e = GameEngine(ROOT, tmp_path)
    shown = e.create_game('初入修罗', 'mutated_yin', 'demonic', 251, preset_id='asura_upper')
    p = e._load(shown['id']).player
    assert not p.asura_cultivation.get('route')
    assert p.asura_cultivation['branches'] and p.asura_cultivation['souls'] > 0


def native(species='serpent', route='ancestral'):
    p = Player('本相', 'supreme_metal', path='monster', world='nether', realm_index=9,
               monster_species_id=species, monster_evolution_id=f'{species.upper()}_NETHER_TRUE_1')
    if route == 'self':
        p.monster_evolution_id = f'{species.upper()}_NETHER_SELF_1'
        rules, cost = normalize_rules([dict(phase='round_start', schedule='every', condition='always',
            target='player', effect='might', value=.03)], MONSTER_BLOODLINE_SETTINGS['custom_lineage'], slots=2, budget=24)
        p.monster_custom_lineage_id = 'confirmed-founder'
        p.monster_custom_lineage = dict(id='confirmed-founder', founder_species_id=species, name='自在祖脉',
            finalized_stage=1, rules=rules, spent_points=cost)
    return p


@pytest.mark.parametrize('species', list(MONSTER_SPECIES))
@pytest.mark.parametrize('route', ['ancestral', 'self'])
def test_eight_origins_two_routes_stable_single_source(species, route):
    p = native(species, route)
    before = p.to_dict()
    preview = form.public(p)
    assert not preview['reason'] and p.to_dict() == before
    primary = preview['choices'][-1]
    form.configure(p, 'true_form_confirm', primary)
    key = form.stored(p)['blueprint_id']
    assert not player_source(p).voisinages
    state = p.world_voisinages['nether']
    state.update(levels={key:3}, active=key)
    assert len(player_source(p).voisinages[0].effects) == 1
    secondary = next(e for e in preview['secondary_choices'] if e != primary)
    form.configure(p, 'true_form_secondary', secondary)
    state['levels'][key] = 6
    form.configure(p, 'true_form_tuning', 'balanced')
    state['levels'][key] = 9
    state['true_form']['finalized'] = True
    source = player_source(p)
    assert len(source.voisinages) == 1
    assert len(source.voisinages[0].effects) == 2
    assert len(source.voisinages[0].features) == 1
    assert source.voisinages[0].upkeep_cost > 0
    assert source.voisinages[0].opening_cost > 0
    restored = Player.from_dict(p.to_dict())
    snap = restored.to_dict()
    for _ in range(3):
        assert form.validate(restored)['blueprint_id'] == key
        assert len(public_upper_voisinages(restored)['rows']) == 3
    assert restored.to_dict() == snap
    for away in ['human', 'spirit', 'celestial', 'reincarnation']:
        restored.world = away
        assert not player_source(restored).voisinages
    restored.world = 'nether'
    with patch.dict(CONTENT_DOCUMENTS, {'monster_true_forms.json':{}}):
        assert form.public(restored) is None
        assert len(public_upper_voisinages(restored)['rows']) == 2
        assert not player_source(restored).voisinages
    assert player_source(restored).voisinages[0].id == key
    assert restored.world_voisinages == p.world_voisinages


@pytest.mark.parametrize('species', list(MONSTER_SPECIES))
def test_all_realm_birth_routes_and_awakenings(species):
    for realm in [3, 6, 9, 10, 11, 12]:
        p = native(species); p.realm_index = realm
        monster(p, 251)
        assert MONSTER_EVOLUTIONS[p.monster_evolution_id]['realm_index'] == realm
        assert len(p.monster_generated_bloodline_traits) == realm
        assert len(set(p.monster_evolution_history)) == len(p.monster_evolution_history)
        for parent, child in zip(p.monster_evolution_history, p.monster_evolution_history[1:]):
            assert parent in MONSTER_EVOLUTIONS[child]['parents']
        if realm >= 9:
            assert not form.public(p)['reason']
        restored = Player.from_dict(p.to_dict())
        assert restored.monster_generated_bloodline_traits == p.monster_generated_bloodline_traits


@pytest.mark.parametrize('corruption', ['id', 'origin', 'snapshot', 'version', 'tuning'])
def test_invalid_blueprint_dormant_not_rewritten(corruption):
    p = native(route='self'); form.configure(p, 'true_form_confirm', 'suppress')
    data = form.stored(p)
    if corruption == 'id': data['blueprint_id'] = 'forged'
    if corruption == 'origin': data['origin_species_id'] = 'fox'
    if corruption == 'snapshot': data['lineage_rules'][0]['value'] = 900
    if corruption == 'version': data['blueprint_version'] = 99
    if corruption == 'tuning': data.update(tuning='ward', tuning_locked=True)
    snapshot = p.to_dict()
    assert form.public(p)['reason']
    assert not form.definition(p)
    assert p.to_dict() == snapshot
    with pytest.raises(ValueError): form.configure(p, 'true_form_confirm', 'suppress')
    assert p.to_dict() == snapshot


@pytest.mark.parametrize('path,world', [('monster','nether'), ('ghost','reincarnation'), ('demonic','asura'), ('confucian','spirit'), ('buddhist','spirit')])
def test_public_custom_birth_dlc_and_load_stability(tmp_path, path, world):
    e = GameEngine(ROOT, tmp_path)
    realm = 11 if path in {'monster','ghost','demonic'} else 6
    shown = e.create_game('前尘', 'supreme_metal', path, 251, monster_species_id='fox',
        custom_start=dict(world=world, realm_index=realm, layer=9))
    g = e._load(shown['id']); p = g.player
    if path == 'monster': assert p.monster_evolution_id == 'FOX_NETHER_TRUE_3' and len(p.monster_generated_bloodline_traits) == 11
    if path == 'ghost':
        assert len(p.ghost_bound_souls) == 10 and len(p.ghost_soul_slots) == 10 and p.ghost_wangsheng_energy > 0
        assert not p.ghost_reincarnation_imprints
    if path == 'demonic':
        assert p.asura_cultivation['route'] == 'yaksha' and p.asura_cultivation['powers']
        assert p.asura_cultivation['veins']['11'] == 24
    if path == 'confucian': assert p.haoran_exp > 0 and p.sage_effects
    if path == 'buddhist': assert g.buddhist_state['wish']['value'] > 0
    snapshot = e._load(g.id).to_dict()
    assert e._load(g.id).to_dict() == snapshot


def test_actual_train_gates_payments_confirmation_and_energy(tmp_path):
    from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance
    from cultivation_life.engine.combat_capabilities import bind_capabilities
    from cultivation_life.system.combat_system import BattleUnit
    e = GameEngine(ROOT, tmp_path)
    shown = e.create_game('铸域', 'supreme_metal', 'monster', 251, preset_id='nether_upper', monster_species_id='avian')
    g = e._load(shown['id']); g.pending_event = None; e.store.save(g)
    reserve, rng, age = copy.deepcopy(g.player.immortal_aperture), g.rng_state, g.player.age
    e.upper_voisinage_action(g.id, 'true_form_confirm', 'strike')
    g = e._load(g.id); key = form.stored(g.player)['blueprint_id']
    assert g.player.immortal_aperture == reserve and g.rng_state == rng
    assert g.player.world_voisinages['nether']['levels'].get(key, 0) == 0
    for target in range(1,10):
        g = e._load(g.id)
        g.player.realm_index = WORLD_SYSTEMS['upper_voisinages']['realms'][target-1]
        g.player.opportunity = opportunity_required(g.player)
        add_item(g.player, 'spirit_stone', 10**7)
        cost = quote(g.player, target, g)
        material = crafting_material_definitions()[cost['material_id']]
        g.player.crafting_materials.extend(make_crafting_material_instance(material, random.Random(i), source='test', origin_world='nether') for i in range(cost['materials']))
        e.store.save(g)
        if target in (4,7):
            before = e._load(g.id).to_dict()
            with pytest.raises(ValueError, match='先'):
                e.upper_voisinage_action(g.id, 'train', key)
            assert e.store.load(g.id).to_dict() == before
            e.upper_voisinage_action(g.id, 'true_form_secondary' if target==4 else 'true_form_tuning', 'restrict' if target==4 else 'assault')
        before = e._load(g.id)
        e.upper_voisinage_action(g.id, 'train', key)
        after = e._load(g.id)
        assert before.player.opportunity - after.player.opportunity == cost['opportunity']
        assert before.player.immortal_aperture == after.player.immortal_aperture
    assert form.stored(after.player)['finalized'] and after.player.age == age
    e.upper_voisinage_action(g.id, 'select', key)
    g = e._load(g.id); g.player.immortal_aperture['current'] = 500
    target = dict(target_name='验证敌手',target_power=100,target_realm_index=9,combat_type='cultivator')
    binding = bind_capabilities(g, [BattleUnit('player',g.player.name,'player',100,12)],target,WORLD_SYSTEMS['transcendent_combat'])
    binding.battle.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    binding.commit(binding.battle.updates())
    assert 0 < g.player.immortal_aperture['current'] < 500
    assert len(player_source(g.player).voisinages) == 1


@pytest.mark.parametrize('bad', ['species','effects','feature','budget','nan','script'])
def test_reject_malformed_dlc_before_gameplay(bad):
    doc = copy.deepcopy(CONTENT_DOCUMENTS['monster_true_forms.json']); row = doc['forms']['serpent']
    if bad == 'species': del doc['forms']['avian']
    if bad == 'effects': row['effects'] = ['strike','restore_money']
    if bad == 'feature': row['feature']['value'] = .9
    if bad == 'budget': row['stability'] = 1.3
    if bad == 'nan': row['stability'] = float('nan')
    if bad == 'script': row['execute'] = 'print(1)'
    with pytest.raises(ValueError): validate_catalog(doc, MONSTER_SPECIES)
