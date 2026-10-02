from pathlib import Path
import random
from unittest.mock import patch
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState

@pytest.fixture
def ready(tmp_path):
    e=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    g=e.store.load(e.create_game('静修','supreme_metal','dao',745)['id'])
    g.settings['silent_events']=True
    g.pending_event=None
    return e,g


def test_setting_defaults_and_persistence(ready):
    e,g=ready
    legacy=g.to_dict();legacy['settings'].pop('silent_events')
    assert not GameState.from_dict(legacy).settings['silent_events']
    e.store.save(g)
    assert e.update_setting(g.id,'silent_events',True)['settings']['silent_events']
    assert e.store.load(g.id).settings['silent_events']
    assert not e.update_setting(g.id,'silent_events',False)['settings']['silent_events']


def test_automatic_producers_never_roll_or_generate(ready):
    e,g=ready
    class NoRoll:
        def __getattr__(self,name):raise AssertionError('silent producer consumed RNG')
    rng=NoRoll()
    assert e._select_event(g,'cultivate',rng) is None
    for method in ['_maybe_relationship_sanction','_maybe_concubine_proposal','_maybe_personal_revenge',
                   '_maybe_probability_story_event','_maybe_xiang_node_event','_maybe_founded_sect_pressure',
                   '_maybe_affinity_gift','_maybe_faction_event','_advance_concubine_aftermath']:
        assert not getattr(e,method)(g,rng)
    assert g.pending_event is None


def test_periodic_lightning_is_never_silent(ready):
    e,g=ready
    p=g.player;p.world='spirit';p.realm_index=6;p.layer=1
    p.location_id=e.maps.normalize_location('spirit',None)
    p.next_tribulation_age=p.age
    e._check_tribulation(g,random.Random(1))
    assert g.pending_event['id']=='EVT_PERIODIC_THUNDER_001'
    assert g.active_trial
    e.store.save(g)
    e.update_setting(g.id,'silent_events',True)
    assert e.store.load(g.id).pending_event['id']=='EVT_PERIODIC_THUNDER_001'


def test_asura_manual_breakthrough_trial_remains(ready):
    e,g=ready
    p=g.player;p.path='demonic';p.world='asura';p.realm_index=9;p.layer=9
    p.location_id=e.maps.normalize_location('asura',None)
    p.asura_cultivation.update(conversion=5,veins={'9':27},body_level=20)
    p.opportunity=1e12;p.awaiting_major_breakthrough=True
    e.store.save(g)
    e.breakthrough(g.id)
    result=e.store.load(g.id)
    assert result.active_trial['kind']=='asura_breakthrough'
    assert result.pending_event


def test_advancement_is_uninterrupted_but_still_advances_world(ready):
    e,g=ready
    e.store.save(g)
    before=g.player.age
    for _ in range(3):
        result=e.advance(g.id,'rest')
        assert result['pending_event'] is None
    assert e.store.load(g.id).player.age>before


def test_silence_does_not_clear_existing_player_event(ready):
    e,g=ready
    g.player.realm_index=1
    event=e._instantiate_event(e.events_by_id['EVT_ENCOUNTER_INJURED_001'],g,random.Random(1))
    g.pending_event=event
    e.store.save(g)
    e.update_setting(g.id,'silent_events',True)
    assert e.store.load(g.id).pending_event['id']==event['id']
