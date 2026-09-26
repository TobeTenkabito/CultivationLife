from __future__ import annotations

from typing import Any
from ...content_registry import (
    FACTION_SYSTEMS,
    ITEM_CATALOG,
    MARKET_GOODS,
    TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from ...models import HistoryRecord
from ...rules import (
    add_item,
    can_practice_technique,
    can_player_practice_technique,
    learn_technique,
    opportunity_multiplier,
    opportunity_required,
    remove_item,
)
from ...runtime import decode_rng, encode_rng, now_iso
from ..dependencies import RelationshipActionDependencies


def dispatch_disciple(deps: RelationshipActionDependencies, game_id: str, target: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if not player.faction_id or player.realm_index < 4:
        raise ValueError("成为元婴期宗门股东后方可派遣弟子")
    if target not in {"item", "technique"}:
        raise ValueError("未知派遣目标")
    if player.last_disciple_dispatch_age == player.age:
        raise ValueError("本年度已经派遣过弟子")
    dispatch_cost = int(FACTION_SYSTEMS["disciple_dispatch_cost"])
    if player.faction_contribution < dispatch_cost:
        raise ValueError(f"派遣弟子需要 {dispatch_cost} 点宗门贡献")
    rng = decode_rng(game.seed, game.rng_state)
    player.faction_contribution -= dispatch_cost
    player.last_disciple_dispatch_age = player.age
    tier = deps._market_tier(player)
    pool = [
        entry for entry in MARKET_GOODS
        if entry["kind"] == target and entry["tier"] == tier
        and entry.get("world", "human") == player.world
    ]
    if target == "technique":
        pool = [
            entry for entry in pool
            if entry["content_id"] not in {known.id for known in player.known_techniques}
            and can_player_practice_technique(player, TECHNIQUE_CATALOG[entry["content_id"]].element)
        ]
    success = bool(pool) and rng.random() < float(FACTION_SYSTEMS["disciple_dispatch_success"])
    if success:
        found = rng.choice(pool)
        if target == "item":
            add_item(player, found["content_id"])
            found_name = ITEM_CATALOG[found["content_id"]].name
        else:
            technique = TECHNIQUE_CATALOG[found["content_id"]]
            learn_technique(player, technique)
            found_name = f"《{technique.name}》"
        result = "found"
        summary = f"你派出的弟子数月后归山，带回了{found_name}。宗门贡献 -{dispatch_cost}。"
    else:
        result = "empty_handed"
        summary = f"弟子循线查访数月，却未找到足以入眼的目标。宗门贡献 -{dispatch_cost}。"
    game.history.append(HistoryRecord(
        "SYS_DISCIPLE_DISPATCH", 1, player.age, "派遣弟子", target, result, summary,
        {"faction_contribution": -dispatch_cost}, ["system", "faction", "disciple"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def manage_faction_relationship(deps: RelationshipActionDependencies, game_id: str, npc_id: str, role: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if not player.faction_id:
        raise ValueError("只有加入宗门后才能直接向宗门 NPC 提出师徒请求")
    if role not in {"master", "disciple"}:
        raise ValueError("未知师徒关系类型")
    if any(str(entry.get("id")) == npc_id for entry in player.concubines):
        raise ValueError("侍妾不是道侣或师徒，必须先解除侍妾名分")
    sect = game.sects.get(player.faction_id)
    npc = next(
        (entry for entry in deps._sect_members(game, sect) if entry.id == npc_id and entry.alive),
        None,
    ) if sect and not sect.extinct else None
    if not npc:
        raise ValueError("该宗门人物不存在或已经陨落")
    attempt_key = f"{role}:{npc_id}"
    if attempt_key in player.relationship_attempts:
        raise ValueError("你已经向此人提出过同类请求")
    player_rank = (player.realm_index, player.layer)
    npc_rank = (npc.realm_index, npc.layer)
    max_disciples = int(WORLD_SYSTEMS["relationship"]["max_disciples"])
    if role == "master":
        if player.master:
            raise ValueError("你已经拜有师承")
        if npc_rank <= player_rank:
            raise ValueError("只能拜修为严格高于自己的修士为师")
    else:
        if len(player.disciples) + len(player.disciple_requests) >= max_disciples:
            raise ValueError(f"当前师徒系统最多记录{max_disciples}名弟子或待决拜师帖")
        if npc_rank >= player_rank:
            raise ValueError("只能收修为严格低于自己的修士为徒")
        if any(entry["id"] == npc_id for entry in player.disciples):
            raise ValueError("此人已经是你的弟子")

    rng = decode_rng(game.seed, game.rng_state)
    player.relationship_attempts.append(attempt_key)
    realm_gap = abs(player.realm_index - npc.realm_index)
    accept_chance = min(0.82, (0.28 + realm_gap * 0.10) if role == "master" else (0.62 + realm_gap * 0.06))
    accepted = rng.random() < accept_chance
    relation = deps._relationship_snapshot(
        npc.id, npc.name, npc.realm_index, npc.layer, player.faction_id,
        npc.age, npc.lifespan, npc.alive, npc.death_reason,
        spirit_root=npc.spirit_root, cultivation_progress=npc.cultivation_progress,
        path=npc.path, race=npc.race, world=npc.world,
    )
    if accepted and role == "master":
        player.master = relation
        summary = f"{npc.name}认可了你的心性与根基，正式收你为徒。"
        result = "master_accepted"
    elif accepted:
        player.disciples.append(relation)
        summary = f"{npc.name}愿执弟子礼，正式拜入你的门下。"
        result = "disciple_accepted"
    else:
        summary = f"{npc.name}拒绝了你的{'拜师' if role == 'master' else '收徒'}请求。"
        result = "rejected"
    game.history.append(HistoryRecord(
        "SYS_FACTION_RELATIONSHIP", 1, player.age, "师徒之请", npc_id, result, summary,
        {"npc_id": npc_id, "role": role, "accept_chance": round(accept_chance, 2)},
        ["system", "relationship", role],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def respond_disciple_request(deps: RelationshipActionDependencies, game_id: str, request_id: str, accept: bool) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    request = next((entry for entry in player.disciple_requests if entry.get("id") == request_id), None)
    if not request:
        raise ValueError("这份拜师帖已经不存在")
    if accept and not request.get("alive", True):
        raise ValueError("求道者已经陨落，无法再收入门下")
    max_disciples = int(WORLD_SYSTEMS["relationship"]["max_disciples"])
    if accept and len(player.disciples) >= max_disciples:
        raise ValueError(f"当前最多记录{max_disciples}名弟子")
    player.disciple_requests.remove(request)
    if accept:
        player.disciples.append(request)
        result = "disciple_accepted"
        summary = f"你亲自收下{request['name']}的拜师帖，正式将其收入门下。"
    else:
        result = "disciple_declined"
        summary = f"你退回了{request['name']}的拜师帖，此段师徒缘分就此作罢。"
    game.history.append(HistoryRecord(
        "SYS_DISCIPLE_REQUEST", 1, player.age, "拜师帖决断", request_id, result, summary,
        {"request_id": request_id, "accepted": bool(accept)}, ["system", "relationship", "disciple"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def request_from_master(deps: RelationshipActionDependencies, game_id: str, kind: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    master = player.master
    if not master:
        raise ValueError("你尚无师承")
    if not master.get("alive", True):
        raise ValueError("师父已经陨落，无法回应请求")
    if kind not in {"item", "technique"}:
        raise ValueError("未知索取类型")
    last_requests = master.setdefault("last_requests", {})
    if last_requests.get(kind) == player.age:
        raise ValueError("本年度已经向师父提出过这类请求")

    master_realm = int(master["realm_index"])
    if kind == "item":
        candidates = list(dict.fromkeys(
            entry["content_id"] for entry in MARKET_GOODS
            if entry["kind"] == "item" and int(entry["tier"]) <= max(1, master_realm)
            and entry.get("world", "human") == master.get("world", player.world)
        ))
    else:
        candidates = list(dict.fromkeys(
            entry["content_id"] for entry in MARKET_GOODS
            if entry["kind"] == "technique" and int(entry["tier"]) <= max(1, master_realm)
            and entry.get("world", "human") == master.get("world", player.world)
            and can_player_practice_technique(player, TECHNIQUE_CATALOG[entry["content_id"]].element)
            and all(known.id != entry["content_id"] for known in player.known_techniques)
        ))
    if not candidates:
        raise ValueError("师父手中已无适合你的新物品或功法")

    rng = decode_rng(game.seed, game.rng_state)
    last_requests[kind] = player.age
    chance = float(WORLD_SYSTEMS["relationship"]["master_request_acceptance"][kind])
    accepted = rng.random() < chance
    content_id: str | None = None
    if not accepted:
        result = "master_refused"
        summary = f"{master['name']}认为你不该过度依赖师门，拒绝了这次{'赐物' if kind == 'item' else '传功'}请求。"
    elif kind == "item":
        content_id = rng.choice(candidates)
        add_item(player, content_id)
        result = "master_gave_item"
        summary = f"{master['name']}应允所求，赐下{ITEM_CATALOG[content_id].name}一件。"
    else:
        content_id = rng.choice(candidates)
        learn_technique(player, TECHNIQUE_CATALOG[content_id])
        result = "master_taught_technique"
        summary = f"{master['name']}为你讲授《{TECHNIQUE_CATALOG[content_id].name}》，功法已收入已悟列表。"
    game.history.append(HistoryRecord(
        "SYS_MASTER_REQUEST", 1, player.age, "求取师门恩赐", kind, result, summary,
        {"kind": kind, "accept_chance": chance, "content_id": content_id},
        ["system", "relationship", "master"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def gift_disciple(deps: RelationshipActionDependencies, game_id: str, disciple_id: str, kind: str, content_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    disciple = next((entry for entry in player.disciples if entry.get("id") == disciple_id), None)
    if not disciple:
        raise ValueError("此人并非你的弟子")
    if not disciple.get("alive", True):
        raise ValueError("弟子已经陨落，无法接受赠予")
    if kind == "item":
        if content_id not in ITEM_CATALOG or not remove_item(player, content_id):
            raise ValueError("物品栏中没有这件物品")
        gifts = disciple.setdefault("items", {})
        gifts[content_id] = int(gifts.get(content_id, 0)) + 1
        if "pill" in ITEM_CATALOG[content_id].tags:
            disciple["breakthrough_bonus"] = min(
                0.35, float(disciple.get("breakthrough_bonus", 0))
                + float(WORLD_SYSTEMS["demonic_cultivation"]["pill_breakthrough_bonus"]),
            )
        result = "disciple_gifted_item"
        summary = f"你将{ITEM_CATALOG[content_id].name}赠予弟子{disciple['name']}。" + (
            f" 其突破率提高至额外 +{float(disciple.get('breakthrough_bonus', 0)):.0%}。"
            if "pill" in ITEM_CATALOG[content_id].tags else ""
        )
    elif kind == "technique":
        technique = next((entry for entry in player.known_techniques if entry.id == content_id), None)
        if not technique:
            raise ValueError("你尚未掌握这部功法")
        taught = disciple.setdefault("techniques", [])
        if content_id in taught:
            raise ValueError("这名弟子已经受过此法")
        taught.append(content_id)
        result = "disciple_taught_technique"
        summary = f"你为弟子{disciple['name']}拓印并讲授《{technique.name}》；你自身的功法不会失去。"
    else:
        raise ValueError("未知赠予类型")
    game.history.append(HistoryRecord(
        "SYS_DISCIPLE_GIFT", 1, player.age, "赐予门下", kind, result, summary,
        {"disciple_id": disciple_id, "kind": kind, "content_id": content_id},
        ["system", "relationship", "disciple"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def manage_dao_companion(
    deps: RelationshipActionDependencies, game_id: str, action: str, npc_id: str = "", kind: str = "", content_id: str = "",
) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法与道侣互动")
    rng = decode_rng(game.seed, game.rng_state)
    companion = player.dao_companion
    if action == "propose":
        if companion and companion.get("alive", True):
            raise ValueError("你已经有道侣")
        npc = deps._find_npc(game, npc_id) or deps._promote_cached_npc(game, npc_id, "结为道侣")
        if not npc or not npc.alive or npc.world != player.world:
            raise ValueError("此人当前无法回应结侣请求")
        if any(str(entry.get("id")) == npc.id for entry in player.concubines):
            raise ValueError("侍妾不是道侣，必须先解除侍妾名分")
        if player.master and player.master.get("id") == npc.id or any(entry.get("id") == npc.id for entry in player.disciples):
            raise ValueError("已有师徒名分，不能再结为道侣")
        realm_gap = abs(npc.realm_index - player.realm_index)
        chance = max(0.05, min(0.9, float(WORLD_SYSTEMS["relationship"]["companion_proposal_base"]) + (npc.affinity or 0) / 180 - realm_gap * 0.12))
        if rng.random() >= chance:
            npc.affinity = (npc.affinity or 0) - 3
            result, summary = "proposal_refused", f"{npc.name}认为缘分未至，婉拒了结为道侣的请求（同意率 {chance:.0%}）。"
        else:
            npc.affinity = (npc.affinity or 0) + deps._sage_affinity_gain(player, 12)
            source = deps._npc_faction_id(game, npc.id) or "world"
            player.dao_companion = deps._relationship_snapshot(
                npc.id, npc.name, npc.realm_index, npc.layer, source, npc.age, npc.lifespan,
                npc.alive, npc.death_reason, npc.spirit_root, npc.cultivation_progress,
                npc.path, npc.race, npc.world,
                main_technique_id=deps._default_npc_main_technique(npc), affinity=npc.affinity,
            )
            result, summary = "companion_joined", f"{npc.name}应下誓约，与你结为道侣（同意率 {chance:.0%}）。"
    else:
        if not companion:
            raise ValueError("你尚无道侣")
        if not companion.get("alive", True) or companion.get("world", player.world) != player.world:
            raise ValueError("道侣当前无法回应")
        last = companion.setdefault("last_interactions", {})
        cooldown = int(WORLD_SYSTEMS["relationship"]["companion_interaction_cooldown_years"])
        if action in {"intimacy", "entwine", "request_item", "request_technique"} and player.age - int(last.get(action, -10**9)) < cooldown:
            raise ValueError("本年度已经进行过这项道侣互动")
        if action == "intimacy":
            last[action] = player.age
            low, high = WORLD_SYSTEMS["relationship"]["companion_heart_demon_intimacy"]
            reduction = min(player.heart_demon, rng.randint(int(low), int(high)))
            player.heart_demon -= reduction
            companion["affinity"] = float(companion.get("affinity", 20)) + deps._sage_affinity_gain(player, 1)
            dialogue = rng.choice([
                "对方与你谈起初次相遇时的窘事，洞府中久违地有了笑声。",
                "你们互相复盘近年的得失，许多执念在言语间自然散去。",
                "二人并肩看了一夜星河，没有论道，却比闭关更觉心境安宁。",
                "对方提醒你莫把长生路走成孤身苦役，你默然许久。",
            ])
            result, summary = "companion_intimacy", f"{dialogue} 心魔 -{reduction:g}。"
        elif action == "entwine":
            last[action] = player.age
            low, high = WORLD_SYSTEMS["relationship"]["companion_heart_demon_entwine"]
            reduction = min(player.heart_demon, rng.randint(int(low), int(high)))
            player.heart_demon -= reduction
            companion["affinity"] = float(companion.get("affinity", 20)) + deps._sage_affinity_gain(player, 2)
            sex_ids = {technique.id for technique in [player.technique] if technique and technique.element == "sex"}
            if companion.get("main_technique_id") in TECHNIQUE_CATALOG and TECHNIQUE_CATALOG[companion["main_technique_id"]].element == "sex":
                sex_ids.add(str(companion["main_technique_id"]))
            gain = 0.0
            if sex_ids:
                gain = round(opportunity_required(player) * 0.04 * opportunity_multiplier(player), 1)
                deps._add_opportunity(player, gain)
            gain_text = f" 合欢功法运转，机缘 +{gain:g}。" if gain else ""
            child_text = deps._try_conceive_child(game, rng)
            result, summary = "companion_entwined", f"你与{companion['name']}缠绵共参，心魔 -{reduction:g}。{gain_text}{child_text}"
        elif action in {"request_item", "request_technique"}:
            last[action] = player.age
            request_kind = action.removeprefix("request_")
            chance = float(WORLD_SYSTEMS["relationship"][f"companion_request_{request_kind}"]) + float(companion.get("affinity", 20)) / 250
            chance = max(0.08, min(0.9, chance))
            candidates = list(dict.fromkeys(
                entry["content_id"] for entry in MARKET_GOODS
                if entry["kind"] == request_kind and int(entry["tier"]) <= max(1, int(companion["realm_index"]))
                and entry.get("world", "human") == player.world
                and (request_kind == "item" or (
                    can_player_practice_technique(player, TECHNIQUE_CATALOG[entry["content_id"]].element)
                    and all(known.id != entry["content_id"] for known in player.known_techniques)
                ))
            ))
            if not candidates:
                raise ValueError("道侣手中没有适合你的新物品或功法")
            if rng.random() >= chance:
                companion["affinity"] = float(companion.get("affinity", 20)) - 1
                result, summary = "companion_refused", f"{companion['name']}拒绝了这次索取（同意率 {chance:.0%}）。"
            else:
                selected = rng.choice(candidates)
                if request_kind == "item":
                    add_item(player, selected)
                    summary = f"{companion['name']}将{ITEM_CATALOG[selected].name}交给了你。"
                else:
                    learn_technique(player, TECHNIQUE_CATALOG[selected])
                    summary = f"{companion['name']}与你分享《{TECHNIQUE_CATALOG[selected].name}》。"
                result = f"companion_gave_{request_kind}"
        elif action == "gift_item":
            if content_id not in ITEM_CATALOG or not remove_item(player, content_id):
                raise ValueError("物品栏中没有这件物品")
            items = companion.setdefault("items", {})
            items[content_id] = int(items.get(content_id, 0)) + 1
            companion["affinity"] = float(companion.get("affinity", 20)) + deps._sage_affinity_gain(player, 3)
            result, summary = "companion_gifted", f"你将{ITEM_CATALOG[content_id].name}赠予{companion['name']}，情意更深。"
        elif action == "teach_technique":
            technique = next((entry for entry in player.known_techniques if entry.id == content_id), None)
            if not technique:
                raise ValueError("你尚未掌握这部功法")
            if not can_practice_technique(str(companion.get("spirit_root", "none")), technique.element):
                raise ValueError("道侣的灵根无法修习这部功法")
            companion["main_technique_id"] = technique.id
            taught = companion.setdefault("techniques", [])
            if technique.id not in taught:
                taught.append(technique.id)
            companion["affinity"] = float(companion.get("affinity", 20)) + deps._sage_affinity_gain(player, 2)
            result, summary = "companion_technique_replaced", f"{companion['name']}废去旧法，将《{technique.name}》改作主修功法。"
        else:
            raise ValueError("未知道侣互动")
    if player.dao_companion:
        source_npc = deps._find_npc(game, str(player.dao_companion.get("id", "")))
        if source_npc:
            source_npc.affinity = float(player.dao_companion.get("affinity", source_npc.affinity or 0))
    if action == "intimacy" and player.dao_companion:
        summary += deps._tianji_npc_conversation_clue(game, str(player.dao_companion.get("id", "")), rng)
    game.history.append(HistoryRecord(
        "SYS_DAO_COMPANION", 1, player.age, "道侣缘法", action, result, summary,
        {"companion": player.dao_companion.get("id") if player.dao_companion else None},
        ["system", "relationship", "dao_companion"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def manage_dao_friend(deps: RelationshipActionDependencies, game_id: str, npc_id: str, action: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法与道友互动")
    friend = next((row for row in player.dao_friends if row.get("id") == npc_id), None)
    rng = decode_rng(game.seed, game.rng_state)
    if action == "befriend":
        if friend:
            raise ValueError("此人已经是你的道友")
        npc = deps._find_npc(game, npc_id) or deps._promote_cached_npc(game, npc_id, "结为道友")
        if not npc or not npc.alive or npc.world != player.world:
            raise ValueError("此人当前无法回应")
        if any(str(entry.get("id")) == npc.id for entry in player.concubines):
            raise ValueError("已有侍妾名分，不能同时结为道友")
        if (player.dao_companion and player.dao_companion.get("id") == npc.id) or (player.master and player.master.get("id") == npc.id) or any(row.get("id") == npc.id for row in player.disciples):
            raise ValueError("你们已经有更紧密的人际名分")
        required = float(WORLD_SYSTEMS["relationship"]["friend_affinity_required"])
        if float(npc.affinity or 0) < required:
            raise ValueError(f"对方好感至少达到 {required:g} 才愿与你结为道友")
        chance = min(0.95, float(WORLD_SYSTEMS["relationship"]["friend_invite_base"]) + float(npc.affinity or 0) / 200)
        if rng.random() >= chance:
            result, summary = "friend_refused", f"{npc.name}认为交情尚浅，婉拒了道友之约（同意率 {chance:.0%}）。"
        else:
            source = deps._npc_faction_id(game, npc.id) or "world"
            friend = deps._relationship_snapshot(
                npc.id,npc.name,npc.realm_index,npc.layer,source,npc.age,npc.lifespan,
                npc.alive,npc.death_reason,npc.spirit_root,npc.cultivation_progress,
                npc.path,npc.race,npc.world,main_technique_id=deps._default_npc_main_technique(npc),affinity=npc.affinity or 0,
            )
            player.dao_friends.append(friend)
            result, summary = "friend_joined", f"{npc.name}与你交换信符，自此以道友相称。"
    else:
        if not friend or not friend.get("alive", True) or friend.get("world") != player.world:
            raise ValueError("这位道友当前无法回应")
        last = friend.setdefault("last_interactions", {})
        cooldown = int(WORLD_SYSTEMS["relationship"]["friend_interaction_cooldown_years"])
        if player.age - int(last.get(action, -10**9)) < cooldown:
            raise ValueError("本年度已经进行过这项道友互动")
        last[action] = player.age
        if action == "spar":
            low, high = WORLD_SYSTEMS["relationship"]["friend_spar_opportunity"]
            gain = rng.randint(int(low), int(high))
            deps._add_opportunity(player, gain)
            deps._adjust_person_affinity(game, npc_id, 1)
            result, summary = "friend_sparred", f"你与{friend['name']}点到为止地切磋数场，彼此印证招式，机缘 +{gain}。"
        elif action == "discuss":
            low, high = WORLD_SYSTEMS["relationship"]["friend_discuss_opportunity"]
            gain = rng.randint(int(low), int(high))
            deps._add_opportunity(player, gain)
            deps._adjust_person_affinity(game, npc_id, 2)
            result, summary = "friend_discussed", f"你与{friend['name']}交换修炼心得，解开数处疑难，机缘 +{gain}。"
        else:
            raise ValueError("未知道友互动")
    if action in {"befriend", "discuss", "spar"}:
        summary += deps._tianji_npc_conversation_clue(game, npc_id, rng)
    game.history.append(HistoryRecord(
        "SYS_DAO_FRIEND",1,player.age,"道友往来",action,result,summary,
        {"friend_id":npc_id},["system","relationship","friend"],
    ))
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def invite_relationship_to_faction(deps: RelationshipActionDependencies, game_id: str, npc_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    sect = game.sects.get(player.faction_id or "")
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法引荐入宗")
    if not sect or sect.extinct or sect.world != player.world:
        raise ValueError("你当前没有可以引荐他人的宗门")
    relations = [entry for entry in [player.master, player.dao_companion, *player.dao_friends] if entry]
    relation = next((entry for entry in relations if str(entry.get("id")) == npc_id), None)
    if not relation or not relation.get("alive", True) or relation.get("world") != player.world:
        raise ValueError("只能邀请当前界面中存活的师父、道侣或道友")
    existing = deps._npc_faction_id(game, npc_id)
    if existing:
        raise ValueError("此人已经有所属宗门")
    npc = deps._persist_relationship_npc(game, relation, "受邀加入宗门")
    npc.faction_id = sect.id
    relation["source"] = "world"
    npc.affinity = max(
        float(npc.affinity or 0), float(relation.get("affinity", 0)),
    ) + deps._sage_affinity_gain(player, 4)
    relation["affinity"] = npc.affinity
    game.history.append(HistoryRecord(
        "SYS_RELATION_JOIN_FACTION",1,player.age,"引荐入宗",npc_id,"joined",
        f"{relation['name']}接受你的引荐，加入{sect.name}，成为宗门中真实在册的一员。",
        {"npc_id":npc_id,"faction_id":sect.id},["system","relationship","faction"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def leave_relationship(deps: RelationshipActionDependencies, game_id: str, kind: str, npc_id: str = "") -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法了断人际关系")
    rules = WORLD_SYSTEMS["relationship"]
    if kind == "companion":
        relation = player.dao_companion
        if not relation:
            raise ValueError("你当前没有道侣")
        npc = deps._persist_relationship_npc(game, relation, "道侣决裂")
        player.heart_demon += deps._sage_scaled_gain(
            player, float(rules["companion_separation_heart_demon"]), "heart_demon_gain_reduction",
        )
        npc.affinity = float(rules.get("relationship_release_affinity", 0))
        player.dao_companion = None
        summary = f"你与{relation['name']}斩断道侣誓约，双方好感重置为中立；心魔骤增 {rules['companion_separation_heart_demon']:g}。"
        tags = ["system","relationship","dao_companion","negative"]
    elif kind == "master":
        relation = player.master
        if not relation:
            raise ValueError("你当前没有师父")
        npc = deps._persist_relationship_npc(game, relation, "脱离师门")
        npc.affinity = float(rules.get("relationship_release_affinity", 0))
        player.master = None
        summary = f"你脱离{relation['name']}门下，双方好感重置为中立，不会因这次离门立即遭到寻仇。"
        tags = ["system","relationship","master","negative"]
    elif kind == "friend":
        relation = next((entry for entry in player.dao_friends if entry.get("id") == npc_id), None)
        if not relation:
            raise ValueError("此人并非你的道友")
        player.dao_friends.remove(relation)
        deps._set_person_affinity(game, str(relation.get("id", "")), float(rules.get("relationship_release_affinity", 0)))
        summary = f"你与{relation['name']}收回道友信符，双方好感重置为中立，此后只是寻常相识。"
        tags = ["system","relationship","friend"]
    elif kind == "disciple":
        relation = next((entry for entry in player.disciples if entry.get("id") == npc_id), None)
        if not relation:
            raise ValueError("此人并非你的弟子")
        npc = deps._persist_relationship_npc(game, relation, "逐出师门")
        npc.affinity = float(rules.get("relationship_release_affinity", 0))
        player.disciples.remove(relation)
        summary = f"你将{relation['name']}逐出门下，双方好感重置为中立。"
        tags = ["system","relationship","disciple","negative"]
    else:
        raise ValueError("未知人际关系类型")
    player.party = [entry for entry in player.party if entry.get("id") != relation.get("id")]
    game.history.append(HistoryRecord(
        "SYS_RELATION_EXIT",1,player.age,"缘尽于此",kind,"departed",summary,
        {"npc_id":relation.get("id"),"kind":kind},tags,
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def manage_party(deps: RelationshipActionDependencies, game_id: str, npc_id: str, action: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or player.imprisonment:
        raise ValueError("当前状态无法调整队伍")
    if action == "interact":
        if not any(entry.get("id") == npc_id for entry in player.party):
            raise ValueError("只有当前队友可以进行同行互动")
        key = f"party_interaction:{npc_id}"
        if game.governance_actions.get(key) == player.age:
            raise ValueError("本行动单位已经与这位队友交流过")
        rng = decode_rng(game.seed, game.rng_state)
        gain_range = WORLD_SYSTEMS["party"].get("interaction_affinity", [4, 8])
        gain = rng.randint(int(gain_range[0]), int(gain_range[1]))
        affinity = deps._adjust_person_affinity(game, npc_id, gain)
        game.governance_actions[key] = player.age
        game.rng_state = encode_rng(rng)
        result, summary = "interacted", f"你与队友交流沿途见闻、互证修炼心得，好感 +{gain}，当前为 {affinity:.0f}。"
        summary += deps._tianji_npc_conversation_clue(game, npc_id, rng)
        game.rng_state = encode_rng(rng)
    elif action in {"crossing_add", "crossing_remove"}:
        if not any(entry.get("id") == npc_id for entry in player.party):
            raise ValueError("只有当前队友可以随行飞升")
        candidate = deps._party_crossing_candidate(game, npc_id)
        if not candidate:
            raise ValueError("此队友尚未达到可共同飞升的境界")
        is_companion = bool(player.dao_companion and str(player.dao_companion.get("id")) == npc_id)
        if is_companion:
            player.joint_spirit_crossing = (
                {"id": npc_id, "name": candidate["name"]}
                if action == "crossing_add"
                else {"id": npc_id, "name": candidate["name"], "declined": True}
            )
        else:
            player.joint_friend_crossing = [entry for entry in player.joint_friend_crossing if entry.get("id") != npc_id]
            if action == "crossing_add":
                player.joint_friend_crossing.append({"id":npc_id, "name":candidate["name"]})
        if action == "crossing_add":
            result, summary = "crossing_selected", f"你邀请{candidate['name']}在飞升时与你一同闯过界壁。"
        else:
            result, summary = "crossing_removed", f"你取消了与{candidate['name']}共同飞升的安排。"
    elif action == "leave":
        before = len(player.party)
        player.party = [entry for entry in player.party if entry.get("id") != npc_id]
        player.joint_friend_crossing = [entry for entry in player.joint_friend_crossing if entry.get("id") != npc_id]
        if player.dao_companion and str(player.dao_companion.get("id")) == npc_id:
            player.joint_spirit_crossing = {
                "id": npc_id, "name": str(player.dao_companion.get("name", "道侣")), "declined": True,
            }
        if len(player.party) == before:
            raise ValueError("此人不在队伍中")
        summary = "你与队友暂且分别。"
        result = "left"
    elif action == "invite":
        if len(player.party) >= int(WORLD_SYSTEMS["party"]["max_companions"]):
            raise ValueError("当前队伍已经满员")
        if any(entry.get("id") == npc_id for entry in player.party):
            raise ValueError("此人已经在队伍中")
        companion = player.dao_companion
        if companion and companion.get("id") == npc_id:
            if not companion.get("alive", True) or companion.get("world") != player.world:
                raise ValueError("道侣当前无法同行")
            player.party.append({"id": npc_id, "name": companion.get("name", "道侣")})
            result, summary = "joined", f"{companion.get('name', '道侣')}与你心意相通，加入了队伍。"
            game.history.append(HistoryRecord(
                "SYS_PARTY_MANAGE", 1, player.age, "道侣同行", npc_id, result, summary,
                {"party": [entry.get("id") for entry in player.party]}, ["system", "party", "companion"],
            ))
            game.updated_at = now_iso()
            deps.store.save(game)
            return deps.present(game)
        friend = next((row for row in player.dao_friends if row.get("id") == npc_id), None)
        if friend:
            if not friend.get("alive", True) or friend.get("world") != player.world:
                raise ValueError("道友当前无法同行")
            player.party.append({"id":npc_id,"name":friend.get("name","道友")})
            result, summary = "joined", f"道友{friend.get('name','无名')}应邀加入队伍。"
            game.history.append(HistoryRecord(
                "SYS_PARTY_MANAGE",1,player.age,"道友同行",npc_id,result,summary,
                {"party":[entry.get("id") for entry in player.party]},["system","party","friend"],
            ))
            game.updated_at = now_iso()
            deps.store.save(game)
            return deps.present(game)
        npc = deps._find_npc(game, npc_id) or deps._promote_cached_npc(game, npc_id, "结伴同行")
        if not npc or not npc.alive or npc.world != player.world:
            raise ValueError("此人当前无法同行")
        rng = decode_rng(game.seed, game.rng_state)
        faction_id = deps._npc_faction_id(game, npc.id)
        global_hostility = max(
            player.hostility.get(deps._hostility_key("race", npc.race), 0),
            player.hostility.get(deps._hostility_key("sect", faction_id), 0) if faction_id else 0,
        )
        chance = deps._party_invitation_chance(player, npc, global_hostility)
        if rng.random() >= chance:
            npc.affinity = (npc.affinity or 0) - 2
            result, summary = "rejected", f"{npc.name}婉拒了同行邀请（同意率 {chance:.0%}）。"
        else:
            npc.affinity = (npc.affinity or 0) + deps._sage_affinity_gain(player, 4)
            player.party.append({"id": npc.id, "name": npc.name})
            result, summary = "joined", f"{npc.name}同意加入队伍（同意率 {chance:.0%}）。"
        game.rng_state = encode_rng(rng)
    else:
        raise ValueError("未知队伍操作")
    game.history.append(HistoryRecord(
        "SYS_PARTY_MANAGE", 1, player.age, "结伴同行", npc_id, result, summary,
        {"party": [entry.get("id") for entry in player.party]}, ["system", "party", "npc"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
