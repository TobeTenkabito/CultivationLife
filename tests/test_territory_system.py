"""Geography, treasury conservation and actual command/save invariants."""
import copy
import random
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import WORLD_SYSTEMS, FACTION_DEFINITIONS
from cultivation_life.models import SectState, SectNpc
from cultivation_life.system.territory import state as territory
from cultivation_life.system.territory.actions import apply, construction_plan
from cultivation_life.system.territory.rules import band
from cultivation_life.system.territory.peace import apply as peace, targets
from cultivation_life.system.territory.runtime import prepare,settle,dividends

@pytest.mark.parametrize('requested,interruption,elapsed', [(1,None,100),(3,None,300),(3,37,37)])
def test_real_action_coalesces_territory_and_charges_only_elapsed_years(scenario,monkeypatch,requested,interruption,elapsed):
    from cultivation_life.system.territory import runtime
    from unittest.mock import Mock
    engine,game,entity=scenario
    game.player.realm_index=9
    game.player.lifespan=None
    game.player.technique=None
    loc=frontier(engine,game,entity)
    territory.ensure(game,engine.maps,'human').setdefault(loc,{})[entity.id]=dict(value=70.,outpost=True,policy='')
    for place,claims in game.intrigue_state['territory']['holdings']['human'].items():
        if place not in {entity.location_id,loc}:claims.pop(entity.id,None)
    row=game.economy_v2['organizations'][accounts.key('sect',entity.id)]
    row['expected_upkeep']=100
    runtime.activate(game,engine.maps)
    start=game.player.age
    def annual(actual,rng,news,**kwargs):
        if interruption and actual.player.age-start==interruption:
            actual.pending_event={'id':'period-interruption','title':'期中验收事件'}
            return False
        return True
    # Isolate the common dispatch boundary, retaining real aging, authority,
    # treasury transfers, influence settlement, command save and presentation.
    monkeypatch.setattr(engine,'_advance_world_year',annual)
    proposal=Mock();monkeypatch.setattr(runtime,'npc_proposal',proposal)
    endpoint=Mock(wraps=runtime.settle_unit);monkeypatch.setattr(runtime,'settle_unit',endpoint)
    # Wrap the named shared capability; keep the real endpoint and command.
    monkeypatch.setattr(engine,'_settle_territory_time',lambda actual,rng:endpoint(engine,actual,rng))
    engine.store.save(game)
    view=engine.advance(game.id,'rest',requested)
    actual=engine._load(game.id)
    paid=actual.economy_v2['organizations'][accounts.key('sect',entity.id)]
    assert view['player']['age']-start==elapsed
    assert endpoint.call_count==proposal.call_count==1
    assert paid['territory_years']==elapsed
    assert paid['territory_due']==paid['territory_paid']==10*elapsed
    assert actual.intrigue_state['territory']['settlement_years'][accounts.key('sect',entity.id)]==start+elapsed
    before=copy.deepcopy(actual.to_dict())
    runtime.settle_unit(engine,actual,random.Random(1))
    assert actual.to_dict()==before and proposal.call_count==1

def test_annual_finance_does_not_run_territory_stages(scenario,monkeypatch):
    from cultivation_life.system.territory import runtime
    from cultivation_life.system.economy.organizations import advance_organizations
    engine,game,entity=scenario
    runtime.activate(game,engine.maps)
    frozen=copy.deepcopy(game.intrigue_state['territory'])
    def forbidden(*args,**kwargs):raise AssertionError('Territory must settle at the action endpoint')
    for method in ('prepare','settle','dividends','npc_proposal'):
        monkeypatch.setattr(runtime,method,forbidden)
    game.player.age+=1
    advance_organizations(game,engine.maps)
    assert game.intrigue_state['territory']==frozen

def test_disabled_years_and_adoption_have_no_territorial_catch_up(scenario,monkeypatch):
    from cultivation_life.system.territory import runtime
    engine,game,entity=scenario
    loc=frontier(engine,game,entity)
    territory.ensure(game,engine.maps,'human').setdefault(loc,{})[entity.id]=dict(value=70.,outpost=True,policy='')
    for place,claims in game.intrigue_state['territory']['holdings']['human'].items():
        if place not in {entity.location_id,loc}:claims.pop(entity.id,None)
    runtime.activate(game,engine.maps)
    row=game.economy_v2['organizations'][accounts.key('sect',entity.id)];row['expected_upkeep']=100
    monkeypatch.setattr(runtime,'npc_proposal',lambda *args:None)
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',False)
    frozen=copy.deepcopy(game.intrigue_state['territory'])
    runtime.activate(game,engine.maps);game.player.age+=100
    runtime.settle_unit(engine,game,random.Random(1))
    assert game.intrigue_state['territory']==frozen
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',True)
    runtime.activate(game,engine.maps)
    game.player.age+=7
    before=cash(game);runtime.settle_unit(engine,game,random.Random(1))
    assert row['territory_years']==7 and row['territory_paid']==70
    assert cash(game)==before
from cultivation_life.system.organization_relocation import relocate,race_site
from cultivation_life.system.economy import organization_accounts as accounts
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.system.economy.state import ensure_regional_market

ROOT=Path(__file__).resolve().parents[1]

def test_remote_settlement_interval_preserves_member_control_and_war(scenario,monkeypatch):
    from cultivation_life.system.economy.organizations import settlement_interval
    engine,game,_=scenario
    entity=game.sects['remote_human_1']
    row=accounts.register(game,'sect',entity.id,'human')
    assert settlement_interval(game,row)==5
    game.player.faction_id=entity.id
    assert settlement_interval(game,row)==1
    game.player.faction_id=None
    game.intrigue_state['factions'][f'sect:{entity.id}']['controller_id']='player'
    assert settlement_interval(game,row)==1
    game.intrigue_state['factions'][f'sect:{entity.id}']['controller_id']=None
    game.wars.append(dict(kind='sect',world='human',status='active',attacker_id=entity.id,defender_id='jade_cloud'))
    assert settlement_interval(game,row)==1

def test_remote_small_sect_buys_one_real_estate_and_does_not_rebuy(scenario):
    from cultivation_life.system.economy.estate_management import invest_surplus
    engine,game,_=scenario
    entity=game.sects['remote_human_1'];row=accounts.register(game,'sect',entity.id,'human')
    transfer_value(game,'background:human',accounts.key('sect',entity.id),10000000,'验收拨款')
    row.update(workforce={'4':4},expected_upkeep=1000,expense=0,shortfall=0)
    before=cash(game)
    invest_surplus(game,engine.maps,entity,row)
    owned=[e for e in game.economy_v2['estates'].values() if e['owner_id']==entity.id]
    assert len(owned)==1 and row['expense']>0 and cash(game)==before
    saved=game.to_dict()
    invest_surplus(game,engine.maps,entity,row)
    assert game.to_dict()==saved

def test_remote_economy_uses_actual_elapsed_clock_without_duplicate_settlement(scenario):
    from cultivation_life.system.economy.organizations import advance_organizations
    engine,game,_=scenario;entity=game.sects['remote_human_1']
    row=accounts.register(game,'sect',entity.id,'human');start=row['last_year']
    game.player.age=start+4
    advance_organizations(game,engine.maps)
    assert row['last_year']==start and not row['history']
    game.player.age=start+5
    advance_organizations(game,engine.maps)
    assert row['last_year']==start+5 and len(row['history'])==1
    prior=copy.deepcopy(row)
    advance_organizations(game,engine.maps)
    assert row==prior

def test_lost_world_presentation_has_no_main_world_territory(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    view=engine.create_game('实例地方隔离','supreme_earth','dao',2110,preset_id='lost_world')
    assert view['player']['world']=='lost'
    assert not view['map'].get('territory') and not view['map'].get('organization_relocation')

def test_foreign_membership_does_not_expose_remote_finance_or_decisions(scenario):
    engine,game,entity=scenario
    entity.world='spirit'
    entity.location_id=next(iter(engine.maps._locations['spirit']))
    row=game.economy_v2['organizations'][accounts.key('sect',entity.id)]
    row.update(territory_income=43210,territory_due=8765,territory_paid=8765)
    before=game.to_dict()
    data=engine._public_map_with_ghost_parade(game,game.player.location_id)['territory']
    assert data['owner_id'] is None and not data['can_propose'] and not data['locations']
    assert data['income']==data['upkeep_due']==data['upkeep_paid']==0
    assert game.to_dict()==before

@pytest.fixture
def scenario(tmp_path,monkeypatch):
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',True)
    engine=GameEngine(ROOT,tmp_path)
    view=engine.create_game('地方验收','supreme_earth','dao',2110,custom_start=dict(world='human',realm_index=4,sect='new',sect_name='地方验收宗'))
    game=engine._load(view['id']);game.pending_event=None;game.active_trial=None
    entity=game.sects[game.player.faction_id]
    for npc in entity.npcs:npc.realm_index=1
    entity.location_id='expanse_human_1';game.player.location_id=entity.location_id
    accounts.register(game,'sect',entity.id,'human')
    transfer_value(game,'background:human',accounts.key('sect',entity.id),10000000,'验收拨款')
    territory.ensure(game,engine.maps,'human')
    return engine,game,entity

def frontier(engine,game,entity):
    book=territory.snapshot(game,engine.maps,entity.world)
    for loc in engine.maps.worlds[entity.world]['locations']:
        if entity.id in book.get(loc['id'],{}):continue
        try:territory.validate_projection(game,engine.maps,entity,loc['id'])
        except ValueError:continue
        return loc['id']
    raise AssertionError('no frontier')

def test_debug_organization_action_uses_real_vote_and_isolated_save(scenario,tmp_path):
    from cultivation_life.debug.runtime import Runtime
    engine,game,entity=scenario
    loc=frontier(engine,game,entity)
    engine.store.save(game)
    original=engine.store._path(game.id).read_bytes()
    manager=Runtime(ROOT,tmp_path/'debug',engine.store)
    session=manager.start(game.id)['session_id']
    before=copy.deepcopy(manager.load(session)['current'])
    with pytest.raises(RuntimeError) as rejected:
        manager.execute(f'organization action territory_policy sect {entity.id} {loc} stewardship',session_id=session)
    assert isinstance(rejected.value.__cause__,ValueError)
    assert manager.load(session)['current']==before
    manager.execute(f'organization action expand_influence sect {entity.id} {loc}',session_id=session)
    current=manager.load(session)['current']['game']
    assert current['intrigue_state']['territory']['holdings']['human'][loc][entity.id]['value']==20
    assert engine.store._path(game.id).read_bytes()==original

def cash(game):
    return sum(r['balance'] for r in game.economy_v2['accounts'].values())+sum(r.get('resources',0) for r in game.intrigue_state['factions'].values())+balance(game,'player')

@pytest.mark.parametrize('value,name',[(100,'中枢地区'),(90,'中枢地区'),(89.9,'核心地区'),(70,'核心地区'),(69.9,'战略要地'),(50,'战略要地'),(49.9,'边缘地区'),(30,'边缘地区'),(29.9,'缓冲地区'),(0,'缓冲地区')])
def test_unambiguous_bands(value,name):assert band(value)==name

def test_readonly_map_and_dlc_off_freeze(scenario,monkeypatch):
    engine,game,entity=scenario
    before=game.to_dict();view=engine._public_map_with_ghost_parade(game,game.player.location_id)
    assert view['roads'] and any(r['headquarters'] and r['value']==100 for loc in view['locations'] for r in loc['influences'] if r['id']==entity.id)
    assert game.to_dict()==before
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',False)
    frozen=copy.deepcopy(game.intrigue_state.get('territory'))
    prepare(game,engine.maps);settle(game,engine.maps,entity,game.economy_v2['organizations'][accounts.key('sect',entity.id)],100);dividends(game)
    assert game.intrigue_state['territory']==frozen
    assert not engine._public_map_with_ghost_parade(game,game.player.location_id)['territory']['enabled']

def test_no_jump_no_gated_projection_and_hq_exception(scenario):
    engine,game,entity=scenario
    books=territory.snapshot(game,engine.maps,'human')
    nonadj=next(r for r in engine.maps.worlds['human']['locations'] if not r.get('min_realm_index',0) and r['id'] not in books and not any(entity.id in books.get(n,{}) for n,_ in engine.maps._graphs['human'][r['id']]))
    with pytest.raises(ValueError,match='连续'):territory.validate_projection(game,engine.maps,entity,nonadj['id'])
    gated=next(r for r in engine.maps.worlds['human']['locations'] if r.get('min_realm_index',0))
    with pytest.raises(ValueError,match='门槛'):territory.validate_projection(game,engine.maps,entity,gated['id'])
    entity.location_id=gated['id'];book=territory.ensure(game,engine.maps,'human')
    assert book[gated['id']][entity.id]['value']==100
    assert territory.snapshot(game,engine.maps,'human')[gated['id']][entity.id]['floor']==100

def test_non_hq_capacity_three_is_enforced(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    book=territory.ensure(game,engine.maps,'human');book[loc]={}
    for i in range(3):
        rival=SectState(id=f'capacity_{i}',name=f'邻宗{i}',world='human',location_id=f'expanse_human_{i+8}')
        game.sects[rival.id]=rival;book[loc][rival.id]=dict(value=20.,outpost=False,policy='')
    with pytest.raises(ValueError,match='三个'):territory.validate_projection(game,engine.maps,entity,loc)
    book[loc].pop('capacity_0');territory.validate_projection(game,engine.maps,entity,loc)

def test_actual_expand_command_and_failed_submission_atomic(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity);engine.store.save(game)
    before=cash(game);rng=game.rng_state
    engine.organization_action(game.id,dict(kind='sect',owner_id=entity.id,action='expand_influence',location_id=loc))
    game=engine.store.load(game.id)
    assert entity.id in game.intrigue_state['territory']['holdings']['human'].get(loc,{}), str(game.intrigue_state['resolutions'][-1]['votes'])
    assert game.intrigue_state['territory']['holdings']['human'][loc][entity.id]['value']==20
    assert cash(game)==before
    previous=game.to_dict()
    with pytest.raises(ValueError,match='政策'):engine.organization_action(game.id,dict(kind='sect',owner_id=entity.id,action='territory_policy',location_id=loc,policy='stewardship'))
    assert engine.store.load(game.id).to_dict()==previous

def test_outpost_spends_original_materials_and_cash(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity);game.player.location_id=loc
    ensure_regional_market(game,engine.maps,'human',loc)
    market=game.economy_v2['markets'][f'human:{loc}'];plan=construction_plan(game,engine.maps,entity,loc)
    for item in plan['materials']:market['commodities'][item['id']]['stock']=30
    previous=cash(game);stocks={r['id']:market['commodities'][r['id']]['stock'] for r in plan['materials']}
    apply(game,engine.maps,entity,'build_outpost',loc,random.Random(1))
    assert cash(game)==previous
    for r in plan['materials']:assert market['commodities'][r['id']]['stock']==stocks[r['id']]-r['quantity']
    assert territory.snapshot(game,engine.maps,'human')[loc][entity.id]['floor']==50
    with pytest.raises(ValueError,match='已有'):apply(game,engine.maps,entity,'build_outpost',loc,random.Random(1))

def test_poverty_shrinks_without_debt_or_replaying_year(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    territory.ensure(game,engine.maps,'human').setdefault(loc,{})[entity.id]=dict(value=70.,outpost=True,policy='')
    row=game.economy_v2['organizations'][accounts.key('sect',entity.id)];row['expected_upkeep']=100000000
    prepare(game,engine.maps);settle(game,engine.maps,entity,row,100)
    actual=territory.snapshot(game,engine.maps,'human')[loc][entity.id]
    assert not actual['outpost'] and actual['value']<50 and row['territory_paid']==0
    assert row['territory_due']>0 and balance(game,accounts.key('sect',entity.id))>=0

def test_local_earnings_are_real_proportional_and_not_replayed(scenario):
    engine,game,entity=scenario;loc=entity.location_id
    rival=next(s for s in game.sects.values() if s.id!=entity.id and s.world=='human')
    accounts.register(game,'sect',rival.id,'human');book=territory.ensure(game,engine.maps,'human');book[loc][rival.id]=dict(value=50.,outpost=False,policy='')
    ensure_regional_market(game,engine.maps,'human',loc);market=game.economy_v2['markets'][f'human:{loc}']
    prepare(game,engine.maps);transfer_value(game,'background:human',f'operator:{market["id"]}',30000,'测试已收费用');market['fees']+=30000
    before=cash(game);a=balance(game,accounts.key('sect',entity.id));b=balance(game,accounts.key('sect',rival.id))
    dividends(game)
    assert balance(game,accounts.key('sect',entity.id))-a==4000 and balance(game,accounts.key('sect',rival.id))-b==2000
    assert cash(game)==before
    second=copy.deepcopy(game.economy_v2);dividends(game);assert game.economy_v2==second

def test_remove_hq_relocates_original_roster_without_respawn(scenario):
    engine,game,entity=scenario;old=entity.location_id;ids=[n.id for n in entity.npcs]
    player=(game.player.world,game.player.location_id);assets=copy.deepcopy(game.economy_v2.get('estates',{}))
    peace(game,engine.maps,'human',entity.id,'remove_influence',old)
    assert entity.location_id!=old and old not in {r['id'] for r in targets(game,engine.maps,'human',entity.id)}
    territory.ensure(game,engine.maps,'human');assert entity.id not in territory.snapshot(game,engine.maps,'human').get(old,{})
    assert ids==[n.id for n in entity.npcs] and player==(game.player.world,game.player.location_id) and assets==game.economy_v2.get('estates',{})
    engine.store.save(game);assert engine.get_game(game.id)['map']['current']==player[1]

def test_destroy_outpost_keeps_influence_and_exact_five_score(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    territory.ensure(game,engine.maps,'human').setdefault(loc,{})[entity.id]=dict(value=65.,outpost=True,policy='')
    peace(game,engine.maps,'human',entity.id,'destroy_outpost',loc)
    row=territory.snapshot(game,engine.maps,'human')[loc][entity.id];assert row['value']==65 and not row['outpost']
    from cultivation_life.system.war_system import WAR_TERM_DEFS
    assert WAR_TERM_DEFS['destroy_outpost'][1]==5

@pytest.mark.parametrize('world',['human','demon','spirit','true_demon','monster_realm','phantom_underworld','hell','celestial','asura','nether','reincarnation'])
def test_remote_sects_are_safe_bounded_and_distinct(world):
    definitions=[r for identity,r in FACTION_DEFINITIONS.items() if r['world']==world and identity.startswith('remote_')]
    assert len(definitions)==2 and len({r['location_id'] for r in definitions})==2

def test_base_relocation_with_dlc_disabled_uses_votes_and_retains_assets(scenario,monkeypatch):
    engine,game,entity=scenario;monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',False)
    destination=next(r['id'] for r in engine.maps.worlds['human']['locations'] if not r.get('min_realm_index',0) and r['id']!=entity.location_id)
    frozen=copy.deepcopy(game.intrigue_state['territory']);player=(game.player.world,game.player.location_id);engine.store.save(game)
    engine.organization_action(game.id,dict(kind='sect',owner_id=entity.id,action='relocate',location_id=destination))
    actual=engine.store.load(game.id)
    assert actual.sects[entity.id].location_id==destination and player==(actual.player.world,actual.player.location_id)
    assert actual.economy_v2['organization_sites']['votes'][-1]['passed']
    assert actual.intrigue_state['territory']==frozen

def test_initial_array_owner_does_not_change_with_new_or_extinct_sects(scenario):
    from cultivation_life.system.teleport_sites import arrays
    engine,game,entity=scenario
    original={loc:r['owner_id'] for loc,r in arrays(game,engine.maps,'human').items()}
    game.sects['aaa_new']=SectState(id='aaa_new',name='新宗',world='human',location_id='expanse_human_19')
    assert original=={loc:r['owner_id'] for loc,r in arrays(game,engine.maps,'human').items()}
    owner=next(identity for identity in original.values() if identity in game.sects)
    game.sects[owner].extinct=True
    for loc,row in arrays(game,engine.maps,'human').items():
        if original[loc]!=owner:assert row['owner_id']==original[loc]
        else:assert row['owner_id']=='human:array-keepers'

def test_political_actions_do_not_adopt_dormant_commodity_markets(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    markets=set(game.economy_v2['markets'])
    apply(game,engine.maps,entity,'expand_influence',loc,random.Random(1))
    apply(game,engine.maps,entity,'territory_policy',loc,random.Random(1),policy='conciliation')
    assert set(game.economy_v2['markets'])==markets

def test_territorial_array_shutdown_survives_dlc_toggle(scenario,monkeypatch):
    from cultivation_life.system.teleport_sites import arrays
    engine,game,entity=scenario
    loc,row=next((loc,row) for loc,row in arrays(game,engine.maps,'human').items() if not engine.maps.location('human',loc).get('min_realm_index',0))
    owner=row['owner_id']
    peace(game,engine.maps,'human',owner,'remove_influence',loc)
    assert loc not in arrays(game,engine.maps,'human')
    frozen=copy.deepcopy(game.intrigue_state['territory'])
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',False)
    assert loc not in arrays(game,engine.maps,'human') and game.intrigue_state['territory']==frozen
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',True)
    assert loc not in arrays(game,engine.maps,'human')

def test_zero_year_adoption_is_not_repeated(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    game.intrigue_state['territory']['adopted']['human']=0
    territory.ensure(game,engine.maps,'human').setdefault(loc,{})[entity.id]=dict(value=23.,outpost=False,policy='')
    territory.ensure(game,engine.maps,'human')
    assert territory.snapshot(game,engine.maps,'human')[loc][entity.id]['value']==23

def test_npc_families_do_not_receive_sect_territorial_claims(scenario):
    engine,game,entity=scenario
    family=next(s for s in game.sects.values() if s.kind=='family' and s.world=='human')
    book=territory.snapshot(game,engine.maps,'human')
    assert all(family.id not in rows for rows in book.values())
    with pytest.raises(ValueError,match='宗门'):territory.validate_projection(game,engine.maps,family,family.location_id)
    assert territory.resource_bonus(game,'human',family.id)==0

def test_fourth_faction_can_harass_from_its_border_without_occupying_a_slot(scenario):
    from unittest.mock import Mock
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    rivals=[game.sects[i] for i in ('tianjian','wanmo','puti')]
    book=territory.ensure(game,engine.maps,'human')
    book[loc]={s.id:dict(value=10.,outpost=False,policy='') for s in rivals}
    array_owner=territory.array_owners(game,engine.maps,'human').get(loc)
    rival=next(s for s in rivals if s.id!=array_owner and s.location_id!=loc)
    apply(game,engine.maps,entity,'territory_harass',loc,Mock(random=lambda:0.),target=rival.id)
    assert entity.id not in book[loc] and rival.id not in book[loc]
    assert len(book[loc])==2

def test_suppressed_player_cannot_duel_at_the_sealed_original_realm(scenario):
    from cultivation_life.system.territory.actions import participants
    engine,game,entity=scenario
    game.player.sealed_cultivation={'realm_index':4,'layer':9}
    game.player.realm_index=1
    assert max(participants(game,entity))[0]==1

def test_resource_bonus_is_relative_and_capped(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    rival=next(s for s in game.sects.values() if s.world=='human' and s.id!=entity.id)
    book=territory.ensure(game,engine.maps,'human');book.clear()
    book[loc]={entity.id:dict(value=100.,outpost=False,policy='')}
    assert territory.resource_bonus(game,'human',entity.id)==pytest.approx(.025)
    book[loc][rival.id]=dict(value=100.,outpost=False,policy='')
    assert territory.resource_bonus(game,'human',entity.id)==pytest.approx(.0125)
    for row in engine.maps.worlds['human']['locations']:
        if row['id']!=entity.location_id and not row.get('min_realm_index',0):book[row['id']]={entity.id:dict(value=100.,outpost=False,policy='')}
    assert territory.resource_bonus(game,'human',entity.id)==.2

def test_assigned_members_cannot_participate_in_duels_or_migration(scenario):
    from cultivation_life.system.territory.actions import participants
    from cultivation_life.system.organization_relocation import candidates
    engine,game,entity=scenario
    npc=entity.npcs[0];npc.realm_index=4;npc.world=entity.world
    game.heavens_state={'runtime':{'mirror':{'survey':dict(status='active',person_id=npc.id)}}}
    assert npc.id not in {n.id for n in candidates(game,'sect',entity.id,entity.world)}
    game.player.alive=False
    assert max(participants(game,entity),default=(-1,0))[0]<4

def test_busy_submission_does_not_write_save(scenario):
    engine,game,entity=scenario;loc=frontier(engine,game,entity)
    game.pending_event=engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1));engine.store.save(game)
    engine._load(game.id)
    before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):engine.organization_action(game.id,dict(kind='sect',owner_id=entity.id,action='expand_influence',location_id=loc))
    assert engine.store._path(game.id).read_bytes()==before

def test_actual_war_peace_demands_exactly_five_points(scenario):
    engine,game,entity=scenario
    rival=game.sects['wanmo'];loc=rival.location_id
    for n in rival.npcs:n.realm_index=1
    territory.ensure(game,engine.maps,'human')[loc][rival.id]['outpost']=True
    war=engine._start_war(game,'sect',entity.id,rival.id,initiated_by_player=True)
    war.update(war_score=4,battles=2,controller='player');engine.store.save(game)
    game=engine._load(game.id);war=next(w for w in game.wars if w['id']==war['id'])
    before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='需要 5'):engine.war_peace(game.id,war['id'],'destroy_outpost',target_id=loc)
    assert engine.store._path(game.id).read_bytes()==before
    war['war_score']=5;engine.store.save(game)
    engine.war_peace(game.id,war['id'],'destroy_outpost',target_id=loc)
    actual=engine.store.load(game.id)
    assert next(w for w in actual.wars if w['id']==war['id'])['status']=='ended'
    assert not territory.snapshot(actual,engine.maps,'human')[loc][rival.id]['outpost']

@pytest.mark.parametrize('dlc',[False,True])
def test_actual_family_relocation_uses_original_family(scenario,monkeypatch,dlc):
    engine,game,entity=scenario;monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',dlc)
    game.sects.pop(entity.id);entity.kind='family';game.family=entity
    destination=next(r['id'] for r in engine.maps.worlds['human']['locations'] if not r.get('min_realm_index',0) and r['id']!=entity.location_id)
    engine.store.save(game);roster=[n.id for n in entity.npcs]
    engine.organization_action(game.id,dict(kind='family',owner_id=entity.id,action='relocate',location_id=destination))
    actual=engine.store.load(game.id)
    assert actual.family.location_id==destination and roster==[n.id for n in actual.family.npcs]

@pytest.mark.parametrize('dlc',[False,True])
def test_actual_race_relocation_is_local_and_does_not_collect_scattered_people(tmp_path,monkeypatch,dlc):
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',dlc)
    engine=GameEngine(ROOT,tmp_path)
    game=engine._load(engine.create_game('族议','supreme_earth','dao',2111,custom_start=dict(world='spirit',realm_index=8,sect='new',sect_name='族议宗'))['id'])
    game.pending_event=None;game.active_trial=None
    for npc in engine._all_world_npcs(game):npc.realm_index=min(npc.realm_index,7)
    current=race_site(game,engine.maps,'spirit','human')
    destination=next(r['id'] for r in engine.maps.worlds['spirit']['locations'] if not r.get('min_realm_index',0) and r['id']!=current)
    engine.store.save(game);game=engine._load(game.id)
    before={n.id:(n.world,n.location_id) for s in game.sects.values() for n in s.npcs}
    monkeypatch.setattr(random.Random,'random',lambda self:0.)
    engine.organization_action(game.id,dict(kind='race',owner_id='human',action='relocate',location_id=destination))
    actual=engine.store.load(game.id)
    assert race_site(actual,engine.maps,'spirit','human')==destination
    assert before=={n.id:(n.world,n.location_id) for s in actual.sects.values() for n in s.npcs}
