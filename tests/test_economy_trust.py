"""Opt-in management and fiscal periods through original paid authorities."""
import copy
from unittest.mock import patch

import pytest

from cultivation_life.models import GameState
from cultivation_life.system.economy import organizations, caravans
from cultivation_life.system.economy.economy_trust import prepare, grow, CONFIG
from cultivation_life.system.economy.enterprise_operations import advance_estates, market_trade
from cultivation_life.system.economy.enterprise_market import market_at
from cultivation_life.system.economy.enterprise_rules import recipes
from cultivation_life.system.economy.state import commodity_catalog
from cultivation_life.system.economy.ledger import transfer_value, balance
from cultivation_life.system.economy.fleet_network import guard_required, guard_cost
from cultivation_life.system.economy.organization_accounts import caravan_dividend
from test_economy_network import economy, cash, act
from test_economy_enterprises import buy, estate_act, own_fleet, fleet


def test_annual_finance_uses_real_settlement_period_and_is_readonly(economy):
    engine, game = economy
    org = organizations.register(game, 'sect', 'tianjian', 'human')
    game.player.age += 5
    organizations.advance_organizations(game, engine.maps)
    frozen = copy.deepcopy(game.to_dict())
    shown = organizations.public_finance(game, 'sect', 'tianjian')
    assert org['settlement_years'] == 5
    assert shown['annual_income'] == org['income']/5
    assert shown['annual_expense'] == org['expense']/5
    assert shown['turnover'] >= shown['income'] > 0
    assert game.to_dict() == frozen
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


def test_old_fiscal_period_does_not_guess_annual_income(economy):
    _, game = economy
    org = organizations.register(game, 'sect', 'tianjian', 'human')
    org.pop('settlement_years')
    org.update(income=5000, expense=2000)
    shown = organizations.public_finance(game, 'sect', 'tianjian')
    assert shown['annual_income'] is None and shown['annual_expense'] is None


def test_dividend_is_counted_once_after_caravan_settlement(economy):
    engine, game = economy
    org = organizations.register(game, 'sect', 'tianjian', 'human')
    f = dict(owner_kind='sect', owner_id='tianjian')
    source = 'organization:sect:tianjian'
    before = cash(game)
    transfer_value(game, 'background:human', source, 700, '测试商队真实分红')
    caravan_dividend(game, f, 700)
    assert org['pending_income'] == 700
    game.player.age += 1
    with patch.object(organizations, 'settle_faction'), patch('cultivation_life.system.economy.enterprise_operations.advance_estates'), patch('cultivation_life.system.economy.market_governance.advance_governance'):
        organizations.advance_organizations(game, engine.maps)
        assert org['income'] == 700 and 'pending_income' not in org
        organizations.advance_organizations(game, engine.maps)
        assert org['income'] == 700
        game.player.age += 1
        organizations.advance_organizations(game, engine.maps)
        assert org['income'] == 0
    assert cash(game) == before


def test_turnover_excludes_funding_and_distinguishes_sales(economy):
    engine, game = economy
    game, key = buy(engine, game, 'shop')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    row = game.economy_v2['estates'][key]
    assert row.get('turnover', 0) == row['income'] == row['expense'] == 0
    market = market_at(game, engine.maps, row)
    purchase = market_trade(game, row, market, 'dew_grass_seed', 1, 'buy')
    sale = market_trade(game, row, market, 'dew_grass_seed', 1, 'sell')
    assert row['turnover'] == purchase['gross'] + sale['gross']
    assert row['income'] == sale['total'] and row['expense'] == purchase['total']
    assert row['income'] - row['expense'] < 0


def test_setting_persists_and_disable_restores_plan_preserving_paid_job(economy):
    engine, game = economy
    assert not game.settings['economy_trust']
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    engine.update_setting(game.id, 'economy_trust', True)
    game = engine._load(game.id)
    row = game.economy_v2['estates'][key]
    previous = {k:row.get(k,default) for k,default in CONFIG.items()}
    player_cash, total = balance(game, 'player'), cash(game)
    market = market_at(game, engine.maps, row)
    for recipe in recipes('human', commodity_catalog('human')).values():
        if recipe['kind'] == 'mine':
            market['commodities'][recipe['output']]['stock'] = 0
    game.player.age += 1
    advance_estates(game, engine.maps)
    assert row.get('trust_config') and row['job']
    job = copy.deepcopy(row['job'])
    engine.store.save(game)
    engine.update_setting(game.id, 'economy_trust', False)
    game = engine._load(game.id)
    row = game.economy_v2['estates'][key]
    assert {k:row[k] for k in previous} == previous and 'trust_config' not in row
    assert row['job'] == job and balance(game, 'player') == player_cash
    game.player.age = job['finish']
    advance_estates(game, engine.maps)
    assert row['job'] is None and row['stock'] == {job['item']:job['quantity']}
    assert row['income'] == 0 and cash(game) == total


def test_trust_missing_inputs_never_invents_output_or_sales(economy):
    engine, game = economy
    game, key = buy(engine, game, 'farm')
    game = estate_act(engine, game, key, 'fund', amount=10000)
    row = game.economy_v2['estates'][key]
    market = market_at(game, engine.maps, row)
    for recipe in recipes(row['world'], commodity_catalog(row['world'])).values():
        if recipe['kind'] == 'farm':
            for item in recipe['inputs']:
                market['commodities'][item]['stock'] = 0
    game.settings['economy_trust'] = True
    before = cash(game)
    game.player.age += 1
    advance_estates(game, engine.maps)
    assert row['job'] is None and not row['stock']
    assert row['produced'] == row['income'] == row.get('turnover',0) == 0
    assert cash(game) == before


def test_trust_guard_is_paid_from_fleet_and_hold_order_is_preserved(economy):
    engine, game = economy
    game, key = own_fleet(engine, game)
    game.settings['economy_trust'] = True
    f = fleet(game, key)
    f['trade_order'] = {'mode':'hold'}
    player_cash, total = balance(game, 'player'), cash(game)
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    assert f['trade_order'] == {'mode':'hold'} and f['guard_power'] == 0 and f['cargo'] is None
    f['trade_order'] = {'mode':'auto'}
    before_profit, before_cost = f['profit'], f['operating_costs']
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    assert f['guard_power'] == guard_required('human')
    assert f['operating_costs'] - before_cost >= guard_cost('human')
    assert balance(game, 'player') == player_cash and cash(game) == total
    assert f['profit'] < before_profit


def test_loss_or_capital_alone_does_not_enable_investment(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=1000000)
    game.settings['economy_trust'] = True
    row = game.economy_v2['estates'][key]
    before = cash(game)
    prepare(game, row)
    grow(game, engine.maps, row, market_at(game, engine.maps, row))
    assert len(game.economy_v2['estates']) == 1 and row['level'] == 1
    assert 'trust_growth_year' not in game.economy_v2 and cash(game) == before


def test_profit_investment_uses_original_cash_and_bounded_cadence(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=1000000)
    game.settings['economy_trust'] = True
    row = game.economy_v2['estates'][key]
    prepare(game, row)
    market = market_at(game, engine.maps, row)
    item = recipes('human', commodity_catalog('human'))[row['recipe']]['output']
    # A test fixture of pre-existing real inventory; sale uses the actual funded
    # dealer and original stock depletion, not a synthetic income increment.
    row['stock'] = {item:1000}
    market['commodities'][item].update(price=1000, reference=1000, target=10000, stock=0)
    before = cash(game)
    market_trade(game, row, market, item, 1000, 'sell')
    grow(game, engine.maps, row, market)
    assert row['level'] == 2 and game.economy_v2['trust_growth_year'] == game.player.age
    frozen = copy.deepcopy(game.economy_v2)
    grow(game, engine.maps, row, market)
    assert game.economy_v2 == frozen and cash(game) == before
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


def test_failed_guard_command_is_atomic_and_guard_cannot_be_purchased_twice(economy):
    engine, game = economy
    game, key = own_fleet(engine, game)
    game = act(engine, game, 'guard', fleet_id=key)
    frozen = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='足额'):
        engine.fleet_action(game.id, {'action':'guard', 'fleet_id':key})
    assert engine.store._path(game.id).read_bytes() == frozen


def test_invalid_trust_snapshot_or_fiscal_counter_is_rejected(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game.economy_v2['estates'][key]['trust_config'] = {'world':'spirit'}
    with pytest.raises(ValueError): GameState.from_dict(game.to_dict())
    game.economy_v2['estates'][key].pop('trust_config')
    org = organizations.register(game, 'sect', 'tianjian', 'human')
    org['settlement_years'] = -1
    with pytest.raises(ValueError): GameState.from_dict(game.to_dict())


def test_new_property_is_funded_from_real_profit_and_waits_until_next_tick(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=1000000)
    row = game.economy_v2['estates'][key]
    row['level'] = 5
    game.settings['economy_trust'] = True
    prepare(game, row)
    market = market_at(game, engine.maps, row)
    item = recipes('human', commodity_catalog('human'))[row['recipe']]['output']
    row['stock'] = {item:1000}
    market['commodities'][item].update(price=1000, reference=1000, target=10000, stock=0)
    player_cash, total = balance(game, 'player'), cash(game)
    market_trade(game, row, market, item, 1000, 'sell')
    grow(game, engine.maps, row, market)
    assert len(game.economy_v2['estates']) == 2
    bought = next(e for e in game.economy_v2['estates'].values() if e['id'] != key)
    assert (bought['world'],bought['location'],bought['owner_kind'],bought['owner_id']) == ('human',row['location'],'player',game.id)
    assert balance(game,'estate:'+bought['id']) > 0 and not bought['job'] and not bought['enabled']
    assert cash(game) == total and balance(game,'player') == player_cash
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


def test_historical_profit_is_not_reused_when_starting_trust(economy):
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=1000000)
    row = game.economy_v2['estates'][key]
    row['income'] = 1000000
    game.settings['economy_trust'] = True
    prepare(game, row)
    grow(game, engine.maps, row, market_at(game,engine.maps,row))
    assert row['level'] == 1 and 'trust_growth_year' not in game.economy_v2


def test_century_jump_replans_once_and_does_not_replay_unstarted_jobs(economy):
    from cultivation_life.system.economy import estate_management
    engine, game = economy
    game, key = buy(engine, game, 'mine')
    game = estate_act(engine, game, key, 'fund', amount=100000)
    game.settings['economy_trust'] = True
    row = game.economy_v2['estates'][key]
    market = market_at(game, engine.maps, row)
    for recipe in recipes('human', commodity_catalog('human')).values():
        if recipe['kind'] == 'mine': market['commodities'][recipe['output']]['stock'] = 0
    before = cash(game)
    with patch.object(estate_management, 'plan', wraps=estate_management.plan) as calls:
        game.player.age += 100
        advance_estates(game, engine.maps)
        assert calls.call_count == 1 and row['produced'] == row['income'] == 0
        assert row['job'] and row['job']['started'] == game.player.age
        advance_estates(game, engine.maps)
        assert calls.call_count == 1
    assert cash(game) == before


def test_sales_between_fiscal_settlements_are_carried_once_without_mixing_periods(economy):
    from cultivation_life.system.economy.organization_accounts import operating_services
    engine, game = economy
    game, key = buy(engine, game, 'shop')
    row = game.economy_v2['estates'][key]
    org = organizations.register(game, 'sect', 'tianjian', 'human')
    row.update(owner_kind='sect',owner_id='tianjian',stock={'dew_grass_ten':10})
    before = cash(game)
    bill = market_trade(game,row,market_at(game,engine.maps,row),'dew_grass_ten',10,'sell')
    assert org['income'] == org['expense'] == org['turnover'] == 0
    assert org['pending_income'] == bill['total'] and org['pending_turnover'] == bill['gross']
    shown = organizations.public_finance(game,'sect','tianjian')
    assert shown['annual_income'] is None and shown['pending_income'] == bill['total']
    def settle(game,maps,row,years):
        operating_services(game,row,row['income']-row['expense'])
    game.player.age += 5
    with patch.object(organizations,'settle_faction',side_effect=settle), patch('cultivation_life.system.economy.enterprise_operations.advance_estates'), patch('cultivation_life.system.economy.market_governance.advance_governance'):
        organizations.advance_organizations(game,engine.maps)
        assert org['income'] == bill['total'] and org['turnover'] == bill['gross']
        assert org['expense'] == bill['total']*40//100
        assert 'pending_income' not in org and 'pending_turnover' not in org
        paid = org['expense']
        organizations.advance_organizations(game,engine.maps)
        assert org['expense'] == paid
    assert cash(game) == before


def test_original_organization_fleet_uses_existing_order_authority_for_guards(economy):
    engine, game = economy
    game, key = own_fleet(engine, game)
    organizations.register(game,'sect','tianjian','human')
    game.sects['tianjian'].founded_by_player = True
    game.player.faction_id = 'tianjian'
    f = fleet(game,key)
    f.update(owner_kind='sect',owner_id='tianjian',player_controlled=False)
    before = cash(game)
    game = act(engine,game,'guard',fleet_id=key)
    assert fleet(game,key)['guard_power'] == guard_required('human') and cash(game) == before
    # Revoked organization control must also revoke the guard command.
    game.sects['tianjian'].founded_by_player = False
    game.player.faction_id = None
    fleet(game,key)['guard_power'] = 0
    engine.store.save(game)
    frozen = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='只能安排'):
        engine.fleet_action(game.id,{'action':'guard','fleet_id':key})
    assert engine.store._path(game.id).read_bytes() == frozen
