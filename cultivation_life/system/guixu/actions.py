from __future__ import annotations
from ...content_registry import ACTIONS
from typing import Any
from ...models import HistoryRecord
from ...content_registry import WORLD_SYSTEMS
from ..possession_system import advance_player_age
from ...rules import divine_sense_level
from ...rules import effective_fame
from ...runtime import encode_rng
from ...rules import max_hp
from ...rules import max_mp
from ...runtime import now_iso
from ...rules import opportunity_multiplier
from ...rules import remove_item
from .dependencies import GuixuActionsDependencies


def guixu_action(deps: GuixuActionsDependencies, game_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    game = deps._load(game_id)
    if not deps.guixu_content_available():
        raise ValueError("归墟之潮 DLC 当前未启用")
    deps._ensure_guixu_state(game)
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if not game.player.alive:
        raise ValueError("此生已经结束")
    rng = deps.decode_rng(game.seed, game.rng_state)
    session = game.guixu_state.get("player_session")
    before_days = int(session.get("remaining_days", 0)) if session else 0
    result, summary = action, ""
    history_event = "SYS_GUIXU_ACTION"

    if action == "enter":
        dungeon_id = str(payload.get("dungeon_id", ""))
        dungeon, cycle = deps._guixu_cycle_and_definition(game, dungeon_id)
        if session:
            raise ValueError("你已经身在归墟之中")
        if cycle.get("phase") != "open":
            raise ValueError("这座归墟当前没有开启")
        if game.player.world != dungeon["world"] or game.player.location_id != dungeon["entry_location_id"]:
            raise ValueError("你必须先抵达归墟入口地域")
        if (game.player.realm_index, game.player.layer) > tuple(dungeon["max_entry_rank"]):
            raise ValueError("你的修为已经超过这座归墟的入场上限")
        key = f"{dungeon_id}:{cycle['cycle_index']}"
        if key in game.guixu_state["entered_cycles"]:
            raise ValueError("每人每届只能进入一次")
        game.guixu_state["entered_cycles"][key] = True
        session = {
            "dungeon_id": dungeon_id, "cycle_index": cycle["cycle_index"], "layer_id": "outer",
            "remaining_days": max(0, int(dungeon["window_days"]) - 1), "trapped": False,
            "entry_location_id": dungeon["entry_location_id"], "clue_count": 0,
            "secret_unlocked": False, "carried_entry_ids": [], "recruited_actor_ids": [],
            "negotiation_attempts": {}, "pending_betrayal": None,
            "pending_threat": None, "threatened_actor_ids": [],
        }
        game.guixu_state["player_session"] = session
        deps._guixu_offer_team(game, cycle, session)
        result, summary, history_event = "entered", f"你踏入{dungeon['name']}，抵达外层。", "SYS_GUIXU_ENTER"
    else:
        if not session:
            raise ValueError("你当前不在归墟之中")
        dungeon, cycle = deps._guixu_cycle_and_definition(game, str(session["dungeon_id"]))
        threat_actions = {"threat_surrender", "threat_resist"}
        pending_threat = session.get("pending_threat")
        if pending_threat and action not in threat_actions:
            raise ValueError("必须先回应拦路修士的交宝威胁")
        if not pending_threat and action in threat_actions:
            raise ValueError("当前没有修士向你索要宝物")
        offer = session.get("pending_team_offer")
        if offer and action not in {"team_accept", "team_decline"}:
            raise ValueError("请先回应临时组队邀请")
        if action in {"team_accept", "team_decline"} and not offer:
            raise ValueError("当前没有临时组队邀请")
        if action in {"team_accept", "team_decline"}:
            if action == "team_accept":
                if game.player.party or session.get("recruited_actor_ids"):
                    raise ValueError("你已有队友，无法接受独行邀请")
                actor = deps._guixu_actor(cycle, str(offer["actor_id"]))
                if actor.get("team_id"):
                    deps._dissolve_guixu_npc_team(game, dungeon, cycle, str(actor["team_id"]), "改与玩家临时同行")
                actor.update(status="recruited", layer_id=session["layer_id"], temporary_invitation=True)
                session.setdefault("recruited_actor_ids", []).append(actor["actor_id"])
                # Old in-dungeon saves can already contain player-owned treasure.
                if session.get("player_ever_claimed") or session.get("carried_entry_ids"):
                    session["player_ever_claimed"] = True
                    actor["empty_since_action"] = int(session.get("action_serial", 0))
                result, summary = "joined", f"{actor['name']}与你临时结伴。所得宝物若只归你一人，对方可能起异心。"
            else:
                result, summary = "declined", "你婉拒了临时同行的邀请。"
            session["pending_team_offer"] = None
        elif action == "gift_treasure":
            actor = next((a for a in cycle["roster"] if a["actor_id"] == payload.get("actor_id")
                          and a.get("status") == "recruited" and a["actor_id"] in session.get("recruited_actor_ids", [])), None)
            if not actor:
                raise ValueError("只能向当前临时队友分宝")
            entry_id = str(payload.get("pool_entry_id", ""))
            if entry_id not in {r["pool_entry_id"] for r, _ in deps._guixu_transferable_player_entries(game, dungeon, cycle, session)}:
                raise ValueError("这件宝物不在本届可转移清单中")
            name = deps._surrender_guixu_treasure(game, dungeon, cycle, session, {"pool_entry_id":entry_id}, actor)
            actor.pop("empty_since_action", None)
            result, summary = "gifted", f"你将{name}交给{actor['name']}，对方已有收获，空手不满消退。"
        elif action == "threat_surrender":
            actor = deps._guixu_actor(cycle, str(pending_threat["actor_id"]))
            name = deps._surrender_guixu_treasure(
                game, dungeon, cycle, session, pending_threat, actor,
            )
            session["pending_threat"] = None
            session["threat_cooldown"] = 1
            result, summary = "surrendered", f"你交出{name}，{actor['name']}暂且放你离开。"
            history_event = "SYS_GUIXU_THREAT_RESPONSE"
        elif action == "threat_resist":
            actor = deps._guixu_actor(cycle, str(pending_threat["actor_id"]))
            session["pending_threat"] = None
            session["threat_cooldown"] = 1
            result, combat_summary = deps._guixu_fight(
                game, dungeon, cycle, session, actor, rng, player_defending=True,
            )
            summary = f"你拒绝交宝，与{actor['name']}当场开战。{combat_summary}"
            history_event = "SYS_GUIXU_THREAT_RESPONSE"
        elif action == "move":
            target = str(payload.get("target_layer_id", ""))
            current = str(session["layer_id"])
            edge = frozenset((current, target))
            if edge not in deps.MOVE_COSTS:
                raise ValueError("两层之间没有直接通路")
            if target == "secret" and not session.get("secret_unlocked"):
                raise ValueError("尚未找到秘层通道")
            if session.get("trapped"):
                cost = 0
            else:
                cost = deps.MOVE_COSTS[edge]
                deps._consume_guixu_days(game, dungeon, cycle, session, cost, rng)
            session["layer_id"] = target
            result = "secret" if target == "secret" else "moved"
            summary = f"你移动到{next(row['name'] for row in dungeon['layers'] if row['id'] == target)}，耗时{cost}天。"
            history_event = "SYS_GUIXU_MOVE"
        elif action == "search":
            if session.get("trapped"):
                raise ValueError("被困期只能静修、移动或等待下一届开启")
            days = int(deps._guixu_settings()["action_days"]["search"])
            elapsed_after = deps._guixu_elapsed_days(dungeon, session) + days
            candidates = [
                row for row in cycle.get("round_entries", [])
                if row.get("layer_id") == session["layer_id"] and row.get("resolution") == "unclaimed"
                and int(row.get("claim_at_day") or 0) > elapsed_after
            ]
            if candidates:
                row = rng.choice(candidates)
                name = deps._guixu_grant_entry(game, dungeon, row, "searched")
                result, summary = "found", f"你赶在其他修士之前找到了{name}。"
            else:
                if not session.get("secret_unlocked") and rng.random() < .35:
                    session["clue_count"] = int(session.get("clue_count", 0)) + 1
                    threshold = int(deps._guixu_settings().get("secret_clue_threshold", 3))
                    if session["clue_count"] >= threshold:
                        session["secret_unlocked"] = True
                        result, summary = "secret_clue_complete", "你拼合潮纹，找到了秘层通道。"
                    else:
                        result, summary = "secret_clue", f"你发现一条秘层线索（{session['clue_count']}/{threshold}）。"
                else:
                    result, summary = "empty", "这一带只剩破碎禁制，没有找到无主宝物。"
            deps._consume_guixu_days(game, dungeon, cycle, session, days, rng)
            history_event = "SYS_GUIXU_SEARCH"
        elif action == "return":
            if session.get("trapped"):
                raise ValueError("潮门已经闭合，只能等待下一届或突破传出")
            cost = deps._guixu_return_days(str(session["layer_id"]))
            before = int(session["remaining_days"])
            if before < cost:
                deps._consume_guixu_days(game, dungeon, cycle, session, cost, rng)
                session["layer_id"] = "outer"
                result, summary = "trapped", "潮门在返程途中闭合，你被困在归墟之内。"
            else:
                session["remaining_days"] = before - cost
                carried = len(session.get("carried_entry_ids", []))
                result = "narrow_escape" if session["remaining_days"] < 3 else "full_return" if carried >= 3 else "returned"
                summary = f"你耗时{cost}天返回入口，携出{carried}件归墟宝物。"
                session["exited"] = True
                game.guixu_state["player_session"] = None
            history_event = "SYS_GUIXU_RETURN"
        elif action == "rest":
            hp_before, mp_before = game.player.hp, game.player.mp
            hp_max, mp_max = max_hp(game.player), max_mp(game.player)
            game.player.hp = min(hp_max, game.player.hp + hp_max * .35)
            game.player.mp = min(mp_max, game.player.mp + mp_max * .45)
            if not session.get("trapped"):
                deps._consume_guixu_days(
                    game, dungeon, cycle, session,
                    int(deps._guixu_settings()["action_days"]["rest"]), rng,
                )
            result = "rested"
            summary = (
                f"你在归墟内就地调息，气血恢复{game.player.hp - hp_before:.0f}，"
                f"法力恢复{game.player.mp - mp_before:.0f}。"
            )
            history_event = "SYS_GUIXU_REST"
        elif action in {"fight", "flee", "recruit", "negotiate"}:
            actor = deps._guixu_actor(cycle, str(payload.get("actor_id", "")))
            if actor["layer_id"] != session["layer_id"]:
                raise ValueError("目标修士不在当前层")
            if action == "fight":
                role = deps._guixu_relationship_role(game, str(actor.get("npc_id") or ""))
                confirmed = bool(payload.get("confirm_betrayal", False))
                marker = {"actor_id": actor["actor_id"], "role": role} if role else None
                if role and not confirmed:
                    session["pending_betrayal"] = marker
                    result, summary = "confirmation_required", f"{actor['name']}是你的{role}。再次确认才会进入致命夺宝战。"
                elif role and session.get("pending_betrayal") != marker:
                    raise ValueError("背叛确认已经失效")
                else:
                    result, summary = deps._guixu_fight(game, dungeon, cycle, session, actor, rng)
                    session["pending_betrayal"] = None
                history_event = "SYS_GUIXU_COMBAT"
            elif action == "flee":
                gap = game.player.realm_index - int(actor["realm_index"])
                settings = deps._guixu_settings()
                chance = max(
                    float(settings.get("flee_min_chance", .04)),
                    min(
                        float(settings.get("flee_max_chance", .68)),
                        float(settings.get("flee_base_chance", .28))
                        + gap * float(settings.get("flee_realm_gap_bonus", .07)),
                    ),
                )
                if rng.random() < chance:
                    result, summary = "escaped", f"你摆脱了{actor['name']}（遁走率{chance:.0%}）。"
                    deps._consume_guixu_days(game, dungeon, cycle, session, 1, rng)
                else:
                    result, summary = deps._guixu_fight(game, dungeon, cycle, session, actor, rng)
                history_event = "SYS_GUIXU_FLEE"
            elif action == "recruit":
                if len(session.get("recruited_actor_ids", [])) >= int(deps._guixu_settings().get("recruit_cap", 2)):
                    raise ValueError("临时队友已经达到上限")
                chance = max(.05, min(.82, .24 + effective_fame(game.player) / 1000 + max(0, game.player.realm_index - int(actor["realm_index"])) * .08))
                if rng.random() < chance:
                    if actor.get("team_id"):
                        deps._dissolve_guixu_npc_team(
                            game, dungeon, cycle, str(actor["team_id"]),
                            f"因{actor['name']}改投玩家队伍而散伙",
                        )
                    actor["status"] = "recruited"
                    session["recruited_actor_ids"].append(actor["actor_id"])
                    result, summary = "joined", f"{actor['name']}同意临时同行（成功率{chance:.0%}）。"
                else:
                    result, summary = "rejected", f"{actor['name']}拒绝同行（成功率{chance:.0%}）。"
                deps._consume_guixu_days(game, dungeon, cycle, session, 1, rng)
                history_event = "SYS_GUIXU_RECRUIT"
            else:
                entry_id = str(payload.get("pool_entry_id", ""))
                row = next((entry for entry in cycle.get("round_entries", []) if entry["pool_entry_id"] == entry_id), None)
                if not row or row.get("holder_id") != actor["actor_id"] or row.get("resolution") != "held":
                    raise ValueError("对方当前并未持有这件宝物")
                key = f"{actor['actor_id']}:{entry_id}"
                if key in session["negotiation_attempts"]:
                    raise ValueError("本届已经为这件宝物正式议价过")
                definition = deps._guixu_entry_definition(dungeon, entry_id)
                offer = int(payload.get("offer_stones", 0))
                if offer <= 0:
                    raise ValueError("正式议价必须提出正数灵石报价")
                wallet = next(
                    (int(item.quantity) for item in game.player.inventory if item.id == "spirit_stone"), 0,
                )
                if wallet < offer:
                    raise ValueError("你没有足够的下品灵石支付报价")
                session["negotiation_attempts"][key] = True
                ratio = offer / max(1.0, float(definition.get("value", 1)))
                npc = deps._find_npc(game, str(actor.get("npc_id"))) if actor.get("npc_id") else None
                affinity = float(npc.affinity or 0) if npc else 0.0
                chance = max(.03, min(.90, .12 + ratio * .55 + max(-.15, affinity / 400)))
                if rng.random() < chance:
                    remove_item(game.player, "spirit_stone", offer)
                    name = deps._guixu_grant_entry(game, dungeon, row, "traded")
                    result, summary = "traded", f"{actor['name']}接受报价，你以{offer}枚灵石换得{name}。"
                else:
                    result, summary = "refused", f"{actor['name']}拒绝了报价（成交率{chance:.0%}）。"
                deps._consume_guixu_days(game, dungeon, cycle, session, 1, rng)
                history_event = "SYS_GUIXU_NEGOTIATE"
        elif action == "trapped_cultivate":
            if not session.get("trapped"):
                raise ValueError("只有被困后才能按年静修")
            layer = next(row for row in dungeon["layers"] if row["id"] == session["layer_id"])
            low, high = ACTIONS["cultivate"]["opportunity"]
            gain = rng.randint(low, high) * opportunity_multiplier(
                game.player, dict(layer["qi_concentrations"]),
            )
            deps._add_opportunity(
                game.player, gain, dict(layer["qi_gain_efficiencies"]), apply_efficiency=False,
            )
            era_news: list[str] = []
            advance_player_age(game.player)
            deps._advance_world_year(game, rng, era_news, encounters=False)
            if not game.player.alive and any(
                record.event_id == "SYS_LIFESPAN" and record.age == game.player.age
                for record in game.history[-3:]
            ):
                game.history.append(HistoryRecord(
                    "SYS_GUIXU_TRAPPED_DEATH", 1, game.player.age, "坐化归墟", dungeon["id"],
                    "dead", f"你被困于{dungeon['name']}期间寿尽坐化。", {},
                    ["system", "guixu", "death"],
                ))
            if game.player.alive and (game.player.realm_index, game.player.layer) >= tuple(dungeon["eject_rank"]):
                game.player.location_id = dungeon["entry_location_id"]
                game.guixu_state["player_session"] = None
                result, summary, history_event = "breakthrough", "你突破归墟界限，被潮眼送回入口。", "SYS_GUIXU_EJECT"
            else:
                result, summary = "cultivated", f"你在{layer['name']}静修一年，获得机缘{gain:.1f}。"
                history_event = "SYS_GUIXU_TRAPPED_CULTIVATE"
        else:
            raise ValueError("未知归墟操作")

    active_session = game.guixu_state.get("player_session")
    if (
        active_session is session and session and action not in {"enter", "threat_surrender", "threat_resist"}
        and not session.get("trapped")
        and int(session.get("remaining_days", 0)) < before_days
    ):
        active_dungeon, active_cycle = deps._guixu_cycle_and_definition(
            game, str(session["dungeon_id"]),
        )
        betrayed = deps._guixu_team_tick(game, active_dungeon, active_cycle, session, rng)
        if not betrayed:
            deps._guixu_offer_team(game, active_cycle, session)
            deps._maybe_guixu_npc_threat(game, active_dungeon, active_cycle, session, rng)

    game.history.append(HistoryRecord(
        history_event, 1, game.player.age, "归墟行动", action, result, summary,
        {"action": action}, ["action", "guixu", f"result:{result}"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)


def _guixu_trapped_training(
    deps: GuixuActionsDependencies, game_id: str, action: str, units: int = 1,
) -> dict[str, Any]:
    """Run only inward-facing training while the player is trapped."""
    game = deps._load(game_id)
    session = (
        game.guixu_state.get("player_session")
        if isinstance(game.guixu_state, dict) else None
    )
    if not session or not session.get("trapped"):
        raise ValueError("你当前并未被困归墟")
    if action not in {"cultivate", "body_train", "sense_train", "rest"}:
        raise ValueError("被困归墟期间只能修炼、炼体、锻炼神识或调息")
    dungeon, _ = deps._guixu_cycle_and_definition(game, str(session["dungeon_id"]))
    layer = next(row for row in dungeon["layers"] if row["id"] == session["layer_id"])
    rng = deps.decode_rng(game.seed, game.rng_state)
    action_units = max(1, min(10, int(units)))
    requested_years = action_units * int(WORLD_SYSTEMS["time_units"][str(game.player.realm_index)])
    start_age = game.player.age
    total_opportunity = 0.0
    total_body = 0.0
    total_sense = 0.0
    hp_before, mp_before = game.player.hp, game.player.mp
    concentrations = dict(layer["qi_concentrations"])
    efficiencies = dict(layer["qi_gain_efficiencies"])
    for elapsed in range(requested_years):
        advance_player_age(game.player)
        low, high = ACTIONS[action]["opportunity"]
        gain = rng.randint(low, high) * opportunity_multiplier(game.player, concentrations)
        total_opportunity += deps._add_opportunity(game.player, gain, efficiencies, apply_efficiency=False)
        if action == "body_train":
            body_gain = deps._body_training_step(game.player, rng, concentrations)
            required = deps._body_progress_required(game.player)
            before = game.player.body_progress
            game.player.body_progress = min(required, before + body_gain)
            total_body += game.player.body_progress - before
            if game.player.body_progress >= required:
                game.player.awaiting_body_breakthrough = True
        elif action == "sense_train":
            sense_gain = deps._sense_training_step(
                game.player, efficiencies, concentrations,
            )
            game.player.divine_sense_experience += sense_gain
            total_sense += sense_gain
        elif action == "rest" and game.player.heart_demon > 0:
            game.player.heart_demon = max(0.0, game.player.heart_demon - .5)
        deps._apply_action_resources(game.player, action, elapsed == 0)
        deps._advance_world_year(game, rng, [], encounters=False)
        if game.player.alive:
            deps._advance_soul_erosion_time(game, 1)
        if (
            not game.player.alive or game.pending_event
            or (action == 'body_train' and game.player.awaiting_body_breakthrough)
            or not (game.guixu_state.get("player_session") or {}).get("trapped")
        ):
            break

    if not game.player.alive and any(
        record.event_id == "SYS_LIFESPAN" and record.age == game.player.age
        for record in game.history[-3:]
    ):
        game.history.append(HistoryRecord(
            "SYS_GUIXU_TRAPPED_DEATH", 1, game.player.age, "坐化归墟", dungeon["id"],
            "dead", f"你被困于{dungeon['name']}期间寿尽坐化。", {},
            ["system", "guixu", "death"],
        ))
    elapsed_years = max(1, game.player.age - start_age)
    if action == "body_train":
        detail = f"炼体积累 +{total_body:.1f}，当前炼体{game.player.body_training}层"
    elif action == "sense_train":
        detail = f"神识经验 +{total_sense:.1f}，当前神识{divine_sense_level(game.player)}级"
    elif action == "rest":
        detail = (
            f"气血恢复{game.player.hp - hp_before:.0f}，"
            f"法力恢复{game.player.mp - mp_before:.0f}"
        )
    else:
        detail = f"机缘 +{total_opportunity:.1f}"
    game.history.append(HistoryRecord(
        "SYS_GUIXU_TRAPPED_TRAIN", 1, game.player.age, "困守修行", action, "completed",
        f"你在{layer['name']}闭关{elapsed_years}年，{detail}。",
        {"action": action, "years": elapsed_years, "opportunity": round(total_opportunity, 1)},
        ["action", "guixu", "trapped", action],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)
