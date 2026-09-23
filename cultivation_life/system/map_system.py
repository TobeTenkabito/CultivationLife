from __future__ import annotations

import hashlib
import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


class MapContentError(ValueError):
    """地图内容包或路线配置不合法。"""


QI_SOURCES = {"spirit", "demon", "monster", "yin"}
COMBAT_TERRAINS = {"狭窄", "开阔", "险要"}
COMBAT_CONDITIONS = {"禁空", "禁神识", "大阵"}


@dataclass(frozen=True)
class TravelPlan:
    origin: str
    destination: str
    base_years: int
    years: int
    route: tuple[str, ...]
    status: str
    warning: str


class MapCatalog:
    """加载地图内容，并负责寻路、境界限制与地域内容分流。"""

    def __init__(self, document: dict[str, Any], expected_worlds: set[str] | None = None):
        self.settings = dict(document.get("settings", {}))
        self.worlds = dict(document.get("worlds", {}))
        self._locations: dict[str, dict[str, dict[str, Any]]] = {}
        self._graphs: dict[str, dict[str, list[tuple[str, int]]]] = {}
        self._validate(expected_worlds)

    @classmethod
    def load(cls, path: Path, expected_worlds: set[str] | None = None) -> "MapCatalog":
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MapContentError(f"无法读取地图内容 {path.name}：{error}") from error
        return cls(document, expected_worlds)

    def _validate(self, expected_worlds: set[str] | None) -> None:
        if expected_worlds is not None and set(self.worlds) != expected_worlds:
            missing = sorted(expected_worlds - set(self.worlds))
            extra = sorted(set(self.worlds) - expected_worlds)
            raise MapContentError(f"地图世界配置不完整；缺少 {missing}，多出 {extra}")
        speeds = self.settings.get("travel_speed_by_realm", {})
        if set(speeds) != {str(index) for index in range(13)} or any(float(value) <= 0 for value in speeds.values()):
            raise MapContentError("地图移动速度必须覆盖凡人至大罗且均为正数")
        coverage = float(self.settings.get("regional_coverage", 0))
        if not 0 < coverage < 1:
            raise MapContentError("地域商品覆盖率必须位于 0 与 1 之间")
        for world_id, world in self.worlds.items():
            rows = world.get("locations", [])
            indexed = {str(row.get("id")): dict(row) for row in rows if row.get("id")}
            if len(indexed) < 2 or len(indexed) != len(rows):
                raise MapContentError(f"{world_id} 至少需要两个且 ID 唯一的地图")
            if world.get("default") not in indexed:
                raise MapContentError(f"{world_id} 的默认地图不存在")
            for location_id, location in indexed.items():
                efficiencies = location.get("qi_gain_efficiencies", {})
                if (
                    set(efficiencies) != QI_SOURCES
                    or any(not isinstance(value, (int, float)) or value < 0 for value in efficiencies.values())
                ):
                    raise MapContentError(f"{world_id}/{location_id} 必须完整配置四种气的非负获取效率")
                if location.get("combat_terrain") not in COMBAT_TERRAINS:
                    raise MapContentError(f"{world_id}/{location_id} 必须配置且只能配置一个自然战斗场地")
                conditions = location.get("combat_conditions", [])
                if (
                    not isinstance(conditions, list)
                    or len(conditions) != len(set(conditions))
                    or any(value not in COMBAT_CONDITIONS for value in conditions)
                ):
                    raise MapContentError(f"{world_id}/{location_id} 包含无效的人工战斗条件")
            graph = {location_id: [] for location_id in indexed}
            for route in world.get("routes", []):
                first, second, years = route.get("from"), route.get("to"), int(route.get("years", 0))
                if first not in indexed or second not in indexed or first == second or years <= 0:
                    raise MapContentError(f"{world_id} 存在无效地图路线")
                graph[first].append((second, years))
                graph[second].append((first, years))
            reachable = self._reachable(graph, str(world["default"]))
            if reachable != set(indexed):
                raise MapContentError(f"{world_id} 存在无法抵达的孤立地图")
            self._locations[world_id] = indexed
            self._graphs[world_id] = graph

    @staticmethod
    def _reachable(graph: dict[str, list[tuple[str, int]]], start: str) -> set[str]:
        seen, stack = set(), [start]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(node for node, _ in graph[current] if node not in seen)
        return seen

    def default_location(self, world: str) -> str:
        if world not in self.worlds:
            raise MapContentError(f"未知界面：{world}")
        return str(self.worlds[world]["default"])

    def normalize_location(self, world: str, location_id: str | None) -> str:
        return location_id if location_id in self._locations.get(world, {}) else self.default_location(world)

    def location(self, world: str, location_id: str) -> dict[str, Any]:
        try:
            return self._locations[world][location_id]
        except KeyError as error:
            raise MapContentError("目标地图不属于当前界面") from error

    def qi_gain_efficiencies(self, world: str, location_id: str | None) -> dict[str, float]:
        location = self.location(world, self.normalize_location(world, location_id))
        return {source: float(location["qi_gain_efficiencies"][source]) for source in QI_SOURCES}

    def travel_plan(
        self, world: str, origin: str, destination: str, realm_index: int,
        travel_multiplier: float = 1.0,
    ) -> TravelPlan:
        origin = self.normalize_location(world, origin)
        target = self.location(world, destination)
        if origin == destination:
            raise MapContentError("你已经身在此地")
        distances: dict[str, int] = {origin: 0}
        previous: dict[str, str] = {}
        queue: list[tuple[int, str]] = [(0, origin)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances.get(node):
                continue
            if node == destination:
                break
            for neighbor, cost in self._graphs[world][node]:
                candidate = distance + cost
                if candidate < distances.get(neighbor, 10**18):
                    distances[neighbor] = candidate
                    previous[neighbor] = node
                    heapq.heappush(queue, (candidate, neighbor))
        if destination not in distances:
            raise MapContentError("目前没有通往目标地图的路线")
        route = [destination]
        while route[-1] != origin:
            route.append(previous[route[-1]])
        route.reverse()
        base_years = distances[destination]
        speed = float(self.settings["travel_speed_by_realm"][str(max(0, min(12, realm_index)))])
        years = max(1, math.ceil(base_years * speed * max(0.05, float(travel_multiplier))))
        required = int(target.get("min_realm_index", 0))
        status, warning = "ok", ""
        if realm_index < required:
            status = "lethal"
            warning = str(
                target.get("failure_reason")
                or f"你的境界低于此地要求（境界序号 {required}），抵达后必然身死道消"
            )
        return TravelPlan(origin, destination, base_years, years, tuple(route), status, warning)

    def localize_goods(
        self, goods: Iterable[dict[str, Any]], world: str, location_id: str, purpose: str,
    ) -> list[dict[str, Any]]:
        """按世界、地图、用途和档位稳定分流，且保证每类每阶至少有一项地方来源。"""
        location_id = self.normalize_location(world, location_id)
        candidates = [dict(good) for good in goods if good.get("world", "human") == world]
        groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for good in candidates:
            key = (int(good.get("tier", 0)), str(good.get("kind", "item")))
            groups.setdefault(key, []).append(good)
        coverage = float(self.settings["regional_coverage"])
        result: list[dict[str, Any]] = []
        for rows in groups.values():
            ranked = sorted(rows, key=lambda row: self._regional_score(world, location_id, purpose, str(row["content_id"])))
            selected = [
                row for row in ranked
                if self._regional_score(world, location_id, purpose, str(row["content_id"])) < coverage
            ]
            result.extend(selected or ranked[:1])
        return result

    @staticmethod
    def _regional_score(world: str, location_id: str, purpose: str, content_id: str) -> float:
        digest = hashlib.blake2b(
            f"{world}:{location_id}:{purpose}:{content_id}".encode("utf-8"), digest_size=8,
        ).digest()
        return int.from_bytes(digest, "big") / float(2**64 - 1)

    def public_map(
        self, world: str, current: str, realm_index: int, world_name: str,
        travel_multiplier_for: Callable[[str], float] | None = None,
    ) -> dict[str, Any]:
        current = self.normalize_location(world, current)
        locations = []
        for location_id, row in self._locations[world].items():
            if location_id == current:
                plan = None
                status, warning, years, route_names = "current", "", 0, [row["name"]]
            else:
                multiplier = travel_multiplier_for(location_id) if travel_multiplier_for else 1.0
                plan = self.travel_plan(world, current, location_id, realm_index, multiplier)
                status, warning, years = plan.status, plan.warning, plan.years
                route_names = [self._locations[world][node]["name"] for node in plan.route]
            locations.append({
                **row, "current":location_id == current, "travel_years":years,
                "travel_status":status, "warning":warning, "route_names":route_names,
            })
        return {
            "world":world, "world_name":world_name, "current":current,
            "current_name":self._locations[world][current]["name"], "locations":locations,
            "current_qi_gain_efficiencies":self.qi_gain_efficiencies(world, current),
            "regional_market":True, "regional_treasure":True,
        }
