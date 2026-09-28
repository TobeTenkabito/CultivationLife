"""World-local Dharma networks. No stored resource conversion or combat caches."""
from __future__ import annotations

from .buddhist_wish import ensure_wish, nirvana, nirvana_target

import copy
import math

from ..content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
from ..models import HistoryRecord
from ..runtime import decode_rng, encode_rng, now_iso
from ..rules import add_item, remove_item, expected_combat_power
from .faction_geography import local_authorities, authority_permission_exempt
from .path_modifiers import register_provider
from .possession_system import advance_player_age


def buddhist_config():
    return CONTENT_DOCUMENTS.get("buddhist_way.json", {}).get("settings", {})


def buddhist_active(subject):
    player = getattr(subject, "player", subject)
    return player.path == "buddhist" and bool(buddhist_config().get("enabled"))


def site_state(state, world, location):
    return state.setdefault("worlds", {}).setdefault(world, {"sites": {}, "blessings": []})["sites"].setdefault(
        location, {"followers": 0.0, "temple": 0, "permissions": {}})


def followers(state, world):
    return sum(max(0, row.get("followers", 0)) for row in state.get("worlds", {}).get(world, {}).get("sites", {}).values())


def selected_blessings(game):
    if not buddhist_active(game) or game.buddhist_state.get("dharma_karma", 0) <= 0:
        return []
    return game.buddhist_state.get("worlds", {}).get(game.player.world, {}).get("blessings", [])


def upkeep(game, blessing):
    config = buddhist_config()
    base = float(config["blessings"][blessing]["upkeep"])
    reduction = 1 / (1 + math.log1p(followers(game.buddhist_state, game.player.world)) / config["upkeep_follower_scale"])
    return base * max(config["upkeep_floor"], reduction)


def set_dharma_karma(game, value):
    state = game.buddhist_state
    old = float(state.get("dharma_karma", 0))
    new = max(-100.0, min(100.0, float(value)))
    state["dharma_karma"] = round(new, 6)
    if old >= -25 and new < -25:
        state["grace_units"] = float(buddhist_config()["grace_units"])
    elif new >= -25:
        state["grace_units"] = None
    if new <= 0:
        for world in state.get("worlds", {}).values():
            world["blessings"] = []


def buddhist_modifier(subject, key, **context):
    if not buddhist_active(subject):
        return None
    player = getattr(subject, "player", subject)
    config = buddhist_config()
    if key in {"karma", "sha_qi"}:
        return getattr(player, key) if context.get("context") == "dharma_assembly" else 0.0
    if key == "fame":
        return player.fame + player.karma * config["karma_fame_ratio"] + player.sha_qi * config["sha_fame_ratio"]
    if key == "ascension_destination":
        if player.world == "human":
            rule = config["ascension_selector"]
            return "spirit" if player.qi_experience.get(rule["upper_qi"], 0) >= player.qi_experience.get(rule["lower_qi"], 0) * rule["lower_weight"] else "hell"
        if player.world == "hell":
            return "reincarnation"
    if key == "ascension_events" and player.world == "hell":
        return list(config["reincarnation_trial_events"])
    if key == "ascension_route":
        lower = player.world in {"hell", "reincarnation"} or (player.world == "human" and buddhist_modifier(player, "ascension_destination") == "hell")
        worlds = ["human", "hell", "reincarnation"] if lower else ["human", "spirit", "celestial"]
        return ("buddhist_lower" if lower else "buddhist_upper", {"name": "诸法无我", "stages": [{"world": world} for world in worlds] + [{"system": "heavens"}]})
    if key == "ascension_source":
        return player.world in {"spirit", "hell"}
    if not hasattr(subject, "buddhist_state"):
        return None
    state = subject.buddhist_state
    karma = float(state.get("dharma_karma", 0))
    if key == "combat_stats":
        return 1 + max(0, -karma) / 100 * config["negative_combat_cap"]
    if key == "pursuit_immunity":
        return context.get("source") == "fame" and (karma >= -25 or float(state.get("grace_units") or 0) > 0)
    chosen = selected_blessings(subject)
    if key == "cost":
        blessing = {"market": "market", "black_market": "market", "natal": "natal"}.get(context.get("activity"))
        if blessing in chosen:
            return config["blessings"][blessing]["multiplier"]
    if key == "commission_duration" and "commission" in chosen:
        return config["blessings"]["commission"]["multiplier"]
    return None


register_provider("buddhist", buddhist_modifier)


class BuddhistSystemMixin:
    def _ensure_buddhist_state(self, game):
        if not buddhist_active(game):
            return
        state = game.buddhist_state
        ensure_wish(game)
        state.setdefault("version", 1)
        state.setdefault("dharma_karma", 0.0)
        state.setdefault("grace_units", None)
        state.setdefault("assembly", None)
        state.setdefault("history", [])
        site_state(state, game.player.world, game.player.location_id)

    def _advance_buddhist_year(self, game):
        if not buddhist_active(game):
            return []
        self._ensure_buddhist_state(game)
        state, config, player = game.buddhist_state, buddhist_config(), game.player
        grace_before = state.get("grace_units")
        for world in state["worlds"].values():
            for site in world["sites"].values():
                temple = config["temples"][int(site["temple"])]
                site["followers"] = max(temple["floor"], site["followers"] * (1 - temple["decay"]))
        total = followers(state, player.world)
        income = min(config["annual_karma_cap"], math.log1p(total / config["follower_income_scale"]) * config["follower_income_coefficient"])
        income += sum(config["temple_karma"] for site in state["worlds"][player.world]["sites"].values() if site["temple"] == 3)
        set_dharma_karma(game, state["dharma_karma"] + income)
        chosen = list(selected_blessings(game))
        expense = sum(upkeep(game, blessing) for blessing in chosen)
        set_dharma_karma(game, state["dharma_karma"] - expense)
        active = selected_blessings(game)
        if "stipend" in active and total > 0:
            table = config["blessings"]["stipend"]["realm_stones"]
            add_item(player, "spirit_stone", table[min(player.realm_index, len(table) - 1)])
        for blessing, attribute in [("karma_decay", "karma"), ("sha_decay", "sha_qi")]:
            if blessing in active:
                spec = config["blessings"][blessing]
                old = getattr(player, attribute)
                setattr(player, attribute, max(0, old - max(spec["minimum"], old * spec["rate"])))
        # Starting a new grace period this year does not spend its first fraction immediately.
        if state["dharma_karma"] < -25 and grace_before is not None:
            unit = max(1, int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]))
            state["grace_units"] = max(0, float(state["grace_units"] or 0) - 1 / unit)
            if state["grace_units"] < 1e-9:
                state["grace_units"] = 0
        state["last_settlement"] = {"age": player.age, "income": round(income, 3), "upkeep": round(expense, 3)}
        return []

    def _buddhist_permissions(self, game):
        player, config = game.player, buddhist_config()
        site = site_state(game.buddhist_state, player.world, player.location_id)
        return [{"id": row.id, "name": row.name,
                 "exempt": authority_permission_exempt(game, row),
                 "intimidated": player.realm_index >= {1: 4, 2: 7, 3: 10}.get(int(WORLD_SYSTEMS["world_profiles"][player.world]["tier"]), 10),
                 "expires": site["permissions"].get(row.id, 0),
                 "permitted": authority_permission_exempt(game, row) or site["permissions"].get(row.id, 0) > player.age,
                 "fee": config["permission_fee"] * max(1, player.realm_index) ** 2}
                for row in local_authorities(game, player.world, player.location_id)]

    def _buddhist_burden(self, game):
        config = buddhist_config()
        return max(0, game.player.karma) * config["burden_karma_weight"] + max(0, game.player.sha_qi) * config["burden_sha_weight"]

    def _public_buddhist(self, game):
        if not buddhist_active(game):
            return {"available": False}
        self._ensure_buddhist_state(game)
        state, player, config = game.buddhist_state, game.player, buddhist_config()
        site = site_state(state, player.world, player.location_id)
        burden = self._buddhist_burden(game)
        chosen = selected_blessings(game)
        from ..rules import effective_fame
        audience = round(config["attendance_base"] + player.realm_index * config["attendance_realm"] + math.sqrt(max(0, effective_fame(player))) * config["attendance_fame"] + math.sqrt(site["followers"]) * config["attendance_followers"] + site["temple"] * config["attendance_temple"])
        sites = []
        for world, network in state["worlds"].items():
            for location, row in network["sites"].items():
                if not row["followers"] and not row["temple"] and world != player.world:
                    continue
                sites.append({"world": world, "world_name": WORLD_SYSTEMS["world_names"][world],
                              "location": location, "name": self.maps.location(world, location)["name"],
                              "active": world == player.world, **copy.deepcopy(row),
                              **config["temples"][row["temple"]]})
        level = site["temple"]
        tier = int(WORLD_SYSTEMS["world_profiles"][player.world]["tier"])
        return {"available": True, "karma": state["dharma_karma"], "grace_units": state["grace_units"],
                "wish": {**copy.deepcopy(state["wish"]), "blocked": nirvana_target(self, game)[1]},
                "raw_karma": player.karma, "raw_sha": player.sha_qi, "effective_fame": effective_fame(player),
                "followers": round(followers(state, player.world)), "sites": sites,
                "site": copy.deepcopy(site), "temple_cost": config["temples"][level + 1]["cost"] * config["temple_tier_scale"] ** (tier - 1) if level < 3 else None,
                "blessings": [{"id": key, **spec, "selected": key in chosen, "annual_cost": round(upkeep(game, key), 3)} for key, spec in config["blessings"].items()],
                "upkeep": round(sum(upkeep(game, key) for key in chosen), 3), "permissions": self._buddhist_permissions(game),
                "techniques": [{"id": row.id, "name": row.name, "level": row.level} for row in player.known_techniques],
                "attendance": audience, "risk": "低" if burden < 50 else "中" if burden < 150 else "高" if burden < 400 else "极高",
                "assembly": copy.deepcopy(state["assembly"]), "can_assemble": state["dharma_karma"] >= -25 and not state["assembly"],
                "history": copy.deepcopy(state["history"][-8:]),
                "route": "人界 → 灵界 → 仙界" if buddhist_modifier(player, "ascension_destination") != "hell" and player.world not in {"hell", "reincarnation"} else "人界 → 地狱界 → 轮回界"}

    def assert_buddhist_operation_allowed(self, game_id, operation):
        game = self.store.load(game_id)
        session = game.buddhist_state.get("assembly")
        # A disabled DLC may have allowed travel; returning must remain possible after re-enabling.
        at_assembly = session and (session["world"], session["location"]) == (game.player.world, game.player.location_id)
        if buddhist_active(game) and at_assembly and operation not in {
            "buddhist-action", "choice", "use-item", "settings", "setting", "world-news-debug", "merchant-preview"}:
            raise ValueError("法会尚未结束，请先继续法会或散会")

    def buddhist_action(self, game_id, action, **payload):
        game = self._load(game_id)
        if not buddhist_active(game) or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前无法主持佛修事务")
        self._ensure_buddhist_state(game)
        state, player, config = game.buddhist_state, game.player, buddhist_config()
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        rng = decode_rng(game.seed, game.rng_state)
        site = site_state(state, player.world, player.location_id)
        if action == "nirvana":
            nirvana(self, game, rng)
        elif action == "blessing":
            chosen = state["worlds"][player.world]["blessings"]
            identity = str(payload.get("blessing", ""))
            if identity not in config["blessings"]:
                raise ValueError("未知加持")
            if identity in chosen:
                chosen.remove(identity)
            elif state["dharma_karma"] > 0 and len(chosen) < 3:
                chosen.append(identity)
            else:
                raise ValueError("正业力时最多启用三项加持")
        elif action == "temple":
            view = self._public_buddhist(game)
            cost = view["temple_cost"]
            if cost is None:
                raise ValueError("寺庙已达三级")
            if not remove_item(player, "spirit_stone", cost):
                raise ValueError(f"需要 {cost} 灵石")
            site["temple"] += 1
            site["followers"] = max(site["followers"], config["temples"][site["temple"]]["floor"])
            self._buddhist_record(game, f"在{self.maps.location(player.world, player.location_id)['name']}修建了{site['temple']}级寺庙。")
        elif action == "permission":
            row = next((row for row in self._buddhist_permissions(game) if row["id"] == payload.get("authority")), None)
            if not row or row["permitted"]:
                raise ValueError("此势力无需再缴纳弘法许可费")
            if not remove_item(player, "spirit_stone", row["fee"]):
                raise ValueError(f"需要 {row['fee']} 灵石")
            unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
            site["permissions"][row["id"]] = player.age + max(config["permission_years"], unit * 4)
        elif action == "start":
            if state["assembly"] or state["dharma_karma"] < -25 or game.active_trial:
                raise ValueError("当前不能开坛：业力须不低于 -25，且没有进行中的法会或劫关")
            art = next((row for row in player.known_techniques if row.id == payload.get("technique")), None)
            if not art:
                raise ValueError("请选择已学功法")
            view = self._public_buddhist(game)
            state["assembly"] = {"world": player.world, "location": player.location_id,
                "technique": art.id, "technique_name": art.name, "level": art.level,
                "started_age": player.age, "stage": 0, "stage_years": 0,
                "unit_years": int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]),
                "attendance": view["attendance"], "burden": self._buddhist_burden(game),
                "score": art.level * config["technique_level_score"] + art.grade * config.get("technique_grade_score", .5), "events": [], "pending": None}
            self._continue_buddhist_assembly(game, rng)
        elif action == "continue":
            self._continue_buddhist_assembly(game, rng)
        elif action == "cancel":
            if not state["assembly"]:
                raise ValueError("没有进行中的法会")
            self._finish_buddhist_assembly(game, forced_failure=True)
        else:
            raise ValueError("未知佛修操作")
        self._ensure_market(game, rng)
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _buddhist_record(self, game, text):
        game.buddhist_state["history"].append({"age": game.player.age, "text": text})
        game.buddhist_state["history"] = game.buddhist_state["history"][-50:]
        game.history.append(HistoryRecord("SYS_BUDDHIST", 1, game.player.age, "诸法无我", None, "resolved", text, {}, ["buddhist", f"world:{game.player.world}"]))

    def _continue_buddhist_assembly(self, game, rng):
        session = game.buddhist_state["assembly"]
        if not session or (session["world"], session["location"]) != (game.player.world, game.player.location_id):
            raise ValueError("请回到开坛地点继续法会")
        if session.get("pending"):
            # DLC disable/enable can remove a pending event; restore the exact saved instance.
            game.pending_event = copy.deepcopy(session["pending"])
            return
        if game.buddhist_state["dharma_karma"] < -25:
            self._finish_buddhist_assembly(game, forced_failure=True)
            return
        news = []
        while session["stage_years"] < session["unit_years"]:
            advance_player_age(game.player)
            session["stage_years"] += 1
            proceed = self._advance_world_year(game, rng, news, encounters=False)
            if game.player.alive:
                self._advance_soul_erosion_time(game, 1)
            if not proceed or game.pending_event or not game.player.alive:
                return
        config = buddhist_config()
        unlicensed = [row for row in self._buddhist_permissions(game) if not row["permitted"] and not row["intimidated"]]
        chance = min(config["negative_chance_cap"], config["negative_chance_base"] + session["burden"] * config["negative_chance_scale"] + len(unlicensed) * config["unlicensed_risk"])
        negative = rng.random() < chance
        options = config["negative_events"] if negative else config["positive_events"]
        identity = rng.choice(options)
        event = self._instantiate_event(self.events_by_id[identity], game, rng)
        event["runtime"] = {"assembly_stage": session["stage"], "negative": negative}
        event["body"] += f"\n这是第 {session['stage'] + 1}/3 个行动间隔，所讲功法《{session['technique_name']}》Lv.{session['level']}。"
        session["pending"] = copy.deepcopy(event)
        game.pending_event = event

    def _resolve_buddhist_assembly(self, effect, game, pending, rng):
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
            result, detail = self._combat(game, target, False, rng)
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
            detail += self._finish_buddhist_assembly(game, rng=rng)
        return "resolved", f"本场论法评价 {score:+g}。" + detail

    def _finish_buddhist_assembly(self, game, rng=None, forced_failure=False):
        state, config = game.buddhist_state, buddhist_config()
        session = state["assembly"]
        score = session["score"] - session["burden"] * config["burden_score_penalty"]
        unlicensed = [row for row in self._buddhist_permissions(game) if not row["permitted"] and not row["intimidated"]]
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
        self._buddhist_record(game, text)
        state["assembly"] = None
        return text
