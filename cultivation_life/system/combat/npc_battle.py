"""Bounded NPC-only engagements using the same domain/tier arbitration.

NPC combat still uses a compact conventional exchange. It cannot bypass a
domain by adding power, rolling an unrelated casualty or resetting resources.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import CapabilitySource, Combatant, domain_definitions, resolve_source
from .domains import DomainBattle
from .ordinary import exchange_damage
from .npc_lifecycle import prepare


@dataclass(frozen=True)
class NpcEngagement:
    outcome: str
    killed: tuple[str, ...]
    suppressed: tuple[str, ...]
    rounds: tuple[dict[str, Any], ...]


def resolve_npc_engagement(attackers: list[tuple[Any, float]], defenders: list[tuple[Any, float]],
                           config: Mapping[str, Any], rng: Any, *, max_rounds: int = 5,
                           now: float | None = None,
                           sources: Mapping[str, CapabilitySource] | None = None) -> NpcEngagement | None:
    # Most background encounters are mortal. Do not parse definitions or build
    # a domain battle for them, and preserve the legacy RNG sequence.
    if not sources and not any(npc.transcendence for roster in (attackers, defenders) for npc, _ in roster):
        return None
    definitions = domain_definitions(config)
    owners = {npc.id: npc for npc, _ in [*attackers, *defenders]}
    resources = {}
    units = []
    for side, roster in (("player", attackers), ("enemy", defenders)):
        for npc, power in roster:
            resources[npc.id] = prepare(npc, now, config)
            capabilities = resolve_source(resources[npc.id].state, definitions, (sources or {}).get(npc.id))
            if capabilities.resource_link != "independent":
                raise ValueError("NPC resources must be independent")
            units.append(Combatant(npc.id, npc.name, side, max(1.0, power), capabilities))
    battle = DomainBattle(units, contest_ratio=float(config.get("contest_ratio", 1.25)))
    if not battle.enabled:
        return None  # No combat RNG or combat costs on the conventional path.
    reports = []
    for round_no in range(1, max(1, min(8, max_rounds)) + 1):
        p = max(0.0, 1 - battle.ordinary_loss("player"))
        e = max(0.0, 1 - battle.ordinary_loss("enemy"))
        frame = battle.begin_round(round_no, player_condition=p, enemy_condition=e, player_mp=1, enemy_mp=1)
        if frame.ordinary and battle.verdict() is None:
            p_power, e_power = battle.totals["player"], battle.totals["enemy"]
            dealt = exchange_damage(p_power * p, e_power * (.72 + .28 * e), p_power / e_power,
                                    rng.uniform(.90, 1.10), coefficient=.135, minimum=.045, maximum=.42)
            received = exchange_damage(e_power * e, p_power * (.72 + .28 * p), e_power / p_power,
                                       rng.uniform(.90, 1.10), coefficient=.135, minimum=.045, maximum=.42)
            battle.ordinary_damage(dealt, received)
        battle.finish_round(player_mp=1, enemy_mp=1)
        reports.append({"round": round_no, "domain": battle.report(), "events": list(frame.events)})
        if battle.verdict() is not None:
            break
    killed, suppressed = [], []
    for update in battle.updates():
        npc = owners[update["id"]]
        resources[npc.id].commit(update["current"])
        if update["suppressed"]:
            suppressed.append(npc.id)
            npc.wounds = max(npc.wounds, 4)
        elif update["vitality"] <= 0:
            killed.append(npc.id)
            npc.alive, npc.death_reason = False, "仙域斗法中陨落"
        elif update["vitality"] < .75:
            npc.wounds = max(npc.wounds, min(4, int((1 - update["vitality"]) * 4)))
    return NpcEngagement(battle.verdict() or "stalemate", tuple(killed), tuple(suppressed), tuple(reports))
