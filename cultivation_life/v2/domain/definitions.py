from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any


QI_SOURCES = ("spirit", "demon", "monster", "yin")


@dataclass(frozen=True, slots=True)
class RealmDefinition:
    id: str
    name: str
    layers: int
    base_power: float
    opportunity_base: int
    lifespan: tuple[int, int] | None
    kill_threshold: float


@dataclass(frozen=True, slots=True)
class RootDefinition:
    id: str
    name: str
    tier: str
    efficiency: float
    elements: tuple[str, ...]
    creation: bool


@dataclass(frozen=True, slots=True)
class TechniqueDefinition:
    id: str
    name: str
    path: str
    element: str
    grade: int
    level: int
    opportunity_bonus: float
    hp_bonus: float
    mp_bonus: float
    combat_bonus: float
    category: str
    sources: dict[str, float]
    body_breakthrough_bonus: float = 0.0
    body_bonus_max_layer: int = 0
    divine_sense_bonus: float = 0.0
    transformation_capacity: int = 0
    transformation_space: int = 0

    @property
    def scale(self) -> float:
        return (1 + 0.12 * (self.grade - 1)) * (1 + 0.025 * (self.level - 1))


@dataclass(frozen=True, slots=True)
class LocationDefinition:
    id: str
    name: str
    min_realm_index: int
    failure: str
    failure_reason: str
    qi_gain_efficiencies: dict[str, float]


@dataclass(frozen=True, slots=True)
class TravelPlan:
    origin: str
    destination: str
    route: tuple[str, ...]
    base_years: int
    years: int
    accessible: bool
    warning: str


@dataclass(frozen=True, slots=True)
class WorldDefinition:
    id: str
    name: str
    tier: int
    enabled: bool
    qi_concentrations: dict[str, float]
    default_location: str
    locations: dict[str, LocationDefinition]
    routes: dict[str, tuple[tuple[str, int], ...]]

    def travel_plan(
        self,
        origin: str,
        destination: str,
        realm_index: int,
        speed_multiplier: float,
    ) -> TravelPlan:
        if origin not in self.locations:
            origin = self.default_location
        if destination not in self.locations:
            raise ValueError("目标地点不属于当前世界")
        if origin == destination:
            raise ValueError("角色已经身在此地")
        distances: dict[str, int] = {origin: 0}
        previous: dict[str, str] = {}
        queue: list[tuple[int, str]] = [(0, origin)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances.get(node):
                continue
            if node == destination:
                break
            for neighbor, cost in self.routes[node]:
                candidate = distance + cost
                if candidate < distances.get(neighbor, 10**18):
                    distances[neighbor] = candidate
                    previous[neighbor] = node
                    heapq.heappush(queue, (candidate, neighbor))
        if destination not in distances:
            raise ValueError("目前没有通往目标地点的路线")
        route = [destination]
        while route[-1] != origin:
            route.append(previous[route[-1]])
        route.reverse()
        target = self.locations[destination]
        accessible = realm_index >= target.min_realm_index
        warning = "" if accessible else (
            target.failure_reason
            or f"境界不足：目标地点要求境界序号至少为 {target.min_realm_index}"
        )
        return TravelPlan(
            origin=origin,
            destination=destination,
            route=tuple(route),
            base_years=distances[destination],
            years=max(1, math.ceil(distances[destination] * max(0.0025, speed_multiplier))),
            accessible=accessible,
            warning=warning,
        )


@dataclass(frozen=True, slots=True)
class FactionDefinition:
    id: str
    name: str
    world_id: str
    path: str
    allegiance_race: str
    description: str
    color: str


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    id: str
    name: str
    description: str
    tags: tuple[str, ...]
    combat_bonus: float
    hp_bonus: float
    mp_bonus: float
    opportunity_bonus: float
    transformation_form_id: str | None = None
    transformation_source: str = ""
    transformation_purity: float = 0.0
    breakthrough_bonus: float = 0.0
    breakthrough_scope: str = ""
    trial_restore_hp: float = 0.0
    trial_restore_mp: float = 0.0
    root_grant: str = ""
    conception_bonus: float = 0.0
    permanent_intrinsic_hp_bonus: float = 0.0
    permanent_intrinsic_mp_bonus: float = 0.0
    tribulation_damage_reduction: float = 0.0


@dataclass(frozen=True, slots=True)
class TransformationDefinition:
    id: str
    name: str
    description: str
    realm_index: int
    layer: int
    stat_multipliers: dict[str, float]
    traits: tuple[str, ...]
    trait_descriptions: tuple[str, ...]
    trait_purity_requirements: tuple[float, ...]
    incompatible_with: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketGoodDefinition:
    world_id: str
    kind: str
    content_id: str
    tier: int
    price: int


@dataclass(frozen=True, slots=True)
class ExtensionDefinition:
    id: str
    name: str
    version: str
    kind: str
    enabled: bool
    status: str
    load_order: int
    description: str
    error: str = ""


@dataclass(frozen=True, slots=True)
class StoryEffectDefinition:
    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StoryChoiceDefinition:
    id: str
    text: str
    effects: tuple[StoryEffectDefinition, ...]
    conditions: dict[str, Any]
    disabled_reason: str
    result_text: str


@dataclass(frozen=True, slots=True)
class StoryEventDefinition:
    id: str
    version: int
    title: str
    body: str
    category: str
    tags: tuple[str, ...]
    weight: float
    intent_weights: dict[str, float]
    repeat: str
    conditions: dict[str, Any]
    choices: tuple[StoryChoiceDefinition, ...]


@dataclass(frozen=True, slots=True)
class GameDefinitions:
    realms: tuple[RealmDefinition, ...]
    roots: dict[str, RootDefinition]
    paths: dict[str, str]
    techniques: dict[str, TechniqueDefinition]
    worlds: dict[str, WorldDefinition]
    factions: dict[str, FactionDefinition]
    faction_rewards: dict[str, dict[str, Any]]
    items: dict[str, ItemDefinition]
    transformations: dict[str, TransformationDefinition]
    market_goods: tuple[MarketGoodDefinition, ...]
    market_settings: dict[str, Any]
    actions: dict[str, dict[str, Any]]
    time_units: dict[int, int]
    travel_speeds: dict[int, float]
    start_worlds: dict[str, tuple[str, ...]]
    breakthrough: dict[str, Any]
    stage_lifespan_bonus: dict[str, dict[str, tuple[int, int]]]
    systems: dict[str, Any]
    extensions: tuple[ExtensionDefinition, ...]
    extension_documents: dict[str, dict[str, Any]]
    story_events: dict[str, StoryEventDefinition]

    def realm_index(self, realm_id: str) -> int:
        for index, definition in enumerate(self.realms):
            if definition.id == realm_id:
                return index
        raise KeyError(f"未知境界：{realm_id}")

    def realm(self, realm_id: str) -> RealmDefinition:
        return self.realms[self.realm_index(realm_id)]

    def default_location(self, world_id: str) -> str:
        try:
            return self.worlds[world_id].default_location
        except KeyError as error:
            raise ValueError(f"未知世界：{world_id}") from error

    def action_time(self, realm_id: str, units: int) -> int:
        return self.time_units[self.realm_index(realm_id)] * units
