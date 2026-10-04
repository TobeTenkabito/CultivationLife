"""HTTP composition boundary; no gameplay module imports this adapter."""
from contextlib import contextmanager
import json
from urllib.parse import urlparse

from .registry import CommandError
from .runtime import Runtime


HEADER = 'X-Cultivation-Debug'


def runtime(project_root, persistence_root, source_engine):
    return Runtime(project_root, persistence_root / 'data' / 'debug', source_engine.store)


@contextmanager
def request_engine(handler, source_engine, project_root, persistence_root):
    session_id = handler.headers.get(HEADER)
    if not session_id:
        yield source_engine
        return
    manager = runtime(project_root, persistence_root, source_engine)
    path = urlparse(handler.path).path
    with manager.lock:
        session = manager.load(session_id)
        game_path = '/api/games/' + session['current']['game']['id']
        allowed = (handler.command == 'GET' and path in {game_path, '/api/games', '/api/achievements', '/api/config'}
                   or handler.command == 'POST' and path.startswith(game_path + '/')
                   and len(path.removeprefix(game_path + '/').split('/')) == 1)
        if not allowed:
            raise CommandError('This operation is unavailable in the isolated debug session. Use debug stop first.')
        operation = {'method': handler.command, 'path': path,
                     'payload': getattr(handler, '_request_payload', None)}
        with manager.gameplay(session_id, operation, handler.request_id) as (engine, outcome):
            yield engine
            pending = handler._pending_json
            outcome['ok'] = pending is not None and int(pending[1]) < 400
            if not outcome['ok']:
                outcome['error'] = getattr(handler, '_debug_failure', None) or (
                    json.loads(pending[0]) if pending else {'message': 'No response was produced.'})


def execute(payload, source_engine, project_root, persistence_root):
    allowed = {'command', 'game_id', 'session_id', 'bundle', 'arguments', 'expected_revision', 'request_key'}
    if set(payload) - allowed or 'arguments' in payload and not isinstance(payload['arguments'], dict):
        raise CommandError('Unknown request field or invalid structured arguments.')
    if (any(payload.get(key) is not None and not isinstance(payload[key], str) for key in ('game_id', 'session_id'))
            or payload.get('bundle') is not None and not isinstance(payload['bundle'], dict)):
        raise CommandError('Expected string IDs and an object bundle.')
    manager = runtime(project_root, persistence_root, source_engine)
    return manager.execute(payload.get('command'), payload.get('game_id'),
                           payload.get('session_id'), payload.get('bundle'),
                           arguments=payload.get('arguments'), expected_revision=payload.get('expected_revision'),
                           request_key=payload.get('request_key'))
