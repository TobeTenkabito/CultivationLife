"""Bounded NPC-only engagements using the same voisinage/tier arbitration.

NPC combat still uses a compact conventional exchange. It cannot bypass a
voisinage by adding power, rolling an unrelated casualty or resetting resources.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .contracts import CapabilitySource, Combatant, voisinage_definitions, resolve_source
from .voisinages import VoisinageBattle
from .ordinary import exchange_damage
from .npc_lifecycle import prepare, commit_condition


@dataclass(frozen=True)
class NpcEngagement:
    outcome: str
    killed: tuple[str, ...]
    suppressed: tuple[str, ...]
    rounds: tuple[dict[str, Any], ...]


def resolve_npc_engagement(attackers: list[tuple[Any, float]], defenders: list[tuple[Any, float]],
                           config: Mapping[str, Any], rng: Any, *, max_rounds: int = 5,
                           now: float | None = None,
                           sources: Mapping[str, CapabilitySource] | None = None,
                           attacker_objective: str = "kill", defender_objective: str = "kill") -> NpcEngagement | None:
    # Most background encounters are mortal. Do not parse definitions or build
    # a voisinage battle for them, and preserve the legacy RNG sequence.
    from ..cultivation_ranks import npc_golden_light
    if not sources and not any(npc.transcendence or (npc.immortal_body_level and npc_golden_light(npc))
                               for roster in (attackers, defenders) for npc, _ in roster):
        return None
    definitions = voisinage_definitions(config)
    owners = {npc.id: npc for npc, _ in [*attackers, *defenders]}
    resources = {}
    units = []
    for side, roster in (("player", attackers), ("enemy", defenders)):
        for npc, power in roster:
            source = (sources or {}).get(npc.id)
            imitation = bool(source and any(d.id.startswith('spirit:') for d in source.voisinages))
            resources[npc.id] = prepare(npc, now, config, imitation=imitation)
            capabilities = resolve_source(resources[npc.id].state, definitions, (sources or {}).get(npc.id))
            if capabilities.resource_link != "independent":
                raise ValueError("NPC resources must be independent")
            from ..cultivation_ranks import rank_for
            multiplier = 1 + .5 * max(0, (npc.realm_index - 9) * 3 + (npc.layer - 1) // 3) if npc.world == 'celestial' else 1
            capabilities = replace(capabilities, ward_tier=2 if npc_golden_light(npc) else 1, ward_cost=0, investment_limit=max((d.max_investment for d in capabilities.voisinages), default=0) * multiplier)
            units.append(Combatant(npc.id, npc.name, side, max(1.0, power), capabilities,
                                   cultivation_rank=rank_for(npc.realm_index, npc.layer),
                                   body_integrity=max(.01, 1 - npc.wounds * .15)))
    battle = VoisinageBattle(units, contest_ratio=float(config.get("contest_ratio", 1.25)))
    if not battle.enabled:
        return None  # No combat RNG or combat costs on the conventional path.
    battle.set_objectives(attacker_objective, defender_objective)
    reports = []
    for round_no in range(1, max(1, min(8, max_rounds)) + 1):
        p = max(0.0, 1 - battle.ordinary_loss("player"))
        e = max(0.0, 1 - battle.ordinary_loss("enemy"))
        frame = battle.begin_round(round_no, player_condition=p, enemy_condition=e, player_mp=1, enemy_mp=1)
        if frame.ordinary and battle.verdict() is None:
            p_power, e_power = battle.totals["player"], battle.totals["enemy"]
            semantic = battle.semantic_ordinary_start()
            first = p_power * (semantic['player']['mobility'] + semantic['player']['sense']) >= e_power * (semantic['enemy']['mobility'] + semantic['enemy']['sense'])
            after = battle.semantic_initiative(first)
            for side in ('player', 'enemy'):
                for stat in semantic[side]:
                    semantic[side][stat] *= after[side][stat]
            ps, es = semantic['player'], semantic['enemy']
            dealt = exchange_damage(p_power * p * ps['might'] * ps['sustain'], e_power * (.72 + .28 * e) * es['guard'], p_power * ps['breach'] / (e_power * es['guard']),
                                    rng.uniform(.90, 1.10), coefficient=.135, minimum=.045, maximum=.42)
            received = exchange_damage(e_power * e * es['might'] * es['sustain'], p_power * (.72 + .28 * p) * ps['guard'], e_power * es['breach'] / (p_power * ps['guard']),
                                       rng.uniform(.90, 1.10), coefficient=.135, minimum=.045, maximum=.42)
            # Compact equivalent of the player initiative/morale disadvantages.
            morale = {side: sum(s.morale * s.unit.power for s in battle.units.values() if s.unit.side == side)
                            / battle.totals[side] for side in ('player', 'enemy')}
            factors = {side: (.6 + .4 * morale[side] / 100) * (.65 + .35 * frame.stat_factors[side]['sense'])
                       for side in ('player', 'enemy')}
            if battle.semantics:
                factors['player'] *= ps['sense'] * (1.05 if first else .97)
                factors['enemy'] *= es['sense'] * (.97 if first else 1.05)
            battle.ordinary_damage(dealt * factors['player'], received * factors['enemy'])
        battle.finish_round(player_mp=1, enemy_mp=1)
        reports.append({"round": round_no, "voisinage": battle.report(), "events": list(frame.events)})
        if battle.verdict() is not None:
            break
    killed, suppressed = [], []
    for update in battle.updates():
        npc = owners[update["id"]]
        resources[npc.id].commit(update["current"])
        commit_condition(npc, update, lethal=True)
        if update["suppressed"]:
            suppressed.append(npc.id)
        elif update["vitality"] <= 0:
            killed.append(npc.id)
            npc.alive, npc.death_reason = False, "仙域斗法中陨落"
    return NpcEngagement(battle.verdict() or "stalemate", tuple(killed), tuple(suppressed), tuple(reports))
