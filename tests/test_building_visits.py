"""Loaded visit events, original estate authority and persistent one-time insight."""
import copy

import pytest

from test_building_system import local, choose
from test_economy_enterprises import buy
from cultivation_life.building_schema import decode_state
from cultivation_life.building_rules import config
from cultivation_life.system import buildings
from cultivation_life.system.buddhist.rules import buddhist_config


@pytest.mark.parametrize('branch', [0,1])
def test_scenery_branches_are_zero_year_and_reward_free(local,branch):
    engine,game=local
    game.player.location_id=config()['scenery'][game.player.world][0]['location_id']
    engine.store.save(game);engine.get_game(game.id)
    game=engine.store.load(game.id)
    row=next(r for r in buildings.local_rows(game) if r['type']=='scenery')
    baseline=(game.player.to_dict(),game.rng_state,copy.deepcopy(game.economy_v2))
    engine.building_action(game.id,'enter',building_id=row['id'])
    for _ in range(2):
        for activity in ('trail','weather','traces'):
            shown=choose(engine,game.id,'visit:'+activity)
            assert len(shown['pending_event']['choices'])==4
            assert engine.get_game(game.id)['pending_event']['id']==shown['pending_event']['id']
            choose(engine,game.id,f'visit:resolve:{activity}:{branch}')
            choose(engine,game.id,'back')
    choose(engine,game.id,'leave')
    after=engine.store.load(game.id)
    assert (after.player.to_dict(),after.rng_state,after.economy_v2)==baseline
    assert not after.building_state.get('visit_usage') and not after.building_state.get('scene')


@pytest.mark.parametrize('kind', ['farm','mine','hunt','alchemy','forge','shop'])
@pytest.mark.parametrize('branch', [0,1])
def test_each_industry_uses_own_tale_and_original_books_with_single_insight(local,kind,branch):
    engine,game=local
    game,identity=buy(engine,game,kind)
    before=copy.deepcopy(game.economy_v2)
    age,rng,opportunity=game.player.age,game.rng_state,game.player.opportunity
    engine.building_action(game.id,'enter',building_id='estate:'+identity)
    choose(engine,game.id,'visit:ledger')
    assert '当前没有在制批次' in engine.get_game(game.id)['pending_event']['body']
    choose(engine,game.id,'back')
    choose(engine,game.id,'visit:work');choose(engine,game.id,f'visit:resolve:work:{branch}');choose(engine,game.id,'back')
    shown=choose(engine,game.id,'visit:lesson');stale=shown['pending_event']['id']
    original=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):engine.choose(game.id,'visit:resolve:lesson:0')
    assert engine.store._path(game.id).read_bytes()==original
    choose(engine,game.id,f'visit:resolve:lesson:{branch}')
    original=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):engine.choose(game.id,'visit:resolve:lesson:0',event_id=stale)
    assert engine.store._path(game.id).read_bytes()==original
    choose(engine,game.id,'back');choose(engine,game.id,'visit:lesson')
    assert all(not c['enabled'] for c in engine.get_game(game.id)['pending_event']['choices'][:2])
    choose(engine,game.id,'leave')
    after=engine.store.load(game.id)
    assert (after.player.age,after.rng_state,after.economy_v2)==(age,rng,before)
    assert after.player.opportunity>opportunity
    assert after.building_state['visit_usage']['estate:'+identity]==dict(insight=1)
    engine.building_action(game.id,'enter',building_id='estate:'+identity)
    choose(engine,game.id,'visit:lesson')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']


def temple(local,monkeypatch):
    engine,game=local
    monkeypatch.setitem(buddhist_config(),'enabled',True)
    game.player.path='buddhist';engine.store.save(game)
    engine.building_action(game.id,'temple-plan');choose(engine,game.id,'confirm')
    return engine,engine.store.load(game.id)


@pytest.mark.parametrize('branch',[0,1])
def test_temple_events_do_not_manufacture_followers_or_buddhist_resources(local,monkeypatch,branch):
    engine,game=temple(local,monkeypatch)
    before=copy.deepcopy(game.buddhist_state);age,rng=game.player.age,game.rng_state
    for activity in ('bell','pilgrims','lesson'):
        choose(engine,game.id,'visit:'+activity)
        choose(engine,game.id,f'visit:resolve:{activity}:{branch}');choose(engine,game.id,'back')
    choose(engine,game.id,'visit:lesson')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']
    choose(engine,game.id,'leave')
    after=engine.store.load(game.id)
    assert (after.buddhist_state,after.player.age,after.rng_state)==(before,age,rng)
    assert next(iter(after.building_state['visit_usage'].values()))==dict(insight=1)


def test_disabled_temple_preserves_earned_followup_and_claim_then_restores(local,monkeypatch):
    engine,game=temple(local,monkeypatch)
    choose(engine,game.id,'visit:lesson');choose(engine,game.id,'visit:resolve:lesson:0')
    saved=engine.store.load(game.id)
    claim=copy.deepcopy(saved.building_state['visit_usage'])
    saved.pending_event['_followup_event']=copy.deepcopy(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'])
    engine.store.save(saved)
    monkeypatch.setitem(buddhist_config(),'enabled',False)
    shown=engine.get_game(game.id)
    assert shown['pending_event']['id']=='EVT_SECT_FIRST_WARNING_001' and not shown['buildings']['inside']
    assert engine.store.load(game.id).building_state['visit_usage']==claim
    monkeypatch.setitem(buddhist_config(),'enabled',True)
    assert any(r['subtype']=='temple' for r in engine.get_game(game.id)['buildings']['rows'])


def test_rebuild_does_not_refresh_industry_insight(local):
    from test_city_buildings import commit
    engine,game=local;game,identity=buy(engine,game,'mine')
    engine.building_action(game.id,'enter',building_id='estate:'+identity)
    choose(engine,game.id,'visit:lesson');choose(engine,game.id,'visit:resolve:lesson:0');choose(engine,game.id,'back')
    choose(engine,game.id,'management');choose(engine,game.id,'destroy');commit(engine,game.id,'destroy:')
    choose(engine,game.id,'rebuild');commit(engine,game.id,'rebuild:');choose(engine,game.id,'back')
    choose(engine,game.id,'visit:lesson')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']


def test_cross_world_roundtrip_keeps_fixed_asset_claim(local):
    engine,game=local;game,identity=buy(engine,game,'mine')
    engine.building_action(game.id,'enter',building_id='estate:'+identity)
    choose(engine,game.id,'visit:lesson');choose(engine,game.id,'visit:resolve:lesson:0');choose(engine,game.id,'leave')
    game=engine.store.load(game.id);claims=copy.deepcopy(game.building_state['visit_usage'])
    location=game.player.location_id
    engine._apply_world_transition(game,engine._plan_world_transition(game,'demon','rift',route_id='rift:human:demon',reason='隔离测试裂缝往返'))
    assert game.building_state['visit_usage']==claims
    assert not any(r['id']=='estate:'+identity for r in buildings.local_rows(game))
    engine._apply_world_transition(game,engine._plan_world_transition(game,'human','rift',route_id='rift:demon:human',arrival_location=location,reason='隔离测试裂缝返程'))
    engine.store.save(game)
    engine.building_action(game.id,'enter',building_id='estate:'+identity);choose(engine,game.id,'visit:lesson')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']
    assert engine.store.load(game.id).building_state['visit_usage']==claims


def test_permission_loss_cannot_leak_industry_books_or_claim(local):
    engine,game=local;game,identity=buy(engine,game,'shop')
    engine.building_action(game.id,'enter',building_id='estate:'+identity);choose(engine,game.id,'visit:lesson')
    old=engine.get_game(game.id)['pending_event']['id']
    saved=engine.store.load(game.id);saved.economy_v2['estates'][identity].update(owner_kind='background',owner_id=saved.player.world)
    engine.store.save(saved)
    with pytest.raises(ValueError):engine.choose(game.id,'visit:resolve:lesson:0',event_id=old)
    shown=engine.get_game(game.id)
    assert not shown['buildings']['inside'] and not shown['pending_event']
    assert not engine.store.load(game.id).building_state.get('visit_usage')


@pytest.mark.parametrize('value',[True,0,2,-1,'1',None])
def test_visit_claim_schema_is_strict(local,value):
    _,game=local
    state=dict(version=1,sequence=0,records={},cultivation={},visit_usage={'estate:test':{'insight':value}})
    with pytest.raises(ValueError):decode_state(state)
