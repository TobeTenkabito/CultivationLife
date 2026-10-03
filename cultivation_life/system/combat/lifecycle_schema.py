"""Validate lifecycle data without importing NPC initialization or runtime rules."""
from typing import Any, Mapping
from .contracts import number, resolve_capabilities


def validate_lifecycle(config: Mapping[str, Any]) -> None:
    rules = config.get("npc_lifecycle", {})
    for environment in rules.get("environments", {}).values():
        number(environment.get("recovery_per_year", 0), "recovery_per_year")
        if number(environment.get("available_fraction", 1), "available_fraction") > 1:
            raise ValueError("available_fraction must be <= 1")
    native = rules.get("native_state")
    if native is not None:
        caps = resolve_capabilities(native, {})
        if caps.resource_link != "independent" or "lifecycle" in native:
            raise ValueError("Native NPC templates require an independent, unanchored ledger")
    number(rules.get("native_min_realm", 9), "native_min_realm")
    player = config.get("converted_player_state")
    if player is not None and resolve_capabilities(player, {}).resource_link != "legacy_mp":
        raise ValueError("Converted player compatibility must use the existing MP pool")
