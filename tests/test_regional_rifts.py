"""Real rift/node commands share entry-time finance and original lifecycles."""
import copy
import random
from unittest.mock import patch

import pytest

from test_regional_calendar import regional
from cultivation_life.engine.world import regions
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import spatial
from cultivation_life.system.economy.ledger import transfer_value


def prepare(engine, game, years=10):
    game.player.realm_index=4; game.player.layer=1
    game.player.hp=max_hp(game.player); game.player.mp=max_mp(game.player)
    for _ in range(years):
        game.player.age += 1
        engine._advance_world_year(game, random.Random(game.player.age), [], encounters=False)
    game.pending_event=None
    engine.store.save(game)
    return game


def node(engine, game, destination, kind='node'):
    row=spatial.new_rift(game, random.Random(8), engine.maps, controlled=True)
    row.update(kind=kind, destination=destination)
    engine.store.save(game)
    return row['id']


def enter(engine, identity, target, outcome='passage'):
    # Fix only the random branch, retaining the real guard, transition,
    # catch-up, payment, save and presentation machinery.
    with patch.object(spatial, 'outcome_weights', return_value={outcome:1}):
        return engine.spatial_action(identity, 'enter', {'target_id':target})


@pytest.mark.parametrize('kind', ['node','rift'])
@pytest.mark.parametrize('destination', sorted(regions.worlds()-{'human'}))
def test_actual_rift_entry_catches_only_destination_and_pays_once(regional, kind, destination):
    engine, game=regional
    prepare(engine,game)
    clocks={w:r['year'] for w,r in game.world_simulation['regions'].items()}
    transfer_value(game, 'background:human', 'background:'+destination, 123, '节点前异界托管')
    target=node(engine,game,destination,kind)
    # Prepare the ordinary local shelf once, as a real opened page does.
    engine.get_game(game.id)
    before=engine.store.load(game.id).to_dict()
    for _ in range(2):
        shown=engine.get_game(game.id)
        assert all('destination' not in row for row in shown['spatial']['rifts'])
    assert engine.store.load(game.id).to_dict()==before
    enter(engine,game.id,target)
    saved=engine.store.load(game.id)
    assert saved.player.world==destination and saved.player.age==game.player.age
    assert saved.world_simulation['regions'][destination]['year']==saved.player.age
    assert all(r['year']==clocks[w] for w,r in saved.world_simulation['regions'].items() if w!=destination)
    assert saved.economy_v2['accounts']['regional:escrow:'+destination]['balance']==0
    assert not any(r['kind']=='credit' and r['amount']==123 for r in saved.world_simulation['deferred']['pending'][destination])
    assert (saved.player.realm_index,saved.player.layer)==(4,1)
    assert GameState.from_dict(saved.to_dict()).to_dict()==saved.to_dict()
    engine.get_game(game.id)  # Complete the original destination's lazy UI adoption.
    disk=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        enter(engine,game.id,target)
    assert engine.store._path(game.id).read_bytes()==disk


def test_instance_node_chain_freezes_outside_then_reconciles_real_society(regional):
    engine, game=regional
    prepare(engine,game,years=0)
    victim=game.sects['taixuan'].npcs[0]
    victim.lifespan=victim.age+1
    target=node(engine,game,'spirit')
    enter(engine,game.id,target,'secluded')
    game=engine.store.load(game.id)
    first=game.spatial_state['current']
    clocks=copy.deepcopy(game.world_simulation['regions'])
    engine.advance(game.id,'rest',1)
    game=engine.store.load(game.id)
    assert game.world_simulation['regions']==clocks
    assert game.sects['taixuan'].npcs[0].alive
    frozen_scene=copy.deepcopy(game.spatial_state['instances'][first])
    target=node(engine,game,'lost')
    enter(engine,game.id,target)
    game=engine.store.load(game.id)
    second=game.spatial_state['current']
    assert second!=first and game.player.world=='lost'
    engine.advance(game.id,'rest',1)
    game=engine.store.load(game.id)
    assert game.world_simulation['regions']==clocks
    assert game.spatial_state['instances'][first]==frozen_scene
    identities={n.id for n in __import__('cultivation_life.spatial_people',fromlist=['people']).people(game)}
    target=node(engine,game,'spirit')
    enter(engine,game.id,target)
    arrived=engine.store.load(game.id)
    assert arrived.spatial_state['current'] is None and arrived.player.world=='spirit'
    assert arrived.world_simulation['regions']['spirit']['year']==arrived.player.age
    assert arrived.world_simulation['regions']['human']==clocks['human']
    assert not arrived.sects['taixuan'].npcs[0].alive
    economy=arrived.economy_v2['organizations']['organization:sect:taixuan']
    assert economy['produced']>0
    assert not identities.intersection(arrived.world_npcs)


def test_same_year_nodes_and_reload_do_not_repeat_years_or_receipts(regional):
    engine,game=regional
    prepare(engine,game)
    transfer_value(game,'background:human','background:spirit',123,'节点往返托管')
    target=node(engine,game,'spirit');enter(engine,game.id,target)
    engine.get_game(game.id)
    first=engine.store.load(game.id)
    sects={k:s.to_dict() for k,s in first.sects.items() if s.world=='spirit'}
    clock=copy.deepcopy(first.world_simulation['regions']['spirit'])
    applied=first.world_simulation['deferred']['applied']
    target=node(engine,first,'human');enter(engine,game.id,target)
    game=engine.store.load(game.id)
    target=node(engine,game,'spirit');enter(engine,game.id,target)
    final=engine.store.load(game.id)
    assert {k:s.to_dict() for k,s in final.sects.items() if s.world=='spirit'}==sects
    assert final.world_simulation['regions']['spirit']==clock
    assert final.world_simulation['deferred']['applied']==applied


@pytest.mark.parametrize('invalid',['expired','location','event'])
def test_invalid_node_never_wakes_destination_or_consumes_protection(regional,invalid):
    engine,game=regional
    prepare(engine,game)
    target=node(engine,game,'spirit')
    row=next(r for r in game.spatial_state['rifts'] if r['id']==target)
    if invalid=='expired': row['expires_age']=game.player.age
    elif invalid=='location': row['location_id']='lanjiang_steppe'
    else:
        from test_travel_relationship_2160 import prepare_journey
        destination,_=prepare_journey(engine,game)
        engine.travel_map(game.id,destination)
        game=engine.store.load(game.id)
        assert game.pending_event['id']=='EVT_GUIXU_ANNOUNCE'
    engine.store.save(game)
    engine.get_game(game.id)
    disk=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError): enter(engine,game.id,target)
    assert engine.store._path(game.id).read_bytes()==disk


def test_failed_rift_catchup_rolls_back_and_retry_enters_once(regional):
    engine,game=regional
    prepare(engine,game)
    target=node(engine,game,'spirit')
    engine.get_game(game.id)
    disk=engine.store._path(game.id).read_bytes()
    real_tick=regions.tick
    def fail(*args,**kwargs):
        real_tick(*args,**kwargs)
        raise RuntimeError('isolated catch-up failure')
    with patch.object(regions,'tick',side_effect=fail),pytest.raises(RuntimeError):
        enter(engine,game.id,target)
    assert engine.store._path(game.id).read_bytes()==disk
    enter(engine,game.id,target)
    saved=engine.store.load(game.id)
    assert saved.player.world=='spirit' and saved.world_simulation['regions']['spirit']['year']==saved.player.age
