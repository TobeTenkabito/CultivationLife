"""Shared bounded influence pool; independent of optional systems."""

from typing import Any


def redistribute(
    doctrines: list[dict[str, Any]],
    doctrine_id: str,
    delta: float,
    config: dict[str, Any] | None = None,
) -> float:
    """Apply a delta without exceeding the pool; reductions free unclaimed influence."""
    rules = config or {}
    floor = float(rules.get("influence_floor", 0.1))
    cap = float(rules.get("doctrine_influence_cap", 60.0))
    pool = float(rules.get("world_influence_pool", 100.0))
    target = next((row for row in doctrines if row.get("id") == doctrine_id), None)
    if target is None:
        return 0.0
    before = float(target.get("external", 0.0))
    wanted = max(floor, min(cap, before + float(delta)))
    if wanted <= before:
        target["external"] = round(wanted, 4)
        return target["external"] - before
    growth = wanted - before
    spare = max(0.0, pool - sum(float(row.get("external", 0.0)) for row in doctrines))
    direct = min(growth, spare)
    target["external"] = before + direct
    remaining = growth - direct
    if remaining > 0:
        donors = [
            row
            for row in doctrines
            if row is not target and float(row.get("external", 0.0)) > floor
        ]
        available = sum(float(row.get("external", 0.0)) - floor for row in donors)
        taken = min(remaining, available)
        if taken > 0 and available > 0:
            for donor in donors:
                room = float(donor.get("external", 0.0)) - floor
                donor["external"] = round(
                    float(donor.get("external", 0.0)) - taken * room / available, 4
                )
            target["external"] += taken
    target["external"] = round(min(cap, target["external"]), 4)
    overflow = sum(float(row.get("external", 0.0)) for row in doctrines) - pool
    if overflow > 0:
        reducer = max(
            doctrines, key=lambda row: float(row.get("external", 0.0)) - floor
        )
        reducer["external"] = max(floor, float(reducer.get("external", 0.0)) - overflow)
    return target["external"] - before
