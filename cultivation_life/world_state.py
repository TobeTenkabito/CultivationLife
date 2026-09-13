from __future__ import annotations

import random
from typing import Any, Iterable


RELATION_LABELS = {
    "neutral": "中立",
    "alliance": "结盟",
    "war": "交战",
    "truce": "停战",
    "vassal": "依附",
}


def race_pair(first: str, second: str) -> str:
    return "|".join(sorted((first, second)))


def split_race_pair(key: str) -> tuple[str, str]:
    first, second = key.split("|", 1)
    return first, second


def relation_status(affinity: float, current: str = "neutral") -> str:
    """Derive a stable diplomatic state with hysteresis around boundaries."""
    if current == "war" and affinity < -18:
        return "war"
    if current == "alliance" and affinity > 35:
        return "alliance"
    if current == "vassal" and affinity > 30:
        return "vassal"
    if affinity <= -55:
        return "war"
    if affinity >= 72:
        return "alliance"
    if current == "war":
        return "truce"
    if current in {"alliance", "vassal"}:
        return "neutral"
    return current if current == "truce" and affinity < 15 else "neutral"


def encounter_weight(status: str, affinity: float) -> float:
    if status == "war":
        return 4.5
    if affinity <= -25:
        return 2.2
    if status in {"alliance", "vassal"}:
        return 0.55
    return 1.0


def choose_weighted_race(
    races: Iterable[str], player_race: str, relations: dict[str, dict[str, Any]], rng: random.Random,
) -> str:
    candidates = list(races)
    if not candidates:
        return player_race
    weights: list[float] = []
    for race_id in candidates:
        if race_id == player_race:
            weights.append(1.35)
            continue
        relation = relations.get(race_pair(player_race, race_id), {})
        weights.append(encounter_weight(str(relation.get("status", "neutral")), float(relation.get("affinity", 0))))
    return rng.choices(candidates, weights=weights, k=1)[0]


def push_fifo_cache(cache: list[dict[str, Any]], entry: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Insert/update an encounter candidate and evict unpromoted oldest entries."""
    cache[:] = [row for row in cache if row.get("id") != entry.get("id")]
    cache.append(entry)
    overflow = max(0, len(cache) - max(1, limit))
    if overflow:
        del cache[:overflow]
    return cache

