"""Map validation and indexed topology independent of the loaded content registry."""
from __future__ import annotations
from typing import Any


class MapContentError(ValueError):
    """地图内容包或路线配置不合法。"""


QI_SOURCES = {"spirit", "demon", "monster", "yin"}


COMBAT_TERRAINS = {"狭窄", "开阔", "险要"}


COMBAT_CONDITIONS = {"禁空", "禁神识", "大阵"}


class MapDefinition:
    def __init__(self, document: dict[str, Any], expected_worlds: set[str] | None = None):
        self.settings = dict(document.get("settings", {}))
        self.worlds = dict(document.get("worlds", {}))
        self._locations: dict[str, dict[str, dict[str, Any]]] = {}
        self._graphs: dict[str, dict[str, list[tuple[str, int]]]] = {}
        self._validate(expected_worlds)

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
