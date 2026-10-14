"""Real commands: current authority, voyage pay and deed cost ownership."""
import copy

import pytest

from test_economy_network import economy, act, cash
from test_economy_enterprises import buy, estate_act, own_fleet, fleet
from cultivation_life.models import GameState
from cultivation_life.system.economy import caravans, trade_orders
from cultivation_life.system.economy.enterprise_state import owner_allowed
from cultivation_life.system.economy.enterprise_acquisition import price
from cultivation_life.system.economy.enterprise_operations import advance_estates
from cultivation_life.system.economy.enterprise_view import public_estates
from cultivation_life.system.economy.estate_management import invest_surplus
from cultivation_life.system.economy.ledger import transfer_value, balance
from cultivation_life.system.economy.local_market import quote
from cultivation_life.system.economy.fleet_network import guard_wages
from cultivation_life.system.faction_geography import faction_site


def sect_owner(game):
    game.player.faction_id = 'tianjian'
    game.sects['tianjian'].founded_by_player = True
    transfer_value(game, 'player', 'organization:sect:tianjian', 100000, 'test actual organizational capital')


def test_stale_controller_cannot_expand_or_debit_original_treasury(economy):
    engine, game = economy
    sect = game.sects['tianjian']
    game.player.faction_id = sect.id
    game.player.location_id = faction_site(sect)['id']
    sect.founded_by_player = False
    transfer_value(game, 'player', 'organization:sect:tianjian', 100000, 'test capital')
    game.intrigue_state['factions']['sect:tianjian']['controller_id'] = 'player'
    engine.store.save(game)
    game = engine._load(game.id)
    assert not owner_allowed(game, 'sect', sect.id, 'human')
    frozen = engine.store._path(game.id).read_bytes()
    before = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError, match='执掌'):
        engine.fleet_action(game.id, dict(action='industry', owner_kind='sect'))
    assert engine.store._path(game.id).read_bytes() == frozen
    assert engine._load(game.id).to_dict() == before
    from cultivation_life.system.economy.network_actions import public_network
    snapshot = copy.deepcopy(game.to_dict())
    assert not public_network(game, engine.maps)['can_industry']['sect']
    assert game.to_dict() == snapshot


def test_current_qualified_member_can_expand_without_old_controller_cache(economy):
    engine, game = economy
    game.player.realm_index = 4
    game.player.faction_id = 'tianjian'
    game.player.location_id = faction_site(game.sects['tianjian'])['id']
    game.sects['tianjian'].founded_by_player = False
    game.intrigue_state['factions']['sect:tianjian']['controller_id'] = None
    transfer_value(game, 'player', 'organization:sect:tianjian', 100000, 'test capital')
    assert owner_allowed(game, 'sect', 'tianjian', 'human')
    total = cash(game)
    game = act(engine, game, 'industry', owner_kind='sect')
    assert game.economy_v2['organizations']['organization:sect:tianjian']['industry_level'] == 1
    assert cash(game) == total and GameState.from_dict(game.to_dict())


@pytest.mark.parametrize('mode', ['once', 'repeat'])
def test_manual_order_needs_exact_voyage_wages_and_pays_them_only_over_time(economy, mode):
    engine, game = economy
    game, identity = own_fleet(engine, game)
    game = act(engine, game, 'guard', fleet_id=identity)
    f = fleet(game, identity)
    routes = [caravans.route_quote(game, engine.maps, 'human', f['location'], r['id'], 1)
              for r in engine.maps.worlds['human']['locations'] if r['id'] != f['location']]
    route = max((r for r in routes if r), key=lambda r: r['years'])
    game = act(engine, game, 'order_configure', fleet_id=identity, mode=mode, kind='local',
               destination=route['destination'], item='dew_grass_seed', quantity=1, buy_limit=10**12, sell_limit=0)
    f = fleet(game, identity)
    offer = trade_orders.candidate(game, engine.maps, f, caravans.route_quote)
    cost = offer['cost']
    wages = guard_wages(f, offer['transport']['years'])
    key = 'caravan:' + identity
    transfer_value(game, key, 'background:human', balance(game, key)-cost-wages+1, 'test scarce working capital')
    engine.store.save(game)
    engine._load(game.id)
    frozen = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='工资'):
        engine.fleet_action(game.id, dict(action='order_dispatch', fleet_id=identity))
    assert engine.store._path(game.id).read_bytes() == frozen
    game = engine._load(game.id)
    transfer_value(game, 'player', key, 1, 'test complete voyage reserve')
    total = cash(game)
    game = act(engine, game, 'order_dispatch', fleet_id=identity)
    f = fleet(game, identity)
    assert balance(game, key) == wages and f['cargo']['cost'] == cost
    assert f['operating_costs'] == 0 and not f['cargo'].get('running_costs')
    assert cash(game) == total
    original_guard = f['guard_power']
    original_age = game.player.age
    engine.advance(game.id, 'rest', 1)
    game = engine._load(game.id)
    elapsed = game.player.age - original_age
    assert 0 < elapsed < route['years']
    f = fleet(game, identity)
    assert f['guard_power'] == original_guard
    assert f['cargo']['running_costs'] == guard_wages(f, elapsed)
    assert balance(game, key) == wages - guard_wages(f, elapsed)
    assert GameState.from_dict(game.to_dict())


@pytest.mark.parametrize('existing_credit', [None, 50])
def test_paid_deed_transfer_keeps_old_history_but_not_old_owner_cost_credit(economy, existing_credit):
    engine, game = economy
    game, identity = buy(engine, game, 'farm')
    game = estate_act(engine, game, identity, 'fund', amount=1000)
    game.player.age += 1
    advance_estates(game, engine.maps)
    row = game.economy_v2['estates'][identity]
    old_expense, old_reserve = row['expense'], row['reserve']
    old_history = copy.deepcopy(row['history'])
    assert old_expense > 0
    sect_owner(game)
    org = game.economy_v2['organizations']['organization:sect:tianjian']
    if existing_credit is not None:
        org['estate_cost_credit'] = existing_credit
    cost = price(game, engine.maps, row) // 2
    total = cash(game)
    game = estate_act(engine, game, identity, 'transfer', owner_kind='sect', cost=cost)
    row = game.economy_v2['estates'][identity]
    org = game.economy_v2['organizations']['organization:sect:tianjian']
    assert org['pending_expense'] == cost
    assert org['estate_cost_credit'] == (existing_credit or 0)
    assert row['expense'] == old_expense and row['reserve'] == old_reserve
    assert row['history'][:len(old_history)] == old_history and not row['stock']
    market = game.economy_v2['markets']['human:' + game.player.location_id]
    bill = quote(market['commodities']['dew_grass_seed'], 'buy', 1)
    game = estate_act(engine, game, identity, 'purchase', item='dew_grass_seed', quantity=1,
                      market_revision=market['revision'], total=bill['total'])
    org = game.economy_v2['organizations']['organization:sect:tianjian']
    assert org['estate_cost_credit'] == (existing_credit or 0) + bill['total']
    assert cash(game) == total and GameState.from_dict(game.to_dict())


@pytest.mark.parametrize('current_period', [False, True])
def test_manual_org_purchase_records_capital_once_in_real_period(economy, current_period):
    engine, game = economy
    sect_owner(game)
    key = 'organization:sect:tianjian'
    org = game.economy_v2['organizations'][key]
    if current_period:
        org['settlement_years'] = 1
    before = balance(game, key)
    total = cash(game)
    offer = next(o for o in public_estates(game, engine.maps)['offers'] if o['kind'] == 'farm')
    game = act(engine, game, 'estate_buy', kind='farm', owner_kind='sect', cost=offer['cost'])
    org = game.economy_v2['organizations'][key]
    field = 'expense' if current_period else 'pending_expense'
    assert org[field] == before - balance(game, key) == offer['cost']
    assert org['estate_cost_credit'] == 0 and not org.get('turnover') and not org.get('income')
    engine._load(game.id)
    frozen = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='所有者'):
        engine.fleet_action(game.id, dict(action='estate_buy', kind='farm', owner_kind='sect', cost=offer['cost']))
    assert engine.store._path(game.id).read_bytes() == frozen
    assert cash(game) == total and GameState.from_dict(game.to_dict())


def test_autonomous_purchase_books_same_interval_without_pending_duplicate(economy):
    engine, game = economy
    entity = game.sects['tianjian']
    game.player.faction_id = None
    entity.founded_by_player = False
    key = 'organization:sect:tianjian'
    transfer_value(game, 'player', key, 100000, 'test autonomous capital')
    finance = game.economy_v2['organizations'][key]
    finance['pending_expense'] = 19
    before = balance(game, key)
    total = cash(game)
    invest_surplus(game, engine.maps, entity, finance)
    assert any(row['owner_id'] == entity.id for row in game.economy_v2['estates'].values())
    assert finance['expense'] == before - balance(game, key) > 0
    assert finance['pending_expense'] == 19 and finance['estate_cost_credit'] == 0
    assert cash(game) == total and GameState.from_dict(game.to_dict())


def test_repeat_empty_return_also_requires_guard_wages(economy):
    engine, game = economy
    game, identity = own_fleet(engine, game)
    game = act(engine, game, 'guard', fleet_id=identity)
    origin = game.player.location_id
    destination = next(r['id'] for r in engine.maps.worlds['human']['locations'] if r['id'] != origin and not r.get('min_realm_index'))
    game = act(engine, game, 'order_configure', fleet_id=identity, mode='repeat', kind='local',
               destination=destination, item='dew_grass_seed', quantity=1, buy_limit=10**12, sell_limit=0)
    f = fleet(game, identity)
    # An already-completed outward leg; test the actual paid empty-return command.
    f['location'] = destination
    game.player.location_id = destination
    offer = trade_orders.candidate(game, engine.maps, f, caravans.route_quote)
    assert offer['empty_return'] and offer['quantity'] == 0
    wages = guard_wages(f, offer['transport']['years'])
    key = 'caravan:' + identity
    transfer_value(game, key, 'background:human', balance(game, key)-offer['cost']-wages+1, 'test return reserve short by one')
    engine.store.save(game)
    engine._load(game.id)
    frozen = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='工资'):
        engine.fleet_action(game.id, dict(action='order_dispatch', fleet_id=identity))
    assert engine.store._path(game.id).read_bytes() == frozen


def test_free_war_takeover_keeps_paid_cost_credit_in_original_treasury(economy):
    from test_economy_governance import war_fixture
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    engine, game = economy
    source = 'organization:sect:wanmo'
    transfer_value(game, 'player', source, 100000, 'test defeated treasury')
    row = acquire(game, engine.maps, 'human', game.player.location_id, 'farm', 'sect', 'wanmo', source, 4)
    identity = row['id']
    game.player.age += 1
    advance_estates(game, engine.maps)
    old_cost = game.economy_v2['organizations'][source]['estate_cost_credit']
    assert old_cost > 0
    physical = {k: copy.deepcopy(row[k]) for k in ('id', 'world', 'location', 'stock', 'job', 'reserve')}
    war = war_fixture(engine, game)
    total = cash(game)
    engine.war_peace(game.id, war['id'], 'economic_rights')
    game = engine._load(game.id)
    row = game.economy_v2['estates'][identity]
    assert row['owner_id'] == 'tianjian' and row['expense'] == old_cost
    assert {k: row[k] for k in physical} == physical
    assert game.economy_v2['organizations'][source]['estate_cost_credit'] == old_cost
    assert game.economy_v2['organizations']['organization:sect:tianjian']['estate_cost_credit'] == 0
    assert cash(game) == total and GameState.from_dict(game.to_dict())


def test_trust_purchase_books_capital_once_without_another_sales_cost_credit(economy):
    from cultivation_life.system.economy.economy_trust import prepare, grow
    from cultivation_life.system.economy.enterprise_operations import market_trade, market_at
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    from cultivation_life.system.economy.enterprise_rules import recipes
    from cultivation_life.system.economy.state import commodity_catalog
    engine, game = economy
    sect_owner(game)
    source = 'organization:sect:tianjian'
    row = acquire(game, engine.maps, 'human', game.player.location_id, 'mine', 'sect', 'tianjian', source, 2)
    row['level'] = 5  # Force purchase rather than upgrading this deed.
    game.settings['economy_trust'] = True
    prepare(game, row)
    market = market_at(game, engine.maps, row)
    item = recipes('human', commodity_catalog('human'))[row['recipe']]['output']
    row['stock'] = {item: 1000}
    market['commodities'][item].update(price=1000, reference=1000, target=10000, stock=0)
    finance = game.economy_v2['organizations'][source]
    finance['settlement_years'] = 1
    market_trade(game, row, market, item, 1000, 'sell')
    old_expense, old_credit = finance['expense'], finance['estate_cost_credit']
    old_cash, total = balance(game, source), cash(game)
    grow(game, engine.maps, row, market)
    assert len(game.economy_v2['estates']) == 2
    cost = old_cash - balance(game, source)
    assert cost > 0 and finance['expense'] == old_expense + cost
    assert finance['estate_cost_credit'] == old_credit
    frozen = copy.deepcopy(game.to_dict())
    grow(game, engine.maps, row, market)
    assert game.to_dict() == frozen and cash(game) == total
    assert GameState.from_dict(game.to_dict())
