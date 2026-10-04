"""Explicit relationships captivity operations; callers own composition."""
from __future__ import annotations

from ...npc_custody import is_free, kill_person, release_person

import copy
import math
import random
import uuid
from typing import Any

from ...content_registry import (
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS,
    PATH_NAMES,
    TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from ...models import GameState, HistoryRecord, Player, SectNpc
from ...rules import combat_power, divine_sense_level, max_hp, puppet_capacity
from ...runtime import decode_rng, encode_rng, now_iso
from ..demonic_definitions import PUPPET_NAMES
from ..possession_system import current_body_age
from ..semantic_events import emit
from .dependencies import CaptivityDependencies


def _capture_cultivator(
    deps: CaptivityDependencies, game: GameState, target: dict[str, Any], own_power: float, rng: random.Random,
) -> tuple[str, str]:
    members = target.get("members") or [{
        "name": target["target_name"], "power": target["target_power"],
        "realm_index": target["target_realm_index"], "layer": target.get("target_layer", 1),
        "npc_id": target.get("npc_id"), "race": target.get("race", "human"),
    }]
    victim = min(members, key=lambda entry: float(entry["power"]))
    ratio = own_power / max(1.0, float(victim["power"]))
    realm_gap = game.player.realm_index - int(victim["realm_index"])
    chance = max(0.08, min(0.92, 0.28 + (ratio - 1) * 0.18 + realm_gap * 0.07))
    victim_index = next(index for index, member in enumerate(members) if member is victim)
    voisinage_captured = str(victim.get("npc_id") or f"enemy-{victim_index}") in target.get("resolved_capture_ids", [])
    if not voisinage_captured and rng.random() >= chance:
        return "victory_escape", f"你虽击败{victim['name']}，却未能封住其遁术（生擒率 {chance:.0%}）。"

    npc_id = victim.get("npc_id")
    npc = deps._find_npc(game, str(npc_id)) if npc_id else None
    path = npc.path if npc else str(victim.get("path", "dao"))
    affinity = float(npc.affinity or 0) if npc else 0.0
    technique = next(
        (entry for entry in TECHNIQUE_CATALOG.values() if entry.path == path and entry.category == "spiritual"
         and entry.grade <= max(1, int(victim["realm_index"]))
         and entry.id not in GUIXU_EXCLUSIVE_TECHNIQUE_IDS),
        None,
    )
    prisoner_id = str(npc_id or f"captive_{uuid.uuid4().hex[:12]}")
    captive_age = int(npc.age if npc else victim.get("age", current_body_age(game.player)))
    captive_lifespan = npc.lifespan if npc else victim.get("lifespan")
    from ..asura import body_facts
    captured_body = body_facts(npc or dict(victim, id=prisoner_id, path=path))
    captive = {
        **captured_body,
        "id": prisoner_id, "npc_id": npc_id, "name": str(victim["name"]),
        "realm_index": int(victim["realm_index"]), "layer": int(victim.get("layer", 1)),
        "realm_name": deps._npc_realm_name(npc or SectNpc("", "", "", int(victim["realm_index"]), int(victim.get("layer", 1)), 0, 1, path=path)),
        "path": path, "path_name": PATH_NAMES.get(path, path), "race": str(victim.get("race", "human")),
        "affinity": affinity - 12, "combat_power": round(float(victim["power"]), 1),
        "main_technique_id": technique.id if technique else None,
        "age": captive_age, "lifespan": captive_lifespan,
        "gender": npc.gender if npc else str(victim.get("gender") or deps._stable_gender(prisoner_id)),
        "captured_age": game.player.age, "source": "combat",
    }
    record = game.detain_person(captive)
    record["affinity"] = affinity - 12
    game.player.prisoners.append(record)
    if npc_id:
        game.encounter_npc_cache = [row for row in game.encounter_npc_cache if row.get("id") != npc_id]
    return "captured", f"你封住{victim['name']}的修为，将其生擒并收入俘虏名册（生擒率 {chance:.0%}）。"


def begin_relationship_capture(deps: CaptivityDependencies, game_id: str, kind: str, target_id: str = "") -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if player.path != "demonic":
        raise ValueError("只有魔修会对亲近之人施展生擒魔禁")
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法对关系人物出手")
    relation = (
        player.master if kind == "master" else
        player.dao_companion if kind == "companion" else
        next((row for row in player.dao_friends if str(row.get("id")) == target_id), None)
        if kind == "friend" else None
    )
    from ...spatial_people import require_access
    require_access(game, relation)
    if not relation or not is_free(relation) or relation.get("world", player.world) != player.world:
        raise ValueError("目标关系人物当前不在身边")
    if relation.setdefault("last_interactions", {}).get("capture_attempt") == player.age:
        raise ValueError("本行动年份已经尝试生擒过此人")
    rng = decode_rng(game.seed, game.rng_state)
    event = deps._instantiate_event(deps.events_by_id["EVT_RELATION_CAPTURE_001"], game, rng)
    event["body"] = event["body"].replace("{target_name}", str(relation["name"]))
    event["runtime"] = {
        "kind":kind, "target_id":str(relation["id"]), "target_name":str(relation["name"]),
        "target_power":deps._relationship_combat_power(relation),
    }
    game.pending_event = event
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _relationship_capture_step(
    deps: CaptivityDependencies, game: GameState, pending: dict[str, Any], stage: str, method: str, rng: random.Random,
) -> tuple[str, str]:
    player = game.player
    runtime = pending.get("runtime", {})
    kind = str(runtime.get("kind", ""))
    relation = (
        player.master if kind == "master" else
        player.dao_companion if kind == "companion" else
        next((row for row in player.dao_friends if str(row.get("id")) == str(runtime.get("target_id"))), None)
        if kind == "friend" else None
    )
    if not relation or str(relation.get("id")) != str(runtime.get("target_id")):
        return "target_absent", "目标已经脱离了这段关系，生擒计划无从继续。"
    relation.setdefault("last_interactions", {})["capture_attempt"] = player.age
    name = str(relation.get("name", "无名修士"))
    if stage == "abandon":
        return "abandoned", f"你最终没有对{name}出手，这段关系暂时维持原状。"

    own_power = deps._player_intrinsic_combat_power(player)
    target_power = max(1.0, float(runtime.get("target_power", deps._relationship_combat_power(relation))))
    ratio_term = math.log2(max(0.25, own_power / target_power))
    realm_gap = player.realm_index - int(relation.get("realm_index", 0))
    affinity = float(relation.get("affinity", 0))
    if stage == "opening":
        method_bonus = 0.16 if method == "ambush" else 0.03
        chance = max(0.06, min(0.94, 0.30 + method_bonus + ratio_term * 0.11 + realm_gap * 0.06 + max(0.0, affinity) / 500))
        if rng.random() >= chance:
            deps._break_capture_relationship(game, relation, kind, captured=False)
            return "escaped", f"{name}识破杀机并断绝关系后遁走（第一重压制成功率 {chance:.0%}）。"
        next_event = deps._instantiate_event(deps.events_by_id["EVT_RELATION_CAPTURE_002"], game, rng)
        next_event["body"] = next_event["body"].replace("{target_name}", name)
        next_event["runtime"] = copy.deepcopy(runtime)
        game.pending_event = next_event
        return "body_suppressed", f"你成功制住{name}的肉身（第一重压制成功率 {chance:.0%}），接下来必须镇封其元神。"

    if stage == "release":
        deps._break_capture_relationship(game, relation, kind, captured=False)
        return "released", f"你放开禁制；{name}惊怒离去，这段关系彻底断绝。"
    if stage != "final":
        raise ValueError("未知关系生擒阶段")
    method_bonus = 0.15 if method == "blood_mark" else 0.04
    if method == "blood_mark":
        damage = max_hp(player) * 0.12
        player.hp = max(1.0, player.hp - damage)
    chance = max(0.05, min(
        0.93,
        0.32 + method_bonus + ratio_term * 0.10 + realm_gap * 0.05
        + max(0, divine_sense_level(player) - int(relation.get("realm_index", 0))) * 0.025,
    ))
    if rng.random() >= chance:
        deps._break_capture_relationship(game, relation, kind, captured=False)
        return "escaped", f"{name}的元神撕开魔禁并远遁（封魂成功率 {chance:.0%}），从此与你恩断义绝。"
    from ..asura import body_facts
    prisoner = {
        **body_facts(deps._find_npc(game, str(relation["id"])) or relation),
        "id":str(relation["id"]), "npc_id":str(relation["id"]), "name":name,
        "realm_index":int(relation.get("realm_index", 0)), "layer":int(relation.get("layer", 1)),
        "realm_name":str(relation.get("realm_name", "境界未明")),
        "path":str(relation.get("path", "dao")),
        "path_name":PATH_NAMES.get(str(relation.get("path", "dao")), str(relation.get("path", "dao"))),
        "race":str(relation.get("race", "human")), "affinity":-100.0,
        "combat_power":round(target_power, 1), "main_technique_id":relation.get("main_technique_id"),
        "age":int(relation.get("age", player.age)), "lifespan":relation.get("lifespan"),
        "gender":str(relation.get("gender") or deps._stable_gender(str(relation.get("id", "")))),
        "captured_age":player.age, "source":f"relationship:{kind}",
    }
    record = game.detain_person(prisoner)
    record["affinity"] = -100.0
    player.prisoners.append(record)
    deps._break_capture_relationship(game, relation, kind, captured=True)
    relation_name = {"master":"师父", "companion":"道侣", "friend":"道友"}.get(kind, "故人")
    return "captured", f"你彻底封住{name}的元神，将昔日{relation_name}收入俘虏名册（封魂成功率 {chance:.0%}）。"


def _break_capture_relationship(
    deps: CaptivityDependencies, game: GameState, relation: dict[str, Any], kind: str, captured: bool,
) -> None:
    player = game.player
    target_id = str(relation.get("id", ""))
    player.party = [entry for entry in player.party if str(entry.get("id")) != target_id]
    if kind == "master":
        player.master = None
    elif kind == "friend":
        player.dao_friends = [row for row in player.dao_friends if str(row.get("id")) != target_id]
    else:
        player.dao_companion = None
    npc = deps._find_npc(game, target_id)
    if npc and not captured:
        npc.affinity = float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0))


def captive_action(deps: CaptivityDependencies, game_id: str, target_id: str, action: str) -> dict[str, Any]:
    if action == "execute":
        return deps.relationship_violence(game_id, "captive", target_id)
    game = deps._load(game_id)
    player = game.player
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法处置俘虏")
    prisoner = next((entry for entry in player.prisoners if str(entry.get("id")) == target_id), None)
    disciple = None if prisoner else next(
        (entry for entry in player.disciples if str(entry.get("id")) == target_id and is_free(entry)), None,
    )
    target = prisoner or disciple
    if not target or not target.get("alive", True):
        raise ValueError("目标俘虏或弟子不存在")
    if action not in {"release", "torture", "corpse", "living", "possess"}:
        raise ValueError("未知俘虏处置方式")
    if action in {"corpse", "living"} and player.path != "demonic":
        raise ValueError("只有魔修能够炼尸或种下活傀标记")
    if action in {"corpse", "living"} and len(player.puppets) >= puppet_capacity(player):
        raise ValueError("神识可控傀儡数量已经达到上限")

    rng = decode_rng(game.seed, game.rng_state)
    name = str(target.get("name", "无名修士"))
    if action == "possess":
        if disciple:
            raise ValueError("夺舍入口只接受已经生擒的肉身")
        from ..possession_system import can_possess, enter_host_body
        allowed, reason = can_possess(player, target)
        if not allowed:
            raise ValueError(reason)
        target_power = max(1.0, float(target.get("combat_power", 1.0)))
        own_power = max(1.0, combat_power(player))
        chance = max(0.10, min(0.95, 0.55 + (own_power - target_power) / (own_power + target_power) * 0.35))
        if rng.random() < chance:
            player.prisoners.remove(target)
            host = enter_host_body(player, target)
            kill_person(game, target.get("npc_id") or target["id"],
                        f"被{player.name}夺舍，原神魂不复存在")
            game.encounter_npc_cache = [
                row for row in game.encounter_npc_cache
                if str(row.get("id")) != str(target.get("npc_id") or target.get("id", ""))
            ]
            result, summary = "possessed", f"你以本魂压过{name}，成功夺取肉身（成功率 {chance:.0%}）；原 NPC 永久退场。"
        else:
            deps._die(game, f"夺舍{name}失败，神魂遭宿主反噬而灭", "SYS_POSSESSION_FAILED")
            result, summary = "dead", f"夺舍{name}失败，魂飞魄散（成功率 {chance:.0%}）。"
    elif action == "release":
        if disciple:
            raise ValueError("弟子不能通过俘虏释放")
        deps._restore_captive_npc(game, target, affinity_gain=10)
        player.prisoners.remove(target)
        emit(game, "captive.released", target_id=target_id)
        result, summary = "released", f"你解开禁制释放{name}，其好感有所回升。"
    elif action == "torture":
        if disciple:
            raise ValueError("弟子不能作为俘虏拷打")
        target["affinity"] = float(target.get("affinity", 0)) - 12
        player.fame += 2
        emit(game, "captive.tortured", target_id=target_id)
        result, summary = "tortured", f"你拷打{name}逼问情报；好感 -12，威名 +2。"
    else:
        result, summary = deps._convert_to_puppet(game, target, action, rng, bool(disciple))

    game.history.append(HistoryRecord(
        "SYS_CAPTIVE_ACTION", 1, player.age, "俘虏处置", action, result, summary,
        {"target_id": target_id, "action": action}, ["system", "captive", "puppet"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _restore_captive_npc(deps: CaptivityDependencies, game: GameState, target: dict[str, Any], affinity_gain: float) -> None:
    release_person(game, target.get("npc_id") or target["id"],
                   affinity=float(target.get("affinity", 0)) + affinity_gain)


def _convert_to_puppet(
    deps: CaptivityDependencies, game: GameState, target: dict[str, Any], kind: str, rng: random.Random, disciple: bool,
) -> tuple[str, str]:
    player = game.player
    rules = deps._demonic_rules()
    target_power = float(target.get("combat_power", max(1.0, combat_power(player) * 0.4)))
    realm_gap = player.realm_index - int(target.get("realm_index", 0))
    power_ratio = combat_power(player) / max(1.0, target_power)
    affinity = float(target.get("affinity", 0))
    if kind == "corpse":
        chance = float(rules["corpse_success_base"]) + realm_gap * 0.07 + math.log2(max(0.25, power_ratio)) * 0.06
    else:
        chance = float(rules["living_success_base"]) + realm_gap * 0.06 + math.log2(max(0.25, power_ratio)) * 0.05 + affinity / 300
    chance = max(0.05, min(0.95, chance))
    if rng.random() >= chance:
        target["affinity"] = affinity - 15
        if kind == "corpse":
            kill_person(game, target.get("npc_id") or target["id"],
                        f"被{player.name}炼尸失败，形神俱灭")
            deps._remove_conversion_target(player, target, disciple)
            return "destroyed", f"你炼制{target['name']}失败，其形神俱灭（成功率 {chance:.0%}）。"
        return "resisted", f"{target['name']}挣脱了活傀标记，好感 -15（成功率 {chance:.0%}）。"

    inherited = float(rules["corpse_power_inheritance"] if kind == "corpse" else rules["living_power_inheritance"])
    technique_id = (
        player.technique.id if kind == "corpse" and player.technique
        else target.get("main_technique_id")
    )
    control = 100.0 if kind == "corpse" else max(15.0, min(92.0, 48 + affinity * 0.28 + realm_gap * 6))
    from ..asura import body_facts
    puppet = {
        **body_facts(target),
        "id": f"puppet_{uuid.uuid4().hex[:12]}", "name": str(target["name"]), "type": kind,
        "type_name": PUPPET_NAMES[kind], "realm_index": int(target.get("realm_index", 0)),
        "layer": int(target.get("layer", 1)), "combat_power": round(target_power * inherited, 1),
        "original_power": round(target_power, 1), "main_technique_id": technique_id,
        "control": round(control, 1), "cultivation_progress": 0.0, "breakthrough_bonus": 0.0,
        "created_age": player.age, "last_infusion_age": None, "alive": True,
        "source": str(target.get("source", "combat")),
        "source_npc_id": str(target.get("npc_id") or target["id"]),
    }
    player.puppets.append(puppet)
    source = str(target.get("source", ""))
    if kind == "corpse" and source == "relationship:companion":
        player.milestones["companion_turned_corpse"] = 1
    elif kind == "corpse" and source == "relationship:master":
        player.milestones["master_turned_corpse"] = 1
    if kind == "living":
        game.detain_person(target, kind="living_puppet")
    else:
        kill_person(game, target.get("npc_id") or target["id"],
                    f"被{player.name}炼为{PUPPET_NAMES[kind]}")
    deps._remove_conversion_target(player, target, disciple)
    return "created", f"{target['name']}已被炼成{PUPPET_NAMES[kind]}，继承 {inherited:.0%} 战力（成功率 {chance:.0%}）。"


def _remove_conversion_target(player: Player, target: dict[str, Any], disciple: bool) -> None:
    if disciple:
        player.disciples = [entry for entry in player.disciples if entry is not target]
    else:
        player.prisoners = [entry for entry in player.prisoners if entry is not target]
