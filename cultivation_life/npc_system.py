from __future__ import annotations

from typing import Any, Callable, Iterable

from .models import Item, SectNpc


def npc_breakthrough_chance(npc: SectNpc, settings: dict[str, Any], root_efficiency: float) -> float:
    """Return the NPC's next visible breakthrough chance without mutating it."""
    if npc.world == "human" and npc.realm_index == 5 and npc.layer >= 3:
        return float(settings["human_ascension_chance"])
    if npc.world == "human" and npc.realm_index == 4 and npc.layer >= 9:
        return float(settings["spirit_breakthrough_chance"])
    return min(0.97, float(settings["base_success"]) + root_efficiency * float(settings["root_success_scale"]))


def npc_combat_power(
    npc: SectNpc,
    expected_power: Callable[[int, int], float],
    root_efficiency: float,
    treasure: Item | None = None,
) -> float:
    root_factor = 0.82 + min(2.0, max(0.0, root_efficiency)) * 0.16
    progress_factor = 1.0 + min(0.12, max(0.0, npc.cultivation_progress) / 1000.0)
    treasure_power = float(treasure.combat_bonus) if treasure else 0.0
    return round(expected_power(npc.realm_index, npc.layer) * root_factor * progress_factor + treasure_power, 1)
def party_combat_power(leader_power: float, companion_powers: Iterable[float]) -> float:
    companions = [max(0.0, float(value)) for value in companion_powers][:2]
    coefficient = 0.5 if len(companions) == 1 else 0.25 if len(companions) >= 2 else 0.0
    return round(max(0.0, float(leader_power)) + sum(companions) * coefficient, 1)


def npc_team_combat_power(member_powers: Iterable[float]) -> float:
    powers = sorted((max(0.0, float(value)) for value in member_powers), reverse=True)[:3]
    if not powers:
        return 0.0
    coefficient = 0.5 if len(powers) == 2 else 0.25 if len(powers) == 3 else 0.0
    return round(powers[0] + sum(powers[1:]) * coefficient, 1)


def attitude_label(personal_affinity: float | None, faction_hostility: float) -> str:
    value = float(personal_affinity or 0) - float(faction_hostility) * 0.6
    if value <= -70:
        return "仇深似海"
    if value <= -25:
        return "明显敌视"
    if value < 15:
        return "态度冷淡"
    if value < 50:
        return "颇有好感"
    return "生死之交"
