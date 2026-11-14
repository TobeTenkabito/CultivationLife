"""Typed debug/Agent commands must use the same priced activation and receipts."""
import copy
from pathlib import Path

import pytest

from cultivation_life.debug.runtime import Runtime
from cultivation_life.models import GameState
from cultivation_life.system.technique_secret_rules import catalog
from cultivation_life.system.technique_secrets import quote
from test_technique_secrets import base, prepare

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('identity',['manual_five_color_ice','manual_know_heaven','manual_read_flame'])
def test_typed_activation_price_replay_and_source_isolation(base,tmp_path,identity):
    engine,original=base;game=prepare(engine,original,identity)
    runtime=Runtime(ROOT,tmp_path/'debug',engine.store)
    sid=runtime.start(game.id)['session_id']
    runtime.execute('game view',session_id=sid)
    source=engine.store._path(game.id).read_bytes()
    session=runtime.load(sid);before=copy.deepcopy(session['current'])
    prepared=GameState.from_dict(copy.deepcopy(before['game']))
    price=quote(prepared,catalog()[identity]);assert not price['reason']
    arguments=dict(art=identity,action='awaken',revision=prepared.player.secret_art_state.get('revision',0),quote=price['token'])
    with pytest.raises(RuntimeError):
        runtime.execute('secret art',session_id=sid,arguments=arguments|{'quote':'stale'},
            expected_revision=session['revision'],request_key='bad-quote')
    assert runtime.load(sid)['current']==before
    # Rejected commands are audited and advance the debug-session revision, not game receipts.
    session=runtime.load(sid)
    result=runtime.execute('secret art',session_id=sid,arguments=arguments,
        expected_revision=session['revision'],request_key='activate')
    state=copy.deepcopy(runtime.load(sid)['current']);player=GameState.from_dict(copy.deepcopy(state['game'])).player
    assert player.secret_art_state['manuals'][identity]['activated']
    assert player.opportunity==prepared.player.opportunity-price['opportunity']
    assert not player.formation_materials
    if identity=='manual_know_heaven':assert player.divine_sense_rank==prepared.player.divine_sense_rank+1
    if identity=='manual_read_flame':assert player.art_experience['alchemy']==prepared.player.art_experience['alchemy']+price['growth']['gain']
    replay=runtime.execute('secret art',session_id=sid,arguments=arguments,
        expected_revision=session['revision'],request_key='activate')
    assert replay['data']==result['data'] and runtime.load(sid)['current']==state
    with pytest.raises(RuntimeError):
        runtime.execute('secret art',session_id=sid,arguments=arguments,
            expected_revision=runtime.load(sid)['revision'],request_key='repeat-payment')
    assert runtime.load(sid)['current']==state
    assert engine.store._path(game.id).read_bytes()==source
