"""Explicit operations for state."""

from __future__ import annotations

import copy
import random

from ...content_registry import REALMS, WORLD_SYSTEMS
from ...models import HistoryRecord, SectNpc
from ...rules import expected_combat_power
from ..exchange_system import EXCHANGE_VENUES
from ..merchant_definitions import CROSS_ALLIANCES, POLICIES
from .dependencies import MerchantStateDependencies


def _merchant_realm_cap(world):
    profile = WORLD_SYSTEMS["world_profiles"][world]
    return int(profile.get("npc_realm_cap", {1: 5, 2: 8, 3: 12}[int(profile["tier"])]))


def _ensure_merchant(deps: MerchantStateDependencies, game) -> bool:
    if game.merchant_state.get("version") == 2:
        return False
    if game.merchant_state.get("version") == 1:
        return deps._migrate_merchant_routes(game)
    state = game.merchant_state = {
        "version": 2, "worlds": {}, "membership": None, "influence": {},
        "posted": [], "active": None, "completed": [], "notices": [],
        "last_age": game.player.age, "sequence": 0,
    }
    for world, geography in deps.maps.worlds.items():
        profile = WORLD_SYSTEMS["world_profiles"][world]
        if profile['tier'] <= 0:
            continue
        safe = [row["id"] for row in geography["locations"] if not row.get("min_realm_index")]
        headquarters = EXCHANGE_VENUES[world]
        sites = [place for place in safe if place != headquarters]
        ids = [key for key, (_, _, worlds) in CROSS_ALLIANCES.items() if world in worlds]
        ids += [f"{world}-{index}" for index in range(3 - len(ids))]
        alliances = []
        for index, alliance_id in enumerate(ids):
            rng = random.Random(f"merchant:{game.seed}:{world}:{alliance_id}")
            cross = CROSS_ALLIANCES.get(alliance_id)
            name = cross[0] if cross else WORLD_SYSTEMS["world_names"][world] + ["通宝商盟", "万珍商盟", "聚贤商盟"][index]
            realm_index = deps._merchant_realm_cap(world)
            leader = SectNpc(f"merchant-{world}-{alliance_id}-leader", rng.choice(["沈", "陆", "宁", "虞"]) + rng.choice(["望舒", "玄衡", "听澜", "怀璧"]),
                             "分盟主" if cross and world != cross[1] else "盟主", realm_index,
                             REALMS[realm_index].layers, 100, None, world=world)
            locations = sites[index::3] or sites[:1]
            locations = locations[:3]
            chief_realm = 8 if alliance_id in {"xuanji", "jiukun"} else realm_index
            chief_power = expected_combat_power(chief_realm, REALMS[chief_realm].layers) * 35
            offices = []
            for site in locations:
                deputy = copy.deepcopy(leader)
                deputy.id += f"-{site}"
                deputy.name = rng.choice(["许", "苏", "秦"]) + rng.choice(["青川", "知微", "照月"])
                deputy.title = "分部主事"
                deputy.realm_index = max(1, realm_index - 1)
                deputy.layer = REALMS[deputy.realm_index].layers
                offices.append({"location_id": site, "leader": deputy.to_dict()})
            alliances.append({
                "id": alliance_id, "name": name, "world": world, "hq": headquarters,
                "home_world": cross[1] if cross else world, "linked_worlds": cross[2] if cross else [world],
                "cross_world": bool(cross), "leader": leader.to_dict(), "offices": offices,
                "chief_name": {"xuanji": "璇玑子", "jiukun": "九坤上人", "taiyuan": "太元道君"}.get(alliance_id, leader.name),
                "chief_realm": chief_realm, "chief_power": chief_power if cross else 0,
                "reserves": (250000 if cross else 8000) * int(profile["tier"]),
                "policy": list(POLICIES)[index], "next_policy_age": game.player.age + 12 + index * 3,
                "relation": "互通有无", "board_epoch": 0,
            })
        state["worlds"][world] = alliances
    return True


def _merchant_alliance(game, world, alliance_id):
    return next((row for row in game.merchant_state["worlds"].get(world, []) if row["id"] == alliance_id), None)


def _merchant_site(game, alliance):
    if game.player.world != alliance["world"]:
        return None
    location = game.player.location_id
    if location == alliance["hq"]:
        return "hq"
    if any(row["location_id"] == location for row in alliance["offices"]):
        return location
    return None


def _merchant_influence_key(member):
    return f"{member['world']}:{member['alliance_id']}:{'hq' if member['site'] == 'hq' else 'offices'}"


def _merchant_power(alliance):
    leader = alliance["leader"]
    power = expected_combat_power(leader["realm_index"], leader["layer"])
    power += sum(expected_combat_power(row["leader"]["realm_index"], row["leader"]["layer"]) for row in alliance["offices"])
    return round(power + alliance["chief_power"] + len(alliance["offices"]) * 5000 + alliance["reserves"] * 2)


def _merchant_notice(game, message):
    notices = game.merchant_state["notices"]
    notices.append({"age": game.player.age, "message": message})
    del notices[:-30]
    game.history.append(HistoryRecord("SYS_MERCHANT", 1, game.player.age, "商盟传讯", None, "notice", message, {}, ["system", "merchant", "world:global"]))


def _merchant_materials(deps: MerchantStateDependencies, world):
    return sorted((row for row in deps._crafting_material_defs().values() if row.get("world") == world),
                  key=lambda row: (int(row.get("tier", 1)), row["id"]))
