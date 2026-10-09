"""Explicit relationships dependents operations; callers own composition."""
from __future__ import annotations

import copy
import random
from typing import Any

from ...content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord, SectNpc
from ...rules import (
    add_item,
    combat_power,
    learn_technique,
    max_hp,
    opportunity_required,
)
from ...runtime import decode_rng, encode_rng, now_iso
from .dependencies import DependentLifecycleDependencies


def _maybe_transfer_player_dependency(
    deps: DependentLifecycleDependencies, game: GameState, loser: SectNpc, winner: SectNpc, rng: random.Random,
    *, context: str,
) -> str:
    if not winner.alive or winner.id == loser.id:
        return ""
    player = game.player
    relationship = ""
    if player.concubine_status and str(player.concubine_status.get("owner_id", "")) == loser.id:
        relationship = "侍妾"
    elif player.ghost_captor and str(player.ghost_captor.get("npc_id") or player.ghost_captor.get("id", "")) == loser.id:
        relationship = str(player.ghost_captor.get("controlled_form", "魂仆"))
    if not relationship:
        return ""
    ratio = deps._npc_power(winner) / max(1.0, deps._npc_power(loser))
    chance = max(0.12, min(0.62, 0.24 + max(0.0, ratio - 1.0) * 0.12))
    if rng.random() >= chance:
        return ""
    if player.concubine_status and str(player.concubine_status.get("owner_id", "")) == loser.id:
        deps._set_concubine_status(game, {
            "owner_id": winner.id, "owner_name": winner.name,
            "owner_realm_index": winner.realm_index, "owner_layer": winner.layer,
            "owner_realm_name": deps._npc_realm_name(winner), "owner_world": winner.world,
        }, forced=True)
    else:
        old_form = str(player.ghost_captor.get("controlled_form", "魂仆"))
        player.ghost_captor = {
            "id": winner.id, "npc_id": winner.id, "name": winner.name,
            "realm_index": winner.realm_index, "layer": winner.layer,
            "path": winner.path, "race": winner.race, "spirit_root": winner.spirit_root,
            "combat_power": deps._npc_power(winner),
            "main_technique_id": deps._default_npc_main_technique(winner),
            "location_id": player.location_id, "source": f"transfer:{context}",
            "followed_years": 0, "controlled_form": old_form,
            "capture_chance": 1.0, "affinity": 0.0,
        }
    summary = (
        f"{loser.name}败给{winner.name}后，将身为{relationship}的你作为战后筹码转交给对方；"
        f"你的正主已经变为{winner.name}。"
    )
    game.history.append(HistoryRecord(
        "SYS_DEPENDENT_TRANSFERRED", 1, player.age, "败后易主", winner.id,
        "transferred", summary,
        {"old_owner_id": loser.id, "new_owner_id": winner.id, "chance": chance, "context": context},
        ["system", "relationship", "owner", "transfer", "negative"],
    ))
    return summary


def _maybe_concubine_proposal(deps: DependentLifecycleDependencies, game: GameState, rng: random.Random) -> bool:
    if game.settings.get("silent_events", False):
        return False
    player = game.player
    if (
        player.gender != "female" or player.concubine_status
        or player.concubine_rejection_aftermath
        or player.realm_index >= deps._world_realm_cap(player.world) - 1
    ):
        return False
    candidates = [
        npc for npc in deps._all_world_npcs(game)
        if npc.alive and npc.world == player.world and npc.gender == "male"
        and deps._rank(npc) > deps._rank(player)
    ]
    if not candidates:
        return False
    candidates.sort(key=lambda npc: (npc.realm_index, npc.layer), reverse=True)
    owner = rng.choice(candidates[: min(8, len(candidates))])
    gap = max(1, owner.realm_index - player.realm_index)
    reputation_multiplier = max(0.01, 0.20 ** player.concubine_escape_reputation)
    chance = min(0.32, 0.05 + gap * 0.035) * reputation_multiplier
    if rng.random() >= chance:
        return False
    event = deps._instantiate_event(deps.events_by_id["SYS_CONCUBINE_PROPOSAL"], game, rng)
    event["body"] = event["body"].replace("{owner_name}", owner.name).replace(
        "{owner_realm}", deps._npc_realm_name(owner),
    )
    event["runtime"] = {
        "owner_id": owner.id, "owner_name": owner.name,
        "owner_realm_index": owner.realm_index, "owner_layer": owner.layer,
        "owner_realm_name": deps._npc_realm_name(owner), "owner_world": owner.world,
    }
    game.pending_event = event
    return True


def _resolve_concubine_proposal(
    deps: DependentLifecycleDependencies, game: GameState, pending: dict[str, Any], accept: bool,
) -> tuple[str, str]:
    runtime = pending.get("runtime", {})
    owner = deps._find_npc(game, str(runtime.get("owner_id", "")))
    name = str(runtime.get("owner_name", "一位高阶修士"))
    if not owner or not owner.alive or owner.world != game.player.world:
        return "owner_absent", "提议者已经离开当前界面，这桩拉拢自然作罢。"
    if not accept:
        owner.affinity = float(owner.affinity or 0) - 8
        player = game.player
        player.concubine_rejection_aftermath = [
            row for row in player.concubine_rejection_aftermath
            if str(row.get("owner_id", "")) != owner.id
        ]
        player.concubine_rejection_aftermath.append({
            **copy.deepcopy(runtime),
            "declined_unit": game.diplomacy_unit,
            "expires_unit": game.diplomacy_unit + 2,
            "last_checked_unit": game.diplomacy_unit,
        })
        return "refused", (
            f"你拒绝成为{name}的侍妾；对方心意难测。若其意图报复，只会在接下来的两个行动单位内发作。"
        )
    deps._set_concubine_status(game, runtime)
    return "accepted", (
        f"你接受{name}的拉拢，成为其侍妾。此后每回合会被抽取机缘，机缘获取效率降至 80%；"
        "修为仍低于对方时，基础突破概率 +2%。"
    )


def _advance_concubine_aftermath(deps: DependentLifecycleDependencies, game: GameState, rng: random.Random) -> bool:
    """Roll a rejected suitor once per unit, and only for the next two units."""
    if game.settings.get("silent_events", False):
        return False
    if game.pending_event or not game.player.concubine_rejection_aftermath:
        return False
    current_unit = game.diplomacy_unit
    kept: list[dict[str, Any]] = []
    triggered: tuple[dict[str, Any], SectNpc] | None = None
    for record in game.player.concubine_rejection_aftermath:
        declined = int(record.get("declined_unit", current_unit))
        expires = int(record.get("expires_unit", declined + 2))
        if current_unit <= int(record.get("last_checked_unit", declined)):
            kept.append(record)
            continue
        owner = deps._find_npc(game, str(record.get("owner_id", "")))
        if not owner or not owner.alive or owner.world != game.player.world or current_unit > expires:
            continue
        record["last_checked_unit"] = current_unit
        if (
            triggered is None
            and deps._revenge_ready(game, "rejected_suitor", owner.id)
            and rng.random() < deps._proposal_revenge_chance(game, owner)
        ):
            triggered = record, owner
            continue
        if current_unit < expires:
            kept.append(record)
    game.player.concubine_rejection_aftermath = kept
    if not triggered:
        return False
    record, owner = triggered
    event = deps._instantiate_event(deps.events_by_id["SYS_CONCUBINE_REVENGE"], game, rng)
    event["body"] = event["body"].replace("{owner_name}", owner.name)
    event["runtime"] = copy.deepcopy(record)
    event["runtime"]["revenge_cooldown_units"] = deps._record_revenge_trigger(
        game, "rejected_suitor", owner.id,
    )
    game.pending_event = event
    return True


def _runtime_from_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(status[key])
        for key in (
            "owner_id", "owner_name", "owner_realm_index", "owner_layer",
            "owner_realm_name", "owner_world",
        )
        if key in status
    }


def _set_concubine_status(
    deps: DependentLifecycleDependencies, game: GameState, runtime: dict[str, Any], *, forced: bool = False,
) -> None:
    game.player.concubine_status = {
        **deps._runtime_from_status(runtime),
        "started_age": game.player.age, "turns": 0, "last_drain": 0.0,
        "dependent": False, "forced": forced, "failed_escape_count": 0,
        "last_requests": {}, "angered_until_unit": -1,
    }


def _resolve_concubine_revenge(
    deps: DependentLifecycleDependencies, game: GameState, pending: dict[str, Any], method: str, rng: random.Random,
) -> tuple[str, str]:
    runtime = pending.get("runtime", {})
    owner = deps._find_npc(game, str(runtime.get("owner_id", "")))
    name = str(runtime.get("owner_name", "一位高阶修士"))
    if not owner or not owner.alive or owner.world != game.player.world:
        return "owner_absent", "追来之人已经离开当前界面，这场逼迫不了了之。"
    relief = float(WORLD_SYSTEMS["relationship"].get("sanction_affinity_relief", 8))
    if method == "submit":
        owner.affinity = min(100.0, float(owner.affinity or 0) + relief)
        deps._set_concubine_status(game, runtime, forced=True)
        return "submitted", f"你暂时向{name}低头，被强行带回府中；对方怒意缓和 {relief:g} 点，仍可在“缘·侍妾”中谋求脱身。"
    if method != "resist":
        raise ValueError("未知的逼迫应对方式")
    player_power = max(1.0, combat_power(game.player))
    owner_power = max(1.0, deps._npc_power(owner))
    chance = max(0.08, min(0.75, 0.16 + 0.42 * player_power / (player_power + owner_power)))
    if rng.random() < chance:
        owner.affinity = min(100.0, float(owner.affinity or 0) + relief)
        game.player.concubine_escape_reputation += 1
        return "escaped_revenge", (
            f"你拼死突破{name}的围堵，保住自由（成功率 {chance:.0%}）。冲突过后双方好感缓和 {relief:g} 点；"
            "此事传开，往后高阶修士强取你的概率大幅降低。"
        )
    owner.affinity = min(100.0, float(owner.affinity or 0) + relief)
    game.player.hp = max(1.0, game.player.hp - max_hp(game.player) * 0.22)
    deps._set_concubine_status(game, runtime, forced=True)
    game.player.concubine_status["angered_until_unit"] = game.diplomacy_unit + 2
    return "captured", f"反抗失败，你负伤后被{name}强行带走；冲突令双方好感缓和 {relief:g} 点，但两个行动单位内机缘抽取仍会更重。"


def _resolve_concubine_escape(
    deps: DependentLifecycleDependencies, game: GameState, pending: dict[str, Any], method: str, rng: random.Random,
) -> tuple[str, str]:
    status = game.player.concubine_status
    if not status:
        return "already_free", "你已经不再受侍妾名分约束。"
    if method == "abandon":
        return "abandoned", "你按下念头，继续等待更合适的脱身时机。"
    owner = deps._find_npc(game, str(status.get("owner_id", "")))
    if not owner or not owner.alive or owner.world != game.player.world:
        game.player.concubine_status = None
        return "owner_absent", "正主已无法再约束你，你顺势恢复自由。"
    if method not in {"covert", "plead"}:
        raise ValueError("未知的脱身方式")
    chance = deps._escape_chance(game, owner, status, method)
    if rng.random() < chance:
        owner.affinity = float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0))
        game.player.concubine_status = None
        game.player.concubine_escape_reputation += 1
        return "escaped", (
            f"你成功{'说服' if method == 'plead' else '逃离'}{owner.name}，重获自由（成功率 {chance:.0%}）。"
            "双方好感重置为中立；消息传开，高阶修士顾忌名声，今后强取你的概率大幅降低。"
        )
    owner.affinity = float(owner.affinity or 0) - 18
    status["failed_escape_count"] = int(status.get("failed_escape_count", 0)) + 1
    status["angered_until_unit"] = game.diplomacy_unit + 2
    return "escape_failed", (
        f"脱身失败（成功率 {chance:.0%}），{owner.name}被彻底激怒；两个行动单位内每期机缘抽取由 2% 提高至 3%。"
    )


def manage_concubine_status(deps: DependentLifecycleDependencies, game_id: str, action: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    status = player.concubine_status
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法处理侍妾处境")
    if not status:
        raise ValueError("你当前并非他人的侍妾")
    owner = deps._find_npc(game, str(status.get("owner_id", "")))
    if not owner or not owner.alive or owner.world != player.world:
        player.concubine_status = None
        game.updated_at = now_iso()
        deps.store.save(game)
        return deps.present(game)
    rng = decode_rng(game.seed, game.rng_state)
    result: str
    summary: str
    details: dict[str, Any] = {"action": action, "owner_id": owner.id}
    if action == "escape":
        event = deps._instantiate_event(deps.events_by_id["SYS_CONCUBINE_ESCAPE"], game, rng)
        event["body"] = event["body"].replace("{owner_name}", owner.name)
        event["runtime"] = deps._runtime_from_status(status)
        game.pending_event = event
        result, summary = "escape_planned", "你开始寻找脱身机会；具体方式将在游戏内事件中选择。"
    elif action == "depend":
        if status.get("dependent"):
            raise ValueError("你已经选择依附正主")
        status["dependent"] = True
        owner.affinity = float(owner.affinity or 0) + 10
        result, summary = "dependent", f"你主动依附{owner.name}，对方好感提高；今后索取资源与请求放手更容易获准。"
    elif action in {"request_technique", "request_stones", "request_equipment"}:
        kind = action.removeprefix("request_")
        last_requests = status.setdefault("last_requests", {})
        if int(last_requests.get(kind, -1)) == game.diplomacy_unit:
            raise ValueError("本行动单位已经索要过这类资源")
        technique_candidates = deps._owner_technique_candidates(player, owner) if kind == "technique" else []
        equipment_candidates = deps._owner_equipment_candidates(owner) if kind == "equipment" else []
        if kind == "technique" and not technique_candidates:
            raise ValueError("正主手中已无适合你的新功法")
        if kind == "equipment" and not equipment_candidates:
            raise ValueError("正主手中没有适合赐下的装备")
        last_requests[kind] = game.diplomacy_unit
        chance = deps._owner_request_chance(game, owner, status, kind)
        details["accept_chance"] = chance
        if rng.random() >= chance:
            owner.affinity = float(owner.affinity or 0) - 3
            result, summary = "request_refused", f"{owner.name}拒绝了你的索求（同意率 {chance:.0%}），并对你的贪求略感不悦。"
        elif kind == "technique":
            content_id = rng.choice(technique_candidates)
            learn_technique(player, TECHNIQUE_CATALOG[content_id])
            details["content_id"] = content_id
            result, summary = "technique_given", f"{owner.name}传下《{TECHNIQUE_CATALOG[content_id].name}》，功法已收入已悟列表。"
        elif kind == "equipment":
            content_id = rng.choice(equipment_candidates)
            add_item(player, content_id)
            details["content_id"] = content_id
            result, summary = "equipment_given", f"{owner.name}赐下{ITEM_CATALOG[content_id].name}，装备已放入包裹。"
        else:
            amount = max(3, int(4 * (max(1, owner.realm_index) ** 2) * rng.uniform(0.8, 1.25)))
            from ..economy.rewards import grant
            amount = grant(game,amount,'依附关系馈赠（背景实付）')
            details["quantity"] = amount
            result, summary = "stones_given", f"{owner.name}赐下下品灵石 ×{amount}。"
    else:
        raise ValueError("未知侍妾处境操作")
    game.history.append(HistoryRecord(
        "SYS_CONCUBINE_STATUS", 1, player.age, "侍妾处境", action, result, summary,
        details, ["system", "relationship", "concubine"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _advance_concubine_status(deps: DependentLifecycleDependencies, game: GameState, units: int = 1) -> float:
    status = game.player.concubine_status
    if not status or units <= 0:
        return 0.0
    owner = deps._find_npc(game, str(status.get("owner_id", "")))
    if owner and (not owner.alive or owner.world != game.player.world):
        game.player.concubine_status = None
        return 0.0
    if not owner and str(status.get("owner_world", game.player.world)) != game.player.world:
        game.player.concubine_status = None
        return 0.0
    angered = int(status.get("angered_until_unit", -1)) >= game.diplomacy_unit
    drain = min(
        game.player.opportunity,
        opportunity_required(game.player) * (0.03 if angered else 0.02) * units,
    )
    game.player.opportunity = max(0.0, game.player.opportunity - drain)
    status["last_drain"] = round(drain, 1)
    status["turns"] = int(status.get("turns", 0)) + units
    return drain

