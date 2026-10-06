"""Heavens tools retain the debug isolation, replay and ordinary-rule contracts."""
import copy

import pytest

from test_debug_console import environment
from cultivation_life.debug.commands import build_registry
from cultivation_life.debug.registry import CommandError
from cultivation_life.debug.runtime import atomic_json


def test_inspection_is_pure_and_respects_observer_world(environment):
    engine, manager, sid, gid = environment
    before = manager._path(sid).read_bytes()
    source = engine.store._path(gid).read_bytes()
    data = manager.execute('heavens inspect', session_id=sid)['data']
    assert {r['world'] for r in data['view']['incidents']} == {'human', 'demon', 'hell', 'monster_realm'}
    assert data['saved_state'] == manager.load(sid)['current']['game']['heavens_state']
    for row in data['view']['incidents']:
        detail = manager.execute('heavens inspect', arguments={'target_id': row['id']}, session_id=sid)
        assert detail['data']['view']['target_id'] == row['id']
    assert manager._path(sid).read_bytes() == before
    assert engine.store._path(gid).read_bytes() == source


def test_act_quotes_costs_allocates_sequence_and_replays_in_isolation(environment):
    engine, manager, sid, gid = environment
    source = engine.store._path(gid).read_bytes()
    session = manager.load(sid)
    session['current']['game']['player']['location_id'] = 'wudi_plain'
    session['current']['game']['settings']['silent_events'] = True
    atomic_json(manager._path(sid), session)
    manager.execute('snapshot create before_heavens', session_id=sid)
    before = copy.deepcopy(manager.load(sid)['current'])
    revision = manager.load(sid)['revision']
    args = {'action': 'incident_survey', 'target_id': 'human_beacon', 'options': {}}
    result = manager.execute('heavens act', arguments=args, session_id=sid,
                             expected_revision=revision, request_key='survey-once')
    after = manager.load(sid)['current']
    assert result['data']['quote']['years'] == 2
    assert 0 < after['game']['player']['age'] - before['game']['player']['age'] <= 2
    assert after['game']['heavens_state']['command_seq'] == before['game']['heavens_state'].get('command_seq', 0) + 1
    assert 'human_beacon' in after['game']['heavens_state']['runtime']['incidents']
    replay = manager.execute('heavens act', arguments=args, session_id=sid,
                             expected_revision=revision, request_key='survey-once')
    assert replay['replayed'] and manager.load(sid)['current'] == after
    manager.execute('snapshot restore before_heavens', session_id=sid)
    assert manager.load(sid)['current'] == before
    assert engine.store._path(gid).read_bytes() == source


def test_failed_act_preserves_state_and_rng(environment):
    _, manager, sid, _ = environment
    before = copy.deepcopy(manager.load(sid)['current'])
    with pytest.raises((ValueError, RuntimeError)):
        manager.execute("heavens act incident_review '{}' asura_banner", session_id=sid)
    assert manager.load(sid)['current'] == before


def test_configuration_helper_and_catalog_share_strict_options(environment):
    _, manager, sid, _ = environment
    result = manager.execute('heavens act configure \'{"watch":false}\'', session_id=sid)
    assert result['data']['heavens']['watch'] is False
    catalog = {r['name']: r for r in build_registry().catalog('heavens')}
    assert set(catalog) == {'heavens view', 'heavens preview', 'heavens command', 'heavens inspect', 'heavens act'}
    assert 'incident_seal' in catalog['heavens act']['input_schema']['properties']['action']['enum']
    assert 'campaign_scout' in catalog['heavens act']['input_schema']['properties']['action']['enum']
    for options in ({'watch': 'false'}, {'teleport': True}):
        with pytest.raises(CommandError):
            build_registry().structured('heavens act', {'action': 'configure', 'options': options})


def test_stale_agent_request_and_missing_session_rejected(environment):
    _, manager, sid, _ = environment
    with pytest.raises(CommandError):
        manager.execute('heavens inspect')
    manager.execute('heavens act configure \'{"watch":false}\'', session_id=sid)
    before = copy.deepcopy(manager.load(sid)['current'])
    with pytest.raises(CommandError, match='revision conflict'):
        manager.execute('heavens act', arguments={'action': 'configure', 'options': {'watch': True}},
                        session_id=sid, expected_revision=0, request_key='stale')
    assert manager.load(sid)['current'] == before
