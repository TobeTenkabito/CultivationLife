"""Public commands, persisted instance ownership and authored birth prerequisites."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.rules import max_mp, opportunity_required
from cultivation_life.runtime import encode_rng
from cultivation_life.system import spatial
from cultivation_life.system.ghost.progression import apply_soul_erosion, perform_reincarnation, spend_wangsheng_energy
from cultivation_life.engine.actions.exploration import enter_scene
from test_spatial_talismans import ready, occupy

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('realm,layer', [(9,1),(9,9),(10,4),(11,9),(12,9)])
def test_custom_celestial_prerequisites(tmp_path, realm, layer):
    engine = GameEngine(ROOT, tmp_path)
    result = engine.create_game('仙脉前尘', 'supreme_metal', 'dao', 250,
        custom_start=dict(world='celestial', realm_index=realm, layer=layer))
    p = engine._load(result['id']).player
    assert p.immortal_veins[str(realm)] == (layer - 1) * 3
    assert all(p.immortal_veins[str(r)] == 27 for r in range(9,realm))
    if realm > 9:
        assert p.immortal_body['level'] >= 20
    p.immortal_veins[str(realm)] += 1
    game = engine._load(result['id']); game.player = p; engine.store.save(game)
    assert engine._load(game.id).player.immortal_veins[str(realm)] == (layer - 1) * 3 + 1


def test_preset_and_asura_veins(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    from cultivation_life.content_registry import WORLD_SYSTEMS
    presets = [r for r in WORLD_SYSTEMS['quick_start_presets'] if r.get('enabled') and r['world']=='celestial' and r['realm_index']>=9]
    for preset in presets:
        result = engine.create_game('前尘', 'supreme_metal', 'dao', 251, preset_id=preset['id'])
        p = engine._load(result['id']).player
        assert p.immortal_veins[str(p.realm_index)] == (p.layer-1)*3
    result = engine.create_game('魔脉前尘','supreme_metal','demonic',252,
        custom_start=dict(world='asura',realm_index=10,layer=8))
    p=engine._load(result['id']).player
    assert p.asura_cultivation['veins']=={'9':27,'10':21}
    assert p.asura_cultivation['conversion']==5


@pytest.mark.parametrize('boundary', range(5,9))
def test_rift_gate_cost_and_natural_exit(ready, boundary):
    engine, game = ready
    scene=occupy(engine,game)
    scene['exit_realm']=boundary
    for realm,layer,allowed in [(5,9,False),(6,9,False),(7,1,boundary<7),(7,7,boundary<=7),(8,6,boundary<8),(8,7,True)]:
        game.player.realm_index,game.player.layer=realm,layer
        game.player.mp=max_mp(game.player)
        engine.store.save(game)
        assert spatial.public(game)['can_open']==allowed
        if not allowed:
            before=engine.store.load(game.id).to_dict()
            with pytest.raises(ValueError,match='合体'):
                engine.spatial_action(game.id,'open')
            assert engine.store.load(game.id).to_dict()==before
        else:
            engine.spatial_action(game.id,'open')
            assert engine.store.load(game.id).player.mp==pytest.approx(max_mp(game.player)*.75)
    game.player.realm_index,game.player.layer=4,1
    rift=spatial.new_rift(game,random.Random(3),engine.maps,controlled=True)
    rift['destination']='human';engine.store.save(game)
    with patch.dict(spatial.cfg(),outcome_weights={'passage':1}):
        result=engine.spatial_action(game.id,'enter',{'target_id':rift['id']})
    assert result['player']['world']=='human'


def test_random_boundaries_are_persisted_and_read_only(ready):
    engine,game=ready
    scenes=[spatial.create_instance(game,random.Random(i),'secluded') for i in range(25)]
    assert {s['exit_realm'] for s in scenes}=={5,6,7,8}
    game.spatial_state['current']=scenes[0]['id']
    before=copy.deepcopy(game.to_dict())
    for _ in range(3): spatial.public(game)
    assert game.to_dict()==before
    restored=GameState.from_dict(before)
    assert restored.spatial_state==game.spatial_state


def test_local_societies_use_original_people_and_keep_outside_identity(ready):
    engine,game=ready
    scene=occupy(engine,game,'lost')
    external=(game.player.faction_id,copy.deepcopy(game.family))
    view=engine.get_game(game.id)
    assert {'faction','family'}<=set(view['spatial']['panels'])
    sect=view['spatial']['scene']['society']['sects'][0]
    engine.spatial_action(game.id,'join_sect',{'target_id':sect['id']})
    engine.spatial_action(game.id,'study_sect',{'target_id':sect['id']})
    with pytest.raises(ValueError,match='已经学过'):
        engine.spatial_action(game.id,'study_sect',{'target_id':sect['id']})
    family=view['spatial']['scene']['society']['families'][0]
    engine.spatial_action(game.id,'move',{'target_id':family['location_id']})
    engine.spatial_action(game.id,'join_family',{'target_id':family['id']})
    restored=engine._load(game.id)
    assert restored.player.faction_id==external[0] and restored.family==external[1]
    assert spatial.current(restored)['joined_family']==family['id']
    other=spatial.create_instance(restored,random.Random(7),'lost')
    enter_scene(engine._exploration_dependencies(),restored,other,random.Random(8));engine.store.save(restored)
    with pytest.raises(ValueError,match='当前失落'):
        engine.spatial_action(game.id,'join_family',{'target_id':family['id']})
    assert spatial.current(engine._load(game.id)).get('joined_family') is None


def test_ghost_ninth_rank_freezes_growth_after_reincarnation(tmp_path):
    engine=GameEngine(ROOT,tmp_path)
    view=engine.create_game('九阶魂基','supreme_metal','ghost',253,
        custom_start=dict(world='reincarnation',realm_index=9,layer=9))
    game=engine._load(view['id']);p=game.player
    p.ghost_soul_erosion_rate_pp=.03
    before=p.ghost_intrinsic_hp_current
    apply_soul_erosion(p,3)
    assert p.ghost_soul_erosion_rate_pp==.03 and p.ghost_intrinsic_hp_current<before
    p.opportunity=opportunity_required(p)
    perform_reincarnation(p)
    assert p.realm_index==1
    apply_soul_erosion(p,3)
    assert p.ghost_soul_erosion_rate_pp==.03
    p.ghost_wangsheng_energy=2
    spend_wangsheng_energy(p)
    assert p.ghost_soul_erosion_rate_pp==pytest.approx(.01)
    engine.store.save(game)
    assert engine.get_game(game.id)['ghost_system']['erosion_growth_stopped']


def test_spatial_events_real_advance_reload_submit_and_silence(ready):
    engine,game=ready
    occupy(engine,game,'lost')
    game.settings['silent_events']=False;engine.store.save(game)
    view=engine.advance(game.id,'rest',1)
    pending=view['pending_event']
    assert pending['id'].startswith('EVT_WANDER_SHARED_')
    engine.get_game(game.id)
    result=engine.choose(game.id,'leave',event_id=pending['id'])
    assert result['pending_event'] is None
    game=engine._load(game.id);game.settings['silent_events']=True;engine.store.save(game)
    assert engine.advance(game.id,'rest',1)['pending_event'] is None


def test_all_new_events_real_load_and_rewards(ready):
    engine,game=ready
    definitions=[e for e in engine.events if e['id'].startswith('EVT_WANDER_')]
    assert len(definitions)==45
    for event in definitions:
        game=engine._load(game.id)
        game.pending_event=engine._instantiate_event(event,game,random.Random(1))
        engine.store.save(game)
        assert engine.get_game(game.id)['pending_event']['id']==event['id']
        result=engine.choose(game.id,'ponder',event_id=event['id'])
        assert any(r['event_id']==event['id'] for r in result['history'])
        assert result['pending_event'] is None


@pytest.mark.parametrize('world', ['human','demon','spirit','true_demon','monster_realm','phantom_underworld',
                                  'hell','celestial','asura','nether','reincarnation','lost','rift'])
def test_new_events_are_reachable_only_in_correct_world(ready, monkeypatch, world):
    engine,game=ready
    game.player.world=world
    game.settings['silent_events']=False
    for prefix in ('EVT_WANDER_SHARED_',f'EVT_WANDER_{world.upper()}_'):
        monkeypatch.setattr(engine,'_event_weight',lambda e,g,a: 1 if e['id'].startswith(prefix) else 0)
        event=engine._select_event(game,'rest',random.Random(9))
        if world in {'lost','rift'} and prefix!='EVT_WANDER_SHARED_':
            assert event is None
        else:
            assert event['id'].startswith(prefix)
