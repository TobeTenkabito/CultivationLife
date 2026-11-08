"""Real branch construction/travel, specialization works and original service authorities."""
import copy
import random
from unittest.mock import patch

import pytest

from test_earth_temple import village, command, build, work, fulfill
from test_immortal_cultivation import prepared
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from cultivation_life.building_schema import decode_state
from cultivation_life.system.earth_temple import public, signature
from cultivation_life.system.earth_temple_rules import root, state, temple, slots, bonus
from cultivation_life.system.building_projects import quote, temple_facility_cost, land_temple_cost
from cultivation_life.system.building_assets import local_rows
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.formation_system import make_formation_material_instance, formation_material_definitions, formation_maintenance_definitions


def choose(e, gid, key, prefix=False):
    shown = e.get_game(gid)
    if prefix:
        key = next(c['id'] for c in shown['pending_event']['choices'] if c['id'].startswith(key))
    return e.choose(gid, key, event_id=shown['pending_event']['id'])


def fund(e, gid):
    g = e._load(gid)
    add_item(g.player, 'spirit_stone', 10**14)
    for key in quote(g,'city')['materials']:
        add_item(g.player, key, 100000)
    e.store.save(g)


def adjacent(e, gid, avoid=()):
    g=e._load(gid); here=g.player.location_id
    candidates=[r['to'] if r['from']==here else r['from'] for r in e.maps.worlds['celestial']['routes'] if here in (r['from'],r['to'])]
    return next(k for k in candidates if k not in avoid and e.maps.travel_plan('celestial',here,k,g.player.realm_index).status=='ok')


def travel(e, gid, destination):
    for _ in range(5):
        e.travel_map(gid,destination)
        if not e._load(gid).map_journey:
            return
        if e._load(gid).pending_event:
            pytest.fail('Unexpected event during fixture journey')
    pytest.fail('Journey did not complete')


def make_city(e, gid):
    if any(r['type']=='city' and r.get('population') in {'mixed','mortal'} for r in local_rows(e._load(gid))):
        return
    e.building_action(gid,'city-plan')
    choose(e,gid,'city:economic'); choose(e,gid,'city:economic:mortal'); choose(e,gid,'city:build:',True); choose(e,gid,'leave')


def facility(e, gid, slot, kind):
    command(e,gid,'facility',f'{slot}:{kind}')
    work(e,gid)
    command(e,gid,'complete_works')


def ground(e, gid):
    g=e._load(gid)
    definitions=formation_material_definitions()
    keys=[k for k,v in definitions.items() if v['world']=='celestial' and v['tier']==9][:3]
    instances=[make_formation_material_instance(definitions[k],source='test',origin_world='celestial') for k in keys]
    g.player.formation_materials.extend(instances)
    e.store.save(g)
    e.save_formation(gid,dict(name='庙域原阵',slots=[i['id'] for i in instances]+[None]*6,activate=True))
    e.deploy_ground_formation(gid,'player')
    g=e._load(gid); original=g.player.formation_ground_arrays[0]; original['durability']=40.
    supply=next(k for k,v in formation_maintenance_definitions().items() if v['world']=='celestial')
    g.player.formation_repair_supplies[supply]=10
    e.store.save(g)
    return original['id'], supply


def test_branch_real_road_real_city_independent_faith_and_shared_person(village):
    e,gid=village; fund(e,gid); build(e,gid); fulfill(e,gid)
    g=e._load(gid); main=copy.deepcopy(root(g)); source=g.player.location_id
    target=adjacent(e,gid); travel(e,gid,target); make_city(e,gid)
    build(e,gid)
    g=e._load(gid); branch=state(g); branch_id=temple(g)['id']
    assert branch_id!=main['temple_id'] and len(root(g)['branches'])==1
    assert temple(g)['parent_temple_id']==main['temple_id']
    assert root(g)['allowance']==400 and branch['allowance']==0 and not bonus(g)
    assert root(g)['until']==main['until']
    command(e,gid,'accept','watch')
    travel(e,gid,source)
    with pytest.raises(ValueError,match='本人一次|当前事务'):
        command(e,gid,'facility','0:watch')
    assert bonus(e._load(gid))==.3
    travel(e,gid,target); command(e,gid,'cancel')
    fulfill(e,gid,'teach')
    assert bonus(e._load(gid))==.275
    assert root(e._load(gid))['allowance']==400
    assert state(e.store.load(gid),branch_id)['completed']==1
    assert len([r for r in e._load(gid).building_state['records'].values() if r.get('subtype')=='land_temple'])==2


def test_one_main_three_branches_ruins_keep_capacity_and_no_remote_build(village):
    e,gid=village; fund(e,gid); build(e,gid)
    seen={e._load(gid).player.location_id}
    for _ in range(3):
        target=adjacent(e,gid,seen); travel(e,gid,target); make_city(e,gid); build(e,gid); seen.add(target)
    g=e._load(gid); last=temple(g)['id']
    assert len(root(g)['branches'])==3
    e.building_action(gid,'manage',building_id=last)
    choose(e,gid,'destroy'); choose(e,gid,'destroy:',True); choose(e,gid,'leave')
    assert len(root(e._load(gid))['branches'])==3
    target=adjacent(e,gid,seen); travel(e,gid,target); make_city(e,gid)
    view=e.get_game(gid)['yaochi']['earth']
    assert not view['local'] and len(view['network'])==4
    with pytest.raises(ValueError,match='一主三分'):
        command(e,gid,'build',next(c['id'] for c in view['cities'] if c['population'] in {'mortal','mixed'}))
    with pytest.raises(ValueError,match='亲临'):
        command(e,gid,'facility','0:care')


def test_branch_rejects_nonadjacent_and_lost_parent_permission(village):
    e,gid=village; fund(e,gid); build(e,gid)
    g=e._load(gid); source=g.player.location_id
    direct={r['to'] if r['from']==source else r['from'] for r in e.maps.worlds['celestial']['routes'] if source in (r['from'],r['to'])}
    distant=next(r['id'] for r in e.maps.worlds['celestial']['locations'] if r['id'] not in direct|{source} and e.maps.travel_plan('celestial',source,r['id'],9).status=='ok')
    travel(e,gid,distant); make_city(e,gid)
    view=e.get_game(gid)['yaochi']['earth']
    with pytest.raises(ValueError,match='直接道路'):
        command(e,gid,'build',next(c['id'] for c in view['cities'] if c['population'] in {'mortal','mixed'}))
    travel(e,gid,source); target=adjacent(e,gid); command(e,gid,'suspend'); travel(e,gid,target); make_city(e,gid)
    view=e.get_game(gid)['yaochi']['earth']
    with pytest.raises(ValueError,match='直接道路'):
        command(e,gid,'build',next(c['id'] for c in view['cities'] if c['population'] in {'mortal','mixed'}))


def test_two_slots_paid_years_replacement_cancellation_and_stale_work(village):
    e,gid=village; build(e,gid); g=e._load(gid); age=g.player.age; money=balance(g,'player')
    before=copy.deepcopy(g.to_dict()); public(g,e.maps); assert g.to_dict()==before
    old=signature(g)+'|0:watch'
    command(e,gid,'facility','0:watch')
    assert slots(e._load(gid))==[None,None]
    assert balance(e._load(gid),'player')==money-temple_facility_cost('celestial','watch')['coins']
    with pytest.raises(ValueError,match='变化'):
        e.yaochi_action(gid,'earth_facility',old)
    with pytest.raises(ValueError,match='工时'):
        command(e,gid,'complete_works')
    work(e,gid); command(e,gid,'complete_works')
    assert e._load(gid).player.age==age+20 and slots(e._load(gid))==['watch',None]
    with pytest.raises(ValueError,match='重复'):
        command(e,gid,'facility','1:watch')
    facility(e,gid,1,'care')
    command(e,gid,'facility','0:teach')
    assert slots(e._load(gid))==[None,'care']
    g=e._load(gid); money=balance(g,'player'); command(e,gid,'cancel_works')
    assert balance(e._load(gid),'player')==money and slots(e._load(gid))==[None,'care']
    assert e._load(gid).yaochi_state['westward']['settlement_years']==40


def test_facility_interruption_and_disabled_dlc_recovery(village):
    e,gid=village; build(e,gid); command(e,gid,'facility','0:teach')
    age=e._load(gid).player.age; original=e._advance_world_year
    def interrupt(game,rng,news,**kwargs):
        result=original(game,rng,news,**kwargs)
        if game.player.age==age+3:
            game.pending_event=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1)); return False
        return result
    with patch.object(e,'_advance_world_year',side_effect=interrupt): command(e,gid,'work')
    assert state(e._load(gid))['works']['progress']==3
    with pytest.raises(ValueError,match='处理事件'): command(e,gid,'cancel_works')
    choose(e,gid,'acknowledge')
    from cultivation_life.content_registry import WORLD_SYSTEMS
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):
        with pytest.raises(ValueError,match='尚未启用'): command(e,gid,'work')
        command(e,gid,'cancel_works')
    assert slots(e._load(gid))==[None,None] and e._load(gid).yaochi_state['westward']['settlement_years']==3


def test_rebuild_pays_for_installed_facilities_and_keeps_original_slots(village):
    e,gid=village; build(e,gid); facility(e,gid,0,'watch'); facility(e,gid,1,'care')
    g=e._load(gid); identity=temple(g)['id']; ledger=copy.deepcopy(state(g))
    e.building_action(gid,'manage',building_id=identity)
    choose(e,gid,'destroy'); choose(e,gid,'destroy:',True)
    choose(e,gid,'rebuild'); g=e._load(gid); money=balance(g,'player')
    quoted=quote(g,'rebuild',temple(g))
    assert quoted['coins']==land_temple_cost('celestial')['coins']+temple_facility_cost('celestial','watch')['coins']+temple_facility_cost('celestial','care')['coins']
    choose(e,gid,'rebuild:',True); choose(e,gid,'leave'); g=e._load(gid)
    assert balance(g,'player')==money-quoted['coins'] and slots(g)==['watch','care']
    assert state(g)==ledger and temple(g)['id']==identity
    value=copy.deepcopy(g.building_state); value['records'][identity]['temple_facilities']=['watch','watch']
    with pytest.raises(ValueError,match='两个不同'): decode_state(value)


def test_watch_uses_original_deployed_array_supplies_and_one_delivery(village):
    e,gid=village; build(e,gid); facility(e,gid,0,'watch'); identity,supply=ground(e,gid)
    g=e._load(gid); bindings=copy.deepcopy(g.player.formation_ground_arrays[0]['bindings'])
    row=next(r for r in e.get_game(gid)['yaochi']['earth']['facilities']['services'] if r['kind']=='watch')
    # An original repair changes the target while leaving the temple quote itself unchanged.
    stale=signature(g)+'|'+row['id']
    e.repair_ground_formation(gid,identity,supply,1)
    with pytest.raises(ValueError,match='对象或原报价'):
        e.yaochi_action(gid,'earth_special',stale)
    g=e._load(gid); held=g.player.formation_repair_supplies[supply]
    row=next(r for r in e.get_game(gid)['yaochi']['earth']['facilities']['services'] if r['kind']=='watch')
    old=signature(g)+'|'+row['id']; command(e,gid,'special',row['id'])
    g=e._load(gid); array=next(a for a in g.player.formation_ground_arrays if a['id']==identity)
    assert array['durability']>40 and array['bindings']==bindings
    assert g.player.formation_repair_supplies.get(supply,0)==held-row['quantity']
    assert state(g)['allowance']==0 and state(g)['duty']['progress']==0
    with pytest.raises(ValueError,match='变化'): e.yaochi_action(gid,'earth_special',old)
    work(e,gid); command(e,gid,'claim')
    assert state(e._load(gid))['allowance']==400 and state(e._load(gid))['trust']==60


def test_care_rebuilds_original_cave_and_preserves_its_claims(village):
    e,gid=village; build(e,gid); facility(e,gid,0,'care')
    e.building_action(gid,'construct'); choose(e,gid,'level:1'); choose(e,gid,'plan:1:professional'); choose(e,gid,'confirm'); choose(e,gid,'leave')
    g=e._load(gid); cave=next(r for r in local_rows(g) if r.get('subtype')=='cave')
    e.building_action(gid,'manage',building_id=cave['id']); choose(e,gid,'destroy'); choose(e,gid,'destroy:',True); choose(e,gid,'leave')
    g=e._load(gid); money=balance(g,'player'); amount=quote(g,'rebuild',g.building_state['records'][cave['id']])['coins']
    row=next(r for r in e.get_game(gid)['yaochi']['earth']['facilities']['services'] if r['kind']=='care')
    command(e,gid,'special',row['id']); g=e._load(gid)
    assert g.building_state['records'][cave['id']]['status']=='intact' and balance(g,'player')==money-amount
    command(e,gid,'cancel')
    assert e._load(gid).building_state['records'][cave['id']]['status']=='intact' and not state(e._load(gid))['allowance']


def test_teach_original_person_qualification_and_paid_growth(village):
    e,gid=village; build(e,gid); facility(e,gid,0,'teach')
    g=e._load(gid)
    n=SectNpc('earth-student','本地门人','门人',2,1,30,300,world='celestial',location_id=g.player.location_id,spirit_root='supreme_metal')
    g.world_npcs[n.id]=n; g.player.disciples.append(g.link_relationship({'id':n.id})); e.store.save(g)
    snapshot=copy.deepcopy(g.to_dict()); public(g,e.maps); assert g.to_dict()==snapshot
    from cultivation_life.system.npc_development.service import quote as train_quote
    original=train_quote(g,'npc',n.id,'cultivation'); money=g.player.opportunity
    row=next(r for r in e.get_game(gid)['yaochi']['earth']['facilities']['services'] if r['kind']=='teach')
    command(e,gid,'special',row['id']); g=e._load(gid)
    assert g.world_npcs[n.id].layer==original['result']['layer']
    assert g.player.opportunity==money-original['opportunity']
    assert g.player.disciples[-1].person is g.world_npcs[n.id]
    command(e,gid,'cancel'); g=e._load(gid); g.world_npcs[n.id].location_id=adjacent(e,gid); e.store.save(g)
    assert not [r for r in e.get_game(gid)['yaochi']['earth']['facilities']['services'] if r['kind']=='teach']
    with pytest.raises(ValueError,match='对象或原报价'): command(e,gid,'special',row['id'])


def test_branch_work_crossing_keeps_original_address_and_elapsed_credit(village):
    e,gid=village; fund(e,gid); build(e,gid)
    target=adjacent(e,gid); travel(e,gid,target); make_city(e,gid); build(e,gid)
    command(e,gid,'facility','0:teach')
    g=e._load(gid); identity=temple(g)['id']; age=g.player.age
    original_building=copy.deepcopy(temple(g)); annual=e._advance_world_year
    def interrupt(game,rng,news,**kwargs):
        result=annual(game,rng,news,**kwargs)
        if game.player.age==age+3:
            plan=e._plan_world_transition(game,'spirit','sealed_descent',reason='原庙工时归属测试')
            e._apply_world_transition(game,plan)
            return False
        return result
    with patch.object(e,'_advance_world_year',side_effect=interrupt): work(e,gid)
    g=e._load(gid)
    assert g.player.world=='spirit' and state(g,identity)['works']['progress']==3
    assert not root(g).get('works') and g.building_state['records'][identity]==original_building
    snapshot=copy.deepcopy(root(g))
    with pytest.raises(ValueError,match='亲临'):
        e.yaochi_action(gid,'earth_work',signature(g))
    g=e.store.load(gid)
    assert root(g)==snapshot
    plan=e._plan_world_transition(g,'celestial','sealed_return',reason='返回原施工分庙',arrival_location=target)
    e._apply_world_transition(g,plan); e.store.save(g)
    assert state(g)['temple_id']==identity and root(g)==snapshot
    work(e,gid); command(e,gid,'complete_works')
    assert slots(e._load(gid))==['teach',None] and e._load(gid).player.age==age+20
