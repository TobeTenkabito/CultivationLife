"""Explicit operations for presentation."""

from __future__ import annotations

import copy

from ...content_registry import REALMS, WORLD_SYSTEMS
from ..merchant_definitions import KINDS as KINDS
from ..merchant_definitions import METRICS, POLICIES, RANKS
from .dependencies import MerchantViewDependencies
from ..economy.fleet_network import route_open, member_of


def _public_merchant(deps: MerchantViewDependencies, game):
    if WORLD_SYSTEMS['world_profiles'][game.player.world]['tier'] <= 0:
        return {'available': False}
    deps._ensure_merchant(game)
    state = game.merchant_state
    member = state["membership"]
    membership = None
    if member:
        home = deps._merchant_alliance(game, member["world"], member["alliance_id"])
        world_name = WORLD_SYSTEMS["world_names"][member["world"]]
        office_name = ("总部" if home["home_world"] == member["world"] else "分总部") if member["site"] == "hq" else deps.maps.location(member["world"], member["site"])["name"] + "分部"
        membership = copy.deepcopy(member) | {"title": f"{home['name']} {world_name}{office_name} {RANKS[member['rank']]}",
                    "influence": state["influence"].get(deps._merchant_influence_key(member), 0)}
    visible = []
    for alliance in state["worlds"][game.player.world]:
        owned = member_of(game, alliance)
        site = deps._merchant_site(game, alliance)
        row = {key: copy.deepcopy(alliance[key]) for key in ("id", "name", "world", "hq", "home_world", "cross_world", "linked_worlds", "reserves", "relation", "policy", "next_policy_age")}
        row.update(policy_name=POLICIES[alliance["policy"]], power=deps._merchant_power(alliance),
                   hq_name=deps.maps.location(game.player.world, alliance["hq"])["name"],
                   leader_name=alliance["leader"]["name"], leader_realm=REALMS[alliance["leader"]["realm_index"]].name,
                   chief_name=alliance["chief_name"], chief_realm=REALMS[alliance["chief_realm"]].name,
                   chief_power=round(alliance["chief_power"]), local_site=site, member=owned,
                   offices=[{"location_id": office["location_id"], "name": deps.maps.location(game.player.world, office["location_id"])["name"],
                             "leader": office["leader"]["name"], "realm": REALMS[office["leader"]["realm_index"]].name} for office in alliance["offices"]],
                   tasks=deps._merchant_board(game, alliance) if owned else [])
        row["destinations"] = [{"id": world, "name": WORLD_SYSTEMS["world_names"][world],
                                 "cost": deps._merchant_passage_cost(game, world),
                                 "open": route_open(game, alliance, world)} for world in alliance["linked_worlds"] if world != game.player.world] if owned else []
        row["catalog"] = deps._merchant_procurement_catalog(game, alliance) if owned else []
        from ..economy.caravans import public_caravans
        row['caravans'] = public_caravans(game, deps.maps, alliance['id'])
        from ..teleport_system import separated
        row['teleports'] = [{'id': key, 'name': deps.maps.location(game.player.world, key)['name']}
            for key in [alliance['hq'], *(o['location_id'] for o in alliance['offices'])]
            if owned and site and separated(deps.maps, game.player.world, game.player.location_id, key)]
        visible.append(row)
    orders = copy.deepcopy(state["posted"])
    for order in orders:
        order.pop("will_finish", None)
        order.pop("failure_age", None)
        order.pop("accept_chance", None)
        order["progress"] = min(.99, max(0, (game.player.age - order.get("started_age", game.player.age)) / order["years"])) if order["status"] == "working" else 1 if order["status"] == "completed" else order.get("progress", 0)
    return {"alliances": visible, "membership": membership, "active": copy.deepcopy(state["active"]),
            "posted": orders, "notices": copy.deepcopy(state["notices"]), "kinds": KINDS,
            "hired_hands": state.get("hired_hands", 0), "year": game.player.age,
            "molds": [{"id": row["id"], "name": row["name"], "description": row["rule"].get("description", "")} for row in deps._crafting_molds().values()],
            "metric_names": METRICS}
