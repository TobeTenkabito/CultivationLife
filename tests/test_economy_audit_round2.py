"""Economic authority, paid production, finite auctions and freight budgets."""
import copy
import math
import random
from unittest.mock import patch

import pytest

from test_economy_network import economy, act, cash
from test_economy_enterprises import buy, configure, estate_act
from test_economy_network_expansion import loaded_fleet
from cultivation_life.models import GameState
from cultivation_life.rules import add_item
from cultivation_life.system.faction_geography import faction_site
from cultivation_life.system.economy import caravans, cross_freight, organizations, fleet_network
from cultivation_life.system.economy.enterprise_acquisition import price
from cultivation_life.system.economy.enterprise_rules import recipes
from cultivation_life.system.economy.enterprise_state import owner_allowed
from cultivation_life.system.economy.enterprise_view import public_estates
from cultivation_life.system.economy.enterprise_operations import advance_estates
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.local_market import quote
from cultivation_life.system.economy.state import commodity_catalog, ensure_regional_market


def held(player, item):
    return sum(i.quantity for i in player.inventory if i.id == item)


def advanced_estate(engine, game):
    game.player.realm_index = 4
    game, key = buy(engine, game, 'forge')
    catalog = commodity_catalog('human')
    recipe = next(k for k, r in recipes('human', catalog).items()
                  if r['kind'] == 'forge' and catalog[r['output']]['tier'] == 5)
    game = configure(engine, game, key, recipe=recipe)
    game = estate_act(engine, game, key, 'fund', amount=1000000)
    return game, key, recipe


def test_reacquisition_adopts_current_qualification_and_requires_new_purchase_permission(economy):
    engine, game = economy
    game, key, old_recipe = advanced_estate(engine, game)
    game = estate_act(engine, game, key, 'release',
                      cost=price(game, engine.maps, game.economy_v2['estates'][key]) // 2)
    game.player.realm_index = 2
    game, key = buy(engine, game, 'forge')
    row = game.economy_v2['estates'][key]
    catalog = commodity_catalog('human')
    assert catalog[recipes('human', catalog)[row['recipe']]['output']]['tier'] <= 3
    assert not row['auto_buy'] and not row['auto_sell']
    assert row['recipe'] != old_recipe and not row['job'] and not row['stock']
    assert GameState.from_dict(game.to_dict())


@pytest.mark.parametrize('handover', [False, True])
def test_retained_high_recipe_cannot_start_after_qualification_changes(economy, handover):
    engine, game = economy
    game, key, _ = advanced_estate(engine, game)
    game.player.realm_index = 2
    if handover:
        game.player.faction_id = 'tianjian'
        game.sects['tianjian'].founded_by_player = True
        transfer_value(game, 'background:human', 'organization:sect:tianjian', 100000, 'test original deed buyer')
        game = estate_act(engine, game, key, 'transfer', owner_kind='sect',
                          cost=price(game, engine.maps, game.economy_v2['estates'][key]) // 2)
    engine.store.save(game)
    game = engine._load(game.id)  # Complete normal state preparation before rejection.
    saved = engine.store._path(game.id).read_bytes()
    total = cash(game)
    with pytest.raises(ValueError, match='资质'):
        engine.fleet_action(game.id, dict(action='estate_start', estate_id=key,
                                        revision=game.economy_v2['estates'][key]['revision']))
    assert engine.store._path(game.id).read_bytes() == saved
    assert cash(engine._load(game.id)) == total
    row = game.economy_v2['estates'][key]
    row['enabled'] = True
    game.player.age += 1
    advance_estates(game, engine.maps)
    assert row['job'] is None and row['produced'] == 0


def test_already_paid_high_batch_finishes_after_lower_qualification(economy):
    engine, game = economy
    game, key, _ = advanced_estate(engine, game)
    game = estate_act(engine, game, key, 'start')
    row = game.economy_v2['estates'][key]
    job = copy.deepcopy(row['job'])
    game.player.realm_index = 2
    game.player.age = job['finish']
    advance_estates(game, engine.maps)
    assert row['stock'][job['item']] == job['quantity'] and row['job'] is None


def sect_estate(engine, game):
    entity = game.sects['tianjian']
    entity.founded_by_player = True
    game.player.faction_id = entity.id
    game.player.location_id = faction_site(entity)['id']
    transfer_value(game, 'background:human', 'organization:sect:' + entity.id, 100000, 'test original treasury')
    ensure_regional_market(game, engine.maps, 'human', game.player.location_id)
    offer = next(o for o in public_estates(game, engine.maps)['offers'] if o['kind'] == 'farm')
    game = act(engine, game, 'estate_buy', owner_kind='sect', kind='farm', cost=offer['cost'])
    key = f'human:{game.player.location_id}:farm'
    market = game.economy_v2['markets']['human:' + game.player.location_id]
    bill = quote(market['commodities']['dew_grass_seed'], 'buy', 3)
    game = estate_act(engine, game, key, 'purchase', item='dew_grass_seed', quantity=3,
                      total=bill['total'], market_revision=market['revision'])
    return game, key


@pytest.mark.parametrize('stale_founder', [False, True])
def test_old_controller_and_founder_cannot_operate_sect_estate_after_leaving(economy, stale_founder):
    engine, game = economy
    game, key = sect_estate(engine, game)
    engine.leave_faction(game.id)
    game = engine._load(game.id)
    game.sects['tianjian'].founded_by_player = stale_founder
    game.intrigue_state['factions']['sect:tianjian']['controller_id'] = 'player'
    engine.store.save(game)
    saved = engine.store._path(game.id).read_bytes()
    assert not owner_allowed(game, 'sect', 'tianjian', 'human')
    assert not public_estates(game, engine.maps)['owned']
    for action, options in [('withdraw', dict(item='dew_grass_seed', quantity=3)),
                            ('configure', dict(recipe='farm', enabled=True, auto_buy=True, auto_sell=True)),
                            ('entrust', dict(enabled=True))]:
        with pytest.raises(ValueError, match='权限'):
            estate_act(engine, game, key, action, **options)
        assert engine.store._path(game.id).read_bytes() == saved
    from cultivation_life.system.economy.economy_trust import prepare
    game.settings['economy_trust'] = True
    assert not prepare(game, game.economy_v2['estates'][key])
    assert 'trust_config' not in game.economy_v2['estates'][key]


def test_frozen_controller_cannot_spend_after_losing_control_while_still_a_member(economy):
    engine, game = economy
    game, key = sect_estate(engine, game)
    game.sects['tianjian'].founded_by_player = False
    game.intrigue_state['factions']['sect:tianjian']['controller_id'] = 'player'
    engine.store.save(game)
    game = engine._load(game.id)
    assert game.player.faction_id == 'tianjian' and game.player.realm_index == 2
    assert any(n.alive and n.realm_index > 2 for n in game.sects['tianjian'].npcs)
    assert not owner_allowed(game, 'sect', 'tianjian', 'human')
    frozen = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='权限'):
        engine.fleet_action(game.id, dict(action='estate_entrust', estate_id=key,
                                         revision=game.economy_v2['estates'][key]['revision'], enabled=True))
    assert engine.store._path(game.id).read_bytes() == frozen


def open_auction(engine, game, rank=None):
    rng = random.Random(3)
    engine._schedule_auction(game, rng)
    while rank is not None and rank not in game.auction_state['rank_band']:
        engine._schedule_auction(game, rng)
    game.player.location_id = game.auction_state['location_id']
    engine._open_auction(game, random.Random(1001))
    engine.store.save(game)
    return game


def consign(engine, game, item=None):
    # Respect the scheduled fair's real rank band; settlement is independent of tier.
    if item is None:
        item = f"econ_human_{max(game.auction_state['rank_band'])}_artifact_attack"
    add_item(game.player, item)
    engine.store.save(game)
    engine.consign_auction_item(game.id, item, engine._catalog_price('item', item) * 5)
    return engine._load(game.id)


def finish_rounds(engine, game):
    for _ in range(int(engine._auction_rules()['auction_rounds'])):
        engine.advance_auction_round(game.id)
    return engine._load(game.id)


@pytest.mark.parametrize('budget', ['zero', 'net_only', 'short_fee', 'full'])
def test_auction_requires_full_bid_cash_and_returns_unsold_item_once(economy, budget):
    engine, game = economy
    game = consign(engine, open_auction(engine, game))
    lot = next(r for r in game.auction_state['lots'] if r.get('seller') == 'player')
    gross = lot['current_bid']
    net = math.floor(gross * (1 - engine._auction_rules()['commission_rate']))
    funds = {'zero': 0, 'net_only': net, 'short_fee': gross - 1, 'full': gross}[budget]
    transfer_value(game, 'background:human', 'player', balance(game, 'background:human') - funds, 'test finite buyer budget')
    engine.store.save(game)
    stones, item_count, total = balance(game, 'player'), held(game.player, lot['content_id']), cash(game)
    game = finish_rounds(engine, game)
    actual = next(r for r in game.auction_state['lots'] if r['id'] == lot['id'])
    assert game.auction_state['status'] == 'black_market' and game.auction_state['economy_settled']
    if budget == 'full':
        assert balance(game, 'player') == stones + net
        assert held(game.player, lot['content_id']) == item_count
        assert not actual.get('unsold') and actual['seller_net'] == net
    else:
        assert actual['unsold'] and actual['seller_net'] == 0
        assert held(game.player, lot['content_id']) == item_count + 1
        assert balance(game, 'player') == stones
    assert cash(game) == total
    snapshot = copy.deepcopy(game.to_dict())
    engine._finish_auction(game, random.Random(5))
    assert game.to_dict() == snapshot
    engine._cancel_auction_for_world_change(game)
    assert held(game.player, lot['content_id']) == item_count + (budget != 'full')
    assert GameState.from_dict(game.to_dict())


def test_underfunded_auction_does_not_block_real_time_action(economy):
    engine, game = economy
    game = consign(engine, open_auction(engine, game))
    transfer_value(game, 'background:human', 'player', balance(game, 'background:human') - 1, 'test exhausted buyer')
    engine.store.save(game)
    age = game.player.age
    engine.advance(game.id, 'rest', 1)
    game = engine._load(game.id)
    assert game.player.age == age + 1
    assert game.auction_state['status'] == 'black_market'
    lot = next(r for r in game.auction_state['lots'] if r.get('seller') == 'player')
    assert lot['unsold'] and held(game.player, lot['content_id']) == 1


def test_underfunded_crafted_consignment_returns_the_original_instance(economy):
    engine, game = economy
    from test_crafting_system import CraftingSystemTests
    helper = CraftingSystemTests()
    helper.engine, helper.game_id = engine, game.id
    instances = helper._give_human_recipe()
    engine.forge_crafted_artifact(game.id, helper._payload(instances))
    game = engine._load(game.id)
    game.pending_event = None
    original = copy.deepcopy(game.player.crafted_artifacts[0])
    game = open_auction(engine, game, rank=original['scaling_realm_index'])
    engine.crafted_artifact_action(game.id, original['id'], 'consign', original['anchor_value'] * 5)
    game = engine._load(game.id)
    assert not game.player.crafted_artifacts
    transfer_value(game, 'background:human', 'player', balance(game, 'background:human'), 'test exhausted artifact buyer')
    engine.store.save(game)
    total = cash(game)
    game = finish_rounds(engine, game)
    assert game.player.crafted_artifacts == [original]
    item = next(i for i in game.player.inventory if i.crafted_artifact_id == original['id'])
    assert item.quantity == 1 and item.description == original['description']
    assert cash(game) == total and GameState.from_dict(game.to_dict())
    engine._cancel_auction_for_world_change(game)
    assert game.player.crafted_artifacts == [original]


def test_multiple_consignments_share_one_finite_buyer_budget(economy):
    engine, game = economy
    game = open_auction(engine, game)
    for _ in range(2):
        game = consign(engine, game)
    lots = [r for r in game.auction_state['lots'] if r.get('seller') == 'player']
    funds = lots[0]['current_bid']
    transfer_value(game, 'background:human', 'player', balance(game, 'background:human') - funds, 'test one funded buyer')
    engine.store.save(game)
    total, coins = cash(game), balance(game, 'player')
    game = finish_rounds(engine, game)
    settled = [r for r in game.auction_state['lots'] if r.get('seller') == 'player']
    assert sum(bool(r.get('unsold')) for r in settled) == 1
    assert balance(game, 'player') - coins == settled[0]['seller_net']
    assert held(game.player, lots[0]['content_id']) == 1 and cash(game) == total


def cheap_freight(engine, game):
    from cultivation_life.system.economy.freight_trade import market
    fleet = loaded_fleet(engine, game)
    home = fleet_network.alliance_at(game, 'spirit', 'xuanji')
    branch = fleet_network.alliance_at(game, 'true_demon', 'xuanji')
    source = market(game, engine.maps, 'spirit', home['hq'])
    target = market(game, engine.maps, 'true_demon', branch['hq'])
    for product in source['commodities'].values():
        product['stock'] = 0
    source['commodities']['dew_grass_seed']['stock'] = 1000
    target['commodities']['dew_grass_seed']['stock'] = 0
    return fleet, source, target


def test_cross_auto_selection_rejects_margin_below_known_voyage_wages(economy):
    engine, game = economy
    fleet, _, _ = cheap_freight(engine, game)
    before = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError, match='盈利运输'):
        cross_freight.dispatch(game, engine.maps, fleet, 'true_demon')
    assert game.to_dict() == before
    fleet['guard_power'] = 0  # A cheaper actual crew may choose the same financed cargo.
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon')
    assert fleet['cross_trip']['quantity'] == 24


def test_cross_multileg_forecast_includes_every_actual_passage(economy):
    engine, game = economy
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.system.economy.freight_trade import market
    world = next(w for w in game.merchant_state['worlds'] if w not in {'spirit', 'true_demon'}
                 and WORLD_SYSTEMS['world_profiles'][w]['tier'] == 2)
    branch = next(a for a in game.merchant_state['worlds'][world] if not a['cross_world'])
    branch.update(network_id='xuanji', cross_world=True, home_world='spirit')
    branch['leader']['realm_index'] = int(WORLD_SYSTEMS['world_profiles'][world]['npc_realm_cap']) - 1
    for w in ['spirit', 'true_demon', world]:
        fleet_network.alliance_at(game, w, 'xuanji')['linked_worlds'] = ['spirit', 'true_demon', world]
    fleet_network.routes(game)[fleet_network.route_key('xuanji', 'spirit', world)] = dict(
        alliance_id='xuanji', home='spirit', branch=world, open=True, built=True,
        maintenance=0, paid=0, shortfall=0, last_year=game.player.age)
    fleet = loaded_fleet(engine, game, 'true_demon')
    source = market(game, engine.maps, 'true_demon', fleet['location'])
    target = market(game, engine.maps, world, branch['hq'])
    for product in source['commodities'].values():
        product['stock'] = 0
    source['commodities']['dew_grass_seed']['stock'] = 1000
    target['commodities']['dew_grass_seed']['stock'] = 0
    fleet['guard_power'] = 400
    cost = quote(source['commodities']['dew_grass_seed'], 'buy', 24)['total']
    tariff = max(10, math.ceil(cost * .15))
    margin = quote(target['commodities']['dew_grass_seed'], 'sell', 24)['total'] - cost - tariff * 2
    assert 20 * 6 < margin < 20 * 12  # One leg's forecast would incorrectly accept.
    snapshot = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError, match='盈利运输'):
        cross_freight.dispatch(game, engine.maps, fleet, world)
    assert game.to_dict() == snapshot
    cross_freight.dispatch(game, engine.maps, fleet, world,
        order=dict(item='dew_grass_seed', quantity=24, buy_limit=10**12, sell_limit=0))
    assert fleet['cross_trip']['path'] == ['true_demon', 'spirit', world]


def test_automatic_return_rejects_cargo_that_cannot_cover_return_wages(economy):
    engine, game = economy
    fleet, source, target = cheap_freight(engine, game)
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon', remittance_percent=0,
        order=dict(item='dew_grass_seed', quantity=24, buy_limit=10**12, sell_limit=0))
    for product in target['commodities'].values():
        product['stock'] = 0
    target['commodities']['dew_grass_seed']['stock'] = 1000
    source['commodities']['dew_grass_seed']['stock'] = 0
    total = cash(game)
    purchases = sum(r['reason'] == '跨界商队采购实货' for r in game.economy_v2['ledger'])
    game.player.age = fleet['cross_trip']['arrival']
    with patch.object(cross_freight, '_risk'):
        cross_freight.advance_freight(game, engine.maps, fleet, {})
    trip = fleet['cross_trip']
    assert trip['phase'] == 'return' and trip['quantity'] == 0 and trip['tariff'] == 0
    assert sum(r['reason'] == '跨界商队采购实货' for r in game.economy_v2['ledger']) == purchases
    assert cash(game) == total and GameState.from_dict(game.to_dict())


@pytest.mark.parametrize('manual', [False, True])
def test_cross_purchase_retains_wage_cash_before_departure(economy, manual):
    engine, game = economy
    fleet, source, _ = cheap_freight(engine, game)
    bill = quote(source['commodities']['dew_grass_seed'], 'buy', 24)
    tariff = max(10, math.ceil(bill['total'] * .15))
    account = 'caravan:' + fleet['id']
    transfer_value(game, account, 'background:spirit', balance(game, account) - bill['total'] - tariff * 2, 'test fare only')
    order = dict(item='dew_grass_seed', quantity=24, buy_limit=10**12, sell_limit=0) if manual else None
    snapshot = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError, match='盈利运输'):
        cross_freight.dispatch(game, engine.maps, fleet, 'true_demon', order=order)
    assert game.to_dict() == snapshot


def test_annual_member_procurement_books_real_turnover_without_extra_income(economy):
    engine, game = economy
    from cultivation_life.system.economy.organization_production import workforce
    entity = game.sects['tianjian']
    finance = organizations.register(game, 'sect', entity.id, 'human')
    transfer_value(game, 'background:human', 'organization:sect:' + entity.id, 10000000, 'test original treasury')
    ensure_regional_market(game, engine.maps, 'human', entity.location_id)
    market = game.economy_v2['markets']['human:' + entity.location_id]
    finance['workforce'] = {str(k): v for k, v in workforce(entity).items()}
    finance['expected_upkeep'] = 10000
    before = market['turnover']
    with patch.object(organizations, 'produce', return_value=0), \
         patch('cultivation_life.system.economy.industry.settle_industry'), \
         patch('cultivation_life.system.economy.depot.advance'), \
         patch('cultivation_life.system.economy.estate_management.invest_surplus'):
        organizations.settle_faction(game, engine.maps, finance, 20)
    traded = market['turnover'] - before
    assert traded > 0 and finance['turnover'] == traded
    assert finance['supply_expense'] == traded and finance['income'] == 0
    assert not finance.get('pending_turnover')
    assert GameState.from_dict(game.to_dict())


@pytest.mark.parametrize('elapsed', [1, 100])
def test_new_fleet_starts_billing_after_establishment_not_before(economy, elapsed):
    engine, game = economy
    region = game.economy_v2['transport']['worlds']['human']
    old = set(region['fleets'])
    transfer_value(game, 'background:human', 'organization:sect:tianjian', 100000, 'test original treasury')
    game.player.age += elapsed
    with patch.object(caravans, '_dispatch'):
        caravans.advance_caravans(game, engine.maps)
    created = [f for key, f in region['fleets'].items() if key not in old
               and f['owner_kind'] == 'sect' and f['owner_id'] == 'tianjian']
    assert len(created) == 2
    for fleet in created:
        assert fleet['operating_costs'] == 0 and fleet['profit'] == 0
        assert balance(game, 'caravan:' + fleet['id']) == fleet['investment']
        fleet['trade_order'] = dict(mode='hold')
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    for fleet in created:
        assert fleet['operating_costs'] == 2 and fleet['profit'] == -2
    snapshot = copy.deepcopy(game.to_dict())
    caravans.advance_caravans(game, engine.maps)
    assert game.to_dict() == snapshot and GameState.from_dict(game.to_dict())
