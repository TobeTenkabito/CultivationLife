from __future__ import annotations

import copy
import random
from typing import Any
from ...content_registry import ACTIONS, ITEM_CATALOG, REALMS, RACE_DEFINITIONS, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord, Player, SectNpc
from ...rules import (
    add_item,
    expected_combat_power,
    max_hp,
    max_mp,
    opportunity_multiplier,
    opportunity_required,
    recommended_combat_power,
)
from ...runtime import decode_rng, encode_rng, now_iso
from ...world_state import encounter_weight, race_pair
from ...system.possession_system import advance_player_age, current_body_age
from ..dependencies import EncounterActionDependencies


def _remember_faction_prison_release(player: Player, prison: dict[str, Any]) -> None:
    """Persist the exact former jailer so a later dissolution can match it."""
    key = str(prison.get("key", ""))
    if ":" not in key:
        return
    kind, faction_id = key.split(":", 1)
    if kind not in {"sect", "family"} or not faction_id:
        return
    flag = f"released_faction_prison:{kind}:{faction_id}"
    if flag not in player.story_flags:
        player.story_flags.append(flag)


def _record_former_jailer_dissolved(player: Player, kind: str, faction_id: str) -> bool:
    flag = f"released_faction_prison:{kind}:{faction_id}"
    if flag not in player.story_flags:
        return False
    player.milestones["dissolved_former_jailer"] = max(
        1, int(player.milestones.get("dissolved_former_jailer", 0)),
    )
    return True


def prison_action(deps: EncounterActionDependencies, game_id: str, action: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    prison = player.imprisonment
    if not prison:
        raise ValueError("你当前并未被关押")
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    rng = decode_rng(game.seed, game.rng_state)
    key = str(prison["key"])
    if action == "endure":
        advance_player_age(player)
        hp_loss = max_hp(player) * rng.uniform(0.08, 0.18)
        mp_loss = max_mp(player) * rng.uniform(0.06, 0.14)
        player.hp = max(1.0, player.hp - hp_loss)
        player.mp = max(0.0, player.mp - mp_loss)
        degraded = False
        if (
            player.realm_index < 9
            and rng.random() < float(WORLD_SYSTEMS["faction_conflict"]["prison_breakthrough_loss_chance"])
        ):
            if player.layer > 1:
                player.layer -= 1
            elif player.realm_index > 1:
                player.realm_index -= 1
                player.layer = REALMS[player.realm_index].layers
            player.opportunity = 0
            degraded = True
        prison["remaining_years"] = max(0, int(prison["remaining_years"]) - 1)
        hostility_reduction = float(prison.get("hostility_reduction_per_year", 4.0))
        player.hostility[key] = max(0.0, player.hostility.get(key, 0) - hostility_reduction)
        prison["hostility"] = round(player.hostility[key], 1)
        deps._annual_sect_update(game, rng)
        deps._annual_world_npc_update(game, rng)
        if player.lifespan is not None and current_body_age(player) >= player.lifespan:
            deps._die(game, "囚禁期间寿元耗尽", "SYS_PRISON_LIFESPAN")
            result, summary = "dead", "你未能熬到刑满，在大牢中寿尽坐化。"
        else:
            deps._check_tribulation(game, rng)
        if not player.alive:
            pass
        elif prison["remaining_years"] <= 0:
            player.hostility[key] = 0.0
            if key.startswith("world:"):
                deps._record_world_coalition_amnesty(player, key.split(":", 1)[1])
            deps._remember_faction_prison_release(player, prison)
            player.imprisonment = None
            deps._intrigue_sync_player_prison(game)
            result = "released"
            summary = "刑期已满，旧案已经服结，对你的敌意与通缉归零。"
        else:
            result = "degraded" if degraded else "endured"
            summary = f"你熬过一年刑狱折磨，尚余 {prison['remaining_years']} 年。" + (" 酷刑令你的修为倒退。" if degraded else "")
    elif action in {"wait", "cultivate"}:
        if prison.get("facility") != "faction_prison":
            raise ValueError("当前牢狱不允许此项行动")
        advance_player_age(player)
        gain = 0.0
        if action == "cultivate":
            gain = deps._add_opportunity(player, max(0.2, opportunity_required(player) * 0.01))
            player.mp = max(0.0, player.mp - max_mp(player) * 0.04)
        prison["remaining_years"] = max(0, int(prison["remaining_years"]) - 1)
        hostility_reduction = float(prison.get("hostility_reduction_per_year", 4.0))
        player.hostility[key] = max(0.0, player.hostility.get(key, 0) - hostility_reduction)
        prison["hostility"] = round(player.hostility[key], 1)
        deps._annual_sect_update(game, rng)
        deps._annual_world_npc_update(game, rng)
        if player.lifespan is not None and current_body_age(player) >= player.lifespan:
            deps._die(game, "囚禁期间寿元耗尽", "SYS_PRISON_LIFESPAN")
            result, summary = "dead", "你未能熬到刑满，在大牢中寿尽坐化。"
        elif prison["remaining_years"] <= 0:
            player.hostility[key] = 0.0
            deps._remember_faction_prison_release(player, prison)
            player.imprisonment = None
            deps._intrigue_sync_player_prison(game)
            result, summary = "released", "刑期已满，你获准离开势力监狱。"
        else:
            result = "cultivated" if action == "cultivate" else "waited"
            summary = (f"你在禁制下完成一年受限修炼，机缘 +{gain:.1f}；" if action == "cultivate" else "你静待一年；") + f"尚余 {prison['remaining_years']} 年刑期。"
    elif action == "escape":
        if prison.get("facility") == "faction_prison":
            raise ValueError("势力监狱 V1 暂不开放越狱")
        guard_power = expected_combat_power(player.realm_index, max(1, player.layer)) * (1 + player.hostility.get(key, 0) / 160)
        own_power = deps._player_intrinsic_combat_power(player)
        chance = max(0.05, min(0.78, 0.18 + own_power / max(1.0, guard_power) * 0.28))
        player.hostility[key] = player.hostility.get(key, 0) + float(WORLD_SYSTEMS["faction_conflict"]["escape_hostility_gain"])
        if rng.random() < chance:
            player.imprisonment = None
            deps._intrigue_sync_player_prison(game)
            result, summary = "escaped", f"你趁守卫换岗杀出大牢（成功率 {chance:.0%}），但通缉进一步加重。"
        else:
            damage = max_hp(player) * rng.uniform(0.25, 0.45)
            player.hp = max(0.0, player.hp - damage)
            if player.hp <= 0:
                deps._die(game, "越狱失败，被狱卒当场格杀", "SYS_PRISON_ESCAPE")
                result, summary = "dead", "越狱失败，你被当场格杀。"
            else:
                result, summary = "failed", f"越狱失败，HP -{damage:.0f}，敌对值继续上升。"
    else:
        raise ValueError("未知牢狱行动")
    if action in {"endure", "wait", "cultivate"} and player.alive and not deps._advance_soul_erosion_time(game, 1):
        result = "dead"
        summary = "刑狱岁月令魂蚀越过最后界限，你在出狱前魂飞魄散。"
    if action in {"endure", "wait", "cultivate"} and player.alive:
        drained = deps._advance_concubine_status(game, 1)
        if drained:
            summary += f" 侍妾名分仍在，机缘又被抽走 {drained:.1f}。"
    deps._intrigue_sync_player_prison(game)
    game.history.append(HistoryRecord(
        "SYS_PRISON_ACTION", 1, player.age, "身陷囹圄", action, result, summary,
        {"imprisonment": copy.deepcopy(player.imprisonment)}, ["system", "prison", "wanted"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _available_bounty_authorities(deps: EncounterActionDependencies, game: GameState) -> list[dict[str, str]]:
    authorities: list[dict[str, str]] = []
    if deps._has_race_voice(game):
        race_id = deps._player_allegiance_race(game.player)
        race_name = RACE_DEFINITIONS.get(race_id, {"name":race_id})["name"]
        authorities.append({"id":"race","name":f"{race_name}大乘议会"})
    if deps._has_sect_voice(game):
        sect = game.sects[game.player.faction_id]
        authorities.append({"id":"sect","name":sect.name})
    if deps._has_family_voice(game):
        authorities.append({"id":"family","name":game.family.name})
    return authorities


def issue_bounty(deps: EncounterActionDependencies, game_id: str, npc_id: str, authority: str = "") -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法颁布通缉令")
    authorities = deps._available_bounty_authorities(game)
    if not authorities:
        raise ValueError("至少取得种族、宗门或家族其中一方的话语权，才能颁布通缉令")
    authority_row = next((row for row in authorities if row["id"] == authority), None)
    if authority and not authority_row:
        raise ValueError("你尚未掌握所选势力的通缉权")
    authority_row = authority_row or authorities[0]
    if any(row.get("target_id") == npc_id and row.get("status") == "active" for row in game.player_bounties):
        raise ValueError("此人已经在你的通缉令上")
    npc = game.world_npcs.get(npc_id) or game.notable_npcs.get(npc_id)
    if not npc:
        npc = deps._promote_cached_npc(game, npc_id, "被玩家颁布通缉令")
    if not npc or not npc.alive or npc.world != player.world:
        raise ValueError("只能通缉当前界面的固定人物或缓存人物")
    bounty = {
        "id":f"bounty_{player.age}_{len(game.player_bounties)}", "target_id":npc.id,
        "name":npc.name, "world":npc.world, "status":"active", "issued_age":player.age,
        "attempts":0, "target_power":round(deps._npc_power(npc),1),
        "authority":authority_row["id"], "issuer_name":authority_row["name"],
    }
    game.player_bounties.append(bounty)
    game.history.append(HistoryRecord(
        "SYS_PLAYER_BOUNTY",1,player.age,"三权通缉令",npc.id,"issued",
        f"你以{authority_row['name']}的名义通缉{npc.name}。",
        {"bounty":copy.deepcopy(bounty)},["system","wanted","player_order",f"world:{player.world}"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def intercept_faction_npc(deps: EncounterActionDependencies, game_id: str, npc_id: str) -> dict[str, Any]:
    """Explicitly attack a member shown in the player's current faction roster."""
    game = deps._load(game_id)
    player = game.player
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法截杀宗门修士")
    sect = game.sects.get(player.faction_id or "")
    if not sect or sect.extinct or sect.world != player.world:
        raise ValueError("当前没有可供截杀的宗门名册")
    npc = next(
        (row for row in deps._sect_members(game, sect) if row.id == npc_id and row.alive and row.world == player.world),
        None,
    )
    if not npc:
        raise ValueError("目标已不在当前宗门名册中")
    rng = decode_rng(game.seed, game.rng_state)
    power = deps._npc_power(npc)
    race = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
    target = {
        "target_name":npc.name, "target_power":power, "primary_power":power,
        "target_realm_index":npc.realm_index, "target_layer":npc.layer,
        "target_realm_visible":True, "target_realm_display":deps._npc_realm_name(npc),
        "combat_type":"cultivator", "race":npc.race, "race_name":race["name"],
        "race_description":race["description"], "world":npc.world, "npc_id":npc.id,
        "faction_id":sect.id, "path":npc.path, "treasure_item_id":npc.treasure_item_id,
        "kill_karma":True, "action":"slay", "non_story_combat":True,
    }
    result, summary = deps._combat(game, target, True, rng)
    summary = deps._apply_combat_action_rewards(game, "slay", result, summary, rng)
    game.history.append(HistoryRecord(
        "SYS_FACTION_INTERCEPT", 1, player.age, "宗门截杀", npc.id, result, summary,
        {"npc_id":npc.id, "faction_id":sect.id},
        ["system","combat","slay","faction","intercept",f"world:{player.world}"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _personal_combat_step(deps: EncounterActionDependencies, game: GameState, action: str, rng: random.Random) -> str:
    player = game.player
    settings = ACTIONS[action]["combat"]
    target_name = rng.choice(settings["target_names"])
    if settings.get("combat_type") == "beast":
        encounter_power = deps._player_intrinsic_combat_power(player)
        if player.cultivation_concealment:
            concealment = player.cultivation_concealment
            encounter_power = recommended_combat_power(
                int(concealment["realm_index"]), int(concealment.get("layer", 1)),
            )
        target = {
            "target_name": target_name,
            "target_power": max(1.0, encounter_power * rng.uniform(*settings["power_multiplier"])),
            "target_realm_index": max(1, player.realm_index - 1),
            "combat_type": "beast",
            "success_threshold": settings.get("success_threshold"),
        }
    else:
        target = deps._known_npc_encounter_target(game, settings, rng)
        if target is None:
            target = deps._generate_cultivator_target(
                player, target_name, settings, rng, game=game,
                use_player_concealment=True,
            )
            deps._cache_encounter_target(game, target, rng)
    target["kill_karma"] = bool(settings.get("kill_karma", True))
    target["capture"] = bool(settings.get("capture", False))
    target["action"] = action
    target["non_story_combat"] = True
    if target.get("combat_type") == "cultivator" and len(target.get("members", [])) > 1 and action in {"spar", "slay"}:
        event_id = "EVT_TEAM_SPAR_PREVIEW_001" if action == "spar" else "EVT_TEAM_SLAY_PREVIEW_001"
        event = deps.events_by_id[event_id]
        game.pending_event = deps._instantiate_event(event, game, rng)
        game.pending_event["runtime"] = copy.deepcopy(target)
        player_power = deps._player_battle_power(game)
        body = game.pending_event["body"]
        replacements = {
            "{team_size}": str(len(target["members"])),
            "{target_realm}": str(target["target_realm_display"]),
            "{target_power}": f"{target.get('target_power_display', target['target_power']):.0f}",
            "{player_power}": f"{player_power:.0f}",
        }
        for marker, value in replacements.items():
            body = body.replace(marker, value)
        if target.get("treasure_rumored") and target.get("treasure_item_id") in ITEM_CATALOG:
            body += f" 传闻为首者携带了{ITEM_CATALOG[target['treasure_item_id']].name}。"
        game.pending_event["body"] = body
        return f"你遇到一支{len(target['members'])}人修士队伍，已先观察其修为与合计战力，尚未交手。"
    result, summary = deps._combat(game, target, bool(settings.get("lethal")), rng)
    if target.get("combat_type") == "cultivator":
        race_text = (
            f"对方属于{target['race_name']}（{target['race_description']}），"
            if deps._world_supports(player.world, "races") else ""
        )
        team_text = f"，同行共 {len(target.get('members', []))} 人" if len(target.get("members", [])) > 1 else ""
        rumor = (
            f" 传闻中这个人携带了{ITEM_CATALOG[target['treasure_item_id']].name}。"
            if target.get("treasure_rumored") and target.get("treasure_item_id") in ITEM_CATALOG else ""
        )
        summary = (
            f"{race_text}你判断对方修为为{target['target_realm_display']}{team_text}，"
            f"表面战斗力约 {target.get('target_power_display', target['target_power']):.0f}。"
            f"{rumor}" + summary
        )
    return deps._apply_combat_action_rewards(game, action, result, summary, rng)


def _apply_combat_action_rewards(
    deps: EncounterActionDependencies, game: GameState, action: str, result: str, summary: str, rng: random.Random,
    *, player_defending: bool = False,
) -> str:
    player = game.player
    settings = ACTIONS[action]["combat"]
    if action == "hunt_beast" and result == "killed" and not player_defending:
        sha_gain = rng.randint(*settings["sha_qi_gain"])
        sha_gain = deps._sage_scaled_gain(player, sha_gain, "sha_qi_gain_reduction")
        player.sha_qi += sha_gain
        summary += f" 妖血淬身，煞气 +{sha_gain}。"
    if result in {"victory", "killed"} and settings.get("reward_stones"):
        reward = rng.randint(*settings["reward_stones"])
        add_item(player, "spirit_stone", reward)
        summary += f" 你从战利品中获得下品灵石 ×{reward}。"
    if action == "spar" and result == "victory":
        bonus = round(2 * opportunity_multiplier(player), 1)
        deps._add_opportunity(player, bonus)
        summary += f" 印证所学使机缘 +{bonus}。"
    return summary


def _known_npc_encounter_target(
    deps: EncounterActionDependencies, game: GameState, settings: dict[str, Any], rng: random.Random,
) -> dict[str, Any] | None:
    player = game.player
    config = WORLD_SYSTEMS["faction_conflict"]
    protected = deps._player_protected_npc_ids(game)
    candidates: list[tuple[SectNpc, str | None, bool]] = [
        (npc, None, False) for npc in [*game.world_npcs.values(), *game.notable_npcs.values()]
        if npc.alive and npc.world == player.world and npc.id not in protected
    ]
    for sect_id, sect in game.sects.items():
        candidates.extend(
            (npc, sect_id, False) for npc in sect.npcs
            if npc.alive and npc.world == player.world and npc.id not in protected
        )
    for cached in game.encounter_npc_cache:
        raw = cached.get("npc", {})
        if raw.get("alive", True) and raw.get("world") == player.world and str(raw.get("id", "")) not in protected:
            candidates.append((SectNpc.from_dict(raw), None, True))
    known_chance = float(config["world_npc_encounter_chance"])
    if player.faction_id:
        known_chance += float(config["sect_npc_encounter_chance"])
    if game.encounter_npc_cache:
        known_chance += min(0.18, len(game.encounter_npc_cache) * 0.005)
    if not candidates or rng.random() >= known_chance:
        return None
    weights = [
        (3.5 if npc.notorious else 1.0) * encounter_weight(
            str(game.race_relations.get(race_pair(deps._player_allegiance_race(player), npc.race), {}).get("status", "neutral")),
            float(game.race_relations.get(race_pair(deps._player_allegiance_race(player), npc.race), {}).get("affinity", 0)),
        ) if deps._world_supports(player.world, "races") and npc.race != deps._player_allegiance_race(player) else 1.25
        for npc, _, _ in candidates
    ]
    npc, faction_id, from_cache = rng.choices(candidates, weights=weights, k=1)[0]
    if from_cache:
        cached = next(row for row in game.encounter_npc_cache if row.get("id") == npc.id)
        cached["seen_count"] = int(cached.get("seen_count", 1)) + 1
        cached["last_seen_age"] = player.age
        npc = deps._promote_cached_npc(game, npc.id, "再度相逢") or npc
    npc.encountered_player = True
    deps._tianji_observe_npc(game, npc.id)
    perception = deps._npc_cultivation_perception(game, npc, True)
    visible = perception["realm_name"] != "无法看清"
    race_definition = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
    target = {
        "target_name": npc.name, "target_power": deps._npc_power(npc), "primary_power": deps._npc_power(npc),
        "target_power_display": perception["display_power"] or deps._npc_power(npc),
        "target_expected_power": expected_combat_power(npc.realm_index, npc.layer),
        "target_realm_index": npc.realm_index, "target_layer": npc.layer,
        "target_realm_visible": visible,
        "target_realm_display": perception["realm_name"],
        "combat_type": "cultivator", "race": npc.race,
        "race_name": race_definition["name"], "race_description": race_definition["description"],
        "world": npc.world, "npc_id": npc.id, "faction_id": faction_id, "path": npc.path,
        "treasure_item_id": npc.treasure_item_id,
        "treasure_rumored": rng.random() < float(config["treasure_rumor_chance"]),
        "notorious": npc.notorious, "notoriety": npc.notoriety,
    }
    target = deps._add_enemy_party(target, settings, rng)
    deps._tianji_preview_npc_power(game, target)
    return target
