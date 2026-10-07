"""Step two: authoritative property, actual production and commanded freight."""
import copy
import pytest
from test_economy_network import economy, act, cash, spirit
from cultivation_life.models import GameState
from cultivation_life.system.economy import caravans, cross_freight
from cultivation_life.system.economy.enterprise_view import public_estates
from cultivation_life.system.economy.enterprise_operations import advance_estates
from cultivation_life.system.economy.enterprise_rules import recipes
from cultivation_life.system.economy.state import commodity_catalog, ensure_regional_market
from cultivation_life.system.economy.ledger import transfer_value, balance
from cultivation_life.system.economy.local_market import quote


def buy(engine, game, kind):
    offer = next(o for o in public_estates(game, engine.maps)['offers'] if o['kind'] == kind)
    game = act(engine, game, 'estate_buy', kind=kind, cost=offer['cost'])
    return game, f'{game.player.world}:{game.player.location_id}:{kind}'


def estate_act(engine, game, identity, action, **payload):
    return act(engine, game, 'estate_' + action, estate_id=identity,
               revision=game.economy_v2['estates'][identity]['revision'], **payload)


def configure(engine, game, identity, **options):
    row = game.economy_v2['estates'][identity]
    return estate_act(engine, game, identity, 'configure', **(dict(recipe=row['recipe'], enabled=False,
        auto_buy=True, auto_sell=False, batches=1, buy_limit=10**12, sell_limit=0) | options))


def own_fleet(engine, game):
    game = act(engine, game, 'create')
    return game, next(f['id'] for f in game.economy_v2['transport']['worlds'][game.player.world]['fleets'].values() if f['player_controlled'])


def fleet(game, identity):
    return game.economy_v2['transport']['worlds'][game.player.world]['fleets'][identity]


def order(engine, game, identity, **options):
    places = engine.maps._locations[game.player.world]
    dest = next(k for k in places if k != game.player.location_id)
    return act(engine, game, 'order_configure', fleet_id=identity, **(dict(mode='once', kind='local',
        destination=dest, item='dew_grass_seed', quantity=1, buy_limit=10**12, sell_limit=0) | options))


def test_property_production_cash_and_readonly_reload(economy):
    engine, game = economy
    before = cash(game)
    game, key = buy(engine, game, 'farm')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = configure(engine, game, key)
    game = estate_act(engine, game, key, 'start')
    row = game.economy_v2['estates'][key]
    assert not row['stock'] and row['job']['inputs'] == {'dew_grass_seed': 1}
    assert row['job']['finish'] == game.player.age + 10
    snapshot = copy.deepcopy(game.to_dict())
    public_estates(game, engine.maps)
    assert game.to_dict() == snapshot and cash(game) == before
    game.player.age += 9
    advance_estates(game, engine.maps)
    assert not row['stock']
    game.player.age += 1
    advance_estates(game, engine.maps)
    assert row['stock'] == {'dew_grass_ten':4} and row['job'] is None
    once = copy.deepcopy(game.to_dict())
    advance_estates(game, engine.maps)
    assert game.to_dict() == once and cash(game) == before
    GameState.from_dict(game.to_dict())


def test_missing_inputs_stale_revision_and_remote_actions_atomic(economy):
    engine, game = economy
    game, key = buy(engine, game, 'farm')
    game = estate_act(engine, game, key, 'fund', amount=1000)
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        estate_act(engine, game, key, 'start')
    assert engine.store._path(game.id).read_bytes() == saved
    with pytest.raises(ValueError, match='已经变化'):
        engine.fleet_action(game.id, dict(action='estate_fund',estate_id=key,revision=0,amount=1))
    assert engine.store._path(game.id).read_bytes() == saved
    game.player.location_id = next(k for k in engine.maps._locations['human'] if k != game.player.location_id)
    with pytest.raises(ValueError, match='亲赴'):
        estate_act(engine, game, key, 'fund', amount=1)


def test_production_chain_consumes_real_crop_and_preserves_unique_field(economy):
    engine, game = economy
    personal = copy.deepcopy(game.player.spirit_field)
    game, farm = buy(engine, game, 'farm')
    game, alchemy = buy(engine, game, 'alchemy')
    for key in (farm, alchemy):
        game = estate_act(engine, game, key, 'fund', amount=10000)
        game = configure(engine, game, key)
    game = estate_act(engine, game, farm, 'start')
    game.player.age += 10
    advance_estates(game, engine.maps)
    game = estate_act(engine, game, farm, 'move_stock', item='dew_grass_ten', quantity=4, target_estate=alchemy)
    game = estate_act(engine, game, alchemy, 'start')
    job = game.economy_v2['estates'][alchemy]['job']
    assert job['inputs'].get('dew_grass_ten',0) > 0
    game.player.age = job['finish']
    advance_estates(game, engine.maps)
    assert game.economy_v2['estates'][alchemy]['stock'][job['item']] == job['quantity']
    assert game.player.spirit_field == personal
    assert cash(game) == cash(engine._load(game.id))


def test_finite_mine_resale_and_ownership_transfer_do_not_reset_reserve(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = configure(engine, game, key)
    game = estate_act(engine, game, key, 'start')
    assert game.economy_v2['estates'][key]['reserve'] == 4996
    with pytest.raises(ValueError, match='结清'):
        estate_act(engine, game, key, 'release', cost=1)
    game.player.age += 2
    advance_estates(game, engine.maps)
    item = next(iter(game.economy_v2['estates'][key]['stock']))
    game = estate_act(engine, game, key, 'withdraw', item=item, quantity=4)
    view = next(r for r in public_estates(game, engine.maps)['owned'] if r['id']==key)
    game = estate_act(engine, game, key, 'release', cost=view['release_price'])
    game, again = buy(engine, game, 'mine')
    assert again == key and game.economy_v2['estates'][key]['reserve'] == 4996


def test_warehouse_trade_and_no_free_old_production(economy):
    engine, game = economy
    game, key = buy(engine, game, 'shop')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    before = cash(game)
    market = game.economy_v2['markets'][f'{game.player.world}:{game.player.location_id}']
    row = market['commodities']['dew_grass_seed']
    stock = row['stock']
    game = estate_act(engine, game, key, 'purchase', item='dew_grass_seed', quantity=10,
        market_revision=market['revision'], total=quote(row,'buy',10)['total'])
    assert game.economy_v2['estates'][key]['stock']['dew_grass_seed']==10
    assert game.economy_v2['markets'][market['id']]['commodities']['dew_grass_seed']['stock']==stock-10
    assert cash(game)==before
    game, mine = buy(engine, game, 'mine')
    game = estate_act(engine, game, mine, 'fund', amount=10000)
    game = configure(engine, game, mine, enabled=True)
    game.player.age += 100
    advance_estates(game, engine.maps)
    assert game.economy_v2['estates'][mine]['produced']==0
    assert game.economy_v2['estates'][mine]['job']['started']==game.player.age


def test_manual_trade_limit_and_sale_retains_unpaid_goods(economy, monkeypatch):
    engine, game = economy
    game, fid = own_fleet(engine, game)
    game = order(engine, game, fid, buy_limit=0)
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='上限'):
        engine.fleet_action(game.id,dict(action='order_dispatch',fleet_id=fid))
    assert engine.store._path(game.id).read_bytes()==saved
    game = order(engine, game, fid, sell_limit=10**12)
    before = cash(game)
    game = act(engine, game, 'order_dispatch', fleet_id=fid)
    f = fleet(game,fid); cargo=f['cargo']
    assert cargo['quantity']==1 and cash(game)==before
    monkeypatch.setattr(caravans,'_roll',lambda *a:1.)
    game.player.age=cargo['arrival']
    region=game.economy_v2['transport']['worlds']['human']
    caravans._arrival(game,engine.maps,f,region)
    assert f['cargo']['quantity']==1 and f['status']=='selling'
    game.player.location_id=f['location']
    game=act(engine,game,'order_limits',fleet_id=fid,sell_limit=0)
    f=fleet(game,fid)
    before = cash(game)  # Loading after elapsed time adopts the explicit macro issue.
    caravans._arrival(game,engine.maps,f,game.economy_v2['transport']['worlds']['human'])
    assert f['cargo'] is None and f['trade_order']['mode']=='hold' and cash(game)==before
    GameState.from_dict(game.to_dict())


def test_production_completes_through_authoritative_year_command(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = estate_act(engine, game, key, 'start')
    engine.advance(game.id, 'rest', 2)
    game = engine._load(game.id)
    assert game.economy_v2['estates'][key]['produced'] == 4


def test_owned_alliance_fleets_disclose_accounts_without_foreign_membership(economy):
    engine, game = economy
    home = spirit(engine, game)
    home['player_owned'] = True
    game.merchant_state['membership'] = None
    view = caravans.public_caravans(game, engine.maps, home['id'])
    assert view and all(row['detail'] and 'cash' in row for row in view)


def test_org_title_uses_original_treasury_and_stays_at_its_world(economy):
    engine, game = economy
    home = spirit(engine, game);home['player_owned']=True
    transfer_value(game, 'background:spirit', f'alliance:spirit:{home["id"]}', 10**7, '验收')
    ensure_regional_market(game,engine.maps,'spirit',home['hq'])
    offer = next(o for o in public_estates(game,engine.maps)['offers'] if o['kind']=='mine')
    before=cash(game);reserve=home['reserves']
    game=act(engine,game,'estate_buy',kind='mine',owner_kind='alliance',cost=offer['cost'])
    key=f'spirit:{home["hq"]}:mine';row=game.economy_v2['estates'][key]
    assert f'estate:{key}' not in game.economy_v2['accounts']
    assert balance(game,f'alliance:spirit:{home["id"]}')==reserve-offer['cost'] and cash(game)==before
    game=estate_act(engine,game,key,'start')
    game.player.world='human';game.player.location_id=next(iter(engine.maps._locations['human']))
    game.player.age+=2;advance_estates(game,engine.maps)
    assert game.economy_v2['estates'][key]['produced']==4
    assert game.economy_v2['estates'][key]['world']=='spirit'
    assert not public_estates(game,engine.maps).get('owned')


def test_repeating_trade_pays_empty_return_and_does_not_clone_stock(economy,monkeypatch):
    engine,game=economy
    game,fid=own_fleet(engine,game)
    origin=game.player.location_id
    game=order(engine,game,fid,mode='repeat')
    game=act(engine,game,'order_dispatch',fleet_id=fid)
    monkeypatch.setattr(caravans,'_roll',lambda *a:1.)
    f=fleet(game,fid);region=game.economy_v2['transport']['worlds']['human']
    game.player.age=f['cargo']['arrival'];caravans._arrival(game,engine.maps,f,region)
    game.player.location_id=f['location']
    game=act(engine,game,'order_dispatch',fleet_id=fid)
    f=fleet(game,fid)
    assert f['cargo']['empty_return'] and f['cargo']['quantity']==0 and f['cargo']['cost']>0
    assert f['cargo']['destination']==origin
    game.player.age=f['cargo']['arrival'];caravans._arrival(game,engine.maps,f,game.economy_v2['transport']['worlds']['human'])
    assert f['location']==origin and f['trade_order']['mode']=='repeat'
    GameState.from_dict(game.to_dict())


def test_warehouse_delivery_uses_one_cargo_and_waits_for_space(economy,monkeypatch):
    engine,game=economy
    game,source=buy(engine,game,'shop');origin=game.player.location_id
    game=estate_act(engine,game,source,'fund',amount=10000)
    market=game.economy_v2['markets'][f'human:{origin}'];product=market['commodities']['dew_grass_seed']
    game=estate_act(engine,game,source,'purchase',item='dew_grass_seed',quantity=10,market_revision=market['revision'],total=quote(product,'buy',10)['total'])
    game.player.location_id=next(k for k in engine.maps._locations['human'] if k!=origin)
    ensure_regional_market(game,engine.maps,'human',game.player.location_id)
    game,target=buy(engine,game,'shop')
    game.player.location_id=origin
    game,fid=own_fleet(engine,game)
    game=order(engine,game,fid,kind='delivery',source_estate=source,target_estate=target,quantity=10)
    game=act(engine,game,'order_dispatch',fleet_id=fid)
    assert not game.economy_v2['estates'][source]['stock']
    assert not game.economy_v2['estates'][target]['stock']
    monkeypatch.setattr(caravans,'_roll',lambda *a:1.)
    f=fleet(game,fid);region=game.economy_v2['transport']['worlds']['human']
    game.economy_v2['estates'][target]['stock']['dew_grass_seed']=999
    game.player.age=f['cargo']['arrival'];caravans._arrival(game,engine.maps,f,region)
    assert f['cargo']['quantity']==9 and game.economy_v2['estates'][target]['stock']['dew_grass_seed']==1000
    game.economy_v2['estates'][target]['stock'].clear()
    caravans._arrival(game,engine.maps,f,region)
    assert f['cargo'] is None and game.economy_v2['estates'][target]['stock']['dew_grass_seed']==9
    GameState.from_dict(game.to_dict())


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(level=6),lambda r:r.update(owner_id='another-player'),
    lambda r:r.update(stock={'dew_grass_seed':1001}),lambda r:r.update(batches=True),
    lambda r:r.update(reserve=5001),lambda r:r.update(world='unknown')])
def test_invalid_estates_rejected_without_migration(economy,mutation):
    engine,game=economy
    game,key=buy(engine,game,'mine');document=game.to_dict()
    mutation(document['economy_v2']['estates'][key])
    with pytest.raises(ValueError):GameState.from_dict(document)


def test_cross_manual_goods_and_limit_use_actual_passage(economy,monkeypatch):
    engine,game=economy
    home=spirit(engine,game)
    f=next(f for f in game.economy_v2['transport']['worlds']['spirit']['fleets'].values() if f['alliance_id']==home['id'])
    f.update(player_controlled=True,investment=1000000)
    transfer_value(game,'background:spirit',f'caravan:{f["id"]}',10**7,'验收')
    game=order(engine,game,f['id'],kind='cross',destination='true_demon',item='dew_grass_seed',quantity=2,sell_limit=10**12)
    game=act(engine,game,'order_dispatch',fleet_id=f['id'])
    f=fleet(game,f['id']);trip=f['cross_trip']
    assert trip['item']=='dew_grass_seed' and trip['quantity']==2 and trip['remittance_percent']==0
    monkeypatch.setattr(cross_freight,'_risk',lambda *a:None)
    game.player.age=trip['arrival'];cross_freight.advance_freight(game,engine.maps,f,{})
    assert trip['phase']=='selling' and trip['quantity']==2
    GameState.from_dict(game.to_dict())
