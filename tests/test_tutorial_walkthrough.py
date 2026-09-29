import copy
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.system.tutorial_walkthrough import STEPS

@pytest.fixture
def guide(tmp_path):
    e=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    g=e.create_game('亲手问道','supreme_wood','dao',seed=1481)
    e.tutorial_action(g['id'],'enable')
    return e,g['id']

def advance(e,key):
    g=e.get_game(key)['tutorial']['guide'];s=g['step'];target=None
    action={'practice':'guide_practice','treasure':'guide_treasure','equip':'guide_equip',
            'meet':'guide_meet','mentor_choice':'guide_accept','join':'guide_join'}.get(s,'guide_next')
    if s=='equip':
        if g['art']:target=g['art']['id']
        else:action='guide_next'
    if s in {'meet','mentor_choice'} and g['mentor_reason']:action='guide_next'
    if s=='join':
        if g['admissions']:target=g['admissions'][0]['id']
        else:action='guide_next'
    return e.tutorial_action(key,action,s,target)

def reach(e,key,step):
    for _ in STEPS:
        if e.get_game(key)['tutorial']['guide']['step']==step:return
        advance(e,key)
    raise AssertionError(step)

def test_full_course_changes_real_state_without_time_or_randomness(guide):
    e,key=guide;before=e.store.load(key)
    for _ in STEPS:advance(e,key)
    g=e.store.load(key)
    assert g.player.tutorial_state['guide_completed']
    assert not g.player.tutorial_state['enabled']
    assert g.player.age==before.player.age and g.rng_state==before.rng_state
    assert g.player.opportunity==before.player.opportunity+5
    assert g.player.technique and g.player.master['realm_index']==3
    assert g.player.faction_id in g.sects and g.player.faction_join_age==g.player.age
    assert g.pending_event==before.pending_event

def test_steps_cannot_skip_training_or_claim_rewards_twice(guide):
    e,key=guide
    with pytest.raises(ValueError):e.tutorial_action(key,'guide_treasure','treasure')
    reach(e,key,'practice')
    with pytest.raises(ValueError):e.tutorial_action(key,'guide_next','practice')
    advance(e,key);first=e.store.load(key)
    e.tutorial_action(key,'guide_practice','practice')
    assert e.store.load(key).player.opportunity==first.player.opportunity
    reach(e,key,'treasure');advance(e,key);first=e.store.load(key)
    e.tutorial_action(key,'disable');e.tutorial_action(key,'enable')
    e.tutorial_action(key,'guide_treasure','treasure')
    assert e.store.load(key).player.inventory==first.player.inventory
    assert len(e.store.load(key).history)==len(first.history)

def test_actual_sect_choice_is_validated_and_persists(guide):
    e,key=guide;reach(e,key,'join')
    choices=e.get_game(key)['tutorial']['guide']['admissions'];assert choices
    with pytest.raises(ValueError):e.tutorial_action(key,'guide_join','join','nonexistent')
    chosen=choices[-1]['id'];e.tutorial_action(key,'guide_join','join',chosen)
    e.tutorial_action(key,'guide_join','join',choices[0]['id'])
    assert e.store.load(key).player.faction_id==chosen
    assert e.get_game(key)['faction']['member']

def test_existing_master_and_sect_are_never_replaced(guide):
    e,key=guide;reach(e,key,'mentor_choice');advance(e,key);reach(e,key,'join');advance(e,key)
    g=e.store.load(key);master=copy.deepcopy(g.player.master);sect=g.player.faction_id
    g.player.tutorial_state['guide_index']=STEPS.index('meet');e.store.save(g)
    assert e.get_game(key)['tutorial']['guide']['mentor_reason']
    reach(e,key,'sect')
    after=e.store.load(key)
    assert after.player.master['id']==master['id'] and after.player.faction_id==sect

def test_pending_event_pauses_instead_of_overwriting(guide):
    import random
    e,key=guide;reach(e,key,'practice');g=e.store.load(key);g.player.realm_index=1
    g.pending_event=e._instantiate_event(e.events_by_id['EVT_TECHNIQUE_STELE_001'],g,random.Random(2));e.store.save(g)
    event=copy.deepcopy(g.pending_event)
    with pytest.raises(ValueError):e.tutorial_action(key,'guide_practice','practice')
    assert e.store.load(key).pending_event==event

def test_high_realm_guide_does_not_grant_or_replace(guide):
    e,_=guide;key=e.create_game('上界重温','supreme_wood','dao',seed=1481,preset_id='true_immortal')['id']
    g=e.store.load(key);g.pending_event=None;g.heavenly_court['open_election']=None;e.store.save(g)
    e.tutorial_action(key,'enable');before=e.store.load(key)
    for _ in STEPS:advance(e,key)
    after=e.store.load(key)
    assert after.player.inventory==before.player.inventory and after.player.opportunity==before.player.opportunity
    assert after.player.technique.id==before.player.technique.id and not after.player.master

def test_mentor_decline_uses_real_event_choice(guide):
    e,key=guide;reach(e,key,'mentor_choice');info=e.get_game(key)['tutorial']['guide']
    assert info['event']['choices'][1]['id']=='guide_decline'
    e.tutorial_action(key,'guide_decline','mentor_choice')
    assert e.store.load(key).player.master is None
    assert e.store.load(key).player.tutorial_state['mentor_result']=='declined'

def test_rootless_training_does_not_create_cultivation(guide):
    e,_=guide;key=e.create_game('凡人','none','dao',seed=1481)['id'];e.tutorial_action(key,'enable')
    reach(e,key,'practice');before=e.store.load(key);advance(e,key);after=e.store.load(key)
    assert after.player.spirit_root=='none' and after.player.opportunity==before.player.opportunity
