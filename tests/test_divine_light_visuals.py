"""Light cosmetics follow real unlocks, visibility and frozen combat capabilities."""
import copy
import random

import pytest

from cultivation_life.combat_visuals import combat_identity,report_visuals
from cultivation_life.rules import public_player
from cultivation_life.system.divine_lights import IDS,visual_lights
from cultivation_life.system.cultivation_ranks import mask_unrevealed
from test_immortal_cultivation import prepared


@pytest.mark.parametrize('level,count',[(0,0),(9,0),(10,1),(19,1),(20,2),(30,3),(40,4),(50,5)])
def test_cosmetic_unlocks_need_body_not_training_or_realm(prepared,level,count):
    _,g,_=prepared;p=g.player;p.realm_index=12;p.immortal_body={'level':level}
    before=copy.deepcopy(p.immortal_body)
    assert public_player(p)['visual_lights']==list(IDS[:count])
    assert visual_lights({'realm_index':12,'immortal_body_level':level})==list(IDS[:count])
    assert p.immortal_body==before


def test_frozen_visual_identity_is_not_recolored_after_training(prepared):
    _,g,_=prepared;g.player.immortal_body={'level':10}
    target={'target_name':'原始战报','combat_type':'cultivator'}
    identity=combat_identity(g,target);before=copy.deepcopy(identity)
    g.player.immortal_body={'level':50}
    report={'rounds':[{'initiative':'player','ordinary_exchange':{'opening':[100,100]}}]}
    visual=report_visuals(g,target,report,identity=identity)
    assert visual['teams']['hero'][0]['visual_lights']==['kun']
    assert identity==before


def test_trial_visuals_use_real_mirror_snapshot_after_player_changes():
    from scripts.calibrate_immortal_trials import fixture
    from cultivation_life.engine.progression.immortal_trials import initialize
    from cultivation_life.system.combat.trials import run_batch
    g=fixture('three_corpses',field_rank=8,doctrine_level=8)
    g.player.immortal_body={'level':50};battle=initialize(g,g.active_trial)
    _,rows=run_batch(battle,g.active_trial['battle_state'],random.Random(7),batch_size=1)
    g.player.immortal_body={'level':0};before=copy.deepcopy(g.to_dict())
    visual=report_visuals(g,g.active_trial['target'],{'rounds':rows})
    assert all(m['visual_lights']==list(IDS) for members in visual['teams'].values() for m in members)
    assert g.to_dict()==before


def test_concealed_people_do_not_leak_body_unlocks_through_cosmetics():
    public={'immortal_body_level':50,'body_training':100,'divine_sense_rank':40}
    mask_unrevealed(public,{'revealed':False,'realm_name':'练气'})
    assert public['visual_lights']==[] and public['immortal_body_level'] is None
    public={'immortal_body_level':30}
    mask_unrevealed(public,{'revealed':True})
    assert public['visual_lights']==['kun','zhen','kan']


def test_possession_visuals_follow_host_body(prepared):
    _,g,_=prepared;g.player.immortal_body={'level':50}
    g.player.ghost_host_body={'immortal_body_level':20,'name':'宿身','gender':'female'}
    g.player.ghost_core_state={}
    assert visual_lights(g.player,player=True)==['kun','zhen']
