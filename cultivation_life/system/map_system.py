from __future__ import annotations

import hashlib
import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from .map_definition import (MapDefinition, MapContentError as MapContentError,
    QI_SOURCES as QI_SOURCES, COMBAT_TERRAINS as COMBAT_TERRAINS, COMBAT_CONDITIONS as COMBAT_CONDITIONS)


@dataclass(frozen=True)
class TravelPlan:
    origin: str
    destination: str
    base_years: int
    years: int
    route: tuple[str, ...]
    status: str
    warning: str


class MapCatalog(MapDefinition):
    """加载地图内容，并负责寻路、境界限制与地域内容分流。"""

    @classmethod
    def load(cls, path: Path, expected_worlds: set[str] | None = None) -> "MapCatalog":
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MapContentError(f"无法读取地图内容 {path.name}：{error}") from error
        return cls(document, expected_worlds)

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
            from ..content_registry import REALMS

            status = "lethal"
            warning = str(
                target.get("failure_reason")
                or f"你的境界低于此地要求（至少需{REALMS[required].name}境），抵达后必然身死道消"
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
