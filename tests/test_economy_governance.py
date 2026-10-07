"""Third step: real peace entry, conserved title transfer and paid competition."""
import copy
import pytest
from test_economy_network import economy, act, cash
from test_economy_enterprises import buy, estate_act, configure
from cultivation_life.models import GameState
from cultivation_life.system.economy import market_power, market_governance, war_assets
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.state import local_market, settle_market
from cultivation_life.system.economy.organizations import register
from cultivation_life.system.economy.presentation import public_economy
from cultivation_life.system.economy.enterprise_operations import sell_stock


def war_fixture(engine, game):
    game.player.realm_index = 4
    game.player.faction_id = 'tianjian'
    game.sects['tianjian'].founded_by_player = True
    relation = engine._war_relation(game, 'sect', 'tianjian', 'wanmo')
    engine._set_diplomatic_relation(game, relation, 'war', 'tianjian', 'wanmo', 'sect', -75)
    war = game.wars[-1]
    war.update(war_score=100, battles=2, controller='player', status='peace_ready')
    engine.store.save(game)
    return war


def test_real_peace_transfers_unique_assets_and_fee_rights(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = estate_act(engine, game, key, 'start')
    row = game.economy_v2['estates'][key]
    register(game, 'sect', 'wanmo', 'human')
    row.update(owner_kind='sect', owner_id='wanmo')
    snapshot = copy.deepcopy(row)
    war = war_fixture(engine, game)
    before, rng = cash(game), game.rng_state
    engine.war_peace(game.id, war['id'], 'economic_rights')
    game = engine._load(game.id)
    row = game.economy_v2['estates'][key]
    assert row['owner_id'] == 'tianjian' and not row['enabled']
    for field in ('id', 'world', 'location', 'reserve', 'job', 'stock'):
        assert row[field] == snapshot[field]
    assert cash(game) == before  # The existing political vote may consume RNG.
    receipt = game.wars[-1]['economic_transfers'][0]
    assert receipt['estates'] == [key] and len(receipt['markets']) == 1
    assert not game.sects['wanmo'].extinct
    with pytest.raises(ValueError):
        engine.war_peace(game.id, war['id'], 'economic_rights')
    GameState.from_dict(game.to_dict())


def test_capacity_takeover_preserves_caravan_cash_and_ids(economy):
    engine, game = economy
    war = war_fixture(engine, game)
    fleets = list(game.economy_v2['transport']['worlds']['human']['fleets'].values())[:4]
    for f in fleets:
        f.update(owner_kind='sect', owner_id='wanmo', alliance_id='', trade_order={'mode':'hold'})
    before = {f['id']:(f['location'], copy.deepcopy(f['cargo']), balance(game, 'caravan:'+f['id'])) for f in fleets}
    total, rng = cash(game), game.rng_state
    war_assets.transfer(game, engine.maps, war, 'tianjian', 'wanmo', strict=True)
    assert sum(f['owner_id']=='tianjian' for f in fleets) == 2
    assert sum(f['owner_kind']=='independent' for f in fleets) == 2
    assert cash(game) == total and game.rng_state == rng
    for f in fleets:
        assert before[f['id']] == (f['location'], f['cargo'], balance(game, 'caravan:'+f['id']))
    saved = copy.deepcopy(game.to_dict())
    war_assets.transfer(game, engine.maps, war, 'tianjian', 'wanmo', strict=True)
    assert game.to_dict() == saved
    GameState.from_dict(saved)


def test_invalid_foreign_title_peace_is_atomic(economy):
    engine, game = economy
    war = war_fixture(engine, game)
    war['world'] = 'spirit'
    engine.store.save(game)
    engine._load(game.id)  # Complete normal load-time faction/realm reconciliation first.
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='同界'):
        war_assets.transfer(game, engine.maps, war, 'tianjian', 'wanmo', strict=True)
    with pytest.raises(ValueError, match='权力'):
        engine.war_peace(game.id, war['id'], 'economic_rights')
    assert engine.store._path(game.id).read_bytes() == before


def test_fee_distribution_only_new_earnings_and_policy_authority(economy):
    engine, game = economy
    register(game, 'sect', 'tianjian', 'human')
    game.sects['tianjian'].founded_by_player = True
    market = local_market(game)
    source = 'operator:'+market['id']
    transfer_value(game, 'player', source, 10000, '旧有资本')
    market_governance.assign(game, market, 'sect', 'tianjian', 'test')
    old = balance(game, 'organization:sect:tianjian')
    transfer_value(game, 'player', source, 1000, '实际手续费')
    game = act(engine, game, 'market_relief', market_id=market['id'], revision=market['revision'], amount=1000)
    market = local_market(game)
    market_governance.settle_claim(game, market)
    assert balance(game, 'organization:sect:tianjian') == old + 250
    game = act(engine, game, 'market_policy', market_id=market['id'], revision=market['revision'], policy='reinvest')
    assert local_market(game)['control']['policy'] == 'reinvest'
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.fleet_action(game.id, dict(action='market_policy', market_id=market['id'], revision=-1, policy='extract'))
    assert engine.store._path(game.id).read_bytes() == saved


@pytest.mark.parametrize('funded,imported', [(False,False),(True,False),(True,True)])
def test_competition_pays_for_native_supply_and_cannot_create_imports(economy, funded, imported):
    engine, game = economy
    market = local_market(game)
    item = next(iter(market['commodities']))
    product = market['commodities'][item]
    product.update(stock=0, imported=imported)
    market_power.record_trade(game, market, item, 'player', 'buy', 100000)
    if funded:
        transfer_value(game, 'player', 'operator:'+market['id'], 100000, '竞争资金')
    before = cash(game)
    game.player.age += 3
    extra = market_power.settle(game, market, 3)
    assert bool(extra) == (funded and not imported)
    assert market['competition'][item]['pressure'] == 48
    assert cash(game) == before
    assert market['location'] in market_power.rival_targets(game, game.player.world)
    assert market['competition'][item]['added'] == extra.get(item, 0)
    snapshot = copy.deepcopy(game.to_dict())
    public_economy(game)
    assert game.to_dict() == snapshot
    GameState.from_dict(snapshot)


def test_paid_supply_enters_local_stock_once_and_pressure_decays(economy):
    engine, game = economy
    market = local_market(game)
    item = next(iter(market['commodities']))
    market['commodities'][item]['stock'] = 0
    market_power.record_trade(game, market, item, 'player', 'buy', 100000)
    transfer_value(game, 'player', 'operator:'+market['id'], 100000, '竞争资金')
    game.player.age += 3
    settle_market(game, market)
    assert market['competition'][item]['added'] > 0 and market['commodities'][item]['stock'] > 0
    snapshot = copy.deepcopy(game.to_dict())
    settle_market(game, market)
    assert game.to_dict() == snapshot
    market['commodities'][item]['stock'] = market['commodities'][item]['target']
    market_power.settle(game, market, 3)
    assert market['competition'][item]['pressure'] == 12


def test_sale_quota_and_malformed_optional_state(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = configure(engine, game, key, sale_quota=2)
    row = game.economy_v2['estates'][key]
    from cultivation_life.system.economy.enterprise_rules import recipes
    from cultivation_life.system.economy.state import commodity_catalog
    item = recipes('human', commodity_catalog('human'))[row['recipe']]['output']
    row['stock'][item] = 10
    sell_stock(game, row, local_market(game))
    assert row['stock'][item] == 8
    broken = game.to_dict()
    broken['economy_v2']['estates'][key]['sale_quota'] = -1
    with pytest.raises(ValueError):
        GameState.from_dict(broken)


def test_departed_controller_cannot_collect_remote_fee_income(economy):
    engine, game = economy
    register(game, 'sect', 'tianjian', 'human')
    market = local_market(game)
    market_governance.assign(game, market, 'sect', 'tianjian', 'boundary')
    treasury = balance(game, 'organization:sect:tianjian')
    transfer_value(game, 'player', 'operator:'+market['id'], 1000, '真实手续费')
    game.sects['tianjian'].world = 'spirit'
    market_governance.settle_claim(game, market)
    assert balance(game, 'organization:sect:tianjian') == treasury
    game.sects['tianjian'].world = 'human'
    market_governance.settle_claim(game, market)
    assert balance(game, 'organization:sect:tianjian') == treasury
