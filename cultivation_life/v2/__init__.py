"""Second-generation simulation runtime.

The V2 package is deliberately isolated from the legacy ``GameEngine``.  It
does not import legacy models or save stores, which lets the new runtime be
built and verified without changing existing saves.
"""

from .application import V2GameEngine
from .domain.character import PerformTimedAction

__all__ = ["PerformTimedAction", "V2GameEngine"]
