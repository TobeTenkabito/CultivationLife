"""Explicit operations for map runtime."""

from __future__ import annotations
from typing import Any
from .content_registry import WORLD_SYSTEMS
from .system.map_system import MapContentError
from .models import HistoryRecord
from .runtime import decode_rng, encode_rng, now_iso
from .system.possession_system import advance_player_age
from .time_dependencies import MapTravelDependencies
from .time_flow import advance_elapsed_year, completed_action_units
from .system.heavens.local_control import arrival_notice

def travel_map(deps: MapTravelDependencies, game_id: str, destination: str) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if not player.alive:
        raise ValueError("此生已经结束")
    if game.pending_event:
        raise ValueError("请先处理当前事件")
    if player.imprisonment:
        raise ValueError("你身陷大牢，无法远行")
    if player.ghost_captor:
        raise ValueError("魂印受制于拘魂者，无法自行远行")
    try:
        plan = deps.maps.travel_plan(
            player.world, player.location_id or "", destination, player.realm_index,
            deps._monster_travel_multiplier(player, destination),
        )
    except MapContentError as error:
        raise ValueError(str(error)) from error
    if plan.status == "blocked":
        raise ValueError(plan.warning)
    if plan.origin == plan.destination:
        raise ValueError('已经身处此地')

    journey = game.map_journey
    if not journey or (journey['world'], journey['origin'], journey['destination'], journey['route']) != (
            player.world, plan.origin, plan.destination, list(plan.route)):
        journey = game.map_journey = dict(world=player.world, origin=plan.origin,
            destination=plan.destination, route=list(plan.route), years=plan.years, completed=0)
    remaining = journey['years'] - journey['completed']

    rng = decode_rng(game.seed, game.rng_state)
    start_age = player.age
    institution_world = player.world
    institution_unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
    # Freeze the action denominator for this journey, including after a realm
    # change or reload. Older journeys adopt it without replaying past units.
    unit_years = journey.setdefault('unit_years', institution_unit)
    settled_before = completed_action_units(journey['completed'], unit_years)
    era_news: list[str] = []
    for _ in range(remaining):
        advance_player_age(player)
        journey['completed'] += 1
        if not advance_elapsed_year(deps.year, game, rng, era_news, encounters=False):
            break
    same_origin = player.world == journey['world'] and player.location_id == journey['origin']
    completed = player.alive and game.pending_event is None and same_origin and journey['completed'] == journey['years']
    if completed:
        player.location_id = plan.destination
        game.map_journey = None
        deps._clear_market(game)
        if plan.status == "lethal":
            deps._die(game, plan.warning, "SYS_MAP_TRAVEL_DEATH")
            result = "dead"
            summary = f"你强行踏上远途，累计行进 {journey['years']} 年抵达边缘，却因{plan.warning}。"
        else:
            deps._ensure_market(game, rng)
            result = "arrived"
            route_names = [deps.maps.location(player.world, node)["name"] for node in plan.route]
            summary = f"你沿{'—'.join(route_names)}行进，累计耗时 {journey['years']} 年抵达目的地，本次续行 {player.age-start_age} 年。"
            summary += arrival_notice(game)
    else:
        result = "interrupted"
        if not player.alive or not same_origin:
            game.map_journey = None
            summary = '远行因身死或所在位置改变而结束，旧路线失效。'
        else:
            summary = f"远行暂歇，已保留 {journey['completed']}/{journey['years']} 年路程；处理变故后选择同一目的地，继续余下 {journey['years']-journey['completed']} 年。"
        deps._ensure_market(game, rng)
    game.history.append(HistoryRecord(
        "SYS_MAP_TRAVEL", 1, player.age, "跨域远行", plan.destination, result, summary,
        {"from":plan.origin, "to":plan.destination, "years":player.age - start_age,
         "completed_years":journey['completed'], "total_years":journey['years']},
        ["action", "travel", "map", f"world:{player.world}"],
    ))
    deps._finish_travel_time(game, start_age, institution_world, institution_unit, era_news, rng,
        action_units=completed_action_units(journey['completed'], unit_years) - settled_before)
    deps._compact_world_history(game)
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)
