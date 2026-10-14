"""Audit regressions through paid commands, original assets and annual clocks."""
import copy
from unittest.mock import patch

import pytest

from test_economy_network import economy, act, cash
from test_economy_enterprises import own_fleet, fleet
from test_release_290 import clan_game
from test_economy_governance import war_fixture
from cultivation_life.models import GameState
from cultivation_life.system.economy import caravans, organizations, depot, state, market_governance
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.enterprise_state import owner_allowed
from cultivation_life.system.economy.estate_management import settlement_interval
from cultivation_life.system.faction_geography import faction_site
from cultivation_life.system.organization_heritage import decision


def test_join_relabels_market_rights_without_losing_receipts_or_save(economy):
    engine, _ = economy
    game, family = clan_game(engine)
    state.ensure_regional_market(game, engine.maps, 'human', family.location_id)
    market = game.economy_v2['markets']['human:' + family.location_id]
    market_governance.assign(game, market, 'sect', family.id, 'audit-war')
    old_claim = copy.deepcopy(market['control'])
    people = [n.id for n in family.npcs]
    treasury = balance(game, 'organization:sect:' + family.id)
    total = cash(game)
    engine.store.save(game)
    engine.family_action(game.id, 'join', {'target_id': family.id})
    game = engine._load(game.id)
    claim = game.economy_v2['markets'][market['id']]['control']
    assert claim == old_claim | {'kind': 'family'}
    assert [n.id for n in game.family.npcs] == people
    assert balance(game, 'organization:family:' + family.id) == treasury
    assert cash(game) == total
    transfer_value(game, 'background:human', 'operator:' + market['id'], 1000, 'test real fee receipt')
    market_governance.settle_claim(game, game.economy_v2['markets'][market['id']])
    assert balance(game, 'organization:family:' + family.id) == treasury + 250
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


def test_low_rank_external_member_cannot_spend_family_industry_cash(economy):
    engine, _ = economy
    game, family = clan_game(engine)
    game.player.realm_index = 2
    engine.store.save(game)
    engine.family_action(game.id, 'join', {'target_id': family.id})
    game = engine._load(game.id)
    assert not decision(game, game.family)
    engine._load(game.id)
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='权|执掌'):
        engine.fleet_action(game.id, {'action': 'industry', 'owner_kind': 'family'})
    assert engine.store._path(game.id).read_bytes() == saved


def captured_fleet(engine, game):
    f = next(iter(game.economy_v2['transport']['worlds']['human']['fleets'].values()))
    key = f['id']
    f.update(owner_kind='sect', owner_id='wanmo', alliance_id='', player_controlled=False, guard_power=0)
    game.player.location_id = f['location']
    war = war_fixture(engine, game)
    engine.war_peace(game.id, war['id'], 'economic_rights')
    return engine._load(game.id), key


@pytest.mark.parametrize('legacy_flag', [False, True])
@pytest.mark.parametrize('cached_controller', [False, True])
def test_captured_fleet_revokes_orders_guards_and_trust_after_leaving(economy, legacy_flag, cached_controller):
    engine, game = economy
    game, key = captured_fleet(engine, game)
    fleet(game, key)['player_controlled'] = legacy_flag
    engine.store.save(game)
    engine.leave_faction(game.id)
    game = engine._load(game.id)
    assert not owner_allowed(game, 'sect', 'tianjian', 'human')
    if cached_controller:
        game.intrigue_state['factions']['sect:tianjian']['controller_id'] = 'player'
        engine.store.save(game)  # A frozen structure-10 political record, not live authority.
    from cultivation_life.system.economy.network_actions import public_network
    snapshot = copy.deepcopy(game.to_dict())
    shown = next(r for r in public_network(game, engine.maps)['fleets'] if r['id'] == key)
    assert not shown['can_order'] and not shown['can_guard'] and not shown['detail']
    assert game.to_dict() == snapshot
    saved = engine.store._path(game.id).read_bytes()
    for payload in ({'action': 'guard'}, {'action': 'order_configure', 'mode': 'hold'}, {'action': 'fund'}):
        with pytest.raises(ValueError, match='只能|权限'):
            engine.fleet_action(game.id, payload | {'fleet_id': key})
        assert engine.store._path(game.id).read_bytes() == saved
    game.settings['economy_trust'] = True
    fleet(game, key)['trade_order'] = {'mode': 'auto'}
    transfer_value(game, 'background:human', 'caravan:' + key, 10000, 'test existing fleet capital')
    fleet(game, key)['investment'] = 10000
    game.player.age += 1
    with patch.object(caravans, '_dispatch'):
        caravans.advance_caravans(game, engine.maps)
    assert fleet(game, key)['guard_power'] == 0


def test_legacy_capture_flag_is_not_personal_leadership_after_losing_control(economy):
    engine, game = economy
    game, key = captured_fleet(engine, game)
    fleet(game, key)['player_controlled'] = True
    game.sects['tianjian'].founded_by_player = False
    game.player.realm_index = 2
    engine.store.save(game)
    game = engine._load(game.id)
    assert game.player.faction_id == 'tianjian' and not owner_allowed(game, 'sect', 'tianjian', 'human')
    with pytest.raises(ValueError, match='只能|权限'):
        engine.fleet_action(game.id, {'action': 'guard', 'fleet_id': key})


def test_real_member_can_still_manage_personally_led_sect_fleet(economy):
    engine, game = economy
    entity = game.sects['tianjian']
    game.player.faction_id = entity.id
    game.player.location_id = faction_site(entity)['id']
    transfer_value(game, 'background:human', 'organization:sect:' + entity.id, 10000, 'test fleet capital')
    game = act(engine, game, 'create', owner_kind='sect')
    f = next(f for f in game.economy_v2['transport']['worlds']['human']['fleets'].values()
             if f['owner_kind'] == 'sect' and f['player_controlled'])
    game = act(engine, game, 'guard', fleet_id=f['id'])
    assert fleet(game, f['id'])['guard_power'] > 0


def travelling_fleet(engine, game):
    game, key = own_fleet(engine, game)
    game = act(engine, game, 'guard', fleet_id=key)
    f = fleet(game, key)
    choices = [caravans.route_quote(game, engine.maps, 'human', f['location'], r['id'], 1)
               for r in engine.maps.worlds['human']['locations'] if r['id'] != f['location']]
    route = max((r for r in choices if r), key=lambda r: r['years'])
    game = act(engine, game, 'order_configure', fleet_id=key, mode='once', kind='local',
               destination=route['destination'], item='dew_grass_seed', quantity=1, buy_limit=10**12, sell_limit=0)
    game = act(engine, game, 'order_dispatch', fleet_id=key)
    return game, key


def test_transit_wages_charge_elapsed_years_once_and_reduce_trip_profit(economy):
    engine, game = economy
    game, key = travelling_fleet(engine, game)
    f = fleet(game, key)
    years = f['cargo']['years'] - 1
    before = balance(game, 'caravan:' + key)
    original_profit = f['profit']
    total = cash(game)
    wages = round(f['guard_power']**.5) * years
    game.player.age += years
    caravans.advance_caravans(game, engine.maps)
    assert f['status'] == 'travelling'
    assert balance(game, 'caravan:' + key) == before - wages
    assert f['profit'] == original_profit - wages
    assert cash(game) == total
    snapshot = copy.deepcopy(game.to_dict())
    caravans.advance_caravans(game, engine.maps)
    assert game.to_dict() == snapshot
    game = GameState.from_dict(game.to_dict())
    f = fleet(game, key)
    cargo = copy.deepcopy(f['cargo'])
    final_wage = round(f['guard_power']**.5)
    game.player.age += 1
    with patch.object(caravans, '_roll', return_value=.99):
        caravans.advance_caravans(game, engine.maps)
    # Tiny manual loss-making cargo is deliberately allowed, but cannot pay dividends.
    assert f['cargo'] is None and f['dividends'] == 0
    assert f['profit'] == original_profit - wages - final_wage + f['sale_income'] - cargo['cost']
    assert cash(game) == total


def test_transit_unpaid_wages_reduce_guards_without_discarding_cargo(economy):
    engine, game = economy
    game, key = travelling_fleet(engine, game)
    f = fleet(game, key)
    transfer_value(game, 'caravan:' + key, 'background:human', balance(game, 'caravan:' + key), 'test cash exhaustion')
    original = copy.deepcopy(f['cargo'])
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    assert f['guard_power'] == 0 and f['status'] == 'travelling'
    assert f['cargo'] == original and balance(game, 'caravan:' + key) == 0


@pytest.mark.parametrize('settled', [False, True])
def test_manual_depot_purchase_books_paid_cost_and_gross_once(economy, settled):
    engine, game = economy
    entity = game.sects['tianjian']
    game.player.faction_id = entity.id
    game.player.location_id = faction_site(entity)['id']
    entity.founded_by_player = True
    transfer_value(game, 'background:human', 'organization:sect:' + entity.id, 100000, 'test existing treasury capital')
    if settled:
        game.player.age += 1
        organizations.advance_organizations(game, engine.maps)
    row = organizations.register(game, 'sect', entity.id, 'human')
    state.ensure_regional_market(game, engine.maps, 'human', entity.location_id)
    market = game.economy_v2['markets']['human:' + entity.location_id]
    item = next(k for k, r in depot.catalog('human').items() if r['kind'] == 'item'
                and market['commodities'].get(r['id'], {}).get('stock', 0) >= 1)
    storage = depot.ensure(game, entity)
    before = balance(game, 'organization:sect:' + entity.id)
    field = 'expense' if settled else 'pending_expense'
    turnover = 'turnover' if settled else 'pending_turnover'
    old_cost, old_volume = row.get(field, 0), row.get(turnover, 0)
    gross = market['turnover']
    total = cash(game)
    game = act(engine, game, 'depot_purchase', owner_id=entity.id, revision=storage['revision'], item=item, quantity=1)
    row = game.economy_v2['organizations']['organization:sect:' + entity.id]
    paid = before - balance(game, 'organization:sect:' + entity.id)
    assert row.get(field, 0) - old_cost == paid > 0
    assert row.get(turnover, 0) - old_volume == game.economy_v2['markets'][market['id']]['turnover'] - gross
    assert cash(game) == total
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


def test_annual_depot_purchase_is_not_double_booked_or_deferred(economy):
    engine, game = economy
    entity = game.sects['tianjian']
    row = organizations.register(game, 'sect', entity.id, 'human')
    transfer_value(game, 'background:human', 'organization:sect:' + entity.id, 100000, 'test existing depot capital')
    state.ensure_regional_market(game, engine.maps, 'human', entity.location_id)
    depot.ensure(game, entity)
    game.player.age += 1
    row.update(income=100000, expense=0, turnover=0)
    before = balance(game, 'organization:sect:' + entity.id)
    market = game.economy_v2['markets']['human:' + entity.location_id]
    gross = market['turnover']
    depot.advance(game, engine.maps, entity, row)
    assert row['expense'] == before - balance(game, 'organization:sect:' + entity.id) > 0
    assert row['turnover'] == market['turnover'] - gross > 0
    assert row.get('pending_expense', 0) == row.get('pending_turnover', 0) == 0


def test_cross_freight_wages_survive_reload_and_are_not_deducted_twice(economy):
    from test_economy_network_expansion import loaded_fleet
    from cultivation_life.system.economy import cross_freight
    engine, game = economy
    f = loaded_fleet(engine, game)
    transfer_value(game, 'background:spirit', 'alliance:spirit:xuanji', 100000000, 'test funded passage maintenance')
    order = dict(mode='once', kind='cross', origin=f['location'], destination='true_demon', item='dew_grass_seed', quantity=1,
                 buy_limit=10**12, sell_limit=0, return_item='dew_grass_seed')
    f['trade_order'] = order
    cross_freight.dispatch(game, engine.maps, f, 'true_demon', remittance_percent=0, order=order)
    key = f['id']
    before = balance(game, 'caravan:' + key)
    profit = f['profit']
    wage = round(f['guard_power']**.5)
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    assert balance(game, 'caravan:' + key) == before - wage
    assert f['profit'] == profit - wage and f['cross_trip']['running_costs'] == wage
    game = GameState.from_dict(game.to_dict())
    f = fleet(game, key)
    receipts = []
    finish = cross_freight._finish
    def capture(actual, ship):
        receipts.append(copy.deepcopy(ship['cross_trip']))
        return finish(actual, ship)
    with patch.object(cross_freight, '_risk'), patch.object(cross_freight, '_finish', side_effect=capture):
        for _ in range(20):
            if f.get('cross_trip') is None:
                break
            game.player.age += 1
            caravans.advance_caravans(game, engine.maps)
        else:
            pytest.fail(f"Real cargo did not return: {f['last_result']}; {f['cross_trip']}")
    trip = receipts[0]
    assert trip['quantity'] == trip['remittance'] == 0
    assert trip['running_costs'] > wage
    assert f['dividends'] == 0 and f['cross_trip'] is None
    assert f['profit'] == profit + trip['revenue'] - trip['cost'] - trip['running_costs']
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


@pytest.mark.parametrize('invalid', [-1, True, 1.5])
def test_saved_cargo_running_costs_reject_invalid_values(economy, invalid):
    engine, game = economy
    game, key = travelling_fleet(engine, game)
    fleet(game, key)['cargo']['running_costs'] = invalid
    with pytest.raises(ValueError, match='经济存档'):
        GameState.from_dict(game.to_dict())


def test_fee_receipt_waits_for_actual_five_year_period_and_is_consumed_once(economy):
    engine, game = economy
    row = next(r for r in game.economy_v2['organizations'].values()
               if r['kind'] == 'sect' and settlement_interval(game, r) == 5)
    market = state.local_market(game)
    market_governance.assign(game, market, 'sect', row['identity'], 'audit-war')
    total = cash(game)
    transfer_value(game, 'background:human', 'operator:' + market['id'], 1000, 'test real fee receipt')
    game.player.age += 1
    organizations.advance_organizations(game, engine.maps)
    assert row['income'] == 0 and row.get('pending_income') == 250
    assert organizations.public_finance(game, 'sect', row['identity'])['annual_income'] is None
    snapshot = copy.deepcopy(game.to_dict())
    market_governance.settle_claim(game, market)
    assert game.to_dict() == snapshot
    game.player.age += 4
    with patch.object(organizations, 'produce', return_value=0), patch('cultivation_life.system.economy.estate_management.invest_surplus'), patch.object(depot, 'advance'):
        organizations.advance_organizations(game, engine.maps)
    assert row['settlement_years'] == 5 and row['income'] == 250
    assert row.get('pending_income', 0) == 0
    assert organizations.public_finance(game, 'sect', row['identity'])['annual_income'] == 50
    assert cash(game) == total
    snapshot = copy.deepcopy(game.to_dict())
    organizations.advance_organizations(game, engine.maps)
    assert game.to_dict() == snapshot
