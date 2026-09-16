"""Infrastructure adapters for V2."""

from .sqlite_store import ConcurrentWriteError, SQLiteSaveStore
from .content_loader import V2ContentError, V2ContentLoader
from .extension_loader import V2ExtensionError
from .legacy_import import (
    LegacyImportBlockedError,
    LegacyImportError,
    LegacyImportIssue,
    LegacyImportReport,
    LegacyImportResult,
    LegacyBackup,
    LegacyV1Importer,
    backup_legacy_save,
    load_legacy_save,
)

__all__ = [
    "ConcurrentWriteError", "SQLiteSaveStore", "V2ContentError",
    "V2ContentLoader", "V2ExtensionError",
    "LegacyImportBlockedError", "LegacyImportError", "LegacyImportIssue",
    "LegacyImportReport", "LegacyImportResult", "LegacyV1Importer",
    "LegacyBackup", "backup_legacy_save", "load_legacy_save",
]
