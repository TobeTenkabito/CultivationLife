"""Serialize public engine commands for a shared save directory."""
from functools import wraps
import inspect


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
                    return command(self, *args, **kwargs)
            return run

        setattr(cls, name, wrap(method))
    return cls
