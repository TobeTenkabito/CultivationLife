from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .factions import FACTION_GOVERNANCE, FACTION_PROFILE, MEMBERSHIP
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


GHOST_DLC = "official.ghost-reincarnation"
MONSTER_DLC = "official.monster-bloodlines"
INTRIGUE_DLC = "official.intrigue-coalitions"
GHOST_SOUL = "dlc.ghost.soul"
MONSTER_BLOODLINE = "dlc.monster.bloodline"
INTRIGUE_GOVERNANCE = "dlc.intrigue.governance"


@dataclass(frozen=True, slots=True)
class SpendWangsheng:
    actor_id: str
    uses: int = 1


@dataclass(frozen=True, slots=True)
class ConfigureMonsterBloodline:
    actor_id: str
    species_id: str


@dataclass(frozen=True, slots=True)
class AssignFactionPosition:
    actor_id: str
    faction_id: str
    member_id: str
    position_id: str


def _loaded(definitions: GameDefinitions, package_id: str) -> bool:
    return any(
        extension.id == package_id and extension.status == "loaded"
        for extension in definitions.extensions
    )


def _new_ghost_state(realm_id: str, layer: int) -> dict[str, Any]:
    return {
        "intrinsic_hp": 100.0,
        "intrinsic_mp": 100.0,
        "erosion_rate_pp": 0.0,
        "erosion_time_progress": 0.0,
        "wangsheng": 0,
        "reincarnation_imprints": {},
        "historical_peak": {"realm_id": realm_id, "layer": layer},
    }


def _new_monster_state() -> dict[str, Any]:
    return {
        "species_id": None,
        "evolution_id": None,
        "evolution_history": [],
        "adaptation_years": {},
        "adaptations": [],
        "imprints": [],
        "traits": [],
        "frozen": False,
    }


def _new_intrigue_state() -> dict[str, Any]:
    return {
        "positions": {},
        "pending_decisions": [],
        "decision_history": [],
        "prisoner_ids": [],
    }


def reconcile_extension_state(state: WorldState, definitions: GameDefinitions) -> None:
    """Idempotently backfill state when an installed DLC is enabled again."""
    for extension in definitions.extensions:
        if extension.status != "loaded":
            continue
        previous = state.content_packages.get(extension.id)
        if previous is not None and previous != extension.version:
            raise ValueError(
                f"扩展 {extension.id} 存档版本为 {previous}，"
                f"当前版本为 {extension.version}；缺少专用迁移"
            )
        state.content_packages[extension.id] = extension.version
    for entity_id in state.entities.with_component(IDENTITY):
        cultivation = state.entities.get(entity_id, CULTIVATION)
        if cultivation is None:
            continue
        path = str(cultivation.get("path", ""))
        if (
            path == "ghost" and _loaded(definitions, GHOST_DLC)
            and state.entities.get(entity_id, GHOST_SOUL) is None
        ):
            state.entities.put(entity_id, GHOST_SOUL, _new_ghost_state(
                str(cultivation["realm_id"]), int(cultivation["layer"])
            ))
        if (
            path == "monster" and _loaded(definitions, MONSTER_DLC)
            and state.entities.get(entity_id, MONSTER_BLOODLINE) is None
        ):
            state.entities.put(entity_id, MONSTER_BLOODLINE, _new_monster_state())
    if _loaded(definitions, INTRIGUE_DLC):
        for faction_id in state.entities.with_component(FACTION_PROFILE):
            if state.entities.get(faction_id, INTRIGUE_GOVERNANCE) is None:
                state.entities.put(faction_id, INTRIGUE_GOVERNANCE, _new_intrigue_state())


def _monster_document(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.extension_documents.get("monster_bloodlines.json", {}))


def _on_character_created(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        entity_id = str(event.payload["entity_id"])
        path = str(event.payload["path"])
        if path == "ghost" and _loaded(definitions, GHOST_DLC):
            context.state.entities.put(entity_id, GHOST_SOUL, _new_ghost_state(
                str(event.payload["realm_id"]), int(event.payload["layer"])
            ))
        if path == "monster" and _loaded(definitions, MONSTER_DLC):
            context.state.entities.put(entity_id, MONSTER_BLOODLINE, _new_monster_state())

    return handler


def _on_faction_registered(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        if not _loaded(definitions, INTRIGUE_DLC):
            return
        faction_id = str(event.payload["faction_id"])
        context.state.entities.put(faction_id, INTRIGUE_GOVERNANCE, _new_intrigue_state())

    return handler


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        if elapsed <= 0:
            return
        if _loaded(definitions, GHOST_DLC):
            config = dict(definitions.systems.get("ghost_cultivation", {}))
            growth = max(0.0, float(config.get("erosion_growth_per_time_unit_pp", 0.0002)))
            floor = max(0.0, float(config.get("soul_death_intrinsic_floor", 1.0)))
            for entity_id in context.state.entities.with_component(GHOST_SOUL):
                life = context.state.entities.require(entity_id, LIFE)
                if not bool(life.get("alive")):
                    continue
                soul = context.state.entities.require(entity_id, GHOST_SOUL)
                cultivation = context.state.entities.require(entity_id, CULTIVATION)
                unit_years = definitions.action_time(str(cultivation["realm_id"]), 1)
                total = float(soul["erosion_time_progress"]) + elapsed / unit_years
                completed = int(total + 1e-12)
                soul["erosion_time_progress"] = total - completed
                for _ in range(completed):
                    rate = max(0.0, float(soul["erosion_rate_pp"]))
                    factor = max(0.0, 1.0 - rate / 100.0)
                    soul["intrinsic_hp"] = float(soul["intrinsic_hp"]) * factor
                    soul["intrinsic_mp"] = float(soul["intrinsic_mp"]) * factor
                    soul["erosion_rate_pp"] = rate + growth
                context.state.entities.put(entity_id, GHOST_SOUL, soul)
                if completed:
                    context.emit(
                        "dlc.ghost.erosion.applied",
                        source=GHOST_DLC,
                        scope=EventScope.entity(entity_id),
                        payload={
                            "entity_id": entity_id,
                            "units": completed,
                            "intrinsic_hp": soul["intrinsic_hp"],
                            "intrinsic_mp": soul["intrinsic_mp"],
                            "rate_pp": soul["erosion_rate_pp"],
                        },
                    )
                if float(soul["intrinsic_hp"]) < floor or float(soul["intrinsic_mp"]) < floor:
                    context.emit(
                        "character.lethal_hazard",
                        source=GHOST_DLC,
                        scope=EventScope.entity(entity_id),
                        payload={"entity_id": entity_id, "reason": "魂蚀尽毁，魂飞魄散"},
                    )

        if _loaded(definitions, MONSTER_DLC):
            document = _monster_document(definitions)
            adaptations = dict(dict(document.get("settings", {})).get("adaptations", {}))
            for entity_id in context.state.entities.with_component(MONSTER_BLOODLINE):
                bloodline = context.state.entities.require(entity_id, MONSTER_BLOODLINE)
                if bool(bloodline.get("frozen")):
                    continue
                location_id = str(context.state.entities.require(entity_id, LOCATION)["location_id"])
                years = dict(bloodline.get("adaptation_years", {}))
                unlocked = list(bloodline.get("adaptations", []))
                for adaptation_id, raw in adaptations.items():
                    definition = dict(raw)
                    if location_id not in set(map(str, definition.get("locations", []))):
                        continue
                    years[adaptation_id] = int(years.get(adaptation_id, 0)) + elapsed
                    if years[adaptation_id] >= int(definition.get("years", 1)) and adaptation_id not in unlocked:
                        unlocked.append(adaptation_id)
                        context.emit(
                            "dlc.monster.adaptation.unlocked",
                            source=MONSTER_DLC,
                            scope=EventScope.entity(entity_id),
                            payload={"entity_id": entity_id, "adaptation_id": adaptation_id},
                        )
                bloodline["adaptation_years"] = years
                bloodline["adaptations"] = unlocked
                context.state.entities.put(entity_id, MONSTER_BLOODLINE, bloodline)

    return handler


def _spend_wangsheng_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SpendWangsheng):
            raise TypeError("命令类型错误")
        soul = context.state.entities.get(command.actor_id, GHOST_SOUL)
        if soul is None or not _loaded(definitions, GHOST_DLC):
            raise ValueError("当前角色没有启用鬼修轮回DLC")
        if not isinstance(command.uses, int) or isinstance(command.uses, bool) or command.uses <= 0:
            raise ValueError("往生使用次数必须为正整数")
        config = dict(definitions.systems.get("ghost_cultivation", {}))
        unit_cost = max(1, int(config.get("wangsheng_cost", 2)))
        cost = unit_cost * command.uses
        if int(soul["wangsheng"]) < cost:
            raise ValueError(f"往生不足：需要 {cost} 点")
        before = float(soul["erosion_rate_pp"])
        reduction = max(0.0, float(config.get("wangsheng_erosion_reduction_pp", 0.02))) * command.uses
        soul["wangsheng"] = int(soul["wangsheng"]) - cost
        soul["erosion_rate_pp"] = max(0.0, before - reduction)
        context.state.entities.put(command.actor_id, GHOST_SOUL, soul)
        context.emit(
            "dlc.ghost.wangsheng.spent",
            source=GHOST_DLC,
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "cost": cost, "reduction_pp": before - soul["erosion_rate_pp"]},
        )

    return handler


def _configure_bloodline_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ConfigureMonsterBloodline):
            raise TypeError("命令类型错误")
        bloodline = context.state.entities.get(command.actor_id, MONSTER_BLOODLINE)
        if bloodline is None or not _loaded(definitions, MONSTER_DLC):
            raise ValueError("当前角色没有启用妖修血脉DLC")
        if bloodline.get("species_id") is not None:
            raise ValueError("本源谱系已经确定，不可重置")
        document = _monster_document(definitions)
        species = {
            str(row["id"]): dict(row)
            for row in document.get("species", [])
        }
        if command.species_id not in species:
            raise ValueError("未知妖修本源谱系")
        bloodline["species_id"] = command.species_id
        bloodline["evolution_id"] = species[command.species_id].get("base_evolution_id")
        context.state.entities.put(command.actor_id, MONSTER_BLOODLINE, bloodline)
        context.emit(
            "dlc.monster.bloodline.configured",
            source=MONSTER_DLC,
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "species_id": command.species_id},
        )

    return handler


def _assign_position_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, AssignFactionPosition):
            raise TypeError("命令类型错误")
        if not _loaded(definitions, INTRIGUE_DLC):
            raise ValueError("势力内政DLC未启用")
        governance = context.state.entities.require(command.faction_id, FACTION_GOVERNANCE)
        if governance.get("controller_id") != command.actor_id:
            raise ValueError("只有势力控制者可以任免职位")
        membership = context.state.relations.find(
            source_id=command.member_id, target_id=command.faction_id, kind=MEMBERSHIP
        )
        if not membership:
            raise ValueError("任职者不是该势力成员")
        profile = context.state.entities.require(command.faction_id, FACTION_PROFILE)
        faction_kind = "sect" if profile.get("path") != "family" else "family"
        config = dict(definitions.systems.get("intrigue_dlc", {}))
        positions = dict(dict(config.get("positions", {})).get(faction_kind, {}))
        position = dict(positions.get(command.position_id, {}))
        if not position:
            raise ValueError("未知势力职位")
        cultivation = context.state.entities.require(command.member_id, CULTIVATION)
        if definitions.realm_index(str(cultivation["realm_id"])) < int(position.get("minimum_realm", 0)):
            raise ValueError("任职者境界不足")
        state = context.state.entities.require(command.faction_id, INTRIGUE_GOVERNANCE)
        assigned = dict(state.get("positions", {}))
        assigned = {
            position_id: member_id
            for position_id, member_id in assigned.items()
            if member_id != command.member_id and position_id != command.position_id
        }
        assigned[command.position_id] = command.member_id
        state["positions"] = assigned
        context.state.entities.put(command.faction_id, INTRIGUE_GOVERNANCE, state)
        context.emit(
            "dlc.intrigue.position.assigned",
            source=INTRIGUE_DLC,
            scope=EventScope("faction", command.faction_id),
            payload={
                "faction_id": command.faction_id,
                "member_id": command.member_id,
                "position_id": command.position_id,
            },
        )

    return handler


def extension_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        for entity_id in state.entities.with_component(GHOST_SOUL):
            cultivation = state.entities.get(entity_id, CULTIVATION)
            soul = state.entities.require(entity_id, GHOST_SOUL)
            possession = state.entities.get(entity_id, "demonic.possession") or {}
            if cultivation is None or (
                cultivation.get("path") != "ghost" and not possession.get("host")
            ):
                errors.append(f"鬼修DLC状态指向非鬼修角色：{entity_id}")
            if min(float(soul.get("intrinsic_hp", -1)), float(soul.get("intrinsic_mp", -1))) < 0:
                errors.append(f"鬼修魂基非法：{entity_id}")
            if int(soul.get("wangsheng", -1)) < 0:
                errors.append(f"鬼修往生非法：{entity_id}")
        monster_document = _monster_document(definitions)
        species_ids = {str(row["id"]) for row in monster_document.get("species", [])}
        monster_loaded = _loaded(definitions, MONSTER_DLC)
        for entity_id in state.entities.with_component(MONSTER_BLOODLINE):
            cultivation = state.entities.get(entity_id, CULTIVATION)
            bloodline = state.entities.require(entity_id, MONSTER_BLOODLINE)
            if cultivation is None or cultivation.get("path") != "monster":
                errors.append(f"妖修DLC状态指向非妖修角色：{entity_id}")
            if (
                monster_loaded and bloodline.get("species_id") is not None
                and bloodline.get("species_id") not in species_ids
            ):
                errors.append(f"妖修本源谱系非法：{entity_id}")
        for faction_id in state.entities.with_component(INTRIGUE_GOVERNANCE):
            governance = state.entities.require(faction_id, INTRIGUE_GOVERNANCE)
            for member_id in dict(governance.get("positions", {})).values():
                if not state.relations.find(
                    source_id=str(member_id), target_id=faction_id, kind=MEMBERSHIP
                ):
                    errors.append(f"势力 {faction_id} 职位指向非成员")
        return errors

    return validate


def register_extension_domains(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(SpendWangsheng, _spend_wangsheng_handler(definitions))
    bus.register(ConfigureMonsterBloodline, _configure_bloodline_handler(definitions))
    bus.register(AssignFactionPosition, _assign_position_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created(definitions))
    bus.event_bus.register("faction.registered", _on_faction_registered(definitions))
    bus.event_bus.register("faction.founded", _on_faction_registered(definitions))
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))


def extension_view(state: Any, definitions: GameDefinitions, entity_id: str | None = None):
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    packages = [
        {
            "id": extension.id,
            "name": extension.name,
            "version": extension.version,
            "kind": extension.kind,
            "enabled": extension.enabled,
            "status": extension.status,
            "description": extension.description,
            "error": extension.error,
        }
        for extension in definitions.extensions
    ]
    return {
        "packages": packages,
        "ghost": state.entities.get(actor_id, GHOST_SOUL),
        "monster_bloodline": state.entities.get(actor_id, MONSTER_BLOODLINE),
    }
