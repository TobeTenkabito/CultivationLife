"""Shared state rules without action or engine dependencies."""
from __future__ import annotations

import math

from ...content_registry import CONTENT_DOCUMENTS


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
