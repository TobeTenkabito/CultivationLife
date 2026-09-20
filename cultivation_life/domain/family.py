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
            "last_recruitment_year": context.state.clock.year,
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
            metadata={"role": "lineal_heir", "cultivation_progress": 0.0},
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


def _on_character_died(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        entity_id = str(event.payload["entity_id"])
        memberships = context.state.relations.find(
            source_id=entity_id, kind=FAMILY_MEMBERSHIP
        )
        family_ids = {membership.target_id for membership in memberships}
        family_ids.update(
            family_id
            for family_id in context.state.entities.with_component(FAMILY_PROFILE)
            if context.state.entities.require(
                family_id, FAMILY_PROFILE
            ).get("controller_id") == entity_id
        )
        for family_id in family_ids:
            profile = context.state.entities.require(family_id, FAMILY_PROFILE)
            if profile.get("controller_id") == entity_id:
                candidates: list[tuple[int, int, str]] = []
                for edge in context.state.relations.find(
                    target_id=family_id, kind=FAMILY_MEMBERSHIP
                ):
                    if edge.source_id == entity_id:
                        continue
                    life = context.state.entities.require(edge.source_id, LIFE)
                    if not bool(life.get("alive")):
                        continue
                    cultivation = context.state.entities.require(
                        edge.source_id, CULTIVATION
                    )
                    candidates.append((
                        definitions.realm_index(str(cultivation["realm_id"])),
                        int(cultivation["layer"]), edge.source_id,
                    ))
                profile["controller_id"] = (
                    max(candidates)[2] if candidates else None
                )
                context.state.entities.put(family_id, FAMILY_PROFILE, profile)
            living = [
                edge for edge in context.state.relations.find(
                    target_id=family_id, kind=FAMILY_MEMBERSHIP
                )
                if bool(context.state.entities.require(
                    edge.source_id, LIFE
                ).get("alive"))
            ]
            if not living:
                profile["active"] = False
                profile["extinct_year"] = context.state.clock.year
                context.state.entities.put(family_id, FAMILY_PROFILE, profile)
                context.emit(
                    "family.extinct", source="family",
                    scope=EventScope("faction", family_id),
                    payload={"family_id": family_id},
                )

    return handler


def _family_recruit(
    context: SimulationContext, definitions: GameDefinitions, family_id: str,
) -> str:
    profile = context.state.entities.require(family_id, FAMILY_PROFILE)
    rules = dict(definitions.systems.get("factions", {}))
    distributions = dict(rules.get("recruitment_distribution_by_world", {}))
    distribution = list(
        distributions.get(str(profile["world_id"]))
        or rules.get("recruitment_distribution", [{"upper": 1.0, "realm_index": 1}])
    )
    roll = context.rng.random()
    realm_index = int(distribution[-1]["realm_index"])
    for row in distribution:
        if roll <= float(row["upper"]):
            realm_index = int(row["realm_index"])
            break
    realm_index = max(0, min(len(definitions.realms) - 1, realm_index))
    realm = definitions.realms[realm_index]
    age = max(16, context.rng.randint(18, 42) + realm_index * 24)
    lifespan = None
    if realm.lifespan is not None:
        lifespan = max(age + 1, context.rng.randint(*realm.lifespan))
    surname = str(profile["name"])[:1] or "林"
    character_id = create_character(
        context,
        name=surname + context.rng.choice(["宁", "安", "澄", "昭", "遥", "真", "元", "清"]),
        age=age, gender=context.rng.choice(["male", "female"]),
        race=str(profile.get("allegiance_race", "human")),
        spirit_root=context.rng.choice([
            "supreme_wood", "supreme_water", "heavenly_metal_fire"
        ]),
        path=str(profile.get("path", "dao")), realm_id=realm.id,
        layer=1 if realm_index == 0 else context.rng.randint(1, min(3, realm.layers)),
        world_id=str(profile["world_id"]), lifespan=lifespan,
    )
    edge = context.state.relations.add(
        source_id=character_id, target_id=family_id, kind=FAMILY_MEMBERSHIP,
        created_year=context.state.clock.year,
        metadata={"role": "external_member", "cultivation_progress": 0.0},
    )
    context.emit(
        "family.member.recruited", source="family",
        scope=EventScope("faction", family_id), payload=edge.to_dict(),
    )
    return character_id


def _advance_family_members(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        from .intrigue import is_intrigue_imprisoned

        elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
        if elapsed <= 0:
            return
        rules = dict(definitions.systems.get("factions", {}))
        cultivation_rules = dict(rules.get("npc_cultivation", {}))
        progress_rates = dict(cultivation_rules.get("progress_per_year", {}))
        threshold = float(cultivation_rules.get("threshold", 100.0))
        base_success = float(cultivation_rules.get("base_success", 0.64))
        retention = float(cultivation_rules.get("failed_progress_retained", 0.55))
        accident = float(cultivation_rules.get("accident_death_chance", 0.0005))
        for family_id in list(context.state.entities.with_component(FAMILY_PROFILE)):
            profile = context.state.entities.require(family_id, FAMILY_PROFILE)
            if not bool(profile.get("active")):
                continue
            for edge in list(context.state.relations.find(
                target_id=family_id, kind=FAMILY_MEMBERSHIP
            )):
                # NPC cultivation is owned by the canonical lifecycle domain.
                # This handler still owns family recruitment below.
                if context.state.entities.get(
                    edge.source_id, "simulation.npc_lifecycle"
                ) is not None:
                    continue
                life = context.state.entities.require(edge.source_id, LIFE)
                if not bool(life.get("alive")) or is_intrigue_imprisoned(
                    context.state, edge.source_id
                ):
                    continue
                cultivation = context.state.entities.require(edge.source_id, CULTIVATION)
                metadata = dict(edge.metadata)
                for _ in range(elapsed):
                    if context.rng.random() < accident:
                        context.emit(
                            "character.lethal_hazard", source="family",
                            scope=EventScope.entity(edge.source_id),
                            payload={"entity_id": edge.source_id, "reason": "家族修行意外陨落"},
                        )
                        break
                    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
                    if realm_index == 0 or realm_index >= len(definitions.realms) - 1:
                        continue
                    progress = float(metadata.get("cultivation_progress", 0.0))
                    progress += float(progress_rates.get(str(realm_index), 0.0))
                    if progress < threshold:
                        metadata["cultivation_progress"] = progress
                        continue
                    root = definitions.roots.get(str(cultivation.get("spirit_root", "none")))
                    chance = base_success
                    if root is not None:
                        chance += (float(root.efficiency) - 1.0) * float(
                            cultivation_rules.get("root_success_scale", 0.20)
                        )
                    chance = max(0.05, min(0.95, chance))
                    if context.rng.random() >= chance:
                        metadata["cultivation_progress"] = threshold * retention
                        continue
                    realm = definitions.realms[realm_index]
                    old = (str(cultivation["realm_id"]), int(cultivation["layer"]))
                    if int(cultivation["layer"]) < realm.layers:
                        cultivation["layer"] = int(cultivation["layer"]) + 1
                    else:
                        cultivation["realm_id"] = definitions.realms[realm_index + 1].id
                        cultivation["layer"] = 1
                        next_span = definitions.realms[realm_index + 1].lifespan
                        if next_span is not None:
                            age = context.state.clock.year - int(life["birth_year"])
                            life["lifespan"] = max(
                                int(life.get("lifespan") or 0), age + 1,
                                context.rng.randint(*next_span),
                            )
                            context.state.entities.put(edge.source_id, LIFE, life)
                            context.emit(
                                "character.lifespan.changed", source="family",
                                scope=EventScope.entity(edge.source_id),
                                payload={"entity_id": edge.source_id},
                            )
                    metadata["cultivation_progress"] = 0.0
                    context.emit(
                        "family.member.breakthrough", source="family",
                        scope=EventScope("faction", family_id),
                        payload={
                            "family_id": family_id, "character_id": edge.source_id,
                            "before": old,
                            "after": (str(cultivation["realm_id"]), int(cultivation["layer"])),
                        },
                    )
                context.state.entities.put(edge.source_id, CULTIVATION, cultivation)
                context.state.relations.replace_metadata(edge.relation_id, metadata)
            interval = max(1, int(rules.get("recruitment_interval_years", 5)))
            last = int(profile.get("last_recruitment_year") or 0)
            due = int(event.payload["to_year"]) // interval > last // interval
            living_count = sum(
                bool(context.state.entities.require(row.source_id, LIFE).get("alive"))
                for row in context.state.relations.find(
                    target_id=family_id, kind=FAMILY_MEMBERSHIP
                )
            )
            if due and living_count < int(rules.get("max_members", 36)):
                _family_recruit(context, definitions, family_id)
                profile["last_recruitment_year"] = int(event.payload["to_year"])
                context.state.entities.put(family_id, FAMILY_PROFILE, profile)

    return handler


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
    bus.event_bus.register("core.time.advanced", _advance_family_members(definitions))
    bus.event_bus.register("character.died", _on_character_died(definitions))


def family_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
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
            cultivation = state.entities.require(edge.source_id, CULTIVATION)
            roster.append({
                **member,
                "role": edge.metadata.get("role", "member"),
                "realm_id": cultivation["realm_id"],
                "realm_index": definitions.realm_index(str(cultivation["realm_id"])),
                "layer": cultivation["layer"],
                "cultivation_progress": float(edge.metadata.get("cultivation_progress", 0.0)),
            })
    return {
        "exists": True,
        "id": family_id,
        **profile,
        "same_world": profile["world_id"] == actor_world,
        "has_voice": bool(
            profile.get("controller_id") == actor_id
            and profile["world_id"] == actor_world
        ),
        "offspring": children,
        "roster": roster,
        "living_count": sum(row["alive"] for row in roster) if visible else None,
        "pending_conception_bonus": lineage.get("next_conception_bonus", 0.0),
    }
