"""Explicit ghost identity operations; callers own composition."""
from __future__ import annotations

from ...npc_custody import kill_person

import copy
import random
from typing import Any

from ...content_registry import REALMS, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord
from ...runtime import now_iso
from ..ghost_resources import ghost_cultivation_active as ghost_cultivation_active
from ..ghost_resources import ghost_phase_two_config as ghost_phase_two_config
from ..possession_system import (
    advance_player_age,
    can_possess,
    current_body_age,
    enter_host_body,
    has_ghost_core,
    is_possessed,
    leave_host_body,
)
from .dependencies import GhostIdentityDependencies


def _post_battle_possession_candidates(game: GameState) -> list[dict[str, Any]]:
    """Return captives that can save a free ghost at a routine battle death."""
    player = game.player
    if not has_ghost_core(player) or player.ghost_captor or is_possessed(player):
        return []
    candidates: list[dict[str, Any]] = []
    for prisoner in player.prisoners:
        allowed, _ = can_possess(player, prisoner)
        if allowed:
            candidates.append(copy.deepcopy(prisoner))
    return candidates


def _prepare_post_battle_possession(deps: GhostIdentityDependencies, game: GameState, source_event: str) -> bool:
    # Terminal death has no pending resurrection branch.
    return False


def post_battle_possess(deps: GhostIdentityDependencies, game_id: str, target_id: str) -> dict[str, Any]:
    raise ValueError("战陨夺舍入口已停用；存活结算后仍在神游时，请使用俘虏夺舍")


def ghost_constraint_action(deps: GhostIdentityDependencies, game_id: str, action: str) -> dict[str, Any]:
    from ...rules import combat_power, max_hp, max_mp
    from ...runtime import decode_rng, encode_rng

    game = deps._load(game_id); player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event or game.active_trial:
        raise ValueError('请先处理当前事件或劫战，再处理拘魂禁制')
    if not player.ghost_captor:
        raise ValueError("当前并未受制于拘魂者")
    rng = decode_rng(game.seed, game.rng_state)
    captor = player.ghost_captor
    target_power = max(1.0, float(captor.get("combat_power", 1.0)))
    chance = max(0.05, min(0.9, combat_power(player) / (combat_power(player) + target_power)))
    if action == "wait":
        origin = (player.world, player.location_id)
        advance_player_age(player)
        deps._advance_world_year(game, rng, [], encounters=False)
        if player.alive:
            deps._advance_soul_erosion_time(game, 1)
        if (player.world, player.location_id) != origin:
            deps._ensure_market(game, rng)
        result, summary = "waited", "你在拘魂禁制中熬过一年，并随拘魂者一同行动。"
    elif action == "resist":
        if rng.random() < chance:
            captor_id = str(captor.get("npc_id") or captor.get("id", ""))
            captor_npc = deps._find_npc(game, captor_id)
            if captor_npc:
                captor_npc.affinity = float(
                    WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)
                )
            player.ghost_captor = None
            result, summary = "escaped", f"你击破拘魂禁制，重获自由（胜算 {chance:.0%}）；双方好感重置为中立。"
        else:
            deps._die(game, "反抗拘魂者失败，魂印崩碎，魂飞魄散", "SYS_GHOST_RESIST_FAILED", survival_stage="spirit_failed")
            result = "survived" if player.alive else "dead"
            outcome = "第二元婴承接本魂，仍处于神游" if player.alive else "魂体被禁制磨灭"
            summary = f"反抗失败，{outcome}（胜算 {chance:.0%}）。"
    elif action == "possess":
        allowed, reason = can_possess(player, captor)
        if not allowed:
            raise ValueError(reason)
        if rng.random() < chance:
            captor_npc = deps._find_npc(game, str(captor.get("npc_id") or captor.get("id", "")))
            from ..npc_techniques import resolve
            host_target = captor_npc.to_dict() if captor_npc else captor
            host = enter_host_body(player, host_target, technique=resolve(game, host_target.get('main_technique_id')))
            if captor_npc:
                captor_npc.alive = False
                captor_npc.death_reason = f"被{player.name}反夺肉身，原神魂不复存在"
            player.hp = min(player.hp, max_hp(player)); player.mp = min(player.mp, max_mp(player))
            result, summary = "possessed", f"你反夺魂印，成功占据{host['name']}的肉身（胜算 {chance:.0%}）。"
        else:
            deps._die(game, "夺舍拘魂者失败，神魂遭反噬而灭", "SYS_GHOST_POSSESSION_FAILED", survival_stage="spirit_failed")
            result = "survived" if player.alive else "dead"
            outcome = "第二元婴承接本魂，仍处于神游" if player.alive else "神魂遭反噬而灭"
            summary = f"夺舍失败，{outcome}（胜算 {chance:.0%}）。"
    else:
        raise ValueError("未知受制行动")
    game.history.append(HistoryRecord(
        "SYS_GHOST_CONSTRAINT", 1, player.age, "拘魂禁制", action, result, summary,
        {"captor_id": captor.get("npc_id"), "chance": chance}, ["action", "ghost", "controlled"],
    ))
    game.rng_state = encode_rng(rng); game.updated_at = now_iso(); deps.store.save(game)
    return deps.present(game)


def _capture_defeated_ghost(game: GameState, target: dict[str, Any], rng: random.Random) -> bool:
    player = game.player
    from ...soul_rules import wandering
    if not player.alive or player.realm_index < 4 or not wandering(player):
        return False
    if not ghost_cultivation_active(player) or player.ghost_captor or is_possessed(player):
        return False
    if target.get("combat_type") not in {None, "cultivator"} or str(target.get("race", "human")) not in {"human", "demon", "immortal"}:
        return False
    base = float(ghost_phase_two_config().get("defeat_capture_chance", 0.45))
    personality = str(target.get("personality", ""))
    base += 0.15 if personality in {"凶厉", "多疑", "贪婪", "残酷"} else -0.12 if personality in {"仁厚", "温和"} else 0
    base += 0.10 if str(target.get("path", "")) in {"ghost", "demonic"} else 0
    capture_chance = max(0.05, min(0.90, base))
    if rng.random() >= capture_chance:
        return False
    player.hp = 1.0
    player.mp = max(0.0, player.mp)
    player.ghost_attachment = None
    player.ghost_captor = {
        "id": str(target.get("npc_id") or target.get("id") or f"captor_{game.seed}_{player.age}"),
        "npc_id": target.get("npc_id"), "name": str(target.get("target_name", "拘魂修士")),
        "realm_index": int(target.get("target_realm_index", player.realm_index)),
        "layer": int(target.get("target_layer", 1)), "path": str(target.get("path", "dao")),
        "race": str(target.get("race", "human")), "spirit_root": str(target.get("spirit_root", "none")),
        "combat_power": float(target.get("target_power", 1.0)),
        "main_technique_id": target.get("main_technique_id"),
        "location_id": player.location_id, "source": "defeat_capture", "followed_years": 0,
        "controlled_form": rng.choice(("拘魂", "法器器灵", "魂幡附庸")),
        "capture_chance": capture_chance, "affinity": float(target.get("affinity", 0)),
    }
    if player.ghost_captor["controlled_form"] == "法器器灵":
        player.milestones["ghost_became_others_attachment"] = 1
    game.history.append(HistoryRecord(
        "SYS_GHOST_CAPTURED", 1, player.age, "败亡拘魂", None, "controlled",
        f"{player.ghost_captor['name']}没有立刻灭杀你，而是以魂印拘束本魂；失败的反抗与夺舍都会真正魂飞魄散。",
        {
            "captor_id": player.ghost_captor["id"],
            "controlled_form": player.ghost_captor["controlled_form"],
        }, ["system", "ghost", "controlled", "negative"],
    ))
    return True


def leave_possessed_body(deps: GhostIdentityDependencies, game_id: str) -> dict[str, Any]:
    from ...rules import max_hp, max_mp
    game = deps._load(game_id); player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    host = leave_host_body(player)
    from ..soul_lifecycle import leave_body
    leave_body(game, destroyed=True)
    player.hp = min(max(1.0, player.hp), max_hp(player)); player.mp = min(player.mp, max_mp(player))
    game.history.append(HistoryRecord(
        "SYS_POSSESSION_LEFT", 1, player.age, "离舍归魂", None, "left",
        f"你主动离开{host.get('name', '宿主')}；这具肉身永久毁去，已经消耗的夺舍次数不返还。",
        {"host_id": host.get("id"), "possession_count": player.possession_count},
        ["action", "ghost", "possession"],
    ))
    game.updated_at = now_iso(); deps.store.save(game)
    return deps.present(game)
