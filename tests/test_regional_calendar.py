"""Real regional finance/lifecycles; no original save is loaded or patched."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.world import regions
from cultivation_life.engine.transactions import request_scope
from cultivation_life.models import GameState
from cultivation_life.regional_context import CalendarGame, synchronize
from cultivation_life.system.economy.ledger import balance

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def regional(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    game = engine._load(engine.create_game('地方历法验收', 'none', 'dao', 20261018)['id'])
    game.settings.update(silent_events=True, guixu_event_popup=False)
    game.pending_event = None
    game.player.lifespan = 10000
    regions.ensure(engine._dependencies.regions, game)
    return engine, game


def projection(game, world):
    econ = game.economy_v2
    return dict(clock=game.world_simulation['regions'][world],
        sects={k:s.to_dict() for k,s in game.sects.items() if s.world == world},
        people={k:n.to_dict() for k,n in game.world_npcs.items() if n.world == world},
        economy=econ['worlds'][world],
        markets={k:v for k,v in econ['markets'].items() if v['world'] == world},
        organizations={k:v for k,v in econ['organizations'].items() if v['world'] == world},
        transport=econ['transport']['worlds'].get(world),
        merchant=game.merchant_state['worlds'].get(world))


def test_frozen_replay_matches_each_real_year_and_is_idempotent(regional):
    engine, original = regional
    regions.synchronize(engine._dependencies.regions, original, regions.worlds())
    # Independent-society equivalence: cross-world transactions have their
    # own deferred-credit contract and are checked separately.
    for route in original.economy_v2['network']['routes'].values():
        route.update(open=False, built=False, paid=0)
    live, lazy = copy.deepcopy(original), copy.deepcopy(original)
    untouched = copy.deepcopy(projection(lazy, 'celestial'))
    for _ in range(25):
        live.player.age += 1
        lazy.player.age += 1
        regions.synchronize(engine._dependencies.regions, live, regions.worlds())
        regions.advance(engine._dependencies.regions, lazy, [])
    assert projection(lazy, 'celestial') == untouched
    regions.synchronize(engine._dependencies.regions, lazy, regions.worlds())
    for world in regions.worlds():
        assert projection(lazy, world) == projection(live, world), world
    before = copy.deepcopy(lazy.to_dict())
    regions.synchronize(engine._dependencies.regions, lazy, regions.worlds())
    assert lazy.to_dict() == before
    restored = GameState.from_dict(before)
    regions.synchronize(engine._dependencies.regions, restored, regions.worlds())
    assert restored.to_dict() == before


def test_unvisited_sect_earns_real_income_recruits_and_can_die(regional):
    engine, game = regional
    sect = game.sects['taixuan']
    original_ids = {n.id for n in sect.npcs}
    victim = sect.npcs[0]
    victim.lifespan = victim.age + 1
    for _ in range(20):
        game.player.age += 1
        regions.advance(engine._dependencies.regions, game, [])
    assert 'organization:sect:taixuan' not in game.economy_v2['organizations']
    assert victim.alive  # All three clocks are frozen together until needed.
    regions.synchronize(engine._dependencies.regions, game, ['spirit'])
    row = game.economy_v2['organizations']['organization:sect:taixuan']
    assert row['last_year'] > game.world_simulation['base_year']
    assert row['produced'] > 0 and balance(game, 'organization:sect:taixuan') > 0
    assert not victim.alive and victim.death_reason
    assert not sect.extinct and {n.id for n in sect.npcs} - original_ids
    assert game.player.world == 'human'


def test_views_keep_original_authorities_and_do_not_copy_game_per_year(regional):
    engine, game = regional
    view = CalendarGame(game, 'human', game.player.age)
    assert view.sects is game.sects and view.economy_v2 is game.economy_v2
    assert view.player.inventory is game.player.inventory
    with pytest.raises(ValueError):
        view.player.world = 'spirit'
    original = copy.deepcopy
    def checked(value, *args, **kwargs):
        assert not isinstance(value, GameState), 'yearly full transaction copy'
        return original(value, *args, **kwargs)
    with patch('copy.deepcopy', checked):
        for _ in range(3):
            game.player.age += 1
            regions.advance(engine._dependencies.regions, game, [])


def test_copy_on_write_scheduler_binds_the_actual_working_state(regional):
    engine, original = regional
    working = copy.deepcopy(original)
    working.player.age += 2
    synchronize(working, ['celestial'], entering=True)
    assert working.world_simulation['regions']['celestial']['year'] == working.player.age
    assert original.world_simulation['regions']['celestial']['year'] == original.player.age


def test_failed_public_action_discards_mutation_and_request_cache(regional):
    engine, game = regional
    engine.store.save(game)
    # Hydrate before measuring: existing load adoption may persist metadata.
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    original = regions.tick
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('fault after real money and people changes')
    with request_scope(engine):
        with patch.object(regions, 'tick', fail), pytest.raises(RuntimeError, match='fault'):
            engine.advance(game.id, 'rest', 1)
        assert engine._load(game.id).player.age == game.player.age
    assert engine.store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('damage', ['future', 'unknown', 'rng', 'person'])
def test_invalid_regional_receipts_rejected(regional, damage):
    _, game = regional
    raw = game.to_dict()
    s = raw['world_simulation']
    if damage == 'future': s['regions']['human']['year'] += 1
    if damage == 'unknown': s['regions']['elsewhere'] = s['regions'].pop('human')
    if damage == 'rng': s['regions']['human']['rng'] = 'broken'
    if damage == 'person': s['people']['somebody'] = game.player.age + 1
    with pytest.raises(ValueError): GameState.from_dict(raw)


def test_new_task_catches_up_target_before_mutating(regional):
    engine, game = regional
    game.player.age += 5
    regions.advance(engine._dependencies.regions, game, [])
    assert game.world_simulation['regions']['celestial']['year'] < game.player.age
    synchronize(game, ['celestial'], entering=True)
    assert game.world_simulation['regions']['celestial']['year'] == game.player.age
    assert all(game.world_simulation['regions'][w]['year'] == game.player.age
               for w in regions.closure(['celestial']))


def test_ascension_dependency_ages_original_npc_once(regional):
    engine, game = regional
    npc = game.sects['tianjian'].npcs[0]
    npc.realm_index, npc.layer = 5, 3
    npc.cultivation_progress = 10**6
    npc.lifespan = None
    age = npc.age
    with patch.object(engine, '_npc_breakthrough_probability', return_value=1):
        game.player.age += 1
        regions.advance(engine._dependencies.regions, game, [])
    assert npc.world == 'spirit' and npc.age == age + 1
    game.player.age += 1
    regions.advance(engine._dependencies.regions, game, [])
    regions.synchronize(engine._dependencies.regions, game, ['spirit'])
    assert npc.age == age + 2


def test_civilization_revision_advances_only_for_its_own_year(regional):
    from cultivation_life.system.monster_civilizations import core
    engine, game = regional
    core.activate(game)
    before = copy.deepcopy(game.monster_civilization_state)
    game.player.age += 1
    core.advance_year(CalendarGame(game, 'celestial', game.player.age))
    assert game.monster_civilization_state == before
    core.advance_year(CalendarGame(game, 'human', game.player.age))
    assert game.monster_civilization_state['revision'] == before['revision'] + 1
    after = copy.deepcopy(game.monster_civilization_state)
    core.advance_year(CalendarGame(game, 'human', game.player.age))
    assert game.monster_civilization_state == after


def test_only_existing_survey_keeps_departure_society_live(regional):
    _, game = regional
    game.player.world = 'celestial'  # Fixture location, no production movement.
    game.heavens_state = {'generation_enabled': True, 'runtime': {'processed_years': 99}}
    assert 'human' not in regions.important_worlds(game)
    game.heavens_state['generation_enabled'] = False
    assert 'human' not in regions.important_worlds(game)
    game.heavens_state['runtime']['ruins'] = {'survey': {'status': 'active'}}
    assert 'human' not in regions.important_worlds(game)


def test_closed_routes_and_unused_alliance_metadata_do_not_bind_regions(regional):
    engine, game = regional
    for route in game.economy_v2['network']['routes'].values():
        route['open'] = False
    assert regions.closure(['spirit']) == ['spirit']
    assert regions.closure(['celestial']) == ['celestial']


def test_existing_cross_freight_keeps_running_when_player_is_elsewhere(regional):
    engine, game = regional
    game.player.world = 'celestial'
    game.economy_v2['transport']['worlds']['human']['fleets']['test'] = {
        'cross_trip': {'destination':'spirit','path':['human','spirit']}}
    assert regions.important_worlds(game) == {'celestial'}
    game.economy_v2['transport']['worlds']['human']['fleets']['test']['cross_trip'] = None
    assert 'human' not in regions.important_worlds(game)


def test_remote_native_does_not_ascend_until_origin_is_entered(regional):
    engine, game = regional
    game.player.world = 'spirit'
    npc = game.world_npcs['xiang_zhili']
    npc.cultivation_progress = 10**6
    npc.lifespan = None
    start = npc.age
    game.player.age += 1
    regions.advance(engine._dependencies.regions, game, [])
    assert npc.world == 'human' and npc.age == start
    with patch.object(engine, '_npc_breakthrough_probability', return_value=1):
        regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert npc.world == 'spirit' and npc.age == start+1



def test_closed_passage_does_not_wake_or_charge_destination(regional):
    from cultivation_life.system.economy import cross_freight
    engine, game = regional
    regions.initialize_region(engine._dependencies.regions,game,'spirit')
    fleet=next(f for f in game.economy_v2['transport']['worlds']['spirit']['fleets'].values()
               if f['alliance_id']=='xuanji')
    for route in game.economy_v2['network']['routes'].values():route['open']=False
    game.player.age+=20
    before=copy.deepcopy(game.to_dict())
    with patch.object(game,'_synchronize_regions',wraps=game._synchronize_regions) as sync:
        with pytest.raises(ValueError,match='开放通道'):
            cross_freight.dispatch(game,engine.maps,fleet,'true_demon')
        sync.assert_not_called()
    assert game.to_dict()==before


def test_historical_unissued_trade_cannot_write_future_market(regional):
    from cultivation_life.system.economy import cross_freight
    engine,game=regional
    regions.initialize_region(engine._dependencies.regions,game,'spirit')
    fleet=next(f for f in game.economy_v2['transport']['worlds']['spirit']['fleets'].values()
               if f['alliance_id']=='xuanji')
    old=game.player.age
    game.player.age+=10
    game.world_simulation['regions']['true_demon']['year']=game.player.age
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError,match='历史补算'):
        cross_freight.dispatch(CalendarGame(game,'spirit',old),engine.maps,fleet,'true_demon')
    assert game.to_dict()==before
