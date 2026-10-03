"""Explicit relationships sanctions operations; callers own composition."""
from __future__ import annotations

import copy
import random
from typing import Any

from ...content_registry import WORLD_SYSTEMS
from ...models import GameState
from ...rules import max_hp, opportunity_required, remove_item
from .dependencies import RelationshipSanctionDependencies


def _maybe_relationship_sanction(deps: RelationshipSanctionDependencies, game: GameState, rng: random.Random) -> bool:
    if game.settings.get("silent_events", False):
        return False
    if game.pending_event:
        return False
    candidates = deps._relationship_sanction_candidates(game)
    if not candidates:
        return False
    threshold = float(WORLD_SYSTEMS["relationship"]["hostile_affinity_threshold"])
    severity = max(0.0, max(threshold - float(row["affinity"]) for row in candidates))
    chance = min(0.68, 0.18 + severity * 0.006)
    if rng.random() >= chance:
        return False
    selected = rng.choices(
        candidates, weights=[max(1.0, abs(float(row["affinity"]))) for row in candidates], k=1,
    )[0]
    event_id = {
        "master": "EVT_MASTER_SANCTION_001",
        "companion": "EVT_COMPANION_SANCTION_001",
        "concubine_owner": "EVT_OWNER_SANCTION_001",
        "ghost_captor": "EVT_OWNER_SANCTION_001",
    }[str(selected["role"])]
    event = deps._instantiate_event(deps.events_by_id[event_id], game, rng)
    event["body"] = event["body"].replace("{npc_name}", str(selected["name"]))
    demand = max(5, (int(selected["realm_index"]) + 1) ** 2 * 4)
    event["runtime"] = {**copy.deepcopy(selected), "demand": demand}
    if selected["role"] in {"concubine_owner", "ghost_captor"}:
        event["body"] += f" 对方开出的价码是下品灵石 ×{demand}；不足部分会以机缘抵偿。"
    interval = deps._record_revenge_trigger(
        game, "relationship_sanction", str(selected["id"]),
    )
    event["runtime"]["revenge_cooldown_units"] = interval
    game.pending_event = event
    return True


def _end_sanctioned_relationship(
    deps: RelationshipSanctionDependencies, game: GameState, role: str, name: str,
) -> tuple[str, str]:
    player = game.player
    if role == "master":
        relation = player.master
        if relation:
            player.party = [row for row in player.party if str(row.get("id")) != str(relation.get("id"))]
            deps._set_person_affinity(
                game, str(relation.get("id", "")),
                float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)),
            )
        player.master = None
        return "expelled", f"{name}将你逐出门墙；师徒关系就此解除，双方好感重置为中立。"
    relation = player.dao_companion
    if relation:
        player.party = [row for row in player.party if str(row.get("id")) != str(relation.get("id"))]
        deps._set_person_affinity(
            game, str(relation.get("id", "")),
            float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)),
        )
    player.dao_companion = None
    player.heart_demon += deps._sage_scaled_gain(
        player, float(WORLD_SYSTEMS["relationship"]["companion_separation_heart_demon"]),
        "heart_demon_gain_reduction",
    )
    return "separated", f"{name}收回道侣信物、解散誓约；双方好感重置为中立，心魔随之增长。"


def _resolve_relationship_sanction(
    deps: RelationshipSanctionDependencies, game: GameState, pending: dict[str, Any], role: str, mode: str,
    rng: random.Random,
) -> tuple[str, str]:
    runtime = pending.get("runtime", {})
    actual_role = str(runtime.get("role", role))
    name = str(runtime.get("name", "对方"))
    target_id = str(runtime.get("id", ""))
    threshold = float(WORLD_SYSTEMS["relationship"]["hostile_affinity_threshold"])
    if actual_role in {"master", "companion"}:
        relation = game.player.master if actual_role == "master" else game.player.dao_companion
        if not relation or str(relation.get("id", "")) != target_id:
            return "relationship_absent", "这段关系已经先一步结束，问罪之事自然作罢。"
        if mode == "accept":
            return deps._end_sanctioned_relationship(game, actual_role, name)
        if mode != "appease":
            raise ValueError("未知的关系问罪应对")
        affinity = float(relation.get("affinity", 0))
        chance = max(0.08, min(0.72, 0.34 + affinity / 250 + game.player.realm_index * 0.025))
        if rng.random() < chance:
            relation["affinity"] = threshold + 6
            npc = deps._find_npc(game, target_id)
            if npc:
                npc.affinity = relation["affinity"]
            return "appeased", f"你暂时平息{name}的怒意（成功率 {chance:.0%}）；关系得以保留。"
        return deps._end_sanctioned_relationship(game, actual_role, name)

    if actual_role not in {"concubine_owner", "ghost_captor"}:
        raise ValueError("未知的主仆问罪来源")
    status = game.player.concubine_status if actual_role == "concubine_owner" else game.player.ghost_captor
    if not status:
        return "relationship_absent", "主仆约束已经解除，这次索偿自然作罢。"
    npc = deps._find_npc(game, target_id)
    affinity = float(npc.affinity or 0) if npc else float(status.get("affinity", 0))
    if mode == "comply":
        demand = max(1, int(runtime.get("demand", 5)))
        stones = next((item.quantity for item in game.player.inventory if item.id == "spirit_stone"), 0)
        paid = min(demand, stones)
        if paid:
            remove_item(game.player, "spirit_stone", paid)
        shortfall = demand - paid
        opportunity_paid = 0.0
        if shortfall:
            opportunity_paid = min(
                game.player.opportunity,
                opportunity_required(game.player) * min(0.08, 0.02 + shortfall / max(1, demand) * 0.04),
            )
            game.player.opportunity -= opportunity_paid
        new_affinity = min(100.0, affinity + (18 if not shortfall else 10))
        if npc:
            npc.affinity = new_affinity
        status["affinity"] = new_affinity
        return "complied", (
            f"你向{name}交出下品灵石 ×{paid}"
            + (f"，并以机缘 {opportunity_paid:.1f} 抵偿不足" if shortfall else "")
            + "；对方暂且收回威胁。"
        )
    if mode == "appease":
        chance = max(0.08, min(0.70, 0.30 + affinity / 260 + game.player.realm_index * 0.02))
        if rng.random() < chance:
            new_affinity = threshold + 5
            if npc:
                npc.affinity = new_affinity
            status["affinity"] = new_affinity
            return "appeased", f"你的解释暂时说动{name}（成功率 {chance:.0%}），这次索偿被撤回。"
        mode = "defy"
    if mode == "defy":
        relief = float(WORLD_SYSTEMS["relationship"].get("sanction_affinity_relief", 8))
        new_affinity = min(100.0, affinity + relief)
        if npc:
            npc.affinity = new_affinity
        status["affinity"] = new_affinity
        status["angered_until_unit"] = game.diplomacy_unit + 2
        game.player.hp = max(1.0, game.player.hp - max_hp(game.player) * 0.10)
        return "defied", f"{name}以主仆约束惩戒于你；HP 损失 10%，震怒持续两个行动单位。怒气宣泄后，双方好感缓和 {relief:g} 点。"
    raise ValueError("未知的主仆问罪应对")
