"""Infrastructure adapters for the game runtime."""

from .sqlite_store import ConcurrentWriteError, SQLiteSaveStore
from .content_loader import ContentError, ContentLoader
from .extension_loader import ExtensionError

__all__ = [
    "ConcurrentWriteError", "SQLiteSaveStore", "ContentError",
    "ContentLoader", "ExtensionError",
]
