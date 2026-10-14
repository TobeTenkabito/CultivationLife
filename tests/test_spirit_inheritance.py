"""Actual HTTP inheritance, branch-specific progression and conservative transfers."""
import copy
import random
from pathlib import Path
from unittest.mock import patch
import pytest

from test_other_systems_audit_fixes import api, snapshot
from cultivation_life.content_registry import WORLD_SYSTEMS, CONTENT_DOCUMENTS
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.spirit_voisinage import catalog, grant, player_source
from cultivation_life.system.spirit_sources import origin
from cultivation_life.system.spirit_inheritance import public
from cultivation_life.system.spirit_inheritance_rules import key, study_years
from cultivation_life.system.upper_voisinage_rules import player_source as upper_source
from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance

ROOT = Path(__file__).resolve().parents[1]


def prepared(engine, world='celestial', path='dao', source_world='celestial', level=9):
    made = engine.create_game('传承验收', 'mutated_yin' if path == 'ghost' else 'supreme_metal', path, 591,
        monster_species_id='serpent' if path == 'monster' else None,
        custom_start=dict(world=world, realm_index=9, layer=1))
    game = engine._load(made['id'])
    game.pending_event = None
    game.settings['silent_events'] = True
    p = game.player
    p.next_tribulation_age = None
    p.opportunity = 10**10
    p.immortal_traces = 10000
    add_item(p, 'spirit_stone', 10**8)
    book = next(b for b in catalog(game).values() if origin(b.spirit_voisinage_id) == source_world)
    grant(game, book.id, level)
    if world != 'celestial':
        material = crafting_material_definitions()[WORLD_SYSTEMS['upper_voisinages']['worlds'][world]['material_id']]
        p.crafting_materials.append(make_crafting_material_instance(material, random.Random(1), source='test', origin_world=world))
    p.hp, p.mp = max_hp(p), max_mp(p)
    engine.store.save(game)
    return game, book


@pytest.mark.parametrize('world', [w for w,p in WORLD_SYSTEMS['world_profiles'].items() if p.get('tier') == 2])
def test_four_origins_are_available_in_all_secondary_worlds(api, world):
    engine, _ = api
    game, _ = prepared(engine)
    from cultivation_life.system.spirit_voisinage import secondary
    assert secondary(world)
    game.player.world = world
    books = catalog(game)
    assert len(books) == 31
    assert {origin(b.spirit_voisinage_id) for b in books.values()} == {'celestial','asura','nether','reincarnation'}
    book = next(b for b in books.values() if origin(b.spirit_voisinage_id) == 'asura')
    grant(game, book.id, 4)
    game.player.spirit_voisinage_manual = book.id
    assert len(player_source(game).voisinages) == 1


@pytest.mark.parametrize('source_world', ['celestial','asura','nether','reincarnation'])
def test_celestial_completion_retains_notes_origin_gates_and_reserves(api, source_world):
    engine, act = api
    game, book = prepared(engine, source_world=source_world)
    p = game.player
    before_reserve = copy.deepcopy(p.immortal_aperture)
    before_origin = game.doctrine_state['player'].get('origin')
    before_rng = game.rng_state
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id)
    saved = engine._load(game.id)
    record = saved.doctrine_state['player']
    assert saved.player.age == p.age and saved.rng_state == before_rng
    assert saved.player.immortal_aperture == before_reserve
    assert record.get('origin') == before_origin
    identity = book.spirit_voisinage_id
    assert record.get('progress', {}).get(identity, {}).get('level', 0) == 0
    assert not record.get('annotations', {}).get(identity)
    assert study_years(saved, identity, 1) == 70
    assert study_years(saved, identity, 5) == 650
    manuals = [t for t in saved.player.known_techniques if t.doctrine_id == identity]
    assert manuals and max(t.level for t in manuals) == 4
    frozen = snapshot(engine, game.id)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'doctrine-action', action='study', doctrine_id=identity, status=400)


@pytest.mark.parametrize('world', ['asura','nether','reincarnation'])
@pytest.mark.parametrize('source_world', ['celestial','asura','nether','reincarnation'])
def test_base_worlds_start_at_one_and_reuse_local_training(api, world, source_world):
    engine, act = api
    game, book = prepared(engine, world=world, source_world=source_world)
    reserve = copy.deepcopy(game.player.immortal_aperture)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id)
    saved = engine._load(game.id)
    identity = key(world, book.spirit_voisinage_id)
    assert saved.player.world_voisinages[world]['levels'][identity] == 1
    assert saved.player.immortal_aperture == reserve
    source = upper_source(saved.player)
    assert len(source.voisinages) == 1 and source.voisinages[0].id == identity
    assert source.voisinages[0].stability + source.voisinages[0].incursion + source.voisinages[0].authority <= 331
    act(game.id, 'upper-voisinage', action='train', voisinage_id=identity)
    assert engine._load(game.id).player.world_voisinages[world]['levels'][identity] == 2
    assert engine._load(game.id).player.age == game.player.age
    frozen = snapshot(engine, game.id)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen


@pytest.mark.parametrize('condition', ['unconverted','low_level','poor','suppressed'])
def test_rejection_is_atomic_and_preview_pure(api, condition):
    engine, act = api
    game, book = prepared(engine)
    p = game.player
    if condition == 'unconverted': p.immortal_power_converted = False
    if condition == 'low_level': next(t for t in p.known_techniques if t.id == book.id).level = 3
    if condition == 'poor': p.immortal_traces = 0
    if condition == 'suppressed': p.cultivation_suppression = {'realm_index':9,'layer':1}
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    before = engine._load(game.id).to_dict()
    public(engine._load(game.id))
    assert engine._load(game.id).to_dict() == before
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen


def test_asura_dlc_requires_fusion_and_keeps_single_domain(api):
    engine, act = api
    game, book = prepared(engine, 'asura', 'demonic')
    s = game.player.asura_cultivation
    s.update(conversion=5, souls=10000)
    s.pop('route', None)
    engine.store.save(game)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id, status=400)
    game = engine._load(game.id)
    game.player.asura_cultivation.update(route='yaksha', level=4, domain_rank=4, domain_power=7, domain_name='本命')
    reserve = copy.deepcopy(game.player.immortal_aperture)
    engine.store.save(game)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id)
    saved = engine._load(game.id)
    assert saved.player.asura_cultivation['domain_rank'] == 4
    assert saved.player.asura_cultivation['domain_power'] == 7
    assert saved.player.immortal_aperture == reserve
    assert len(upper_source(saved.player).voisinages) == 1
    act(game.id, 'asura', action='train_domain')
    assert engine._load(game.id).player.asura_cultivation['domain_rank'] == 5


@pytest.mark.parametrize('path,world', [('monster','nether'),('ghost','reincarnation')])
def test_dlc_forms_keep_identity_and_stage_locks(api, path, world):
    engine, act = api
    game, book = prepared(engine, world, path)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id, status=400)
    game = engine._load(game.id)
    if path == 'monster':
        from cultivation_life.system import monster_true_form as form
        game.player.monster_evolution_id = 'SERPENT_NETHER_TRUE_1'
        choice = form.public(game.player)['choices'][0]
        form.configure(game.player, 'true_form_confirm', choice)
    else:
        from cultivation_life.system import ghost_soul_form as form
        cause, route = next(iter(form.catalog()['forms'])).split('.')
        form.confirm(game, cause, route)
    data = copy.deepcopy(form.stored(game.player))
    identity = data['blueprint_id']
    game.player.world_voisinages[world].update(levels={identity:4}, active=identity)
    reserve = copy.deepcopy(game.player.immortal_aperture)
    engine.store.save(game)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id)
    saved = engine._load(game.id)
    assert form.stored(saved.player) == data
    assert saved.player.world_voisinages[world]['levels'][identity] == 4
    assert saved.player.immortal_aperture == reserve
    assert len(upper_source(saved.player).voisinages) == 1
    act(game.id, 'upper-voisinage', action='train', voisinage_id=identity, status=400)


@pytest.mark.parametrize('source_world', ['asura','nether','reincarnation'])
def test_other_origins_are_bought_through_real_black_market(api, source_world):
    from cultivation_life.system.spirit_voisinage import offers
    engine, act = api
    game, _ = prepared(engine)
    game.player.world = 'spirit'
    game.player.realm_index = 8
    game.player.location_id = engine.maps.default_location('spirit')
    opening = next(str(i) for i in range(1000)
                   if any(origin(b.spirit_voisinage_id) == source_world for b in offers(game, 'black_market', str(i))))
    game.auction_state = dict(id=opening, status='black_market', world='spirit', location_id=game.player.location_id)
    engine.store.save(game)
    shown = act(game.id, 'black-market-search', pattern='灵域残解')
    row = next(r for r in shown['auction_system']['black_market_results']
               if r['kind'] == 'spirit_manual' and origin(r['content_id'].removeprefix('spirit:')) == source_world)
    before = engine._load(game.id).player.age
    act(game.id, 'black-market-buy', result_id=row['id'], quantity=1)
    saved = engine._load(game.id)
    assert any(t.id == row['content_id'] and t.level == 1 for t in saved.player.known_techniques)
    assert saved.player.age == before


@pytest.mark.parametrize('world,path', [('asura','demonic'),('nether','monster'),('reincarnation','ghost')])
def test_disabled_dlc_uses_its_local_base_route(api, world, path):
    engine, act = api
    game, book = prepared(engine, world, path, source_world=world)
    settings = WORLD_SYSTEMS['asura_manifestation'] if path == 'demonic' else WORLD_SYSTEMS['ghost_cultivation']
    changes = {'enabled': False}
    with patch.dict(settings, changes), patch.dict(CONTENT_DOCUMENTS, {'monster_true_forms.json': {}} if path == 'monster' else {}):
        shown = act(game.id, 'aperture-action', action='inherit', manual_id=book.id)
        assert any(r['mode'] == 'native' for r in shown['aperture']['inheritances'])
        saved = engine._load(game.id)
        assert saved.player.world_voisinages[world]['levels'][key(world, book.spirit_voisinage_id)] == 1


def test_possession_rejects_adaptation_without_consuming_the_hosts_book(api):
    from cultivation_life.system.possession_system import enter_host_body
    engine, act = api
    game, _ = prepared(engine, 'reincarnation', 'ghost')
    target = dict(id='host', name='宿身', race='human', path='dao', realm_index=9, layer=1,
                  age=100, lifespan=None, alive=True)
    enter_host_body(game.player, target)
    book = next(iter(catalog(game).values()))
    grant(game, book.id, 4)
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen


@pytest.mark.parametrize('world,destination', [('celestial','spirit'),('asura','true_demon'),('nether','monster_realm'),('reincarnation','hell')])
def test_canonical_descent_and_return_preserve_each_inherited_growth(api, world, destination):
    engine, act = api
    game, book = prepared(engine, world, source_world='nether')
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id)
    game = engine._load(game.id)
    growth = copy.deepcopy(game.player.world_voisinages)
    doctrine = copy.deepcopy(game.doctrine_state)
    reserve = copy.deepcopy(game.player.immortal_aperture)
    transition = engine._plan_world_transition(game, destination, 'sealed_descent')
    engine._apply_world_transition(game, transition)
    assert game.player.world == destination and len(player_source(game).voisinages) == 1
    transition = engine._plan_world_transition(game, world, 'sealed_return')
    engine._apply_world_transition(game, transition)
    assert game.player.world_voisinages == growth and game.doctrine_state == doctrine
    assert game.player.immortal_aperture == reserve


def test_external_celestial_study_applies_reduction_to_actual_elapsed_time(api):
    engine, act = api
    game, book = prepared(engine, source_world='asura')
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id)
    game = engine._load(game.id)
    identity = book.spirit_voisinage_id
    record = game.doctrine_state['player']
    record['annotations'][identity] = [1]
    record['study_target'] = identity
    record['progress'][identity] = {'level':0, 'experience':69}
    game.player.next_tribulation_age = game.player.age + 1
    engine.store.save(game)
    with patch.dict(CONTENT_DOCUMENTS['doctrines.json']['cultivation'], {'success_rates':[1]*9}):
        act(game.id, 'doctrine-action', action='study', doctrine_id=identity)
    saved = engine._load(game.id)
    progress = saved.doctrine_state['player']['progress'][identity]
    assert saved.player.age - game.player.age == 1
    assert progress['attempts'] == 1 and progress['level'] == 1
    assert saved.pending_event
    assert saved.doctrine_state['player'].get('origin') is None


def test_unsupported_inheritance_record_is_retained_and_never_reclaimed(api):
    engine, act = api
    game, book = prepared(engine)
    identity = book.spirit_voisinage_id
    game.doctrine_state['player'].setdefault('spirit_inheritances', {})[identity] = {'version':999}
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    act(game.id, 'aperture-action', action='inherit', manual_id=book.id, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen


def test_npc_keeps_recorded_residual_when_catalog_expands(api):
    import hashlib
    from cultivation_life.system.spirit_voisinage import npc_source
    engine, _ = api
    game, book = prepared(engine, source_world='reincarnation')
    identity = next(str(i) for i in range(10000) if int.from_bytes(hashlib.blake2s(('spirit-book:' + str(i)).encode(), digest_size=4).digest(),'big') % 100 < 3)
    npc = dict(id=identity, world='spirit', realm_index=6, transcendence={'spirit_manual':book.id})
    assert npc_source(game, npc).attainments == {book.spirit_voisinage_id:4}
    assert npc['transcendence']['spirit_manual'] == book.id
    npc['transcendence']['spirit_manual'] = 'unknown:retained'
    before = copy.deepcopy(npc)
    assert not npc_source(game, npc).voisinages
    assert npc == before
