from __future__ import annotations

from typing import Any

from .character import IDENTITY, LIFE, WORLD_NPC_PROFILE
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .factions import FACTION_NPC, FACTION_PROFILE, MEMBERSHIP
from .family import FAMILY_MEMBERSHIP, FAMILY_PROFILE
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


NPC_LIFECYCLE = "simulation.npc_lifecycle"


def _initial_progress(state: WorldState, entity_id: str) -> float:
    values: list[float] = []
    for component_name in (WORLD_NPC_PROFILE, FACTION_NPC):
        component = state.entities.get(entity_id, component_name)
        if component is not None:
            values.append(float(component.get("cultivation_progress", 0.0)))
    for edge in state.relations.find(source_id=entity_id, kind=FAMILY_MEMBERSHIP):
        values.append(float(edge.metadata.get("cultivation_progress", 0.0)))
    return max(values, default=0.0)


def _default_lifecycle(state: WorldState, entity_id: str) -> dict[str, Any]:
    return {
        "cultivation_progress": _initial_progress(state, entity_id),
        "next_tribulation_year": None,
        "tribulation_count": 0,
        "tribulation_power": None,
        "last_advanced_year": state.clock.year,
    }


def reconcile_npc_lifecycle(state: WorldState) -> None:
    """Give every non-player character one canonical autonomous lifecycle.

    Older V2 snapshots kept progress in whichever subsystem happened to own an
    NPC.  Import the greatest of those values once, then mirror the canonical
    value back to compatibility projections after each simulation step.
    """
    for entity_id in state.entities.with_component(IDENTITY):
        if entity_id == state.controlled_entity_id:
            continue
        lifecycle = state.entities.get(entity_id, NPC_LIFECYCLE)
        if lifecycle is None:
            lifecycle = _default_lifecycle(state, entity_id)
        else:
            defaults = _default_lifecycle(state, entity_id)
            for key, value in defaults.items():
                lifecycle.setdefault(key, value)
            lifecycle["cultivation_progress"] = max(
                float(lifecycle.get("cultivation_progress", 0.0)),
                _initial_progress(state, entity_id),
            )
        state.entities.put(entity_id, NPC_LIFECYCLE, lifecycle)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    if entity_id != context.state.controlled_entity_id:
        context.state.entities.put(
            entity_id, NPC_LIFECYCLE, _default_lifecycle(context.state, entity_id)
        )


def _is_imprisoned(state: WorldState, entity_id: str) -> bool:
    from .intrigue import is_intrigue_imprisoned

    if is_intrigue_imprisoned(state, entity_id):
        return True
    imprisonment = state.entities.get(entity_id, "demonic.imprisonment") or {}
    return bool(imprisonment.get("active"))


def _realm_label(
    definitions: GameDefinitions, cultivation: dict[str, Any]
) -> str:
    realm = definitions.realm(str(cultivation["realm_id"]))
    layer = int(cultivation["layer"])
    if realm.layers == 1 or realm.id == "mortal":
        return realm.name
    if realm.id == "qi":
        return f"{realm.name}{layer}层"
    stage = "初期" if layer <= 3 else "中期" if layer <= 6 else "后期"
    return f"{realm.name}{stage}"


def _lifespan_multiplier(path: str) -> int:
    return 3 if path == "monster" else 1


def _sync_progress(
    context: SimulationContext, entity_id: str, lifecycle: dict[str, Any]
) -> None:
    progress = float(lifecycle.get("cultivation_progress", 0.0))
    for component_name in (WORLD_NPC_PROFILE, FACTION_NPC):
        component = context.state.entities.get(entity_id, component_name)
        if component is not None:
            component["cultivation_progress"] = progress
            context.state.entities.put(entity_id, component_name, component)
    for edge in context.state.relations.find(
        source_id=entity_id, kind=FAMILY_MEMBERSHIP
    ):
        metadata = dict(edge.metadata)
        metadata["cultivation_progress"] = progress
        context.state.relations.replace_metadata(edge.relation_id, metadata)


def _event_scope(state: WorldState, entity_id: str) -> EventScope:
    membership = state.relations.find(source_id=entity_id, kind=MEMBERSHIP)
    if membership:
        return EventScope("faction", membership[0].target_id)
    family = state.relations.find(source_id=entity_id, kind=FAMILY_MEMBERSHIP)
    if family:
        return EventScope("faction", family[0].target_id)
    location = state.entities.require(entity_id, LOCATION)
    return EventScope("world", str(location["world_id"]))


def _emit_breakthrough(
    context: SimulationContext,
    entity_id: str,
    before: tuple[str, int],
    after: tuple[str, int],
) -> None:
    location = context.state.entities.require(entity_id, LOCATION)
    payload = {
        "character_id": entity_id,
        "world_id": str(location["world_id"]),
        "before": before,
        "after": after,
    }
    context.transient.setdefault("npc.breakthrough.facts", []).append(payload)


def _advance_tribulation(
    context: SimulationContext,
    definitions: GameDefinitions,
    entity_id: str,
    lifecycle: dict[str, Any],
    year: int,
) -> bool:
    cultivation = context.state.entities.require(entity_id, CULTIVATION)
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    location = context.state.entities.require(entity_id, LOCATION)
    profile = dict(definitions.systems.get("world_profiles", {})).get(
        str(location["world_id"]), {}
    )
    if realm_index < 6 or "ranking" not in set(profile.get("supports", [])):
        return True
    config = dict(definitions.breakthrough.get("periodic_thunder", {}))
    interval = max(1, int(config.get("interval_years", 3000)))
    if lifecycle.get("next_tribulation_year") is None:
        lifecycle["next_tribulation_year"] = year + interval
        lifecycle["tribulation_power"] = float(config.get("base_power", 1000))
        return True
    if year < int(lifecycle["next_tribulation_year"]):
        return True
    count = int(lifecycle.get("tribulation_count", 0))
    realm = definitions.realms[realm_index]
    own_power = float(realm.base_power) * (1 + 0.12 * (int(cultivation["layer"]) - 1))
    pressure = max(
        1.0,
        float(lifecycle.get("tribulation_power") or config.get("base_power", 1000)),
    )
    preparedness = own_power / max(1.0, own_power * 0.72 + pressure * 16)
    chance = max(0.48, min(0.985, 0.62 + preparedness * 0.24))
    lifecycle["tribulation_count"] = count + 1
    lifecycle["next_tribulation_year"] = int(lifecycle["next_tribulation_year"]) + interval
    lifecycle["tribulation_power"] = float(config.get("base_power", 1000)) * (
        float(config.get("power_multiplier", 2.0)) ** (count + 1)
    )
    survived = context.rng.random() < chance
    context.emit(
        "npc.tribulation.resolved", source="npc_lifecycle",
        scope=_event_scope(context.state, entity_id),
        payload={
            "character_id": entity_id,
            "world_id": str(location["world_id"]),
            "count": count + 1,
            "chance": round(chance, 4),
            "survived": survived,
        },
    )
    if not survived:
        context.emit(
            "character.lethal_hazard", source="npc_lifecycle",
            scope=EventScope.entity(entity_id),
            payload={
                "entity_id": entity_id,
                "reason": f"第{count + 1}次大天劫下灰飞烟灭",
            },
        )
    return survived


def _ascension_destination(path: str) -> str:
    return {
        "demonic": "demon",
        "ghost": "hell",
        "monster": "nether",
    }.get(path, "spirit")


def _advance_one_year(
    context: SimulationContext,
    definitions: GameDefinitions,
    entity_id: str,
    lifecycle: dict[str, Any],
    year: int,
    *,
    imprisoned: bool = False,
    years: int = 1,
) -> None:
    life = context.state.entities.require(entity_id, LIFE)
    if not bool(life.get("alive")) or imprisoned:
        return
    cultivation = context.state.entities.require(entity_id, CULTIVATION)
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    if realm_index <= 0:
        return
    if not _advance_tribulation(
        context, definitions, entity_id, lifecycle, year
    ):
        return
    rules = dict(definitions.systems.get("factions", {})).get(
        "npc_cultivation", {}
    )
    accident = max(0.0, float(rules.get("accident_death_chance", 0.0005)))
    accident_over_period = 1.0 - (1.0 - accident) ** max(1, years)
    if context.rng.random() < accident_over_period:
        context.emit(
            "character.lethal_hazard", source="npc_lifecycle",
            scope=EventScope.entity(entity_id),
            payload={"entity_id": entity_id, "reason": "修行意外陨落"},
        )
        return
    if realm_index >= len(definitions.realms) - 1:
        return
    location = context.state.entities.require(entity_id, LOCATION)
    world = definitions.worlds[str(location["world_id"])]
    realm = definitions.realms[realm_index]
    if realm_index > world.npc_realm_cap or (
        str(location["world_id"]) != "human"
        and realm_index == world.npc_realm_cap
        and int(cultivation["layer"]) >= realm.layers
    ):
        return
    rates = dict(rules.get("progress_per_year", {}))
    if str(realm_index) not in rates:
        return
    root = definitions.roots.get(str(cultivation.get("spirit_root", "none")))
    efficiency = float(root.efficiency) if root is not None else 1.0
    progress = float(lifecycle.get("cultivation_progress", 0.0))
    progress += (
        float(rates[str(realm_index)]) * efficiency * max(1, years)
        * context.rng.uniform(0.82, 1.18)
    )
    threshold = float(rules.get("threshold", 100.0)) * (
        1 + 0.06 * (int(cultivation["layer"]) - 1)
    )
    lifecycle["cultivation_progress"] = progress
    if progress < threshold:
        return
    chance = float(rules.get("base_success", 0.64))
    if root is not None:
        chance += (float(root.efficiency) - 1.0) * float(
            rules.get("root_success_scale", 0.20)
        )
    chance = max(0.05, min(0.98, chance))
    if context.rng.random() >= chance:
        lifecycle["cultivation_progress"] = threshold * float(
            rules.get("failed_progress_retained", 0.55)
        )
        return
    before = (str(cultivation["realm_id"]), int(cultivation["layer"]))
    lifecycle["cultivation_progress"] = max(0.0, progress - threshold)
    if (
        str(location["world_id"]) == "human"
        and realm_index == 5
        and int(cultivation["layer"]) >= 3
    ):
        destination = _ascension_destination(str(cultivation.get("path", "dao")))
        if destination in definitions.worlds and definitions.worlds[destination].enabled:
            origin = str(location["world_id"])
            location["world_id"] = destination
            location["location_id"] = definitions.default_location(destination)
            context.state.entities.put(entity_id, LOCATION, location)
            context.emit(
                "npc.departed", source="npc_lifecycle",
                scope=EventScope("world", origin),
                payload={
                    "character_id": entity_id,
                    "origin_world_id": origin,
                    "destination_world_id": destination,
                },
            )
        return
    if int(cultivation["layer"]) < realm.layers:
        cultivation["layer"] = int(cultivation["layer"]) + 1
        stage = (
            "middle" if int(cultivation["layer"]) == 4
            else "late" if int(cultivation["layer"]) == 7
            else None
        )
        bonus = definitions.stage_lifespan_bonus.get(realm.id, {}).get(str(stage))
        if bonus and life.get("lifespan") is not None:
            life["lifespan"] = int(life["lifespan"]) + context.rng.randint(*bonus) * _lifespan_multiplier(str(cultivation.get("path", "dao")))
            context.state.entities.put(entity_id, LIFE, life)
            context.emit(
                "character.lifespan.changed", source="npc_lifecycle",
                scope=EventScope.entity(entity_id), payload={"entity_id": entity_id},
            )
    else:
        cultivation["realm_id"] = definitions.realms[realm_index + 1].id
        cultivation["layer"] = 1
        span = definitions.realms[realm_index + 1].lifespan
        if span is None:
            life["lifespan"] = None
        else:
            age = year - int(life["birth_year"])
            rolled = context.rng.randint(*span) * _lifespan_multiplier(
                str(cultivation.get("path", "dao"))
            )
            life["lifespan"] = max(int(life.get("lifespan") or 0), age + 1, rolled)
        context.state.entities.put(entity_id, LIFE, life)
        context.emit(
            "character.lifespan.changed", source="npc_lifecycle",
            scope=EventScope.entity(entity_id), payload={"entity_id": entity_id},
        )
    context.state.entities.put(entity_id, CULTIVATION, cultivation)
    _emit_breakthrough(
        context, entity_id, before,
        (str(cultivation["realm_id"]), int(cultivation["layer"])),
    )


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        start = int(event.payload["from_year"])
        end = int(event.payload["to_year"])
        if end <= start:
            return
        actor_id = context.state.controlled_entity_id
        runtime = (
            context.state.entities.get(actor_id, "core.action_runtime")
            if actor_id else None
        ) or {}
        active = runtime.get("active")
        if isinstance(active, dict):
            action_start = int(active.get("started_year", start))
            target = int(active.get("target_year", end))
            # Player cultivation deliberately has annual ticks.  Replaying the
            # entire NPC population on every one of those ticks is redundant:
            # settle autonomous lives in ten-year slices and always flush the
            # remainder at the action target. Lifespan scheduler events remain
            # exact and can still kill an NPC between slices.
            if end != target and (end - action_start) % 10:
                return
        player_rng_state = context.rng.getstate()
        for entity_id in list(context.state.entities.with_component(NPC_LIFECYCLE)):
            lifecycle = context.state.entities.require(entity_id, NPC_LIFECYCLE)
            cursor = max(start, int(lifecycle.get("last_advanced_year", start)))
            # Imprisonment is a unit-level state change.  Resolving it once per
            # interval avoids repeatedly scanning every relation for every
            # elapsed year (500-year immortal actions made that quadratic).
            imprisoned = _is_imprisoned(context.state, entity_id)
            while cursor < end:
                if not bool(context.state.entities.require(entity_id, LIFE).get("alive")):
                    break
                # Five-year blocks preserve low-realm multi-breakthrough
                # behavior (even the fastest configured NPC cannot normally
                # clear two thresholds in one block) while keeping immortal
                # 500/1000-year actions responsive.
                years = min(5, end - cursor)
                year = cursor + years
                _advance_one_year(
                    context, definitions, entity_id, lifecycle, year,
                    imprisoned=imprisoned,
                    years=years,
                )
                cursor = year
            lifecycle["last_advanced_year"] = end
            context.state.entities.put(entity_id, NPC_LIFECYCLE, lifecycle)
            _sync_progress(context, entity_id, lifecycle)
        facts = list(context.transient.pop("npc.breakthrough.facts", []))
        if facts:
            context.emit(
                "npc.breakthrough.batch", source="npc_lifecycle",
                scope=EventScope.global_scope(),
                payload={"entries": facts},
                immediate=True,
            )
        # Autonomous world simulation has its own deterministic consequences
        # and must not change which player event/combat roll comes next.
        context.rng.setstate(player_rng_state)

    return handler


def npc_lifecycle_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    for entity_id in state.entities.with_component(IDENTITY):
        if entity_id == state.controlled_entity_id:
            continue
        lifecycle = state.entities.get(entity_id, NPC_LIFECYCLE)
        if lifecycle is None:
            errors.append(f"NPC {entity_id} 缺少统一生命周期")
            continue
        if float(lifecycle.get("cultivation_progress", -1.0)) < 0:
            errors.append(f"NPC {entity_id} 修炼进度非法")
        if int(lifecycle.get("last_advanced_year", -1)) > state.clock.year:
            errors.append(f"NPC {entity_id} 生命周期越过世界时钟")
    return errors


def register_npc_lifecycle_domain(
    bus: CommandBus, definitions: GameDefinitions
) -> None:
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))
