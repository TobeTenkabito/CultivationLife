"""Actual city commands, original cash conservation and persistent landscape endings."""
import copy
from pathlib import Path

import pytest

from test_building_system import local, choose, stable_time
from test_city_buildings import fund_city, build_city, commit
from cultivation_life.building_rules import config
from cultivation_life.building_schema import decode_state
from cultivation_life.content_registry import ITEM_CATALOG, WORLD_SYSTEMS, restricted_acquisition
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, remove_item
from cultivation_life.system import buildings
from cultivation_life.system import building_management as management
from cultivation_life.system.building_projects import quote, defense
from cultivation_life.system.economy.ledger import balance


def owned(local,kind='economic'):
    engine,game=local;fund_city(engine,game);build_city(engine,game,kind)
    return engine,engine.store.load(game.id)


def facility(engine,game,kind):
    choose(engine,game.id,'civic:main');choose(engine,game.id,'civic:facilities');choose(engine,game.id,'civic:'+kind)
    return commit(engine,game.id,'civic:commit:')


def test_facility_consumes_original_materials_and_obeys_slots(local):
    engine,game=owned(local);row=next(r for r in game.building_state['records'].values() if r['type']=='city')
    bill=management.quote(game,row,'works');before=stable_time(game);coins=balance(game,'player')
    facility(engine,game,'works')
    after=engine.store.load(game.id);actual=after.building_state['records'][row['id']]
    assert actual['facilities']==['works'] and stable_time(after)==before
    assert coins-balance(after,'player')==bill['coins']
    held={i.id:i.quantity for i in game.player.inventory};now={i.id:i.quantity for i in after.player.inventory}
    for key,n in bill['materials'].items():assert held[key]-now[key]==n
    assert not management.quote(after,actual,'watch')['reason']==''
    assert all(n<=old for n,old in zip(quote(after,'govern',actual)['materials'].values(),quote(game,'govern',row)['materials'].values()))
    choose(engine,game.id,'civic:facilities');choose(engine,game.id,'civic:watch')
    before=engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError):commit(engine,game.id,'civic:commit:')
    assert engine.store.load(game.id).to_dict()==before


@pytest.mark.parametrize('kind,receipt',[('military',1600),('economic',2000),('comprehensive',1800)])
def test_business_waits_for_real_year_and_transfers_existing_cash_once(local,kind,receipt):
    engine,game=owned(local,kind);facility(engine,game,'exchange')
    choose(engine,game.id,'civic:settle')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']
    choose(engine,game.id,'leave')
    engine.advance(game.id,'rest',1)
    game=engine.store.load(game.id);game.pending_event=None;engine.store.save(game)
    row=next(r for r in buildings.local_rows(game) if r.get('facilities')==['exchange'])
    engine.building_action(game.id,'enter',building_id=row['id']);choose(engine,game.id,'civic:main');choose(engine,game.id,'civic:settle')
    old=engine.get_game(game.id)['pending_event'];before=engine.store.load(game.id)
    bill=management.quote(before,row,'settle');cash=management.local_cash(before,row);coins=balance(before,'player')
    assert bill['receipt']==receipt
    commit(engine,game.id,'civic:commit:')
    after=engine.store.load(game.id)
    assert balance(after,'player')-coins==bill['receipt']-bill['coins']
    assert management.local_cash(after,row)-cash==bill['coins']-bill['receipt']
    assert stable_time(after)==stable_time(before)
    with pytest.raises(ValueError):engine.choose(game.id,old['choices'][0]['id'],event_id=old['id'])
    choose(engine,game.id,'civic:settle');assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']
    assert len([h for h in after.history if h.event_id=='SYS_CITY_BUSINESS'])==2


def test_aid_and_governance_share_real_year_and_no_rebuild_reset(local):
    engine,game=owned(local);choose(engine,game.id,'leave');engine.advance(game.id,'rest',1)
    game=engine.store.load(game.id);game.pending_event=None;engine.store.save(game)
    row=next(r for r in buildings.local_rows(game) if r['owner']==dict(kind='player',id=game.id) and r['type']=='city')
    engine.building_action(game.id,'enter',building_id=row['id']);choose(engine,game.id,'civic:main');choose(engine,game.id,'civic:aid');commit(engine,game.id,'civic:commit:')
    choose(engine,game.id,'back');choose(engine,game.id,'city:govern')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']
    choose(engine,game.id,'back');choose(engine,game.id,'management');choose(engine,game.id,'destroy');commit(engine,game.id,'destroy:')
    choose(engine,game.id,'rebuild');commit(engine,game.id,'rebuild:');choose(engine,game.id,'back');choose(engine,game.id,'civic:main');choose(engine,game.id,'civic:aid')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']


def test_stale_treasury_and_lost_city_ownership_cannot_pay(local):
    engine,game=owned(local);facility(engine,game,'exchange')
    saved=engine.store.load(game.id);row=next(r for r in buildings.local_rows(saved) if r.get('facilities'))
    saved.building_state['city_business'][row['id']]['last_year']=max(0,saved.player.age-1);engine.store.save(saved)
    choose(engine,game.id,'civic:settle');old=engine.get_game(game.id)['pending_event']
    saved=engine.store.load(game.id);saved.economy_v2['accounts'][management.account_key(row)]['balance']=0;engine.store.save(saved)
    before=engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError):engine.choose(game.id,old['choices'][0]['id'],event_id=old['id'])
    after=engine.store.load(game.id).to_dict()
    before.pop('pending_event');after.pop('pending_event')
    assert after==before
    saved=engine.store.load(game.id);saved.building_state['records'][row['id']]['owner']=dict(kind='background',id='local');engine.store.save(saved)
    with pytest.raises(ValueError):engine.choose(game.id,old['choices'][0]['id'],event_id=old['id'])
    assert balance(engine.store.load(game.id),'player')==balance(saved,'player')


@pytest.mark.parametrize('world',list(config()['cities']))
def test_eleven_world_new_scenery_real_multistage_tales_once(tmp_path,world):
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path/'saves')
    tier=WORLD_SYSTEMS['world_profiles'][world]['tier']
    game=engine._load(engine.create_game('山河故事','supreme_metal','dao',2172,custom_start=dict(world=world,realm_index={1:3,2:6,3:9}[tier]))['id'])
    specs=config()['scenery'][world]
    assert len(specs)==3 and len(config()['cities'][world])==4
    for spec in specs[1:]:
        game=engine.store.load(game.id);game.pending_event=None;game.player.location_id=spec['location_id'];engine.store.save(game)
        engine.get_game(game.id);game=engine.store.load(game.id)
        before=copy.deepcopy(game.player.to_dict());economy=copy.deepcopy(game.economy_v2);time=stable_time(game)
        engine.building_action(game.id,'enter',building_id=f"scenery:{world}:{spec['id']}")
        for route,ending in [('0','1'),('1','0'),('1','1')]:
            choose(engine,game.id,'explore:main');choose(engine,game.id,'explore:route:'+route)
            shown=choose(engine,game.id,'explore:finish:'+route+':'+ending)
            assert spec['exploration']['endings'][int(ending)] in shown['pending_event']['body']
            choose(engine,game.id,'back')
        choose(engine,game.id,'leave')
        game=engine.store.load(game.id);relic=spec['exploration']['relic_id']
        assert game.building_state['landscape_usage'][f"scenery:{world}:{spec['id']}"]==dict(ending='0:1')
        assert stable_time(game)==time and game.economy_v2==economy
        if relic:
            assert sum(i.quantity for i in game.player.inventory if i.id==relic)==1
            assert restricted_acquisition('item',relic)
            remove_item(game.player,relic,1)
            engine.store.save(game)
            engine.building_action(game.id,'enter',building_id=f"scenery:{world}:{spec['id']}")
            choose(engine,game.id,'explore:main');choose(engine,game.id,'explore:route:0');choose(engine,game.id,'explore:finish:0:1');choose(engine,game.id,'leave')
            assert not any(i.id==relic for i in engine.store.load(game.id).player.inventory)
        else:assert game.player.to_dict()==before


def test_first_choice_to_leave_relic_is_permanent_across_worlds(local):
    engine,game=local;spec=config()['scenery']['human'][1]
    game.player.location_id=spec['location_id'];engine.store.save(game)
    identity='scenery:human:'+spec['id'];engine.building_action(game.id,'enter',building_id=identity)
    choose(engine,game.id,'explore:main');choose(engine,game.id,'explore:route:1');choose(engine,game.id,'explore:finish:1:0');choose(engine,game.id,'leave')
    game=engine.store.load(game.id);before=copy.deepcopy(game.building_state['landscape_usage'])
    engine._apply_world_transition(game,engine._plan_world_transition(game,'demon','rift',route_id='rift:human:demon',reason='隔离景色阅历测试'))
    engine._apply_world_transition(game,engine._plan_world_transition(game,'human','rift',route_id='rift:demon:human',arrival_location=spec['location_id'],reason='隔离景色返程测试'))
    engine.store.save(game);engine.building_action(game.id,'enter',building_id=identity)
    choose(engine,game.id,'explore:main');choose(engine,game.id,'explore:route:0');choose(engine,game.id,'explore:finish:0:1')
    game=engine.store.load(game.id)
    assert game.building_state['landscape_usage']==before and not any(i.id==spec['exploration']['relic_id'] for i in game.player.inventory)


@pytest.mark.parametrize('field,value',[
    ('city_business',{'x':{'last_year':True,'expense':0,'income':0}}),
    ('city_business',{'x':{'last_year':0,'expense':-1,'income':0}}),
    ('landscape_usage',{'x':{'ending':[]}}),('landscape_usage',{'x':{'ending':'2:0'}}),
])
def test_new_nested_contract_rejects_invalid_values(field,value):
    with pytest.raises(ValueError):decode_state(dict(version=1,sequence=0,records={},cultivation={},**{field:value}))
