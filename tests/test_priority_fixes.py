import io
import json
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from unittest.mock import patch
import zipfile

import pytest

from cultivation_life import server
from cultivation_life.achievements import GlobalMetadataStore
from cultivation_life.engine import GameEngine
from cultivation_life.errors import MetadataReadError
from cultivation_life.models import GameState, Player
from scripts.android_provenance import FILES, ASSET, build_record, validate_apk_inputs


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('damage', ['io', 'json', 'encoding', 'shape', 'schema', 'record'])
def test_unreadable_metadata_is_never_replaced_by_new_achievements(tmp_path, damage):
    store = GlobalMetadataStore(tmp_path)
    original = json.dumps({'schema_version': 1, 'achievements': {'earned': {}}}).encode()
    original = {'json': b'{broken', 'encoding': b'\xff', 'shape': b'[]',
                'schema': b'{"schema_version":2,"achievements":{}}',
                'record': b'{"schema_version":1,"achievements":{"earned":[]}}'}.get(damage, original)
    store.path.write_bytes(original)
    definition = dict(id='new', name='New', description='New', category='story', source={})
    game = GameState('audit', 1, Player('Audit', 'none'), '', '')
    reader = Path.read_text

    def read(path, *args, **kwargs):
        if damage == 'io' and path == store.path:
            raise PermissionError('temporary sharing violation')
        return reader(path, *args, **kwargs)

    with patch.object(Path, 'read_text', read), pytest.raises(MetadataReadError):
        store.unlock([definition], game)
    assert store.path.read_bytes() == original
    assert not store.path.with_suffix('.tmp').exists()


def test_missing_metadata_can_be_created_normally(tmp_path):
    store = GlobalMetadataStore(tmp_path)
    assert store.read()['achievements'] == {}
    store.ensure_exists()
    assert store.path.is_file()


@pytest.fixture
def api_server(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    class Quiet(server.Handler):
        timeout = .5
        def log_message(self, *_args):
            pass
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
    with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', tmp_path):
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield httpd, Quiet, engine
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


def test_incomplete_body_does_not_hold_save_lock_and_times_out(api_server):
    httpd, handler, engine = api_server
    entered = threading.Event()
    original = handler._body
    def body(self):
        entered.set()
        return original(self)
    with patch.object(handler, '_body', body), socket.create_connection(httpd.server_address, timeout=3) as slow:
        host = f'127.0.0.1:{httpd.server_port}'
        slow.sendall((f'POST /api/games HTTP/1.1\r\nHost: {host}\r\n'
                      'Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{').encode())
        assert entered.wait(2)
        assert engine.store.lock.acquire(blocking=False)
        engine.store.lock.release()
        with urlopen(f'http://{host}/api/games', timeout=2) as response:
            assert response.status == 200
        assert b'408' in slow.recv(4096)


def test_response_transport_does_not_hold_save_lock(api_server):
    httpd, handler, _engine = api_server
    entered, release = threading.Event(), threading.Event()
    original = handler._send_json
    def send(self, body, status):
        if self.path == '/api/config':
            entered.set()
            assert release.wait(3)
        return original(self, body, status)
    base = f'http://127.0.0.1:{httpd.server_port}'
    def config():
        with urlopen(base + '/api/config', timeout=5) as response:
            return response.status
    with patch.object(handler, '_send_json', send), ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(config)
        try:
            assert entered.wait(2)
            request = Request(base + '/api/ui-preferences', data=b'{"theme":"b"}',
                              headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=2) as response:
                assert json.load(response)['theme'] == 'b'
        finally:
            release.set()
        assert future.result(timeout=3) == 200


def make_build(tmp_path):
    for name in FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('build input', encoding='utf-8')
    source = tmp_path / 'cultivation_life/rules.py'
    source.parent.mkdir()
    source.write_text('VALUE = 1\n')
    staged = tmp_path / 'staged'
    (staged / 'cultivation_life').mkdir(parents=True)
    (staged / 'cultivation_life/rules.py').write_bytes(source.read_bytes())
    return staged


def apk_bytes(record, *, module=True):
    python = io.BytesIO()
    with zipfile.ZipFile(python, 'w') as archive:
        if module:
            archive.writestr('cultivation_life/rules.pyc', b'compiled Python')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        if record is not None:
            archive.writestr(ASSET, json.dumps(record))
        archive.writestr('assets/chaquopy/app.imy', python.getvalue())
    return io.BytesIO(output.getvalue())


@pytest.mark.parametrize('change', ['unchanged', 'backend', 'added', 'deleted', 'java', 'dlc', 'missing', 'payload'])
def test_android_provenance_binds_all_release_inputs(tmp_path, change):
    staged = make_build(tmp_path)
    record = build_record(tmp_path, staged)
    changes = {'backend': 'cultivation_life/rules.py', 'added': 'cultivation_life/new.py',
               'java': 'android/app/src/main/java/Main.java', 'dlc': 'dlc/sample/content/world.json'}
    if change in changes:
        path = tmp_path / changes[change]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('changed', encoding='utf-8')
    if change == 'deleted':
        (tmp_path / 'cultivation_life/rules.py').unlink()
    with zipfile.ZipFile(apk_bytes(None if change == 'missing' else record,
                                 module=change != 'payload')) as archive:
        if change == 'unchanged':
            assert validate_apk_inputs(tmp_path, archive) == record
        else:
            with pytest.raises(RuntimeError):
                validate_apk_inputs(tmp_path, archive)


def test_android_receipt_cannot_be_generated_from_stale_staged_python(tmp_path):
    staged = make_build(tmp_path)
    (staged / 'cultivation_life/rules.py').write_text('old code')
    with pytest.raises(RuntimeError, match='Staged'):
        build_record(tmp_path, staged)


@pytest.mark.parametrize('optimization', ['', '-O', '-OO'])
def test_android_missing_provenance_is_rejected_under_optimization(tmp_path, optimization):
    archive = tmp_path / 'old.apk'
    archive.write_bytes(apk_bytes(None).getvalue())
    script = ('import sys, zipfile; from pathlib import Path; '
              'from scripts.android_provenance import validate_apk_inputs; '
              'validate_apk_inputs(Path(sys.argv[1]), zipfile.ZipFile(sys.argv[2]))')
    result = subprocess.run([sys.executable, *([optimization] if optimization else []),
                             '-c', script, str(tmp_path), str(archive)],
                            cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert 'Missing Android build provenance' in result.stderr
