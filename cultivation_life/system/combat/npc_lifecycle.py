"""Lazy NPC resource accounting. No annual tick, registry, RNG or doctrine logic.

The clock is elapsed world time (currently player.age), never the NPC's age.
Only creation, participation in combat and explicit movement touch this ledger.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import number, resolve_capabilities


def read(owner: Any, key: str, default=None):
    return owner.get(key, default) if isinstance(owner, dict) else getattr(owner, key, default)


def _write(owner: Any, key: str, value: Any) -> None:
    if isinstance(owner, dict):
        owner[key] = value
    else:
        setattr(owner, key, value)


def commit_condition(owner: Any, update: Mapping[str, Any], *, lethal: bool) -> None:
    """Physical restoration and control have identical meaning in both callers."""
    if 'body' in update:
        wounds = min(4, max(0, int((1 - update['body']) / .15 + 1e-8)))
    else:
        wounds = max(read(owner, 'wounds', 0), min(4, int((1 - update['vitality']) * 4)))
    _write(owner, 'wounds', wounds)
    if lethal and update['vitality'] <= 0 and not update['suppressed'] and not update.get('escaped'):
        _write(owner, 'alive', False)
        _write(owner, 'death_reason', '仙域斗法中陨落')


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


def initialize_native(owner: Any, config: Mapping[str, Any], *, now: float | None = None) -> None:
    """Creation policy, deliberately NOT a legacy-save or combat-time inference.

    An explicit state, including {}, overrides the default. A future cultivation
    provider can supply its own state without changing the combat engine.
    """
    from ..cultivation_ranks import ensure_npc
    ensure_npc(owner)
    if read(owner, "transcendence") is not None or read(owner, "realm_index", 0) < 9:
        return
    rules = config.get("npc_lifecycle", {})
    if (read(owner, "world") not in rules.get("native_worlds", ())
            or read(owner, "realm_index", 0) < rules.get("native_min_realm", 9)):
        return
    template = rules.get("native_state")
    if template is not None:
        _write(owner, "transcendence", deepcopy(template))
        if now is not None:
            settle(owner, now, config)


def settle(owner: Any, now: float, config: Mapping[str, Any]) -> dict | None:
    """Accrue an arbitrary interval in O(1), preserving absent legacy records.

    Missing anchors never grant speculative past recovery. Unexpected world
    changes discard the unknown interval; known movements must use move_world.
    Saved rates apply to the elapsed interval, new rules to subsequent time.
    """
    state = read(owner, "transcendence")
    if state is None:
        return None
    if state.get("resource_link", "independent") != "independent":
        raise ValueError("NPC resources must be independent")
    now = number(now, "world time")
    world = read(owner, "world", "")
    environment = config.get("npc_lifecycle", {}).get("environments", {}).get(world, {})
    capacity = number(state.get("capacity", 0), "capacity")
    conversion = number(state.get("conversion", 0), "conversion")
    if conversion > 1:
        raise ValueError("conversion must be <= 1")
    ceiling = capacity * conversion
    current = min(ceiling, number(state.get("current", 0), "current"))
    anchor = state.get("lifecycle")
    if anchor:
        previous = number(anchor["at"], "lifecycle.at")
        if now < previous:
            raise ValueError("NPC resource clock cannot move backwards")
        if anchor["world"] == world and read(owner, "alive", True):
            current = min(ceiling, current + (now - previous) * number(anchor["rate"], "lifecycle.rate"))
    state["current"] = current
    state["lifecycle"] = {
        "at": now, "world": world,
        "rate": ceiling * number(environment.get("recovery_per_year", 0), "recovery_per_year"),
    }
    return state


@dataclass(frozen=True)
class NpcResourceBinding:
    state: dict | None
    ledger: dict | None
    reserve: float = 0

    def commit(self, current: float) -> None:
        if self.ledger is not None:
            # Includes explicit battle supplies, bounded by the combat snapshot's
            # usable capacity. Never re-apply the environmental fraction here.
            self.ledger["current"] = self.reserve + current


def prepare(owner: Any, now: float | None, config: Mapping[str, Any], *, imitation=False) -> NpcResourceBinding:
    ledger = settle(owner, now, config) if now is not None else read(owner, "transcendence")
    if ledger is None:
        return NpcResourceBinding(None, None)
    if imitation:
        pool = ledger.setdefault('imitation', dict(capacity=60, current=20, conversion=1,
                                 resource_link='independent', force_tier=1, ward_tier=1,
                                 attack_cost=0, ward_cost=0))
        return NpcResourceBinding(dict(pool), pool)
    environment = config.get("npc_lifecycle", {}).get("environments", {}).get(read(owner, "world", ""), {})
    fraction = number(environment.get("available_fraction", 1), "available_fraction")
    if fraction > 1:
        raise ValueError("available_fraction must be <= 1")
    capacity = number(ledger.get("capacity", 0), "capacity")
    conversion = number(ledger.get("conversion", 0), "conversion")
    current = min(number(ledger.get("current", 0), "current"), capacity * conversion)
    accessible = min(current, capacity * conversion * fraction)
    snapshot = dict(ledger, capacity=capacity * fraction, current=accessible)
    return NpcResourceBinding(snapshot, ledger, current - accessible)


def move_world(owner: Any, destination: str, now: float, config: Mapping[str, Any]) -> None:
    settle(owner, now, config)
    _write(owner, "world", destination)
    settle(owner, now, config)
