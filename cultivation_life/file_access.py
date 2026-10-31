"""Short process-local file/account locks, independent of gameplay computation.

Lock order: game writer -> metadata transaction -> file I/O; summary index ->
file I/O. File I/O never calls gameplay, metadata transactions or summary code.
Windows readers must close handles before atomic replace/unlink can proceed.
"""
import os
from pathlib import Path
import threading
from weakref import WeakValueDictionary

_registry = WeakValueDictionary()
_registry_lock = threading.Lock()


def _shared(directory, kind):
    key = (kind, os.path.normcase(str(Path(directory).resolve())))
    with _registry_lock:
        return _registry.setdefault(key, threading.RLock())


def directory_io_lock(directory):
    return _shared(directory, 'file-io')


def metadata_lock(directory):
    return _shared(directory, 'metadata')
