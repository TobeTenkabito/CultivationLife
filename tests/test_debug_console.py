"""Behavioral boundaries for isolated developer commands and gameplay requests."""
import copy
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.debug.commands import build_registry
from cultivation_life.debug.engine_adapter import SessionEngine
from cultivation_life.debug.registry import Command, CommandError
from cultivation_life.debug.runtime import Runtime
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def environment(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'normal')
    made = engine.create_game('Debug Test', 'heavenly', 'dao', 881, preset_id='core')
    game = engine.store.load(made['id'])
    game.pending_event = None
    game.active_trial = None
    engine.store.save(game)
    manager = Runtime(ROOT, tmp_path / 'debug', engine.store)
    session_id = manager.start(game.id)['session_id']
    return engine, manager, session_id, game.id


def run(env, text):
    return env[1].execute(text, session_id=env[2])


def test_resource_authority_and_source_isolation(environment):
    engine, manager, sid, gid = environment
    before = {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}
    run(environment, 'player set spirit_stones 100000')
    run(environment, 'give spirit_stone 30')
    run(environment, 'remove spirit_stone 12')
    assert run(environment, 'player get spirit_stones')['data'] == {'spirit_stones': 100018}
    game = manager.load(sid)['current']['game']
    assert 'spirit_stones' not in game['player']
    assert sum(i['quantity'] for i in game['player']['inventory'] if i['id'] == 'spirit_stone') == 100018
    assert before == {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}


@pytest.mark.parametrize('command', [
    'player set realm_index 999', 'player set layer 0', 'player set spirit_stones -1',
    'player set opportunity nan', 'player set hp inf', 'player set age 2.5',
    'player set breakthrough_chance 1.01', 'player set neighborhood 1', 'player set linyu 1',
    'give spirit_stones 10', 'player set __dict__ 1', 'player set alive true',
    'player set world spirit', 'rng seed -1', 'snapshot create ../../file',
    'player set spirit_stones 1; whoami', 'unknown command', 'player set "unterminated',
])
def test_invalid_commands_never_change_game(environment, command):
    manager, sid = environment[1:3]
    before = copy.deepcopy(manager.load(sid)['current'])
    with pytest.raises(CommandError):
        run(environment, command)
    assert manager.load(sid)['current'] == before


def test_all_query_commands_are_pure(environment):
    manager, sid = environment[1:3]
    path = manager._path(sid)
    run(environment, 'snapshot create before')
    npc_id = run(environment, 'npc list')['data'][0]['id']
    queries = ['help', 'help player', 'version', 'debug status', 'debug sessions', 'player',
               'player get realm_index', 'player fields', 'realm list', 'npc list',
               f'npc inspect {npc_id}', 'rng state', 'save validate', 'snapshot list',
               'snapshot diff before', 'extensions']
    assert {manager.registry.parse(q)[0].name for q in queries} == {
        command.name for command in manager.registry.commands.values() if command.kind == 'query'}
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    for query in queries:
        run(environment, query)
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_realm_change_validates_layers_and_pending_state(environment):
    run(environment, 'player set realm_index 4')
    assert run(environment, 'player get layer')['data']['layer'] == 1
    run(environment, 'player set layer 7')
    with pytest.raises(CommandError):
        run(environment, 'player set layer 10')
    assert run(environment, 'player get layer')['data']['layer'] == 7


def test_probability_override_only_on_session_instance(environment, tmp_path):
    engine, manager, sid, gid = environment
    player = engine.store.load(gid).player
    normal = engine._breakthrough_chance(player, True)
    run(environment, 'player set breakthrough_chance 1')
    session_engine = SessionEngine(ROOT, tmp_path / 'stage', manager.load(sid)['current']['overrides'])
    assert session_engine._breakthrough_chance(player, True)['final'] == 1
    assert session_engine._breakthrough_chance(player, False)['final'] == 1
    assert session_engine._dependencies.breakthroughs._breakthrough_chance(player, major=True)['final'] == 1
    assert engine._breakthrough_chance(player, True) == normal
    assert 'breakthrough_chance' not in manager.load(sid)['current']['game']['player']
    run(environment, 'player reset breakthrough_chance')
    assert manager.load(sid)['current']['overrides'] == {}


def test_snapshot_restore_and_failed_gameplay_rollback(environment):
    engine, manager, sid, gid = environment
    run(environment, 'snapshot create baseline')
    baseline = copy.deepcopy(manager.load(sid)['current'])
    run(environment, 'player set breakthrough_chance 0')
    run(environment, 'rng seed 114514')
    run(environment, 'player set spirit_stones 123456')
    run(environment, 'snapshot restore baseline')
    assert manager.load(sid)['current'] == baseline
    with pytest.raises(RuntimeError, match='fixture failure'):
        with manager.gameplay(sid, {'method': 'POST', 'path': '/test'}, 'request-a') as (stage, outcome):
            game = stage.store.load(gid)
            game.player.age += 3
            stage.store.save(game)
            (stage.store.directory / 'global_metadata.json').write_text('{}')
            raise RuntimeError('fixture failure')
    saved = manager.load(sid)
    assert saved['current'] == baseline
    assert 'fixture failure' in saved['journal'][-1]['error']['traceback']
    assert saved['last_before'] == baseline


def test_successful_gameplay_is_committed_only_to_copy(environment):
    engine, manager, sid, gid = environment
    original = (engine.store.directory / f'{gid}.json').read_bytes()
    with manager.gameplay(sid, {'method': 'POST', 'path': '/advance'}, 'request-b') as (stage, outcome):
        stage.advance(gid, 'rest', 1)
        outcome['ok'] = True
    assert manager.load(sid)['current'] != manager.load(sid)['initial']
    assert (engine.store.directory / f'{gid}.json').read_bytes() == original
    before = manager.load(sid)['last_before']
    run(environment, 'snapshot restore last_before')
    assert manager.load(sid)['current'] == before


def test_export_import_reproduction_bundle_and_original_untouched(environment):
    engine, manager, sid, gid = environment
    run(environment, 'player set spirit_stones 123')
    run(environment, 'snapshot create sample')
    exported = run(environment, 'repro export')['data']['download']['content']
    result = manager.execute('repro import', bundle=json.loads(exported))['data']
    assert result['session_id'] != sid
    assert manager.load(result['session_id'])['current'] == manager.load(sid)['current']
    assert result['environment_matches']
    assert engine.store.list_games()[0]['id'] == gid


def test_registry_extension_duplicate_and_internal_exception(environment):
    manager = environment[1]
    manager.registry.register(Command('test fail', 'mutation', 'Injected failure',
        lambda ctx: (_ for _ in ()).throw(RuntimeError('internal problem'))))
    with pytest.raises(RuntimeError, match='Debug command failed'):
        run(environment, 'test fail')
    with pytest.raises(RuntimeError, match='Duplicate'):
        manager.registry.register(manager.registry.commands['player'])
    assert build_registry().catalog('player')


def test_concurrent_commands_do_not_lose_resource_updates(environment):
    run(environment, 'player set spirit_stones 0')
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: run(environment, 'give spirit_stone 1'), range(12)))
    assert run(environment, 'player get spirit_stones')['data']['spirit_stones'] == 12


def test_debug_dependency_direction_is_enforced():
    assert violations([('cultivation_life.rules', 'cultivation_life.debug.runtime', 1)])
    assert not violations([('cultivation_life.server', 'cultivation_life.debug.gateway', 1)])


def test_uncovered_query_mutation_is_rejected_without_disk_write(environment):
    manager, sid = environment[1:3]
    before = manager._path(sid).read_bytes()
    manager.registry.register(Command('test bad query', 'query', 'Injected impure query',
        lambda ctx: ctx.document['player'].update(age=999)))
    with pytest.raises(RuntimeError, match='Debug command failed'):
        run(environment, 'test bad query')
    assert manager._path(sid).read_bytes() == before


@pytest.fixture
def api_environment(environment, tmp_path, monkeypatch):
    from cultivation_life import server
    engine = environment[0]
    monkeypatch.setattr(server, 'ENGINE', engine)
    monkeypatch.setattr(server, 'ENGINE_ROOT', ROOT)
    monkeypatch.setattr(server, 'APP_ROOT', tmp_path)
    monkeypatch.setattr(server, 'PERSISTENCE_ROOT', tmp_path)
    class QuietHandler(server.Handler):
        def log_message(self, *_args):
            pass
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    def request(path, payload=None, session_id=None, headers=None):
        options = {'Content-Type': 'application/json', **(headers or {})}
        if session_id:
            options['X-Cultivation-Debug'] = session_id
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(f'http://127.0.0.1:{httpd.server_port}' + path, data=body, headers=options)
        try:
            with urlopen(req, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)
    try:
        yield request, tmp_path / 'game_config.txt'
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=5)


def test_api_disabled_and_unknown_tokens_fail_closed(environment, api_environment):
    request, config = api_environment
    assert request('/api/debug/command', {'command': 'help'})[0] == 404
    assert request('/api/games/' + environment[3], session_id=environment[2])[0] == 404
    config.write_text('Debug=True')
    assert request('/api/debug/command', {'command': 'help'})[0] == 200
    assert request('/api/games/' + environment[3], session_id='a' * 32)[0] == 404
    assert request('/api/debug/command', headers={'Origin': 'https://example.org'})[0] == 403


def test_api_console_gameplay_and_two_tabs_are_isolated(environment, api_environment):
    request, config = api_environment
    config.write_text('Debug=True')
    engine, _, _, gid = environment
    source_path = engine.store.directory / f'{gid}.json'
    original = source_path.read_bytes()
    status, result = request('/api/debug/command', {'command': 'debug start', 'game_id': gid})
    assert status == 200, result
    sid = result['data']['session_id']
    status, result = request('/api/debug/command', {'command': 'player set spirit_stones 88888', 'session_id': sid})
    assert status == 200, result
    status, played = request('/api/games/' + gid + '/advance', {'action': 'rest', 'years': 1}, session_id=sid)
    assert status == 200, played
    assert played['id'] == gid
    assert source_path.read_bytes() == original
    # Save transfer and extension changes must not escape the debug store.
    assert request('/api/save-transfer/export', {'id': gid}, session_id=sid)[0] == 400
    assert request('/api/extensions/asura-manifestation', {'enabled': False}, session_id=sid)[0] == 400
    assert request('/api/games', {'name': 'Leak'}, session_id=sid)[0] == 400
    assert request('/api/games/another-game', session_id=sid)[0] == 400
    status, normal = request('/api/games/' + gid)
    assert status == 200
    assert sum(i['quantity'] for i in normal['player']['inventory'] if i['id'] == 'spirit_stone') != 88888
    config.write_text('Debug=False')
    assert request('/api/games/' + gid + '/advance', {'action': 'rest', 'years': 1}, session_id=sid)[0] == 404


def test_api_internal_errors_are_not_reported_as_input_errors(environment, api_environment, monkeypatch):
    from cultivation_life.debug import runtime
    request, config = api_environment
    config.write_text('Debug=True')
    original_registry = runtime.build_registry
    def registry():
        result = original_registry()
        result.register(Command('test internal', 'query', 'Injected internal ValueError',
            lambda ctx: (_ for _ in ()).throw(ValueError('broken implementation')), requires_session=False))
        return result
    monkeypatch.setattr(runtime, 'build_registry', registry)
    status, result = request('/api/debug/command', {'command': 'test internal'})
    assert status == 500
    assert result['code'] == 'internal_error'
    assert request('/api/debug/command', {'command': 'player set age abc'})[0] == 400


def test_start_does_not_migrate_source_file(environment):
    engine, manager, _, gid = environment
    path = engine.store.directory / f'{gid}.json'
    source = json.loads(path.read_text(encoding='utf-8'))
    source['version'] = 7
    path.write_text(json.dumps(source), encoding='utf-8')
    original = path.read_bytes()
    sid = manager.start(gid)['session_id']
    assert manager.load(sid)['current']['game']['version'] == 8
    assert path.read_bytes() == original


def test_import_rejects_invalid_bundle_without_creating_session(environment):
    _, manager, sid, _ = environment
    bundle = manager.load(sid)
    bundle['current']['overrides']['breakthrough_chance'] = 9
    before = sorted(manager.directory.glob('*.json'))
    with pytest.raises(CommandError):
        manager.import_bundle(bundle)
    assert sorted(manager.directory.glob('*.json')) == before


@pytest.mark.parametrize('field,value', [('environment', None), ('source_sha256', None),
    ('snapshots', []), ('journal', 'bad'), ('journal', ['bad']), ('source_game_id', '../escape')])
def test_import_rejects_malformed_envelope(environment, field, value):
    _, manager, sid, _ = environment
    bundle = manager.load(sid)
    bundle[field] = value
    before = sorted(manager.directory.glob('*.json'))
    with pytest.raises(CommandError):
        manager.import_bundle(bundle)
    assert sorted(manager.directory.glob('*.json')) == before
