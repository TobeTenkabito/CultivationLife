from __future__ import annotations
from typing import Any
from ...models import GameState
from ...content_registry import WORLD_SYSTEMS
from ..doctrine.provider import battle_sources
import random
from . import logistics
from ..combat.npc_battle import resolve_npc_engagement
from .dependencies import WarLifecycleDependencies


def _advance_wars_unit(deps: WarLifecycleDependencies, game: GameState, rng: random.Random) -> list[str]:
    news: list[str] = []
    for war in game.wars:
        if war.get("status") != "active":
            continue
        deps._ensure_war_shape(game, war)
        if deps._finish_war_by_morale(game, war):
            if war.get("controller") == "ai":
                winner = str(war["winner"])
                offer = deps._generate_ai_peace_offer(game, war, winner)
                war["peace_offer"] = offer
                deps._conclude_war_bundle(game, war, offer["demands"], winner, automatic=True)
            continue
        player_side = deps._player_war_side(game, war)
        if player_side and deps._player_has_war_voice(game, war) and war.get("controller") != "player":
            war["controller"] = "player"
            war["player_side"] = player_side
            deps._append_war_log(game, war, "指挥权移交", f"你取得势力话语权，接管战争；此前 {war.get('abstract_rounds', 0)} 个行动单位的战报已经补录。")
            continue
        if war.get("controller") == "player":
            # 自动推进只替玩家下达主力会战命令，不会把玩家本人编入先锋或参战队伍。
            enemy_side = "defender" if player_side == "attacker" else "attacker"
            enemy_score = float(war.get("war_score", 0)) * (1 if enemy_side == "attacker" else -1)
            if enemy_score < float(deps._war_rules().get("ai_call_ally_score_threshold", -25)):
                deps._call_war_allies(game, war, enemy_side, rng, limit=1)
            if game.settings.get("auto_advance_player_wars", False):
                if not war.get("preliminary_resolved"):
                    war["preliminary_resolved"] = True
                    war["vanguard_skipped"] = True
                    deps._append_war_log(game, war, "自动略过先锋战", "自动推进仅调度势力主力，玩家本人没有出阵。")
                logistics.begin_round(game, deps.maps, war, rng, player_side)
                contexts = deps._war_formation_contexts(game, war)
                lines = [deps._war_formation_text(contexts)]
                lines.append(deps._resolve_field_attack(game, war, "attacker", rng, contexts))
                if not deps._finish_war_by_morale(game, war):
                    lines.append(deps._resolve_field_attack(game, war, "defender", rng, contexts))
                war["battles"] = int(war.get("battles", 0)) + 1
                deps._wear_war_guard_arrays(game, war)
                for side in ("attacker", "defender"):
                    war["exhaustion"][side] = min(100.0, float(war["exhaustion"][side]) + 7.0)
                deps._finish_war_by_morale(game, war)
                deps._append_war_log(game, war, f"第{war['battles']}场自动会战", " ".join(lines))
            else:
                for side in ("attacker", "defender"):
                    war["exhaustion"][side] = min(100.0, float(war["exhaustion"][side]) + 2.0)
            continue
        threshold = float(deps._war_rules().get("ai_call_ally_score_threshold", -25))
        if float(war.get("war_score", 0)) < threshold:
            deps._call_war_allies(game, war, "attacker", rng, limit=1)
        if -float(war.get("war_score", 0)) < threshold:
            deps._call_war_allies(game, war, "defender", rng, limit=1)
        # The player contributes personal combat power only after choosing
        # to participate through the detailed battle action.
        logistics.begin_round(game, deps.maps, war, rng)
        attack_profile = deps._war_power_profile(game, war, "attacker", include_player=False)
        defend_profile = deps._war_power_profile(game, war, "defender", include_player=False)
        contexts = deps._war_formation_contexts(game, war)
        attack_power = max(
            1.0, float(attack_profile["composite"]) * float(contexts["attacker"]["modifier"]) * logistics.factor(war, "attacker"),
        )
        defend_power = max(
            1.0, float(defend_profile["composite"]) * float(contexts["defender"]["modifier"]) * logistics.factor(war, "defender"),
        )
        voisinage_rosters = {side: deps._available_warriors(game, war, side)
                          for side in ("attacker", "defender")}
        voisinage_result = resolve_npc_engagement(
            [(npc, deps._npc_power(npc) * float(contexts["attacker"].get("modifier", 1)) * logistics.factor(war, "attacker"))
             for npc in voisinage_rosters["attacker"]],
            [(npc, deps._npc_power(npc) * float(contexts["defender"].get("modifier", 1)) * logistics.factor(war, "defender"))
             for npc in voisinage_rosters["defender"]],
            WORLD_SYSTEMS.get("transcendent_combat", {}), rng,
            now=game.player.age,
            sources=battle_sources(game, {npc.id: npc for roster in voisinage_rosters.values() for npc in roster}),
        )
        if voisinage_result is not None:
            war["last_voisinage_engagement"] = list(voisinage_result.rounds)
            war["voisinage_suppressed"] = list(dict.fromkeys([*war.get("voisinage_suppressed", []), *voisinage_result.suppressed]))
            war["abstract_rounds"] = int(war.get("abstract_rounds", 0)) + 1
            war["battles"] = int(war.get("battles", 0)) + 1
            deps._wear_war_guard_arrays(game, war)
            for side in ("attacker", "defender"):
                war["exhaustion"][side] = min(100.0, float(war["exhaustion"][side]) + 7.0)
            if voisinage_result.outcome != "stalemate":
                loser = "defender" if voisinage_result.outcome == "victory" else "attacker"
                deps._shift_war_morale(war, loser, 12.0, 2.5)
            deps._append_war_log(game, war, "仙域 AI 战报",
                                 "仙域交锋" + {"victory": "攻方取胜", "defeat": "守方取胜", "stalemate": "相持"}[voisinage_result.outcome]
                                 + "；保留实际资源消耗和伤亡。")
            if deps._finish_war_by_morale(game, war):
                winner = str(war["winner"])
                offer = deps._generate_ai_peace_offer(game, war, winner)
                war["peace_offer"] = offer
                deps._conclude_war_bundle(game, war, offer["demands"], winner, automatic=True)
            elif min(war["exhaustion"].values()) >= float(deps._war_rules().get("white_peace_exhaustion", 78)):
                deps._conclude_war(game, war, "white_peace", "attacker", automatic=True)
            continue
        ratio = attack_power * rng.uniform(0.86, 1.16) / defend_power
        if ratio >= 1:
            loss = min(24.0, 7.0 + (ratio - 1) * 9.0)
            deps._shift_war_morale(war, "defender", loss, 2.5)
            victor = "attacker"
        else:
            loss = min(24.0, 7.0 + (1 / max(0.1, ratio) - 1) * 9.0)
            deps._shift_war_morale(war, "attacker", loss, 2.5)
            victor = "defender"
        war["abstract_rounds"] = int(war.get("abstract_rounds", 0)) + 1
        war["battles"] = int(war.get("battles", 0)) + 1
        deps._wear_war_guard_arrays(game, war)
        for side in ("attacker", "defender"):
            war["exhaustion"][side] = min(100.0, float(war["exhaustion"][side]) + rng.uniform(6, 10))
        loser = "defender" if victor == "attacker" else "attacker"
        outcome = deps._resolve_abstract_defeat(game, war, loser, rng)
        text = (
            f"综合双方总战力、前三位高阶修士与阵势条件权重结算。"
            f"{deps._war_formation_text(contexts)} "
            f"{deps._war_side_name(game, war['kind'], war[f'{victor}_id'])}在本行动单位占据上风。"
            + (f" {outcome}" if outcome else "")
        )
        deps._append_war_log(game, war, "AI 战报", text)
        finished = deps._finish_war_by_morale(game, war)
        if finished:
            winner = str(war["winner"])
            offer = deps._generate_ai_peace_offer(game, war, winner)
            war["peace_offer"] = offer
            deps._conclude_war_bundle(game, war, offer["demands"], winner, automatic=True)
        elif min(war["exhaustion"].values()) >= float(deps._war_rules().get("white_peace_exhaustion", 78)):
            deps._conclude_war(game, war, "white_peace", "attacker", automatic=True)
        if game.player.world == war.get("world"):
            news.append(f"{game.player.age}岁：{text}")
    return news


def _finish_war_by_morale(deps: WarLifecycleDependencies, game: GameState, war: dict[str, Any]) -> bool:
    if war.get("status") == "peace_ready":
        return True
    if war["morale"]["attacker"] > 0 and war["morale"]["defender"] > 0:
        return False
    winner = "defender" if war["morale"]["attacker"] <= 0 else "attacker"
    loser = "attacker" if winner == "defender" else "defender"
    war["status"] = "peace_ready"
    war["winner"] = winner
    war["loser"] = loser
    decisive = max(20.0, abs(float(war.get("war_score", 0))))
    war["war_score"] = decisive if winner == "attacker" else -decisive
    deps._append_war_log(game, war, "士气崩溃", f"{deps._war_side_name(game, war['kind'], war[f'{loser}_id'])}阵营士气归零，战争胜负已定，等待签订和约。")
    if war.get("controller") == "player" and deps._player_war_side(game, war) == loser:
        war["peace_offer"] = deps._generate_ai_peace_offer(game, war, winner)
        demands = "、".join(row["label"] for row in war["peace_offer"]["demands"])
        deps._append_war_log(game, war, "敌方提出和约", f"敌方依据 {war['peace_offer']['budget']} 点战争分数提出：{demands}。")
    return True
