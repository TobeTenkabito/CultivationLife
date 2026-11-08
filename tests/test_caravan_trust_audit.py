"""Managed fleets retain real cash; available cargo must justify hiring."""
import copy
import pytest

from cultivation_life.system.economy import caravans, state
from cultivation_life.system.economy.fleet_network import guard_required, guard_cost, guard_wages, owner_sites
from cultivation_life.system.economy.ledger import balance
from test_economy_network import economy, cash, act
from test_economy_enterprises import own_fleet, fleet


def test_empty_and_fractional_stock_cannot_hide_available_goods():
    source = {'commodities': {f'empty-{i}': dict(price=1, stock=.9, target=10) for i in range(20)}}
    target = {'commodities': {k: dict(price=100) for k in source['commodities']}}
    source['commodities']['real'] = dict(price=10, stock=24, target=10)
    target['commodities']['real'] = dict(price=20)
    assert caravans._candidate_items(source, target) == ['real']


def test_no_business_does_not_hire_or_dissolve_managed_fleet(economy):
    engine, game = economy
    game, key = own_fleet(engine, game)
    game.settings['economy_trust'] = True
    f = fleet(game, key)
    owner_cash, total = balance(game, 'player'), cash(game)
    initial = balance(game, caravans._cash(f))
    for _ in range(180):
        game.player.age += 1
        state.advance_economy(game)
        caravans.advance_caravans(game, engine.maps)
    assert f['status'] == 'waiting' and f['voyages'] == 0 and f['guard_power'] == 0
    assert balance(game, caravans._cash(f)) == initial - 360
    assert balance(game, 'player') == owner_cash and cash(game) == total
    visible = caravans.public_caravans(game, engine.maps, local=True)
    assert any(row['id'] == key and row['status'] == 'waiting' for row in visible)
    before = copy.deepcopy(game.to_dict())
    caravans.advance_caravans(game, engine.maps)
    assert game.to_dict() == before
    engine.store.save(game)
    assert fleet(engine.store.load(game.id), key) == f


@pytest.mark.parametrize('reference', [100, 1])
def test_hiring_requires_funded_profitable_real_cargo(economy, reference):
    engine, game = economy
    game, key = own_fleet(engine, game)
    game.settings['economy_trust'] = True
    f = fleet(game, key)
    alliance = owner_sites(game, engine.maps, f)
    sites = {f['location'], *(row['location_id'] for row in alliance['offices'])}
    item = 'dew_grass_seed'
    for place in sites:
        state.ensure_regional_market(game, engine.maps, 'human', place)
        market = game.economy_v2['markets'][f'human:{place}']
        for row in market['commodities'].values():
            row['stock'] = 0
            state.reprice(game, market, row)
        row = market['commodities'][item]
        row['reference'] = reference
        row['stock'] = row['target'] * 3 if place == f['location'] else 0
        state.reprice(game, market, row)
    source = game.economy_v2['markets'][f'human:{f["location"]}']['commodities'][item]
    stock, total, owner_cash = source['stock'], cash(game), balance(game, 'player')
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    if reference == 1:
        assert f['guard_power'] == 0 and f['cargo'] is None and f['status'] == 'waiting'
        assert balance(game, caravans._cash(f)) == 4998
        assert balance(game, 'player') == owner_cash and cash(game) == total
        return
    assert f['guard_power'] == guard_required('human') and f['status'] == 'travelling'
    assert f['cargo']['expected_profit'] > guard_cost('human')
    bought = sum(row['cargo']['quantity'] for row in game.economy_v2['transport']['worlds']['human']['fleets'].values()
                 if row.get('cargo') and row['cargo']['item'] == item
                 and row['cargo']['origin'] == game.player.location_id and row['cargo']['departure'] == game.player.age)
    assert source['stock'] == stock - bought
    assert balance(game, caravans._cash(f)) >= guard_wages(f, f['cargo']['years'] + 3) + 6
    assert balance(game, 'player') == owner_cash and cash(game) == total


def test_idle_guards_are_released_without_refund_but_hold_is_preserved(economy):
    engine, game = economy
    game, key = own_fleet(engine, game)
    game = act(engine, game, 'guard', fleet_id=key)
    game.settings['economy_trust'] = True
    f = fleet(game, key)
    f['trade_order'] = {'mode': 'hold'}
    initial, total = balance(game, caravans._cash(f)), cash(game)
    wages = guard_wages(f, 1)
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    assert f['guard_power'] == guard_required('human') and f['trade_order'] == {'mode': 'hold'}
    f['trade_order'] = {'mode': 'auto'}
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    assert f['guard_power'] == 0 and f['status'] == 'waiting'
    assert balance(game, caravans._cash(f)) == initial - 2 * (wages + 2)
    assert cash(game) == total
