"""Frozen pre-batch-four HTTP transaction adapter; dependencies supplied by tests."""
from functools import wraps
from contextlib import nullcontext
from urllib.parse import urlparse
from .engine.transactions import request_scope


def local_request(command):
    @wraps(command)
    def run(handler):
        handler.request_id = uuid.uuid4().hex
        handler._pending_json = None
        handler._defer_json = False
        handler.request_engine = ENGINE
        try:
            handler._validate_request()
            if handler.command == 'POST':
                handler._request_payload = handler._body()
            # Guards, migration reads, save import/export and command execution
            # must share one transaction, including API GETs which can migrate.
            if urlparse(handler.path).path.startswith('/api/'):
                handler._defer_json = True
                try:
                    context = nullcontext(ENGINE)
                    if handler.headers.get('X-Cultivation-Debug'):
                        from .debug.gateway import request_engine
                        context = request_engine(handler, ENGINE, ENGINE_ROOT, PERSISTENCE_ROOT)
                    with context as engine:
                        handler.request_engine = engine
                        scope = nullcontext() if urlparse(handler.path).path == '/api/debug/command' else request_scope(engine)
                        with scope:
                            command(handler)
                finally:
                    handler._defer_json = False
                if handler._pending_json is not None:
                    body, status = handler._pending_json
                    handler._send_json(body, status)
            else:
                return command(handler)
        except ConnectionError:
            # The browser can close or navigate away while a request completes.
            return
        except Exception as error:
            handler._error(error)
    return run
