"""Actual mainline/identity/repair commands, original assets and replay boundaries."""
import copy
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_yaochi_westward import pool
from test_earth_temple import village,build,command as earth_cmd,fulfill
from test_earth_network import travel
from test_court_bureaus import cmd as bureau_cmd
from test_westward_ventures import seats,training_offer,propose,complete as complete_council,npc
from test_yaochi_fair import leased,cmd as gathering,work as gathering_work
from cultivation_life.rules import add_item,remove_item
from cultivation_life.economy_content import material_id
from cultivation_life.system import purple_east as story,immortal_identity as identity,immortal_relief as relief
from cultivation_life.system.immortal_identity_rules import primary
from cultivation_life.system.earth_temple_rules import root as earth,temple,bonus
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.yaochi_garden import estate
from cultivation_life.system.building_projects import quote
from cultivation_life.person_assignments import research_assignment

@pytest.fixture
def finale(pool):
    e,gid=pool;g=e._load(gid)
    add_item(g.player,'spirit_stone',10**11)
    add_item(g.player,material_id('celestial',4,'ore_conduct'),100)
    e.store.save(g);return e,gid

def cmd(e,gid,name,value=''):
    data=e.get_game(gid)['yaochi']['purple_east']
    return e.yaochi_action(gid,'purple_'+name,data['token']+'|'+value)

def work(e,gid):
    with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):return cmd(e,gid,'work')

def step(e,gid):
    work(e,gid);return cmd(e,gid,'submit')

def hearing(e,gid,mitigation='canal'):
    cmd(e,gid,'start');step(e,gid);cmd(e,gid,'mitigate',mitigation);step(e,gid)

def finish(e,gid,plan='guard'):
    cmd(e,gid,'plan',plan);step(e,gid);cmd(e,gid,'build');step(e,gid)

def test_mainline_view_is_readonly_and_creates_no_deed(finale):
    e,gid=finale;g=e._load(gid);before=copy.deepcopy(g.to_dict())
    for _ in range(3):story.public(g,e.maps);identity.public(g);relief.public(g)
    assert g.to_dict()==before and story.BUILDING not in g.building_state.get('records',{})

@pytest.mark.parametrize('mitigation',['canal','wait'])
def test_four_chapters_real_years_original_rebuild_and_no_replay(finale,mitigation):
    e,gid=finale
    if mitigation=='wait':
        from cultivation_life.system.earth_temple import bill as temple_bill
        g=e._load(gid)
        for key,n in temple_bill(g)['materials'].items():add_item(g.player,key,n)
        e.store.save(g);build(e,gid);assert primary(e._load(gid))=='earth'
    start=e._load(gid).player.age;hearing(e,gid,mitigation)
    g=e._load(gid);assert g.player.age==start+(10 if mitigation=='canal' else 20)
    assert estate(g)['public_water_until']==start+10
    city=g.building_state['records'][story.state(g)['city']];assert city['civic_disruption_until']<=g.player.age
    cmd(e,gid,'civic');step(e,gid)
    before=balance(e._load(gid),'player');finish(e,gid)
    g=e._load(gid);row=story.original(g)
    assert g.player.age==start+(55 if mitigation=='canal' else 65)
    assert row['status']=='intact' and row['public'] and row['owner']==dict(kind='player',id=gid)
    assert balance(g,'player')<before and story.state(g)['phase']=='complete'
    saved=e.store._path(gid).read_bytes()
    for action in ('start','submit','build','work'):
        with pytest.raises(ValueError):cmd(e,gid,action)
        assert e.store._path(gid).read_bytes()==saved

def test_real_yaochi_supply_receipt_unlocks_yard_ending(finale):
    e,gid=finale;hearing(e,gid)
    with pytest.raises(ValueError,match='供货'):cmd(e,gid,'plan','yaochi')
    leased(e,gid);gathering(e,gid,'garden_order');gathering(e,gid,'garden_start');gathering_work(e,gid,'garden');gathering(e,gid,'garden_deliver')
    assert story.proofs(e._load(gid))['garden']
    farm=estate(e._load(gid));stock=copy.deepcopy(farm['stock']);produced=farm['produced'];farm_id=farm['id']
    finish(e,gid,'yaochi');g=e._load(gid);row=story.original(g)
    assert row['owner']==dict(kind='background',id='institution:celestial:yaochi') and row['users']==[dict(kind='player',id=gid)]
    farm=estate(g)
    assert farm['owner_kind']=='yaochi' and farm['id']==farm_id
    assert sum(farm['stock'].values())-sum(stock.values())==farm['produced']-produced
    assert farm['produced']>produced  # the original operating farm keeps producing during mainline years
    assert e.get_game(gid)['yaochi']['purple_east']['state']['phase']=='complete'

def test_actual_seven_office_training_unlocks_public_ending(finale):
    e,gid=finale;hearing(e,gid)
    with pytest.raises(ValueError,match='七曜'):cmd(e,gid,'plan','public')
    seats(e,gid);propose(e,gid,training_offer(e,gid));complete_council(e,gid)
    assert story.proofs(e._load(gid))['council']
    finish(e,gid,'public');row=story.original(e._load(gid))
    assert row['public'] and row['owner']['id']=='organization:court:heavenly'

def test_original_companion_occupancy_pause_and_resume(finale):
    e,gid=finale;hearing(e,gid);cmd(e,gid,'civic');step(e,gid);n=npc(e,gid,'mainline-companion')
    cmd(e,gid,'plan','shared~'+n);step(e,gid);cmd(e,gid,'build')
    assert research_assignment(e._load(gid),n)['id']==story.BUILDING
    cmd(e,gid,'pause');assert not research_assignment(e._load(gid),n)
    g=e._load(gid);g.world_npcs[n].location_id='jade_capital';e.store.save(g)
    with pytest.raises(ValueError,match='当面'):cmd(e,gid,'resume')
    g=e._load(gid);g.world_npcs[n].location_id=g.player.location_id;e.store.save(g)
    cmd(e,gid,'resume');step(e,gid);g=e._load(gid)
    assert story.original(g)['users']==[dict(kind='npc',id=n)] and not research_assignment(g,n)

def test_missing_material_and_stale_page_are_atomic(finale):
    e,gid=finale;cmd(e,gid,'start');old=e.get_game(gid)['yaochi']['purple_east']['token'];step(e,gid)
    g=e._load(gid);key=material_id('celestial',4,'ore_conduct');remove_item(g.player,key,100);e.store.save(g);before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='不足'):cmd(e,gid,'mitigate','canal')
    assert e.store._path(gid).read_bytes()==before
    with pytest.raises(ValueError,match='变化'):e.yaochi_action(gid,'purple_start',old+'|')
    assert e.store._path(gid).read_bytes()==before

def test_failed_companion_can_replan_without_refund_or_duplicate_deed(finale):
    e,gid=finale;hearing(e,gid);cmd(e,gid,'civic');step(e,gid);n=npc(e,gid,'failed-companion')
    cmd(e,gid,'plan','shared~'+n);step(e,gid);cmd(e,gid,'build')
    g=e._load(gid);before=balance(g,'player');g.world_npcs[n].alive=False;e.store.save(g)
    with pytest.raises(ValueError):cmd(e,gid,'work')
    cmd(e,gid,'pause');cmd(e,gid,'replan');g=e._load(gid)
    assert balance(g,'player')==before and not research_assignment(g,n)
    assert story.state(g)['civic_done'] and story.state(g)['phase']=='hearing'
    assert story.original(g)['owner']['kind']=='background'
    cmd(e,gid,'plan','guard');assert story.work(e._load(gid))['progress']==0

def test_early_work_direct_rebuild_and_double_schedule_rejected(finale):
    e,gid=finale;cmd(e,gid,'start')
    with pytest.raises(ValueError,match='工时'):cmd(e,gid,'submit')
    with pytest.raises(ValueError):e.yaochi_action(gid,'accept','care')
    from cultivation_life.system.building_destruction import rebuild
    g=e._load(gid)
    with pytest.raises(ValueError,match='权限'):rebuild(g,story.original(g),None)
    step(e,gid);cmd(e,gid,'mitigate','wait')
    with pytest.raises(ValueError,match='事务'):cmd(e,gid,'mitigate','wait')

def test_earth_primary_handover_and_xuan_faith_exclusion(village):
    e,gid=village;build(e,gid);fulfill(e,gid);g=e._load(gid)
    assert primary(g)=='earth' and bonus(g)>0
    allowance=earth(g)['allowance'];until=earth(g)['until'];home=g.player.location_id
    travel(e,gid,'jade_capital')
    with pytest.raises(ValueError,match='主持'):bureau_cmd(e,gid,'join','patrol')
    token=e.get_game(gid)['yaochi']['identity']['token'];e.yaochi_action(gid,'identity_register',token)
    travel(e,gid,home);token=e.get_game(gid)['yaochi']['identity']['token'];e.yaochi_action(gid,'identity_retire',token)
    travel(e,gid,'jade_capital');bureau_cmd(e,gid,'join','patrol');g=e._load(gid)
    assert primary(g)=='xuan' and earth(g)['allowance']==allowance and earth(g)['until']==until
    travel(e,gid,home)
    with pytest.raises(ValueError,match='玄仙'):earth_cmd(e,gid,'resume')
    assert bonus(e._load(gid))==0
    travel(e,gid,'jade_capital');token=e.get_game(gid)['yaochi']['identity']['token'];e.yaochi_action(gid,'identity_retire',token)
    assert primary(e._load(gid))=='free'
    travel(e,gid,home);earth_cmd(e,gid,'resume');assert primary(e._load(gid))=='earth'

def test_private_repair_consumes_merit_original_budget_and_pays_builder(village):
    e,gid=village;build(e,gid);g=e._load(gid);row=temple(g);row['status']='destroyed';g.heavenly_court['player_merit']=50;e.store.save(g)
    from cultivation_life.system.westward_rules import adopt_merit
    g=e._load(gid);adopt_merit(g);e.store.save(g)
    shown=e.get_game(gid)['yaochi']['relief'];off=next(r for r in shown['offers'] if r['id']==row['id'])
    assert off['subsidy']>0 and off['personal']+off['subsidy']==off['coins']
    before=balance(e._load(gid),'player');e.yaochi_action(gid,'relief_rebuild',off['token']);g=e._load(gid)
    assert temple(g)['status']=='intact' and balance(g,'player')==before-off['personal']
    assert g.heavenly_court['merit_account']['available']==50-off['merit'] and g.heavenly_court['player_merit']==50
    assert not any(k.startswith('escrow:yaochi-westward:repair:') for k in g.economy_v2['accounts'])
    saved=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='变化'):e.yaochi_action(gid,'relief_rebuild',off['token'])
    assert e.store._path(gid).read_bytes()==saved

def test_disabled_expansion_retains_mainline_and_allows_pause(finale):
    e,gid=finale;cmd(e,gid,'start');before=copy.deepcopy(story.state(e._load(gid)))
    from cultivation_life.content_registry import WORLD_SYSTEMS
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):
        with pytest.raises(ValueError):cmd(e,gid,'work')
        assert story.state(e._load(gid))==before
        cmd(e,gid,'pause');assert story.state(e._load(gid))['paused_work']==before['work']
    cmd(e,gid,'resume');assert story.state(e._load(gid))['work']==before['work']
