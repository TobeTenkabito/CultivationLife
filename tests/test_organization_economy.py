"""Economic boundaries: finite counterparties, one treasury and one year clock."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system.economy import organizations as finance
from cultivation_life.system.economy.ledger import balance, transfer_value, account
from cultivation_life.system.economy.state import advance_economy, ensure_regional_market
from cultivation_life.system.faction_geography import faction_site
from cultivation_life.system.institution_state import fresh
from cultivation_life.system.upper_institutions import advance_time

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def economy(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game = engine._load(engine.create_game('组织财政', 'supreme_metal', 'dao', 315, preset_id='core')['id'])
    game.pending_event = None
    return engine, game


def total_cash(game):
    return (balance(game, 'player') + sum(a['balance'] for a in game.economy_v2['accounts'].values())
        + sum(a['reserves'] for rows in game.merchant_state['worlds'].values() for a in rows)
        + sum(r.get('resources', 0) for r in game.intrigue_state.get('factions', {}).values())
        + game.heavenly_court.get('treasury', 0)
        + sum(r['treasury'] for r in game.upper_institutions.values()))


def sect(game):
    return next(s for s in game.sects.values() if s.world == 'human' and s.kind == 'sect' and not s.extinct)


def test_adoption_preserves_old_treasury_rng_and_has_no_retroactive_income(economy):
    engine, game = economy
    entity = sect(game)
    finance.faction_record(game, 'sect', entity.id)['resources'] = 12345
    game.economy_v2.pop('organizations', None)
    game.player.age += 800
    before, rng = total_cash(game), game.rng_state
    finance.ensure_organizations(game)
    finance.advance_organizations(game, engine.maps)
    assert total_cash(game) == before and game.rng_state == rng
    assert balance(game, finance.key('sect', entity.id)) == 12345
    assert GameState.from_dict(game.to_dict()).economy_v2 == game.economy_v2


def test_real_production_goods_fees_and_finite_market_money(economy):
    engine, game = economy
    entity = sect(game)
    row = finance.register(game, 'sect', entity.id, entity.world)
    location = faction_site(entity)['id']
    ensure_regional_market(game, engine.maps, entity.world, location)
    market = game.economy_v2['markets'][f'human:{location}']
    before, goods, rng = total_cash(game), copy.deepcopy(market['commodities']), game.rng_state
    revenue = finance.produce(game, engine.maps, entity, row)
    assert revenue > 0 and row['produced'] > 0
    product = row['commodity']
    assert sum(round(p['stock']-goods[k]['stock'], 6) for k,p in market['commodities'].items()) + market.get('input_consumed', 0) == row['produced']
    assert total_cash(game) == before and game.rng_state == rng
    assert balance(game, finance.key('sect', entity.id)) == revenue
    dealer = f'market:{market["id"]}'
    transfer_value(game, dealer, 'background:human', balance(game, dealer), '测试清空经销商现金')
    before = copy.deepcopy(market)
    assert finance.produce(game, engine.maps, entity, row) == 0
    assert market == before


def test_zero_funds_cannot_grant_permanent_welfare_and_partial_payment_is_exact(economy):
    _, game = economy
    entity = sect(game)
    source = finance.key('sect', entity.id)
    assert balance(game, source) == 0
    assert finance.welfare(game, entity) == 0
    game.player.age += 1
    transfer_value(game, 'background:human', source, 25, '测试预算')
    before = total_cash(game)
    assert finance.welfare(game, entity) == .25
    assert balance(game, source) == 0 and total_cash(game) == before
    assert finance.welfare(game, entity) == 0


def test_upper_world_production_accumulates_work_without_moving_player(economy):
    engine, game = economy
    entity = next(s for s in game.sects.values() if s.world == 'celestial' and s.kind == 'sect' and not s.extinct)
    row = finance.register(game, 'sect', entity.id, entity.world)
    address, rng = (game.player.world, game.player.location_id), game.rng_state
    finance.produce(game, engine.maps, entity, row, years=100)
    assert row['commodity'] is not None and row['produced'] > 0
    assert (game.player.world, game.player.location_id) == address and game.rng_state == rng
    assert row['production_credit'] >= 0


def test_freight_reaches_actual_owner_once(economy):
    engine, game = economy
    entity = sect(game)
    receiver = f'transport:human:{entity.id}'
    account(game, receiver)
    transfer_value(game, 'background:human', receiver, 4321, '测试货运收入')
    game.player.age += 1
    before = total_cash(game)
    row = game.economy_v2['organizations'][finance.key('sect', entity.id)]
    finance.settle_faction(game, engine.maps, row, 1)
    row['last_year'] = game.player.age
    assert balance(game, receiver) == 0 and total_cash(game) == before
    rows = [r for r in game.economy_v2['ledger'] if r['source'] == receiver]
    assert len(rows) == 1 and rows[0]['destination'] == finance.key('sect', entity.id)
    finance.advance_organizations(game, engine.maps)
    snapshot = copy.deepcopy(game.to_dict())
    finance.advance_organizations(game, engine.maps)
    assert game.to_dict() == snapshot


@pytest.mark.parametrize('world', ['asura', 'nether', 'reincarnation'])
def test_yearly_pay_ignores_action_unit_size_and_stops_when_background_and_treasury_empty(economy, world):
    _, game = economy
    game.player.world, game.player.realm_index = world, 9
    state = game.upper_institutions.setdefault(world, fresh())
    state['joined'] = True
    row = finance.register(game, 'upper', world, world)
    other = copy.deepcopy(game)
    before = total_cash(game)
    finance.settle_institution(game, row, 100)
    finance.settle_institution(other, other.economy_v2['organizations'][finance.key('upper', world)], 40)
    finance.settle_institution(other, other.economy_v2['organizations'][finance.key('upper', world)], 60)
    assert state['treasury'] == other.upper_institutions[world]['treasury']
    assert balance(game, 'player') == balance(other, 'player') and total_cash(game) == before
    amount = balance(game, 'player')
    # Political clocks cannot mint or pay even a complete 500-year action unit.
    advance_time(game, 500, 500)
    assert balance(game, 'player') == amount
    transfer_value(game, finance.key('upper', world), f'background:{world}', balance(game, finance.key('upper', world)), '测试清空府库')
    pool = game.economy_v2['accounts'][f'background:{world}']
    pool['balance'] = 0
    finance.settle_institution(game, row, 100)
    assert balance(game, 'player') == amount and row['benefit_paid'] == 0


def test_remote_finance_is_hidden_and_no_player_stipend(economy):
    _, game = economy
    game.upper_institutions['asura'] = fresh() | {'joined': True}
    row = finance.register(game, 'upper', 'asura', 'asura')
    before = balance(game, 'player')
    finance.settle_institution(game, row, 100)
    assert game.upper_institutions['asura']['treasury'] > 2000000
    assert balance(game, 'player') == before
    snapshot = copy.deepcopy(game.to_dict())
    assert finance.public_finance(game, 'upper', 'asura') is None
    assert game.to_dict() == snapshot


@pytest.mark.parametrize('corruption', ['duplicate', 'negative', 'identity', 'world', 'timestamp'])
def test_invalid_org_save_rejected_without_repair(economy, corruption):
    _, game = economy
    entity = sect(game)
    raw = game.to_dict()
    address = finance.key('sect', entity.id)
    if corruption == 'duplicate':
        raw['economy_v2']['accounts'][address] = dict(balance=1, income=0, expense=0)
    elif corruption == 'negative':
        raw['intrigue_state']['factions'][f'sect:{entity.id}']['resources'] = -1
    else:
        raw['economy_v2']['organizations'][address][{'identity': 'identity', 'world': 'world', 'timestamp': 'last_year'}[corruption]] = {'identity': 'wrong', 'world': 'unknown', 'timestamp': -1}[corruption]
    before = copy.deepcopy(raw)
    with pytest.raises(ValueError, match='经济存档'):
        GameState.from_dict(raw)
    assert raw == before


def test_nodlc_family_funding_and_gathering_are_real(economy, monkeypatch):
    engine, game = economy
    from test_family_expansion import family_game
    game = family_game(engine)
    game.family.npcs[0].realm_index = 4
    monkeypatch.setattr(engine, '_intrigue_enabled', lambda: False)
    finance.ensure_organizations(game)
    engine.store.save(game)
    source = finance.key('family', game.family.id)
    before = balance(game, 'player')
    engine.family_action(game.id, 'fund', {'amount': 1000})
    saved = engine._load(game.id)
    assert balance(saved, source) == 1000 and balance(saved, 'player') == before - 1000
    engine.family_action(game.id, 'gather', {})
    saved = engine._load(game.id)
    assert balance(saved, source) > 1000
    assert engine._public_family(saved)['ledger'] is not None
    with pytest.raises(ValueError, match='本年'):
        engine.family_action(game.id, 'gather', {})


def test_unfunded_yaochi_purchase_keeps_merit_inventory_and_rng(economy):
    engine, game = economy
    game.player.world, game.player.realm_index = 'celestial', 9
    from cultivation_life.system.yaochi_rules import config, offers
    game.player.location_id = config()['location_id']
    game.yaochi_state['merit'] = 1000000
    finance.register(game, 'yaochi', 'yaochi', 'celestial')
    source = finance.key('yaochi', 'yaochi')
    transfer_value(game, source, 'background:celestial', balance(game, source), '测试清空采购资金')
    engine.store.save(game)
    offer = next(o for o in offers(game) if o['kind'] == 'item')
    engine.get_game(game.id)  # Complete ordinary world-entry initialization first.
    before = engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError, match='府库不足'):
        engine.yaochi_action(game.id, 'buy', offer['id'], 1)
    after = engine.store.load(game.id).to_dict()
    assert after == before
