import copy
import json
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system.economy import caravans, state
from cultivation_life.system.economy.ledger import balance, transfer_value

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def trade(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game = engine._load(engine.create_game('商队验收','supreme_metal','dao',213,preset_id='core')['id'])
    game.pending_event = None
    game.player.next_tribulation_age = None
    region = game.economy_v2['transport']['worlds']['human']
    fleet = next(iter(region['fleets'].values()))
    alliance = game.merchant_state['worlds']['human'][0]
    for other in list(region['fleets'].values())[1:]:
        other['status'] = 'retired'
    origin, destination = alliance['hq'], alliance['offices'][0]['location_id']
    game.player.age += 1
    state.advance_economy(game)
    for place in [origin, *(row['location_id'] for row in alliance['offices'])]:
        state.ensure_regional_market(game, engine.maps, 'human', place)
    source = game.economy_v2['markets'][f'human:{origin}']
    target = game.economy_v2['markets'][f'human:{destination}']
    item = next(key for key,row in source['commodities'].items() if 20 <= row['reference'] <= 100)
    for key,row in source['commodities'].items():
        row['stock'] = row['target'] * 3 if key == item else 0
        state.reprice(game, source, row)
    for place in [row['location_id'] for row in alliance['offices']]:
        market = game.economy_v2['markets'][f'human:{place}']
        row = market['commodities'][item]
        row['stock'] = 0 if place == destination else row['target'] * 3
        state.reprice(game, market, row)
    return engine, game, fleet, source, target, item


def cash(game):
    return (balance(game,'player') + sum(row['balance'] for row in game.economy_v2['accounts'].values())
        + sum(a['reserves'] for rows in game.merchant_state['worlds'].values() for a in rows))


def dispatch(trade):
    engine, game, fleet, source, target, item = trade
    caravans.advance_caravans(game, engine.maps)
    assert fleet['status'] == 'travelling'
    assert fleet['cargo']['destination'] == target['location']
    return fleet['cargo']['quantity']


def arrive(trade):
    engine, game, fleet, source, target, item = trade
    game.player.age = fleet['cargo']['arrival']
    state.advance_economy(game)
    state.ensure_regional_market(game,engine.maps,'human',target['location'])


def test_real_stock_cash_cargo_and_exactly_once_arrival(trade, monkeypatch):
    engine, game, fleet, source, target, item = trade
    original = source['commodities'][item]['stock']
    money, rng = cash(game), game.rng_state
    count = dispatch(trade)
    assert source['commodities'][item]['stock'] == original-count
    assert target['commodities'][item]['stock'] == 0
    assert cash(game) == money and game.rng_state == rng
    snapshot = copy.deepcopy(game.to_dict())
    caravans.advance_caravans(game,engine.maps)
    assert game.to_dict() == snapshot
    monkeypatch.setattr(caravans,'_roll',lambda *args:.99)
    arrive(trade)
    before = target['commodities'][item]['stock']; money = cash(game)
    caravans.advance_caravans(game,engine.maps)
    assert target['commodities'][item]['stock'] == before+count
    assert fleet['cargo'] is None and fleet['delivered'] == count
    assert fleet['dividends'] > 0 and cash(game) == money
    snapshot = copy.deepcopy(game.to_dict())
    caravans.advance_caravans(game,engine.maps)
    assert game.to_dict() == snapshot
    engine.store.save(game)
    assert engine.store.load(game.id).economy_v2 == game.economy_v2


def test_transit_save_load_preserves_the_same_goods_and_owner(trade):
    engine, game, fleet, *_ = trade
    dispatch(trade)
    saved = game.to_dict()
    restored = GameState.from_dict(saved)
    assert restored.economy_v2 == game.economy_v2
    assert restored.merchant_state == game.merchant_state
    assert restored.rng_state == game.rng_state
    assert fleet['world'] == 'human' and fleet['alliance_id'] in {a['id'] for a in game.merchant_state['worlds']['human']}


def test_limited_buyer_funds_keep_unsold_cargo(trade, monkeypatch):
    engine, game, fleet, source, target, item = trade
    count = dispatch(trade); arrive(trade)
    monkeypatch.setattr(caravans,'_roll',lambda *args:.99)
    payer = f'market:{target["id"]}'
    transfer_value(game,payer,'background:human',balance(game,payer),'验收隔离流动性')
    before = target['commodities'][item]['stock']
    caravans.advance_caravans(game,engine.maps)
    assert fleet['status'] == 'selling' and fleet['cargo']['quantity'] == count
    assert target['commodities'][item]['stock'] == before
    transfer_value(game,'background:human',payer,10**6,'验收恢复流动性')
    game.player.age += 1
    caravans.advance_caravans(game,engine.maps)
    assert fleet['cargo'] is None and fleet['delivered'] == count


def test_transport_loss_is_real_and_not_paid_twice(trade, monkeypatch):
    engine, game, fleet, source, target, item = trade
    count = dispatch(trade); arrive(trade)
    monkeypatch.setattr(caravans,'_roll',lambda *args:0)
    before = target['commodities'][item]['stock']; money = cash(game)
    caravans.advance_caravans(game,engine.maps)
    assert fleet['lost'] == count and fleet['delivered'] == 0
    assert fleet['profit'] < 0 and fleet['dividends'] == 0 and fleet['cargo'] is None
    assert target['commodities'][item]['stock'] == before and cash(game) == money


def test_changed_destination_price_can_make_the_trip_unprofitable(trade, monkeypatch):
    engine, game, fleet, source, target, item = trade
    dispatch(trade); arrive(trade)
    monkeypatch.setattr(caravans,'_roll',lambda *args:.99)
    target['commodities'][item]['stock'] = target['commodities'][item]['target'] * 20
    caravans.advance_caravans(game,engine.maps)
    assert fleet['profit'] < 0 and fleet['dividends'] == 0


def test_teleport_charge_matches_time_saved_and_uses_actual_owner(trade):
    engine, game, *_ = trade
    network = caravans.arrays(game,engine.maps,'human')
    plans = [caravans.route_quote(game,engine.maps,'human',a,b,10000)
        for a in network for b in network if a != b]
    plan = next(p for p in plans if p and p['array_fee'] > 0)
    assert plan['years'] < plan['normal_years']
    assert plan['array_fee'] == int(plan['cost'] * (plan['normal_years']-plan['years'])/plan['normal_years'])
    assert plan['transport_cost'] + plan['array_fee'] == plan['cost']
    assert plan['array_operator'] == network[plan['origin']]['owner_id']
    assert game.player.teleport_permissions == []


def test_remote_opening_does_not_move_player_or_copy_inventory(trade):
    engine, game, *_ = trade
    before = copy.deepcopy(game.player.to_dict())
    place = engine.maps.default_location('spirit')
    money = cash(game)
    state.ensure_regional_market(game,engine.maps,'spirit',place)
    assert game.player.to_dict() == before and cash(game) == money


def test_real_departure_pays_array_operator_without_moving_player(trade):
    engine, game, fleet, *_ = trade
    network = caravans.arrays(game,engine.maps,'human')
    plan = next(p for a in network for b in network if a != b
        for p in [caravans.route_quote(game,engine.maps,'human',a,b,10000)] if p and p['array_fee'] > 0)
    alliance = game.merchant_state['worlds']['human'][0]
    alliance['hq'] = plan['origin']
    alliance['offices'] = [dict(location_id=plan['destination'],leader=alliance['leader'])]
    fleet['location'] = plan['origin']
    for place in (plan['origin'],plan['destination']):
        state.ensure_regional_market(game,engine.maps,'human',place)
    source = game.economy_v2['markets'][f"human:{plan['origin']}"]
    target = game.economy_v2['markets'][f"human:{plan['destination']}"]
    item = next(key for key,row in source['commodities'].items() if 20 <= row['reference'] <= 100)
    for key,row in source['commodities'].items():
        row['stock'] = row['target'] * 3 if key == item else 0
        state.reprice(game,source,row)
    target['commodities'][item]['stock'] = 0
    state.reprice(game,target,target['commodities'][item])
    player = copy.deepcopy(game.player.to_dict()); money=cash(game)
    caravans.advance_caravans(game,engine.maps)
    assert fleet['status'] == 'travelling' and fleet['cargo']['array_fee'] > 0
    assert balance(game,f"transport:human:{plan['array_operator']}") == fleet['cargo']['array_fee']
    assert cash(game) == money and game.player.to_dict() == player


def test_repeated_real_losses_shrink_and_eventually_close_fleet(trade, monkeypatch):
    engine, game, fleet, *_ = trade
    monkeypatch.setattr(caravans,'_roll',lambda *args:0)
    for _ in range(600):
        game.player.age += 1
        state.advance_economy(game)
        caravans.advance_caravans(game,engine.maps)
        if fleet['status'] == 'retired':
            break
    assert fleet['lost'] > 0 and fleet['profit'] < 0 and fleet['status'] == 'retired'
    assert balance(game,f'caravan:{fleet["id"]}') == 0


def test_canonical_crossing_keeps_cargo_in_original_world(trade, monkeypatch):
    engine, game, fleet, *_ = trade
    dispatch(trade)
    cargo = copy.deepcopy(fleet['cargo'])
    plan = engine._plan_world_transition(game,'spirit','rift',reason='商队异地年度验收')
    engine._apply_world_transition(game,plan)
    assert fleet['world'] == 'human' and fleet['cargo'] == cargo
    assert caravans.public_caravans(game,engine.maps) == []
    monkeypatch.setattr(caravans,'_roll',lambda *args:.99)
    game.player.age = cargo['arrival']; state.advance_economy(game)
    caravans.advance_caravans(game,engine.maps)
    assert fleet['cargo'] is None and fleet['delivered'] > 0
    assert game.player.world == 'spirit'


def test_insolvent_fleet_retires_without_a_bailout(trade):
    engine, game, fleet, *_ = trade
    dispatch(trade)
    # Establish a legitimate liquidation boundary after the cargo was lost.
    fleet['cargo']['risk'] = 1
    fleet['cargo']['quantity'] = 0
    arrive(trade); caravans.advance_caravans(game,engine.maps)
    key = f'caravan:{fleet["id"]}'
    transfer_value(game,key,'background:human',balance(game,key),'验收清空商队周转金')
    game.player.age += 1
    before = cash(game)
    caravans.advance_caravans(game,engine.maps)
    assert fleet['status'] == 'retired' and cash(game) == before


def test_read_only_projection_hides_remote_world_and_nonmember_accounts(trade):
    engine, game, fleet, *_ = trade
    dispatch(trade)
    before = copy.deepcopy(game.to_dict())
    rows = caravans.public_caravans(game,engine.maps)
    assert all('cash' not in row and 'cargo' not in row for row in rows)
    assert game.to_dict() == before
    game.merchant_state['membership'] = dict(world='human',alliance_id=fleet['alliance_id'],site='hq',rank=0)
    rows = caravans.public_caravans(game,engine.maps)
    assert next(row for row in rows if row['id']==fleet['id'])['cargo']['quantity'] > 0
    assert not any('cargo' in row for row in caravans.public_caravans(game,engine.maps,local=True))


@pytest.mark.parametrize('corruption',['owner','foreign_cargo','negative','duplicate_wallet'])
def test_invalid_transport_preserves_save(trade, corruption):
    engine, game, fleet, *_ = trade
    dispatch(trade)
    if corruption == 'owner': fleet['alliance_id'] = 'sect-caravan'
    elif corruption == 'foreign_cargo': fleet['cargo']['destination'] = 'spirit:town'
    elif corruption == 'negative': fleet['cargo']['quantity'] = -1
    else: game.economy_v2['accounts']['alliance:human:human-0'] = dict(balance=123,income=0,expense=0)
    path = engine.store._path(game.id)
    path.write_text(json.dumps(game.to_dict(),ensure_ascii=False),encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(ValueError): engine.store.load(game.id)
    assert path.read_bytes() == before


def test_first_round_adoption_keeps_merchant_capital_and_rng(trade):
    engine, game, *_ = trade
    engine.store.save(game)
    game = engine._load(game.id)  # Settle unrelated age-driven shelf refresh first.
    game.economy_v2.pop('transport')
    before = copy.deepcopy(game.merchant_state); rng = game.rng_state
    engine.store.save(game)
    loaded = engine._load(game.id)
    assert loaded.merchant_state == before and loaded.rng_state == rng
    before = copy.deepcopy(loaded.to_dict())
    assert not caravans.ensure_caravans(loaded,engine.maps)
    assert loaded.to_dict() == before


def test_public_action_advances_freight_on_the_shared_year_clock(trade):
    engine, game, fleet, *_ = trade
    game.settings['silent_events'] = True
    engine.store.save(game)
    before = game.player.age
    result = engine.advance(game.id, 'rest', 1)
    loaded = engine.store.load(game.id)
    region = loaded.economy_v2['transport']['worlds']['human']
    assert result['player']['age'] > before
    assert region['last_year'] == loaded.player.age
    assert region['fleets'][fleet['id']]['voyages'] > 0


def test_long_running_fleets_have_bounded_state_and_actual_profit(trade):
    engine, game, *_ = trade
    for _ in range(1000):
        game.player.age += 1
        state.advance_economy(game)
        caravans.advance_caravans(game,engine.maps)
    region = game.economy_v2['transport']['worlds']['human']
    from cultivation_life.system.economy.fleet_network import active_fleets, fleet_limit
    assert len(region['fleets']) <= 100 and len(region['history']) <= 36
    for alliance in game.merchant_state['worlds']['human']:
        assert len(active_fleets(game, 'human', 'alliance', alliance['id'])) <= fleet_limit('alliance', alliance)
    assert any(row['delivered'] > 0 for row in region['fleets'].values())
    assert all(row['capacity'] <= 240 for row in region['fleets'].values())
    assert len(game.economy_v2['ledger']) <= 80
    GameState.from_dict(game.to_dict())
