"""Economic invariants exercised through persisted public commands."""
import copy
import json
import math
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import request_scope, request_games
from cultivation_life.models import GameState
from cultivation_life.rules import add_item
from cultivation_life.system.economy import state, local_market as trading
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy.pricing import growth, total_price

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    view = engine.create_game('经济验收', 'supreme_metal', 'dao', 213, preset_id='core')
    game = engine._load(view['id'])
    game.pending_event = game.active_trial = None
    add_item(game.player, 'spirit_stone', 10**10)
    engine.store.save(game)
    return engine, game.id


def order(engine, gid, side='buy', quantity=10):
    game = engine._load(gid)
    market = state.local_market(game)
    item, row = next((key, row) for key, row in market['commodities'].items()
                     if row['tier'] == 1 and row['stock'] >= quantity)
    return dict(market_id=market['id'], revision=market['revision'], item_id=item,
                side=side, quantity=quantity, total=trading.quote(row, side, quantity)['total'])


def total_cash(game):
    return balance(game, 'player') + sum(a['balance'] for a in game.economy_v2['accounts'].values())


def test_real_buy_sell_fees_stock_and_stale_rejection(ready):
    engine, gid = ready
    payload = order(engine, gid)
    before = engine.store.load(gid)
    market = state.local_market(before)
    stock = market['commodities'][payload['item_id']]['stock']
    view = engine.trade_local_market(gid, payload)
    after = engine.store.load(gid)
    current = state.local_market(after)
    assert current['commodities'][payload['item_id']]['stock'] == stock - 10
    assert total_cash(before) == total_cash(after)
    assert current['fees'] > market['fees']
    assert balance(after, 'player') == balance(before, 'player') - payload['total']
    unchanged = engine.store._path(gid).read_bytes()
    with pytest.raises(ValueError, match='报价'):
        engine.trade_local_market(gid, payload)
    assert engine.store._path(gid).read_bytes() == unchanged
    row = current['commodities'][payload['item_id']]
    payload.update(side='sell', revision=current['revision'], total=trading.quote(row,'sell',10)['total'])
    engine.trade_local_market(gid, payload)
    final = engine.store.load(gid)
    assert state.local_market(final)['commodities'][payload['item_id']]['stock'] == stock
    assert total_cash(final) == total_cash(before)
    assert balance(final,'player') < balance(before,'player')
    assert view['map']['economy']['revision'] == current['revision']


@pytest.mark.parametrize('change', [dict(quantity=True),dict(quantity=0),dict(quantity=-1),dict(quantity=1000001),
    dict(side='steal'),dict(total=-1),dict(item_id='spirit_stone'),dict(market_id='other:town')])
def test_invalid_commands_do_not_touch_save_or_rng(ready, change):
    e,gid=ready
    payload=order(e,gid)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError): e.trade_local_market(gid, payload|change)
    assert e.store._path(gid).read_bytes()==before


def test_failed_save_preserves_request_cached_object(ready, monkeypatch):
    e,gid=ready
    payload=order(e,gid)
    before=e.store._path(gid).read_bytes()
    with request_scope(e):
        loaded=e._load(gid)
        original=copy.deepcopy(loaded.to_dict())
        def fail(*args): raise OSError('disk full')
        monkeypatch.setattr(e.store,'save',fail)
        with pytest.raises(OSError): e.trade_local_market(gid,payload)
        assert loaded.to_dict()==original
    assert e.store._path(gid).read_bytes()==before


def test_success_publishes_request_cache(ready):
    e,gid=ready;payload=order(e,gid)
    with request_scope(e):
        before=e._load(gid)
        e.trade_local_market(gid,payload)
        assert e._load(gid) is not before
        assert state.local_market(e._load(gid))['revision']>payload['revision']


def test_reserved_goods_survive_departure_and_return(ready):
    import random
    e,gid=ready;g=e._load(gid)
    offer=next(o for o in g.market_offers if o.get('economy_reserved'))
    e.toggle_market_offer_lock(gid,offer['id'])
    g=e._load(gid);location=g.player.location_id
    locked=copy.deepcopy(next(o for o in g.market_offers if o['id']==offer['id']))
    other=next(row['id'] for row in e.maps.worlds[g.player.world]['locations'] if row['id']!=location)
    g.player.location_id=other
    e._refresh_world_market(g,random.Random(9))
    old=g.economy_v2['markets'][f'{g.player.world}:{location}']
    assert old['reserved_offers'][0]==locked
    g.player.location_id=location
    e._refresh_world_market(g,random.Random(10))
    assert next(o for o in g.market_offers if o['id']==offer['id'])==locked
    assert not old.get('reserved_offers')


def test_liquidity_and_player_funds_are_real(ready):
    e,gid=ready
    payload=order(e,gid)
    game=e._load(gid)
    game.player.inventory=[i for i in game.player.inventory if i.id!='spirit_stone']
    e.store.save(game)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='灵石'):e.trade_local_market(gid,payload)
    assert e.store._path(gid).read_bytes()==before
    add_item(game.player,payload['item_id'],10)
    state.local_market(game)['revision']+=1
    game.economy_v2['accounts'][f'market:{payload["market_id"]}']['balance']=0
    e.store.save(game)
    row=state.local_market(game)['commodities'][payload['item_id']]
    payload.update(side='sell',revision=state.local_market(game)['revision'],total=trading.quote(row,'sell',10)['total'])
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='资金不足'):e.trade_local_market(gid,payload)
    assert e.store._path(gid).read_bytes()==before


@pytest.mark.parametrize('years',[10,100,1000,10000,1000000])
def test_long_growth_is_bounded_and_deterministic(ready,years):
    e,gid=ready
    g=e._load(gid)
    rng=g.rng_state
    g.player.age+=years
    assert state.advance_economy(g)
    for world in g.economy_v2['worlds'].values():
        assert 1<world['scale']<=1000
        assert math.isfinite(world['scale']) and len(world['history'])<=24
    assert g.rng_state==rng
    before=copy.deepcopy(g.economy_v2)
    assert not state.advance_economy(g)
    assert g.economy_v2==before
    GameState.from_dict(g.to_dict())


def test_bulk_and_split_orders_have_bounded_prices():
    assert total_price(100,120,100,120,'buy')/100 > total_price(100,120,1,120,'buy')
    assert total_price(100,120,100,120,'sell')/100 < total_price(100,120,1,120,'sell')
    for stock,quantity in [(120,100),(1000000,1000000),(0,1000000)]:
        for side in ('buy','sell'):
            total=total_price(100,stock,quantity,120,side)
            assert 0<=total<=300*quantity+1
    assert growth(999,100)<1000
    assert growth(1,10000)<1000


def test_old_save_adoption_keeps_assets_rng_and_current_prices(ready):
    e,gid=ready
    g=e._load(gid)
    g.economy_v2={}
    for offer in g.market_offers:
        for key in list(offer):
            if key.startswith('economy_'):offer.pop(key)
    inventory=copy.deepcopy(g.player.inventory)
    offers=[o['price'] for o in g.market_offers]
    rng=g.rng_state
    e.store.save(g)
    loaded=e._load(gid)
    assert loaded.player.inventory==inventory
    assert loaded.rng_state==rng
    assert [o['price'] for o in loaded.market_offers]==offers
    assert loaded.economy_v2['base_year']==g.player.age
    assert all(w['scale']==1 for w in loaded.economy_v2['worlds'].values())
    before=e.store._path(gid).read_bytes()
    e._load(gid)
    assert e.store._path(gid).read_bytes()==before


def test_lock_reserves_once_and_holds_price(ready):
    e,gid=ready
    g=e._load(gid)
    offer=next(o for o in g.market_offers if o.get('economy_reserved'))
    e.toggle_market_offer_lock(gid,offer['id'])
    g=e._load(gid)
    locked=next(o for o in g.market_offers if o['id']==offer['id'])
    price=locked['price']
    before=copy.deepcopy(g.economy_v2)
    assert not trading.sync_shelf(g)
    assert g.economy_v2==before
    row=state.local_market(g)['commodities'][offer['content_id']]
    row['stock']=0
    state.reprice(g,state.local_market(g),row)
    assert trading.shelf_price(g,locked)==price
    e.store.save(g)
    e.buy_market_offer(gid,offer['id'])
    saved=e.store.load(gid)
    assert next(o for o in saved.market_offers if o['id']==offer['id'])['sold']


def test_empty_shelf_refresh_never_creates_stock(ready):
    import random
    e, gid = ready
    g = e._load(gid)
    e._clear_market(g)
    market = state.local_market(g)
    for row in market['commodities'].values():
        row['stock'] = 0
    for seed in (27, 28):
        e._refresh_world_market(g, random.Random(seed))
        assert any(o.get('economy_unavailable') for o in g.market_offers)
        assert not any(o.get('economy_reserved') for o in g.market_offers)
        e._clear_market(g)
        assert all(row['stock'] == 0 for row in market['commodities'].values())


def test_public_projection_does_not_tick_or_leak_other_worlds(ready):
    from cultivation_life.system.economy.presentation import public_economy
    e,gid=ready;g=e._load(gid)
    before=copy.deepcopy(g.to_dict())
    result=public_economy(g)
    assert g.to_dict()==before
    assert 'worlds' not in result and 'accounts' not in result
    g.player.world='rift'
    assert public_economy(g)=={'available':False}


def test_captive_market_buttons_and_command_share_rejection(ready):
    from cultivation_life.system.economy.presentation import public_economy
    e,gid=ready;g=e._load(gid)
    g.player.ghost_captor={'id':'captor'}
    assert not public_economy(g)['can_trade']
    with pytest.raises(ValueError):trading.require_access(g)


def test_imported_player_goods_have_demand_without_local_generation(ready):
    e,gid=ready;g=e._load(gid)
    foreign=next(key for key in state.commodity_catalog('spirit') if key not in state.commodity_catalog('human'))
    add_item(g.player,foreign,10)
    e.store.save(g);g=e._load(gid)
    row=state.local_market(g)['commodities'][foreign]
    assert row['imported'] and row['stock']==0
    from cultivation_life.system.economy.presentation import public_economy
    shown=next(r for r in public_economy(g)['rows'] if r['id']==foreign)
    assert shown['can_buy'] == (row['tier'] <= g.player.realm_index + 1)
    g.player.age+=100
    state.advance_economy(g)
    assert row['stock']==0 and row['production']==0


def test_black_market_supply_is_separate_and_money_enters_world(ready):
    e,gid=ready;g=e._load(gid)
    g.auction_state.update(status='black_market',world=g.player.world,location_id=g.player.location_id,
                          location_name='经济验收集会')
    e.store.save(g)
    result=e.search_black_market(gid,'聚气珠')
    offer=result['auction_system']['black_market_results'][0]
    before=e.store.load(gid)
    stock=copy.deepcopy(state.local_market(before)['commodities'])
    world=f'world:{before.player.world}'
    e.buy_black_market_item(gid,offer['id'],3)
    after=e.store.load(gid)
    assert balance(after,world)-balance(before,world)==3*offer['price']
    assert total_cash(after)==total_cash(before)
    assert state.local_market(after)['commodities']==stock
    assert after.economy_v2['worlds'][after.player.world]['black_market_quantity']==3


def test_auction_listing_and_commission_reach_local_operator(ready):
    import random
    e,gid=ready;g=e._load(gid)
    e._schedule_auction(g,random.Random(213))
    g.auction_state.update(location_id=g.player.location_id,location_name='经济验收集会')
    e._open_auction(g,random.Random(213))
    add_item(g.player,'foundation_pill',1)
    e.store.save(g)
    before=e._load(gid)
    operator=f'operator:{state.local_market(before)["id"]}'
    e.consign_auction_item(gid,'foundation_pill',10)
    listed=e.store.load(gid)
    assert balance(listed,operator)>balance(before,operator)
    assert total_cash(listed)==total_cash(before)
    for _ in range(20):
        view=e.advance_auction_round(gid)
        if view['auction_system']['status']=='black_market':break
    after=e.store.load(gid)
    assert after.auction_state['economy_settled']
    fee=sum(lot['current_bid']-lot['seller_net'] for lot in after.auction_state['lots'] if 'seller_net' in lot)
    assert balance(after,operator)-balance(listed,operator)==fee
    assert total_cash(after)==total_cash(listed)


def test_ten_thousand_annual_ticks_keep_storage_bounded(ready):
    e,gid=ready;g=e._load(gid)
    for _ in range(10000):
        g.player.age+=1
        state.advance_economy(g)
    assert all(1<w['scale']<=1000 and len(w['history'])<=24 for w in g.economy_v2['worlds'].values())
    assert len(g.economy_v2['ledger'])<=80
    for row in state.local_market(g)['commodities'].values():
        assert math.isfinite(row['stock']) and row['stock']>=0 and len(row['history'])<=12
    assert len(json.dumps(g.economy_v2))<250000


@pytest.mark.parametrize('corrupt',[None,dict(schema_version=99)])
def test_invalid_economy_preserves_file(ready,corrupt):
    e,gid=ready
    path=e.store._path(gid)
    document=json.loads(path.read_text(encoding='utf-8'));document['economy_v2']=corrupt
    path.write_text(json.dumps(document),encoding='utf-8');before=path.read_bytes()
    with pytest.raises(ValueError):e._load(gid)
    assert path.read_bytes()==before
