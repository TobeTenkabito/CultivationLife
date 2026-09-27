"""World movement: pure route planning, then one authoritative commit.

No DLC, merchant or engine imports. Business entry points authorize their own
costs/trials. Direction describes geography, never permission or cleanup.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class TransitionDirection(str, Enum):
    ASCEND = "ascend"
    LATERAL = "lateral"
    DESCEND = "descend"


class TransitionMode(str, Enum):
    PROGRESSION = "progression"
    SEALED_DESCENT = "sealed_descent"
    SEALED_RETURN = "sealed_return"
    PASSAGE = "passage"
    STORY = "story"


@dataclass(frozen=True, slots=True)
class WorldTransitionRequest:
    destination: str
    mode: TransitionMode
    route_id: str
    reason: str = ""
    arrival_location: str | None = None


@dataclass(frozen=True, slots=True)
class WorldTransitionPlan:
    source: str
    destination: str
    direction: TransitionDirection
    mode: TransitionMode
    route_id: str
    reason: str
    arrival_location: str
    source_rank: tuple[int, int]
    target_rank: tuple[int, int]
    seal_action: str
    seal_snapshot: dict | None


@dataclass(frozen=True, slots=True)
class WorldTransitionResult:
    source: str
    destination: str
    direction: TransitionDirection
    mode: TransitionMode
    route_id: str
    suppressed: bool


@dataclass(frozen=True, slots=True)
class WorldTransitionPorts:
    cancel_auction: Callable
    clear_market: Callable
    permanent_departure: Callable


def classify_transition(profiles, source, destination):
    if source not in profiles or destination not in profiles or source == destination:
        raise ValueError("目标界面无效")
    difference = profiles[destination]["tier"] - profiles[source]["tier"]
    return TransitionDirection.ASCEND if difference > 0 else TransitionDirection.DESCEND if difference < 0 else TransitionDirection.LATERAL


def validate_transition_content(profiles, routes, realms):
    for world, profile in profiles.items():
        if (profile.get("kind") != "world" or type(profile.get("tier")) is not int
                or profile["tier"] < 1 or type(profile.get("enabled")) is not bool):
            raise ValueError(f"界面 {world} 的类型、等级或开关不合法")
        for field in ("cultivation_ceiling", "passage_ceiling"):
            ceiling = profile.get(field)
            if ceiling is not None:
                rank, layer = ceiling.get("realm_index"), ceiling.get("layer")
                if (type(rank) is not int or type(layer) is not int or not 0 <= rank < len(realms)
                        or not 1 <= layer <= realms[rank].layers):
                    raise ValueError(f"界面 {world} 的修为上限不合法")
    seen = set()
    for route in routes:
        if not route.get("id") or route["id"] in seen:
            raise ValueError("跨界路线编号缺失或重复")
        seen.add(route["id"])
        direction = classify_transition(profiles, route["source"], route["destination"])
        mode = TransitionMode(route["mode"])
        if type(route.get("enabled")) is not bool:
            raise ValueError("跨界路线必须声明开关")
        if mode == TransitionMode.SEALED_RETURN:
            raise ValueError("返界授权仅能来自当前封印")
        if mode == TransitionMode.SEALED_DESCENT and direction != TransitionDirection.DESCEND:
            raise ValueError("封印下界路线必须通往低阶界面")
        if route.get("generic_cross_world") and mode != TransitionMode.SEALED_DESCENT:
            raise ValueError("普通跨界入口只能公开既有下界路线")


def cultivation_ceiling(systems, world, *, passage=False):
    profile = systems["world_profiles"][world]
    if passage and profile.get("passage_ceiling") is not None:
        value = profile["passage_ceiling"]
    elif "cultivation_ceiling" in profile:
        value = profile["cultivation_ceiling"]
    else:
        # Compatibility for old content documents, independent of NPC spawn caps.
        rules = systems.get("world_travel", {})
        prefix = {1: "human", 2: "spirit"}.get(profile["tier"])
        value = ({"realm_index": rules.get(f"{prefix}_suppression_realm", 5 if profile["tier"] == 1 else 8),
                  "layer": rules.get(f"{prefix}_suppression_layer", 3 if profile["tier"] == 1 else 9)} if prefix else None)
    return (int(value["realm_index"]), int(value["layer"])) if value else None


def normalized_seal(player):
    if not player.sealed_cultivation:
        return None
    seal = copy.deepcopy(player.sealed_cultivation)
    # The oldest saves predate every route except spirit -> human.
    seal.setdefault("return_world", seal.get("upper_world", "spirit"))
    seal.setdefault("suppressed_world", seal.get("lower_world", "human"))
    seal.setdefault("upper_world", seal["return_world"])
    seal.setdefault("lower_world", seal["suppressed_world"])
    return seal


def plan_world_transition(game, request, systems, maps):
    player = game.player
    profiles = systems["world_profiles"]
    direction = classify_transition(profiles, player.world, request.destination)
    if not profiles[request.destination].get("enabled", False):
        raise ValueError("目标界面尚未开放")
    mode = TransitionMode(request.mode)
    seal = normalized_seal(player)
    route = None
    if mode == TransitionMode.SEALED_RETURN:
        if (not seal or player.world != seal["suppressed_world"] or request.destination != seal["return_world"]
                or request.route_id != "sealed_return" or seal.get("merchant_passage")):
            raise ValueError("你没有可在目标上界复原的封存道果")
    else:
        route = next((row for row in systems["world_transition_routes"] if row["id"] == request.route_id), None)
        if (not route or not route["enabled"] or route["source"] != player.world
                or route["destination"] != request.destination or route["mode"] != mode.value):
            raise ValueError("此玩法没有获准的跨界路线")
    recovery = bool(route and route.get("seal_recovery"))
    if seal and mode not in {TransitionMode.SEALED_RETURN, TransitionMode.PASSAGE} and not recovery:
        raise ValueError("请先返回原界解除现有封印，不能叠加跨界封印")
    if seal and mode == TransitionMode.PASSAGE and not seal.get("merchant_passage"):
        raise ValueError("普通下界封印须循原路返界解除")
    current = (player.realm_index, player.layer)
    actual = (int(seal["realm_index"]), int(seal["layer"])) if seal else current
    target, action = current, "none"
    if mode == TransitionMode.SEALED_RETURN or recovery:
        if not seal:
            raise ValueError("没有需要恢复的道果")
        target, action = actual, "restore"
    elif mode in {TransitionMode.SEALED_DESCENT, TransitionMode.PASSAGE}:
        ceiling = cultivation_ceiling(systems, request.destination, passage=mode == TransitionMode.PASSAGE)
        if ceiling and actual > ceiling:
            target, action = ceiling, "seal"
        elif seal:
            target, action = actual, "restore"
    location = request.arrival_location or maps.default_location(request.destination)
    site = maps.location(request.destination, location)
    if target[0] < int(site.get("min_realm_index", 0)):
        raise ValueError("跨界落点的境界要求高于你抵达后的修为")
    return WorldTransitionPlan(player.world, request.destination, direction, mode, request.route_id,
                               request.reason, location, current, target, action, copy.deepcopy(player.sealed_cultivation))


def apply_world_transition(game, plan, ports, *, entourage=None):
    """Commit a validated plan. Market generation stays at the action's RNG boundary.

    The engine's market adapter finalizes the invalidated market after court,
    founder and event effects, preserving the established seeded RNG order.
    """
    from ..rules import max_hp, max_mp
    player = game.player
    if (player.world != plan.source or (player.realm_index, player.layer) != plan.source_rank
            or player.sealed_cultivation != plan.seal_snapshot):
        raise ValueError("跨界计划已失效，请重新规划")
    hp, mp = player.hp / max(1, max_hp(player)), player.mp / max(1, max_mp(player))
    ports.cancel_auction(game)
    if plan.mode == TransitionMode.PROGRESSION:
        keep_companion, keep_ids = False, set()
        if entourage:
            keep_companion, keep_ids = entourage.commit(game, plan.destination)
        ports.permanent_departure(game, keep_companion=keep_companion, keep_friend_ids=keep_ids)
    seal = normalized_seal(player)
    if plan.seal_action == "seal":
        seal = seal or {"realm_index": player.realm_index, "layer": player.layer,
                        "lifespan": player.lifespan, "return_world": plan.source, "upper_world": plan.source,
                        "tribulation_remaining": max(0, player.next_tribulation_age - player.age)
                        if player.next_tribulation_age is not None else None}
        seal.update(suppressed_world=plan.destination, lower_world=plan.destination,
                    route_id=plan.route_id, reason=plan.reason, hp_ratio=hp, mp_ratio=mp)
        if plan.mode == TransitionMode.PASSAGE:
            seal["merchant_passage"] = True
        player.sealed_cultivation = seal
        player.realm_index, player.layer = plan.target_rank
    elif plan.seal_action == "restore":
        player.realm_index, player.layer = plan.target_rank
        player.lifespan = seal.get("lifespan")
        remaining = seal.get("tribulation_remaining")
        player.next_tribulation_age = player.age + int(remaining) if remaining is not None else None
        player.sealed_cultivation = None
    player.world = plan.destination
    player.location_id = plan.arrival_location
    if plan.mode != TransitionMode.PROGRESSION:
        player.party = []
        player.awaiting_major_breakthrough = False
        player.awaiting_minor_breakthrough = False
        player.awaiting_spirit_realm_crossing = False
        player.active_breakthrough_aids = []
        player.hp, player.mp = max_hp(player) * hp, max_mp(player) * mp
    ports.clear_market(game)
    result = WorldTransitionResult(plan.source, plan.destination, plan.direction, plan.mode,
                                   plan.route_id, bool(player.sealed_cultivation))
    game._pending_world_market = result
    return result


def finish_world_transition(game, rng, refresh_market):
    """Finish at the existing action boundary, after all business RNG draws."""
    pending = getattr(game, "_pending_world_market", None)
    if pending and game.player.world != pending.destination:
        raise ValueError("跨界坊市结算与目的界面不一致")
    changed = refresh_market(game, rng)
    if pending:
        del game._pending_world_market
    return changed


@dataclass(frozen=True, slots=True)
class EntourageManifest:
    companion_kept: bool
    survivor_ids: frozenset[str]
    survivor_names: tuple[str, ...]
    fallen_names: tuple[str, ...]
    snapshots: tuple[tuple[str, bool, str], ...]

    def __iter__(self):
        yield self.companion_kept
        yield set(self.survivor_ids)
        yield list(self.survivor_names)
        yield list(self.fallen_names)

    def commit(self, game, destination):
        player = game.player
        people = [*game.world_npcs.values(), *game.notable_npcs.values(),
                  *(npc for sect in game.sects.values() for npc in sect.npcs),
                  *(game.family.npcs if game.family else [])]
        records = [*player.dao_friends, *([player.dao_companion] if player.dao_companion else [])]
        for npc_id, alive, reason in self.snapshots:
            for row in records:
                if str(row.get("id")) == npc_id:
                    if alive:
                        row["world"] = destination
                    else:
                        row.update(alive=False, death_reason=reason)
            for npc in people:
                if npc.id == npc_id:
                    if alive:
                        npc.world, npc.departed_age, npc.departure_reason = destination, npc.age, reason
                    else:
                        npc.alive, npc.death_reason = False, reason
        return self.companion_kept, set(self.survivor_ids)
