"""Paid conversion through real commands, legacy queue recovery and atomic failure."""
import copy
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.system.conversion import COSTS, retire_events
from cultivation_life.system.doctrine.provider import ensure

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    gid=engine.create_game('转化验收','supreme_metal','dao',9921,preset_id='true_immortal')['id']
    g=engine._load(gid);g.pending_event=None;g.player.immortal_power_converted=False
    g.player.immortal_conversion_stage=0;g.player.mp=0;g.player.opportunity=2000
    g.heavenly_court['open_election']=None;engine.store.save(g);engine.get_game(gid)
    return engine,engine._load(gid)


def test_conversion_is_one_paid_stage_no_rng_or_time_and_one_reward(setup):
    engine,g=setup;age,rng=g.player.age,g.rng_state
    for stage,cost in enumerate(COSTS,1):
        before=g.player.opportunity
        engine.doctrine_action(g.id,'convert');g=engine._load(g.id)
        assert g.player.opportunity==before-cost and g.player.immortal_conversion_stage==stage
        assert g.player.age==age and g.rng_state==rng and g.pending_event is None
    before=engine.store.load(g.id).to_dict()
    with pytest.raises(ValueError):engine.doctrine_action(g.id,'convert')
    assert engine.store.load(g.id).to_dict()==before
    assert sum(h.event_id=='SYS_IMMORTAL_POWER_CONVERTED' for h in g.history)==1


def test_insufficient_and_suppression_leave_saved_state_unchanged(setup):
    engine,g=setup;g.player.opportunity=99;engine.store.save(g)
    before=engine.store.load(g.id).to_dict()
    with pytest.raises(ValueError,match='机缘'):engine.doctrine_action(g.id,'convert')
    assert engine.store.load(g.id).to_dict()==before


def test_legacy_progress_discounts_current_stage_only(setup):
    engine,g=setup;ensure(g);g.doctrine_state['player']['conversion_progress']=50
    engine.store.save(g);engine.doctrine_action(g.id,'convert');saved=engine._load(g.id)
    assert saved.player.opportunity==g.player.opportunity-50
    assert saved.doctrine_state['player']['conversion_progress']==0


def test_retired_nodes_preserve_followup_objects_without_randomness(setup):
    _,g=setup
    reward={'id':'earned_reward','runtime':{'amount':71},'choices':[{'id':'take','enabled':True}]}
    event={'id':'ordinary','_followup_event':{'id':'EVT_ASURA_CONVERSION_2','_followup_event':reward}}
    g.pending_event={'id':'EVT_IMMORTAL_CONVERSION_1','_followup_event':event}
    g.active_trial={'kind':'immortal_conversion'};rng=g.rng_state
    assert retire_events(g)
    assert g.pending_event is event and event['_followup_event'] is reward
    assert g.active_trial is None and g.rng_state==rng and g.player.immortal_conversion_stage==0
    state=copy.deepcopy(g.to_dict());assert not retire_events(g);assert state==g.to_dict()


def test_asura_conversion_requires_payment_and_does_not_queue_trial(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    gid=engine.create_game('煞元验收','supreme_metal','demonic',9922,preset_id='asura_upper')['id']
    g=engine._load(gid);g.pending_event=None;g.active_trial=None
    g.player.asura_cultivation['conversion']=0;g.player.opportunity=99
    engine.store.save(g);engine.get_game(gid);before=engine.store.load(gid).to_dict()
    with pytest.raises(ValueError,match='机缘'):engine.asura_action(gid,'convert')
    assert before==engine.store.load(gid).to_dict()
    g=engine._load(gid);g.player.opportunity=100;engine.store.save(g)
    engine.asura_action(gid,'convert');g=engine._load(gid)
    assert g.player.opportunity==0 and g.player.asura_cultivation['conversion']==1
    assert g.pending_event is None and g.active_trial is None
