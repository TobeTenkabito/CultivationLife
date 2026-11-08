"""Actual court commands over original evidence, people, roads and combat."""
import copy
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_court_bureaus import bureau,cmd,work,officers,supervisor,advance
from test_earth_network import travel
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.court_bureau_rules import state,active,HOME,COURT
from cultivation_life.system.court_case_facts import leads
from cultivation_life.system.court_inspection import active as inquiry
from cultivation_life.system.court_enforcement import offers as patrol_offers
from cultivation_life.system.economy.state import local_market,ensure_regional_market
from cultivation_life.system.economy.ledger import balance
from cultivation_life.person_assignments import research_assignment

def take(e,gid,operation,person='player'):
    row=next(r for r in e.get_game(gid)['heavenly_court']['bureaus']['offers'] if r.get('operation')==operation)
    cmd(e,gid,'accept',row['token']+'~'+person)
    return active(e._load(gid))[-1]

def named(e,gid,identity='wanted',*,wounds=0):
    g=e._load(gid);npc=SectNpc(identity,'原巡天目标','散修',9 if wounds else 1,1,25,100000,world='celestial',location_id=HOME,wounds=wounds)
    g.world_npcs[npc.id]=npc
    if identity=='wanted':g.heavenly_court['wanted_ids'].append(npc.id)
    e.store.save(g);return npc.id

def conflict(e,gid):
    ids=supervisor(e,gid,'audit')
    cmd(e,gid,'release',ids[0]);g=e._load(gid);g.player.disciples.append(g.link_relationship({'id':ids[0]}));e.store.save(g)
    cmd(e,gid,'appoint',ids[0]);row=leads(e._load(gid))[0];cmd(e,gid,'case_open',row['token'])
    return inquiry(e._load(gid))['id'],ids

def investigate(e,gid,identity):
    c=inquiry(e._load(gid))
    for step in ('accounts','hearing','site'):
        dest=c['location'] if step=='site' else HOME
        if e._load(gid).player.location_id!=dest:travel(e,gid,dest)
        cmd(e,gid,'case_step',identity+'~'+step);work(e,gid)
    if e._load(gid).player.location_id!=HOME:travel(e,gid,HOME)
    cmd(e,gid,'case_defend',identity+'~acknowledge')

def review(e,gid,identity,npc,verdict):
    cmd(e,gid,'case_propose',identity+'~'+verdict)
    cmd(e,gid,'case_reviewer',identity+'~'+npc);work(e,gid)

def diverted(e,gid):
    cmd(e,gid,'join','works');g=e._load(gid)
    dest=next(r['to'] if r['from']==HOME else r['from'] for r in e.maps.worlds['celestial']['routes'] if HOME in (r['from'],r['to']))
    ensure_regional_market(g,e.maps,'celestial',dest);market=local_market(g)
    key=next(k for k,r in market['commodities'].items() if r['tier']==9 and r['stock']>=20)
    for k,r in g.economy_v2['markets']['celestial:'+dest]['commodities'].items():r['stock']=r['target']
    g.economy_v2['markets']['celestial:'+dest]['commodities'][key]['stock']=0
    market['commodities'][key]['stock']=20;e.store.save(g)
    row=next(r for r in e.get_game(gid)['heavenly_court']['bureaus']['offers'] if r['location']==dest)
    cmd(e,gid,'accept',row['token']+'~player');j=active(e._load(gid))[0]
    cmd(e,gid,'divert',j['id']);cmd(e,gid,'handover',j['id']);cmd(e,gid,'join','audit')
    row=next(r for r in leads(e._load(gid)) if r['kind']=='procurement');cmd(e,gid,'case_open',row['token'])
    return inquiry(e._load(gid))['id'],j

def test_conflict_evidence_independent_review_and_actual_recusal(bureau):
    e,gid=bureau;identity,ids=conflict(e,gid)
    with pytest.raises(ValueError,match='三步'):cmd(e,gid,'case_propose',identity+'~recuse')
    investigate(e,gid,identity);cmd(e,gid,'case_propose',identity+'~recuse')
    with pytest.raises(ValueError,match='独立'):cmd(e,gid,'case_reviewer',identity+'~'+ids[0])
    with pytest.raises(ValueError,match='直属'):cmd(e,gid,'case_reviewer',identity+'~'+ids[1])
    cmd(e,gid,'case_reviewer',identity+'~'+ids[2]);assert research_assignment(e._load(gid),ids[2])
    work(e,gid);cmd(e,gid,'case_execute',identity);g=e._load(gid)
    assert ids[0] not in state(g)['staff'] and ids[0] in g.world_npcs
    assert not research_assignment(g,ids[2]) and g.heavenly_court['player_grade']==7
    assert state(g)['inquiries'][-1]['spent']==20000

def test_procurement_actual_diversion_compensation_and_no_self_award(bureau):
    e,gid=bureau;ids=officers(e,gid);identity,j=diverted(e,gid);g=e._load(gid)
    assert not state(g)['jobs'][0]['cargo'] and state(g)['jobs'][0]['diversion']['goods']==j['offer']['materials']
    before=g.heavenly_court['player_merit'];investigate(e,gid,identity)
    with pytest.raises(ValueError,match='补交'):cmd(e,gid,'case_propose',identity+'~remedy')
    travel(e,gid,j['location']);g=e._load(gid)
    for key,n in j['offer']['materials'].items():add_item(g.player,key,n)
    e.store.save(g);cmd(e,gid,'case_restitution',identity)
    with pytest.raises(ValueError,match='没有来源'):cmd(e,gid,'case_restitution',identity)
    travel(e,gid,HOME);review(e,gid,identity,ids[0],'remedy');cmd(e,gid,'case_execute',identity);g=e._load(gid)
    assert state(g)['jobs'][0]['restitution']==j['offer']['materials'] and g.heavenly_court['player_merit']==before

def test_neglect_suspension_real_qualification_and_appeal_different_reviewer(bureau):
    e,gid=bureau;cmd(e,gid,'join','patrol');j=take(e,gid,None)
    g=e._load(gid);g.player.age=j['deadline'];e.store.save(g);cmd(e,gid,'handover',j['id']);cmd(e,gid,'join','audit')
    lead=next(r for r in leads(e._load(gid)) if r['kind']=='neglect');cmd(e,gid,'case_open',lead['token']);identity=inquiry(e._load(gid))['id']
    investigate(e,gid,identity);ids=officers(e,gid);review(e,gid,identity,ids[0],'suspend');cmd(e,gid,'case_execute',identity)
    assert state(e._load(gid))['restrictions']['player']['until']>e._load(gid).player.age
    with pytest.raises(ValueError,match='监察'):cmd(e,gid,'promote')
    cmd(e,gid,'case_appeal',identity);cmd(e,gid,'case_propose',identity+'~suspend')
    with pytest.raises(ValueError,match='独立'):cmd(e,gid,'case_reviewer',identity+'~'+ids[0])
    cmd(e,gid,'case_reviewer',identity+'~'+ids[1]);work(e,gid);cmd(e,gid,'case_execute',identity)
    with pytest.raises(ValueError,match='一次'):cmd(e,gid,'case_appeal',identity)

def test_inquiry_pause_disable_resume_keeps_work_and_escrow(bureau):
    e,gid=bureau;identity,ids=conflict(e,gid);cmd(e,gid,'case_step',identity+'~accounts')
    g=e._load(gid);c=inquiry(g);c['work']['progress']=2;c['spent']=2000
    from cultivation_life.system.economy.ledger import transfer_value
    transfer_value(g,c['wallet'],'background:celestial',2000,'验收已做两年');e.store.save(g)
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):cmd(e,gid,'case_cancel',identity)
    g=e._load(gid);c=state(g)['inquiries'][0];assert c['work']['progress']==2 and balance(g,c['wallet'])==0
    with pytest.raises(ValueError,match='续查'):cmd(e,gid,'case_appeal',identity)
    cmd(e,gid,'case_resume',identity);work(e,gid);g=e._load(gid)
    assert inquiry(g)['spent']==5000 and 'accounts' in inquiry(g)['evidence']
    c=inquiry(g);assert c['funded']==c['spent']+c['refunded_total']+balance(g,c['wallet'])

def test_warrant_revoked_and_remote_target_atomic_refusal(bureau):
    e,gid=bureau;named(e,gid);cmd(e,gid,'join','patrol');j=take(e,gid,'bounty');work(e,gid)
    g=e._load(gid);g.heavenly_court['wanted_ids'].remove('wanted');e.store.save(g)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='撤销'):cmd(e,gid,'fight',j['id']+'~kill')
    assert e.store._path(gid).read_bytes()==before and e._load(gid).world_npcs['wanted'].alive

def test_actual_player_bounty_combat_and_no_repeat(bureau):
    e,gid=bureau;named(e,gid);cmd(e,gid,'join','patrol');j=take(e,gid,'bounty');work(e,gid)
    cmd(e,gid,'fight',j['id']+'~repel');g=e._load(gid)
    assert active(g)[0]['operation_done'] and g.world_npcs['wanted'].alive and g.last_combat_report
    with pytest.raises(ValueError,match='再次'):cmd(e,gid,'fight',j['id']+'~kill')
    cmd(e,gid,'claim',j['id']);assert not active(e._load(gid))
    assert not any(o.get('operation')=='bounty' for o in e.get_game(gid)['heavenly_court']['bureaus']['offers'])

def test_actual_npc_bounty_combat_preserves_canonical_actor(bureau):
    e,gid=bureau;ids=supervisor(e,gid);named(e,gid);j=take(e,gid,'bounty',ids[0]);advance(e,gid,5)
    cmd(e,gid,'fight',j['id']+'~kill');g=e._load(gid)
    assert active(g)[0]['operation_done'] and not g.world_npcs['wanted'].alive
    assert g.world_npcs[ids[0]].alive and research_assignment(g,ids[0])
    cmd(e,gid,'review',j['id']);work(e,gid);cmd(e,gid,'claim',j['id']);cmd(e,gid,'handover',j['id'])
    assert not research_assignment(e._load(gid),ids[0])

def test_rescue_real_patient_medicine_route_and_handover(bureau):
    e,gid=bureau;n=named(e,gid,'patient',wounds=4);cmd(e,gid,'join','patrol');j=take(e,gid,'rescue')
    g=e._load(gid);assert research_assignment(g,n) and j['cargo']
    work(e,gid);before=e._load(gid).world_npcs[n].wounds;cmd(e,gid,'evacuate',j['id']);g=e._load(gid)
    assert g.world_npcs[n].wounds==max(0,before-1) and g.world_npcs[n].location_id==HOME
    with pytest.raises(ValueError,match='转运'):cmd(e,gid,'handover',j['id'])
    dest=active(g)[0]['evacuation']['destination'];travel(e,gid,dest)
    # Player travel and casualty transport each consume their original real route.
    g=e._load(gid);assert g.world_npcs[n].location_id==dest and active(g)[0]['operation_done']
    cmd(e,gid,'claim',j['id']);g=e._load(gid)
    assert not active(g) and not research_assignment(g,n) and g.world_npcs[n].id==n

def test_inspection_and_patrol_views_are_readonly(bureau):
    from cultivation_life.system.court_bureaus import public
    e,gid=bureau;named(e,gid,'patient',wounds=4);g=e._load(gid);before=copy.deepcopy(g.to_dict())
    public(g,e.maps);patrol_offers(g,e.maps);assert g.to_dict()==before

@pytest.mark.parametrize('paused',[False,True])
def test_failed_reviewer_handover_preserves_evidence_and_no_false_testimony(bureau,paused):
    from cultivation_life.npc_custody import kill_person
    from cultivation_life.system.court_bureaus import public
    e,gid=bureau;identity,ids=conflict(e,gid);investigate(e,gid,identity)
    cmd(e,gid,'case_propose',identity+'~recuse');cmd(e,gid,'case_reviewer',identity+'~'+ids[2])
    g=e._load(gid);before=copy.deepcopy(g.to_dict());public(g,e.maps);assert g.to_dict()==before
    if paused:cmd(e,gid,'case_cancel',identity);g=e._load(gid)
    kill_person(g,ids[2],'验收原人物陨落');e.store.save(g)
    if paused:cmd(e,gid,'case_resume',identity)
    else:
        with pytest.raises(ValueError,match='原人物'):work(e,gid)
        cmd(e,gid,'case_reassign',identity)
    g=e._load(gid)
    assert inquiry(g)['stage']=='decision' and len(inquiry(g)['evidence'])==3 and not research_assignment(g,ids[2])
    assert inquiry(g)['evidence']['hearing']['attendance']=='实际到场'
    assert not inquiry(g).get('result')

def test_dead_patient_can_close_failed_evacuation_without_teleport_or_reward(bureau):
    from cultivation_life.npc_custody import kill_person
    e,gid=bureau;n=named(e,gid,'patient',wounds=4);cmd(e,gid,'join','patrol');j=take(e,gid,'rescue');work(e,gid);cmd(e,gid,'evacuate',j['id'])
    advance(e,gid,2);g=e._load(gid);spent=active(g)[0]['spent'];merit=g.heavenly_court['player_merit']
    kill_person(g,n,'验收救援途中陨落');e.store.save(g)
    cmd(e,gid,'abort_rescue',j['id']);cmd(e,gid,'handover',j['id']);g=e._load(gid)
    from cultivation_life.relationship_records import find_person
    assert not find_person(g,n).alive and find_person(g,n).location_id==HOME
    assert not active(g) and state(g)['jobs'][-1]['receipt']['labor']==spent and g.heavenly_court['player_merit']==merit

def test_rescue_crossworld_and_instance_years_preserve_original_escrow(bureau):
    from cultivation_life.system.court_bureau_runtime import year_step
    from cultivation_life.engine.world import regions
    from cultivation_life.regional_context import CalendarGame
    e,gid=bureau;n=named(e,gid,'patient',wounds=4);cmd(e,gid,'join','patrol');j=take(e,gid,'rescue');work(e,gid);cmd(e,gid,'evacuate',j['id'])
    g=e._load(gid);original=copy.deepcopy(active(g));cash=balance(g,j['wallet'])
    plan=e._plan_world_transition(g,'spirit','sealed_descent',reason='救援归属验收');e._apply_world_transition(g,plan)
    g.player.age+=1;year_step(g,e.maps)
    assert active(g)==original and balance(g,j['wallet'])==cash and g.world_npcs[n].world=='celestial'
    regions.ensure(e._dependencies.regions,g);year=g.player.age+1;g.world_simulation['space_years']=[[year,year]]
    year_step(CalendarGame(g,'celestial',year),e.maps)
    assert active(g)==original and balance(g,j['wallet'])==cash

def test_dead_escort_releases_original_patient_after_failed_handover(bureau):
    from cultivation_life.npc_custody import kill_person
    from cultivation_life.relationship_records import find_person
    e,gid=bureau;ids=supervisor(e,gid);n=named(e,gid,'patient',wounds=4)
    j=take(e,gid,'rescue',ids[0]);advance(e,gid,1);cmd(e,gid,'evacuate',j['id'])
    with pytest.raises(ValueError,match='仍可继续'):cmd(e,gid,'abort_rescue',j['id'])
    g=e._load(gid);merit=g.heavenly_court['player_merit'];kill_person(g,ids[0],'验收护送属员途中陨落');e.store.save(g)
    advance(e,gid,1);g=e._load(gid);assert active(g)[0]['blocked'] and active(g)[0]['evacuation']['progress']==0
    cmd(e,gid,'abort_rescue',j['id']);cmd(e,gid,'handover',j['id']);g=e._load(gid)
    assert find_person(g,n).alive and find_person(g,n).location_id==HOME and not find_person(g,ids[0]).alive
    assert not active(g) and not research_assignment(g,n) and not research_assignment(g,ids[0])
    assert g.heavenly_court['player_merit']==merit

def test_paused_review_cannot_reopen_via_appeal_or_disclose_foreign_cases(bureau):
    from cultivation_life.system.court_inspection import public
    e,gid=bureau;identity,ids=conflict(e,gid);investigate(e,gid,identity);review(e,gid,identity,ids[2],'recuse')
    cmd(e,gid,'case_cancel',identity)
    with pytest.raises(ValueError,match='续查'):cmd(e,gid,'case_appeal',identity)
    g=e._load(gid);assert state(g)['inquiries'][0]['status']=='paused'
    plan=e._plan_world_transition(g,'spirit','sealed_descent',reason='原监察案远界信息验收');e._apply_world_transition(g,plan)
    shown=public(g,e.maps);assert not shown['cases'] and not shown['leads'] and shown['notice']
