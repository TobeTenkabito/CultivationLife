from __future__ import annotations

from ...npc_custody import is_free, retire_owned_people
from ...relationship_records import RelationshipRecord
from ...system.combat.npc_lifecycle import move_world

from ...system.path_modifiers import modifier

import random
from typing import Any
from ...content_registry import REALMS, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord
from ...rules import max_hp, max_mp, opportunity_required, public_player, qi_level
from ...runtime import decode_rng, encode_rng, now_iso
from ..dependencies import WorldTravelDependencies


def _handover_faction_for_ascension(deps: WorldTravelDependencies, game: GameState) -> dict[str, Any] | None:
    """Remove the player from a lower-world faction and leave a real NPC ruler."""
    player = game.player
    sect = game.sects.get(player.faction_id or "")
    if not sect or sect.extinct:
        return None
    record = deps._intrigue_state(game).get("factions", {}).get(deps._intrigue_key("sect", sect.id), {})
    controlled = bool(sect.founded_by_player or record.get("controller_id") == "player")
    plan = deps._intrigue_state(game).setdefault("succession_plans", {}).get(sect.id, {})
    successor_id = str(plan.get("successor_id", "")) if plan.get("arranged") else ""
    members = [npc for npc in deps._sect_members(game, sect) if npc.alive and npc.world == sect.world]
    successor = next((npc for npc in members if npc.id == successor_id), None)
    if not successor:
        successor = max(members, key=lambda npc: (npc.realm_index, npc.layer, -npc.age), default=None)
    if controlled:
        was_founder = bool(sect.founded_by_player and sect.founder_player_id == game.id)
        arranged = bool(plan.get("arranged") and successor)
        sect.founded_by_player = False
        sect.founded_by_npc = bool(successor)
        sect.founder_npc_id = successor.id if successor else None
        # Only an explicitly arranged succession preserves the historical
        # founder link required by the later 寻觅祖师 event.
        sect.founder_player_id = game.id if was_founder and arranged else None
        if record:
            record["controller_id"] = successor.id if successor else None
            positions = record.setdefault("positions", {})
            if positions:
                leader = next(iter(deps._intrigue_position_specs("sect")), "")
                if leader:
                    positions[leader] = successor.id if successor else None
        plan.update({
            "arranged": arranged, "eligible_return": bool(was_founder and arranged),
            "successor_id": successor.id if successor else None,
            "origin_world": sect.world, "ascended_age": player.age,
        })
        deps._intrigue_state(game).setdefault("succession_plans", {})[sect.id] = plan
    return {
        "sect_id": sect.id, "sect_name": sect.name, "controlled": controlled,
        "arranged": bool(plan.get("arranged")),
        "successor_name": successor.name if successor else None,
    }


def _prepare_permanent_world_transition(
    deps: WorldTravelDependencies, game: GameState, *, keep_companion: bool = False,
    keep_friend_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Apply the shared, irreversible cleanup required by every ascension."""
    player = game.player
    keep_friend_ids = keep_friend_ids or set()
    handover = deps._handover_faction_for_ascension(game)
    removed = {
        "puppets": len(player.puppets), "prisoners": len(player.prisoners),
        "concubines": len(player.concubines),
    }
    player.puppets = []
    retire_owned_people(game)
    player.prisoners = []
    player.concubines = []
    player.concubine_status = None
    player.concubine_rejection_aftermath = []
    player.master = None
    player.disciples = []
    player.disciple_requests = []
    player.relationship_attempts = []
    player.dao_friends = [
        row for row in player.dao_friends if str(row.get("id")) in keep_friend_ids
    ]
    if not keep_companion:
        player.dao_companion = None
    player.joint_spirit_crossing = None
    player.joint_friend_crossing = []
    player.party = []
    player.faction_id = None
    player.faction_join_age = None
    player.faction_contribution = 0
    player.faction_reward_preference = None
    player.allegiance_race = player.lineage_race or player.race
    player.fame = 0.0
    if player.imprisonment:
        player.imprisonment = None
        deps._intrigue_sync_player_prison(game)
    for record in deps._intrigue_state(game).get("factions", {}).values():
        record["guests"] = [
            row for row in record.get("guests", []) if row.get("npc_id") != "player"
        ]
    deps._intrigue_state(game)["pending_guest_invitation"] = None
    return {"removed": removed, "faction_handover": handover}


def _resolve_selected_ascension_entourage(
    deps: WorldTravelDependencies, game: GameState, destination: str, rng: random.Random,
) -> tuple[bool, set[str], list[str], list[str]]:
    """Resolve explicitly invited partner/friends before permanent cleanup."""
    player = game.player
    companion = player.dao_companion
    companion_kept = bool(
        companion and player.joint_spirit_crossing
        and str(companion.get("id")) == str(player.joint_spirit_crossing.get("id"))
        and not player.joint_spirit_crossing.get("declined")
        and deps._party_crossing_candidate(game, str(companion.get("id", "")))
    )
    if companion_kept and companion:
        move_world(companion, destination, player.age, WORLD_SYSTEMS.get("transcendent_combat", {}))
        npc = deps._find_npc(game, str(companion.get("id", "")))
        if npc:
            if not isinstance(companion, RelationshipRecord):
                move_world(npc, destination, player.age, WORLD_SYSTEMS.get("transcendent_combat", {}))
            npc.departed_age = npc.age
            npc.departure_reason = f"与{player.name}共同飞升{WORLD_SYSTEMS['world_names'][destination]}"
    survivors: set[str] = set()
    survivor_names: list[str] = []
    fallen_names: list[str] = []
    chance = float(WORLD_SYSTEMS["relationship"]["friend_crossing_survival_chance"])
    selected = {str(row.get("id", "")) for row in player.joint_friend_crossing}
    for npc_id in selected:
        if not any(str(row.get("id")) == npc_id for row in player.party):
            continue
        candidate = deps._party_crossing_candidate(game, npc_id)
        friend = next((row for row in player.dao_friends if str(row.get("id")) == npc_id), None)
        if not candidate or not friend:
            continue
        npc = deps._find_npc(game, npc_id)
        if rng.random() < chance:
            move_world(friend, destination, player.age, WORLD_SYSTEMS.get("transcendent_combat", {}))
            survivors.add(npc_id)
            survivor_names.append(str(friend.get("name", candidate["name"])))
            if npc:
                if not isinstance(friend, RelationshipRecord):
                    move_world(npc, destination, player.age, WORLD_SYSTEMS.get("transcendent_combat", {}))
                npc.departed_age = npc.age
                npc.departure_reason = f"与{player.name}共同飞升{WORLD_SYSTEMS['world_names'][destination]}"
        else:
            friend["alive"] = False
            friend["death_reason"] = "飞升界壁时迷失于空间风暴"
            fallen_names.append(str(friend.get("name", candidate["name"])))
            if npc:
                npc.alive = False
                npc.death_reason = "飞升界壁时迷失于空间风暴"
    return companion_kept, survivors, survivor_names, fallen_names


def _maybe_founder_return_event(deps: WorldTravelDependencies, game: GameState, rng: random.Random) -> bool:
    if game.pending_event or game.player.faction_id:
        return False
    plans = deps._intrigue_state(game).get("succession_plans", {})
    candidates = [
        (sect_id, plan) for sect_id, plan in plans.items()
        if plan.get("eligible_return")
        and (sect := game.sects.get(sect_id)) is not None
        and not sect.extinct and sect.world == game.player.world
        and sect.founder_player_id == game.id
    ]
    if not candidates or rng.random() >= 0.5:
        return False
    sect_id, _ = candidates[0]
    sect = game.sects[sect_id]
    event = deps._instantiate_event(deps.events_by_id["EVT_FOUNDER_RETURN_001"], game, rng)
    event["body"] = str(event.get("body", "")).replace("{sect_name}", sect.name)
    event["runtime"] = {"sect_id": sect.id, "sect_name": sect.name}
    game.pending_event = event
    return True


def begin_spirit_crossing(deps: WorldTravelDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if player.sealed_cultivation:
        raise ValueError("当前身处下界且真实道果处于封印中，只能重返原上界")
    if player.path == "demonic":
        if player.imprisonment:
            raise ValueError("服刑期间只能尝试人界偷渡，无法走魔界飞升通道")
        return deps._complete_demonic_ascension(game)
    if player.world != "human":
        raise ValueError("你已经脱离人界")
    if player.realm_index != 5 or player.layer > 3:
        raise ValueError("只有达到人界化神初期，方能尝试偷渡灵界")
    if player.spirit_realm_attempted:
        raise ValueError("偷渡灵界的机会只有一次")
    rng = decode_rng(game.seed, game.rng_state)
    player.spirit_realm_attempted = True
    companion = player.dao_companion
    can_cross_together = bool(
        companion and is_free(companion)
        and companion.get("world", player.world) == "human"
        and int(companion.get("realm_index", -1)) == 5
        and int(companion.get("layer", 99)) <= 3
    )
    companion_selected = bool(
        can_cross_together
        and (
            player.joint_spirit_crossing is None
            or (
                str(player.joint_spirit_crossing.get("id")) == str(companion.get("id"))
                and not player.joint_spirit_crossing.get("declined")
            )
        )
    )
    player.joint_spirit_crossing = (
        {"id": companion["id"], "name": companion["name"]} if companion_selected else None
    )
    selected_ids = {str(entry.get("id")) for entry in player.joint_friend_crossing}
    player.joint_friend_crossing = [
        candidate for npc_id in selected_ids
        if (candidate := deps._party_crossing_candidate(game, npc_id)) is not None
        and any(str(member.get("id")) == npc_id for member in player.party)
    ]
    destination = deps._ascension_destination(player.path, player)
    destination_name = WORLD_SYSTEMS["world_names"][destination]
    event = deps.events_by_id["EVT_SPIRIT_CROSSING_001"]
    game.pending_event = deps._instantiate_event(event, game, rng)
    if destination != "spirit":
        game.pending_event["title"] = f"偷渡{destination_name}"
        game.pending_event["body"] = str(game.pending_event.get("body", "")).replace("灵界", destination_name)
    game.history.append(HistoryRecord(
        "SYS_SPIRIT_CROSSING_BEGIN", 1, player.age, "破界之举", None, "started",
        f"你已锁定空间乱流，踏出后便再无回头路。偷渡{destination_name}的机会只有这一次。"
        + (f" {companion['name']}接受了你的邀请，将与你共同闯过界壁。" if companion_selected else "")
        + (f" 你还邀上了{len(player.joint_friend_crossing)}位同境队友；他们没有道侣契约庇护，极可能陨落。" if player.joint_friend_crossing else ""),
        {"spirit_realm_attempted": [False, True]}, ["system", "ascension", "milestone"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def begin_celestial_ascension(deps: WorldTravelDependencies, game_id: str) -> dict[str, Any]:
    """Start the dedicated nine-stage Mahayana ascension trial."""
    game = deps._load(game_id)
    player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event or game.active_trial:
        raise ValueError("请先处理当前事件")
    if player.imprisonment:
        raise ValueError("身陷牢狱时无法渡劫飞升")
    if player.sealed_cultivation:
        raise ValueError("真实道果正受下界压制，不能在封印状态下飞升")
    if player.world != "hell" and player.path not in {"dao", "buddhist", "confucian"}:
        raise ValueError("当前道统尚未开放飞升仙界路线")
    if not modifier(player, "ascension_source", player.world == "spirit") or player.realm_index != 8 or player.layer != REALMS[8].layers:
        raise ValueError("须身处灵界或地狱界，且本界最高大境界九层圆满，方可渡劫飞升")
    if player.opportunity < opportunity_required(player):
        raise ValueError("大乘九层机缘尚未圆满")
    destination = modifier(player, "ascension_destination", "celestial")
    event_ids = modifier(player, "ascension_events", [f"EVT_CELESTIAL_ASCENSION_{index:03d}" for index in range(1, 10)])
    rng = decode_rng(game.seed, game.rng_state)
    game.active_trial = {
        "kind":"celestial_ascension", "source_realm":8, "target_realm":9,
        "target_layer":1, "major":True, "old_label":public_player(player)["realm_name"],
        "step_index":0, "event_ids":event_ids, "lethal":True,
        "destination": destination,
    }
    game.pending_event = deps._instantiate_event(deps.events_by_id[event_ids[0]], game, rng)
    game.history.append(HistoryRecord(
        "SYS_CELESTIAL_ASCENSION_BEGIN", 1, player.age, "渡劫飞升", None, "started",
        f"你以大乘九层圆满道果叩问{WORLD_SYSTEMS['world_names'][destination]}之门；九重判定已经开始，其中第三、六、九关皆为劫雷。",
        {"trial_steps":9}, ["system", "ascension", "celestial", "milestone"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def begin_asura_ascension(deps: WorldTravelDependencies, game_id: str) -> dict[str, Any]:
    """Start the nine-stage demonic ascension from the True Demon Realm."""
    game = deps._load(game_id)
    player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event or game.active_trial:
        raise ValueError("请先处理当前事件")
    if player.imprisonment:
        raise ValueError("身陷牢狱时无法渡劫飞升")
    if player.sealed_cultivation:
        raise ValueError("真实道果正受下界压制，不能在封印状态下飞升")
    if player.path != "demonic":
        raise ValueError("只有魔修可以飞升修罗界")
    if player.world != "true_demon" or player.realm_index != 8 or player.layer != REALMS[8].layers:
        raise ValueError("只有身处真魔界且魔尊九层圆满，方可渡劫飞升")
    if player.opportunity < opportunity_required(player):
        raise ValueError("魔尊九层机缘尚未圆满")
    event_ids = [f"EVT_ASURA_ASCENSION_{index:03d}" for index in range(1, 10)]
    rng = decode_rng(game.seed, game.rng_state)
    game.active_trial = {
        "kind":"asura_ascension", "source_realm":8, "target_realm":9,
        "target_layer":1, "major":True, "old_label":public_player(player)["realm_name"],
        "step_index":0, "event_ids":event_ids, "lethal":True,
    }
    game.pending_event = deps._instantiate_event(deps.events_by_id[event_ids[0]], game, rng)
    game.history.append(HistoryRecord(
        "SYS_ASURA_ASCENSION_BEGIN", 1, player.age, "九重修罗天魔劫", None, "started",
        "你以魔尊九层圆满道果叩问修罗天关；九重判定已经开始，第三、六、九关皆为修罗兵雷。",
        {"trial_steps":9}, ["system", "ascension", "asura", "demonic", "milestone"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _complete_demonic_ascension(deps: WorldTravelDependencies, game: GameState) -> dict[str, Any]:
    """魔界路线直接渡界；飞升真魔界时必须承受魔气纯度判定。"""
    player = game.player
    if player.world == "human" and player.realm_index == 5 and player.layer >= 3:
        destination = "demon"
    elif player.world == "demon" and player.realm_index == 5 and player.layer >= 1:
        destination = "true_demon"
        required_qi = int(WORLD_SYSTEMS["demonic_cultivation"]["true_demon_ascension_demon_qi_level"])
        current_qi = qi_level(player.qi_experience.get("demon", 0.0))
        if current_qi < required_qi:
            deps._die(
                game,
                f"魔气等级仅有 {current_qi} 级，未达飞升真魔界所需的 {required_qi} 级；肉身与元神在界壁魔潮中一同崩解",
                "SYS_TRUE_DEMON_ASCENSION_QI_DEATH",
            )
            game.updated_at = now_iso()
            deps.store.save(game)
            return deps.present(game)
    else:
        raise ValueError("当前境界尚未触及下一魔界的飞升门槛")
    origin = player.world
    old_fame = player.fame
    lost_puppets = len(player.puppets)
    rng = decode_rng(game.seed, game.rng_state)
    plan = deps._plan_world_transition(game, destination, reason="魔道飞升")
    entourage = deps._resolve_selected_ascension_entourage(game, destination, rng)
    companion_kept, friend_ids, friend_names, fallen_names = entourage
    deps._apply_world_transition(game, plan, entourage=entourage)
    player.awaiting_ascension = False
    player.awaiting_spirit_realm_crossing = False
    deps._ensure_market(game, rng)
    origin_name = WORLD_SYSTEMS["world_names"][origin]
    destination_name = WORLD_SYSTEMS["world_names"][destination]
    puppet_text = f" 受界壁排斥，{lost_puppets}具傀儡全部遗失。" if lost_puppets else ""
    entourage_text = (
        (f" 道侣与你一同抵达。" if companion_kept else "")
        + (f" 道友{'、'.join(friend_names)}成功同行。" if friend_names else "")
        + (f" 道友{'、'.join(fallen_names)}陨落于界壁。" if fallen_names else "")
    )
    game.history.append(HistoryRecord(
        "SYS_DEMONIC_ASCENSION", 1, player.age, f"{'平移' if plan.direction.value == 'lateral' else '飞升'}{destination_name}", destination, "ascended",
        f"你撕开{origin_name}界壁，降临{destination_name}。{puppet_text}{entourage_text}",
        {"world": [origin, destination], "lost_puppets": lost_puppets, "fame": [old_fame, 0]},
        ["system", "ascension", "demonic", "world:global"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def plan_public_crossing(game, destination, maps):
    player = game.player
    if not player.alive or game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法跨越界面")
    if (player.sealed_cultivation or {}).get("merchant_passage"):
        raise ValueError("逆灵通道的访客封印须经商盟通道返界解除")
    route = next((row for row in WORLD_SYSTEMS["world_transition_routes"]
                  if row.get("generic_cross_world") and row["enabled"] and row["source"] == player.world
                  and row["destination"] == destination), None)
    descending = route is not None
    if descending:
        if player.world == "celestial" and not player.immortal_power_converted:
            raise ValueError("仙灵力尚未完全转化，无法承受逆行界壁的消耗")
        profile = WORLD_SYSTEMS["world_profiles"][player.world]
        rules = WORLD_SYSTEMS["world_travel"]
        required = int(rules["celestial_required_realm"] if profile["tier"] >= 3 else rules["required_realm"])
        if player.realm_index < required:
            raise ValueError(f"只有达到{REALMS[required].name}境的修士才能重返对应下界")
    from ...system.world_transition_system import WorldTransitionRequest, TransitionMode, plan_world_transition
    mode = TransitionMode.SEALED_DESCENT if descending else TransitionMode.SEALED_RETURN
    request = WorldTransitionRequest(destination, mode, route["id"] if route else "sealed_return", "循原界壁往返")
    return plan_world_transition(game, request, WORLD_SYSTEMS, maps)


def cross_world(deps: WorldTravelDependencies, game_id: str, destination: str) -> dict[str, Any]:
    """Authorize the public reversible routes; progression is never a shortcut."""
    game = deps._load(game_id)
    player = game.player
    plan = plan_public_crossing(game, destination, deps.maps)
    descending = plan.mode.value == "sealed_descent"
    deps._apply_world_transition(game, plan)
    world_name = WORLD_SYSTEMS['world_names'][destination]
    summary = (f"你逆穿界壁重返{world_name}。天地法则将修为压至{REALMS[player.realm_index].name}{player.layer}层，真实道果仍在。"
               if descending else f"你再入{world_name}，界面压制尽去，被封存的道果与法力层次完全复原。")
    result = f"returned_{destination}"
    game.history.append(HistoryRecord(
        "SYS_CROSS_WORLD", 1, player.age, "跨界往返", destination, result, summary,
        {"world": player.world, "cultivation_suppressed": bool(player.sealed_cultivation), "direction": plan.direction.value},
        ["system", "world_crossing", "world:global"],
    ))
    rng = decode_rng(game.seed, game.rng_state)
    if descending:
        deps._maybe_founder_return_event(game, rng)
    deps._ensure_market(game, rng)
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
