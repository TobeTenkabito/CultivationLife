"""Android-only host: isolated assets, authenticated loopback, serialized game APIs."""
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import threading
import zipfile
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer

_httpd = None
_token = None
_lock = threading.RLock()


def debug_mode_enabled():
    from cultivation_life.runtime_config import load_runtime_config
    return bool(load_runtime_config(Path(os.environ['CULTIVATION_APP_ROOT']))['debug'])


def set_debug_mode(enabled):
    """Native settings only: no remotely callable API can enable developer mode."""
    import tempfile
    if type(enabled) is not bool:
        raise ValueError('enabled must be boolean')
    root = Path(os.environ['CULTIVATION_APP_ROOT'])
    temporary = None
    with _lock:
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=root, delete=False) as out:
                temporary = Path(out.name)
                out.write('Debug=True\n' if enabled else 'Debug=False\n')
            temporary.replace(root / 'game_config.txt')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def start(files_dir, bundle_path, bundle_hash, build_record=None):
    global _httpd, _token
    with _lock:
        if _httpd is not None:
            return f'http://127.0.0.1:{_httpd.server_port}|{_token}'
        files = Path(str(files_dir))
        root = files / 'game'
        root.mkdir(parents=True, exist_ok=True)
        # Re-extract immutable shipped resources after an APK update. Never touch data/.
        marker = root / 'bundle.sha256'
        if not marker.exists() or marker.read_text() != str(bundle_hash):
            archive = Path(str(bundle_path))
            if hashlib.sha256(archive.read_bytes()).hexdigest() != str(bundle_hash):
                raise ValueError('游戏资源校验失败，请重新安装')
            stage = files / 'game-assets-staging'
            if stage.exists():
                shutil.rmtree(stage)
            stage.mkdir(exist_ok=True)
            with zipfile.ZipFile(archive) as bundle:
                for entry in bundle.infolist():
                    target = (stage / entry.filename).resolve()
                    if stage.resolve() not in target.parents:
                        raise ValueError('非法资源路径')
                bundle.extractall(stage)
            for name in ('content', 'web', 'dlc'):
                target = root / name
                if target.exists():
                    shutil.rmtree(target)
                (stage / name).replace(target)
            shutil.rmtree(stage)
            marker.write_text(str(bundle_hash))
        os.environ['CULTIVATION_APP_ROOT'] = str(root)
        if build_record is not None:
            os.environ['CULTIVATION_BUILD_FINGERPRINT'] = hashlib.sha256(str(build_record).encode()).hexdigest()
        from cultivation_life import server
        _token = secrets.token_urlsafe(32)

        class AndroidHandler(server.Handler):
            def _allowed(self):
                origin = f'http://127.0.0.1:{self.server.server_port}'
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get('Cookie', ''))
                    token = cookie['cultivation_session'].value
                except (KeyError, ValueError):
                    token = ''
                if (not secrets.compare_digest(token, _token)
                        or self.headers.get('Host') != origin.removeprefix('http://')
                        or self.headers.get('Origin', origin) != origin):
                    self._json({'error': '无权访问本地游戏'}, 403)
                    return False
                return True

            def do_GET(self):
                if self._allowed():
                    super().do_GET()

            def do_POST(self):
                if self._allowed():
                    super().do_POST()

            def do_DELETE(self):
                if self._allowed():
                    super().do_DELETE()

            def log_message(self, *_args):
                pass

        _httpd = ThreadingHTTPServer(('127.0.0.1', 0), AndroidHandler)
        _httpd.daemon_threads = True
        threading.Thread(target=_httpd.serve_forever, name='game-http', daemon=True).start()
        return f'http://127.0.0.1:{_httpd.server_port}|{_token}'
