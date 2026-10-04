"""Agent contracts: live discovery, strict schemas, concurrency, replay, and isolation."""
import copy
import io
import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_debug_console import environment, api_environment  # Shared isolated fixtures.
from cultivation_life.debug.agent import MCPServer, serve
from cultivation_life.debug.client import DebugClient, ToolError
from cultivation_life.debug.registry import CommandError
from cultivation_life.debug.runtime import atomic_json
from cultivation_life.engine.transactions import request_scope
from tools.check_module_dependencies import violations


def structured(env, name, arguments, **kwargs):
    return env[1].execute(name, session_id=env[2], arguments=arguments, **kwargs)


def test_structured_schemas_and_type_rejections(environment):
    manager = environment[1]
    catalog = {row['name']: row for row in manager.registry.catalog()}
    assert catalog['player set']['input_schema']['properties']['value']['type'] == 'number'
    before = manager.load(environment[2])['current']
    for name, args in [('player set', {'field': 'age', 'value': True}),
                       ('player set', {'field': 'age', 'value': 2.5}),
                       ('player set', {'field': 'age', 'value': '20'}),
                       ('player set', {'field': 'neighborhood', 'value': 1}),
                       ('player set', {'field': 'age', 'value': 20, 'extra': 1}),
                       ('rng seed', {'seed': 1.5}), ('rng seed', {'seed': -1}),
                       ('action advance', {'action': 'rest', 'units': 11})]:
        with pytest.raises(CommandError):
            structured(environment, name, args, expected_revision=manager.load(environment[2]).get('revision', 0),
                       request_key='invalid')
        assert manager.load(environment[2])['current'] == before
    with pytest.raises(CommandError, match='require'):
        structured(environment, 'give', {'resource': 'spirit_stone', 'amount': 1})


def test_atomic_idempotency_and_concurrent_stale_writes(environment):
    manager, sid = environment[1:3]
    initial = manager.execute('player get spirit_stones', session_id=sid)['data']['spirit_stones']
    def attempt(key):
        try:
            return structured(environment, 'give', {'resource': 'spirit_stone', 'amount': 5},
                              expected_revision=0, request_key=key)
        except CommandError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, ['one'] * 4))
    assert all(isinstance(result, dict) for result in results)
    assert sum(bool(result.get('replayed')) for result in results) == 3
    assert manager.load(sid)['revision'] == 1
    assert manager.execute('player get spirit_stones', session_id=sid)['data']['spirit_stones'] == initial + 5
    assert 'revision conflict' in attempt('different')
    with pytest.raises(CommandError, match='different request'):
        structured(environment, 'give', {'resource': 'spirit_stone', 'amount': 6},
                   expected_revision=0, request_key='one')
    manager.execute('snapshot restore initial', session_id=sid)
    assert attempt('one')['replayed']  # Restoring a snapshot never restores receipts/revision.
    assert manager.execute('player get spirit_stones', session_id=sid)['data']['spirit_stones'] == initial


def test_read_paths_catalog_pagination_and_inventory_contract(environment):
    manager, sid = environment[1:3]
    assert structured(environment, 'state get', {'pointer': '/player/realm_index'})['data'] == 3
    for pointer in ('player.age', '/player/__class__', '/player/inventory/-1', '/player/~bad'):
        with pytest.raises(CommandError):
            structured(environment, 'state get', {'pointer': pointer})
    rows = structured(environment, 'item list', {'query': '', 'offset': 0})['data']
    assert len(rows['rows']) <= 50
    assert rows['total'] >= len(rows['rows'])
    before = copy.deepcopy(manager.load(sid)['current'])
    manager.execute('item give spirit_stone 12', session_id=sid)
    manager.execute('item remove spirit_stone 12', session_id=sid)
    assert manager.load(sid)['current'] == before
    for command in ('item give immortal_trace 1', 'item give unknown_item 1', 'item remove spirit_stone 1000000000'):
        with pytest.raises(CommandError):
            manager.execute(command, session_id=sid)
    assert manager.load(sid)['current'] == before


def test_action_uses_same_engine_guards_and_preserves_sources(environment, monkeypatch):
    engine, manager, sid, gid = environment
    originals = {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}
    before = manager.load(sid)['current']
    # Lock time/UUID across both branches so all game/RNG/achievement data can be compared.
    import uuid
    monkeypatch.setattr(uuid, 'uuid4', lambda: uuid.UUID('12345678123456781234567812345678'))
    for name, module in list(sys.modules.items()):
        if name.startswith('cultivation_life.') and callable(getattr(module, 'now_iso', None)):
            monkeypatch.setattr(module, 'now_iso', lambda: '2026-10-04T00:00:00')
    with manager.staged(before) as (stage, store), request_scope(stage):
        for guard in (stage.assert_ghost_operation_allowed, stage.assert_guixu_operation_allowed,
                      stage.assert_buddhist_operation_allowed):
            guard(gid, 'advance')
        stage.advance(gid, 'rest', 1)
        expected = manager.staged_result(store, before)
    result = structured(environment, 'action advance', {'action': 'rest', 'units': 1},
                        expected_revision=0, request_key='rest-one')
    assert result['changed']
    assert manager.load(sid)['current'] == expected
    assert originals == {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}
    assert manager.load(sid)['last_before'] == before


def test_simulation_failed_partial_save_rolls_back(environment, monkeypatch):
    from cultivation_life.debug.engine_adapter import SessionEngine
    manager, sid = environment[1:3]
    before = manager.load(sid)['current']
    def broken(engine, gid, *args):
        game = engine.store.load(gid)
        game.player.age += 100
        engine.store.save(game)
        raise ValueError('internal simulation bug')
    monkeypatch.setattr(SessionEngine, 'advance', broken)
    with pytest.raises(RuntimeError, match='Debug command failed'):
        structured(environment, 'action advance', {'action': 'rest', 'units': 1},
                   expected_revision=0, request_key='failed')
    saved = manager.load(sid)
    assert saved['current'] == before
    assert 'internal simulation bug' in saved['journal'][-1]['error']['traceback']
    assert saved['journal'][-1]['operation']['arguments'] == {'action': 'rest', 'units': 1}
    assert saved['journal'][-1]['request_id'] == 'failed'
    assert not saved['receipts']


def test_event_choice_normal_rules_and_pending_action_rejection(environment):
    engine, manager, sid, gid = environment
    game = engine.store.load(gid)
    game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_ENCOUNTER_INJURED_001'], game, random.Random(2))
    engine.store.save(game)
    sid = manager.start(gid)['session_id']
    event = manager.execute('event inspect', session_id=sid)['data']
    assert event and event['choices']
    original = manager.load(sid)['current']
    with pytest.raises(CommandError, match='pending_event'):
        manager.execute('action advance rest 1', session_id=sid)
    with pytest.raises(CommandError, match='choice_id'):
        manager.execute('event choose missing_choice', session_id=sid)
    assert manager.load(sid)['current'] == original
    choice = next(c for c in event['choices'] if c.get('enabled', True))
    result = manager.execute('event choose ' + choice['id'], session_id=sid)
    assert result['type'] == 'simulation' and result['changed']
    assert manager.load(sid)['current']['game']['history'][-1]['choice_id'] == choice['id']


def test_old_debug_envelope_and_import_reset_transport_state(environment):
    manager, sid = environment[1:3]
    old = manager.load(sid)
    old.pop('revision'); old.pop('receipts')
    atomic_json(manager._path(sid), old)
    structured(environment, 'give', {'resource': 'spirit_stone', 'amount': 1},
               expected_revision=0, request_key='first')
    imported = manager.import_bundle(manager.load(sid))
    new = manager.load(imported['session_id'])
    assert new['revision'] == 0 and new['receipts'] == {}


def test_http_structured_validation_and_disable(environment, api_environment):
    request, config = api_environment
    config.write_text('Debug=True')
    status, started = request('/api/debug/command', {'command': 'debug start', 'arguments': {}, 'game_id': environment[3]})
    assert status == 200
    sid = started['data']['session_id']
    payload = {'command': 'give', 'arguments': {'resource': 'spirit_stone', 'amount': 9},
               'session_id': sid, 'expected_revision': 0, 'request_key': 'http-retry'}
    assert request('/api/debug/command', payload)[0] == 200
    assert request('/api/debug/command', payload)[1]['replayed']
    assert request('/api/debug/command', dict(payload, unexpected=True))[0] == 400
    assert request('/api/debug/command', dict(payload, arguments=None))[0] == 400
    assert request('/api/debug/command', {'command': 'debug status', 'arguments': {}, 'session_id': 0})[0] == 400
    config.write_text('Debug=False')
    assert request('/api/debug/command', payload)[0] == 404


def initialized_server(client):
    server = MCPServer(client)
    result = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}})
    assert result['result']['protocolVersion'] == '2025-11-25'
    assert server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) is None
    return server


def test_real_client_cli_and_mcp_tools(environment, api_environment):
    request, config = api_environment
    # The fixture request closure owns the local HTTP server; use its bound port.
    httpd = next(cell.cell_contents for cell in request.__closure__ if hasattr(cell.cell_contents, 'server_port'))
    url = f'http://127.0.0.1:{httpd.server_port}'
    client = DebugClient(url)
    with pytest.raises(ToolError) as error:
        client.tools()
    assert error.value.status == 404
    config.write_text('Debug=True')
    tools = client.tools()
    assert any(t['name'] == 'cultivation_action_advance' for t in tools)
    assert not any(t['name'].endswith('eval') for t in tools)
    source = client.call_tool('cultivation_save_list', {'arguments': {}})['data'][0]
    sid = client.call_tool('cultivation_debug_start', {'arguments': {}, 'game_id': source['game_id']})['data']['session_id']
    server = initialized_server(client)
    payload = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
        'name': 'cultivation_player_set', 'arguments': {'arguments': {'field': 'spirit_stones', 'value': 12345},
            'session_id': sid, 'expected_revision': 0, 'request_key': 'mcp-one'}}}
    result = server.handle(payload)['result']
    assert not result['isError'] and result['structuredContent']['data']['spirit_stones'] == 12345
    assert server.handle(payload)['result']['structuredContent']['replayed']
    invalid = copy.deepcopy(payload)
    invalid['params']['arguments']['arguments']['value'] = True
    assert server.handle(invalid)['result']['isError']
    command = [sys.executable, '-m', 'cultivation_life.debug.agent', '--url', url]
    process = subprocess.run([*command, 'call', 'player get', '--arguments', '{"field":"spirit_stones"}',
                              '--session-id', sid], capture_output=True, timeout=20)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)['data']['spirit_stones'] == 12345
    messages = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}]
    process = subprocess.run([*command, 'mcp'], input=''.join(json.dumps(m)+'\n' for m in messages).encode(),
                             capture_output=True, timeout=20)
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert process.returncode == 0 and len(responses) == 2
    assert responses[-1]['result']['tools'][0]['inputSchema']['additionalProperties'] is False
    config.write_text('Debug=False')
    assert server.handle(payload)['result']['isError']


def test_mcp_protocol_errors_no_stdout_noise_and_no_game_imports():
    assert violations([('cultivation_life.debug.client', 'cultivation_life.storage', 1)])
    assert violations([('cultivation_life.debug.agent', 'cultivation_life.debug.runtime', 1)])
    assert not violations([('cultivation_life.debug.agent', 'cultivation_life.debug.client', 1)])
    server = MCPServer(None)
    assert server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['error']['code'] == -32000
    assert server.handle([])['error']['code'] == -32600
    output = io.BytesIO()
    serve(None, io.BytesIO(b'not json\n{"jsonrpc":"2.0","id":1,"method":"ping"}\n'), output)
    rows = [json.loads(row) for row in output.getvalue().splitlines()]
    assert rows[0]['error']['code'] == -32700 and rows[1]['result'] == {}
    process = subprocess.run([sys.executable, '-c',
        'import sys; import cultivation_life.debug.agent; '
        'assert "cultivation_life.engine" not in sys.modules; '
        'assert "cultivation_life.content_registry" not in sys.modules'], capture_output=True)
    assert process.returncode == 0, process.stderr


@pytest.mark.parametrize('url', ['https://example.org', 'http://192.168.1.2:8000',
    'http://localhost:8000/api/games', 'http://user:pass@localhost:8000', 'http://localhost:8000/?x=1'])
def test_client_rejects_nonlocal_or_ambiguous_targets(url):
    with pytest.raises(ValueError):
        DebugClient(url)
