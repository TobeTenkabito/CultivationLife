"""New-game array spacing and preservation of adopted physical facilities."""
import copy
import json
from pathlib import Path

import pytest

from cultivation_life.content_registry import CONTENT_DOCUMENTS
from cultivation_life.models import GameState
from cultivation_life.system.teleport_sites import arrays
from cultivation_life.system.teleport_system import public_teleport
from test_economy_network import economy

WORLDS=[world for world in CONTENT_DOCUMENTS['maps.json']['worlds'] if world not in {'lost','rift'}]
CHANGED={'human','spirit','demon','true_demon','phantom_underworld','hell','monster_realm'}


@pytest.mark.parametrize('world',WORLDS)
def test_starting_arrays_are_nonadjacent_on_the_real_road_graph(world):
    geography=CONTENT_DOCUMENTS['maps.json']['worlds'][world]
    nodes={r['id'] for r in geography['locations'] if r.get('teleport_array')}
    assert len(nodes)>=4 and geography['default'] in nodes
    assert not any({road['from'],road['to']}<=nodes for road in geography['routes'])
    if world in CHANGED:
        assert all(not r.get('min_realm_index',0) for r in geography['locations'] if r['id'] in nodes)


def test_real_new_game_can_use_the_repositioned_array_with_existing_permission_rules(economy):
    engine,game=economy
    old_age=game.player.age
    info=public_teleport(game,engine.maps)
    assert info['origin']['id']=='wudi_plain'
    destinations={row['id'] for row in info['destinations']}
    assert 'expanse_human_12' in destinations and 'mirror_lake' not in destinations
    engine.store.save(game)
    saved=engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError,match='许可'):
        engine.teleport_action(game.id,'travel','expanse_human_12')
    assert engine.store._path(game.id).read_bytes()==saved
    shown=engine.teleport_action(game.id,'bribe','expanse_human_12')
    assert shown['player']['location_id']=='expanse_human_12' and shown['player']['age']==old_age
    loaded=engine.store.load(game.id)
    assert loaded.player.world=='human' and public_teleport(loaded,engine.maps)['origin']['id']=='expanse_human_12'


def legacy_sites(game):
    book=game.economy_v2.setdefault('organization_sites',{})
    book['initial_arrays']={key:value for key,value in book.get('initial_arrays',{}).items() if not key.startswith('human:')}
    book['initial_arrays'].update({'human:wudi_plain':'tianjian','human:mirror_lake':'wanmo'})
    return book


def test_adopted_arrays_keep_their_address_owner_and_no_new_content_gifts(economy):
    engine,game=economy
    legacy_sites(game)
    before=copy.deepcopy(game.to_dict())
    projected=arrays(game,engine.maps,'human')
    assert set(projected)=={'wudi_plain','mirror_lake'}
    assert projected['mirror_lake']['owner_id']=='wanmo'
    assert game.to_dict()==before
    game=GameState.from_dict(before)
    assert arrays(game,engine.maps,'human')==projected
    engine.store.save(game)
    saved=engine.store._path(game.id).read_bytes()
    # Historical neighbors remain physical sites but cannot bypass the travel rule.
    with pytest.raises(ValueError,match='目的地'):
        engine.teleport_action(game.id,'bribe','mirror_lake')
    assert engine.store._path(game.id).read_bytes()==saved


def test_repositioning_preserves_paid_arrays_and_does_not_revive_retired_sites(economy):
    engine,game=economy
    book=legacy_sites(game)
    book.setdefault('retired_arrays',{})['human:mirror_lake:wanmo']=True
    game.economy_v2.setdefault('teleport_arrays',{})['human:muling_desert']=dict(
        world='human',location='muling_desert',owner_id='tianjian',owner_kind='sect',built_year=game.player.age)
    before=copy.deepcopy(game.to_dict())
    projected=arrays(game,engine.maps,'human')
    assert set(projected)=={'wudi_plain','muling_desert'}
    assert projected['muling_desert']['owner_id']=='tianjian'
    assert game.to_dict()==before
    assert arrays(GameState.from_dict(before),engine.maps,'human')==projected
