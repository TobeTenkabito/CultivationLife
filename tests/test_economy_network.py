"""Round four: formal commands, cash conservation, freight ownership and closure."""
import copy
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system.economy import caravans, fleet_network as network, cross_freight
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.personal import public_personal
from cultivation_life.system.economy.state import ensure_regional_market

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def economy(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game = engine._load(engine.create_game('四轮商路', 'supreme_metal', 'dao', 419, preset_id='core')['id'])
    game.pending_event = None
    game.player.realm_index = 2
    game.player.next_tribulation_age = None
    transfer_value(game, 'background:human', 'player', 10**9, '验收资金')
    engine.store.save(game)
    return engine, engine._load(game.id)


def cash(game):
    return (balance(game, 'player') + sum(a['balance'] for a in game.economy_v2['accounts'].values())
            + sum(a['reserves'] for rows in game.merchant_state['worlds'].values() for a in rows)
            + sum(r.get('resources', 0) for r in game.intrigue_state.get('factions', {}).values())
            + game.heavenly_court.get('treasury', 0) + sum(r['treasury'] for r in game.upper_institutions.values()))


def act(engine, game, action, **payload):
    engine.store.save(game)
    engine.fleet_action(game.id, dict(action=action, **payload))
    return engine._load(game.id)


def found(engine, game):
    game = act(engine, game, 'create')
    free = [f['id'] for f in game.economy_v2['transport']['worlds'][game.player.world]['fleets'].values()
            if f['owner_kind'] == 'independent' and not f['player_controlled']]
    for key in free[:2]:
        game.player.location_id = game.economy_v2['transport']['worlds'][game.player.world]['fleets'][key]['location']
        game = act(engine, game, 'pledge', fleet_id=key)
    return act(engine, game, 'found')


def test_personal_statement_keeps_own_cash_entries_after_world_ledger_rollover(economy):
    engine, game = economy
    opening = copy.deepcopy(public_personal(game))
    for _ in range(100):
        transfer_value(game, 'background:human', 'world:human', 1, '公共流水')
    assert public_personal(game) == opening
    game.player.inventory[0].quantity += 1 if game.player.inventory[0].id == 'spirit_stone' else 0
    snapshot = copy.deepcopy(game.to_dict())
    public_personal(game)
    assert game.to_dict() == snapshot
    GameState.from_dict(snapshot)


def test_starting_fleet_count_and_legacy_adoption_preserve_ids_money_rng(economy):
    engine, game = economy
    region = game.economy_v2['transport']['worlds']['human']
    assert len(region['fleets']) == 12
    old = next(iter(region['fleets'].values()))
    region['fleets'] = {old['id']: old}
    region.pop('ownership_version')
    for k in ['owner_kind', 'owner_id', 'player_controlled', 'pledged', 'guard_power']:
        old.pop(k)
    before, rng = cash(game), game.rng_state
    caravans.ensure_caravans(game, engine.maps)
    assert old['id'] in region['fleets'] and cash(game) == before and game.rng_state == rng
    assert not caravans.ensure_caravans(game, engine.maps)


def test_found_requires_own_and_two_others_and_uses_actual_map(economy):
    engine, game = economy
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='自己的商队'):
        engine.fleet_action(game.id, dict(action='found'))
    assert engine.store._path(game.id).read_bytes() == before
    money = cash(game)
    game = found(engine, game)
    own = next(a for a in game.merchant_state['worlds']['human'] if a.get('player_owned'))
    assert own['hq'] == game.player.location_id and own['offices'] == []
    assert len(network.active_fleets(game, 'human', 'alliance', own['id'])) == 3
    assert cash(game) == money
    with pytest.raises(ValueError, match='容量'):
        engine.fleet_action(game.id, dict(action='create', owner_kind='alliance'))


def test_independent_guard_purchase_and_duplicate_create_are_atomic(economy):
    engine, game = economy
    money = cash(game)
    game = act(engine, game, 'create')
    fleet = next(f for f in game.economy_v2['transport']['worlds']['human']['fleets'].values() if f['player_controlled'])
    assert fleet['guard_power'] == 0
    game = act(engine, game, 'guard', fleet_id=fleet['id'])
    assert game.economy_v2['transport']['worlds']['human']['fleets'][fleet['id']]['guard_power'] >= network.guard_required('human')
    assert cash(game) == money
    snapshot = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.fleet_action(game.id, dict(action='create'))
    assert engine.store._path(game.id).read_bytes() == snapshot


def test_alliance_application_funded_by_owner_with_guards(economy):
    engine, game = economy
    alliance = game.merchant_state['worlds']['human'][0]
    game.player.location_id = alliance['hq']
    game.merchant_state['membership'] = dict(world='human', alliance_id=alliance['id'], site='hq', rank=0)
    transfer_value(game, 'background:human', f'alliance:human:{alliance["id"]}', 100000, '验收出资')
    player_cash, reserve = balance(game, 'player'), alliance['reserves']
    game = act(engine, game, 'create', owner_kind='alliance')
    fleet = next(f for f in game.economy_v2['transport']['worlds']['human']['fleets'].values() if f['player_controlled'])
    assert fleet['guard_power'] > 0 and balance(game, 'player') == player_cash
    assert network.alliance_at(game, 'human', alliance['id'])['reserves'] < reserve


def spirit(engine, game):
    game.player.world = 'spirit'
    home = network.alliance_at(game, 'spirit', 'xuanji')
    game.player.location_id = home['hq']
    game.player.realm_index = 8
    caravans.ensure_caravans(game, engine.maps)
    return home


def test_passage_receipts_stay_in_departure_world_and_inventory_is_not_taxed(economy):
    engine, game = economy
    home = spirit(engine, game)
    branch = network.alliance_at(game, 'true_demon', 'xuanji')
    game.merchant_state['membership'] = dict(world='spirit', alliance_id='xuanji', site='hq', rank=2)
    old_home, old_branch = home['reserves'], branch['reserves']
    price = engine._merchant_passage_cost(game, 'true_demon')
    transfer_value(game, 'background:spirit', 'player', price, '验收路费')
    engine.store.save(game)
    engine.merchant_action(game.id, 'passage', dict(alliance_id='xuanji', destination='true_demon'))
    game = engine._load(game.id)
    assert network.alliance_at(game, 'spirit', 'xuanji')['reserves'] == old_home + price
    assert network.alliance_at(game, 'true_demon', 'xuanji')['reserves'] == old_branch
    assert game.player.world == 'true_demon'


def test_maintenance_closes_route_once_without_sweeping_branch(economy):
    engine, game = economy
    home = spirit(engine, game)
    branch = network.alliance_at(game, 'true_demon', 'xuanji')
    source = 'alliance:spirit:xuanji'
    transfer_value(game, source, 'background:spirit', balance(game, source), '验收府库耗尽')
    old = branch['reserves']
    game.player.age += 1
    network.advance_network(game, engine.maps)
    route = network.routes(game)[network.route_key('xuanji', 'spirit', 'true_demon')]
    assert not route['open'] and route['shortfall'] > 0
    assert branch['reserves'] == old and not network.route_open(game, home, 'true_demon')
    snapshot = copy.deepcopy(game.to_dict())
    network.advance_network(game, engine.maps)
    assert game.to_dict() == snapshot


def test_cross_freight_cash_and_goods_arrive_only_once(economy):
    engine, game = economy
    home = spirit(engine, game)
    region = game.economy_v2['transport']['worlds']['spirit']
    fleet = next(f for f in region['fleets'].values() if f['alliance_id'] == 'xuanji')
    transfer_value(game, 'background:spirit', f'caravan:{fleet["id"]}', 10**7, '验收商队本金')
    fleet['investment'] = 10**7
    ensure_regional_market(game, engine.maps, 'spirit', home['hq'])
    source = game.economy_v2['markets'][f'spirit:{home["hq"]}']
    for row in source['commodities'].values():
        row['stock'] = row['target'] * 3
    before = cash(game)
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon')
    trip = fleet['cross_trip']
    target = game.economy_v2['markets'][f'true_demon:{trip["location"]}']
    item, bought = trip['item'], trip['quantity']
    assert trip['quantity'] == bought and cash(game) == before
    snapshot = copy.deepcopy(game.to_dict())
    cross_freight.advance_freight(game, engine.maps, fleet, region)
    assert game.to_dict() == snapshot
    game.player.age = trip['arrival']
    before_home = home['reserves']
    cross_freight.advance_freight(game, engine.maps, fleet, region)
    assert trip['phase'] == 'return' and trip['remittance'] > 0 and home['reserves'] == before_home
    assert balance(game, f'freight:{fleet["id"]}') == trip['remittance']
    GameState.from_dict(game.to_dict())
    amount = trip['remittance']
    game.player.age = trip['arrival']
    cross_freight.advance_freight(game, engine.maps, fleet, region)
    assert not fleet['cross_trip'] and home['reserves'] >= before_home + amount
    assert cash(game) == before


def test_persistent_network_rejects_negative_guard_or_duplicate_cash(economy):
    _, game = economy
    data = game.to_dict()
    fleet = next(iter(data['economy_v2']['transport']['worlds']['human']['fleets'].values()))
    fleet['guard_power'] = -1
    with pytest.raises(ValueError, match='经济存档'):
        GameState.from_dict(data)


def test_branch_expansion_increases_capacity_and_debits_local_treasury(economy):
    engine, game = economy
    game = found(engine, game)
    own = next(a for a in game.merchant_state['worlds']['human'] if a.get('player_owned'))
    old_hq = own['hq']
    transfer_value(game, 'background:human', f'alliance:human:{own["id"]}', 100000, '验收分部资金')
    game.player.location_id = next(r['id'] for r in engine.maps.worlds['human']['locations'] if not r.get('min_realm_index') and r['id'] != old_hq)
    game = act(engine, game, 'branch')
    own = network.alliance_at(game, 'human', own['id'])
    assert network.fleet_limit('alliance', own) == 6 and own['reserves'] == 80000
    game = act(engine, game, 'create', owner_kind='alliance')
    assert len(network.active_fleets(game, 'human', 'alliance', own['id'])) == 4


def test_player_regional_hq_three_local_fleets_and_separate_construction(economy):
    engine, game = economy
    spirit(engine, game)
    game = found(engine, game)
    home = next(a for a in game.merchant_state['worlds']['spirit'] if a.get('player_owned'))
    game.player.world = 'true_demon'
    game.player.location_id = game.merchant_state['worlds']['true_demon'][0]['hq']
    caravans.ensure_caravans(game, engine.maps)
    free = [f['id'] for f in game.economy_v2['transport']['worlds']['true_demon']['fleets'].values() if f['owner_kind'] == 'independent']
    for key in free:
        game.player.location_id = game.economy_v2['transport']['worlds']['true_demon']['fleets'][key]['location']
        game = act(engine, game, 'pledge', fleet_id=key)
    game = act(engine, game, 'regional_hq')
    branch = network.alliance_at(game, 'true_demon', home['id'])
    assert branch and branch['leader']['realm_index'] >= 7
    route = network.routes(game)[network.route_key(home['id'], 'spirit', 'true_demon')]
    assert not route['open']
    game = act(engine, game, 'build_passage')
    assert network.route_open(game, network.alliance_at(game, 'true_demon', home['id']), 'spirit')
    assert network.alliance_at(game, 'spirit', home['id'])['reserves'] == 0


def test_affiliation_preserves_regional_identity_cash_and_fleet_ids(economy):
    engine, game = economy
    spirit(engine, game)
    game = found(engine, game)
    home = next(a for a in game.merchant_state['worlds']['spirit'] if a.get('player_owned'))
    game.player.world = 'true_demon'
    target = next(a for a in game.merchant_state['worlds']['true_demon'] if not a['cross_world'])
    game.player.location_id = target['hq']
    caravans.ensure_caravans(game, engine.maps)
    identities = set(game.economy_v2['transport']['worlds']['true_demon']['fleets'])
    original, reserves = target['id'], target['reserves']
    game = act(engine, game, 'affiliate', alliance_id=original)
    branch = network.alliance_at(game, 'true_demon', home['id'])
    assert branch['id'] == original and branch['name'] == home['name']
    assert branch['reserves'] > reserves and set(game.economy_v2['transport']['worlds']['true_demon']['fleets']) == identities
    game = act(engine, game, 'build_passage')
    assert network.route_open(game, network.alliance_at(game, 'true_demon', original), 'spirit')


def test_closed_route_keeps_return_remittance_in_transit(economy):
    engine, game = economy
    home = spirit(engine, game)
    region = game.economy_v2['transport']['worlds']['spirit']
    fleet = next(f for f in region['fleets'].values() if f['alliance_id'] == 'xuanji')
    transfer_value(game, 'background:spirit', f'caravan:{fleet["id"]}', 10**7, '验收运输资金')
    ensure_regional_market(game, engine.maps, 'spirit', home['hq'])
    for row in game.economy_v2['markets'][f'spirit:{home["hq"]}']['commodities'].values():
        row['stock'] = row['target'] * 3
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon')
    game.player.age = fleet['cross_trip']['arrival']
    cross_freight.advance_freight(game, engine.maps, fleet, region)
    escrow = balance(game, f'freight:{fleet["id"]}')
    route = network.routes(game)[network.route_key('xuanji', 'spirit', 'true_demon')]
    route['open'] = False
    game.player.age = fleet['cross_trip']['arrival']
    money = home['reserves']
    cross_freight.advance_freight(game, engine.maps, fleet, region)
    assert balance(game, f'freight:{fleet["id"]}') == escrow and home['reserves'] == money
    assert fleet['cross_trip']['phase'] == 'return'


def test_unadopted_society_does_not_create_empty_routes_on_spatial_year(economy):
    engine, game = economy
    game.merchant_state = {}
    game.economy_v2.pop('network')
    game.economy_v2['transport']['worlds'] = {}
    game.player.age += 1
    caravans.advance_caravans(game, engine.maps)
    assert 'network' not in game.economy_v2
    assert not game.economy_v2['transport']['worlds']


def test_unvisited_hq_is_not_bankrupted_before_financial_adoption(economy):
    engine, game = economy
    home = network.alliance_at(game, 'spirit', 'xuanji')
    opening = home['reserves']
    game.player.age += 1000
    network.advance_network(game, engine.maps)
    assert home['reserves'] == opening
    game.player.world = 'true_demon'
    game.player.location_id = network.alliance_at(game, 'true_demon', 'xuanji')['hq']
    caravans.ensure_caravans(game, engine.maps)
    assert 'spirit' in game.economy_v2['transport']['worlds']
    assert home['reserves'] == opening
    game.player.age += 1
    network.advance_network(game, engine.maps)
    assert 0 < home['reserves'] < opening


def test_sect_capacity_and_institution_exclusion(economy):
    engine, game = economy
    from cultivation_life.system.economy.organizations import register
    from cultivation_life.system.faction_geography import faction_site
    entity = next(s for s in game.sects.values() if s.world == 'human' and s.kind == 'sect')
    register(game, 'sect', entity.id, 'human')
    transfer_value(game, 'background:human', f'organization:sect:{entity.id}', 100000, '验收组织资本')
    game.player.faction_id = entity.id
    game.player.location_id = faction_site(entity)['id']
    game = act(engine, game, 'create', owner_kind='sect')
    game = act(engine, game, 'create', owner_kind='sect')
    assert len(network.active_fleets(game, 'human', 'sect', entity.id)) == 2
    network.seed_organization_fleets(game, engine.maps, 'human', game.economy_v2['transport']['worlds']['human'])
    assert len(network.active_fleets(game, 'human', 'sect', entity.id)) == 2
    with pytest.raises(ValueError, match='容量'):
        engine.fleet_action(game.id, dict(action='create', owner_kind='sect'))
    with pytest.raises(ValueError, match='机构'):
        engine.fleet_action(game.id, dict(action='create', owner_kind='court'))


def test_industry_paid_investment_and_war_supply_shortage(economy):
    engine, game = economy
    from cultivation_life.system.economy.organizations import register
    from cultivation_life.system.economy.industry import settle_industry
    from cultivation_life.system.faction_geography import faction_site
    entity = next(s for s in game.sects.values() if s.world == 'human' and s.kind == 'sect')
    entity.founded_by_player = True
    game.player.faction_id = entity.id
    game.player.location_id = faction_site(entity)['id']
    register(game, 'sect', entity.id, 'human')
    key = f'organization:sect:{entity.id}'
    transfer_value(game, 'background:human', key, 100000, '验收产业资金')
    money = cash(game)
    game = act(engine, game, 'industry', owner_kind='sect')
    row = game.economy_v2['organizations'][key]
    assert row['industry_level'] == 1 and cash(game) == money
    transfer_value(game, key, 'background:human', balance(game, key), '验收财政枯竭')
    game.wars.append(dict(kind='sect', world='human', status='active', attacker_id=entity.id, defender_id='opponent'))
    entity = game.sects[entity.id]
    market = game.economy_v2['markets'][f'human:{entity.location_id}']
    stocks = {k:r['stock'] for k,r in market['commodities'].items()}
    settle_industry(game, engine.maps, entity, row, 1)
    assert row['war_funding'] == 0 and row['industry_utilization'] == 0
    assert stocks == {k:r['stock'] for k,r in market['commodities'].items()}
