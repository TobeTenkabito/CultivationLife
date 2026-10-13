"""Regressions found while auditing idle estates and their accounting extensions."""
import copy

import pytest

from cultivation_life.models import GameState
from cultivation_life.system.economy.enterprise_market import market_at
from cultivation_life.system.economy.enterprise_operations import advance_estates, annual_maintenance
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.local_market import quote
from test_economy_enterprises import buy, configure, estate_act
from test_economy_network import economy, cash


def test_missing_materials_cannot_create_estate_sales_through_real_time_command(economy):
    engine, game = economy
    game, key = buy(engine, game, 'farm')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = configure(engine, game, key, enabled=True, auto_buy=False, auto_sell=True)
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='原料不足'):
        engine.fleet_action(game.id, dict(action='estate_start', estate_id=key,
                                        revision=game.economy_v2['estates'][key]['revision']))
    assert engine.store._path(game.id).read_bytes() == saved
    engine.advance(game.id, 'rest', 10)
    game = engine._load(game.id)
    row = game.economy_v2['estates'][key]
    assert row['income'] == row['produced'] == 0
    assert row['job'] is None and not row['stock']
    assert row['expense'] + row['arrears'] > game.player.age - row['history'][0][0]
    assert balance(game, 'estate:' + key) == 10000 - row['expense']
    # The market includes real background organizations and fleets, even when
    # this estate has no inputs. Its turnover is not the estate's own revenue.
    assert game.economy_v2['markets']['human:' + row['location']]['turnover'] > 0


def test_recall_steward_stops_automatic_sales_and_new_batches(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = estate_act(engine, game, key, 'entrust', enabled=True)
    game = estate_act(engine, game, key, 'start')
    game = estate_act(engine, game, key, 'entrust', enabled=False)
    row = game.economy_v2['estates'][key]
    job = copy.deepcopy(row['job'])
    assert not row['enabled'] and not row['entrusted']
    game.player.age = job['finish']
    advance_estates(game, engine.maps)
    assert row['produced'] == job['quantity'] and row['income'] == 0
    assert row['stock'] == {job['item']: job['quantity']} and row['job'] is None
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


def test_entrusted_sale_quota_is_not_spent_twice_in_one_settlement(economy):
    engine, game = economy
    game, key = buy(engine, game, 'farm')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = configure(engine, game, key, enabled=True, auto_sell=True, sale_quota=1)
    game = estate_act(engine, game, key, 'start')
    row = game.economy_v2['estates'][key]
    row.update(entrusted=True, stock={'dew_grass_ten': 4})
    before = cash(game)
    game.player.age += 1
    advance_estates(game, engine.maps)
    assert row['stock'] == {'dew_grass_ten': 3}
    assert cash(game) == before


def test_war_takeover_cancels_previous_stewards_authority(economy):
    from cultivation_life.system.economy.organizations import register
    from test_economy_governance import war_fixture
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = estate_act(engine, game, key, 'start')
    register(game, 'sect', 'wanmo', 'human')
    row = game.economy_v2['estates'][key]
    row.update(owner_kind='sect', owner_id='wanmo', entrusted=True, enabled=True)
    job = copy.deepcopy(row['job'])
    war = war_fixture(engine, game)
    before = cash(game)
    engine.war_peace(game.id, war['id'], 'economic_rights')
    game = engine._load(game.id)
    row = game.economy_v2['estates'][key]
    assert not row['enabled'] and not row['entrusted']
    assert row['job'] == job and row['reserve'] == 4996 and cash(game) == before
    game.player.age = job['finish']
    advance_estates(game, engine.maps)
    assert row['stock'] == {job['item']: job['quantity']} and row['income'] == 0
    assert row['job'] is None


def test_organization_arrears_payment_counts_as_a_paid_cost(economy):
    from cultivation_life.system.economy.organizations import register
    from cultivation_life.system.economy.organization_accounts import estate_sale
    from test_economy_network import act
    engine, game = economy
    game.player.faction_id = 'tianjian'
    game.sects['tianjian'].founded_by_player = True
    register(game, 'sect', 'tianjian', 'human')
    game, key = buy(engine, game, 'shop')
    row = game.economy_v2['estates'][key]
    row.update(owner_kind='sect', owner_id='tianjian', arrears=1000)
    source = 'organization:sect:tianjian'
    transfer_value(game, 'background:human', source, 10000, '测试周转金')
    org = game.economy_v2['organizations'][source]
    org['estate_cost_credit'] = 0
    game = act(engine, game, 'estate_pay_arrears', estate_id=key, revision=row['revision'])
    org = game.economy_v2['organizations'][source]
    row = game.economy_v2['estates'][key]
    assert row['expense'] == 1000 and row['arrears'] == 0
    assert org['estate_cost_credit'] == 1000
    assert estate_sale(game, row, 500) == 0 and org['estate_cost_credit'] == 500


def test_empty_estate_and_paid_work_have_real_maintenance(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    row = game.economy_v2['estates'][key]
    market = market_at(game, engine.maps, row)
    base = annual_maintenance(row, market)
    assert base > 1
    row['level'] = 2
    assert annual_maintenance(row, market) > base
    game, farm = buy(engine, game, 'farm')
    game = estate_act(engine, game, farm, 'fund', amount=10000)
    game = configure(engine, game, farm)
    game = estate_act(engine, game, farm, 'start')
    row = game.economy_v2['estates'][farm]
    job = row['job']
    product = market['commodities'][job['item']]
    product['price'] = 100000
    assert annual_maintenance(row, market) >= 800


def test_shop_does_not_automatically_purchase_a_guaranteed_spread_loss(economy):
    engine, game = economy
    game, key = buy(engine, game, 'shop')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    game = configure(engine, game, key, recipe='dew_grass_seed', enabled=True, auto_sell=True)
    row = game.economy_v2['estates'][key]
    market = market_at(game, engine.maps, row)
    assert quote(market['commodities']['dew_grass_seed'], 'buy', 4)['total'] > quote(
        market['commodities']['dew_grass_seed'], 'sell', 4)['total']
    before = cash(game)
    game.player.age += 1
    advance_estates(game, engine.maps)
    assert not row['stock'] and row['income'] == 0
    assert row['expense'] == annual_maintenance(row, market)
    assert cash(game) == before
