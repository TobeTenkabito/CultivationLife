"""Debug uses the original dungeon command, frozen receipts and isolated save."""
import copy
from pathlib import Path

import pytest

from cultivation_life.debug.runtime import Runtime
from test_seeded_dungeons import local

ROOT=Path(__file__).resolve().parents[1]


def test_dungeon_debug_discovery_replay_stale_guard_and_source_isolation(local,tmp_path):
    engine,game=local
    runtime=Runtime(ROOT,tmp_path/'debug',engine.store)
    sid=runtime.start(game.id)['session_id']
    runtime.execute('game view',session_id=sid)
    source=engine.store._path(game.id).read_bytes()
    session=runtime.load(sid)
    player=session['current']['game']['player']
    arguments=dict(action='discover',world=player['world'],location_id=player['location_id'],slot=0)
    result=runtime.execute('dungeon action',session_id=sid,arguments=arguments,
        expected_revision=session['revision'],request_key='discover')
    discovered=copy.deepcopy(runtime.load(sid)['current'])
    assert len(discovered['game']['dungeon_state']['instances'])==1
    replay=runtime.execute('dungeon action',session_id=sid,arguments=arguments,
        expected_revision=session['revision'],request_key='discover')
    assert replay['data']==result['data'] and runtime.load(sid)['current']==discovered
    with pytest.raises(RuntimeError) as refused:
        runtime.execute('dungeon action',session_id=sid,arguments=arguments,
            expected_revision=runtime.load(sid)['revision'],request_key='stale-map')
    assert '地图或探寻次数' in str(refused.value.__cause__)
    assert runtime.load(sid)['current']==discovered
    site=next(iter(discovered['game']['dungeon_state']['instances'].values()))
    runtime.execute('dungeon action',session_id=sid,arguments=dict(
        action='enter',dungeon_id=site['id'],revision=site['revision']),
        expected_revision=runtime.load(sid)['revision'],request_key='enter')
    entered=runtime.load(sid)['current']['game']
    assert entered['dungeon_state']['active']==site['id']
    assert entered['player']['age']==discovered['game']['player']['age']
    assert engine.store._path(game.id).read_bytes()==source
