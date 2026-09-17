from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE, character_view, create_character
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .presentation import PREFERENCES
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


LINEAGE = "family.lineage"
FAMILY_PROFILE = "family.profile"
PARENT_CHILD = "parent_child"
FAMILY_MEMBERSHIP = "family_membership"


@dataclass(frozen=True, slots=True)
class CreateFamily:
    founder_id: str
    name: str


def _default_lineage() -> dict[str, Any]:
    return {
        "child_ids": [],
        "family_id": None,
        "next_conception_bonus": 0.0,
        "conceptions_attempted": 0,
    }


def reconcile_family_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        component = state.entities.get(entity_id, LINEAGE) or _default_lineage()
        component["child_ids"] = list(dict.fromkeys(
            child_id for child_id in map(str, component.get("child_ids", []))
            if state.entities.exists(child_id)
        ))
        component["next_conception_bonus"] = max(
            0.0, float(component.get("next_conception_bonus", 0.0))
        )
        component["conceptions_attempted"] = max(
            0, int(component.get("conceptions_attempted", 0))
        )
        family_id = component.get("family_id")
        if family_id is not None and state.entities.get(str(family_id), FAMILY_PROFILE) is None:
            component["family_id"] = None
        state.entities.put(entity_id, LINEAGE, component)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(str(event.payload["entity_id"]), LINEAGE, _default_lineage())


def _innate_root(root_id: str) -> bool:
    return root_id != "none" and not root_id.startswith("acquired_")


def _child_name(parent_name: str, context: SimulationContext) -> str:
    surname = parent_name[:1] or "林"
    return surname + context.rng.choice(["宁", "安", "澄", "昭", "遥", "真", "元", "清"])


def _on_conception_bonus(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["entity_id"])
    lineage = context.state.entities.require(actor_id, LINEAGE)
    lineage["next_conception_bonus"] = max(
        float(lineage.get("next_conception_bonus", 0.0)),
        float(event.payload["bonus"]),
    )
    context.state.entities.put(actor_id, LINEAGE, lineage)


def _on_conception_requested(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        partner_id = str(event.payload["partner_id"])
        relation = next(
            (
                edge for edge in context.state.relations.involving(
                    actor_id, kind="dao_companion"
                )
                if partner_id in {edge.source_id, edge.target_id}
            ),
            None,
        )
        if relation is None:
            raise ValueError("只有当前道侣能够共同孕育后代")
        for entity_id in (actor_id, partner_id):
            life = context.state.entities.require(entity_id, LIFE)
            if not bool(life.get("alive")):
                raise ValueError("死亡人物不能孕育后代")
        actor_location = context.state.entities.require(actor_id, LOCATION)
        partner_location = context.state.entities.require(partner_id, LOCATION)
        if actor_location.get("world_id") != partner_location.get("world_id"):
            raise ValueError("道侣不在同一世界，无法孕育后代")

        lineage = context.state.entities.require(actor_id, LINEAGE)
        medicine_bonus = max(0.0, float(lineage.get("next_conception_bonus", 0.0)))
        lineage["next_conception_bonus"] = 0.0
        lineage["conceptions_attempted"] = int(lineage.get("conceptions_attempted", 0)) + 1
        actor_cultivation = context.state.entities.require(actor_id, CULTIVATION)
        partner_cultivation = context.state.entities.require(partner_id, CULTIVATION)
        realm_index = definitions.realm_index(str(actor_cultivation["realm_id"]))
        rules = dict(definitions.systems.get("family", {}))
        natural = float(
            dict(rules.get("conception_chance_by_realm", {})).get(
                str(realm_index), 0.0
            )
        )
        chance = min(0.95, natural + medicine_bonus)
        conceived = context.rng.random() < chance
        child_id: str | None = None
        if conceived:
            actor_root = str(actor_cultivation["spirit_root"])
            partner_root = str(partner_cultivation["spirit_root"])
            inherits = (
                _innate_root(actor_root)
                and _innate_root(partner_root)
                and context.rng.random()
                < float(rules.get("spirit_root_inheritance_chance", 0.9))
            )
            child_root = context.rng.choice([actor_root, partner_root]) if inherits else "none"
            identity = context.state.entities.require(actor_id, IDENTITY)
            child_id = create_character(
                context,
                name=_child_name(str(identity["name"]), context),
                age=0,
                gender=context.rng.choice(["male", "female"]),
                race=str(identity["race"]),
                spirit_root=child_root,
                path=str(actor_cultivation["path"]),
                realm_id="mortal",
                layer=1,
                world_id=str(actor_location["world_id"]),
                lifespan=context.rng.randint(80, 100),
            )
            context.state.relations.add(
                source_id=actor_id,
                target_id=child_id,
                kind=PARENT_CHILD,
                created_year=context.state.clock.year,
                metadata={"role": "parent"},
            )
            context.state.relations.add(
                source_id=partner_id,
                target_id=child_id,
                kind=PARENT_CHILD,
                created_year=context.state.clock.year,
                metadata={"role": "parent"},
            )
            child_ids = list(map(str, lineage.get("child_ids", [])))
            child_ids.append(child_id)
            lineage["child_ids"] = list(dict.fromkeys(child_ids))
        context.state.entities.put(actor_id, LINEAGE, lineage)
        context.emit(
            "family.conception.resolved",
            source="family",
            scope=EventScope.entity(actor_id),
            payload={
                "actor_id": actor_id,
                "partner_id": partner_id,
                "chance": chance,
                "medicine_bonus": medicine_bonus,
                "conceived": conceived,
                "child_id": child_id,
            },
        )

    return handler


def _on_time_advanced(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = context.state.controlled_entity_id
        if actor_id is None:
            return
        lineage = context.state.entities.get(actor_id, LINEAGE)
        if lineage is None:
            return
        start_age = int(dict(definitions.systems.get("family", {})).get(
            "cultivation_start_age", 8
        ))
        for child_id in map(str, lineage.get("child_ids", [])):
            life = context.state.entities.get(child_id, LIFE)
            cultivation = context.state.entities.get(child_id, CULTIVATION)
            if not life or not cultivation or not bool(life.get("alive")):
                continue
            age = context.state.clock.year - int(life["birth_year"])
            if (
                age >= start_age
                and str(cultivation.get("spirit_root", "none")) != "none"
                and str(cultivation.get("realm_id")) == "mortal"
            ):
                cultivation["realm_id"] = "qi"
                cultivation["layer"] = 1
                before = int(life.get("lifespan") or 0)
                life["lifespan"] = max(before, context.rng.randint(100, 120), age + 1)
                context.state.entities.put(child_id, CULTIVATION, cultivation)
                context.state.entities.put(child_id, LIFE, life)
                context.emit(
                    "character.lifespan.changed",
                    source="family",
                    scope=EventScope.entity(child_id),
                    payload={"entity_id": child_id, "lifespan": life["lifespan"]},
                )
                context.emit(
                    "family.child.cultivation_started",
                    source="family",
                    scope=EventScope.entity(actor_id),
                    payload={"parent_id": actor_id, "child_id": child_id},
                )

    return handler


def _create_family(context: SimulationContext, command: object) -> None:
    if not isinstance(command, CreateFamily):
        raise TypeError("命令类型错误")
    if command.founder_id != context.state.controlled_entity_id:
        raise ValueError("只能由当前角色建立家族")
    name = command.name.strip()
    if not name or len(name) > 18:
        raise ValueError("家族名称必须为1至18个字符")
    lineage = context.state.entities.require(command.founder_id, LINEAGE)
    current_id = lineage.get("family_id")
    if current_id and context.state.entities.get(str(current_id), FAMILY_PROFILE):
        current = context.state.entities.require(str(current_id), FAMILY_PROFILE)
        if bool(current.get("active")):
            raise ValueError("你已经建立修仙家族")
    heirs = []
    for child_id in map(str, lineage.get("child_ids", [])):
        life = context.state.entities.require(child_id, LIFE)
        cultivation = context.state.entities.require(child_id, CULTIVATION)
        if bool(life.get("alive")) and str(cultivation.get("realm_id")) != "mortal":
            heirs.append(child_id)
    if not heirs:
        raise ValueError("至少要有一名拥有灵根并已经踏入仙途的后代，才能建立修仙家族")
    if any(
        context.state.entities.require(family_id, FAMILY_PROFILE).get("name") == name
        and bool(context.state.entities.require(family_id, FAMILY_PROFILE).get("active"))
        for family_id in context.state.entities.with_component(FAMILY_PROFILE)
    ):
        raise ValueError("家族名称已经存在")
    founder_identity = context.state.entities.require(command.founder_id, IDENTITY)
    founder_cultivation = context.state.entities.require(command.founder_id, CULTIVATION)
    world_id = str(context.state.entities.require(command.founder_id, LOCATION)["world_id"])
    family_id = context.state.entities.create("family")
    context.state.entities.put(
        family_id,
        FAMILY_PROFILE,
        {
            "name": name,
            "world_id": world_id,
            "path": founder_cultivation["path"],
            "allegiance_race": founder_identity["race"],
            "creator_id": command.founder_id,
            "controller_id": command.founder_id,
            "active": True,
            "founded_year": context.state.clock.year,
        },
    )
    context.state.relations.add(
        source_id=command.founder_id,
        target_id=family_id,
        kind="family_founder",
        created_year=context.state.clock.year,
    )
    for child_id in heirs:
        context.state.relations.add(
            source_id=child_id,
            target_id=family_id,
            kind=FAMILY_MEMBERSHIP,
            created_year=context.state.clock.year,
            metadata={"role": "lineal_heir"},
        )
    lineage["family_id"] = family_id
    context.state.entities.put(command.founder_id, LINEAGE, lineage)
    context.emit(
        "family.founded",
        source="family",
        scope=EventScope("faction", family_id),
        payload={
            "family_id": family_id,
            "founder_id": command.founder_id,
            "name": name,
            "heir_ids": heirs,
        },
    )


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    memberships = context.state.relations.find(
        source_id=entity_id, kind=FAMILY_MEMBERSHIP
    )
    for membership in memberships:
        family_id = membership.target_id
        living = [
            edge for edge in context.state.relations.find(
                target_id=family_id, kind=FAMILY_MEMBERSHIP
            )
            if bool(context.state.entities.require(edge.source_id, LIFE).get("alive"))
        ]
        if not living:
            profile = context.state.entities.require(family_id, FAMILY_PROFILE)
            profile["active"] = False
            profile["extinct_year"] = context.state.clock.year
            context.state.entities.put(family_id, FAMILY_PROFILE, profile)
            context.emit(
                "family.extinct",
                source="family",
                scope=EventScope("faction", family_id),
                payload={"family_id": family_id},
            )


def family_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    for entity_id in state.entities.with_component(IDENTITY):
        lineage = state.entities.get(entity_id, LINEAGE)
        if lineage is None:
            errors.append(f"角色 {entity_id} 缺少家族血脉组件")
            continue
        child_ids = list(map(str, lineage.get("child_ids", [])))
        if len(child_ids) != len(set(child_ids)):
            errors.append(f"角色 {entity_id} 的后代列表重复")
        for child_id in child_ids:
            if not any(
                edge.target_id == child_id
                for edge in state.relations.find(
                    source_id=entity_id, kind=PARENT_CHILD
                )
            ):
                errors.append(f"角色 {entity_id} 的后代缺少亲子关系边：{child_id}")
    for family_id in state.entities.with_component(FAMILY_PROFILE):
        profile = state.entities.require(family_id, FAMILY_PROFILE)
        if not str(profile.get("name", "")).strip():
            errors.append(f"家族 {family_id} 缺少名称")
        if not state.entities.exists(str(profile.get("creator_id", ""))):
            errors.append(f"家族 {family_id} 缺少创建者")
    return errors


def register_family_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(CreateFamily, _create_family)
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("family.conception_bonus.granted", _on_conception_bonus)
    bus.event_bus.register(
        "family.conception.requested", _on_conception_requested(definitions)
    )
    bus.event_bus.register("core.time.advanced", _on_time_advanced(definitions))
    bus.event_bus.register("character.died", _on_character_died)


def family_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    del definitions
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    lineage = state.entities.require(actor_id, LINEAGE)
    children = []
    for child_id in map(str, lineage.get("child_ids", [])):
        child = character_view(state, child_id)
        cultivation = state.entities.require(child_id, CULTIVATION)
        location = state.entities.require(child_id, LOCATION)
        children.append({
            **child,
            "world_id": location["world_id"],
            "spirit_root": cultivation["spirit_root"],
            "realm_id": cultivation["realm_id"],
            "layer": cultivation["layer"],
            "cultivation_started": cultivation["realm_id"] != "mortal",
        })
    family_id = lineage.get("family_id")
    if not family_id:
        return {
            "exists": False,
            "can_found": any(row["alive"] and row["cultivation_started"] for row in children),
            "offspring": children,
            "pending_conception_bonus": lineage.get("next_conception_bonus", 0.0),
            "roster": [],
        }
    profile = state.entities.require(str(family_id), FAMILY_PROFILE)
    actor_world = state.entities.require(actor_id, LOCATION)["world_id"]
    preferences = state.entities.get(actor_id, PREFERENCES) or {}
    visible = profile["world_id"] == actor_world or bool(
        preferences.get("debug_world_news", False)
    )
    roster = []
    if visible:
        for edge in state.relations.find(
            target_id=str(family_id), kind=FAMILY_MEMBERSHIP
        ):
            member = character_view(state, edge.source_id)
            roster.append({**member, "role": edge.metadata.get("role", "member")})
    return {
        "exists": True,
        "id": family_id,
        **profile,
        "same_world": profile["world_id"] == actor_world,
        "offspring": children,
        "roster": roster,
        "living_count": sum(row["alive"] for row in roster) if visible else None,
        "pending_conception_bonus": lineage.get("next_conception_bonus", 0.0),
    }
