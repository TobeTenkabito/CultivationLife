"""Explicit buddhist assembly operations; callers own composition."""
from __future__ import annotations

import copy

from ...content_registry import WORLD_SYSTEMS
from ...rules import expected_combat_power
from ..possession_system import advance_player_age
from .dependencies import BuddhistAssemblyDependencies
from .rules import buddhist_active, buddhist_config, set_dharma_karma, site_state


def _continue_buddhist_assembly(deps: BuddhistAssemblyDependencies, game, rng):
    session = game.buddhist_state["assembly"]
    if not session or (session["world"], session["location"]) != (game.player.world, game.player.location_id):
        raise ValueError("请回到开坛地点继续法会")
    if session.get("pending"):
        # DLC disable/enable can remove a pending event; restore the exact saved instance.
        game.pending_event = copy.deepcopy(session["pending"])
        return
    if game.buddhist_state["dharma_karma"] < -25:
        deps._finish_buddhist_assembly(game, forced_failure=True)
        return
    news = []
    while session["stage_years"] < session["unit_years"]:
        advance_player_age(game.player)
        session["stage_years"] += 1
        proceed = deps._advance_world_year(game, rng, news, encounters=False)
        if game.player.alive:
            deps._advance_soul_erosion_time(game, 1)
        if not proceed or game.pending_event or not game.player.alive:
            return
    config = buddhist_config()
    unlicensed = [row for row in deps._buddhist_permissions(game) if not row["permitted"] and not row["intimidated"]]
    chance = min(config["negative_chance_cap"], config["negative_chance_base"] + session["burden"] * config["negative_chance_scale"] + len(unlicensed) * config["unlicensed_risk"])
    negative = rng.random() < chance
    options = config["negative_events"] if negative else config["positive_events"]
    identity = rng.choice(options)
    event = deps._instantiate_event(deps.events_by_id[identity], game, rng)
    event["runtime"] = {"assembly_stage": session["stage"], "negative": negative}
    event["body"] += f"\n这是第 {session['stage'] + 1}/3 个行动间隔，所讲功法《{session['technique_name']}》Lv.{session['level']}。"
    session["pending"] = copy.deepcopy(event)
    game.pending_event = event


def _resolve_buddhist_assembly(deps: BuddhistAssemblyDependencies, effect, game, pending, rng):
    if not buddhist_active(game):
        raise ValueError("佛修 DLC 已关闭")
    session = game.buddhist_state.get("assembly")
    if not session or pending.get("runtime", {}).get("assembly_stage") != session["stage"] or not session.get("pending"):
        raise ValueError("法会事件已经失效")
    config = buddhist_config()
    action = effect["action"]
    detail = ""
    if action == "spar":
        difficulty = 1 + min(config["burden_difficulty_cap"], session["burden"] * config["burden_difficulty_scale"])
        target = {"target_name": "问法修士", "target_power": expected_combat_power(game.player.realm_index, game.player.layer) * difficulty,
                  "target_realm_index": game.player.realm_index, "target_layer": game.player.layer,
                  "combat_type": "cultivator", "path": "buddhist", "nonlethal": True}
        result, detail = deps._combat(game, target, False, rng)
        score = config["spar_win_score"] if result == "victory" else config["spar_loss_score"]
    elif action == "debate":
        chance = max(.1, min(.95, .45 + session["level"] * .05 - session["burden"] * config["debate_burden_scale"]))
        score = config["debate_win_score"] if rng.random() < chance else config["debate_loss_score"]
    elif action in {"teach", "listen", "withdraw"}:
        score = config["choice_scores"][action]
    else:
        raise ValueError("未知法会事件结果")
    session["score"] += score
    session["events"].append({"stage": session["stage"] + 1, "event": pending["id"], "score": score})
    session["stage"] += 1
    session["stage_years"] = 0
    session["pending"] = None
    if session["stage"] >= 3:
        detail += deps._finish_buddhist_assembly(game, rng=rng)
    return "resolved", f"本场论法评价 {score:+g}。" + detail


def _finish_buddhist_assembly(deps: BuddhistAssemblyDependencies, game, rng=None, forced_failure=False):
    state, config = game.buddhist_state, buddhist_config()
    session = state["assembly"]
    score = session["score"] - session["burden"] * config["burden_score_penalty"]
    unlicensed = [row for row in deps._buddhist_permissions(game) if not row["permitted"] and not row["intimidated"]]
    site = site_state(state, session["world"], session["location"])
    intervention = []
    retained_followers = 1.0
    if rng:
        for row in unlicensed:
            if rng.random() < config["intervention_chance"]:
                score -= config["intervention_score_penalty"]
                intervention.append(row["name"])
                if rng.random() < config["intervention_purge_chance"]:
                    retained_followers = 0.0
                elif rng.random() < config["intervention_dispersion_chance"]:
                    retained_followers *= config["intervention_retention"]
                if rng.random() < config["intervention_wanted_chance"]:
                    key = f"sect:{row['id']}"
                    game.player.hostility[key] = max(game.player.hostility.get(key, 0), float(WORLD_SYSTEMS["faction_conflict"]["wanted_threshold"]) + 10)
    result = "failure" if forced_failure else "great" if score >= config["great_threshold"] else "success" if score >= config["success_threshold"] else "normal" if score >= config["normal_threshold"] else "failure"
    reward = config["outcomes"][result]
    delta = round(session["attendance"] * reward["followers_ratio"])
    floor = config["temples"][site["temple"]]["floor"]
    before_followers = site["followers"]
    site["followers"] = max(floor, (site["followers"] + delta) * retained_followers)
    delta = round(site["followers"] - before_followers)
    set_dharma_karma(game, state["dharma_karma"] + reward["karma"])
    game.player.fame = max(0, game.player.fame + reward["fame"])
    text = f"法会{reward['name']}，评价 {score:.1f}，信众 {delta:+}，业力 {reward['karma']:+}。"
    if intervention:
        text += f"因未获许可，{'、'.join(intervention)}干预了此次弘法。"
        if retained_followers < 1:
            text += "地方势力驱散了听众；寺庙保底信众仍受保留。"
    deps._buddhist_record(game, text)
    state["assembly"] = None
    return text
