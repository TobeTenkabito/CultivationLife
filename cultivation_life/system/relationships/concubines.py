"""Explicit relationships concubines operations; callers own composition."""
from __future__ import annotations

import copy
from typing import Any

from ...content_registry import WORLD_SYSTEMS
from ...models import HistoryRecord
from ...rules import max_hp, max_mp, opportunity_required
from ...runtime import decode_rng, encode_rng, now_iso
from ..semantic_events import emit
from .dependencies import ConcubineActionDependencies


def manage_concubine(
    deps: ConcubineActionDependencies, game_id: str, target_id: str, action: str,
) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法处理侍妾事务")
    rng = decode_rng(game.seed, game.rng_state)
    existing = next((row for row in player.concubines if str(row.get("id")) == target_id), None)

    if action == "recruit":
        if existing:
            raise ValueError("此人已经在侍妾名册中")
        target, source = deps._concubine_target(game, target_id)
        if not target:
            raise ValueError("目标人物当前无法回应")
        normalized = deps._normalize_concubine(target, source)
        normalized["world"] = player.world
        if normalized["gender"] != "female":
            raise ValueError("侍妾名分只可向女性修士提出")
        if deps._rank(normalized) > deps._rank(player):
            raise ValueError("修为高于你的修士必定拒绝侍妾之请")
        gap = player.realm_index - int(normalized["realm_index"])
        layer_gap = player.layer - int(normalized["layer"]) if gap == 0 else 0
        chance = 1.0 if source == "captive" else max(
            0.12, min(0.96, 0.34 + gap * 0.14 + layer_gap * 0.025 + float(normalized["affinity"]) / 300),
        )
        if rng.random() >= chance:
            npc = deps._find_npc(game, normalized["npc_id"])
            if npc:
                npc.affinity = float(npc.affinity or 0) - 6
            result = "refused"
            summary = f"{normalized['name']}拒绝了侍妾之请（同意率 {chance:.0%}）。"
        else:
            normalized["joined_age"] = player.age
            player.concubines.append(normalized)
            emit(game, "concubine.recruited", target_id=normalized["id"])
            if source == "captive":
                player.prisoners = [row for row in player.prisoners if row is not target]
            player.party = [row for row in player.party if str(row.get("id")) != target_id]
            if player.master and str(player.master.get("id")) == target_id:
                player.master = None
            if player.dao_companion and str(player.dao_companion.get("id")) == target_id:
                player.dao_companion = None
            player.dao_friends = [row for row in player.dao_friends if str(row.get("id")) != target_id]
            player.disciples = [row for row in player.disciples if str(row.get("id")) != target_id]
            result = "joined"
            summary = f"{normalized['name']}进入侍妾名册（同意率 {chance:.0%}）；侍妾数量没有上限。"
    else:
        if not existing:
            raise ValueError("侍妾名册中没有此人")
        name = str(existing.get("name", "无名修士"))
        npc = deps._find_npc(game, str(existing.get("npc_id", target_id)))
        alive = bool(npc.alive) if npc and existing.get("source") != "captive" else bool(existing.get("alive", True))
        world = str(npc.world) if npc else str(existing.get("world", ""))
        if action in {"cauldron", "corpse"} and (not alive or world != player.world):
            raise ValueError("此人已经陨落或不在当前界面，无法处置")
        if action == "cauldron":
            if existing.get("last_cauldron_unit") == game.diplomacy_unit:
                raise ValueError("本行动单位已经以此人作过炉鼎")
            scale = 0.8 if player.concubine_status else 1.0
            gain = round(opportunity_required(player) * (0.018 + int(existing.get("realm_index", 0)) * 0.003) * scale, 1)
            actual = deps._add_opportunity(player, gain)
            hp_gain = min(max_hp(player) - player.hp, max_hp(player) * 0.24)
            mp_gain = min(max_mp(player) - player.mp, max_mp(player) * 0.24)
            player.hp += hp_gain
            player.mp += mp_gain
            existing["last_cauldron_unit"] = game.diplomacy_unit
            existing["cauldron_uses"] = int(existing.get("cauldron_uses", 0)) + 1
            existing["affinity"] = float(existing.get("affinity", 0)) - 8
            hehuan = bool(player.technique and player.technique.element == "sex")
            if hehuan:
                player.concubine_breakthrough_bonus = min(0.02, player.concubine_breakthrough_bonus + 0.01)
            result = "cauldron"
            summary = (
                f"你以{name}作炉鼎，机缘 +{actual:.1f}，HP +{hp_gain:.0f}，MP +{mp_gain:.0f}。"
                + (f" 合欢功法使下次突破基础概率累计 +{player.concubine_breakthrough_bonus:.0%}。" if hehuan else "")
            )
        elif action == "corpse":
            if player.path != "demonic":
                raise ValueError("只有魔修能够将侍妾炼尸")
            from ...rules import puppet_capacity
            if len(player.puppets) >= puppet_capacity(player):
                raise ValueError("神识可控傀儡数量已经达到上限")
            captive = copy.deepcopy(existing) | {"source": "relationship:concubine"}
            player.concubines = [row for row in player.concubines if row is not existing]
            player.prisoners.append(captive)
            result, summary = deps._convert_to_puppet(game, captive, "corpse", rng, False)
        elif action == "dismiss":
            player.concubines = [row for row in player.concubines if row is not existing]
            npc = deps._find_npc(game, str(existing.get("npc_id", target_id)))
            if npc and existing.get("source") == "captive":
                for field in ("age", "lifespan", "realm_index", "layer", "cultivation_progress"):
                    if field in existing:
                        setattr(npc, field, existing[field])
                npc.alive = bool(existing.get("alive", True))
                npc.death_reason = None if npc.alive else existing.get("death_reason", npc.death_reason)
            deps._set_person_affinity(
                game, str(existing.get("npc_id", target_id)),
                float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)),
            )
            result, summary = "dismissed", f"你遣散了{name}，双方好感重置为中立，此后不再以侍妾名分相待。"
        else:
            raise ValueError("未知侍妾操作")

    game.history.append(HistoryRecord(
        "SYS_CONCUBINE_ACTION", 1, player.age, "侍妾名册", action, result, summary,
        {"target_id": target_id, "action": action}, ["system", "relationship", "concubine"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)
