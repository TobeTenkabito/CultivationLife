"""Real appointments, finite public cargo, local work and canonical officers."""
import copy
import random
from fractions import Fraction
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_earth_network import travel,choose
from cultivation_life.models import SectNpc
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.court_bureau_rules import state,active,personal,HOME,COURT
from cultivation_life.system.court_bureaus import public
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.system.economy.state import local_market,ensure_regional_market
from cultivation_life.person_assignments import research_assignment,require_unassigned

@pytest.fixture
def bureau(prepared):
    e,g,_=prepared;g.player.location_id=HOME
    g.settings.update(silent_events=True,combat_popup=False,court_election_popup=False)
    transfer_value(g,'background:celestial',COURT,10**11,'验收公务预算')
    e.store.save(g);e.get_game(g.id)
    return e,g.id

def cmd(e,gid,name,target=''):
    d=e.get_game(gid)['heavenly_court']['bureaus']
    return e.yaochi_action(gid,'bureau_'+name,d['token']+('|' +target if target else ''))

def offer(e,gid,person='player',index=0):
    d=e.get_game(gid)['heavenly_court']['bureaus'];row=d['offers'][index]
    cmd(e,gid,'accept',row['token']+'~'+person)
    return active(e._load(gid))[-1]

def work(e,gid):
    with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):return cmd(e,gid,'work')

def patrol(e,gid,index=0):
    job=offer(e,gid,index=index);travel(e,gid,job['location']);work(e,gid);cmd(e,gid,'claim',job['id'])
    travel(e,gid,HOME);return job

def officers(e,gid):
    g=e._load(gid)
    for i in range(3):
        n=SectNpc('bureau-officer-'+str(i),'验收天官'+str(i),'天官',9,1,50,100000,world='celestial',location_id=HOME)
        g.world_npcs[n.id]=n;g.heavenly_court['officials'][n.id]=dict(id=n.id,name=n.name,grade=8,support=50,source='npc',faction_id=None)
    g.heavenly_court['player_grade']=7;e.store.save(g)
    return ['bureau-officer-'+str(i) for i in range(3)]

def supervisor(e,gid,office='patrol'):
    # Appointment tests separately earn the two completions through actual travel/work.
    cmd(e,gid,'join',office);ids=officers(e,gid);g=e._load(gid)
    state(g).setdefault('completed',{})[office]=2;e.store.save(g);cmd(e,gid,'promote')
    for identity in ids[:2]:cmd(e,gid,'appoint',identity)
    return ids

def advance(e,gid,years):
    g=e._load(gid);rng=random.Random(4)
    for _ in range(years):
        g.player.age+=1;e._advance_world_year(g,rng,[],encounters=False)
    e.store.save(g)

def test_four_appointments_readonly_qualification_and_real_promotion(bureau):
    e,gid=bureau;g=e._load(gid);snap=copy.deepcopy(g.to_dict());public(g,e.maps);assert g.to_dict()==snap
    cmd(e,gid,'join','patrol')
    with pytest.raises(ValueError,match='七品'):cmd(e,gid,'promote')
    officers(e,gid)
    with pytest.raises(ValueError,match='两项'):cmd(e,gid,'promote')
    patrol(e,gid,0);patrol(e,gid,1);cmd(e,gid,'promote')
    g=e._load(gid);assert state(g)['heads']['patrol']=='player' and state(g)['completed']['patrol']==2
    for office in ('land','works','audit'):
        cmd(e,gid,'join',office);assert state(e._load(gid))['office']==office
    assert e._load(gid).heavenly_court['player_grade']==7

def test_funded_patrol_requires_actual_road_work_and_one_reward(bureau):
    e,gid=bureau;cmd(e,gid,'join','patrol');job=offer(e,gid)
    with pytest.raises(ValueError,match='亲临'):work(e,gid)
    with pytest.raises(ValueError,match='交接'):cmd(e,gid,'join','land')
    travel(e,gid,job['location']);g=e._load(gid);before=g.heavenly_court['player_merit'];xp=g.player.opportunity
    work(e,gid);cmd(e,gid,'claim',job['id']);g=e._load(gid)
    assert g.heavenly_court['player_merit']==before+1 and Fraction(state(g)['merit_remainder'])==Fraction(1,5)
    assert g.player.opportunity==xp and not active(g)
    row=state(g)['jobs'][-1];r=row['receipt'];assert r['reserved']==sum(r[k] for k in ('purchase','labor','engineering','refunded'))
    with pytest.raises(ValueError):cmd(e,gid,'claim',job['id'])

def test_staff_canonical_occupancy_roundtrip_review_and_reward_split(bureau):
    e,gid=bureau;ids=supervisor(e,gid);job=offer(e,gid,ids[0]);g=e._load(gid)
    assert research_assignment(g,ids[0])['id']==job['id']
    with pytest.raises(ValueError):require_unassigned(g,ids[0])
    with pytest.raises(ValueError,match='占用'):offer(e,gid,ids[0],1)
    with pytest.raises(ValueError,match='两席'):cmd(e,gid,'appoint',ids[2])
    advance(e,gid,job['leg']['years']+job['years'])
    g=e._load(gid);assert g.world_npcs[ids[0]].location_id==job['location'] and active(g)[0]['phase']=='ready'
    travel(e,gid,job['location']);before=e._load(gid).heavenly_court['player_merit']
    with pytest.raises(ValueError,match='复核'):cmd(e,gid,'claim',job['id'])
    cmd(e,gid,'review',job['id']);work(e,gid);cmd(e,gid,'claim',job['id'])
    g=e._load(gid);assert g.heavenly_court['player_merit']==before
    assert Fraction(state(g)['merit_remainder'])==Fraction(3,25)
    assert Fraction(g.heavenly_court['officials'][ids[0]]['service_merit'])==Fraction(27,25)
    return_years=active(g)[0]['leg']['years'];advance(e,gid,return_years);travel(e,gid,HOME)
    cmd(e,gid,'handover',job['id']);g=e._load(gid)
    assert not research_assignment(g,ids[0]) and g.world_npcs[ids[0]].location_id==HOME
    cmd(e,gid,'join','land');assert not state(e._load(gid))['staff']

def test_cancel_refunds_only_unspent_and_does_not_reroll(bureau):
    e,gid=bureau;cmd(e,gid,'join','patrol');job=offer(e,gid);g=e._load(gid)
    original=balance(g,COURT);cmd(e,gid,'handover',job['id']);g=e._load(gid)
    assert balance(g,COURT)==original+job['budget'] and not active(g)
    with pytest.raises(ValueError,match='本期已承接'):offer(e,gid)
    cmd(e,gid,'leave')
    with pytest.raises(ValueError,match='销假'):offer(e,gid,index=1)

def test_procurement_real_cargo_delivery_and_stale_budget(bureau):
    e,gid=bureau;cmd(e,gid,'join','works');g=e._load(gid)
    dest=next(r['to'] if r['from']==HOME else r['from'] for r in e.maps.worlds['celestial']['routes'] if HOME in (r['from'],r['to']))
    ensure_regional_market(g,e.maps,'celestial',dest)
    source=local_market(g);other=g.economy_v2['markets']['celestial:'+dest]
    key=next(k for k,r in source['commodities'].items() if r['stock']>=20 and r['tier']==9)
    other['commodities'][key]['stock']=0;e.store.save(g)
    d=e.get_game(gid)['heavenly_court']['bureaus'];row=next(o for o in d['offers'] if o['location']==dest)
    token=d['token']+'|'+row['token']+'~player';g=e._load(gid);g.heavenly_court['treasury']-=1;e.store.save(g)
    with pytest.raises(ValueError,match='变化'):e.yaochi_action(gid,'bureau_accept',token)
    index=next(i for i,o in enumerate(e.get_game(gid)['heavenly_court']['bureaus']['offers']) if o['location']==dest)
    job=offer(e,gid,index=index);g=e._load(gid);assert job['cargo']==job['offer']['materials'] and job['purchase']>0
    travel(e,gid,dest);work(e,gid);g=e._load(gid);market=local_market(g)
    item=job['offer']['item'];stock=market['commodities'][item]['stock'];cash=balance(g,'player')
    cmd(e,gid,'claim',job['id']);g=e._load(gid)
    assert local_market(g)['commodities'][item]['stock']==stock+job['cargo'][item] and balance(g,'player')==cash
    assert not state(g)['jobs'][-1]['cargo']

def test_original_public_city_rebuild_paid_by_treasury_not_player(bureau):
    from cultivation_life.system.building_assets import local_rows
    from cultivation_life.system.building_destruction import destroy
    from cultivation_life.system.building_projects import quote
    e,gid=bureau;cmd(e,gid,'join','land');g=e._load(gid)
    row=next(r for r in local_rows(g) if r['type']=='city' and r.get('public'))
    # Seed a disaster-damaged public city; reconstruction keeps real permissions/costs.
    with patch('cultivation_life.system.building_projects.demolition_reason',return_value=''):destroy(g,row)
    row=g.building_state['records'][row['id']];bill=quote(g,'rebuild',row)
    for item,n in bill['materials'].items():local_market(g)['commodities'][item]['stock']=n+100
    e.store.save(g);job=offer(e,gid);work(e,gid);g=e._load(gid);cash=balance(g,'player');cmd(e,gid,'claim',job['id']);g=e._load(gid)
    assert g.building_state['records'][row['id']]['status']=='intact' and balance(g,'player')==cash
    assert state(g)['jobs'][-1]['receipt']['engineering']==bill['coins']

def test_audit_original_receipt_once_without_invented_guilt(bureau):
    e,gid=bureau;cmd(e,gid,'join','patrol');job=offer(e,gid);cmd(e,gid,'handover',job['id'])
    cmd(e,gid,'join','audit');audit=offer(e,gid);work(e,gid);cmd(e,gid,'claim',audit['id'])
    g=e._load(gid);assert state(g)['jobs'][0]['audited']['difference']==0
    assert not e.get_game(gid)['heavenly_court']['bureaus']['offers']

def test_interrupted_personal_work_followup_and_disabled_recovery(bureau):
    e,gid=bureau;cmd(e,gid,'join','patrol');job=offer(e,gid);travel(e,gid,job['location'])
    age=e._load(gid).player.age;annual=e._advance_world_year
    def stop(g,rng,news,**kw):
        result=annual(g,rng,news,**kw)
        if g.player.age==age+2:
            g.pending_event=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],g,random.Random(1));return False
        return result
    with patch.object(e,'_advance_world_year',side_effect=stop):work(e,gid)
    assert personal(e._load(gid))['progress']==2
    with pytest.raises(ValueError,match='事件'):cmd(e,gid,'handover',job['id'])
    choose(e,gid,'acknowledge');travel(e,gid,HOME)
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):cmd(e,gid,'handover',job['id'])
    assert not active(e._load(gid))

def test_staff_frozen_foreign_world_keeps_original_person_and_escrow(bureau):
    from cultivation_life.system.court_bureau_runtime import year_step
    e,gid=bureau;ids=supervisor(e,gid);job=offer(e,gid,ids[0]);g=e._load(gid)
    original=copy.deepcopy(active(g));wallet=balance(g,job['wallet'])
    plan=e._plan_world_transition(g,'spirit','sealed_descent',reason='属员原界归属验收');e._apply_world_transition(g,plan)
    g.player.age+=1;year_step(g,e.maps)
    assert active(g)==original and balance(g,job['wallet'])==wallet and g.world_npcs[ids[0]].world=='celestial'

def test_officer_stale_quote_cultivation_lock_and_recall_keeps_elapsed(bureau):
    from cultivation_life.system.npc_development.service import quote as training_quote
    e,gid=bureau;ids=supervisor(e,gid)
    g=e._load(gid);g.player.disciples.append(g.link_relationship({'id':ids[0]}));e.store.save(g)
    d=e.get_game(gid)['heavenly_court']['bureaus'];offer_row=d['offers'][0]
    old=d['token']+'|'+offer_row['token']+'~'+ids[0]
    g=e._load(gid);g.world_npcs[ids[0]].layer=2;e.store.save(g);before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='变化'):e.yaochi_action(gid,'bureau_accept',old)
    assert e.store._path(gid).read_bytes()==before
    job=offer(e,gid,ids[0]);g=e._load(gid)
    with pytest.raises(ValueError,match='无法接触'):training_quote(g,'npc',ids[0],'cultivation')
    advance(e,gid,2);paid=active(e._load(gid))[0]['spent'];cmd(e,gid,'recall',job['id'])
    assert active(e._load(gid))[0]['phase']=='handover'
    with pytest.raises(ValueError,match='不可重置'):cmd(e,gid,'recall',job['id'])
    cmd(e,gid,'handover',job['id']);g=e._load(gid)
    assert state(g)['jobs'][-1]['receipt']['labor']==paid==2000
    assert not research_assignment(g,ids[0])

def test_unfunded_offer_and_remote_recovery_do_not_write_save(bureau):
    e,gid=bureau;cmd(e,gid,'join','patrol');g=e._load(gid)
    transfer_value(g,COURT,'background:celestial',balance(g,COURT),'验收府库耗尽');e.store.save(g)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='府库不足'):offer(e,gid)
    assert e.store._path(gid).read_bytes()==before and not active(e._load(gid))


def test_missing_officer_keeps_original_custody_site(bureau):
    e,gid=bureau;ids=supervisor(e,gid);job=offer(e,gid,ids[0])
    advance(e,gid,job['leg']['years']+job['years'])
    g=e._load(gid);assert active(g)[0]['phase']=='ready'
    g.world_npcs.pop(ids[0]);e.store.save(g)
    data=e.get_game(gid)['heavenly_court']['bureaus']
    before=e.store._path(gid).read_bytes()
    assert public(e._load(gid),e.maps)['jobs'][0]['handover_reason']
    with pytest.raises(ValueError,match='保管地点'):e.yaochi_action(gid,'bureau_handover',data['token']+'|'+job['id'])
    assert e.store._path(gid).read_bytes()==before
    travel(e,gid,job['location']);cmd(e,gid,'handover',job['id'])
    g=e._load(gid);assert not active(g) and state(g)['jobs'][-1]['receipt']['location']==job['location']


def test_officer_excludes_recorded_instance_years(bureau):
    from cultivation_life.engine.world import regions
    from cultivation_life.regional_context import CalendarGame
    from cultivation_life.system.court_bureau_runtime import year_step
    e,gid=bureau;ids=supervisor(e,gid);job=offer(e,gid,ids[0]);g=e._load(gid)
    regions.ensure(e._dependencies.regions,g)
    first=g.player.age+1;g.player.age=first+3
    g.world_simulation['space_years']=[[first,first+2]]
    original=copy.deepcopy(active(g));cash=balance(g,job['wallet'])
    for year in range(first,first+3):year_step(CalendarGame(g,'celestial',year),e.maps)
    assert active(g)==original and balance(g,job['wallet'])==cash
    year_step(CalendarGame(g,'celestial',first+3),e.maps)
    assert active(g)[0]['leg']['progress']==1 and balance(g,job['wallet'])==cash-1000
