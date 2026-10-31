"""Serialize public engine commands for a shared save directory."""
from functools import wraps
import inspect
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from ..visual_assets import catalog_scope


_request_state = ContextVar('game_request_state', default=None)
_active_command = ContextVar('game_active_command', default=None)


def directory_independent_query(guard):
    """Opt in one audited read, only while its concrete capabilities are native."""
    def mark(method):
        method._directory_independent_query = (method, guard)
        return method
    return mark


def _query_guard(method):
    implementation = getattr(method, '__func__', method)
    declaration = getattr(implementation, '_directory_independent_query', None)
    # functools.wraps copies attributes: a different wrapper is not the audited
    # implementation, even when its names and copied marker match.
    if (isinstance(declaration, tuple) and len(declaration) == 2
            and declaration[0] is implementation and callable(declaration[1])):
        return declaration[1]
    return None


def independent_query_allowed(engine, method):
    if getattr(method, '__self__', engine) is not engine:
        return False
    guard = _query_guard(method)
    return guard is not None and bool(guard(engine))


def active_command():
    return _active_command.get()


@contextmanager
def request_scope(engine, *, serialized=True):
    """Fresh request state; audited independent reads never hydrate game sessions."""
    with (engine.store.lock if serialized else nullcontext()), catalog_scope():
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
                lock = nullcontext() if independent_query_allowed(self, command) else self.store.lock
                with lock, catalog_scope():
                    token = _active_command.set(command.__name__)
                    try:
                        return command(self, *args, **kwargs)
                    except Exception:
                        # A failed command must not expose its unsaved working
                        # state to a recovery GET in the same HTTP request.
                        games = request_games(self)
                        if games is not None:
                            games.clear()
                        raise
                    finally:
                        _active_command.reset(token)
            guard = _query_guard(command)
            if guard is not None:
                run._directory_independent_query = (run, guard)
            return run

        setattr(cls, name, wrap(method))
    return cls
