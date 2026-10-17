"""Real commands, persistence, source ownership, and interrupted personal time."""
import copy
from pathlib import Path

import pytest

from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, ContentRegistry
from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import request_scope
from cultivation_life.models import Player
from cultivation_life.rules import add_item, has_item, max_hp, max_mp, root_definition
from cultivation_life.secret_art_schema import decode_state
from cultivation_life.system.secret_arts import catalog, materials, project

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    made = engine.create_game('补灵修士', 'supreme_metal', 'dao', 81731, preset_id='nascent')
    game = engine._load(made['id'])
    p = game.player
    game.pending_event = None
    p.spirit_root = 'supreme_metal'
    p.additional_roots = []
    p.realm_index, p.layer = 4, 1
    p.hp, p.mp = max_hp(p), max_mp(p)
    p.lifespan = max(p.lifespan or 0, p.age + 1000)
    game.settings['silent_events'] = True
    game.settings['guixu_event_popup'] = False
    add_item(p, 'spirit_stone', 50000)
    add_item(p, 'secret_manual_water')
    add_item(p, 'secret_core_water_4', 2)
    engine.store.save(game)
    engine.get_game(game.id)
    return engine, engine.store.load(game.id)


def act(engine, game_id, art='root_water', action='study', **kwargs):
    revision = engine.get_game(game_id)['secret_arts']['revision']
    return engine.train_secret_art(game_id, art, action, revision=revision, **kwargs)


def learned(game, art='root_water'):
    required = catalog()[art]['study_years']
    game.player.secret_art_state = dict(schema_version=1, revision=0, arts={
        art: dict(study_years=required, study_required=required, casting=None)})


def test_all_manuals_and_cores_have_real_local_sources():
    for art in catalog().values():
        assert art['manual_id'] in ITEM_CATALOG
        assert {row['world'] for row in MARKET_GOODS if row['content_id'] == art['manual_id']} == {
            'human', 'demon', 'spirit', 'true_demon', 'monster_realm', 'phantom_underworld',
            'hell', 'celestial', 'asura', 'nether', 'reincarnation'}
    assert 'root_manual' not in ITEM_CATALOG['secret_manual_water'].tags
    assert ITEM_CATALOG['jinque_water'].root_grant == 'water'


def test_actual_learning_and_grafting_keep_quality_and_consume_once(ready):
    engine, game = ready
    age = game.player.age
    efficiency = root_definition(game.player.spirit_root)['efficiency']
    act(engine, game.id, years=2)
    saved = engine.store.load(game.id)
    assert saved.player.age == age + 2
    assert not has_item(saved.player, 'secret_manual_water')
    assert saved.player.secret_art_state['arts']['root_water']['study_years'] == 2
    stones = next(i.quantity for i in saved.player.inventory if i.id == 'spirit_stone')
    act(engine, game.id, years=100)
    assert engine.store.load(game.id).player.age == age + 5
    # Time is capped to what actually remains, and the first source is paid once.
    act(engine, game.id, action='practice', years=3, material_id='item:secret_core_water_4')
    saved = engine.store.load(game.id)
    assert has_item(saved.player, 'secret_core_water_4', 1)
    assert not has_item(saved.player, 'secret_core_water_4', 2)
    assert 'water' not in saved.player.additional_roots
    assert saved.player.secret_art_state['arts']['root_water']['casting']['years'] == 3
    act(engine, game.id, action='practice', years=100)
    saved = engine.store.load(game.id)
    assert saved.player.age == age + 15
    assert saved.player.additional_roots == ['water']
    assert saved.player.secret_art_state['arts']['root_water']['casting'] is None
    assert root_definition(saved.player.spirit_root)['efficiency'] == efficiency
    assert saved.player.spirit_root == 'supreme_metal'
    assert has_item(saved.player, 'secret_core_water_4', 1)
    with pytest.raises(ValueError, match='已经拥有'):
        act(engine, game.id, action='practice', material_id='item:secret_core_water_4')
    assert stones > 0


@pytest.mark.parametrize('mutation', ['missing_manual', 'poor', 'pending', 'prison', 'suppressed'])
def test_rejected_learning_does_not_mutate_save_or_rng(ready, mutation):
    engine, game = ready
    if mutation == 'missing_manual':
        game.player.inventory = [i for i in game.player.inventory if i.id != 'secret_manual_water']
    elif mutation == 'poor':
        game.player.inventory = [i for i in game.player.inventory if i.id != 'spirit_stone']
    elif mutation == 'pending':
        import random
        game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_REALM_COMMON_FOUNDATION_01'], game, random.Random(1))
    elif mutation == 'prison':
        game.player.imprisonment = dict(years=1, remaining_years=1)
    else:
        engine.store.save(game)
        engine.manage_secret_art(game.id, 'suppress', 'activate', 3, 1)
        game = engine.store.load(game.id)
    engine.store.save(game)
    # Loading has its existing preparation contract; compare after that preparation.
    engine.get_game(game.id)
    before = engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError):
        engine.train_secret_art(game.id, 'root_water', 'study', revision=0, years=1)
    assert engine.store.load(game.id).to_dict() == before


def test_source_attributes_and_realm_are_checked_again_at_submission(ready):
    engine, game = ready
    learned(game)
    add_item(game.player, 'secret_core_fire_4')
    add_item(game.player, 'econ_human_4_core_energy')
    engine.store.save(game)
    for identity in ('item:secret_core_fire_4', 'item:econ_human_4_core_energy', 'item:missing'):
        before = engine.store.load(game.id).to_dict()
        with pytest.raises(ValueError, match='材料'):
            act(engine, game.id, action='practice', material_id=identity)
        assert engine.store.load(game.id).to_dict() == before


def test_mutated_root_needs_fifth_rank_even_if_manual_is_learned(ready):
    engine, game = ready
    learned(game, 'root_wind')
    add_item(game.player, 'secret_core_wind_4')
    engine.store.save(game)
    assert not materials(game.player, catalog()['root_wind'])
    with pytest.raises(ValueError, match='材料'):
        act(engine, game.id, art='root_wind', action='practice', material_id='item:secret_core_wind_4')
    add_item(game.player, 'secret_core_wind_5')
    engine.store.save(game)
    act(engine, game.id, art='root_wind', action='practice', years=1, material_id='item:secret_core_wind_5')
    assert engine.store.load(game.id).player.secret_art_state['arts']['root_wind']['casting']['years'] == 1


def test_real_soul_consumed_without_awarding_unearned_devour_bonus(ready):
    engine, game = ready
    learned(game)
    add_item(game.player, 'secret_soul_water_4')
    before_bonus = game.player.devouring_breakthrough_bonus
    engine.store.save(game)
    act(engine, game.id, action='practice', years=1, material_id='item:secret_soul_water_4')
    saved = engine.store.load(game.id)
    assert not has_item(saved.player, 'secret_soul_water_4')
    assert saved.player.devouring_breakthrough_bonus == before_bonus


def test_old_souls_with_unknown_attributes_are_not_inferred(ready):
    _, game = ready
    game.player.foreign_souls = [dict(id='old', name='水行修士', realm_index=8, refined=False)]
    assert not any(row['kind'] == 'soul' for row in materials(game.player, catalog()['root_water']))


def test_mortal_can_learn_without_cultivation_requirement(ready):
    engine, game = ready
    game.player.realm_index, game.player.layer = 0, 1
    game.player.spirit_root = 'none'
    game.player.age, game.player.lifespan = 18, 100
    engine.store.save(game)
    act(engine, game.id, years=1)
    assert engine.store.load(game.id).player.secret_art_state['arts']['root_water']['study_years'] == 1


def test_all_twelve_grades_and_both_kinds_are_universal():
    from cultivation_life.secret_art_content import AFFINITIES, core_id, soul_id
    for affinity in AFFINITIES:
        for rank in range(1, 13):
            for identity in (core_id(affinity, rank), soul_id(affinity, rank)):
                tags = ITEM_CATALOG[identity].tags
                assert 'affinity:' + affinity in tags and 'realm:' + str(rank) in tags
                assert not any(t.startswith('native_world:') for t in tags)


@pytest.mark.parametrize('kind', ['core', 'soul'])
@pytest.mark.parametrize('rank', [1, 4, 5, 12])
def test_loot_probability_and_actual_source_root(ready, kind, rank):
    import random
    from cultivation_life.system.secret_art_loot import grant
    _, game = ready
    cfg = ContentRegistry.loaded_documents['secret_arts.json']
    before = cfg[kind + '_drop_chance']
    try:
        source = dict(spirit_root='heavenly_metal_water', realm_index=rank)
        cfg[kind + '_drop_chance'] = 0
        assert grant(game, source, random.Random(3), kind) == ''
        cfg[kind + '_drop_chance'] = 1
        assert grant(game, source, random.Random(3), kind)
        new = [i for i in game.player.inventory if i.id.startswith('secret_' + kind + '_') and i.quantity > 0]
        assert any(i.id in {f'secret_{kind}_metal_{rank}', f'secret_{kind}_water_{rank}'} for i in new)
        assert grant(game, dict(spirit_root='none', realm_index=rank), random.Random(1), kind) == ''
    finally:
        cfg[kind + '_drop_chance'] = before


def test_books_are_excluded_from_generic_acquisition_and_auction(ready):
    from cultivation_life.content_registry import ROOT_BOOK_GOODS, restricted_acquisition, natural_market_acquisition_allowed
    engine, game = ready
    assert ROOT_BOOK_GOODS
    assert all(not (r['kind'] == 'item' and ITEM_CATALOG[r['content_id']].root_grant) for r in MARKET_GOODS)
    assert restricted_acquisition('item', 'jinque_water')
    assert not natural_market_acquisition_allowed('item', 'jinque_water')
    assert not any(ITEM_CATALOG[r['content_id']].root_grant for r in engine._auction_goods_pool('human') if r['kind'] == 'item')
    assert not any(ITEM_CATALOG[r['id']].root_grant for r in engine._merchant_items('human'))


@pytest.mark.parametrize('action,kind', [('hunt_beast', 'core'), ('slay', 'soul')])
def test_real_personal_kill_grants_elemental_material(ready, monkeypatch, action, kind):
    import random
    engine, game = ready
    add_item(game.player, 'broken_god')
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    config = ContentRegistry.loaded_documents['secret_arts.json']
    monkeypatch.setitem(config, kind + '_drop_chance', 1)
    # The actual target generated by the encounter owns this root, rather than the player.
    monkeypatch.setattr(engine, '_random_npc_root', lambda rank, rng: 'supreme_water')
    summary = engine._personal_combat_step(game, action, random.Random(3))
    assert '击杀' in summary
    assert any(i.id.startswith(f'secret_{kind}_water_') and i.quantity > 0 for i in game.player.inventory)


def test_black_market_search_retains_restricted_books(ready):
    engine, game = ready
    game.auction_state = dict(id='books', status='black_market', world='human',
        location_id=game.player.location_id, location_name='会场', black_market_results=[])
    add_item(game.player, 'spirit_stone', 1000000)
    engine.store.save(game)
    shown = engine.search_black_market(game.id, '金阙')
    result = next(r for r in shown['auction_system']['black_market_results'] if r['content_id'] == 'jinque_water')
    engine.buy_black_market_item(game.id, result['id'])
    assert has_item(engine.store.load(game.id).player, 'jinque_water')


def test_exchange_book_trade_consumes_materials_and_cannot_replay(ready):
    import random
    from cultivation_life.system.crafting_system import make_crafting_material_instance
    engine, game = ready
    rng = random.Random(2150)
    engine._schedule_exchange(game, rng)
    engine._open_exchange(game, rng)
    game.player.location_id = game.exchange_state['location_id']
    game.exchange_state['alias'] = '青笠客'
    offer = next(o for o in game.exchange_state['offers'] if o.get('reward_kind') == 'root_book')
    demand = offer['demands'][0]
    definition = engine._crafting_material_defs()[demand['definition_id']]
    selected = []
    for _ in range(demand['quantity']):
        material = make_crafting_material_instance(definition, rng, source='测试', origin_world='human')
        game.player.crafting_materials.append(material)
        selected.append(dict(id=material['id'], quantity=1))
    stones = engine._spirit_stones(game.player)
    engine.store.save(game)
    payload = dict(offer_id=offer['id'], materials=selected)
    engine.exchange_action(game.id, 'trade', payload)
    saved = engine.store.load(game.id)
    assert has_item(saved.player, offer['item_id'])
    assert engine._spirit_stones(saved.player) == stones
    assert not set(m['id'] for m in selected).intersection(m['id'] for m in saved.player.crafting_materials)
    with pytest.raises(ValueError, match='结束'):
        engine.exchange_action(game.id, 'trade', payload)


def test_old_page_revision_and_request_cache_rollback(ready, monkeypatch):
    engine, game = ready
    act(engine, game.id, years=1)
    engine.get_game(game.id)
    before = engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError, match='过期'):
        engine.train_secret_art(game.id, 'root_water', 'study', revision=0)
    assert engine.store.load(game.id).to_dict() == before
    with request_scope(engine):
        original = engine._load(game.id)
        snapshot = copy.deepcopy(original.to_dict())
        with monkeypatch.context() as m:
            m.setattr(engine.store, 'save', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
            with pytest.raises(OSError):
                engine.train_secret_art(game.id, 'root_water', 'study', revision=1, years=1)
        assert engine._load(game.id).to_dict() == snapshot
    assert engine.store.load(game.id).to_dict() == before


def test_interrupted_years_preserve_paid_source_and_later_resume(ready, monkeypatch):
    engine, game = ready
    learned(game)
    engine.store.save(game)
    original_year = engine._advance_world_year
    start = game.player.age
    def interrupt(g, rng, news, **kwargs):
        proceeded = original_year(g, rng, news, **kwargs)
        if g.player.age == start + 2:
            # A real registered event is persisted and loaded through the public boundary.
            event = next(e for e in engine.events if e['id'] == 'EVT_REALM_COMMON_FOUNDATION_01')
            g.pending_event = engine._instantiate_event(event, g, rng)
            return False
        return proceeded
    with monkeypatch.context() as m:
        m.setattr(engine, '_advance_world_year', interrupt)
        act(engine, game.id, action='practice', years=10, material_id='item:secret_core_water_4')
    shown = engine.get_game(game.id)
    assert shown['pending_event']
    saved = engine.store.load(game.id)
    assert saved.player.age == start + 2
    assert saved.player.secret_art_state['arts']['root_water']['casting']['years'] == 2
    assert 'water' not in saved.player.additional_roots
    # Complete the actual offered event before resuming.
    choice = next(c for c in shown['pending_event']['choices'] if c.get('enabled', True))
    engine.choose(game.id, choice['id'], event_id=shown['pending_event']['id'])
    while engine.get_game(game.id)['pending_event']:
        event = engine.get_game(game.id)['pending_event']
        engine.choose(game.id, event['choices'][0]['id'], event_id=event['id'])
    act(engine, game.id, action='practice', years=100)
    saved = engine.store.load(game.id)
    assert saved.player.additional_roots == ['water']
    assert has_item(saved.player, 'secret_core_water_4', 1)


def test_projection_is_read_only_and_missing_state_keeps_builtin_arts(ready):
    engine, game = ready
    before = game.to_dict()
    assert len(project(game)['library']) == 9
    assert game.to_dict() == before
    document = game.player.to_dict()
    document.pop('secret_art_state')
    assert Player.from_dict(document).secret_art_state == {}
    assert engine.get_game(game.id)['secret_arts']['targets']


@pytest.mark.parametrize('value', [dict(schema_version=2, revision=0, arts={}),
    dict(schema_version=1, revision=-1, arts={}),
    dict(schema_version=1, revision=0, arts={'unknown': {}})])
def test_unknown_or_invalid_progress_rejected(value):
    with pytest.raises(ValueError):
        decode_state(value)


def test_existing_books_still_directly_supplement_roots(ready):
    engine, game = ready
    add_item(game.player, 'jinque_water')
    engine.store.save(game)
    engine.use_item(game.id, 'jinque_water')
    saved = engine.store.load(game.id)
    assert saved.player.additional_roots == ['water']
    assert saved.player.secret_art_state == {}
