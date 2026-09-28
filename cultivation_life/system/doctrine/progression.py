"""Bounded progression over elapsed time; no world loops or content lookups."""
from __future__ import annotations

from ..combat.contracts import CapabilitySource, DomainDefinition


def train(progress: dict, definition: dict, years: float, realm: int, origin: str | None,
          *, batch: bool = False) -> list[int]:
    level = int(progress.get("level", 0))
    completed = []
    remaining = max(0, years)
    # At most nine iterations even after a million years. Player training stops
    # at each revelation; NPC training may settle all already-authorized stages.
    for _ in range(9 - level):
        if level >= 4 and origin not in (None, definition["id"]):
            break
        stage = definition["stages"][level]
        if realm < stage["realm"]:
            break
        required = stage["years"]
        prior = float(progress.get("experience", 0))
        used = min(max(0, required - prior), remaining)
        progress["experience"] = min(required, prior + used)
        remaining -= used
        if progress["experience"] < required or (level == 4 and origin is None):
            break
        level += 1
        progress.update(level=level, experience=0)
        completed.append(level)
        if not batch or level == 9 or remaining <= 0:
            break
    return completed


def bind_origin(record: dict, definition: dict, realm: int) -> None:
    key = definition["id"]
    progress = record["progress"].get(key, {})
    stage = definition["stages"][4]
    if record.get("origin"):
        raise ValueError("本源已有归属，不能再让另一道统越过 Lv4")
    if progress.get("level") != 4 or progress.get("experience", 0) < stage["years"] or realm < stage["realm"]:
        raise ValueError("须将此道统修至 Lv4，并完成 Lv5 的修炼积累")
    record["origin"] = key
    progress.update(level=5, experience=0)


def source(record: dict, definitions: dict, world: str) -> CapabilitySource:
    if world != "celestial":
        return CapabilitySource()
    key = record.get("active")
    definition = definitions.get(key)
    level = int(record.get("progress", {}).get(key, {}).get("level", 0))
    if not definition or level < 4:
        return CapabilitySource()
    if level > 4 and record.get("origin") != key:
        raise ValueError("非本源道统不能超过 Lv4")
    if level > 9:
        raise ValueError("道统等级不能超过 Lv9")
    return CapabilitySource((DomainDefinition(**definition["stages"][level - 1]["domain"]),), {key: level})
