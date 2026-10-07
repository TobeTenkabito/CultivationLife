"""Explicit operations for merchant system."""

from __future__ import annotations
import copy
from ..content_registry import REALMS
from ..rules import remove_item, has_item, expected_combat_power, combat_power
from ..runtime import decode_rng, encode_rng, now_iso
from .merchant_definitions import POLICIES, RANKS, CROSS_ALLIANCES, METRICS, PROCUREMENT_KINDS
from .merchant.dependencies import MerchantActionDependencies
from .economy.fleet_network import member_of

def merchant_action(deps: MerchantActionDependencies, game_id, action, payload=None, *, committed=None):
    game = copy.deepcopy(deps._load(game_id))
    deps._ensure_merchant(game)
    payload = payload or {}
    player, state = game.player, game.merchant_state
    if not player.alive or game.pending_event or player.imprisonment or player.ghost_captor or game.active_trial or game.guixu_state.get("player_session"):
        raise ValueError("当前状态无法处理商盟事务")
    rng = decode_rng(game.seed, game.rng_state)
    member = state["membership"]
    alliance_id = str(payload.get("alliance_id") or (member or {}).get("alliance_id", ""))
    alliance = deps._merchant_alliance(game, player.world, alliance_id)
    if not alliance and member and not payload.get('alliance_id'):
        issuer = deps._merchant_alliance(game, member['world'], member['alliance_id'])
        if issuer:
            alliance = deps._merchant_alliance(game, player.world, issuer.get('network_id', issuer['id']))
            if alliance:
                alliance_id = alliance['id']
    if action == "dismiss_notices":
        state["notices"] = []
    elif action == "leave":
        if state["active"]:
            raise ValueError("请先完成或放弃已接委托")
        state["membership"] = None
    else:
        if not alliance or not deps._merchant_site(game, alliance):
            raise ValueError("请前往该商盟在本界的总部或分部地图")
        site = deps._merchant_site(game, alliance)
        if action == "join":
            if member:
                raise ValueError("已加入商盟，请先退出原商盟")
            state["membership"] = {"alliance_id": alliance_id, "world": player.world, "site": site, "rank": 0}
            deps._merchant_notice(game, f"你已加入{alliance['name']}，成为{'总部' if site == 'hq' else deps.maps.location(player.world, site)['name'] + '分部'}成员。宗门、家族和种族身份不受影响。")
        else:
            if not member_of(game, alliance):
                raise ValueError("你不是该商盟成员")
            influence_key = deps._merchant_influence_key(member)
            influence = state["influence"].get(influence_key, 0)
            if action == 'teleport':
                destination = str(payload.get('destination', ''))
                sites = {alliance['hq'], *(o['location_id'] for o in alliance['offices'])}
                if destination not in sites:
                    raise ValueError('目的地不是本盟总部或分部')
                deps._instant_arrival(game, destination)
                deps._merchant_notice(game, f"由本盟内部传送阵抵达{deps.maps.location(player.world, destination)['name']}，不增加年龄。")
            elif action == "promote":
                if member["world"] != player.world or (member["site"] == "hq" and member["rank"] == 0):
                    raise ValueError("总部直入成员须先调往本界分部，从分部成员开始历练")
                threshold = [120, 360][min(member["rank"], 1)]
                if member["rank"] >= 2 or influence < threshold:
                    raise ValueError(f"晋升所需本部影响力：{threshold}")
                member["rank"] += 1
                deps._merchant_notice(game, f"盟内考绩通过，晋升为{RANKS[member['rank']]}。")
            elif action == "transfer_branch":
                if state["active"] or member["world"] != player.world or site == "hq":
                    raise ValueError("请完成当前委托并前往入盟界面的分部申请历练")
                if member["site"] == "hq":
                    member.update(site=site, rank=0)
                    state["influence"][f"{player.world}:{alliance_id}:offices"] = 0
                else:
                    member["site"] = site
                deps._merchant_notice(game, "调任分部；同界分部之间共用影响力，总部调出从成员重新历练。")
            elif action == "hq_exam":
                if state["active"] or member["world"] != player.world or site != "hq" or member["site"] == "hq" or member["rank"] != 2 or influence < 600:
                    raise ValueError("分部特使须累积600影响力、完成当前委托，前往本界总部参加调任考核")
                required = max(1, deps._merchant_realm_cap(player.world) - 3)
                if player.realm_index < required or combat_power(player) < expected_combat_power(required, 1):
                    raise ValueError(f"考核需至少{REALMS[required].name}修为与相应基础实战能力")
                state["influence"][influence_key] -= 600
                member.update(site="hq", rank=1)
                deps._merchant_notice(game, "总部实战资历考核通过，调任总部使节；跨界商盟使节可启用逆灵通道。")
            elif action == "accept":
                if state["active"]:
                    raise ValueError("一次只能接取一个商盟委托")
                task = next((row for row in deps._merchant_board(game, alliance) if row["id"] == payload.get("task_id")), None)
                if not task:
                    raise ValueError("委托已刷新或已完成")
                task.update(worked=0, influence_key=influence_key, existing_artifacts=[row["id"] for row in player.crafted_artifacts])
                task["existing_talismans"] = [row["id"] for row in player.talismans]
                state["active"] = task
            elif action == "work":
                deps._merchant_work(game, rng)
            elif action == "abandon":
                state["active"] = None
            elif action == "post":
                deps._merchant_post(game, alliance, payload)
            elif action == "passage":
                if state["active"]:
                    raise ValueError("请先完成或放弃当前商盟任务")
                deps._merchant_passage(game, alliance, str(payload.get("destination", "")))
                deps._ensure_market(game, rng)
            else:
                raise ValueError("未知商盟操作")
    game.rng_state = encode_rng(rng)
    game.updated_at = now_iso()
    result = deps.present(game)
    deps.store.save(game)
    if committed:
        committed(game)
    return result


def _merchant_post(deps: MerchantActionDependencies, game, alliance, payload):
    state = game.merchant_state
    if sum(row["status"] in {"open", "working"} for row in state["posted"]) >= 12:
        raise ValueError("最多同时发布12个委托")
    quote = deps._merchant_quote(game, alliance, payload)
    if payload.get("preview_token") and payload["preview_token"] != quote["preview_token"]:
        raise ValueError("委托条件或报价已变化，请重新预览")
    if not has_item(game.player, "spirit_stone", quote["total"]):
        raise ValueError(f"发布需悬赏本金 {quote['principal']:,} + 手续费 {quote['fee']:,} 灵石")
    remove_item(game.player, "spirit_stone", quote["total"])
    state["sequence"] += 1
    years = quote["years"]
    state["posted"].append(copy.deepcopy(quote) | {
        "id": state["sequence"], "world": game.player.world, "alliance_id": alliance["id"],
        "posted_age": game.player.age, "check_age": game.player.age + max(1, years // 3),
        "deadline": game.player.age + years * 4, "status": "open",
        "accept_chance": min(.85, .3 + .15 * quote["principal"] / quote["minimum"]),
    })
    terminal = [row for row in state["posted"] if row["status"] not in {"open", "working"}]
    for old in terminal[:-30]:
        state["posted"].remove(old)
