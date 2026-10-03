from __future__ import annotations
from typing import Any
from ...models import GameState
from ...content_registry import REALMS
from ...content_registry import WORLD_SYSTEMS
from ..doctrine.provider import battle_sources
import copy
from ..npc_system import npc_team_combat_power
import random
from ..combat.npc_battle import resolve_npc_engagement
from .dependencies import WarCombatDependencies


def _resolve_abstract_defeat(deps: WarCombatDependencies, game: GameState, war: dict[str, Any], loser: str, rng: random.Random) -> str:
    candidates = deps._available_warriors(game, war, loser)
    if not candidates or rng.random() >= float(deps._war_rules().get("ai_casualty_roll_chance", 0.34)):
        return ""
    weights = [max(0.25, (len(REALMS) - npc.realm_index) ** 1.15) for npc in candidates]
    target = rng.choices(candidates, weights=weights, k=1)[0]
    death_chance, escape_chance = deps._war_defeat_probabilities(target.realm_index)
    roll = rng.random()
    if roll < death_chance:
        target.alive = False
        target.death_reason = "势力征伐中阵亡"
        return f"{target.name}在溃阵中陨落。"
    winner_side = "defender" if loser == "attacker" else "attacker"
    victors = deps._available_warriors(game, war, winner_side)
    victor = max(victors, key=deps._npc_power, default=None)
    transfer = (
        deps._maybe_transfer_player_dependency(game, target, victor, rng, context="war_defeat")
        if victor else ""
    )
    if roll < death_chance + escape_chance:
        war.setdefault("escaped", {}).setdefault(loser, []).append(target.id)
        return f"{target.name}败退后脱离战场。" + (f" {transfer}" if transfer else "")
    target.wounds = min(4, target.wounds + 2)
    return f"{target.name}在败退中遭到重创。" + (f" {transfer}" if transfer else "")


def _shift_war_morale(deps: WarCombatDependencies, war: dict[str, Any], loser: str, loss: float, gain: float, *, attacker_kill: bool = False) -> None:
    winner = "defender" if loser == "attacker" else "attacker"
    if winner == "attacker" and attacker_kill:
        gain *= 1 + float(deps._war_rules().get("attacker_morale_shock_bonus", 0.10))
    war["morale"][loser] = max(0.0, float(war["morale"][loser]) - loss)
    war["morale"][winner] = min(150.0, float(war["morale"][winner]) + gain)
    signed = loss + gain
    war["war_score"] = max(-100.0, min(100.0, float(war["war_score"]) + (signed if winner == "attacker" else -signed)))


def _resolve_field_attack(
    deps: WarCombatDependencies, game: GameState, war: dict[str, Any], attacking: str, rng: random.Random,
    formation_contexts: dict[str, dict[str, Any]] | None = None,
) -> str:
    defending = "defender" if attacking == "attacker" else "attacker"
    attackers = deps._available_warriors(game, war, attacking)
    defenders = deps._available_warriors(game, war, defending)
    if not attackers or not defenders:
        war["morale"][defending if not defenders else attacking] = 0.0
        return "一方已经无可出阵之人。"
    striker = rng.choice(attackers[:min(8, len(attackers))])
    target = rng.choice(defenders[:min(12, len(defenders))])
    defense_bonus = 1 + float(deps._war_rules().get("defender_power_bonus", 0.10))
    attack_power = deps._npc_power(striker) * deps._npc_formation_power_multiplier(game, striker.id)
    defend_power = deps._npc_power(target) * deps._npc_formation_power_multiplier(game, target.id)
    attack_power *= defense_bonus if attacking == "defender" else 1.0
    defend_power *= defense_bonus if defending == "defender" else 1.0
    contexts = formation_contexts or deps._war_formation_contexts(game, war)
    attack_power *= float(contexts[attacking].get("modifier", 1.0))
    defend_power *= float(contexts[defending].get("modifier", 1.0))
    voisinage_result = resolve_npc_engagement(
        [(striker, attack_power)], [(target, defend_power)],
        WORLD_SYSTEMS.get("transcendent_combat", {}), rng,
        now=game.player.age,
        sources=battle_sources(game, {striker.id: striker, target.id: target}),
    )
    if voisinage_result is not None:
        war["last_voisinage_engagement"] = list(voisinage_result.rounds)
        war["voisinage_suppressed"] = list(dict.fromkeys([*war.get("voisinage_suppressed", []), *voisinage_result.suppressed]))
        if voisinage_result.outcome == "stalemate":
            return f"{striker.name}与{target.name}仙域及有效攻防相持，双方消耗已保留。"
        loser = defending if voisinage_result.outcome == "victory" else attacking
        deps._shift_war_morale(war, loser, 19.0 if voisinage_result.killed else 9.0, 3.0,
                               attacker_kill=bool(voisinage_result.killed))
        winner = striker if voisinage_result.outcome == "victory" else target
        return f"{winner.name}取得仙域斗法胜利；伤亡与镇压按实际交锋结算。"
    ratio = attack_power * rng.uniform(0.85, 1.18) / max(1.0, defend_power)
    if ratio < 1:
        return f"{striker.name}攻势受阻，{target.name}守住阵线。"
    highness = target.realm_index / max(1, len(REALMS) - 1)
    threshold = max(1.25, REALMS[target.realm_index].kill_threshold * (0.50 + highness * 0.20))
    kill_chance = min(0.90, 0.64 + (ratio - threshold) * 0.15) * (1 - highness * 0.58)
    if ratio >= threshold and rng.random() < kill_chance:
        target.alive = False
        target.death_reason = "势力征伐中阵亡"
        deps._shift_war_morale(war, defending, 19.0, 5.0, attacker_kill=True)
        return f"{striker.name}击杀{target.name}；战场杀机令击杀门槛显著降低。"
    if ratio >= 1.35 and rng.random() < max(0.28, 0.68 - highness * 0.34):
        target.wounds = min(4, target.wounds + 2)
        deps._shift_war_morale(war, defending, 9.0, 2.0)
        transfer = deps._maybe_transfer_player_dependency(
            game, target, striker, rng, context="war_field",
        )
        return f"{striker.name}重创{target.name}，后者被迫退入后阵。" + (f" {transfer}" if transfer else "")
    war.setdefault("escaped", {}).setdefault(defending, []).append(target.id)
    deps._shift_war_morale(war, defending, 12.0, 3.0)
    transfer = deps._maybe_transfer_player_dependency(
        game, target, striker, rng, context="war_field",
    )
    return f"{target.name}不敌{striker.name}，脱离战场逃遁。" + (f" {transfer}" if transfer else "")


def _resolve_player_war_round(
    deps: WarCombatDependencies, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
) -> None:
    enemy = "defender" if side == "attacker" else "attacker"
    candidates = deps._available_warriors(game, war, enemy)
    if not candidates:
        war["morale"][enemy] = 0.0
        deps._finish_war_by_morale(game, war)
        return
    if not war.get("preliminary_resolved"):
        war["preliminary_resolved"] = True
        war["vanguard_skipped"] = True
        deps._append_war_log(
            game, war, "转入主力会战",
            "你越过单独先锋战，选择直接在本轮主力会战中亲自出阵。",
        )
    contexts = deps._war_formation_contexts(game, war)
    pool = candidates[:min(12, len(candidates))]
    team_size = min(len(pool), rng.randint(1, 3))
    opponents = rng.sample(pool, team_size)
    formation_owner = str(contexts[enemy].get("source_id", ""))
    if formation_owner and contexts[enemy].get("source_kind") == "npc":
        bearer = next((npc for npc in pool if npc.id == formation_owner), None)
        if bearer and bearer not in opponents:
            opponents[-1] = bearer
    required = npc_team_combat_power(deps._npc_power(npc) for npc in opponents)
    if enemy == "defender":
        required *= 1 + float(deps._war_rules().get("defender_power_bonus", 0.10))
    members = [{
        "name": npc.name, "power": deps._npc_power(npc),
        "realm_index": npc.realm_index, "layer": npc.layer, "npc_id": npc.id,
        "faction_id": deps._npc_faction_id(game, npc.id), "path": npc.path, "race": npc.race,
    } for npc in opponents]
    target = {
        "target_name": f"{deps._war_side_name(game, war['kind'], war[f'{enemy}_id'])}会战队",
        "player_defending": side == "defender",
        "target_power": max(1.0, required),
        "target_realm_index": max((npc.realm_index for npc in opponents), default=game.player.realm_index),
        "target_layer": max((npc.layer for npc in opponents), default=1),
        "combat_type": "cultivator", "members": members, "action": "repel",
        "enemy_objective": "repel", "max_rounds": 8,
    }
    # A portable/player-local formation still takes precedence inside the
    # detailed resolver. Without one, the side's command array supports the
    # player so that both armies retain their formation identity.
    if contexts[side].get("active"):
        target["allied_formation_profile"] = copy.deepcopy(contexts[side]["profile"])
        target["formation_initial_integrity"] = float(contexts[side]["integrity"])
    result, combat_text = deps._combat(game, target, False, rng)
    won = result == "victory"
    if won:
        deps._shift_war_morale(war, enemy, 12.0, 3.0)
        outcome = "你亲自击退敌方会战队，我方取得本轮主动。"
    else:
        deps._shift_war_morale(war, side, 10.0, 2.0)
        outcome = "你未能击穿敌阵，本方主力接应后退守下一道战线。"
    if not deps._finish_war_by_morale(game, war):
        counter = deps._resolve_field_attack(game, war, enemy, rng, contexts)
    else:
        counter = ""
    war["battles"] = int(war.get("battles", 0)) + 1
    deps._wear_war_guard_arrays(game, war)
    for battle_side in ("attacker", "defender"):
        war["exhaustion"][battle_side] = min(
            100.0, float(war["exhaustion"][battle_side]) + 7.0,
        )
    deps._finish_war_by_morale(game, war)
    formation_text = deps._war_formation_text(contexts)
    deps._append_war_log(
        game, war, f"玩家参战·第{war['battles']}场会战",
        f"{formation_text} {outcome} {combat_text}" + (f" 其余战线：{counter}" if counter else ""),
    )


def _resolve_war_vanguard(deps: WarCombatDependencies, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random) -> tuple[str, str]:
    war_id = str(pending.get("runtime", {}).get("war_id", ""))
    war = next((row for row in game.wars if row.get("id") == war_id and row.get("status") == "active"), None)
    if not war or war.get("preliminary_resolved"):
        return "war_absent", "战阵已经变化，这次先锋对阵不再有效。"
    if mode == "delay":
        return "delayed", "你暂缓出阵；先锋战尚未结算，整备后仍可再次征伐。"
    side = deps._player_war_side(game, war)
    if not side or not deps._player_has_war_voice(game, war):
        return "authority_lost", "你已经失去代表本势力出阵的权力。"
    required = max(1.0, float(pending.get("runtime", {}).get("required_power", 1.0)))
    enemy_ids = [str(npc_id) for npc_id in pending.get("runtime", {}).get("enemy_ids", [])]
    opponents = [deps._find_npc(game, npc_id) for npc_id in enemy_ids]
    opponents = [npc for npc in opponents if npc is not None]
    enemy_name = "、".join(npc.name for npc in opponents) or "敌方先锋"
    members = [{
        "name": npc.name, "power": deps._npc_power(npc),
        "realm_index": npc.realm_index, "layer": npc.layer, "npc_id": npc.id,
        "faction_id": deps._npc_faction_id(game, npc.id), "path": npc.path, "race": npc.race,
    } for npc in opponents]
    result, combat_text = deps._combat(game, {
        "target_name": enemy_name, "target_power": required,
        "player_defending": side == "defender",
        "target_realm_index": max((npc.realm_index for npc in opponents), default=game.player.realm_index),
        "target_layer": max((npc.layer for npc in opponents), default=1),
        "combat_type": "cultivator", "members": members, "action": "repel",
        "enemy_objective": "repel", "max_rounds": 5,
    }, False, rng)
    won = result == "victory"
    if won:
        war["morale"][side] = min(150.0, float(war["morale"][side]) + 30.0)
        text = f"{combat_text} 先锋目标达成，我方士气提升初始值的 30%。"
    else:
        war["morale"][side] = max(0.0, float(war["morale"][side]) - 20.0)
        text = f"{combat_text} 先锋目标未能达成，我方士气降低初始值的 20%。"
    war["preliminary_resolved"] = True
    deps._append_war_log(game, war, "玩家先锋战", text)
    return "victory" if won else "defeat", text
