"""Addressed influence, original local workers and finite market receipts."""
import copy
from pathlib import Path

import pytest

from test_heavens_outposts import frontier, quiet, act, load, dispatch, wait
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.person_assignments import in_transit, require_unassigned
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.heavens import outposts, outpost_runtime as base, outpost_development as development
from cultivation_life.system.heavens.outpost_schema import validate_outposts, validate_references
from cultivation_life.system.heavens.outpost_definitions import target
from cultivation_life.system.territory import state as territory, revenue


@pytest.fixture(scope='module')
def established(tmp_path_factory):
    bundle = quiet(frontier.__wrapped__(tmp_path_factory.mktemp('development')))
    act(bundle, 'outpost_authorize')
    dispatch(bundle)
    dispatch(bundle)
    wait(bundle, 16)
    act(bundle, 'outpost_depart')
    wait(bundle, 10)
    game = load(bundle)
    row = base.get(game, target('tianjian'))
    assert row['status'] == 'active'
    assert len(development.workers(bundle[2], game, row)) == 1
    return bundle, copy.deepcopy(game)


@pytest.fixture
def branch(established, monkeypatch):
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'], 'enabled', False)
    bundle, original = established
    bundle[0].store.save(copy.deepcopy(original))
    return bundle


def local(bundle):
    game = load(bundle)
    return game, base.get(game, target('tianjian'))


def open_branch(bundle):
    act(bundle, 'outpost_develop')
    game, row = local(bundle)
    worker = development.workers(bundle[2], game, row)[0]['id']
    places = development.project(bundle[2], game, row, row['id'])['locations']
    place = next(p for p in places if p['id'] != 'red_marrow_city' and any(a['action'] == 'outpost_expand' and a['enabled'] for a in p['actions']))
    return worker, place['id']


def tick(bundle, until=None, years=1):
    """Use actual original annual NPC transport; persist for command/reload checks."""
    game, row = local(bundle)
    for _ in range(years):
        game.player.age += 1
        base.year_step(bundle[2], game)
        if until and until(game, row):
            break
    bundle[0].store.save(game)
    return game, row


def finish(bundle):
    return tick(bundle, lambda g, r: all(u.get('local_job', {}).get('status') != 'active' for u in r['units']), 120)


def test_original_worker_expands_builds_and_returns_materials_are_consumed_once(branch):
    worker, place = open_branch(branch)
    game, row = local(branch)
    original_people = {n.id for s in game.sects.values() for n in s.npcs} | set(game.world_npcs)
    governor = row['governor_id']
    act(branch, 'outpost_expand', dict(person_id=worker, location_id=place))
    game, row = local(branch)
    unit = next(u for u in row['units'] if u['person_id'] == worker)
    assert in_transit(game, worker)
    assert game.world_npcs[worker].location_id == 'red_marrow_city'
    assert row['owner_id'] not in territory.snapshot(game, branch[0].maps, 'demon').get(place, {})
    with pytest.raises(ValueError): require_unassigned(game, worker)
    game, row = finish(branch)
    assert next(u for u in row['units'] if u['person_id'] == worker)['local_job']['result'] == 'expanded'
    own = territory.snapshot(game, branch[0].maps, 'demon')[place][row['owner_id']]
    assert 0 < own['value'] <= 20 and not own['outpost']
    assert game.world_npcs[worker].location_id == game.world_npcs[governor].location_id == 'red_marrow_city'
    before = dict(row['stock'])
    act(branch, 'outpost_build_site', dict(person_id=worker, location_id=place))
    game, row = local(branch)
    for key, quantity in base.materials('human').items():
        assert row['stock'][key] == before[key] - quantity
    game, row = finish(branch)
    own = territory.snapshot(game, branch[0].maps, 'demon')[place][row['owner_id']]
    assert own['outpost'] and own['value'] >= 50
    assert {n.id for s in game.sects.values() for n in s.npcs} | set(game.world_npcs) == original_people
    assert game.sects['tianjian'].world == 'human'
    assert game.sects['tianjian'].location_id == 'wudi_plain'
    act(branch, 'outpost_policy', dict(location_id=place, policy='patrol'))
    validate_outposts(local(branch)[0].heavens_state['runtime']['outposts'])
    validate_references(local(branch)[0])


def test_preview_pure_invalid_worker_nonadjacent_and_unfunded_are_atomic(branch):
    worker, place = open_branch(branch)
    game, row = local(branch)
    path = branch[0].store._path(branch[1]); before = path.read_bytes()
    original = copy.deepcopy(game.to_dict())
    outposts.project(branch[2], game)
    development.quote(branch[2], game, row, 'outpost_expand', dict(person_id=worker, location_id=place))
    assert path.read_bytes() == before
    assert game.to_dict() == original
    for options in [dict(person_id=row['governor_id'], location_id=place), dict(person_id=worker, location_id='unknown')]:
        with pytest.raises(ValueError): act(branch, 'outpost_expand', options)
        assert path.read_bytes() == before
    transfer_value(game, base.wallet(row), 'player', balance(game, base.wallet(row)), 'test real withdrawal')
    branch[0].store.save(game); before=path.read_bytes()
    with pytest.raises(ValueError, match='经费不足'): act(branch, 'outpost_expand', dict(person_id=worker, location_id=place))
    assert path.read_bytes() == before


def test_real_market_procurement_stale_quote_and_no_duplicate_goods(branch):
    open_branch(branch)
    game, row = local(branch)
    ensure_regional_market(game, branch[0].maps, 'demon', 'red_marrow_city')
    branch[0].store.save(game)
    game, row = local(branch)
    market, needed, bills, total, fingerprint = development.local_quote(branch[2], game, row)
    assert len(bills) == 3
    original = {key: market['commodities'][key.removeprefix('item:')]['stock'] for key in needed}
    oldcash = balance(game, base.wallet(row))
    market['revision'] += 1
    branch[0].store.save(game)
    with pytest.raises(ValueError, match='报价已经变化'): act(branch, 'outpost_buy_materials', {'quote_id': fingerprint})
    game, row = local(branch)
    fingerprint = development.local_quote(branch[2], game, row)[4]
    act(branch, 'outpost_buy_materials', {'quote_id': fingerprint})
    game, row = local(branch)
    market = development.local_quote(branch[2], game, row)[0]
    assert balance(game, base.wallet(row)) == oldcash - total
    for key, qty in needed.items():
        assert row['stock'][key] == qty
        assert market['commodities'][key.removeprefix('item:')]['stock'] == original[key] - qty
    from cultivation_life.system.territory.runtime import settle_unit
    import random
    operator=balance(game,f'operator:{market["id"]}')
    settle_unit(branch[0],game,random.Random(1))
    assert row['development']['income']>0
    assert balance(game,f'operator:{market["id"]}')<operator


def test_cancel_suspended_job_returns_original_unspent_materials_along_road(branch):
    worker, place = open_branch(branch)
    act(branch, 'outpost_expand', dict(person_id=worker, location_id=place)); finish(branch)
    game, row = local(branch); stock=copy.deepcopy(row['stock'])
    act(branch, 'outpost_build_site', dict(person_id=worker, location_id=place))
    tick(branch, lambda g,r: next(u for u in r['units'] if u['person_id']==worker)['phase']=='local_work', 50)
    act(branch, 'outpost_suspend')
    act(branch, 'outpost_cancel_local', dict(person_id=worker))
    game, row = finish(branch)
    assert row['status'] == 'suspended' and row['stock'] == stock
    unit=next(u for u in row['units'] if u['person_id']==worker)
    assert unit['local_job']['status']=='cancelled' and not balance(game,unit['local_job']['wallet'])
    assert game.world_npcs[worker].location_id == 'red_marrow_city'


def test_death_loses_cargo_and_purse_without_replacement(branch):
    worker, place = open_branch(branch)
    act(branch,'outpost_expand',dict(person_id=worker,location_id=place)); finish(branch)
    act(branch,'outpost_build_site',dict(person_id=worker,location_id=place))
    game,row=local(branch); unit=next(u for u in row['units'] if u['person_id']==worker)
    before=dict(row['stock']); people=set(game.world_npcs)
    game.world_npcs[worker].alive=False; branch[0].store.save(game)
    game,row=tick(branch)
    unit=next(u for u in row['units'] if u['person_id']==worker)
    assert unit['phase']=='lost' and unit['local_job']['status']=='lost'
    assert row['stock']==before and not unit['local_job']['stock']
    assert not balance(game,unit['local_job']['wallet']) and set(game.world_npcs)==people


def test_fee_income_is_finite_local_endpoint_only_and_cursors_prevent_repay(branch):
    open_branch(branch)
    game,row=local(branch); ensure_regional_market(game,branch[0].maps,'demon','red_marrow_city')
    market=game.economy_v2['markets']['demon:red_marrow_city']; revenue.adopt(game,market)
    previous=balance(game,base.wallet(row))
    transfer_value(game,'player',f'operator:{market["id"]}',10000,'test actual operator funds')
    market['fees']+=10000
    revenue.distribute(game,branch[0].maps)
    earned=balance(game,base.wallet(row))-previous
    assert 0<earned<=2000 and row['development']['income']==earned
    revenue.distribute(game,branch[0].maps)
    assert balance(game,base.wallet(row))==previous+earned
    row['status']='suspended'; market['fees']+=10000
    revenue.distribute(game,branch[0].maps)
    row['status']='active'; revenue.distribute(game,branch[0].maps)
    assert balance(game,base.wallet(row))==previous+earned


def test_export_arrives_at_original_treasury_never_player_and_governor_stays(branch):
    worker,_=open_branch(branch)
    game,row=local(branch)
    cash=balance(game,'organization:sect:tianjian'); player=balance(game,'player')
    act(branch,'outpost_export',dict(person_id=worker))
    game,row=local(branch)
    assert balance(game,'organization:sect:tianjian')==cash and balance(game,'player')==player
    # Destination years pay and complete the physical crossing. Only source
    # years can unload at the fixed original depot.
    game,row=tick(branch,years=8)
    assert game.world_npcs[worker].world=='human'
    from cultivation_life.regional_context import CalendarGame
    base.year_step(branch[2],CalendarGame(game,'human',game.player.age+1))
    assert balance(game,'organization:sect:tianjian')==cash+10000
    assert balance(game,'player')==player and row['status']=='active'
    assert game.world_npcs[row['governor_id']].world=='demon'
    base.year_step(branch[2],CalendarGame(game,'human',game.player.age+2))
    assert balance(game,'organization:sect:tianjian')==cash+10000


def test_frozen_world_and_instance_years_do_not_advance_local_job(branch):
    from cultivation_life.engine.world.regions import ensure
    worker,place=open_branch(branch)
    act(branch,'outpost_expand',dict(person_id=worker,location_id=place))
    game,row=local(branch); ensure(branch[0]._dependencies.regions, game)
    from cultivation_life.regional_context import CalendarGame
    frozen=copy.deepcopy(row)
    base.year_step(branch[2],CalendarGame(game,'human',game.player.age+1))
    assert row==frozen
    game.world_simulation['space_years']=[[game.player.age+1,game.player.age+5]]
    base.year_step(branch[2],CalendarGame(game,'demon',game.player.age+1))
    assert row==frozen


def test_withdraw_retracts_only_our_claims_and_local_worker_returns_before_crossing(branch):
    worker,place=open_branch(branch)
    act(branch,'outpost_expand',dict(person_id=worker,location_id=place))
    before=territory.snapshot(local(branch)[0],branch[0].maps,'demon')
    act(branch,'outpost_withdraw')
    game,row=local(branch)
    after=territory.snapshot(game,branch[0].maps,'demon')
    assert all('tianjian' not in rows for rows in after.values())
    for loc,rows in before.items():
        for identity,claim in rows.items():
            if identity!='tianjian': assert after[loc][identity]==claim
    tick(branch,years=2)
    game,row=local(branch)
    assert next(u for u in row['units'] if u['person_id']==worker)['phase'] in {'stationed','returning'}


def test_capacity_and_restricted_maps_reuse_native_geographic_rules(branch):
    worker,place=open_branch(branch)
    game,row=local(branch)
    others=[s.id for s in game.sects.values() if s.world=='demon' and not s.extinct and s.kind=='sect'][:3]
    assert len(others)==3
    book=territory.state(game)['holdings']['demon']
    book[place]={identity:dict(value=20.,outpost=False,policy='') for identity in others}
    restricted=next(s['id'] for s in branch[0].maps.worlds['demon']['locations'] if s.get('min_realm_index',0))
    branch[0].store.save(game)
    for location,reason in [(place,'三个势力'),(restricted,'境界门槛')]:
        with pytest.raises(ValueError,match=reason):
            act(branch,'outpost_expand',dict(person_id=worker,location_id=location))


def test_controller_loss_and_custody_pause_without_consuming_escrow(branch):
    worker,place=open_branch(branch)
    game,row=local(branch);game.player.faction_id=None;branch[0].store.save(game)
    with pytest.raises(ValueError,match='授权'):act(branch,'outpost_expand',dict(person_id=worker,location_id=place))
    game.player.faction_id='tianjian';branch[0].store.save(game)
    act(branch,'outpost_expand',dict(person_id=worker,location_id=place))
    game,row=local(branch);unit=next(u for u in row['units'] if u['person_id']==worker)
    before=unit['progress'],balance(game,unit['local_job']['wallet'])
    game.intrigue_state.setdefault('npc_prisons',{})[worker]={'test':True}
    branch[0].store.save(game)
    game,row=tick(branch,years=3);unit=next(u for u in row['units'] if u['person_id']==worker)
    assert (unit['progress'],balance(game,unit['local_job']['wallet']))==before
    assert game.world_npcs[worker].location_id=='red_marrow_city'


def test_real_counter_costs_native_treasury_once_and_history_does_not_replay(branch):
    worker,_=open_branch(branch)
    game,row=local(branch)
    rival=next(s for s in game.sects.values() if s.world=='demon' and s.kind=='sect' and s.npcs)
    rival.location_id='red_marrow_city'
    rival.npcs[0].location_id='red_marrow_city'
    from cultivation_life.system.economy import organizations
    organizations.register(game,'sect',rival.id,'demon')
    funds=game.intrigue_state['factions']['sect:'+rival.id]
    funds['resources']=100000
    before=sum(r['resources'] for k,r in game.intrigue_state['factions'].items() if k.startswith('sect:') and k!='sect:tianjian')
    game.player.age+=10;branch[0].store.save(game)
    act(branch,'outpost_expand',dict(person_id=worker,location_id='red_marrow_city'))
    game,row=finish(branch)
    after=sum(r['resources'] for k,r in game.intrigue_state['factions'].items() if k.startswith('sect:') and k!='sect:tianjian')
    assert before-after==1000
    assert any('出资抵制' in h['text'] for h in row['history'])
    from cultivation_life.regional_context import CalendarGame
    unit=next(u for u in row['units'] if u['person_id']==worker)
    row['development']['counter_decade']=0
    development.reaction(branch[2],CalendarGame(game,'demon',game.player.age-1),row,unit)
    assert sum(r['resources'] for k,r in game.intrigue_state['factions'].items() if k.startswith('sect:') and k!='sect:tianjian')==after


def test_dlc_and_branch_share_one_pool_and_removing_branch_never_reclaims_old_fees(branch,monkeypatch):
    open_branch(branch)
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',True)
    from cultivation_life.system.territory import runtime
    game,row=local(branch)
    runtime.activate(game,branch[0].maps)
    market=game.economy_v2['markets']['demon:red_marrow_city']
    revenue.distribute(game,branch[0].maps)  # A mode change adopts current fees.
    previous=balance(game,f'operator:{market["id"]}')
    transfer_value(game,'player',f'operator:{market["id"]}',10000,'test original new receipt')
    market['fees']+=10000
    revenue.distribute(game,branch[0].maps)
    left=balance(game,f'operator:{market["id"]}')
    assert 0<previous+10000-left<=2000
    assert row['development']['income']>0
    row['status']='withdrawing';development.abandon(game,row)
    revenue.distribute(game,branch[0].maps)
    assert balance(game,f'operator:{market["id"]}')==left
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',False)
    market['fees']+=10000;row['status']='active'
    revenue.distribute(game,branch[0].maps)
    assert balance(game,f'operator:{market["id"]}')==left


def test_family_frontier_uses_original_family_identity_and_map_projection(branch):
    from cultivation_life.system.territory.presentation import augment
    from cultivation_life.system.economy import organizations
    game,row=local(branch)
    family=game.sects.pop('tianjian');family.kind='family';game.family=family
    row['owner_kind']='family'
    organizations.register(game,'family',family.id,'human')
    game.intrigue_state['factions']['family:tianjian']['controller_id']='player'
    branch[0].store.save(game)
    act(branch,'outpost_develop')
    game,row=local(branch)
    data=augment(game,branch[0].maps,dict(locations=[dict(id='red_marrow_city')]))
    own=next(r for r in data['locations'][0]['influences'] if r['id']=='tianjian')
    assert own['name']==family.name and own['owned'] and not own['headquarters']
    assert game.family.id=='tianjian' and game.family.world=='human' and 'tianjian' not in game.sects
    validate_references(game)


def test_lost_duel_preserves_main_floor_and_records_real_result(branch,monkeypatch):
    worker,_=open_branch(branch)
    game,row=local(branch)
    # Use a real local rival at the main site; the completed real duel cannot
    # remove the existing maintained main-site floor on a loss.
    main='red_marrow_city'
    rival=next(s for s in game.sects.values() if s.world=='demon' and s.kind=='sect' and s.npcs)
    rival.location_id=main
    rival.npcs[0].realm_index=3;rival.npcs[0].location_id=main
    import cultivation_life.system.heavens.outpost_development as module
    monkeypatch.setattr(module,'contest_chance',lambda own,enemy:0.)
    branch[0].store.save(game)
    act(branch,'outpost_spar',dict(person_id=worker,location_id=main,rival_id=rival.id))
    game,row=finish(branch)
    assert next(u for u in row['units'] if u['person_id']==worker)['local_job']['result']=='lost'
    assert territory.snapshot(game,branch[0].maps,'demon')[main]['tianjian']['value']==50


def test_long_suspension_keeps_original_main_facility_recoverable_without_new_money(branch):
    open_branch(branch)
    act(branch,'outpost_suspend')
    original_game,original_row=local(branch)
    original_cash=balance(original_game,base.wallet(original_row))
    game,row=tick(branch,years=110)
    before=balance(game,base.wallet(row))
    main=territory.state(game)['holdings']['demon']['red_marrow_city']['tianjian']
    assert main['value']==0 and main['outpost']
    assert row['development']['income']==0 and before==original_cash
    act(branch,'outpost_activate')
    game,row=local(branch)
    assert territory.snapshot(game,branch[0].maps,'demon')['red_marrow_city']['tianjian']['value']==50
    assert territory.state(game)['holdings']['demon']['red_marrow_city']['tianjian']['value']==50
    assert balance(game,base.wallet(row))==before
    act(branch,'outpost_policy',dict(location_id='red_marrow_city',policy='extraction'))
    game,row=tick(branch)
    assert territory.state(game)['holdings']['demon']['red_marrow_city']['tianjian']['policy']=='extraction'

