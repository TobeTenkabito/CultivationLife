"""Actual command/travel/advance pipelines and conserved public delivery."""
import copy
import random
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_yaochi_westward import pool
from test_earth_temple import village,build,fulfill
from test_earth_network import travel
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from cultivation_life.economy_content import material_id
from cultivation_life.system import yaochi_antiquity as ancient,court_projects as council
from cultivation_life.system.court_project_offers import offers
from cultivation_life.system.court_bureau_rules import COURT
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.system.economy.state import ensure_regional_market,local_market,reprice
from cultivation_life.person_assignments import research_assignment

def test_original_high_influence_ballot_has_no_new_probability_cap():
    from cultivation_life.system.court.ballots import player_ballot
    class Roll:
        def random(self):return .99
    result=player_ballot(dict(player_support=100),['player','original-star'],Roll(),.35)
    assert result['yes']==2 and result['passed']

def cmd(e,gid,action,value=''):
    d=e.get_game(gid)
    shown=d['yaochi']['antiquity'] if action.startswith('antiquity_') else d['heavenly_court']['projects']
    if action=='council_vote' and not value:value=(shown.get('vote_offer') or {}).get('token','')
    return e.yaochi_action(gid,action,shown['token']+'|'+value)

def work(e,gid,kind):
    with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):return cmd(e,gid,kind+'_work')

def seats(e,gid,extra=False):
    g=e._load(gid);c=g.heavenly_court;c['open_election']=None;c['queued_elections']=[]
    for k in c['offices']:c['offices'][k]=None
    key=next(iter(c['offices']));c['offices'][key]=dict(holder_id='player',holder_name=g.player.name,start_unit=c['unit'],end_unit=c['unit']+100)
    c['officials']['player']=dict(id='player',source='player',name=g.player.name,grade=1)
    if extra:
        for i,key in enumerate(list(c['offices'])[1:3]):
            ident='project-seat-'+str(i);c['officials'][ident]=dict(id=ident,source='court_pool',name='原机构代表'+str(i),grade=1)
            c['offices'][key]=dict(holder_id=ident,holder_name='原机构代表'+str(i),start_unit=c['unit'],end_unit=c['unit']+100)
    add_item(g.player,'spirit_stone',10**10)
    transfer_value(g,'player',COURT,10**10,'验收个人实付项目原款')
    e.store.save(g)

def npc(e,gid,identity='public-scholar'):
    g=e._load(gid);n=SectNpc(identity,'来访修士','散修',9,1,40,100000,spirit_root='supreme_metal',world='celestial',location_id=g.player.location_id)
    g.world_npcs[n.id]=n;e.store.save(g);return identity

def training_offer(e,gid):
    npc(e,gid);g=e._load(gid);market=local_market(g)
    key='npc_training_dao_cultivation_3';market['commodities'][key]['stock']=20;reprice(g,market,market['commodities'][key]);e.store.save(g)
    return next(o for o in offers(e._load(gid),e.maps) if o['policy']=='training' and o['target']=='public-scholar')

def propose(e,gid,offer):
    cmd(e,gid,'council_propose',offer['token']);work(e,gid,'council');cmd(e,gid,'council_vote')
    assert council.current(e._load(gid))['status']=='approved'

def complete(e,gid):
    cmd(e,gid,'council_execute');work(e,gid,'council');cmd(e,gid,'council_finish')
    origin=council.current(e._load(gid))['offer']['origin']
    if e._load(gid).player.location_id!=origin:travel(e,gid,origin)
    cmd(e,gid,'council_review');work(e,gid,'council');cmd(e,gid,'council_finish')

def visit(e,gid,key,mode='study',choice='salvage'):
    g=e._load(gid);g.player.realm_index=ancient.SITES[key]['realm'];g.player.location_id=ancient.SITES[key]['location']
    add_item(g.player,material_id('celestial',4,'ore_conduct'),100);e.store.save(g);e.get_game(gid)
    cmd(e,gid,'antiquity_start',key);work(e,gid,'antiquity');cmd(e,gid,'antiquity_open',mode);work(e,gid,'antiquity');cmd(e,gid,'antiquity_choose',choice)
    if choice=='preserve':work(e,gid,'antiquity');cmd(e,gid,'antiquity_rebuild')

def test_readonly_and_no_authority(pool):
    e,gid=pool;g=e._load(gid);before=copy.deepcopy(g.to_dict());ancient.public(g,e.maps);council.public(g,e.maps);assert g.to_dict()==before
    offer=training_offer(e,gid)
    with pytest.raises(ValueError,match='七曜'):cmd(e,gid,'council_propose',offer['token'])

@pytest.mark.parametrize('choice',['salvage','preserve'])
def test_three_ruins_real_return_unique_materials_or_original_cave(pool,choice):
    e,gid=pool
    for key in ancient.SITES:
        visit(e,gid,key,choice=choice);g=e._load(gid);row=g.building_state['records'][ancient.building_id(key)]
        assert row['status']==('intact' if choice=='preserve' else 'destroyed')
        if choice=='preserve':assert row['owner']==dict(kind='player',id=gid)
        travel(e,gid,'expanse_celestial_8');cmd(e,gid,'antiquity_return');assert ancient.records(e._load(gid))[key]['returned']
        with pytest.raises(ValueError):cmd(e,gid,'antiquity_return')

def test_cooperation_occupancy_and_actual_share(pool):
    e,gid=pool;g=e._load(gid);g.player.location_id=ancient.SITES['archive']['location'];add_item(g.player,material_id('celestial',4,'ore_conduct'),100);e.store.save(g)
    n=npc(e,gid);cmd(e,gid,'antiquity_start','archive');work(e,gid,'antiquity');cmd(e,gid,'antiquity_open','cooperate~'+n)
    assert research_assignment(e._load(gid),n)['phase']=='antiquity'
    work(e,gid,'antiquity');cmd(e,gid,'antiquity_choose','salvage');g=e._load(gid)
    assert not research_assignment(g,n)
    assert sum(i.quantity for i in g.player.inventory if i.id==ancient.SITES['archive']['item'])==2

def test_training_public_budget_consumes_cargo_and_original_growth(pool):
    e,gid=pool;seats(e,gid);o=training_offer(e,gid);propose(e,gid,o);g=e._load(gid);job=council.current(g)['job']
    assert job['cargo'] and balance(g,job['wallet'])==job['budget']-job['purchase']
    complete(e,gid);g=e._load(gid);assert g.world_npcs['public-scholar'].layer==2
    r=council.state(g)['history'][-1];receipt=r['receipt']
    assert receipt['reserved']==sum(receipt[k] for k in ('purchase','labor','engineering','refunded'))
    assert any(j['id']==r['job_id'] for j in g.heavenly_court['bureaus']['jobs'])
    with pytest.raises(ValueError,match='没有'):cmd(e,gid,'council_finish')

def test_training_invalidated_and_stale_page_are_atomic(pool):
    e,gid=pool;seats(e,gid);o=training_offer(e,gid);d=e.get_game(gid)['heavenly_court']['projects'];propose(e,gid,o)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='变化'):e.yaochi_action(gid,'council_vote',d['token']+'|')
    assert e.store._path(gid).read_bytes()==before
    g=e._load(gid);g.world_npcs['public-scholar'].alive=False;e.store.save(g)
    with pytest.raises(ValueError):cmd(e,gid,'council_execute')
    cmd(e,gid,'council_cancel');assert not council.current(e._load(gid))

def test_public_city_restoration_original_quote(village):
    from cultivation_life.system.building_assets import local_rows
    from cultivation_life.system.building_destruction import destroy
    e,gid=village;seats(e,gid);g=e._load(gid);row=next(r for r in local_rows(g) if r['type']=='city');destroy(g,row);market=local_market(g)
    for item in market['commodities'].values():item['stock']=max(item['stock'],100000)
    e.store.save(g);o=next(o for o in offers(e._load(gid),e.maps) if o['policy']=='repair')
    g=e._load(gid);add_item(g.player,'spirit_stone',o['budget']);transfer_value(g,'player',COURT,o['budget'],'验收按原工程预算实付追加');e.store.save(g)
    propose(e,gid,o);complete(e,gid)
    row=e._load(gid).building_state['records'][row['id']];assert row['status']=='intact' and row['level']==1 and row['owner']['kind']=='background'

def test_procurement_actual_roads_market_and_conservation(pool):
    e,gid=pool;seats(e,gid);g=e._load(gid);here=g.player.location_id
    dest=next(r['to'] if r['from']==here else r['from'] for r in e.maps.worlds['celestial']['routes'] if here in (r['from'],r['to']))
    ensure_regional_market(g,e.maps,'celestial',dest);other=g.economy_v2['markets']['celestial:'+dest];source=local_market(g)
    key=next(k for k,v in source['commodities'].items() if v['stock']>=20 and v['tier']<=10 and k in other['commodities'])
    other['commodities'][key]['stock']=0;e.store.save(g)
    o=next(o for o in offers(e._load(gid),e.maps) if o['policy']=='procurement' and o['item']==key);propose(e,gid,o)
    with pytest.raises(ValueError,match='到达'):cmd(e,gid,'council_execute')
    travel(e,gid,dest);complete(e,gid);assert council.state(e._load(gid))['history'][-1]['status']=='closed'

def test_service_agreement_requires_new_original_duty(village):
    e,gid=village;build(e,gid);seats(e,gid);o=next(o for o in offers(e._load(gid),e.maps) if o['policy']=='service');propose(e,gid,o)
    with pytest.raises(ValueError,match='庙务'):cmd(e,gid,'council_execute')
    cmd(e,gid,'council_public');fulfill(e,gid,'teach');complete(e,gid);assert council.state(e._load(gid))['history'][-1]['status']=='closed'

def test_event_interrupt_and_recovery(pool):
    e,gid=pool;seats(e,gid);o=training_offer(e,gid);cmd(e,gid,'council_propose',o['token']);age=e._load(gid).player.age;annual=e._advance_world_year
    def stop(g,rng,news,**kw):
        out=annual(g,rng,news,**kw)
        if g.player.age==age+2:
            ev=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],g,random.Random(1));ev['_followup_event']=e._prepare_treasure_reward_event(g,random.Random(2));g.pending_event=ev;return False
        return out
    with patch.object(e,'_advance_world_year',side_effect=stop):work(e,gid,'council')
    assert council.work(e._load(gid))['progress']==2
    with pytest.raises(ValueError):cmd(e,gid,'council_work')
    for _ in range(2):
        d=e.get_game(gid);e.choose(gid,next(c['id'] for c in d['pending_event']['choices'] if c.get('available',True)),event_id=d['pending_event']['id'])
    work(e,gid,'council');assert council.work(e._load(gid))['progress']==5

def test_rejected_ballot_requires_real_new_hearing(pool):
    e,gid=pool;seats(e,gid,True);o=training_offer(e,gid);cmd(e,gid,'council_propose',o['token']);work(e,gid,'council')
    with patch('cultivation_life.system.court_projects.decode_rng',return_value=random.Random(2)):cmd(e,gid,'council_vote')
    assert council.current(e._load(gid))['status']=='rejected'
    with pytest.raises(ValueError,match='五年'):cmd(e,gid,'council_vote')
    o=next(o for o in offers(e._load(gid),e.maps) if o['target']=='public-scholar');cmd(e,gid,'council_revise',o['token'])
    assert council.work(e._load(gid))['progress']==0

def test_insufficient_treasury_and_stale_procurement_quote(pool):
    e,gid=pool;seats(e,gid);o=training_offer(e,gid);cmd(e,gid,'council_propose',o['token']);work(e,gid,'council')
    shown=e.get_game(gid)['heavenly_court']['projects'];g=e._load(gid)
    market=local_market(g);row=market['commodities']['npc_training_dao_cultivation_3'];row['stock']=1;reprice(g,market,row);e.store.save(g)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='报价'):e.yaochi_action(gid,'council_vote',shown['token']+'|'+shown['vote_offer']['token'])
    assert e.store._path(gid).read_bytes()==before
    g=e._load(gid);transfer_value(g,COURT,'background:celestial',balance(g,COURT),'验收实际府库不足');e.store.save(g);before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='府库不足'):cmd(e,gid,'council_vote')
    assert e.store._path(gid).read_bytes()==before and not council.current(e._load(gid))['job']

@pytest.mark.parametrize('kind',['antiquity','council'])
def test_real_crossworld_freeze_disable_and_handover(pool,kind):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.engine.world import regions
    e,gid=pool
    if kind=='antiquity':
        g=e._load(gid);g.player.location_id=ancient.SITES['archive']['location'];e.store.save(g);cmd(e,gid,'antiquity_start','archive')
    else:seats(e,gid);o=training_offer(e,gid);cmd(e,gid,'council_propose',o['token'])
    g=e._load(gid);module=ancient if kind=='antiquity' else council;before=copy.deepcopy(module.state(g))
    plan=e._plan_world_transition(g,'spirit','sealed_descent',reason='访古与项目原址冻结验收');e._apply_world_transition(g,plan)
    g.player.age+=2;regions.synchronize(e._dependencies.regions,g,{'spirit'},end=g.player.age)
    assert module.state(g)==before and module.public(g,e.maps) is None
    with pytest.raises(ValueError):module.begin(g)
    plan=e._plan_world_transition(g,'celestial','sealed_return',reason='访古与项目真实返界验收');e._apply_world_transition(g,plan);e.store.save(g)
    assert module.state(g)==before
    if kind=='antiquity':travel(e,gid,ancient.SITES['archive']['location'])
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):
        with pytest.raises(ValueError,match='启用'):work(e,gid,kind)
        cmd(e,gid,'antiquity_abandon' if kind=='antiquity' else 'council_cancel')
    assert (ancient.current(e._load(gid))['phase']=='return') if kind=='antiquity' else council.current(e._load(gid)) is None

def test_pledge_deadline_consequence_and_original_inspection(pool):
    from cultivation_life.system.court_case_facts import leads
    e,gid=pool;seats(e,gid,True);o=training_offer(e,gid);cmd(e,gid,'council_propose',o['token'])
    cmd(e,gid,'council_contact','project-seat-0');work(e,gid,'council')
    with patch('cultivation_life.system.court_projects.decode_rng',return_value=random.Random(1)):cmd(e,gid,'council_vote')
    g=e._load(gid);r=council.current(g);assert r['status']=='approved';g.player.age=r['deadline'];support=g.heavenly_court['player_support'];e.store.save(g)
    cmd(e,gid,'council_cancel');g=e._load(gid)
    assert g.heavenly_court['player_support']==max(0,support-5)
    assert any(l['kind']=='neglect' and l['source']==r['id'] for l in leads(g))

def test_companion_death_pauses_and_releases_original_person(pool):
    e,gid=pool;g=e._load(gid);g.player.location_id=ancient.SITES['archive']['location'];add_item(g.player,material_id('celestial',4,'ore_conduct'),100);e.store.save(g)
    n=npc(e,gid);cmd(e,gid,'antiquity_start','archive');work(e,gid,'antiquity');cmd(e,gid,'antiquity_open','cooperate~'+n)
    g=e._load(gid);g.world_npcs[n].alive=False;e.store.save(g)
    with pytest.raises(ValueError,match='同道'):work(e,gid,'antiquity')
    cmd(e,gid,'antiquity_release');g=e._load(gid);assert not research_assignment(g,n) and not g.world_npcs[n].alive
