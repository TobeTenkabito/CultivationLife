from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE
from .definitions import GameDefinitions
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState
from ..kernel.services import TimeService


LOCATION = "world.location"
TRAVEL_DUE = "world.travel.due"


@dataclass(frozen=True, slots=True)
class TravelWithinWorld:
    actor_id: str
    destination_id: str


def _on_character_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        entity_id = str(event.payload["entity_id"])
        world_id = str(event.payload["world_id"])
        context.state.entities.put(
            entity_id,
            LOCATION,
            {
                "world_id": world_id,
                "location_id": definitions.default_location(world_id),
            },
        )

    return handler


def _travel_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, TravelWithinWorld):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能控制当前角色旅行")
        life = context.state.entities.require(command.actor_id, LIFE)
        if not bool(life.get("alive")):
            raise ValueError("死亡角色不能旅行")
        location = context.state.entities.require(command.actor_id, LOCATION)
        cultivation = context.state.entities.require(command.actor_id, "cultivation.state")
        world_id = str(location["world_id"])
        world = definitions.worlds[world_id]
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        plan = world.travel_plan(
            str(location["location_id"]),
            command.destination_id,
            realm_index,
            definitions.travel_speeds[realm_index],
        )
        target = world.locations[command.destination_id]
        if not plan.accessible and target.failure != "lethal":
            raise ValueError(plan.warning)
        context.state.scheduler.schedule(
            due_year=context.state.clock.year + plan.years,
            event_type=TRAVEL_DUE,
            source="world",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id,
                "world_id": world_id,
                "origin_id": plan.origin,
                "destination_id": plan.destination,
                "route": list(plan.route),
                "years": plan.years,
                "lethal": not plan.accessible,
                "warning": plan.warning,
            },
        )
        TimeService.advance(context, plan.years, source="world.travel")

    return handler


def _on_travel_due(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    life = context.state.entities.require(actor_id, LIFE)
    if not bool(life.get("alive")):
        context.emit(
            "world.travel.interrupted",
            source="world",
            scope=EventScope.entity(actor_id),
            payload={**event.payload, "reason": str(life.get("death_reason") or "角色已经死亡")},
        )
        return
    location = context.state.entities.require(actor_id, LOCATION)
    if (
        location.get("world_id") != event.payload["world_id"]
        or location.get("location_id") != event.payload["origin_id"]
    ):
        raise ValueError("旅行期间角色位置发生冲突")
    location["location_id"] = str(event.payload["destination_id"])
    context.state.entities.put(actor_id, LOCATION, location)
    context.emit(
        "world.travel.arrived",
        source="world",
        scope=EventScope.entity(actor_id),
        payload=dict(event.payload),
    )
    if bool(event.payload.get("lethal")):
        context.emit(
            "character.lethal_hazard",
            source="world",
            scope=EventScope.entity(actor_id),
            payload={"entity_id": actor_id, "reason": str(event.payload["warning"])},
        )


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["entity_id"])
    cancelled = context.state.scheduler.cancel(
        lambda scheduled: (
            scheduled.event_type == TRAVEL_DUE
            and str(scheduled.payload.get("actor_id", "")) == actor_id
        )
    )
    for scheduled in cancelled:
        context.emit(
            "world.travel.interrupted",
            source="world",
            scope=EventScope.entity(actor_id),
            payload={
                **scheduled.payload,
                "reason": event.payload.get("reason"),
            },
        )


def world_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for entity_id in state.entities.with_component(IDENTITY):
            location = state.entities.get(entity_id, LOCATION)
            if location is None:
                errors.append(f"角色 {entity_id} 缺少位置组件")
                continue
            world_id = str(location.get("world_id", ""))
            location_id = str(location.get("location_id", ""))
            if world_id not in definitions.worlds:
                errors.append(f"角色 {entity_id} 位于未知世界 {world_id}")
            elif location_id not in definitions.worlds[world_id].locations:
                errors.append(f"角色 {entity_id} 位于未知地点 {location_id}")
        return errors

    return validate


def register_world_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(TravelWithinWorld, _travel_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created(definitions))
    bus.event_bus.register(TRAVEL_DUE, _on_travel_due)
    bus.event_bus.register("character.died", _on_character_died)


def world_view(state: Any, definitions: GameDefinitions, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    location = state.entities.require(actor_id, LOCATION)
    cultivation = state.entities.require(actor_id, "cultivation.state")
    world_id = str(location["world_id"])
    location_id = str(location["location_id"])
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    world = definitions.worlds[world_id]
    destinations = []
    for target_id, target in world.locations.items():
        if target_id == location_id:
            destinations.append({"id": target_id, "name": target.name, "current": True, "travel_years": 0})
            continue
        plan = world.travel_plan(
            location_id,
            target_id,
            realm_index,
            definitions.travel_speeds[realm_index],
        )
        destinations.append({
            "id": target_id,
            "name": target.name,
            "current": False,
            "travel_years": plan.years,
            "accessible": plan.accessible,
            "warning": plan.warning,
            "route": list(plan.route),
        })
    return {
        "world_id": world_id,
        "world_name": world.name,
        "location_id": location_id,
        "location_name": world.locations[location_id].name,
        "destinations": destinations,
    }
