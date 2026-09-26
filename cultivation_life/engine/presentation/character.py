from __future__ import annotations

import copy
from typing import Any
from ...content_registry import ITEM_CATALOG, REALMS, RACE_DEFINITIONS, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from ...models import GameState, Player, SectNpc
from ...system.npc_system import attitude_label
from ...rules import opportunity_required
from ...system.concubine_system import gender_name
from ..dependencies import CharacterViewDependencies


def _public_major_breakthrough(deps: CharacterViewDependencies, player: Player) -> dict[str, Any]:
    if player.cultivation_suppression:
        return {
            "kind": None, "ready": False, "enabled": False, "target_realm": None,
            "action_label": "突破瓶颈", "chance": None, "active_aids": [],
            "met": False, "reason": "当前修为受秘法压制，解除压制后方可继续修行与突破。",
            "missing_affinities": [],
        }
    if player.sealed_cultivation:
        upper_world = str(player.sealed_cultivation.get("upper_world", "spirit"))
        return {
            "kind": None, "ready": False, "enabled": False, "target_realm": None,
            "action_label": "突破瓶颈", "chance": None, "active_aids": [],
            "met": False, "reason": f"真实道果正受下界压制，返回{WORLD_SYSTEMS['world_names'].get(upper_world, upper_world)}后方可继续修行。",
            "missing_affinities": [],
        }
    kind = deps._manual_breakthrough_kind(player)
    at_bottleneck = kind is not None
    major = kind == "major"
    deterministic_monster_evolution = bool(major and player.path == "monster" and deps.bloodline_content_available())
    waiting = player.awaiting_major_breakthrough if major else player.awaiting_minor_breakthrough
    requirement = deps._major_breakthrough_requirement(player) if major else {
        "met": True, "reason": "尚未抵达大境界瓶颈。", "missing_affinities": [],
    }
    chance = (
        None if deterministic_monster_evolution
        else deps._breakthrough_chance(player, major=major) if at_bottleneck else None
    )
    active_aids = [
        {"id": item_id, "name": ITEM_CATALOG[item_id].name, "bonus": ITEM_CATALOG[item_id].breakthrough_bonus}
        for item_id in player.active_breakthrough_aids if item_id in ITEM_CATALOG
    ]
    if major:
        target_index = player.realm_index + 1
        target_name = (
            WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(str(target_index), REALMS[target_index].name)
            if target_index < len(REALMS) else None
        ) if player.path == "demonic" else (REALMS[target_index].name if target_index < len(REALMS) else None)
        action_label = "选择血脉进化" if deterministic_monster_evolution else "突破大境界"
    elif at_bottleneck:
        target_name = deps._minor_layer_target(player)
        action_label = "突破小境界"
        requirement["reason"] = (
            "阶段关隘已经圆满，可以服丹整备后手动冲关。"
            if player.layer in {3, 6} else
            "层级瓶颈已经圆满；本层冲击失败会为下一次累积专属成功率。"
        )
    else:
        target_name = None
        action_label = "突破瓶颈"
    return {
        "kind": kind,
        "ready": bool(waiting and at_bottleneck and player.opportunity >= opportunity_required(player)),
        "enabled": bool(
            player.alive and waiting and at_bottleneck
            and player.opportunity >= opportunity_required(player) and requirement["met"]
        ),
        "target_realm": target_name,
        "action_label": action_label,
        "chance": chance,
        "active_aids": active_aids,
        **requirement,
    }


def _public_body_cultivation(deps: CharacterViewDependencies, player: Player) -> dict[str, Any]:
    maximum = int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
    required = deps._body_progress_required(player)
    ready = bool(
        player.body_technique and player.body_training < maximum
        and player.awaiting_body_breakthrough and player.body_progress >= required
    )
    return {
        "layer":player.body_training, "max_layer":maximum,
        "progress":round(player.body_progress, 1), "required":round(required, 1),
        "technique":copy.deepcopy(player.body_technique.__dict__) if player.body_technique else None,
        "ready":ready, "chance":deps._body_breakthrough_chance(player) if ready else None,
        "target_layer":player.body_training + 1 if player.body_training < maximum else None,
        "tribulation_damage_reduction":deps._body_tribulation_damage_reduction(player),
        "cultivation_breakthrough_bonus":player.body_training // 20 * float(WORLD_SYSTEMS["body_cultivation"]["cultivation_breakthrough_bonus_per_20_layers"]),
        "training_speed_multiplier":(
            float(WORLD_SYSTEMS.get("monster_cultivation", {}).get("body_training_multiplier", 1.5))
            if player.path == "monster" else 1.0
        ),
    }


def _public_dao_companion(deps: CharacterViewDependencies, game: GameState) -> dict[str, Any] | None:
    companion = game.player.dao_companion
    if not companion:
        return None
    result = copy.deepcopy(companion)
    result["gender"] = str(result.get("gender") or deps._stable_gender(str(result.get("id", ""))))
    result["gender_name"] = gender_name(result["gender"])
    result["can_recruit_concubine"] = bool(
        result["gender"] == "female" and deps._rank(result) <= deps._rank(game.player)
        and not any(str(row.get("id")) == str(result.get("id")) for row in game.player.concubines)
    )
    technique_id = result.get("main_technique_id")
    result["main_technique_name"] = (
        TECHNIQUE_CATALOG[technique_id].name if technique_id in TECHNIQUE_CATALOG else "尚无主修功法"
    )
    result["same_cultivation"] = bool(deps._joint_companion_eligible(game.player))
    result["breakthrough_bonus"] = (
        float(WORLD_SYSTEMS["relationship"]["companion_breakthrough_bonus"])
        if result["same_cultivation"] else 0.0
    )
    result["combat_power"] = deps._relationship_combat_power(companion)
    result["in_party"] = any(entry.get("id") == companion.get("id") for entry in game.player.party)
    result["can_invite_party"] = bool(
        companion.get("alive", True) and companion.get("world") == game.player.world
        and not result["in_party"]
        and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
    )
    result["can_invite_faction"] = deps._relationship_can_join_faction(game, companion)
    result["can_invite_guest"] = deps._intrigue_can_invite_guest(
        game, str(companion.get("id", "")),
    )
    return result


def _public_dao_friends(deps: CharacterViewDependencies, game: GameState) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for friend in game.player.dao_friends:
        row = copy.deepcopy(friend)
        row["gender"] = str(row.get("gender") or deps._stable_gender(str(row.get("id", ""))))
        row["gender_name"] = gender_name(row["gender"])
        row["can_recruit_concubine"] = bool(
            row["gender"] == "female" and deps._rank(row) <= deps._rank(game.player)
            and not any(str(entry.get("id")) == str(row.get("id")) for entry in game.player.concubines)
        )
        technique_id = str(row.get("main_technique_id", ""))
        row["main_technique_name"] = (
            TECHNIQUE_CATALOG[technique_id].name if technique_id in TECHNIQUE_CATALOG else "主修未明"
        )
        row["combat_power"] = deps._relationship_combat_power(friend)
        row["in_party"] = any(entry.get("id") == row.get("id") for entry in game.player.party)
        row["can_invite_party"] = bool(
            row.get("alive", True) and row.get("world") == game.player.world and not row["in_party"]
            and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
        )
        row["can_invite_faction"] = deps._relationship_can_join_faction(game, friend)
        row["can_invite_guest"] = deps._intrigue_can_invite_guest(
            game, str(friend.get("id", "")),
        )
        result.append(row)
    return result


def _relationship_can_join_faction(deps: CharacterViewDependencies, game: GameState, relation: dict[str, Any]) -> bool:
    sect = game.sects.get(game.player.faction_id or "")
    return bool(
        sect and not sect.extinct and sect.world == game.player.world
        and relation.get("alive", True) and relation.get("world") == game.player.world
        and not deps._npc_faction_id(game, str(relation.get("id", "")))
    )


def _public_personal_relations(deps: CharacterViewDependencies, game: GameState) -> dict[str, list[dict[str, Any]]]:
    rules = WORLD_SYSTEMS["relationship"]
    high_threshold = float(rules["positive_affinity_threshold"])
    low_threshold = float(rules["hostile_affinity_threshold"])
    people = {npc.id:npc for npc in deps._all_world_npcs(game) if npc.alive and npc.world == game.player.world}
    relationship_labels: dict[str, str] = {}
    for label, entries in (
        ("师父", [game.player.master] if game.player.master else []),
        ("道侣", [game.player.dao_companion] if game.player.dao_companion else []),
        ("道友", game.player.dao_friends), ("弟子", game.player.disciples),
    ):
        for relation in entries:
            if relation and relation.get("alive", True) and relation.get("world") == game.player.world:
                relationship_labels[str(relation.get("id"))] = label
                if str(relation.get("id")) not in people:
                    people[str(relation.get("id"))] = SectNpc(
                        str(relation.get("id")),str(relation.get("name","无名修士")),"旧识",
                        int(relation.get("realm_index",0)),int(relation.get("layer",1)),
                        int(relation.get("age",18)),relation.get("lifespan"),
                        spirit_root=str(relation.get("spirit_root","none")),path=str(relation.get("path","dao")),
                        race=str(relation.get("race","human")),world=str(relation.get("world",game.player.world)),
                        affinity=float(relation.get("affinity",0)),
                    )
    rows = [{
        "id":npc.id,"name":npc.name,"affinity":round(float(npc.affinity or 0),1),
        "attitude":attitude_label(npc.affinity or 0,0),"realm_name":deps._npc_realm_name(npc),
        "gender":npc.gender,"gender_name":gender_name(npc.gender),
        "can_recruit_concubine":bool(
            npc.gender == "female" and deps._rank(npc) <= deps._rank(game.player)
            and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
        ),
        "can_invite_guest":deps._intrigue_can_invite_guest(game, npc.id),
        "relationship":relationship_labels.get(npc.id,"相识"),
        "faction_name":deps._faction_meta(game, deps._npc_faction_id(game,npc.id))["name"] if deps._npc_faction_id(game,npc.id) else None,
    } for npc in people.values() if float(npc.affinity or 0) >= high_threshold or float(npc.affinity or 0) <= low_threshold]
    return {
        "high":sorted((row for row in rows if row["affinity"] >= high_threshold),key=lambda row:-row["affinity"]),
        "low":sorted((row for row in rows if row["affinity"] <= low_threshold),key=lambda row:row["affinity"]),
    }


def _relationship_combat_power(deps: CharacterViewDependencies, relation: dict[str, Any]) -> float:
    shell = SectNpc(
        str(relation.get("id", "relation")), str(relation.get("name", "无名")), "",
        int(relation.get("realm_index", 0)), int(relation.get("layer", 1)),
        int(relation.get("age", 1)), relation.get("lifespan"),
        spirit_root=str(relation.get("spirit_root", "none")),
        path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
        world=str(relation.get("world", "human")), affinity=float(relation.get("affinity", 0)),
    )
    base = deps._npc_power(shell)
    technique = TECHNIQUE_CATALOG.get(str(relation.get("main_technique_id", "")))
    technique_bonus = technique.combat_bonus if technique else 0.0
    item_bonus = sum(
        ITEM_CATALOG[item_id].combat_bonus * int(quantity)
        for item_id, quantity in relation.get("items", {}).items() if item_id in ITEM_CATALOG
    )
    return round(base + technique_bonus + item_bonus, 1)


def _public_party(deps: CharacterViewDependencies, game: GameState) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for reference in game.player.party:
        companion = game.player.dao_companion
        if companion and companion.get("id") == reference.get("id"):
            if companion.get("alive", True) and companion.get("world") == game.player.world:
                perception = deps._relationship_cultivation_perception(game, companion, "道侣")
                result.append({
                    "id": companion["id"], "name": companion["name"],
                    "realm_index": perception["realm_index"], "layer": perception["layer"],
                    "realm_name": perception["realm_name"],
                    "combat_power": perception["display_power"] or deps._relationship_combat_power(companion),
                    "cultivation_concealment": {
                        key: value for key, value in perception.items()
                        if key not in {"realm_index", "layer", "realm_name", "display_power"}
                    } if perception["concealed"] else None,
                    "affinity": round(float(companion.get("affinity", 0)), 1), "attitude": "道侣",
                    "can_interact":game.governance_actions.get(f"party_interaction:{companion['id']}") != game.player.age,
                    "can_cross_spirit":bool(deps._party_crossing_candidate(game, str(companion["id"]))),
                    "selected_for_crossing":bool(
                        game.player.joint_spirit_crossing
                        and str(game.player.joint_spirit_crossing.get("id")) == str(companion["id"])
                        and not game.player.joint_spirit_crossing.get("declined")
                    ),
                })
            continue
        npc = deps._find_npc(game, str(reference.get("id", "")))
        relation = next((entry for entry in [game.player.master, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == str(reference.get("id"))), None)
        if npc and npc.alive and npc.world == game.player.world:
            perception = deps._npc_cultivation_perception(game, npc)
            row = {
                "id": npc.id, "name": npc.name,
                "realm_index": perception["realm_index"], "layer": perception["layer"],
                "realm_name": perception["realm_name"],
                "combat_power": perception["display_power"] or deps._npc_power(npc),
                "cultivation_concealment": {
                    key: value for key, value in perception.items()
                    if key not in {"realm_index", "layer", "realm_name", "display_power"}
                } if perception["concealed"] else None,
                "affinity": round(npc.affinity or 0, 1), "attitude": attitude_label(npc.affinity or 0, 0),
            }
        elif relation and relation.get("alive", True) and relation.get("world") == game.player.world:
            perception = deps._relationship_cultivation_perception(game, relation)
            row = {
                "id":str(relation["id"]), "name":str(relation["name"]),
                "realm_index": perception["realm_index"], "layer": perception["layer"],
                "realm_name": perception["realm_name"],
                "combat_power": perception["display_power"] or deps._relationship_combat_power(relation),
                "cultivation_concealment": {
                    key: value for key, value in perception.items()
                    if key not in {"realm_index", "layer", "realm_name", "display_power"}
                } if perception["concealed"] else None,
                "affinity":round(float(relation.get("affinity",0)),1),
                "attitude":attitude_label(float(relation.get("affinity",0)),0),
            }
        else:
            continue
        row["can_interact"] = game.governance_actions.get(f"party_interaction:{row['id']}") != game.player.age
        row["can_cross_spirit"] = bool(deps._party_crossing_candidate(game, row["id"]))
        row["selected_for_crossing"] = any(str(entry.get("id")) == row["id"] for entry in game.player.joint_friend_crossing)
        result.append(row)
    return result


def _public_wanted(deps: CharacterViewDependencies, game: GameState) -> list[dict[str, Any]]:
    player = game.player
    threshold = float(WORLD_SYSTEMS["faction_conflict"]["wanted_threshold"])
    labels = {"sect": "宗门", "family": "家族", "race": "种族", "world": "修仙界包围网"}
    result = []
    for key, value in sorted(player.hostility.items()):
        if value <= threshold:
            continue
        kind, entity_id = key.split(":", 1)
        if deps._hostility_entity_state(game, key).get("status") != "active":
            continue
        display_name = (
            deps._hostility_name(key, game)
            if kind in {"sect", "family"} else
            RACE_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
            if kind == "race" else WORLD_SYSTEMS["world_names"].get(entity_id, entity_id) + "包围网"
        )
        result.append({
            "key": key, "kind": kind, "id": entity_id,
            "name": labels.get(kind, "势力"), "display_name": display_name,
            "hostility": round(value, 1),
        })
    return result
