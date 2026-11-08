"""Real teacher occupancy, annual settlement, invalidation and refund."""
import copy
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_yaochi_westward import pool,start,token,quote
from test_westward_ventures import npc
from cultivation_life.system.yaochi_guidance import annual_gain
from cultivation_life.system.westward_rules import project
from cultivation_life.person_assignments import research_assignment

@pytest.fixture
def lesson(pool):
    e,gid=pool;ident=npc(e,gid,'guidance-teacher');g=e._load(gid)
    g.world_npcs[ident].layer=2;e.store.save(g)
    return e,gid,ident

def test_real_lesson_delivers_expected_opportunity_without_trace(lesson):
    e,gid,ident=lesson;g=e._load(gid);before=g.player.opportunity;traces=g.player.immortal_traces
    expected=annual_gain(g)*10;age=g.player.age;start(e,gid,'guidance')
    assert research_assignment(e._load(gid),ident)['phase']=='guidance'
    with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):
        e.yaochi_action(gid,'westward_work',token(e,gid))
    g=e._load(gid)
    assert g.player.age==age+10 and project(g)['progress']==10
    assert g.player.opportunity-before==pytest.approx(expected)
    assert project(g)['opportunity_delivered']==pytest.approx(expected)
    assert g.player.immortal_traces==traces
    e.yaochi_action(gid,'westward_claim',token(e,gid))
    assert not project(e._load(gid)) and not research_assignment(e._load(gid),ident)

def test_teacher_departure_and_layer_change_reject_without_spending(lesson):
    e,gid,ident=lesson;start(e,gid,'guidance');g=e._load(gid)
    g.world_npcs[ident].location_id='jade_capital';e.store.save(g);before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='当面'):e.yaochi_action(gid,'westward_work',token(e,gid))
    assert e.store._path(gid).read_bytes()==before
    g=e._load(gid);g.world_npcs[ident].location_id=g.player.location_id;g.player.layer+=1;e.store.save(g)
    with pytest.raises(ValueError,match='境层'):e.yaochi_action(gid,'westward_work',token(e,gid))
    e.yaochi_action(gid,'westward_cancel',token(e,gid))
    assert e._load(gid).yaochi_state['merit']==100000 and not research_assignment(e._load(gid),ident)

def test_quote_requires_higher_actual_teacher_and_is_readonly(pool):
    e,gid=pool;g=e._load(gid)
    # Isolate the local scene, without synthesizing a tutor as a side effect of viewing.
    for n in g.world_npcs.values():n.location_id='jade_capital'
    for n in g.notable_npcs.values():n.location_id='jade_capital'
    e.store.save(g);before=copy.deepcopy(g.to_dict())
    from cultivation_life.system.yaochi_guidance import quote as lesson_quote
    assert lesson_quote(g,'')['reason'] and g.to_dict()==before
