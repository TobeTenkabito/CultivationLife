"""Second-generation simulation runtime.

The V2 package is deliberately isolated from the legacy ``GameEngine``.  It
does not import legacy models or save stores, which lets the new runtime be
built and verified without changing existing saves.
"""

from .application import V2GameEngine
from .domain.character import PerformTimedAction, RegisterCharacter
from .domain.cultivation import (
    AttemptBreakthrough,
    EquipMainTechnique,
    GrantTechnique,
    PerformActionUnits,
)
from .domain.factions import (
    ChangeContribution,
    FoundFaction,
    JoinFaction,
    LeaveFaction,
    TransferFactionControl,
)
from .domain.relations import EndRelationship, FormRelationship
from .domain.world import TravelWithinWorld

__all__ = [
    "AttemptBreakthrough",
    "ChangeContribution",
    "EndRelationship",
    "EquipMainTechnique",
    "FormRelationship",
    "FoundFaction",
    "GrantTechnique",
    "JoinFaction",
    "LeaveFaction",
    "PerformActionUnits",
    "PerformTimedAction",
    "RegisterCharacter",
    "TransferFactionControl",
    "TravelWithinWorld",
    "V2GameEngine",
]
