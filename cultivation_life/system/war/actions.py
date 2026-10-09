from __future__ import annotations
from typing import Any
import copy
from . import logistics
from ...runtime import encode_rng
from ...runtime import now_iso
from ..npc_system import npc_team_combat_power
from ..faction_geography import war_site
from .dependencies import WarActionsDependencies


def war_action(deps: WarActionsDependencies, game_id: str, war_id: str, action: str, *, ally_id: str = "") -> dict[str, Any]:
    game = copy.deepcopy(deps._load(game_id))
    war = next((row for row in game.wars if row.get("id") == war_id), None)
    if not war or war.get("status") not in {"active", "peace_ready"}:
        raise ValueError("这场战争已经结束或不存在")
    if game.pending_event or game.active_trial or not game.player.alive or game.player.imprisonment or game.player.ghost_captor:
        raise ValueError("当前状态无法处理征伐")
    side = deps._player_war_side(game, war)
    if not side:
        raise ValueError("你并非这场战争的参战方")
    if action != "participate_round" and (
        war.get("controller") != "player" or not deps._player_has_war_voice(game, war)
    ):
        raise ValueError("你尚未取得本势力的战争指挥权")
    rng = deps.decode_rng(game.seed, game.rng_state)
    if action in {'deploy_half','deploy_all'}:
        if war.get('status') != 'active':
            raise ValueError('战争已停战，不能调整动员')
        war.setdefault('deployment',{})[side] = .5 if action == 'deploy_half' else 1.
        from .requirements import refresh
        refresh(game,war,side)
        row=war.get('logistics',{}).get('sides',{}).get(side)
        if row is not None:row['reference_need']=logistics.need(game,war,side)
        deps._append_war_log(game,war,'调整动员','动员半数名册修士' if action=='deploy_half' else '动员全体名册修士')
    elif action in {'scout', 'forage', 'resupply'}:
        if war.get('status') != 'active':
            raise ValueError('战争已停战，不能继续执行军需策略')
        text = logistics.strategy(game, deps.maps, war, side, action, rng)
        deps._append_war_log(game, war, '军需策略', text)
    elif action == "participate_round":
        if war.get("status") != "active":
            raise ValueError("战场胜负已定，无法再次参战")
        deps._resolve_player_war_round(game, war, side, rng)
    elif action == "call_allies":
        if war.get("status") != "active":
            raise ValueError("胜负已定后不能再召集盟友")
        if not ally_id:
            raise ValueError("请选择要邀请参战的盟友")
        outcomes = deps._call_war_allies(game, war, side, rng, ally_id=ally_id, limit=1)
        if not outcomes:
            raise ValueError("该势力并非可邀请盟友，或仍处于重邀冷却")
    elif action == "accept_ai_peace":
        offer = war.get("peace_offer")
        if war.get("status") != "peace_ready" or not offer or offer.get("recipient_side") != side:
            raise ValueError("当前没有需要接受的敌方和约")
        deps._conclude_war_bundle(game, war, offer["demands"], offer["proposer_side"], automatic=True)
    elif action == "conquest":
        if war.get("preliminary_resolved"):
            raise ValueError("先锋出阵已经结算")
        enemy = "defender" if side == "attacker" else "attacker"
        candidates = deps._available_warriors(game, war, enemy)
        if not candidates:
            war["morale"][enemy] = 0.0
            deps._finish_war_by_morale(game, war)
            game.rng_state = encode_rng(rng)
            deps.store.save(game)
            return deps.present(game)
        team_size = min(len(candidates), rng.randint(1, 3))
        opponents = rng.sample(candidates[:min(12, len(candidates))], team_size)
        # Player-involved vanguard combat resolves the strongest enemy
        # formation through the detailed bilateral broadcaster.  Keep the
        # base team power raw here so that the same array is not counted a
        # second time by the off-screen abstraction multiplier.
        required = npc_team_combat_power(deps._npc_power(npc) for npc in opponents)
        if enemy == "defender":
            required *= 1 + float(deps._war_rules().get("defender_power_bonus", 0.10))
        event = deps._instantiate_event(deps.events_by_id["EVT_WAR_VANGUARD_001"], game, rng)
        event["body"] = event["body"].replace("{attacker}", deps._war_side_name(game, war["kind"], war["attacker_id"])).replace("{defender}", deps._war_side_name(game, war["kind"], war["defender_id"]))
        event["body"] += f" 敌方先锋为{'、'.join(npc.name for npc in opponents)}，队伍战力约 {required:.0f}。"
        event["runtime"] = {"war_id": war["id"], "enemy_ids": [npc.id for npc in opponents], "required_power": round(required, 1)}
        game.pending_event = event
    elif action == "round":
        if war.get("status") != "active":
            raise ValueError("战场胜负已定，只能进行和谈")
        if not war.get("preliminary_resolved"):
            war["preliminary_resolved"] = True
            war["vanguard_skipped"] = True
            deps._append_war_log(game, war, "放弃先锋战", "你没有亲自参加先锋遭遇，直接命双方主力推进会战；本场不获得先锋士气修正。")
        logistics.begin_round(game, deps.maps, war, rng, side)
        contexts = deps._war_formation_contexts(game, war)
        lines = [deps._war_formation_text(contexts)]
        lines.append(deps._resolve_field_attack(game, war, "attacker", rng, contexts))
        if not deps._finish_war_by_morale(game, war):
            lines.append(deps._resolve_field_attack(game, war, "defender", rng, contexts))
        war["battles"] = int(war.get("battles", 0)) + 1
        deps._wear_war_guard_arrays(game, war)
        war["exhaustion"]["attacker"] = min(100.0, float(war["exhaustion"]["attacker"]) + 7.0)
        war["exhaustion"]["defender"] = min(100.0, float(war["exhaustion"]["defender"]) + 7.0)
        deps._finish_war_by_morale(game, war)
        deps._append_war_log(game, war, f"第{war['battles']}场会战", " ".join(lines))
    elif action == "retreat":
        if war.get("status") != "active":
            raise ValueError("战场胜负已经确定")
        war["morale"][side] = 0.0
        deps._append_war_log(game, war, "主动撤退", f"{deps._war_side_name(game, war['kind'], war[f'{side}_id'])}主动撤出战场，视为战败。")
        deps._finish_war_by_morale(game, war)
    else:
        raise ValueError("未知战争行动")
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def _maybe_map_war_encounter(deps: WarActionsDependencies, game, rng):
    player = game.player
    if game.pending_event or not player.alive or player.imprisonment:
        return False
    last = game.map_war_last_encounter_unit
    if game.diplomacy_unit - last < 2:
        return False
    fronts = [war for war in game.wars if war.get("kind") == "sect"
              and war.get("status") == "active" and war.get("world") == player.world
              and war_site(deps.maps, war)["id"] == player.location_id]
    if not fronts or rng.random() >= .42:
        return False
    war = rng.choice(fronts)
    deps._ensure_war_shape(game, war)
    own = deps._participant_side(war, deps._war_player_identity(game, war))
    sides = ["defender" if own == "attacker" else "attacker"] if own else ["attacker", "defender"]
    candidates = [deps._find_npc(game, npc_id) for side in sides for npc_id in war.get("roster", {}).get(side, [])]
    candidates = [npc for npc in candidates if npc and npc.alive and npc.world == player.world]
    if not candidates:
        return False
    npc = rng.choice(candidates)
    power = deps._npc_power(npc)
    target = {"npc_id": npc.id, "target_name": npc.name, "target_power": power,
              "primary_power": power, "target_expected_power": power,
              "target_realm_index": npc.realm_index, "target_layer": npc.layer,
              "target_realm_visible": True, "target_realm_display": deps._npc_realm_name(npc),
              "target_power_display": power, "path": npc.path, "race": npc.race,
              "faction_id": deps._npc_faction_id(game, npc.id), "combat_type": "cultivator",
              "player_defending": True, "kill_karma": False, "action": "slay", "war_id": war["id"]}
    event = deps._instantiate_event(deps.events_by_id["EVT_ENCOUNTER_AMBUSH_001"], game, rng)
    site = war_site(deps.maps, war)
    event.update(title="战区遭遇", runtime=target,
                 body=f"{deps._war_side_name(game, 'sect', war['attacker_id'])}与{deps._war_side_name(game, 'sect', war['defender_id'])}正在{site['name']}交战。{npc.name}将你截住，来者修为{deps._npc_realm_name(npc)}。")
    game.pending_event = event
    game.map_war_last_encounter_unit = game.diplomacy_unit
    return True
