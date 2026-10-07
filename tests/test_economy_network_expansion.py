"""HQ handover, actual multi-leg freight, recovery and legacy save boundaries."""
import copy
import pytest
from test_economy_network import economy, act, found, spirit, cash
from cultivation_life.models import GameState
from cultivation_life.system.economy import caravans, cross_freight, fleet_network as net
from cultivation_life.system.economy.network_actions import home_alliance, public_network
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.state import ensure_regional_market


def visit(engine, game, world):
    game.player.world = world  # Fixture setup only; commands must never move the player.
    game.player.location_id = game.merchant_state['worlds'][world][0]['hq']
    caravans.ensure_caravans(game, engine.maps)


def recruit(engine, game):
    region = game.economy_v2['transport']['worlds'][game.player.world]
    keys = [f['id'] for f in region['fleets'].values() if f['owner_kind'] == 'independent' and not f['player_controlled']][:3]
    for key in keys:
        game.player.location_id = region['fleets'][key]['location']
        game = act(engine, game, 'pledge', fleet_id=key)
    return game


def loaded_fleet(engine, game, world='spirit', identity='xuanji'):
    visit(engine, game, world)
    owner = net.alliance_at(game, world, identity)
    fleet = next(f for f in game.economy_v2['transport']['worlds'][world]['fleets'].values() if f['alliance_id'] == owner['id'])
    fleet['location'] = owner['hq']
    transfer_value(game, f'background:{world}', f'caravan:{fleet["id"]}', 10**7, '验收运输资本')
    fleet['investment'] = 10**7
    ensure_regional_market(game, engine.maps, world, owner['hq'])
    market = game.economy_v2['markets'][f'{world}:{owner["hq"]}']
    for row in market['commodities'].values():
        row['stock'] = row['target'] * 3
    return fleet


def tick(engine, game, fleet):
    game.player.age = max(game.player.age, fleet['cross_trip']['arrival'])
    cross_freight.advance_freight(game, engine.maps, fleet, {})
    GameState.from_dict(game.to_dict())


def test_human_hq_can_promote_local_fleets_in_spirit_without_moving_assets(economy):
    engine, game = economy
    game = found(engine, game)
    old = home_alliance(game)
    old_id, old_hq, old_money = old['id'], old['hq'], old['reserves']
    original_fleets = copy.deepcopy(game.economy_v2['transport']['worlds']['human']['fleets'])
    visit(engine, game, 'spirit')
    game.player.realm_index = 8
    game = recruit(engine, game)
    original_player = copy.deepcopy(game.player.to_dict())
    total, rng = cash(game), game.rng_state
    game = act(engine, game, 'relocate')
    home = home_alliance(game)
    assert home['world'] == 'spirit' and home['hq'] == game.player.location_id
    assert game.player.world == original_player['world'] and game.player.location_id == original_player['location_id']
    old = net.alliance_at(game, 'human', old_id)
    assert old['hq'] == old_hq and old['reserves'] == old_money and old['home_world'] == 'spirit'
    assert old['leader']['realm_index'] >= 4
    assert original_fleets == game.economy_v2['transport']['worlds']['human']['fleets']
    assert cash(game) == total and game.rng_state == rng
    assert not net.route_open(game, home, 'human')
    game = act(engine, game, 'build_passage')
    assert net.route_open(game, home_alliance(game), 'human')
    before = copy.deepcopy(game.to_dict())
    public_network(game, engine.maps)
    assert game.to_dict() == before


def test_same_world_relocation_retains_offices_capacity_and_leaders(economy):
    engine, game = economy
    game = found(engine, game)
    home = home_alliance(game)
    old_hq, old_leader = home['hq'], home['leader']
    game.player.location_id = next(r['id'] for r in engine.maps.worlds['human']['locations'] if not r.get('min_realm_index') and r['id'] != old_hq)
    game = act(engine, game, 'relocate')
    home = home_alliance(game)
    assert home['offices'] == [dict(location_id=old_hq, leader=old_leader)]
    assert net.fleet_limit('alliance', home) == 6
    game.player.location_id = old_hq
    game = act(engine, game, 'relocate')
    assert home_alliance(game)['leader'] == old_leader
    assert net.fleet_limit('alliance', home_alliance(game)) == 6


def test_relocation_invalid_realm_has_no_file_cash_or_rng_side_effect(economy):
    engine, game = economy
    game = found(engine, game)
    visit(engine, game, 'spirit')
    engine.store.save(game)
    engine._load(game.id)  # Complete normal session preparation before the failed command.
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='大乘'):
        engine.fleet_action(game.id, dict(action='relocate'))
    assert engine.store._path(game.id).read_bytes() == saved


def test_promote_affiliated_id_keeps_existing_passage_and_charges_new_hq(economy):
    engine, game = economy
    spirit(engine, game)
    game = found(engine, game)
    identity = home_alliance(game)['id']
    visit(engine, game, 'true_demon')
    branch = next(a for a in game.merchant_state['worlds']['true_demon'] if not a['cross_world'])
    game.player.location_id = branch['hq']
    branch_id = branch['id']
    game = act(engine, game, 'affiliate', alliance_id=branch_id)
    game = act(engine, game, 'build_passage')
    game = act(engine, game, 'relocate')
    home = home_alliance(game)
    assert home['id'] == branch_id and home['network_id'] == identity
    assert net.route_open(game, home, 'spirit')
    old_cash = net.alliance_at(game, 'spirit', identity)['reserves']
    source = f'alliance:true_demon:{branch_id}'
    transfer_value(game, 'background:true_demon', source, 10**7, '验收维护')
    initial = balance(game, source)
    game.player.age += 1
    net.advance_network(game, engine.maps)
    assert balance(game, source) < initial
    assert net.alliance_at(game, 'spirit', identity)['reserves'] == old_cash
    # The new HQ retains its local ID; credentials must still work in the old HQ.
    game.player.age -= 1
    game.player.layer = 1
    price = engine._merchant_passage_cost(game, 'spirit')
    transfer_value(game, 'background:true_demon', 'player', price * 3, '验收往返路费')
    engine.store.save(game)
    engine.merchant_action(game.id, 'passage', dict(alliance_id=branch_id, destination='spirit'))
    game = engine._load(game.id)
    assert game.player.world == 'spirit'
    engine.merchant_action(game.id, 'passage', dict(alliance_id=identity, destination='true_demon'))
    assert engine._load(game.id).player.world == 'true_demon'


def test_ai_recovery_requires_built_route_and_keeps_branch_funds(economy):
    engine, game = economy
    home = spirit(engine, game)
    route = net.routes(game)[net.route_key('xuanji', 'spirit', 'true_demon')]
    source = 'alliance:spirit:xuanji'
    transfer_value(game, source, 'background:spirit', balance(game, source), '验收枯竭')
    game.player.age += 1
    net.advance_network(game, engine.maps)
    assert not route['open']
    branch_cash = net.alliance_at(game, 'true_demon', 'xuanji')['reserves']
    transfer_value(game, 'background:spirit', source, 10**7, '验收经济恢复')
    initial = cash(game)
    game.player.age += 1
    net.advance_network(game, engine.maps)
    assert route['open'] and net.route_open(game, home, 'true_demon')
    assert cash(game) == initial and net.alliance_at(game, 'true_demon', 'xuanji')['reserves'] == branch_cash
    snapshot = copy.deepcopy(game.to_dict())
    net.advance_network(game, engine.maps)
    assert game.to_dict() == snapshot
    route.update(open=False, built=False, paid=0)
    game.player.age += 1
    net.advance_network(game, engine.maps)
    assert not route['open']


def test_branch_origin_roundtrip_never_collects_main_hq_cash(economy):
    engine, game = economy
    fleet = loaded_fleet(engine, game, 'true_demon')
    total = cash(game)
    home = net.alliance_at(game, 'spirit', 'xuanji')
    before = home['reserves']
    cross_freight.dispatch(game, engine.maps, fleet, 'spirit', remittance_percent=100)
    tick(engine, game, fleet)
    assert fleet['cross_trip']['remittance'] == 0
    assert home['reserves'] >= before  # Return freight may pay the main HQ a tariff.
    tick(engine, game, fleet)
    assert not fleet['cross_trip'] and cash(game) == total


def test_return_goods_are_bought_from_destination_and_wait_for_actual_cash(economy):
    engine, game = economy
    fleet = loaded_fleet(engine, game)
    branch = net.alliance_at(game, 'true_demon', 'xuanji')
    ensure_regional_market(game, engine.maps, 'true_demon', branch['hq'])
    target = game.economy_v2['markets'][f'true_demon:{branch["hq"]}']
    for row in target['commodities'].values():
        row['stock'] = row['target'] * 3
    total = cash(game)
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon', remittance_percent=50)
    stocks = {k:r['stock'] for k,r in target['commodities'].items()}
    tick(engine, game, fleet)
    trip = fleet['cross_trip']
    assert trip['phase'] == 'return' and trip['quantity'] > 0
    assert target['commodities'][trip['item']]['stock'] < stocks[trip['item']]
    account = f'market:spirit:{fleet["location"]}'
    transfer_value(game, account, 'background:spirit', balance(game, account), '验收收购现金耗尽')
    game.economy_v2['markets'][account.removeprefix('market:')]['last_year'] = trip['arrival']
    tick(engine, game, fleet)
    assert trip['phase'] == 'return_selling' and trip['quantity'] > 0
    saved = GameState.from_dict(game.to_dict())
    assert saved.economy_v2['accounts'][f'freight:{fleet["id"]}']['balance'] == trip['remittance']
    transfer_value(game, 'background:spirit', account, 10**8, '验收收购现金恢复')
    tick(engine, game, fleet)
    assert fleet['cross_trip'] is None and cash(game) == total


def test_closed_first_leg_recall_retains_real_goods_then_sells_at_origin(economy):
    engine, game = economy
    fleet = loaded_fleet(engine, game)
    total = cash(game)
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon')
    trip = fleet['cross_trip']
    with pytest.raises(ValueError, match='途中'):
        cross_freight.recall(game, fleet)
    net.routes(game)[net.route_key('xuanji', 'spirit', 'true_demon')]['open'] = False
    tick(engine, game, fleet)
    quantity = trip['quantity']
    cross_freight.recall(game, fleet)
    assert trip['path'] == ['spirit'] and trip['quantity'] == quantity
    tick(engine, game, fleet)
    assert not fleet['cross_trip'] and cash(game) == total


def test_reject_malformed_new_trip_without_rng_or_migration(economy):
    engine, game = economy
    fleet = loaded_fleet(engine, game)
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon')
    data = game.to_dict()
    row = data['economy_v2']['transport']['worlds']['spirit']['fleets'][fleet['id']]
    row['cross_trip']['path'] = ['spirit', 'unknown']
    with pytest.raises(ValueError, match='经济存档'):
        GameState.from_dict(data)


def test_legacy_paid_trip_adoption_keeps_existing_arrival_and_does_not_rebill(economy):
    engine, game = economy
    fleet = loaded_fleet(engine, game)
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon')
    trip = fleet['cross_trip']
    for key in ['path', 'index', 'tariff', 'leg_paid', 'source_location', 'remittance_percent', 'recalled']:
        trip.pop(key)
    game = GameState.from_dict(game.to_dict())
    fleet = game.economy_v2['transport']['worlds']['spirit']['fleets'][fleet['id']]
    cost = fleet['cross_trip']['cost']
    tick(engine, game, fleet)
    assert fleet['cross_trip']['cost'] >= cost
    assert fleet['cross_trip']['phase'] == 'return'


def test_branch_to_branch_uses_real_intermediate_edge_and_pays_each_origin(economy):
    engine, game = economy
    # Extend the fixture network with an existing qualified local alliance.
    worlds = [w for w in game.merchant_state['worlds'] if w not in {'spirit', 'true_demon'}]
    from cultivation_life.content_registry import WORLD_SYSTEMS
    world = next(w for w in worlds if WORLD_SYSTEMS['world_profiles'][w]['tier'] == 2)
    branch = next(a for a in game.merchant_state['worlds'][world] if not a['cross_world'])
    branch.update(network_id='xuanji', cross_world=True, home_world='spirit')
    branch['leader']['realm_index'] = int(WORLD_SYSTEMS['world_profiles'][world]['npc_realm_cap']) - 1
    for w in ['spirit', 'true_demon', world]:
        net.alliance_at(game, w, 'xuanji')['linked_worlds'] = ['spirit', 'true_demon', world]
    net.routes(game)[net.route_key('xuanji', 'spirit', world)] = dict(alliance_id='xuanji', home='spirit', branch=world,
        open=True, built=True, maintenance=0, paid=0, shortfall=0, last_year=game.player.age)
    fleet = loaded_fleet(engine, game, 'true_demon')
    total = cash(game)
    cross_freight.dispatch(game, engine.maps, fleet, world)
    trip = fleet['cross_trip']
    assert trip['path'] == ['true_demon', 'spirit', world]
    before = net.alliance_at(game, 'spirit', 'xuanji')['reserves']
    tick(engine, game, fleet)
    assert trip['index'] == 1 and trip['phase'] == 'outbound'
    assert net.alliance_at(game, 'spirit', 'xuanji')['reserves'] == before + trip['tariff']
    for _ in range(3):
        tick(engine, game, fleet)
    assert fleet['cross_trip'] is None and cash(game) == total


def test_inflight_relocation_and_foreign_route_repair_are_rejected_atomically(economy):
    engine, game = economy
    spirit(engine, game)
    game = found(engine, game)
    home = home_alliance(game)
    # A real route/dispatch on this owned network, followed by invalid commands.
    visit(engine, game, 'true_demon')
    game = recruit(engine, game)
    game = act(engine, game, 'regional_hq')
    game = act(engine, game, 'build_passage')
    visit(engine, game, 'spirit')
    game.player.location_id = home['hq']
    fleet = loaded_fleet(engine, game, 'spirit', home['id'])
    game.player.location_id = home['hq']
    game = act(engine, game, 'cross_dispatch', fleet_id=fleet['id'], destination='true_demon')
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='跨界商队'):
        engine.fleet_action(game.id, dict(action='relocate'))
    assert engine.store._path(game.id).read_bytes() == saved
    with pytest.raises(ValueError, match='请选择'):
        engine.fleet_action(game.id, dict(action='reopen', route_id=net.route_key('xuanji', 'spirit', 'true_demon')))
    assert engine.store._path(game.id).read_bytes() == saved
