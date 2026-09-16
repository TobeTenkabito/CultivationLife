"""Cross-runtime migration and verification tools.

Unlike :mod:`cultivation_life.v2`, this package is an integration boundary and
may deliberately import both runtimes.  Production V2 domain code must never
depend on it.
"""

from .shadow import (
    ShadowCharacterSpec,
    ShadowCommand,
    ShadowDifference,
    ShadowReport,
    ShadowRunner,
)

__all__ = [
    "ShadowCharacterSpec",
    "ShadowCommand",
    "ShadowDifference",
    "ShadowReport",
    "ShadowRunner",
]
