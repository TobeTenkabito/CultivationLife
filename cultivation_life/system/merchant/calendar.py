"""Explicit operations for calendar."""

from __future__ import annotations
from ..merchant_definitions import intelligence_route

import copy
import random

from ...models import SectNpc
from ..merchant_definitions import POLICIES
from .dependencies import MerchantCalendarDependencies
from ..economy.ledger import transfer_value, balance
from ..economy.caravans import treasury


def _advance_merchant_year(deps: MerchantCalendarDependencies, game):
    deps._ensure_merchant(game)
    state = game.merchant_state
    if game.player.age <= state["last_age"]:
        return
    state["last_age"] = game.player.age
    for world, alliances in state["worlds"].items():
        for alliance in alliances:
            if game.player.age < alliance["next_policy_age"]:
                continue
            rng = random.Random(f"merchant-policy:{game.seed}:{world}:{alliance['id']}:{alliance['next_policy_age']}")
            policies = [key for key in POLICIES if key != alliance["policy"]]
            weights = [1.0] * len(policies)
            if deps._intrigue_enabled():
                npc = SectNpc.from_dict(alliance["leader"])
                personality = deps._ensure_intrigue_personality(game, npc)["primary"]
                preferred = "economy" if personality in {"greedy", "smooth", "open"} else "materials" if personality in {"suspicious", "conservative", "paranoid"} else "cultivation"
                weights = [4.0 if key == preferred else 1.0 for key in policies]
            alliance["policy"] = rng.choices(policies, weights)[0]
            alliance["next_policy_age"] = game.player.age + rng.randint(12, 24)
            alliance["board_epoch"] += 1
            occupied = {alliance["hq"], *(row["location_id"] for row in alliance["offices"])}
            expansion = [row["id"] for row in deps.maps.worlds[world]["locations"]
                         if not row.get("min_realm_index") and row["id"] not in occupied]
            if not alliance.get('player_owned') and expansion and alliance['reserves'] >= 40000 and rng.random() < .2:
                location = rng.choice(expansion)
                deputy = copy.deepcopy(alliance["offices"][0]["leader"] if alliance['offices'] else alliance['leader'])
                deputy.update(id=f"merchant-{world}-{alliance['id']}-{location}", name=rng.choice(["叶知秋", "方清和", "江行远"]))
                alliance["offices"].append({"location_id": location, "leader": deputy})
                transfer_value(game, treasury(world, alliance['id']), f'background:{world}', 10000, '商盟分部建设')
            elif not alliance.get('player_owned') and len(alliance["offices"]) > 1 and alliance["reserves"] < 3000:
                member = state["membership"] or {}
                removable = [office for office in alliance["offices"] if not (
                    member.get("world") == world and member.get("alliance_id") == alliance["id"]
                    and member.get("site") == office["location_id"])]
                from ..economy.fleet_network import active_fleets
                if removable and len(active_fleets(game, world, 'alliance', alliance['id'])) <= len(alliance['offices']) * 3:
                    alliance["offices"].remove(removable[-1])
                    refund = min(2000, balance(game, f'background:{world}'))
                    transfer_value(game, f'background:{world}', treasury(world, alliance['id']), refund, '商盟撤部资产出售')
            rival = rng.choice([row for row in alliances if row is not alliance])
            if rng.random() < .5:
                alliance["relation"] = f"与{rival['name']}合作通商"
            else:
                alliance["relation"] = f"与{rival['name']}竞争商路"
    for order in state["posted"]:
        if order["status"] not in {"open", "working"}:
            continue
        alliance = deps._merchant_alliance(game, order["world"], order["alliance_id"])
        if not deps._merchant_route_exists(game, alliance, order["source_world"]) and not (alliance and order["kind"] == "intel" and intelligence_route(game, order["source_world"])):
            deps._merchant_refund(game, order, "cancelled", "目标界面未设本盟总部，商路不可用", order["fee"])
            continue
        if not deps._merchant_commission_available(order):
            deps._merchant_refund(game, order, "cancelled", "所需内容当前不可用")
            continue
        if order.get("target_id"):
            target = deps._find_npc(game, order["target_id"])
            if not target or not target.alive:
                deps._merchant_refund(game, order, "cancelled", "悬赏目标已失效")
                continue
        if order["status"] == "open":
            if game.player.age >= order["deadline"]:
                deps._merchant_refund(game, order, "cancelled", "长期无人接取，已逾期")
                continue
            if game.player.age >= order["check_age"]:
                rng = random.Random(f"merchant-order:{game.seed}:{order['id']}:{order['check_age']}")
                order["check_age"] = game.player.age + max(1, order["years"] // 3)
                if rng.random() < order["accept_chance"]:
                    deps._merchant_start_order(game, order, rng)
        if order["status"] == "working":
            deps._merchant_tick_order(game, order)
