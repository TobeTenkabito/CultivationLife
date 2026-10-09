"""Player encyclopedia release and upper achievements use existing authority only."""
import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.achievements import AchievementSystem, load_achievement_definitions
from cultivation_life.content_registry import CONTENT_DOCUMENTS, ContentRegistry, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.system import monster_true_form, ghost_soul_form
from cultivation_life.rules import add_item, opportunity_required
from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance
import random

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    e = GameEngine(ROOT, tmp_path)
    shown = e.create_game('修持成就', 'mutated_yin', 'monster', 270, preset_id='nether_upper', monster_species_id='serpent')
    return e, e._load(shown['id'])


def matches(e, g, condition):
    before = copy.deepcopy(g.to_dict())
    result = e.achievements._matches(condition, g, player_rank=None)
    assert g.to_dict() == before, 'Achievement checks must not initialize state or consume RNG/resources'
    return result


@pytest.mark.parametrize('rank', [9, 10, 11, 12])
def test_upper_realm_thresholds_and_world_scope(ready, rank):
    e, g = ready
    g.player.realm_index = rank
    assert matches(e, g, {'upper_realm_at_least': rank})
    assert not matches(e, g, {'upper_realm_at_least': rank + 1})
    g.player.world = 'human'
    assert not matches(e, g, {'upper_realm_at_least': rank})


@pytest.mark.parametrize('world,path', [('asura', 'demonic'), ('nether', 'monster'), ('reincarnation', 'ghost')])
def test_institution_requires_real_seat_not_rank_only(ready, world, path):
    e, g = ready
    g.player.world, g.player.path = world, path
    state = g.upper_institutions.setdefault(world, {})
    state.update(joined=True, rank=len(WORLD_SYSTEMS['upper_institutions']['worlds'][world]['ranks']) - 1)
    if world == 'asura':
        state['court'] = {'holders': {'5': 'someone-else'}}
        assert not matches(e, g, {'upper_institution': world})
        state['court']['holders']['5'] = 'player'
    elif world == 'nether':
        state.update(bloc=2, support=[60]*5, seat_active=False)
        assert not matches(e, g, {'upper_institution': world})
        state['seat_active'] = True
        state['support'][2] = 49
        assert not matches(e, g, {'upper_institution': world})
        state['support'][2] = 50
    else:
        state['rank'] -= 1
        assert not matches(e, g, {'upper_institution': world})
        state['rank'] += 1
    assert matches(e, g, {'upper_institution': world})
    state['joined'] = False
    assert not matches(e, g, {'upper_institution': world})


def test_real_confirmation_and_training_unlock_once_and_pay_cost(ready):
    e, g = ready
    g.player.opportunity = opportunity_required(g.player)
    add_item(g.player, 'spirit_stone', 100000000)
    material = WORLD_SYSTEMS['upper_voisinages']['worlds']['nether']['material_id']
    rng = random.Random(270)
    definition = crafting_material_definitions()[material]
    g.player.crafting_materials += [make_crafting_material_instance(definition, rng, source='test', origin_world='nether') for _ in range(20)]
    e.store.save(g)
    shown = e.upper_voisinage_action(g.id, 'true_form_confirm', 'suppress')
    assert 'monster_true_form_confirmed' in {r['id'] for r in shown['new_achievements']}
    g = e._load(g.id)
    key = monster_true_form.stored(g.player)['blueprint_id']
    for _ in range(4):
        e.upper_voisinage_action(g.id, 'train', key)
    g = e._load(g.id)
    secondary = next(v for v in monster_true_form.public(g.player)['secondary_choices'] if v != 'suppress')
    e.upper_voisinage_action(g.id, 'true_form_secondary', secondary)
    g = e._load(g.id)
    # Realm ten is the existing gate for the fifth rank; the actual train entry pays the quoted cost.
    g.player.realm_index = 10
    g.player.opportunity = opportunity_required(g.player)
    e.store.save(g)
    before = e._load(g.id)
    shown = e.upper_voisinage_action(g.id, 'train', key)
    assert {'monster_true_form_transformed', 'cultivation_voisinage_transformed'} <= {r['id'] for r in shown['new_achievements']}
    after = e._load(g.id)
    assert after.player.opportunity < before.player.opportunity
    assert sum(i.quantity for i in after.player.inventory if i.id == 'spirit_stone') < sum(i.quantity for i in before.player.inventory if i.id == 'spirit_stone')
    assert after.rng_state == before.rng_state
    assert not e.present(after)['new_achievements']


@pytest.mark.parametrize('kind', ['monster', 'ghost'])
def test_personal_forms_validate_blueprint_dlc_and_thirteen_rank(ready, kind):
    e, g = ready
    p = g.player
    if kind == 'monster':
        authority = monster_true_form
        authority.configure(p, 'true_form_confirm', 'suppress')
        key = authority.stored(p)['blueprint_id']
        state = p.world_voisinages['nether']
        state['levels'] = {key: 4}
        secondary = next(v for v in authority.public(p)['secondary_choices'] if v != 'suppress')
        authority.configure(p, 'true_form_secondary', secondary)
        state['levels'][key] = 8
        authority.configure(p, 'true_form_tuning', 'balanced')
        document = 'monster_true_forms.json'
    else:
        p.world, p.path = 'reincarnation', 'ghost'
        authority = ghost_soul_form
        authority.confirm(g, 'battle_scars', 'sever')
        key = authority.stored(p)['blueprint_id']
        state = p.world_voisinages['reincarnation']
        state['levels'] = {key: 4}
        authority.configure(p, 'soul_form_secondary', 'suppress')
        state['levels'][key] = 8
        authority.configure(p, 'soul_form_feature', 'execution')
        document = 'ghost_soul_forms.json'
    assert matches(e, g, {'personal_form': {'kind': kind}})
    perfected = {'personal_form': {'kind': kind, 'minimum': 13, 'finalized': True}}
    state['levels'][key] = 9
    assert not matches(e, g, perfected)
    state['levels'][key] = 13
    authority.stored(p)['finalized'] = True
    assert matches(e, g, perfected)
    assert matches(e, g, {'voisinage_rank_at_least': 13})
    with patch.dict(CONTENT_DOCUMENTS, {document: {}}):
        assert not matches(e, g, perfected)
        assert not matches(e, g, {'personal_form': {'kind': kind}})
    authority.stored(p)['blueprint_id'] = 'forged'
    assert not matches(e, g, perfected)


def test_magic_domain_requires_loaded_dlc_and_confirmed_route(ready):
    e, g = ready
    g.player.world, g.player.path = 'asura', 'demonic'
    g.player.asura_cultivation.update(level=1, domain_rank=13)
    cond = {'asura_attainment': {'domain_rank': 13}}
    assert not matches(e, g, cond)
    g.player.asura_cultivation['route'] = 'asura'
    assert matches(e, g, cond)
    with patch.dict(WORLD_SYSTEMS, {'asura_manifestation': {}}):
        assert not matches(e, g, cond)


@pytest.mark.parametrize('rank,transformed,perfected', [(4, False, False), (5, True, False), (9, True, False), (12, True, False), (13, True, True)])
def test_celestial_attainment_requires_real_doctrine_and_current_stage(ready, rank, transformed, perfected):
    e, g = ready
    g.player.world = 'celestial'
    g.doctrine_state = {'definitions': {'known': {'id': 'known'}}, 'player': {
        'progress': {'known': {'level': 4}}, 'voisinage_training': {'known': {'rank': rank}}}}
    assert matches(e, g, {'voisinage_rank_at_least': 5}) is transformed
    assert matches(e, g, {'voisinage_rank_at_least': 13}) is perfected
    g.doctrine_state['player']['progress']['known']['level'] = 3
    assert not matches(e, g, {'voisinage_rank_at_least': 5})
    g.doctrine_state['player']['progress']['known']['level'] = 4
    g.doctrine_state['definitions'] = {}
    assert not matches(e, g, {'voisinage_rank_at_least': 5})


def test_disabled_dlc_catalog_hides_entries_but_keeps_global_unlock(ready, tmp_path):
    e, g = ready
    definitions = e.achievements.definitions
    rows = {r['id']: r for r in definitions}
    sources = {'monster_true_form_confirmed': 'official.monster-bloodlines',
               'ghost_soul_form_confirmed': 'official.ghost-reincarnation',
               'asura_natal_manifestation': 'official.asura-manifestation'}
    for key, source in sources.items():
        assert rows[key]['source']['id'] == source
    e.achievements.metadata.unlock([rows['monster_true_form_confirmed']], g)
    preferences = {f'official.{p.name}': False for p in (ROOT/'dlc').iterdir() if (p/'manifest.json').is_file()}
    with patch('cultivation_life.system.extension_system.read_extension_preferences', return_value=preferences), \
         patch.object(ContentRegistry, 'loaded_documents', CONTENT_DOCUMENTS), \
         patch.object(ContentRegistry, 'extension_report', ContentRegistry.extension_report):
        ContentRegistry.load(ROOT/'content', ROOT)
        pure = load_achievement_definitions(ContentRegistry.loaded_documents['achievements.json'])
    base = AchievementSystem(pure, tmp_path)
    assert all(r['source']['kind'] == 'base' for r in base.public_catalog()['achievements'])
    assert 'monster_true_form_confirmed' in base.metadata.read()['achievements']
    assert next(r for r in e.achievements.public_catalog()['achievements'] if r['id'] == 'monster_true_form_confirmed')['unlocked']
