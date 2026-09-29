import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import Player

@pytest.fixture
def lesson(tmp_path):
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    data=engine.create_game('初问道','supreme_wood','dao',seed=1480)
    return engine,engine.store.load(data['id'])

def reach_mentor(e,g):
    e.tutorial_action(g.id,'enable')
    e.tutorial_action(g.id,'navigate',6)

def test_opt_in_progress_resume_and_legacy_save(lesson):
    e,g=lesson
    assert not e.get_game(g.id)['tutorial']['enabled']
    legacy=g.player.to_dict();legacy.pop('tutorial_state')
    assert Player.from_dict(legacy).tutorial_state=={}
    e.tutorial_action(g.id,'enable');e.tutorial_action(g.id,'navigate',3)
    e.tutorial_action(g.id,'disable')
    assert e.get_game(g.id)['tutorial']['step']==3
    assert e.tutorial_action(g.id,'enable')['tutorial']['step']==3
    e.tutorial_action(g.id,'finish')
    assert e.get_game(g.id)['tutorial']['completed']
    assert not e.get_game(g.id)['tutorial']['enabled']

def test_deterministic_mentor_is_persistent_and_only_once(lesson):
    e,g=lesson;reach_mentor(e,g)
    before=e.store.load(g.id);age,rng=before.player.age,before.rng_state
    shown=e.tutorial_action(g.id,'offer_mentor');key=shown['tutorial']['mentor']['id']
    assert e.store.load(g.id).notable_npcs[key].realm_index==3
    assert e.store.load(g.id).player.master is None
    assert e.store.load(g.id).pending_event==before.pending_event
    e.tutorial_action(g.id,'accept_mentor')
    e.get_game(g.id)  # Normalize standard relationship defaults before comparison.
    after=e.store.load(g.id)
    assert after.player.master['id']==key and after.player.master['realm_index']==3
    assert after.player.age==age and after.rng_state==rng
    assert after.player.inventory==before.player.inventory and after.player.opportunity==before.player.opportunity
    original=copy.deepcopy(after.player.master);history=len(after.history)
    e.tutorial_action(g.id,'disable');e.tutorial_action(g.id,'enable')
    e.tutorial_action(g.id,'offer_mentor');e.tutorial_action(g.id,'accept_mentor')
    after=e.store.load(g.id)
    assert after.player.master==original and len(after.history)==history
    assert len([k for k in after.notable_npcs if k.startswith('tutorial_mentor:')])==1
    # The real relationship actions recognize the same authoritative NPC.
    e.request_from_master(g.id,'consult')
    assert e.store.load(g.id).player.opportunity>before.player.opportunity
    assert e.store.load(g.id).player.master['id']==key

def test_decline_never_grants_or_reoffers_master(lesson):
    e,g=lesson;reach_mentor(e,g)
    e.tutorial_action(g.id,'offer_mentor');before=e.store.load(g.id)
    e.tutorial_action(g.id,'decline_mentor');e.tutorial_action(g.id,'accept_mentor')
    after=e.store.load(g.id)
    assert not after.player.master and after.player.fame==before.player.fame
    assert after.player.tutorial_state['mentor_result']=='declined'

@pytest.mark.parametrize('condition',['master','high_realm','sealed','upper_world','pending','trial','dead','prison'])
def test_reading_allowed_but_mentor_cannot_override_current_life(lesson,condition):
    e,g=lesson
    if condition=='master':g.player.master={'id':'original','name':'旧师','alive':True,'realm_index':3,'world':'human'}
    elif condition=='high_realm':g.player.realm_index=3
    elif condition=='sealed':g.player.sealed_cultivation={'realm_index':9,'layer':1}
    elif condition=='upper_world':g.player.world='spirit';g.player.location_id=e.maps.default_location('spirit')
    elif condition in {'pending','trial'}:
        g.player.realm_index=1
        g.pending_event=e._instantiate_event(e.events_by_id['EVT_TECHNIQUE_STELE_001'],g,random.Random(2))
        if condition=='trial':g.active_trial={'kind':'test','event_ids':['EVT_TECHNIQUE_STELE_001']}
    elif condition=='dead':g.player.alive=False
    elif condition=='prison':g.player.imprisonment={'captor_name':'守卫'}
    e.store.save(g);reach_mentor(e,g)
    assert not e.get_game(g.id)['tutorial']['can_offer']
    before=e.store.load(g.id)
    with pytest.raises(ValueError):e.tutorial_action(g.id,'offer_mentor')
    after=e.store.load(g.id)
    assert after.player.master==before.player.master and after.pending_event==before.pending_event

def test_mentor_death_during_paused_lesson_is_not_undone(lesson):
    e,g=lesson;reach_mentor(e,g)
    e.tutorial_action(g.id,'offer_mentor');g=e.store.load(g.id)
    npc=g.notable_npcs[g.player.tutorial_state['mentor_id']];npc.alive=False;npc.death_reason='客途陨落';e.store.save(g)
    with pytest.raises(ValueError):e.tutorial_action(g.id,'accept_mentor')
    assert not e.store.load(g.id).notable_npcs[npc.id].alive
    assert not e.store.load(g.id).player.master

@pytest.mark.parametrize('step',[-1,10,True,2.5,'6'])
def test_invalid_chapters_are_rejected(lesson,step):
    e,g=lesson;e.tutorial_action(g.id,'enable')
    with pytest.raises(ValueError):e.tutorial_action(g.id,'navigate',step)
