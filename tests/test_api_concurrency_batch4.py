"""Real concurrent HTTP requests, committed reads and unchanged writer isolation."""
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cultivation_life import server
from cultivation_life.achievements import GlobalMetadataStore
from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import independent_query_allowed, request_scope, request_games
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore, supports_committed_summaries

ROOT = Path(__file__).resolve().parents[1]
INDEPENDENT = ['/api/config', '/api/ui-preferences', '/api/visual-assets', '/api/fleet-goods',
    '/api/domain-styles', '/api/games', '/api/achievements', '/api/authored-lineages']


def fetch(base, path, *, method='GET', body=None, headers=None):
    request = Request(base+path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json', 'Origin':base, **(headers or {})})
    try:
        with urlopen(request, timeout=25) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path/'saves')
    identities = []
    for name in ('行动中', '另一角色'):
        identity = engine.create_game(name, 'heavenly', 'dao', 280, preset_id='core')['id']
        game = engine.store.load(identity)
        game.pending_event = None
        game.settings['silent_events'] = True
        game.player.next_tribulation_age = None
        engine.store.save(game)
        for _ in range(2):
            engine.get_game(identity)
        identities.append(identity)
    probes = {}
    class Quiet(server.Handler):
        def log_message(self, *args):
            pass
        def _validate_request(self):
            super()._validate_request()
            probe = probes.get(self.headers.get('X-Test-Probe'))
            if probe:
                probe.set()
    monkeypatch.setattr(server, 'ENGINE', engine)
    monkeypatch.setattr(server, 'PERSISTENCE_ROOT', tmp_path)
    http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(engine=engine, ids=identities,
            base=f'http://127.0.0.1:{http.server_port}', probes=probes, handler=Quiet)
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=3)


def gated_action(api, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = api.engine._advance_world_year
    def advance(*args, **kwargs):
        cache = request_games(api.engine)
        assert cache
        entered.set()
        if not release.wait(15):
            raise TimeoutError('test action gate was not released')
        assert request_games(api.engine) is cache and cache
        return original(*args, **kwargs)
    monkeypatch.setattr(api.engine, '_advance_world_year', advance)
    return entered, release


def test_frozen_reference_adapter_is_unchanged():
    path = ROOT/'tests/fixtures/api_serialization_332.py'
    assert hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == '8cf481dcda9fe0dc1068245be62cf560cc80655fbc557d44d73d79a709c69946'


def test_all_audited_reads_complete_while_real_action_is_paused(api, monkeypatch):
    expected = {path:fetch(api.base, path) for path in INDEPENDENT}
    hashes = {p.name:p.read_bytes() for p in api.engine.store.directory.glob('*.json')}
    entered, release = gated_action(api, monkeypatch)
    with ThreadPoolExecutor(max_workers=10) as pool:
        action = pool.submit(fetch, api.base, f'/api/games/{api.ids[0]}/advance', method='POST', body=dict(action='rest',years=1))
        try:
            assert entered.wait(5)
            reads = {path:pool.submit(fetch, api.base, path) for path in INDEPENDENT}
            for path, future in reads.items():
                assert future.result(timeout=5) == expected[path]
            assert not release.is_set() and not action.done()
            assert {p.name:p.read_bytes() for p in api.engine.store.directory.glob('*.json')} == hashes
        finally:
            release.set()
        assert action.result(timeout=15)[0] == 200


@pytest.mark.parametrize('operation', ['same-game', 'other-game', 'path-eligibility', 'write', 'delete'])
def test_game_reads_eligibility_and_mutations_remain_serialized(api, monkeypatch, operation):
    entered, release = gated_action(api, monkeypatch)
    seen = api.probes['dependent'] = threading.Event()
    path, method, body = f'/api/games/{api.ids[0]}', 'GET', None
    if operation == 'other-game':
        path = f'/api/games/{api.ids[1]}'
    elif operation == 'path-eligibility':
        path = f'/api/domain-styles?id={api.ids[1]}'
    elif operation == 'write':
        path, method, body = f'/api/games/{api.ids[1]}/advance', 'POST', dict(action='rest', years=1)
    elif operation == 'delete':
        path, method = f'/api/games/{api.ids[1]}', 'DELETE'
    with ThreadPoolExecutor(max_workers=2) as pool:
        action = pool.submit(fetch, api.base, f'/api/games/{api.ids[0]}/advance', method='POST', body=dict(action='rest',years=1))
        try:
            assert entered.wait(5)
            dependent = pool.submit(fetch, api.base, path, method=method, body=body, headers={'X-Test-Probe':'dependent'})
            assert seen.wait(5)
            # Validated on the server, not merely waiting in a client queue.
            time.sleep(.05)
            assert not dependent.done()
        finally:
            release.set()
        assert action.result(timeout=15)[0] == 200
        assert dependent.result(timeout=15)[0] == 200


@pytest.mark.parametrize('adapter', ['wrapped-method', 'store-subclass', 'store-class-method', 'metadata-subclass', 'custom-handler'])
def test_replaced_capabilities_and_handlers_fail_closed_to_original_lock(api, monkeypatch, adapter):
    path = '/api/games'
    if adapter == 'wrapped-method':
        original = api.engine.list_games
        @wraps(original)
        def replacement():
            return original()
        monkeypatch.setattr(api.engine, 'list_games', replacement)
        assert not independent_query_allowed(api.engine, replacement)
    elif adapter == 'store-subclass':
        class Adapter(SaveStore):
            pass
        api.engine.store = Adapter(api.engine.store.directory)
        assert not supports_committed_summaries(api.engine.store)
    elif adapter == 'store-class-method':
        original = SaveStore.list_games
        @wraps(original)
        def replacement(store):
            return original(store)
        monkeypatch.setattr(SaveStore, 'list_games', replacement)
        assert not supports_committed_summaries(api.engine.store)
    elif adapter == 'metadata-subclass':
        class Adapter(GlobalMetadataStore):
            pass
        api.engine.achievements.metadata = Adapter(api.engine.store.directory)
        path = '/api/achievements'
        assert not independent_query_allowed(api.engine, api.engine.list_achievements)
    else:
        handler = SimpleNamespace(command='GET', path='/api/config', headers={})
        assert not server._independent_api_read(lambda value: value, handler, api.engine)
        return
    entered, release = gated_action(api, monkeypatch)
    seen = api.probes['adapter'] = threading.Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        action = pool.submit(fetch, api.base, f'/api/games/{api.ids[0]}/advance', method='POST', body=dict(action='rest',years=1))
        try:
            assert entered.wait(5)
            read = pool.submit(fetch, api.base, path, headers={'X-Test-Probe':'adapter'})
            assert seen.wait(5)
            time.sleep(.05)
            assert not read.done()
        finally:
            release.set()
        assert action.result(timeout=15)[0] == read.result(timeout=15)[0] == 200


def test_validation_and_debug_cannot_bypass_policy(api, monkeypatch):
    entered, release = gated_action(api, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        action = pool.submit(fetch, api.base, f'/api/games/{api.ids[0]}/advance', method='POST', body=dict(action='rest',years=1))
        try:
            assert entered.wait(5)
            assert fetch(api.base, '/api/config', headers={'Origin':'https://foreign.invalid'})[0] == 403
            assert fetch(api.base, '/api/games', headers={'Host':'foreign.invalid'})[0] == 403
            handler = SimpleNamespace(command='GET', path='/api/config', headers={'X-Cultivation-Debug':'session'})
            assert not server._independent_api_read(server._READ_QUERY_HANDLER, handler, api.engine)
            assert fetch(api.base, '/api/visual-assets', headers={'X-Cultivation-Debug':'invalid'})[0] != 200
        finally:
            release.set()
        assert action.result(timeout=15)[0] == 200


def test_independent_request_context_is_nested_and_always_reset(api):
    engine = api.engine
    assert request_games(engine) is None
    with request_scope(engine):
        outer = request_games(engine)
        outer['sentinel'] = object()
        with pytest.raises(ValueError), request_scope(engine, serialized=False):
            assert request_games(engine) == {} and request_games(engine) is not outer
            raise ValueError('failure')
        assert request_games(engine) is outer
    assert request_games(engine) is None


def test_failed_independent_read_never_clears_the_actions_cached_game(api, monkeypatch):
    entered, release = gated_action(api, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        action = pool.submit(fetch, api.base, f'/api/games/{api.ids[0]}/advance', method='POST', body=dict(action='rest', years=1))
        try:
            assert entered.wait(5)
            def broken_config(*args):
                raise RuntimeError('isolated independent read failure')
            with monkeypatch.context() as context:
                context.setattr(server, 'load_runtime_config', broken_config)
                status, result = fetch(api.base, '/api/config')
                assert status == 500 and result['code'] == 'internal_error'
            assert not action.done()
            assert fetch(api.base, '/api/config')[0] == 200
        finally:
            release.set()
        assert action.result(timeout=15)[0] == 200
        assert fetch(api.base, f'/api/games/{api.ids[0]}')[0] == 200


def test_shared_metadata_transactions_never_lose_unlocks(tmp_path):
    stores = [GlobalMetadataStore(tmp_path) for _ in range(12)]
    assert all(store._lock is stores[0]._lock and store._file_lock is stores[0]._file_lock for store in stores)
    game = GameState('account-test', 4, Player('元数据验收', 'none'), '', '')
    from cultivation_life.achievement_definitions import load_achievement_definitions
    from cultivation_life.content_registry import CONTENT_DOCUMENTS
    definitions = load_achievement_definitions(CONTENT_DOCUMENTS['achievements.json'])[:12]
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(store.unlock, [definition], game) for store, definition in zip(stores, definitions)]
        for future in futures:
            future.result(timeout=5)
    assert set(stores[0].read()['achievements']) == {row['id'] for row in definitions}


@pytest.mark.parametrize('operation', ['replace', 'delete', 'metadata'])
def test_open_summary_read_handles_cannot_break_windows_commits(tmp_path, monkeypatch, operation):
    first, second = SaveStore(tmp_path), SaveStore(tmp_path)
    game = GameState('atomic-test', 4, Player('旧记录', 'none'), '', '')
    first.save(game)
    assert first._file_lock is second._file_lock
    metadata = GlobalMetadataStore(tmp_path)
    metadata.ensure_exists()
    target = metadata.path if operation=='metadata' else first._path(game.id)
    entered, release = threading.Event(), threading.Event()
    read_bytes = Path.read_bytes
    def held_read(path):
        if path == target:
            with path.open('rb') as stream:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('reader gate')
                return stream.read()
        return read_bytes(path)
    monkeypatch.setattr(Path, 'read_bytes', held_read)
    game.player.name = '新记录'
    def commit():
        if operation == 'replace':
            second.save(game)
        elif operation == 'delete':
            second.delete(game.id)
        else:
            metadata._write({'schema_version':1, 'achievements':{}})
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(first.list_games)
        try:
            assert entered.wait(5)
            writer = pool.submit(commit)
            time.sleep(.05)
            assert not writer.done()
        finally:
            release.set()
        reader.result(timeout=5)
        writer.result(timeout=5)
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    if operation == 'replace':
        assert first.list_games()[0]['name'] == '新记录'
    elif operation == 'delete':
        assert first.list_games() == []
    else:
        assert metadata.read() == {'schema_version':1, 'achievements':{}}
