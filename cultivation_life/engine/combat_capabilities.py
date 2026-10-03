"""Compatibility exports; game-state battle adaptation is shared by systems and engine."""
from ..system.combat_adapter import (
    CapabilityBinding as CapabilityBinding,
    bind_capabilities as bind_capabilities,
    persistent_owner as persistent_owner,
    persistent_owners as persistent_owners,
)
