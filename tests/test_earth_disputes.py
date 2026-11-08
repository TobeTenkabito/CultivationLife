"""Actual registration, timed investigation, opposing choices and original settlements."""
import copy
import random
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_earth_temple import village,build,command,work
from test_earth_network import fund,ground,choose,travel,adjacent
from test_economy_enterprises import buy,estate_act,configure
from cultivation_life.rules import add_item
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.building_rules import may_use
from cultivation_life.system.earth_temple import signature,public
from cultivation_life.system.earth_temple_rules import state,temple,root
from cultivation_life.system.earth_disputes import current
from cultivation_life.system.earth_dispute_roads import delay
from cultivation_life.system.economy.state import local_market
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy.enterprise_rules import recipes
from cultivation_life.system.economy.state import commodity_catalog


def setup_case(e,gid,kind):
    fund(e,gid); build(e,gid)
    if kind=='water':
        g,key=buy(e,e._load(gid),'farm'); estate_act(e,g,key,'fund',amount=10**11)
    if kind=='guard': ground(e,gid)
    if kind=='rebuild':
        e.building_action(gid,'manage',building_id=temple(e._load(gid))['id'])
        choose(e,gid,'destroy'); choose(e,gid,'destroy:',True); choose(e,gid,'leave')
    if kind=='supply':
        g=e._load(gid); market=local_market(g)
        key=next(k for k,r in market['commodities'].items() if r['tier']<=9)
        market['commodities'][key]['stock']=0; add_item(g.player,key,1000); e.store.save(g)
    command(e,gid,'case_report')
    report=state(e._load(gid))['cases']['reports'].get(kind)
    assert report,kind
    if kind=='supply':
        g=e._load(gid); add_item(g.player,report['target'],1000);e.store.save(g)
    return report


def scarcity(e,gid):
    g=e._load(gid); case=current(g)
    if case and case['kind']=='supply':
        local_market(g)['commodities'][case['target']]['stock']=0;e.store.save(g)


def accept(e,gid,kind):
    case=state(e._load(gid))['cases']['reports'][kind]
    command(e,gid,'case_accept',case['id']);work(e,gid);scarcity(e,gid)
    command(e,gid,'case_prepare')


def plan(e,gid,key,action='case_plan'):
    view=e.get_game(gid)['yaochi']['earth']['disputes']['active']
    option=next(p for p in view['options'] if p['id']==key)
    command(e,gid,action,key+':'+option['token'])
    return option


@pytest.mark.parametrize('kind,choice',[
    ('water','release'),('water','canal'),('supply','donate'),('supply','retain'),
    ('road','clear'),('road','bypass'),('property','open'),('property','private'),
    ('guard','repair'),('guard','suspend'),('rebuild','restore'),('rebuild','relief')])
def test_six_cases_opposing_paths_use_original_assets(village,kind,choice):
    e,gid=village;report=setup_case(e,gid,kind);start=e._load(gid).player.age
    accept(e,gid,kind);selected=plan(e,gid,choice)
    with pytest.raises(ValueError,match='工时'):plan(e,gid,choice,'case_resolve')
    with pytest.raises(ValueError,match='原城市不可用' if kind=='rebuild' else '本人一次'):command(e,gid,'accept','watch')
    work(e,gid);scarcity(e,gid)
    if kind=='water':
        g=e._load(gid);key=report['target'];g=configure(e,g,key,auto_buy=False)
        recipe=recipes('celestial',commodity_catalog('celestial'))[g.economy_v2['estates'][key]['recipe']]
        for item,number in recipe['inputs'].items():
            add_item(g.player,item,number);e.store.save(g)
            g=estate_act(e,g,key,'deposit',item=item,quantity=number)
        estate_act(e,g,key,'start')
    before=e._load(gid);wallet=balance(before,'player');original=copy.deepcopy(before.to_dict())
    selected=plan(e,gid,choice,'case_resolve');g=e._load(gid);case=state(g)['cases']['reports'][kind]
    assert not current(g) and case['stage']=='closed'
    assert state(g)['trust']==50+selected['trust'] and not state(g)['allowance'] and not state(g)['until']
    assert g.player.age==start+5+selected['years']
    assert balance(g,'player')==wallet-selected['bill']['coins']
    assert g.yaochi_state['westward']['settlement_years']==5+selected['years']
    if kind=='water':
        row=g.economy_v2['estates'][report['target']];old=before.economy_v2['estates'][report['target']]
        assert row['job']['finish']==old['job']['finish']+(10 if choice=='release' else 0)
        assert row['stock']==old['stock'] and row['produced']==old['produced']
        if choice=='release':
            assert row['public_water_until']==g.player.age+10
            with pytest.raises(ValueError,match='分水约定'):estate_act(e,g,report['target'],'start')
    elif kind=='supply':
        row=local_market(g)['commodities'][report['target']]
        assert row['stock']==(report['quantity'] if choice=='donate' else 0)
        before_qty=sum(i.quantity for i in before.player.inventory if i.id==report['target'])
        assert sum(i.quantity for i in g.player.inventory if i.id==report['target'])==before_qty-(report['quantity'] if choice=='donate' else 0)
    elif kind=='road': assert delay(g,report['edge'])==(0 if choice=='clear' else 2)
    elif kind=='property':
        assert temple(g)['public']==(choice=='open')
        assert may_use(temple(g),'npc','unrelated')==(choice=='open')
        assert temple(g)['owner']==temple(before)['owner']
    elif kind=='guard':
        array=next(a for a in g.player.formation_ground_arrays if a['id']==report['target'])
        assert array['durability']==(100 if choice=='repair' else 40)
        assert state(g)['active']==(choice=='repair')
    elif kind=='rebuild': assert temple(g)['status']==('intact' if choice=='restore' else 'destroyed')
    old=signature(g)+'|'+choice+':'+selected['token']
    with pytest.raises(ValueError,match='没有正在'):e.yaochi_action(gid,'earth_case_resolve',old)


def test_registration_decline_stale_pages_and_readonly(village):
    e,gid=village;fund(e,gid);build(e,gid);g=e._load(gid)
    snapshot=copy.deepcopy(g.to_dict());public(g,e.maps);assert g.to_dict()==snapshot
    token=signature(g);command(e,gid,'case_report')
    with pytest.raises(ValueError,match='变化'):e.yaochi_action(gid,'earth_case_report',token)
    case=state(e._load(gid))['cases']['reports']['road'];command(e,gid,'case_decline',case['id'])
    g=e._load(gid);assert state(g)['trust']==50 and delay(g,case['edge'])==5
    with pytest.raises(ValueError,match='没有新的'):command(e,gid,'case_report')
    assert state(e.store.load(gid))['cases']['reports']['road']['id']==case['id']


def test_promised_cancel_loss_and_expiry_never_refresh(village):
    e,gid=village;setup_case(e,gid,'property');accept(e,gid,'property');plan(e,gid,'open')
    g=e._load(gid);deadline=current(g)['until'];g.player.age=deadline;e.store.save(g)
    with pytest.raises(ValueError,match='期限'):command(e,gid,'work')
    command(e,gid,'case_cancel');assert state(e._load(gid))['trust']==45
    command(e,gid,'case_report');assert state(e._load(gid))['cases']['reports']['property']['until']==deadline+500


def test_case_interruption_followup_and_disabled_recovery(village):
    e,gid=village;setup_case(e,gid,'property');r=state(e._load(gid))['cases']['reports']['property']
    command(e,gid,'case_accept',r['id']);age=e._load(gid).player.age;annual=e._advance_world_year
    def stop(game,rng,news,**kwargs):
        result=annual(game,rng,news,**kwargs)
        if game.player.age==age+2:
            game.pending_event=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1));return False
        return result
    with patch.object(e,'_advance_world_year',side_effect=stop):command(e,gid,'work')
    assert current(e._load(gid))['progress']==2
    with pytest.raises(ValueError,match='处理事件'):command(e,gid,'case_cancel')
    choose(e,gid,'acknowledge')
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):
        with pytest.raises(ValueError,match='尚未启用'):command(e,gid,'work')
        command(e,gid,'case_cancel')
    assert not current(e._load(gid)) and state(e._load(gid))['trust']==50


def test_road_projection_actual_journey_and_crossing_preserve_case(village):
    e,gid=village;report=setup_case(e,gid,'road');g=e._load(gid);source=g.player.location_id;dest=report['target']
    baseline=e.maps.travel_plan('celestial',source,dest,g.player.realm_index).years
    shown=e.get_game(gid);view=next(p for p in shown['map']['locations'] if p['id']==dest)
    assert view['travel_years']==baseline+5
    age=g.player.age;travel(e,gid,dest);assert e._load(gid).player.age==age+baseline+5
    with pytest.raises(ValueError,match='亲临'):command(e,gid,'case_report')
    travel(e,gid,source);accept(e,gid,'road');plan(e,gid,'clear');g=e._load(gid);snapshot=copy.deepcopy(state(g)['cases'])
    p=e._plan_world_transition(g,'spirit','sealed_descent',reason='地方争议原址验证');e._apply_world_transition(g,p);e.store.save(g)
    assert not delay(g,report['edge']) and state(g)['cases']==snapshot
    p=e._plan_world_transition(g,'celestial','sealed_return',reason='返回争议原址',arrival_location=source);e._apply_world_transition(g,p);e.store.save(g)
    assert state(g)['cases']==snapshot
    work(e,gid);plan(e,gid,'clear','case_resolve');assert not delay(e._load(gid),report['edge'])


def test_resolved_original_target_invalidates_quote_and_releases_promise(village):
    e,gid=village;report=setup_case(e,gid,'guard');accept(e,gid,'guard');plan(e,gid,'repair');work(e,gid)
    g=e._load(gid);shown=e.get_game(gid)['yaochi']['earth']['disputes']['active']
    offered=next(p for p in shown['options'] if p['id']=='repair')
    old=signature(g)+'|repair:'+offered['token']
    e.repair_ground_formation(gid,report['target'],offered['extra']['supply'],offered['extra']['quantity'])
    snapshot=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='报价已经变化'):e.yaochi_action(gid,'earth_case_resolve',old)
    assert e.store._path(gid).read_bytes()==snapshot
    command(e,gid,'case_cancel');g=e._load(gid)
    assert state(g)['trust']==50 and not current(g) and not state(g)['allowance']


def test_insufficient_delivery_is_atomic_and_cannot_change_promised_option(village):
    e,gid=village;setup_case(e,gid,'road');accept(e,gid,'road');plan(e,gid,'clear');work(e,gid)
    with pytest.raises(ValueError,match='换案'):plan(e,gid,'bypass','case_resolve')
    g=e._load(gid)
    from cultivation_life.rules import remove_item
    from cultivation_life.economy_content import material_id
    key=material_id('celestial',9,'ore_structure')
    held=next(i.quantity for i in g.player.inventory if i.id==key);remove_item(g.player,key,held);e.store.save(g)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='工料不足'):plan(e,gid,'clear','case_resolve')
    assert e.store._path(gid).read_bytes()==before
    assert current(e._load(gid))['stage']=='execute'


def test_water_pause_original_automatic_gate_and_fixed_expiry(village):
    e,gid=village;report=setup_case(e,gid,'water');accept(e,gid,'water');plan(e,gid,'release');work(e,gid);plan(e,gid,'release','case_resolve')
    g=e._load(gid);row=g.economy_v2['estates'][report['target']]
    from cultivation_life.system.economy.enterprise_operations import start_job,advance_estates
    before=copy.deepcopy(row);cash=balance(g,'estate:'+row['id'])
    with pytest.raises(ValueError,match='分水约定'):start_job(g,e.maps,row,automatic=True)
    assert row==before
    g.player.age+=9;advance_estates(g,e.maps)
    assert not row['job'] and balance(g,'estate:'+row['id'])<cash and not row['produced']
    recipe=recipes('celestial',commodity_catalog('celestial'))[row['recipe']]
    for item,number in recipe['inputs'].items():
        add_item(g.player,item,number)
    e.store.save(g);g=configure(e,g,row['id'],auto_buy=False)
    for item,number in recipe['inputs'].items():g=estate_act(e,g,row['id'],'deposit',item=item,quantity=number)
    g.player.age+=1;advance_estates(g,e.maps)
    g=estate_act(e,g,row['id'],'start')
    assert g.economy_v2['estates'][row['id']]['job'] is not None
