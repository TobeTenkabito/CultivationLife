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
from .readiness import (
    CutoverBlockedError,
    FeatureEntry,
    FeatureMatrix,
    FeatureMatrixError,
    ReadinessReport,
    assess_default_matrix,
    assert_ready_for_cutover,
)

__all__ = [
    "ShadowCharacterSpec",
    "ShadowCommand",
    "ShadowDifference",
    "ShadowReport",
    "ShadowRunner",
    "CutoverBlockedError",
    "FeatureEntry",
    "FeatureMatrix",
    "FeatureMatrixError",
    "ReadinessReport",
    "assess_default_matrix",
    "assert_ready_for_cutover",
]
