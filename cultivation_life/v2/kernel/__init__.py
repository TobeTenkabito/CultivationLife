"""Stable primitives shared by V2 domain modules."""

from .bus import CommandBus, SimulationContext
from .model import EventEnvelope, EventScope, WorldState
from .services import InvariantRegistry, InvariantViolation, TimeService, validate_world_state

__all__ = [
    "CommandBus",
    "EventEnvelope",
    "EventScope",
    "InvariantViolation",
    "InvariantRegistry",
    "SimulationContext",
    "TimeService",
    "WorldState",
    "validate_world_state",
]
