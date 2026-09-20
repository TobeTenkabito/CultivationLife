from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE
from .actions import begin_action, complete_action
from .definitions import GameDefinitions
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState
from ..kernel.services import TimeService


LOCATION = "world.location"
WORLD_TRANSITION = "world.transition"
TRAVEL_DUE = "world.travel.due"


@dataclass(frozen=True, slots=True)
class TravelWithinWorld:
    actor_id: str
    destination_id: str


@dataclass(frozen=True, slots=True)
class AscendWorld:
    actor_id: str
    destination_world_id: str
    invited_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CrossWorld:
    actor_id: str
    destination_world_id: str


def reconcile_world_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        if state.entities.get(entity_id, WORLD_TRANSITION) is None:
            state.entities.put(entity_id, WORLD_TRANSITION, {
                "sealed_cultivation": None, "last_transaction": None, "history": [],
            })


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
        context.state.entities.put(
            entity_id,
            WORLD_TRANSITION,
            {"sealed_cultivation": None, "last_transaction": None, "history": []},
        )

    return handler


def _transition_ack(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        transition = context.state.entities.require(actor_id, WORLD_TRANSITION)
        transaction = transition.get("last_transaction")
        if not isinstance(transaction, dict) or transaction.get("id") != event.payload.get("transaction_id"):
            raise ValueError("跨界清理回执不属于当前事务")
        domain = str(event.payload["domain"])
        if domain not in transaction.get("required_domains", []):
            raise ValueError(f"跨界事务收到未声明领域回执：{domain}")
        acknowledgements = list(transaction.get("acknowledgements", []))
        if domain in acknowledgements:
            raise ValueError(f"跨界领域重复回执：{domain}")
        acknowledgements.append(domain)
        transaction["acknowledgements"] = acknowledgements
        transition["last_transaction"] = transaction
        context.state.entities.put(actor_id, WORLD_TRANSITION, transition)
        if (
            transaction.get("status") == "preparing"
            and bool(transaction.get("commit_after_ack"))
            and set(acknowledgements) == set(transaction.get("required_domains", []))
        ):
            _commit_transition(
                context,
                definitions,
                actor_id=actor_id,
                destination=str(transaction["destination"]),
                transaction_id=str(transaction["id"]),
            )

    return handler


def _eligible_entourage(
    context: SimulationContext,
    definitions: GameDefinitions,
    actor_id: str,
    invited_ids: tuple[str, ...],
    origin: str,
) -> tuple[list[str], list[str]]:
    invited = list(dict.fromkeys(map(str, invited_ids)))
    if len(invited) != len(invited_ids):
        raise ValueError("同行邀请不能重复")
    keep: list[str] = []
    fallen: list[str] = []
    relation_by_other = {}
    for edge in context.state.relations.involving(actor_id):
        if edge.kind not in {"friend", "dao_companion"}:
            continue
        other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
        relation_by_other[other_id] = edge
    actor_cultivation = context.state.entities.require(actor_id, "cultivation.state")
    actor_realm = definitions.realm_index(str(actor_cultivation["realm_id"]))
    chance = float(definitions.systems.get("relationship", {}).get(
        "friend_crossing_survival_chance", 0.35
    ))
    for other_id in invited:
        edge = relation_by_other.get(other_id)
        if edge is None:
            raise ValueError("只有道侣和好友可以受邀同行")
        life = context.state.entities.require(other_id, LIFE)
        location = context.state.entities.require(other_id, LOCATION)
        cultivation = context.state.entities.require(other_id, "cultivation.state")
        if not bool(life.get("alive")) or location.get("world_id") != origin:
            raise ValueError("受邀者已经死亡或不在同一界面")
        if definitions.realm_index(str(cultivation["realm_id"])) < actor_realm:
            raise ValueError("受邀者境界不足，无法穿过界壁")
        if edge.kind == "dao_companion" or context.rng.random() < chance:
            keep.append(other_id)
        else:
            fallen.append(other_id)
    return keep, fallen


def _begin_cleanup_transaction(
    context: SimulationContext,
    *,
    actor_id: str,
    origin: str,
    destination: str,
    keep_ids: list[str],
    fallen_ids: list[str],
    commit_after_ack: bool = False,
) -> str:
    transition = context.state.entities.require(actor_id, WORLD_TRANSITION)
    previous = transition.get("last_transaction")
    if isinstance(previous, dict) and previous.get("status") == "preparing":
        raise ValueError("已有跨界事务正在处理")
    transaction_id = f"crossing:{context.state.next_event_sequence:010d}"
    required = [
        "relations", "factions", "economy", "assets", "auction", "artifacts",
        "combat", "party", "demonic",
    ]
    transition["last_transaction"] = {
        "id": transaction_id,
        "status": "preparing",
        "origin": origin,
        "destination": destination,
        "required_domains": required,
        "acknowledgements": [],
        "keep_ids": list(keep_ids),
        "fallen_ids": list(fallen_ids),
        "commit_after_ack": commit_after_ack,
    }
    context.state.entities.put(actor_id, WORLD_TRANSITION, transition)
    context.emit(
        "world.permanent_transition.requested",
        source="world",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": transaction_id,
            "actor_id": actor_id,
            "origin_world_id": origin,
            "destination_world_id": destination,
            "keep_relationship_ids": list(keep_ids),
            "fallen_ids": list(fallen_ids),
        },
    )
    transition = context.state.entities.require(actor_id, WORLD_TRANSITION)
    transaction = dict(transition["last_transaction"])
    missing = set(required) - set(transaction.get("acknowledgements", []))
    if missing and not commit_after_ack:
        raise ValueError(f"跨界清理未完成：{', '.join(sorted(missing))}")
    return transaction_id


def _commit_transition(
    context: SimulationContext,
    definitions: GameDefinitions,
    *, actor_id: str, destination: str, transaction_id: str,
) -> None:
    location = context.state.entities.require(actor_id, LOCATION)
    origin = str(location["world_id"])
    location.update(
        world_id=destination,
        location_id=definitions.default_location(destination),
    )
    context.state.entities.put(actor_id, LOCATION, location)
    transition = context.state.entities.require(actor_id, WORLD_TRANSITION)
    transaction = dict(transition["last_transaction"])
    if transaction.get("id") != transaction_id:
        raise ValueError("跨界事务在提交前被替换")
    transaction["status"] = "committed"
    transaction["committed_year"] = context.state.clock.year
    transition["last_transaction"] = transaction
    history = list(transition.get("history", []))
    history.append({
        "transaction_id": transaction_id, "kind": "permanent",
        "origin": origin, "destination": destination,
        "year": context.state.clock.year,
    })
    transition["history"] = history[-50:]
    context.state.entities.put(actor_id, WORLD_TRANSITION, transition)
    for other_id in transaction.get("keep_ids", []):
        other_location = context.state.entities.require(str(other_id), LOCATION)
        other_location.update(
            world_id=destination,
            location_id=definitions.default_location(destination),
        )
        context.state.entities.put(str(other_id), LOCATION, other_location)
    for other_id in transaction.get("fallen_ids", []):
        context.emit(
            "character.lethal_hazard",
            source="world",
            scope=EventScope.entity(str(other_id)),
            payload={"entity_id": str(other_id), "reason": "穿越界壁时失陷于空间风暴"},
        )
    context.emit(
        "world.permanent_transition.committed",
        source="world",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": transaction_id, "actor_id": actor_id,
            "origin_world_id": origin, "destination_world_id": destination,
        },
    )


def _ascend_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, AscendWorld):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能控制当前角色飞升")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("死亡角色不能飞升")
        location = context.state.entities.require(command.actor_id, LOCATION)
        origin = str(location["world_id"])
        destination = command.destination_world_id
        cultivation = context.state.entities.require(command.actor_id, "cultivation.state")
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        layer = int(cultivation["layer"])
        path = str(cultivation["path"])
        routes = {
            ("human", "spirit"): (path in {"dao", "buddhist", "confucian"}, 5, 3),
            ("human", "demon"): (path == "demonic", 5, 3),
            ("human", "monster_realm"): (path == "monster", 5, 3),
            ("human", "hell"): (path == "ghost", 5, 3),
            ("demon", "true_demon"): (path == "demonic", 5, 1),
        }
        allowed, required_realm, max_start_layer = routes.get(
            (origin, destination), (False, -1, -1)
        )
        imprisoned = bool(context.state.relations.find(
            target_id=command.actor_id, kind="combat_prisoner"
        ))
        prison_crossing_routes = {
            ("human", "spirit"), ("human", "monster_realm"), ("human", "hell"),
        }
        if imprisoned and (origin, destination) not in prison_crossing_routes:
            raise ValueError("服刑期间只能尝试人界偷渡")
        if not allowed or realm_index != required_realm or layer > max_start_layer:
            if (origin, destination) in {("spirit", "celestial"), ("true_demon", "asura")}:
                raise ValueError("该飞升路线必须通过九重飞升试炼，请使用飞升试炼入口")
            raise ValueError("当前道统、境界或界面不满足飞升条件")
        if destination not in definitions.worlds or not definitions.worlds[destination].enabled:
            raise ValueError("目标界面尚未开放")
        keep, fallen = _eligible_entourage(
            context, definitions, command.actor_id, command.invited_ids, origin,
        )
        transaction_id = _begin_cleanup_transaction(
            context, actor_id=command.actor_id, origin=origin, destination=destination,
            keep_ids=keep, fallen_ids=fallen,
        )
        _commit_transition(
            context, definitions, actor_id=command.actor_id,
            destination=destination, transaction_id=transaction_id,
        )

    return handler


def _on_ascension_commit_requested(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        location = context.state.entities.require(actor_id, LOCATION)
        origin = str(location["world_id"])
        destination = str(event.payload["destination_world_id"])
        expected = {("spirit", "celestial"), ("true_demon", "asura")}
        if (origin, destination) not in expected:
            raise ValueError("飞升试炼的起点与目标界面不匹配")
        keep, fallen = _eligible_entourage(
            context,
            definitions,
            actor_id,
            tuple(map(str, event.payload.get("invited_ids", []))),
            origin,
        )
        _begin_cleanup_transaction(
            context,
            actor_id=actor_id,
            origin=origin,
            destination=destination,
            keep_ids=keep,
            fallen_ids=fallen,
            commit_after_ack=True,
        )

    return handler


def _on_monster_ascension_requested(definitions: GameDefinitions):
    """Commit the realm-eight bloodline ascension through normal cleanup."""
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        actor_id = str(event.payload["actor_id"])
        destination = str(event.payload.get("destination_world_id", "nether"))
        location = context.state.entities.require(actor_id, LOCATION)
        origin = str(location["world_id"])
        cultivation = context.state.entities.require(actor_id, "cultivation.state")
        if cultivation.get("path") != "monster" or definitions.realm_index(
            str(cultivation["realm_id"])
        ) != 9:
            raise ValueError("妖修血脉飞升请求与角色境界不一致")
        if destination != "nether" or destination not in definitions.worlds:
            raise ValueError("妖修血脉飞升目标无效")
        _begin_cleanup_transaction(
            context,
            actor_id=actor_id,
            origin=origin,
            destination=destination,
            keep_ids=[],
            fallen_ids=[],
            commit_after_ack=True,
        )

    return handler


def _cross_world_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, CrossWorld):
            raise TypeError("命令类型错误")
        if command.actor_id != context.state.controlled_entity_id:
            raise ValueError("只能控制当前角色跨界")
        if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
            raise ValueError("死亡角色不能跨界")
        if context.state.relations.find(target_id=command.actor_id, kind="combat_prisoner"):
            raise ValueError("服刑期间不能正常跨界")
        location = context.state.entities.require(command.actor_id, LOCATION)
        origin, destination = str(location["world_id"]), command.destination_world_id
        lower_worlds = {
            "spirit": {"human"}, "true_demon": {"demon"},
            "celestial": {"spirit"}, "asura": {"true_demon"},
            "nether": {"monster_realm", "phantom_underworld"},
            "hell": {"human"},
        }
        reverse = {
            lower: upper
            for upper, lowers in lower_worlds.items()
            for lower in lowers
        }
        transition = context.state.entities.require(command.actor_id, WORLD_TRANSITION)
        cultivation = context.state.entities.require(command.actor_id, "cultivation.state")
        sealed = transition.get("sealed_cultivation")
        if destination in lower_worlds.get(origin, set()):
            if sealed is not None:
                raise ValueError("当前已经处于下界封印状态")
            required = int(definitions.systems["world_travel"][
                "celestial_required_realm"
                if origin in {"celestial", "asura", "nether"}
                else "required_realm"
            ])
            if definitions.realm_index(str(cultivation["realm_id"])) < required:
                raise ValueError("境界不足，无法逆穿界壁")
            transition["sealed_cultivation"] = {
                "realm_id": cultivation["realm_id"], "layer": cultivation["layer"],
                "upper_world": origin, "lower_world": destination,
            }
            suppressed_index = int(definitions.systems["world_travel"][
                "spirit_suppression_realm"
                if origin in {"celestial", "asura", "nether"}
                else "human_suppression_realm"
            ])
            cultivation["realm_id"] = definitions.realms[suppressed_index].id
            cultivation["layer"] = int(definitions.systems["world_travel"][
                "spirit_suppression_layer"
                if origin in {"celestial", "asura", "nether"}
                else "human_suppression_layer"
            ])
            cultivation["bottleneck"] = None
        elif sealed and origin == sealed.get("lower_world") and destination == sealed.get("upper_world"):
            cultivation["realm_id"] = sealed["realm_id"]
            cultivation["layer"] = int(sealed["layer"])
            cultivation["bottleneck"] = None
            transition["sealed_cultivation"] = None
        else:
            expected = reverse.get(origin)
            if expected == destination:
                raise ValueError("没有可在目标上界复原的封存道果")
            raise ValueError("目标界面不是当前界面的合法往返对象")
        location.update(
            world_id=destination,
            location_id=definitions.default_location(destination),
        )
        context.state.entities.put(command.actor_id, LOCATION, location)
        context.state.entities.put(command.actor_id, "cultivation.state", cultivation)
        context.state.entities.put(command.actor_id, WORLD_TRANSITION, transition)
        context.emit(
            "world.temporary_transition.committed",
            source="world",
            scope=EventScope.entity(command.actor_id),
            payload={
                "actor_id": command.actor_id, "origin_world_id": origin,
                "destination_world_id": destination,
                "suppressed": transition.get("sealed_cultivation") is not None,
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
        action_token = begin_action(
            context,
            actor_id=command.actor_id,
            action="travel",
            years=plan.years,
            source="world.travel",
            metadata={"destination_id": plan.destination},
        )
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
                "action_token": action_token,
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
    complete_action(
        context,
        actor_id=actor_id,
        token=str(event.payload["action_token"]),
        metadata={"destination_id": event.payload["destination_id"]},
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
            transition = state.entities.get(entity_id, WORLD_TRANSITION)
            if location is None or transition is None:
                errors.append(f"角色 {entity_id} 缺少位置组件")
                continue
            world_id = str(location.get("world_id", ""))
            location_id = str(location.get("location_id", ""))
            if world_id not in definitions.worlds:
                errors.append(f"角色 {entity_id} 位于未知世界 {world_id}")
            elif location_id not in definitions.worlds[world_id].locations:
                errors.append(f"角色 {entity_id} 位于未知地点 {location_id}")
            transaction = transition.get("last_transaction")
            if isinstance(transaction, dict):
                if transaction.get("status") == "preparing":
                    errors.append(f"角色 {entity_id} 的跨界事务尚未完成")
                elif transaction.get("status") != "committed":
                    errors.append(f"角色 {entity_id} 的跨界事务状态无效")
                elif set(transaction.get("acknowledgements", [])) != set(transaction.get("required_domains", [])):
                    errors.append(f"角色 {entity_id} 的跨界事务缺少领域回执")
        return errors

    return validate


def register_world_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(TravelWithinWorld, _travel_handler(definitions))
    bus.register(AscendWorld, _ascend_handler(definitions))
    bus.register(CrossWorld, _cross_world_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created(definitions))
    bus.event_bus.register(TRAVEL_DUE, _on_travel_due)
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register(
        "world.transition.acknowledged", _transition_ack(definitions)
    )
    bus.event_bus.register(
        "world.ascension.commit.requested", _on_ascension_commit_requested(definitions)
    )
    bus.event_bus.register(
        "world.monster_ascension.requested",
        _on_monster_ascension_requested(definitions),
    )


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
        public_location = {
            "id": target_id, "name": target.name,
            "description": target.description,
            "themes": list(target.themes),
            "combat_terrain": target.combat_terrain,
            "combat_conditions": list(target.combat_conditions),
            "qi_gain_efficiencies": dict(target.qi_gain_efficiencies),
        }
        if target_id == location_id:
            destinations.append({
                **public_location, "current": True, "travel_years": 0,
                "accessible": True, "warning": "", "route": [target_id],
            })
            continue
        plan = world.travel_plan(
            location_id,
            target_id,
            realm_index,
            definitions.travel_speeds[realm_index],
        )
        destinations.append({
            **public_location,
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
        "transition": state.entities.require(actor_id, WORLD_TRANSITION),
    }
