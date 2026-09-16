"""Second-generation simulation runtime.

The V2 package is deliberately isolated from the legacy ``GameEngine``.  It
does not import legacy models or save stores, which lets the new runtime be
built and verified without changing existing saves.
"""

from .application import LegacyImportExecution, V2GameEngine
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
    InviteRelationshipToFaction,
    SetFactionRewardPreference,
    LeaveFaction,
    TransferFactionControl,
)
from .domain.combat import ResolveCombat, RestoreCombatCondition
from .domain.economy import (
    BuyMarketOffer,
    GrantItem,
    RefreshMarket,
    ToggleMarketOfferLock,
)
from .domain.extensions import (
    AssignFactionPosition,
    ConfigureMonsterBloodline,
    SpendWangsheng,
)
from .domain.relations import EndRelationship, FormRelationship
from .domain.world import TravelWithinWorld
from .domain.story import QueueStoryEvent, ResolveStoryChoice

__all__ = [
    "AttemptBreakthrough",
    "AssignFactionPosition",
    "BuyMarketOffer",
    "ChangeContribution",
    "ConfigureMonsterBloodline",
    "EndRelationship",
    "EquipMainTechnique",
    "FormRelationship",
    "FoundFaction",
    "GrantItem",
    "GrantTechnique",
    "JoinFaction",
    "InviteRelationshipToFaction",
    "SetFactionRewardPreference",
    "LeaveFaction",
    "PerformActionUnits",
    "PerformTimedAction",
    "RefreshMarket",
    "ResolveStoryChoice",
    "QueueStoryEvent",
    "RegisterCharacter",
    "ResolveCombat",
    "RestoreCombatCondition",
    "SpendWangsheng",
    "ToggleMarketOfferLock",
    "TransferFactionControl",
    "TravelWithinWorld",
    "V2GameEngine",
    "LegacyImportExecution",
]
