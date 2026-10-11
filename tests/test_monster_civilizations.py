"""Behavioral boundaries of the independent ecology and civilization expansion."""
import copy
import json
from pathlib import Path
import time
from unittest.mock import patch
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, SectNpc
from cultivation_life.content_registry import CONTENT_DOCUMENTS
from cultivation_life.monster_civilization_content import validate_state, validate_content
from cultivation_life.system.monster_civilizations import core, actions, presentation

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def engine(tmp_path): return GameEngine(ROOT,tmp_path)

def make(engine,world='human'):
    path='dao' if world=='human' else 'monster'
    rank=4 if world=='human' else 9 if world=='nether' else 7
    made=engine.create_game('万灵验收','supreme_earth',path,21001,custom_start=dict(world=world,realm_index=rank),monster_species_id='fox' if path=='monster' else None)
    game=engine._load(made['id']);game.pending_event=None;game.active_trial=None;game.player.opportunity=10000
    game.player.location_id=core.config()['worlds'][world]['regions'][0]
    engine.store.save(game)
    return game

def cmd(engine,game,action,**options):
    view=engine.civilizations_view(game.id)
    return engine.civilizations_action(game.id,action,dict(expected_revision=view['revision'],**options))

def test_read_view_does_not_activate_or_save(engine):
    game=make(engine);before=engine.store._path(game.id).read_bytes()
    view=engine.civilizations_view(game.id)
    assert len(view['regions'])==6 and not any(r['known'] for r in view['regions'])
    assert engine.store._path(game.id).read_bytes()==before
    core.advance_year(game);assert game.monster_civilization_state=={}

@pytest.mark.parametrize('world',['unknown_world',0,'celestial'])
def test_invalid_requested_world_does_not_fall_back_to_human(engine,world):
    game=make(engine);before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):engine.civilizations_view(game.id,{'world':world})
    assert engine.store._path(game.id).read_bytes()==before


def test_all_retained_history_is_readable_on_last_page_without_writes(engine):
    game=make(engine);core.activate(game)
    for i in range(192):core.fact(game,'human','observation',game.player.location_id,f'史事{i:03}',[core.PLAYER],'observed')
    engine.store.save(game);before=engine.store._path(game.id).read_bytes()
    view=engine.civilizations_view(game.id,{'page':15})
    assert view['total']==192 and len(view['facts'])==12 and view['facts'][-1]['text']=='史事000'
    with pytest.raises(ValueError,match='页码'):engine.civilizations_view(game.id,{'page':16})
    assert engine.store._path(game.id).read_bytes()==before


def test_old_local_view_cannot_act_after_instant_location_change(engine):
    game=make(engine);view=engine.civilizations_view(game.id)
    game.player.location_id=core.config()['worlds']['human']['regions'][1];engine.store.save(game)
    engine._load(game.id)  # Prepare the ordinary arrival state before checking DLC atomicity.
    before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='地点已改变'):
        engine.civilizations_action(game.id,'observe',dict(expected_revision=view['revision'],expected_world=view['world'],expected_location=view['location']))
    assert engine.store._path(game.id).read_bytes()==before

@pytest.mark.parametrize('world',['human','monster_realm','phantom_underworld','nether'])
def test_actual_commands_roundtrip_and_no_economic_writes(engine,world):
    game=make(engine,world);before=copy.deepcopy(game.economy_v2);rng=copy.deepcopy(game.rng_state)
    cmd(engine,game,'observe');actual=engine.store.load(game.id)
    assert actual.economy_v2==before and actual.rng_state==rng
    assert set(actual.monster_civilization_state['worlds'])=={world}
    assert GameState.from_dict(actual.to_dict()).monster_civilization_state==actual.monster_civilization_state
    stale=engine.civilizations_view(game.id)
    cmd(engine,actual,'protect')
    baseline=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='已更新'):
        engine.civilizations_action(game.id,'guide',dict(expected_revision=stale['revision']))
    assert engine.store._path(game.id).read_bytes()==baseline

def test_migration_conserves_population_and_capacity():
    regions={'a':dict(populations={'deer':dict(p=1000,k=1000)}),'b':dict(populations={'deer':dict(p=0,k=8)}),'c':dict(populations={'deer':dict(p=1000,k=1000)})}
    assert core.migrate(regions,[('a','b'),('c','b')])==8
    assert sum(r['populations']['deer']['p'] for r in regions.values())==2000
    assert regions['b']['populations']['deer']['p']==8
    isolated=copy.deepcopy(regions);core.migrate(regions,[]);assert regions==isolated
    regions['b']['populations']['deer']['k']=0;core.migrate(regions,[('a','b')]);assert regions['b']['populations']['deer']['p']==8

def test_clan_branch_transfers_share_and_member_preserves_ancestry(engine):
    game=make(engine,'monster_realm');cmd(engine,game,'observe');cmd(engine,game,'found',name='青丘氏')
    original=engine.store.load(game.id);data=original.monster_civilization_state['worlds']['monster_realm'];parent=data['player_clan'];share=data['clans'][parent]['share']
    cmd(engine,original,'branch',name='望月支');actual=engine.store.load(game.id);data=actual.monster_civilization_state['worlds']['monster_realm'];child=data['clans'][data['player_clan']]
    assert child['parent_id']==parent and core.PLAYER not in data['clans'][parent]['members']
    assert child['share']+data['clans'][parent]['share']==share
    broken=copy.deepcopy(actual.monster_civilization_state);broken['worlds']['monster_realm']['clans'][parent]['parent_id']=child['id']
    with pytest.raises(ValueError,match='无环'):validate_state(broken)

def test_succession_references_existing_eligible_people(engine):
    game=make(engine,'monster_realm');data=core.activate(game)
    npc=SectNpc('actual-heir','真族员','族员',7,1,200,None,path='monster',world='monster_realm',location_id=game.player.location_id)
    game.world_npcs[npc.id]=npc
    clan=core.create_clan(game,'monster_realm',game.player.location_id,core.PLAYER,'承约氏')
    clan['members'].append(npc.id);game.player.alive=False
    core.politics(game,'monster_realm',data);assert clan['leader']==npc.id
    npc.custody={'captor':'test'};core.politics(game,'monster_realm',data);assert clan['leader'] is None and clan['status']=='dormant'
    assert game.world_npcs[npc.id] is npc

def test_closed_dlc_freezes_and_resumes_without_replay(engine):
    game=make(engine);actions.apply(game,'observe',{'expected_revision':0});actions.apply(game,'protect',{'expected_revision':1})
    data=game.monster_civilization_state['worlds']['human'];frozen=copy.deepcopy(game.monster_civilization_state)
    with patch.dict(CONTENT_DOCUMENTS,{},clear=True):
        game.player.age+=1000;core.advance_year(game)
        assert game.monster_civilization_state==frozen
    core.advance_year(game);assert data['ecology_clock']==1
    assert data['regions'][game.player.location_id]['effect']['until']==20

def test_observation_does_not_reveal_live_unobserved_populations(engine):
    game=make(engine);actions.apply(game,'observe',{'expected_revision':0});data=game.monster_civilization_state['worlds']['human'];before=copy.deepcopy(presentation.project(game)['regions'])
    game.player.age+=100;core.advance_year(game)
    after=presentation.project(game)['regions'];assert before==after
    assert all('populations' not in r for r in after if not r['known'])
    game.player.location_id=core.config()['worlds']['human']['regions'][1]
    first=core.config()['worlds']['human']['regions'][0]
    core.fact(game,'human','ecology',first,'远处发生的新变化',cause='test')
    assert not any(r['text']=='远处发生的新变化' for r in presentation.project(game)['facts'])

@pytest.mark.parametrize('opaque',[{'future':['keep']},{'worlds':['future-world'],'revision':{'future':1}},{'worlds':None,'revision':None}])
def test_unknown_subversion_preserved_and_execution_blocked(engine,opaque):
    game=make(engine);game.monster_civilization_state={'schema_version':99,**opaque};engine.store.save(game)
    assert engine.store.load(game.id).monster_civilization_state==game.monster_civilization_state
    assert not engine.civilizations_view(game.id)['supported']
    with pytest.raises(ValueError,match='子版本'):cmd(engine,game,'observe')

def test_court_uses_original_weights_and_freezes_off_world(engine):
    game=make(engine,'nether');data=core.activate(game)
    from cultivation_life.system.monster_civilizations.court import blocs
    assert [r['weight'] for r in blocs(game)]==[5,4,3,2,1]
    original=copy.deepcopy(game.upper_institutions)
    for i in range(100):game.player.age+=1;core.advance_year(game)
    assert data['political_clock']==1 and game.upper_institutions==original
    game.player.world='human'  # Test fixture only: no runtime move implementation.
    for i in range(100):game.player.age+=1;core.advance_year(game)
    assert data['political_clock']==1

def test_five_thousand_years_bounded_and_deterministic(engine):
    game=make(engine);actions.apply(game,'observe',{'expected_revision':0});other=copy.deepcopy(game)
    before=copy.deepcopy(game.economy_v2);rng=copy.deepcopy(game.rng_state)
    for g in (game,other):
        for i in range(5000):g.player.age+=1;core.advance_year(g)
    assert game.monster_civilization_state==other.monster_civilization_state
    assert game.economy_v2==before and game.rng_state==rng
    assert len(json.dumps(game.monster_civilization_state))<100000
    validate_state(game.monster_civilization_state)

@pytest.mark.parametrize('bloodline',[False,True])
@pytest.mark.parametrize('civilizations',[False,True])
def test_two_dlc_independent_toggle_matrix(engine,bloodline,civilizations):
    game=make(engine,'monster_realm');documents=copy.deepcopy(CONTENT_DOCUMENTS)
    if not bloodline:documents.pop('monster_bloodlines.json',None)
    if not civilizations:documents.pop(core.DOCUMENT,None)
    with patch.dict(CONTENT_DOCUMENTS,documents,clear=True):
        if civilizations:
            actions.apply(game,'observe',{'expected_revision':0});game.player.age+=1;core.advance_year(game)
            assert game.monster_civilization_state['worlds']['monster_realm']['ecology_clock']==1
        else:
            core.advance_year(game);assert game.monster_civilization_state=={}
            assert not core.marker(game)['available']

def test_real_loader_accepts_second_dlc_when_first_fails(tmp_path, monkeypatch):
    import shutil
    from cultivation_life.content_registry import ContentRegistry
    # The real loader updates class reports; this fixture must not leak its
    # deliberately incomplete extension set into subsequent DLC regressions.
    for name in ('loaded_documents', 'extension_report'):
        monkeypatch.setattr(ContentRegistry, name, getattr(ContentRegistry, name))
    for package in ('monster-bloodlines','monster-civilizations'):
        shutil.copytree(ROOT/'dlc'/package,tmp_path/'dlc'/package)
    bad=tmp_path/'dlc/monster-bloodlines/content/world.json'
    bad.write_text(json.dumps({'systems':{'monster_species':None}}),encoding='utf-8')
    loaded=ContentRegistry.load(ROOT/'content',tmp_path)
    report={r['id']:r['status'] for r in loaded.extension_report}
    assert report['official.monster-bloodlines']=='error'
    assert report['official.monster-civilizations']=='loaded'
    assert core.DOCUMENT in loaded.loaded_documents

def test_court_failed_vote_is_atomic_and_success_preserves_original_treasury(engine):
    game=make(engine,'nether');cmd(engine,game,'observe')
    engine.upper_institution_action(game.id,'join','')
    game=engine._load(game.id)
    from cultivation_life.system.institution_state import account
    state=account(game,create=True);state.update(joined=True,seat_active=True,bloc=4,support=[0,0,0,0,80],policy='study')
    # Only feathers/shells and own one vote support study: seven, insufficient.
    engine.store.save(game);before=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='八议权'):cmd(engine,game,'regime',target_id='strongest')
    assert engine.store._path(game.id).read_bytes()==before
    game=engine.store.load(game.id);state=account(game,create=True);state['support']=[100]*5;engine.store.save(game)
    baseline=copy.deepcopy(game.upper_institutions);economic=copy.deepcopy(game.economy_v2)
    cmd(engine,game,'regime',target_id='strongest');actual=engine.store.load(game.id)
    assert actual.monster_civilization_state['worlds']['nether']['court']['regime']=='strongest'
    assert actual.upper_institutions==baseline and actual.economy_v2==economic
