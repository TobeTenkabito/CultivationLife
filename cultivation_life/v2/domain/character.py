from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .definitions import GameDefinitions
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


IDENTITY = "core.identity"
LIFE = "character.life"
ACTIVITY = "character.activity"
LIFESPAN_DUE = "character.lifespan.due"


@dataclass(frozen=True, slots=True)
class BootstrapGame:
    name: str
    starting_age: int = 16
    gender: str = "male"
    race: str = "human"
    spirit_root: str = "supreme_wood"
    path: str = "dao"
    start_world: str = "human"


@dataclass(frozen=True, slots=True)
class RegisterCharacter:
    name: str
    age: int
    gender: str
    race: str
    spirit_root: str
    path: str
    realm_id: str
    layer: int
    world_id: str
    lifespan: int | None = None


@dataclass(frozen=True, slots=True)
class PerformTimedAction:
    """Compatibility command retained from the first V2 vertical slice.

    Cultivation owns its handler from schema 2 onward.
    """

    actor_id: str
    action: str
    years: int = 1


def _validate_character_spec(
    definitions: GameDefinitions,
    *,
    name: str,
    age: int,
    gender: str,
    spirit_root: str,
    path: str,
    realm_id: str,
    layer: int,
    world_id: str,
) -> str:
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 40:
        raise ValueError("角色名必须为1至40个字符")
    if not 0 <= age <= 1_000_000:
        raise ValueError("角色年龄非法")
    if gender not in {"male", "female"}:
        raise ValueError("未知性别")
    if spirit_root not in definitions.roots:
        raise ValueError("未知灵根")
    if path not in definitions.paths:
        raise ValueError("未知修行道路")
    realm = definitions.realm(realm_id)
    if not 1 <= layer <= realm.layers:
        raise ValueError("境界层数非法")
    if world_id not in definitions.worlds or not definitions.worlds[world_id].enabled:
        raise ValueError("目标世界尚未开放")
    return clean_name


def _create_character(
    context: SimulationContext,
    *,
    name: str,
    age: int,
    gender: str,
    race: str,
    spirit_root: str,
    path: str,
    realm_id: str,
    layer: int,
    world_id: str,
    lifespan: int | None,
    controlled: bool,
) -> str:
    entity_id = context.state.entities.create("character")
    context.state.entities.put(entity_id, IDENTITY, {"name": name, "gender": gender, "race": race})
    context.state.entities.put(
        entity_id,
        LIFE,
        {
            "birth_year": context.state.clock.year - age,
            "lifespan": lifespan,
            "alive": True,
            "death_reason": None,
        },
    )
    context.state.entities.put(entity_id, ACTIVITY, {"rest_years": 0, "actions_completed": 0})
    if lifespan is not None:
        context.state.scheduler.schedule(
            due_year=context.state.clock.year - age + lifespan,
            event_type=LIFESPAN_DUE,
            source="character",
            scope=EventScope.entity(entity_id),
            payload={"entity_id": entity_id},
        )
    if controlled:
        context.state.controlled_entity_id = entity_id
    context.emit(
        "character.created",
        source="character",
        scope=EventScope.entity(entity_id),
        payload={
            "entity_id": entity_id,
            "name": name,
            "age": age,
            "spirit_root": spirit_root,
            "path": path,
            "realm_id": realm_id,
            "layer": layer,
            "world_id": world_id,
            "controlled": controlled,
        },
    )
    return entity_id


def _bootstrap_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, BootstrapGame):
            raise TypeError("命令类型错误")
        if context.state.controlled_entity_id is not None:
            raise ValueError("游戏已经初始化")
        clean_name = _validate_character_spec(
            definitions,
            name=command.name,
            age=command.starting_age,
            gender=command.gender,
            spirit_root=command.spirit_root,
            path=command.path,
            realm_id="mortal",
            layer=1,
            world_id=command.start_world,
        )
        if command.start_world not in definitions.start_worlds.get(command.path, ("human",)):
            raise ValueError("该修行道路不能从所选世界开局")
        span = definitions.realms[0].lifespan
        lifespan = None if command.path == "ghost" or span is None else context.rng.randint(*span)
        if command.path == "monster" and lifespan is not None:
            lifespan *= 3
        lifespan = None if lifespan is None else max(lifespan, command.starting_age + 1)
        actor_id = _create_character(
            context,
            name=clean_name,
            age=command.starting_age,
            gender=command.gender,
            race=command.race,
            spirit_root=command.spirit_root,
            path=command.path,
            realm_id="mortal",
            layer=1,
            world_id=command.start_world,
            lifespan=lifespan,
            controlled=True,
        )
        context.emit(
            "core.game.created",
            source="core",
            scope=EventScope.global_scope(),
            payload={"game_id": context.state.game_id, "controlled_entity_id": actor_id},
        )

    return handler


def _register_character_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RegisterCharacter):
            raise TypeError("命令类型错误")
        clean_name = _validate_character_spec(
            definitions,
            name=command.name,
            age=command.age,
            gender=command.gender,
            spirit_root=command.spirit_root,
            path=command.path,
            realm_id=command.realm_id,
            layer=command.layer,
            world_id=command.world_id,
        )
        realm = definitions.realm(command.realm_id)
        lifespan = command.lifespan
        if lifespan is None and realm.lifespan is not None and command.path != "ghost":
            lifespan = context.rng.randint(*realm.lifespan)
            if command.path == "monster":
                lifespan *= 3
        if lifespan is not None and lifespan <= command.age:
            raise ValueError("在世角色的寿元必须大于当前年龄")
        _create_character(
            context,
            name=clean_name,
            age=command.age,
            gender=command.gender,
            race=command.race,
            spirit_root=command.spirit_root,
            path=command.path,
            realm_id=command.realm_id,
            layer=command.layer,
            world_id=command.world_id,
            lifespan=lifespan,
            controlled=False,
        )

    return handler


def _kill_character(context: SimulationContext, entity_id: str, reason: str) -> None:
    life = context.state.entities.require(entity_id, LIFE)
    if not bool(life.get("alive")):
        return
    life["alive"] = False
    life["death_reason"] = reason
    context.state.entities.put(entity_id, LIFE, life)
    context.state.scheduler.cancel(
        lambda scheduled: (
            scheduled.event_type == LIFESPAN_DUE
            and str(scheduled.payload.get("entity_id", "")) == entity_id
        )
    )
    context.emit(
        "character.died",
        source="character",
        scope=EventScope.entity(entity_id),
        payload={
            "entity_id": entity_id,
            "reason": reason,
            "age": context.state.clock.year - int(life["birth_year"]),
        },
    )
    if entity_id == context.state.controlled_entity_id:
        context.halt_time(reason)


def _on_lifespan_due(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    life = context.state.entities.require(entity_id, LIFE)
    lifespan = life.get("lifespan")
    age = context.state.clock.year - int(life["birth_year"])
    if lifespan is not None and age >= int(lifespan):
        _kill_character(context, entity_id, "寿元已尽")


def _on_lifespan_changed(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    life = context.state.entities.require(entity_id, LIFE)
    context.state.scheduler.cancel(
        lambda scheduled: (
            scheduled.event_type == LIFESPAN_DUE
            and str(scheduled.payload.get("entity_id", "")) == entity_id
        )
    )
    lifespan = life.get("lifespan")
    if lifespan is None or not bool(life.get("alive")):
        return
    due_year = int(life["birth_year"]) + int(lifespan)
    if due_year <= context.state.clock.year:
        _kill_character(context, entity_id, "寿元已尽")
        return
    context.state.scheduler.schedule(
        due_year=due_year,
        event_type=LIFESPAN_DUE,
        source="character",
        scope=EventScope.entity(entity_id),
        payload={"entity_id": entity_id},
    )


def _on_lethal_hazard(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    _kill_character(context, entity_id, str(event.payload["reason"]))


def character_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    if not state.controlled_entity_id:
        errors.append("没有受控角色")
    for entity_id in state.entities.with_component(IDENTITY):
        for component in (LIFE, ACTIVITY):
            if state.entities.get(entity_id, component) is None:
                errors.append(f"角色 {entity_id} 缺少组件 {component}")
        identity = state.entities.require(entity_id, IDENTITY)
        if not str(identity.get("name", "")).strip():
            errors.append(f"角色 {entity_id} 缺少姓名")
        if identity.get("gender") not in {"male", "female"}:
            errors.append(f"角色 {entity_id} 性别非法")
        life = state.entities.get(entity_id, LIFE)
        if life is not None:
            age = state.clock.year - int(life.get("birth_year", state.clock.year + 1))
            if age < 0:
                errors.append(f"角色 {entity_id} 尚未出生")
            lifespan = life.get("lifespan")
            if bool(life.get("alive")) and lifespan is not None and age >= int(lifespan):
                errors.append(f"角色 {entity_id} 已达寿限但仍标记为存活")
    return errors


def register_character_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(BootstrapGame, _bootstrap_handler(definitions))
    bus.register(RegisterCharacter, _register_character_handler(definitions))
    bus.event_bus.register(LIFESPAN_DUE, _on_lifespan_due)
    bus.event_bus.register("character.lifespan.changed", _on_lifespan_changed)
    bus.event_bus.register("character.lethal_hazard", _on_lethal_hazard)


def character_view(state: Any, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    identity = state.entities.require(actor_id, IDENTITY)
    life = state.entities.require(actor_id, LIFE)
    activity = state.entities.require(actor_id, ACTIVITY)
    return {
        "id": actor_id,
        "name": str(identity["name"]),
        "gender": str(identity["gender"]),
        "race": str(identity["race"]),
        "age": state.clock.year - int(life["birth_year"]),
        "lifespan": life.get("lifespan"),
        "alive": bool(life["alive"]),
        "death_reason": life.get("death_reason"),
        "activity": activity,
    }
