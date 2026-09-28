"""Vow power is saved once; passive bonuses are derived at the point of use."""
from __future__ import annotations

import math

from ..content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS, REALMS
from ..rules import public_player
from .path_modifiers import register_provider
from .semantic_events import subscribe
from .world_transition_system import cultivation_ceiling


def active(subject):
    return (getattr(subject, "player", subject).path == "buddhist"
            and CONTENT_DOCUMENTS.get("buddhist_way.json", {}).get("settings", {}).get("enabled", False))


def ensure_wish(game):
    # Transient reference, deliberately absent from Player's dataclass/save schema.
    game.player._modifier_context = game.buddhist_state
    state = game.buddhist_state.setdefault("wish", {})
    state.setdefault("value", 0)
    state["value"] = max(0, min(100, int(state["value"])))
    state.setdefault("quiet", {"kill": 0.0, "concubine": 0.0, "entwine": 0.0})
    state.setdefault("nirvana_units", 0.0)
    state.setdefault("log", [])
    return state


def change(game, delta, reason):
    state = ensure_wish(game)
    before = state["value"]
    state["value"] = max(0, min(100, before + delta))
    state["log"].append({"age": game.player.age, "reason": reason,
                         "delta": state["value"] - before, "value": state["value"]})
    del state["log"][:-30]


def on_event(game, event):
    if not active(game):
        return
    state = ensure_wish(game)
    data, name = event.data, event.name
    if name == "time.elapsed":
        units = max(0.0, float(data["years"])) / max(1, float(data["unit_years"]))
        labels = {"kill": "不杀生", "concubine": "不纳侍妾", "entwine": "清净自持"}
        for key, label in labels.items():
            old = state["quiet"][key]
            new = old + units
            gain = max(0, math.floor(new + 1e-9) - 5) - max(0, math.floor(old + 1e-9) - 5)
            state["quiet"][key] = new
            if gain:
                change(game, gain, label)
        state["nirvana_units"] = max(0.0, state["nirvana_units"] - units)
        if state["nirvana_units"] < 1e-9:
            state["nirvana_units"] = 0.0
    elif name in {"concubine.recruited", "companion.entwined"}:
        state["quiet"]["concubine" if name == "concubine.recruited" else "entwine"] = 0.0
    elif name == "cultivator.killed" and data.get("actor", "player") == "player":
        state["quiet"]["kill"] = 0.0
        if not data.get("penalty_handled"):
            if data.get("execution"):
                change(game, -5, "处死亲随或俘虏")
            elif data.get("in_combat") and not data.get("defending"):
                change(game, -2, "主动进攻并击杀修士")
    elif name == "relationship.attacked":
        roles = data.get("roles", [])
        if "master" in roles or "companion" in roles:
            change(game, -30, "截杀师傅或道侣")
        elif "sect_member" in roles:
            change(game, -10, "截杀同门")
        elif data.get("kind") == "party":
            change(game, -2, "背叛同行队友")
    elif name == "captive.released":
        change(game, 1, "释放俘虏")
    elif name == "captive.tortured":
        change(game, -1, "拷打俘虏")
    elif name == "disciple.recruited":
        change(game, 2, "招收弟子")
    elif name == "diplomacy.proposal_passed" and data.get("status") == "war":
        change(game, -5, "宣战提议获通过")


def wish_modifier(subject, key, **context):
    if not active(subject):
        return None
    source = getattr(subject, "buddhist_state", getattr(subject, "_modifier_context", {}))
    state = source.get("wish", {})
    value = max(0, min(100, float(state.get("value", 0))))
    if key == "breakthrough_base_bonus":
        return value * .0005
    if key == "opportunity_efficiency":
        return 1 + value * .002 + (1 if state.get("nirvana_units", 0) > 0 else 0)
    if key == "thunder_damage_reduction":
        return value * .001


def nirvana_target(engine, game):
    player = game.player
    if (player.realm_index < 1 or player.realm_index >= 9 or player.spirit_root == "none"
            or player.sealed_cultivation or player.cultivation_suppression):
        return None, "当前修为状态不能涅槃"
    layer = player.layer + 1
    if layer > REALMS[player.realm_index].layers:
        return None, "已达本境后期，涅槃不能跨越大境界"
    cap = cultivation_ceiling(WORLD_SYSTEMS, player.world)
    if cap and (player.realm_index, layer) > cap:
        return None, "已达当前界面修为上限"
    return layer, ""


def nirvana(engine, game, rng):
    state = ensure_wish(game)
    layer, reason = nirvana_target(engine, game)
    if reason:
        raise ValueError(reason)
    if game.pending_event or game.active_trial or game.buddhist_state.get("assembly"):
        raise ValueError("请先结束当前事件、渡劫或法会")
    if state["value"] < 100:
        raise ValueError("需要完整的 100 愿力")
    old_label = public_player(game.player)["realm_name"]
    change(game, -100, "涅槃")
    # The existing completion routine grants lifespan and progression exactly once.
    game.player.layer = layer - 1
    engine._complete_minor_breakthrough(game, rng, old_label)
    game.player.awaiting_major_breakthrough = False
    game.player.opportunity = 0
    state["nirvana_units"] = 3.0
    engine._buddhist_record(game, "涅槃突破一个小境界，免除此关天劫；三个时间单位内机缘获取效率额外 +100%。")


subscribe("buddhist.wish", on_event)
register_provider("buddhist.wish", wish_modifier)
