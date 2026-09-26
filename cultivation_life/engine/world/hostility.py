from __future__ import annotations

import random
from typing import Any
from ...content_registry import (
    ACTIONS,
    FACTION_DEFINITIONS,
    ITEM_CATALOG,
    PATH_NAMES,
    REALMS,
    RACE_DEFINITIONS,
    WORLD_SYSTEMS,
)
from ...models import GameState, HistoryRecord, Player, SectNpc
from ...system.npc_system import npc_team_combat_power
from ...rules import add_item
from ...world_state import race_pair
from ..dependencies import HostilityDependencies


def _hostility_key(kind: str, entity_id: str) -> str:
    return f"{kind}:{entity_id}"


def _maybe_wanted_encounter(deps: HostilityDependencies, game: GameState, rng: random.Random) -> bool:
    player = game.player
    config = WORLD_SYSTEMS["faction_conflict"]
    coalition_threshold = float(
        config["demonic_coalition_fame_threshold"]
        if player.path == "demonic" else config["coalition_fame_threshold"]
    )
    key = deps._hostility_key("world", player.world)
    subdued_flag = f"world_coalition_subdued:{player.world}"
    if subdued_flag in player.story_flags:
        # “全界”不是会重建组织结构的实体；一旦被玩家压服，本界不能
        # 仅因威名仍高就立即重发同一份围杀令。
        player.hostility[key] = 0.0
    else:
        amnesty_fame = deps._world_coalition_amnesty_fame(player, player.world)
        issue_threshold = max(coalition_threshold, amnesty_fame)
        if player.fame > issue_threshold:
            player.hostility[key] = max(
                player.hostility.get(key, 0),
                player.fame - issue_threshold + float(config["wanted_threshold"]),
            )
    hostiles: list[tuple[str, float]] = []
    for key, value in list(player.hostility.items()):
        if value <= float(config["wanted_threshold"]):
            continue
        player.milestones["became_wanted_target"] = 1
        state = deps._hostility_entity_state(game, key)
        if state["status"] == "inactive":
            continue
        if state["status"] == "friendly":
            player.hostility[key] = 0.0
            continue
        if state["status"] == "fallen":
            deps._queue_wanted_settlement(game, key, state, rng, fallen=True)
            return True
        if (
            deps._player_battle_power(game) >= float(state["power"])
            or int(state["max_realm"]) <= deps._actual_player_realm(player)[0]
        ):
            deps._queue_wanted_settlement(game, key, state, rng, fallen=False)
            return True
        if not deps._revenge_ready(game, "wanted", key):
            continue
        hostiles.append((key, value))
    if not hostiles:
        return False
    chance = min(0.92, float(config["encounter_base_chance"]) + max(value for _, value in hostiles) * float(config["encounter_hostility_scale"]))
    if rng.random() >= chance:
        return False
    key, hostility = rng.choices(hostiles, weights=[value for _, value in hostiles], k=1)[0]
    kind, entity_id = key.split(":", 1)
    target = deps._wanted_target(game, kind, entity_id, hostility, rng)
    deps._cache_encounter_target(game, target, rng)
    event = deps.events_by_id["EVT_WANTED_ENCOUNTER_001"]
    game.pending_event = deps._instantiate_event(event, game, rng)
    game.pending_event["runtime"] = {"hostility_key": key, "hostility": hostility, "target": target}
    game.pending_event["body"] = game.pending_event["body"].replace("{pursuer}", deps._hostility_name(key, game))
    if len(target.get("members", [])) > 1:
        game.pending_event["body"] += f" 此次追兵共有{len(target['members'])}人，合计战斗力约{target['target_power']:.0f}。"
    interval = deps._record_revenge_trigger(game, "wanted", key)
    game.pending_event["runtime"]["revenge_cooldown_units"] = interval
    return True


def _world_coalition_amnesty_fame(player: Player, world: str) -> float:
    prefix = f"world_coalition_amnesty:{world}:"
    values = []
    for flag in player.story_flags:
        if not flag.startswith(prefix):
            continue
        try:
            values.append(float(flag[len(prefix):]))
        except ValueError:
            continue
    return max(values, default=0.0)


def _record_world_coalition_amnesty(player: Player, world: str) -> None:
    prefix = f"world_coalition_amnesty:{world}:"
    player.story_flags = [flag for flag in player.story_flags if not flag.startswith(prefix)]
    player.story_flags.append(f"{prefix}{max(0.0, player.fame):.1f}")


def _player_protected_npc_ids(deps: HostilityDependencies, game: GameState) -> set[str]:
    player = game.player
    protected = {
        str(row.get("id")) for row in [
            player.master, player.dao_companion, *player.dao_friends,
            *player.concubines, *player.disciples,
        ] if row and row.get("id")
    }
    own_sect = game.sects.get(player.faction_id or "")
    if own_sect and not own_sect.extinct:
        protected.update(npc.id for npc in deps._sect_members(game, own_sect) if npc.alive)
    if game.family and not game.family.extinct:
        protected.update(npc.id for npc in game.family.npcs if npc.alive)
    protected.update(deps._retaliatory_relationship_ids(game))
    return protected


def _hostility_entity_members(deps: HostilityDependencies, game: GameState, kind: str, entity_id: str) -> list[SectNpc]:
    world = game.player.world
    if kind in {"sect", "family"}:
        entity = game.sects.get(entity_id)
        if entity is None and game.family and game.family.id == entity_id:
            entity = game.family
        return [
            npc for npc in deps._sect_members(game, entity)
            if npc.alive and npc.world == world
        ] if entity else []
    people = list({npc.id:npc for npc in deps._all_world_npcs(game)}.values())
    if kind == "race":
        return [npc for npc in people if npc.alive and npc.world == world and npc.race == entity_id]
    if kind == "world":
        return [npc for npc in people if npc.alive and npc.world == world]
    return []


def _hostility_entity_state(deps: HostilityDependencies, game: GameState, key: str) -> dict[str, Any]:
    kind, entity_id = key.split(":", 1)
    player = game.player
    if kind == "world" and entity_id != player.world:
        return {"status":"inactive"}
    if kind == "race" and (
        not deps._world_supports(player.world, "races")
        or player.world not in RACE_DEFINITIONS.get(entity_id, {}).get("worlds", [])
    ):
        return {"status":"inactive"}
    entity = None
    if kind in {"sect", "family"}:
        entity = game.sects.get(entity_id)
        if entity is None and game.family and game.family.id == entity_id:
            entity = game.family
        if entity and entity.world != player.world:
            return {"status":"inactive"}
    own_entity = (
        (kind == "sect" and entity_id == player.faction_id)
        or (kind == "family" and game.family and entity_id == game.family.id)
        or (kind == "race" and entity_id == deps._player_allegiance_race(player))
    )
    if own_entity:
        return {"status":"friendly"}
    raw_members = deps._hostility_entity_members(game, kind, entity_id)
    if (entity and entity.extinct) or not raw_members:
        return {"status":"fallen", "kind":kind, "entity_id":entity_id, "members":[]}
    members = [npc for npc in raw_members if npc.id not in deps._player_protected_npc_ids(game)]
    if not members:
        return {"status":"friendly"}
    powers = sorted((deps._npc_power(npc) for npc in members), reverse=True)[:5]
    return {
        "status":"active", "kind":kind, "entity_id":entity_id, "members":members,
        "power":sum(powers), "max_realm":max(npc.realm_index for npc in members),
    }


def _queue_wanted_settlement(
    deps: HostilityDependencies, game: GameState, key: str, state: dict[str, Any], rng: random.Random, *, fallen: bool,
) -> None:
    event_id = "EVT_POWER_FALL_001" if fallen else "EVT_WANTED_NEGOTIATION_001"
    event = deps._instantiate_event(deps.events_by_id[event_id], game, rng)
    name = deps._hostility_name(key, game)
    event["body"] = event["body"].replace("{pursuer}", name)
    event["runtime"] = {
        "hostility_key":key, "kind":state.get("kind", key.split(":", 1)[0]),
        "entity_id":state.get("entity_id", key.split(":", 1)[1]), "entity_name":name,
        "member_ids":[npc.id for npc in state.get("members", [])],
        "power":round(float(state.get("power", 0)), 1),
    }
    if fallen:
        titles = {"sect":"宗门的陨落", "family":"家族的陨落", "race":"种族势力的陨落", "world":"围杀令的陨落"}
        event["title"] = titles.get(event["runtime"]["kind"], "势力的陨落")
        game.player.hostility[key] = 0.0
    else:
        kind = event["runtime"]["kind"]
        own_sect = game.sects.get(game.player.faction_id or "")
        for choice in event["choices"]:
            if choice["id"] == "dissolve" and kind not in {"sect", "family"}:
                choice["enabled"] = False
                choice["disabled_reason"] = "种族与全界势力不能以解散宗门的方式处置"
            if choice["id"] == "sect_vassal" and (not own_sect or kind not in {"sect", "family"}):
                choice["enabled"] = False
                choice["disabled_reason"] = "需要拥有当前宗门，且谈判对象必须是宗门或家族"
    game.pending_event = event


def _resolve_wanted_settlement(
    deps: HostilityDependencies, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random,
) -> tuple[str, str]:
    runtime = pending.get("runtime", {})
    key = str(runtime.get("hostility_key", ""))
    if not key or ":" not in key:
        raise ValueError("议和对象已经不存在")
    kind = str(runtime.get("kind", key.split(":", 1)[0]))
    entity_id = str(runtime.get("entity_id", key.split(":", 1)[1]))
    name = str(runtime.get("entity_name", deps._hostility_name(key, game)))
    game.player.hostility[key] = 0.0
    if kind == "world":
        subdued_flag = f"world_coalition_subdued:{entity_id}"
        if subdued_flag not in game.player.story_flags:
            game.player.story_flags.append(subdued_flag)
    if mode == "fallen":
        return "pursuit_ended", f"{name}已经覆灭，针对你的追杀与通缉至此自动终止。"

    members = deps._hostility_entity_members(game, kind, entity_id)
    target = max(members, key=deps._npc_power, default=None)
    if mode == "compensation":
        amount = max(500, int(max(1.0, float(runtime.get("power", 1))) ** 0.5) * 80)
        add_item(game.player, "spirit_stone", amount)
        return "compensated", f"{name}交出下品灵石 ×{amount}作为巨额赔偿，并撤销全部追杀令。"
    if mode == "dissolve":
        entity = game.sects.get(entity_id)
        if entity is None and game.family and game.family.id == entity_id:
            entity = game.family
        if not entity or kind not in {"sect", "family"}:
            raise ValueError("该类势力不能就地解散")
        entity.extinct = True
        game.player.milestones["became_wanted_target"] = 1
        game.player.milestones["dissolved_wanted_power"] = 1
        deps._record_former_jailer_dissolved(game.player, kind, entity_id)
        for npc in members:
            npc.faction_id = None
            game.notable_npcs.setdefault(npc.id, npc)
        return "dissolved", f"你勒令{name}撤下门庭、解散传承；幸存者各自散去，旧通缉令失效。"
    if mode in {"personal_vassal", "sect_vassal"}:
        own_sect = game.sects.get(game.player.faction_id or "")
        if mode == "sect_vassal" and (not own_sect or kind not in {"sect", "family"}):
            raise ValueError("当前条件无法将对方纳为本宗附庸")
        if mode == "sect_vassal" and own_sect:
            relation = game.sect_relations.setdefault(
                race_pair(own_sect.id, entity_id), {"affinity":0.0, "since_age":game.player.age},
            )
            relation.update(status="vassal", affinity=70.0, since_age=game.player.age,
                            overlord=own_sect.id, subject=entity_id)
            return "sect_vassal", f"{name}交出外交与征召权，成为{own_sect.name}的附庸。"
        flag = f"personal_vassal:{kind}:{entity_id}"
        if flag not in game.player.story_flags:
            game.player.story_flags.append(flag)
        return "personal_vassal", f"{name}向你本人奉上臣服契约，承诺不再追杀并听候你的号令。"
    if mode == "hostages":
        amount = max(200, int(max(1.0, float(runtime.get("power", 1))) ** 0.5) * 35)
        add_item(game.player, "spirit_stone", amount)
        if target:
            game.player.prisoners.append({
                "id":target.id, "npc_id":target.id, "name":target.name,
                "realm_index":target.realm_index, "layer":target.layer,
                "realm_name":deps._npc_realm_name(target), "path":target.path,
                "path_name":PATH_NAMES.get(target.path, target.path), "race":target.race,
                "affinity":-80.0, "combat_power":round(deps._npc_power(target), 1),
                "main_technique_id":deps._default_npc_main_technique(target),
                "captured_age":game.player.age, "source":f"settlement:{kind}",
            })
            target.alive = False
            target.death_reason = f"被{game.player.name}扣作议和人质"
            return "hostages", f"{name}交出灵石 ×{amount}，并将最强者{target.name}交给你作为人质。"
        return "hostages", f"{name}已无强者可交，只得献上灵石 ×{amount}并永远撤销追杀。"
    raise ValueError("未知议和条件")


def _wanted_target(
    deps: HostilityDependencies, game: GameState, kind: str, entity_id: str, hostility: float, rng: random.Random,
) -> dict[str, Any]:
    player = game.player
    desired_realm = min(8, player.realm_index + max(0, int(hostility // 45)))
    candidates = [
        npc for npc in deps._hostility_entity_members(game, kind, entity_id)
        if npc.id not in deps._player_protected_npc_ids(game) and npc.realm_index >= player.realm_index
    ]
    if candidates:
        candidates.sort(key=lambda npc: (abs(npc.realm_index - desired_realm), -npc.realm_index, -npc.layer))
        npc = candidates[0]
        race_def = RACE_DEFINITIONS.get(npc.race, RACE_DEFINITIONS["human"])
        target = {
            "target_name": npc.name, "target_power": deps._npc_power(npc), "primary_power": deps._npc_power(npc),
            "target_realm_index": npc.realm_index, "target_layer": npc.layer,
            "target_realm_visible": npc.realm_index <= player.realm_index + 1,
            "target_realm_display": deps._npc_realm_name(npc) if npc.realm_index <= player.realm_index + 1 else "无法看清",
            "combat_type": "cultivator", "race": npc.race, "race_name": race_def["name"],
            "race_description": race_def["description"], "world": player.world,
            "npc_id": npc.id, "faction_id": deps._npc_faction_id(game, npc.id),
            "treasure_item_id": npc.treasure_item_id, "path":npc.path,
        }
        return deps._add_enemy_party(target, ACTIONS["slay"]["combat"], rng)
    race_id = entity_id if kind == "race" and entity_id in RACE_DEFINITIONS else "human"
    settings = dict(ACTIONS["slay"]["combat"])
    offset = desired_realm - player.realm_index
    settings["realm_offsets"] = [[offset, 1.0]]
    target = deps._generate_cultivator_target(player, "追缉使", settings, rng, game=game, forced_race=race_id)
    target["race"] = race_id
    target["race_name"] = RACE_DEFINITIONS[race_id]["name"]
    target["race_description"] = RACE_DEFINITIONS[race_id]["description"]
    target["faction_id"] = entity_id if kind in {"sect", "family"} else None
    for member in target.get("members", []):
        member["race"] = race_id
        member["faction_id"] = target.get("faction_id")
    return target


def _resolve_wanted_response(
    deps: HostilityDependencies, game: GameState, pending: dict[str, Any], response: str, rng: random.Random,
) -> tuple[str, str]:
    runtime = pending.get("runtime", {})
    key = str(runtime.get("hostility_key", "world:unknown"))
    target = runtime.get("target") or {}
    config = WORLD_SYSTEMS["faction_conflict"]
    if response == "fight":
        target["player_defending"] = True
        target["kill_karma"] = True
        target["non_story_combat"] = True
        result, summary = deps._combat(game, target, True, rng)
        game.player.hostility[key] = game.player.hostility.get(key, 0) + float(config["fight_hostility_gain"])
        if result == "defeat" and game.player.alive:
            custody = deps._imprison_or_execute(game, key, rng)
            summary += " " + custody
        return result, summary
    if response == "surrender":
        return "surrendered", deps._imprison_or_execute(game, key, rng, surrendered=True)
    if response == "escape":
        own_power = deps._player_battle_power(game)
        chance = max(0.08, min(0.8, 0.22 + own_power / max(1.0, float(target.get("target_power", own_power))) * 0.25))
        game.player.hostility[key] = game.player.hostility.get(key, 0) + float(config["escape_hostility_gain"])
        if rng.random() < chance:
            return "escaped", f"你付出代价甩脱追兵（成功率 {chance:.0%}），敌对值却进一步上升。"
        return "captured", f"突围失败（成功率 {chance:.0%}）。" + deps._imprison_or_execute(game, key, rng)
    raise ValueError("未知通缉应对方式")


def _imprison_or_execute(
    deps: HostilityDependencies, game: GameState, key: str, rng: random.Random, surrendered: bool = False,
) -> str:
    player = game.player
    config = WORLD_SYSTEMS["faction_conflict"]
    hostility = player.hostility.get(key, 0)
    execution_threshold = float(config["execution_threshold"])
    execution_chance = 0.0 if hostility < execution_threshold else min(0.9, 0.35 + (hostility - execution_threshold) / 100)
    if not surrendered:
        execution_chance = min(0.95, execution_chance + 0.12)
    if rng.random() < execution_chance:
        deps._die(game, f"落入{deps._hostility_name(key, game)}之手，被当场处决", "SYS_WANTED_EXECUTION")
        return f"敌对值 {hostility:.0f}，对方拒绝收押，将你当场处决。"
    low, high = config["prison_years"]
    years = rng.randint(int(low), int(high)) + min(8, int(hostility // 35))
    player.imprisonment = {
        "key": key, "name": deps._hostility_name(key, game), "remaining_years": years,
        "captured_age": player.age, "hostility": round(hostility, 1),
        "sentence_years": years,
        "hostility_reduction_per_year": max(4.0, hostility / max(1, years)),
    }
    deps._intrigue_record_player_prison(game, key, years)
    player.party = []
    return f"你被押入{deps._hostility_name(key, game)}大牢，刑期 {years} 年。"


def _hostility_name(deps: HostilityDependencies, key: str, game: GameState | None = None) -> str:
    kind, entity_id = key.split(":", 1)
    if kind in {"sect", "family"}:
        if game and entity_id in game.sects:
            return game.sects[entity_id].name
        if game and game.family and entity_id == game.family.id:
            return game.family.name
        return FACTION_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
    if kind == "race":
        return RACE_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
    return WORLD_SYSTEMS["world_names"].get(entity_id, entity_id) + "修仙界"


def _advance_player_bounties(deps: HostilityDependencies, game: GameState, rng: random.Random) -> None:
    active = [row for row in game.player_bounties if row.get("status") == "active" and row.get("world") == game.player.world]
    if not active:
        return
    bounty = active[0]
    bounty["attempts"] = int(bounty.get("attempts", 0)) + 1
    npc = deps._find_npc(game, str(bounty.get("target_id", "")))
    if not npc or not npc.alive:
        bounty["status"] = "closed"
        return
    authority = str(bounty.get("authority", ""))
    available = {row["id"]:row for row in deps._available_bounty_authorities(game)}
    if authority not in available:
        bounty["status"] = "suspended"
        return
    if authority == "race":
        allegiance_race = deps._player_allegiance_race(game.player)
        members = [
            member for member in [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]
            if member.alive and member.world == game.player.world and member.race == allegiance_race
        ]
    elif authority == "sect":
        sect = game.sects.get(game.player.faction_id or "")
        members = [member for member in sect.npcs if member.alive] if sect else []
    else:
        members = [member for member in game.family.npcs if member.alive] if game.family else []
    # 同一 NPC 可能同时出现在宗门与世界人物集合中，只允许出战一次；
    # 发布者本人不自动参战，通缉令依靠玩家实际掌握的同僚执行。
    unique_members = {
        member.id: member for member in members
        if member.id != npc.id and member.alive and member.world == game.player.world
    }
    candidates = sorted(unique_members.values(), key=deps._npc_power, reverse=True)
    if not candidates:
        game.history.append(HistoryRecord(
            "SYS_PLAYER_BOUNTY_NO_HUNTERS",1,game.player.age,"通缉无人可遣",npc.id,"delayed",
            f"{bounty.get('issuer_name','麾下势力')}暂时没有可跨界执行追杀的弟子或同僚，通缉令仍然有效。",
            {"bounty_id":bounty["id"],"attempts":bounty["attempts"]},["system","wanted","player_order",f"world:{npc.world}"],
        ))
        return

    # 每个行动单位派出一至三人。优先从最强的五人中抽调，兼顾势力会认真
    # 执行命令与同一位高层不会机械地永远出战两种表现。
    pool = candidates[: min(5, len(candidates))]
    team_size = min(len(pool), rng.randint(1, 3))
    hunters = rng.sample(pool, team_size)
    hunter_powers = {member.id: deps._npc_power(member) for member in hunters}
    pursuit_power = npc_team_combat_power(hunter_powers.values())
    target_power = max(1.0, deps._npc_power(npc))
    ratio = pursuit_power / target_power
    victory_chance = max(0.06, min(0.94, 0.18 + ratio * 0.34))
    hunter_names = "、".join(member.name for member in hunters)

    if rng.random() < victory_chance:
        target_threshold = float(REALMS[npc.realm_index].kill_threshold)
        can_kill = ratio >= target_threshold
        killed = can_kill and rng.random() < min(0.92, 0.55 + (ratio - target_threshold) * 0.12)
        if killed:
            npc.alive = False
            npc.death_reason = f"被{bounty.get('issuer_name','麾下势力')}通缉后伏诛"
            bounty["status"] = "completed"
            bounty["completed_age"] = game.player.age
            reward_text = "其身上并无可入眼的重宝"
            if npc.treasure_item_id and not npc.treasure_looted:
                add_item(game.player, npc.treasure_item_id)
                npc.treasure_looted = True
                reward_text = f"其重宝《{ITEM_CATALOG[npc.treasure_item_id].name}》已交由你接收"
            for candidate_sect in game.sects.values():
                if any(member.id == npc.id for member in candidate_sect.npcs):
                    deps._check_sect_extinction(game, candidate_sect)
            game.history.append(HistoryRecord(
                "SYS_PLAYER_BOUNTY_COMPLETE",1,game.player.age,"通缉伏诛",npc.id,"completed",
                f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}），围杀{npc.name}（战力 {target_power:.0f}）；{reward_text}。",
                {"bounty_id":bounty["id"],"target_id":npc.id,"hunter_ids":[row.id for row in hunters],"pursuit_power":pursuit_power,"target_power":target_power},
                ["system","wanted","player_order",f"world:{npc.world}"],
            ))
            return
        npc.wounds = min(4, npc.wounds + (2 if ratio >= 1 else 1))
        for hunter in hunters:
            if ratio < 1.6 and rng.random() < 0.30:
                hunter.wounds = min(4, hunter.wounds + 1)
        game.history.append(HistoryRecord(
            "SYS_PLAYER_BOUNTY_TARGET_WOUNDED",1,game.player.age,"通缉重创",npc.id,"target_wounded",
            f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}）重创了{npc.name}（战力 {target_power:.0f}），但未满足击杀条件；通缉令继续执行。",
            {"bounty_id":bounty["id"],"hunter_ids":[row.id for row in hunters],"target_wounds":npc.wounds},
            ["system","wanted","player_order",f"world:{npc.world}"],
        ))
        return

    outcomes: list[str] = []
    for hunter in hunters:
        hunter_power = max(1.0, hunter_powers[hunter.id])
        counter_ratio = target_power / hunter_power
        kill_threshold = float(REALMS[hunter.realm_index].kill_threshold)
        if counter_ratio >= kill_threshold and rng.random() < 0.55:
            hunter.alive = False
            hunter.death_reason = f"执行对{npc.name}的通缉令时反遭灭杀"
            outcomes.append(f"{hunter.name}阵亡")
            for candidate_sect in game.sects.values():
                if any(member.id == hunter.id for member in candidate_sect.npcs):
                    deps._check_sect_extinction(game, candidate_sect)
        elif rng.random() < min(0.85, 0.38 + max(0.0, counter_ratio - 1) * 0.18):
            hunter.wounds = min(4, hunter.wounds + 2)
            outcomes.append(f"{hunter.name}重伤遁回")
        else:
            outcomes.append(f"{hunter.name}及时脱身")
    if ratio >= 0.65:
        npc.wounds = min(4, npc.wounds + 1)
    game.history.append(HistoryRecord(
        "SYS_PLAYER_BOUNTY_COUNTERED",1,game.player.age,"通缉反噬",npc.id,"hunters_defeated",
        f"{hunter_names}组成{team_size}人追缉队（结算战力 {pursuit_power:.0f}）截住{npc.name}（战力 {target_power:.0f}），却被对方击退：{'、'.join(outcomes)}。通缉令仍然有效。",
        {"bounty_id":bounty["id"],"hunter_ids":[row.id for row in hunters],"outcomes":outcomes},
        ["system","wanted","player_order",f"world:{npc.world}"],
    ))
