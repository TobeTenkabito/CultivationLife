"""Serialize public engine commands for a shared save directory."""
from functools import wraps
import inspect
from contextlib import contextmanager
from contextvars import ContextVar


_request_state = ContextVar('game_request_state', default=None)
_active_command = ContextVar('game_active_command', default=None)


def active_command():
    return _active_command.get()


@contextmanager
def request_scope(engine):
    """Share hydrated games only within one locked HTTP request, never across requests."""
    with engine.store.lock:
        token = _request_state.set((engine, engine.store, {}))
        try:
            yield
        finally:
            _request_state.reset(token)


def request_games(engine):
    state = _request_state.get()
    if state is not None and state[0] is engine and state[1] is engine.store:
        return state[2]
    return None


def accept_committed_game(engine, game):
    """Publish a successful copy-on-write command into this request only."""
    games = request_games(engine)
    if games is not None:
        games[game.id] = game


def serialized_commands(cls):
    # Include mixin entry points. Private helpers and static utilities operate
    # inside their caller's transaction; nested public calls use the same RLock.
    for name, method in inspect.getmembers(cls, inspect.isfunction):
        descriptor = inspect.getattr_static(cls, name)
        if name.startswith('_') or isinstance(descriptor, (staticmethod, classmethod)):
            continue

        def wrap(command):
            @wraps(command)
            def run(self, *args, **kwargs):
                with self.store.lock:
                    token = _active_command.set(command.__name__)
                    try:
                        return command(self, *args, **kwargs)
                    finally:
                        _active_command.reset(token)
            return run

        setattr(cls, name, wrap(method))
    return cls
