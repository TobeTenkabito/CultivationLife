"""Live permissions and location changes must invalidate old operation context."""
import copy
import random

import pytest

from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.economy.ledger import transfer_value, balance
from cultivation_life.system.economy.local_market import quote
from cultivation_life.system.economy.enterprise_state import owner_allowed
from test_pending_audit_fixes import engine, local_game
from test_audit_round56_fixes import controlled_ghost
from test_economy_enterprises import buy, estate_act, own_fleet, order, fleet
from test_economy_network import act
from test_travel_relationship_2160 import prepare_journey
from test_regional_audit_fixes import dismiss


def ordered_sect_delivery(engine):
    game = local_game(engine)
    transfer_value(game, 'background:human', 'player', 10**9, '隔离资金')
    engine.store.save(game)
    game, first = buy(engine, game, 'shop')
    origin = game.player.location_id
    game = estate_act(engine, game, first, 'fund', amount=10000)
    market = game.economy_v2['markets'][f'human:{origin}']
    game = estate_act(engine, game, first, 'purchase', item='dew_grass_seed', quantity=10,
        market_revision=market['revision'], total=quote(market['commodities']['dew_grass_seed'], 'buy', 10)['total'])
    # Initial fixture: two real warehouses owned by the player's current sect.
    game.player.location_id = 'lanjiang_steppe'
    ensure_regional_market(game, engine.maps, 'human', game.player.location_id)
    game, second = buy(engine, game, 'shop')
    game.player.location_id = origin
    game.player.faction_id = 'tianjian'
    for identity in (first, second):
        game.economy_v2['estates'][identity].update(owner_kind='sect', owner_id='tianjian')
    assert owner_allowed(game, 'sect', 'tianjian', 'human')
    game, fid = own_fleet(engine, game)
    assert fleet(game, fid)['owner_kind'] == 'independent'
    game = act(engine, game, 'fund', fleet_id=fid, amount=1000000)
    game = order(engine, game, fid, kind='delivery', mode='repeat', source_estate=first,
                 target_estate=second, quantity=1)
    return game, fid, first, second


def test_leaving_sect_revokes_saved_personal_fleet_warehouse_order(engine):
    game, fid, first, second = ordered_sect_delivery(engine)
    engine.leave_faction(game.id)
    game = engine._load(game.id)
    assert not owner_allowed(game, 'sect', 'tianjian', 'human')
    engine.store.save(game)
    snapshot = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='权限|授权'):
        engine.fleet_action(game.id, dict(action='order_dispatch', fleet_id=fid))
    assert engine.store._path(game.id).read_bytes() == snapshot


def test_automatic_personal_fleet_also_stops_extracting_old_sect_stock(engine):
    game, fid, first, second = ordered_sect_delivery(engine)
    engine.leave_faction(game.id)
    before = engine.store.load(game.id).economy_v2['estates'][first]['stock']['dew_grass_seed']
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert game.economy_v2['estates'][first]['stock']['dew_grass_seed'] == before
    assert fleet(game, fid)['voyages'] == 0 and fleet(game, fid)['cargo'] is None
    assert '授权' in fleet(game, fid)['last_result']


def test_org_fleet_keeps_its_own_warehouse_order_after_player_leaves(engine):
    game, fid, first, second = ordered_sect_delivery(engine)
    fleet(game, fid).update(owner_kind='sect', owner_id='tianjian', player_controlled=False)
    engine.store.save(game)
    engine.leave_faction(game.id)
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert fleet(game, fid)['voyages'] >= 1
    assert game.economy_v2['estates'][first]['stock']['dew_grass_seed'] < 10


@pytest.mark.parametrize('action', ['wait', 'resist', 'possess'])
def test_pending_event_blocks_ghost_constraint_action_atomically(engine, action):
    game, npc = controlled_ghost(engine)
    npc.age, npc.lifespan = 30, 10000
    game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    game.pending_event['_followup_event'] = engine._prepare_treasure_reward_event(game, random.Random(11))
    engine.store.save(game)
    engine.get_game(game.id)
    snapshot = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='事件|劫战'):
        engine.ghost_constraint_action(game.id, action)
    assert engine.store._path(game.id).read_bytes() == snapshot


def interrupted_ghost_journey(engine):
    game, npc = controlled_ghost(engine)
    captor = copy.deepcopy(game.player.ghost_captor)
    game.player.ghost_captor = None
    npc.age, npc.lifespan = 30, 10000
    destination, years = prepare_journey(engine, game)
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    engine.store.save(game)
    engine.travel_map(game.id, destination)
    assert engine.store.load(game.id).map_journey
    dismiss(engine, game.id)
    game = engine.store.load(game.id)
    game.settings.update(silent_events=True, guixu_event_popup=False)
    # An unregistered encounter opponent uses the established snapshot rule.
    captor.update(id='roaming-captor', npc_id=None, location_id=destination)
    game.player.ghost_captor = captor
    engine.store.save(game)
    return game, destination


@pytest.mark.parametrize('action', ['wait', 'rest'])
def test_captor_forced_local_move_cancels_old_journey_and_refreshes_actual_market(engine, action):
    game, destination = interrupted_ghost_journey(engine)
    origin = game.player.location_id
    if action == 'wait':
        engine.ghost_constraint_action(game.id, 'wait')
    else:
        engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert game.player.location_id != origin
    assert game.map_journey is None
    assert game.market_location_id == game.player.location_id
    assert game.market_world == game.player.world
