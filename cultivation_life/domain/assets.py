from __future__ import annotations

from typing import Any

from .character import IDENTITY
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, WorldState


ASSET_LEDGER = "economy.asset_ledger"
INVENTORY = "economy.inventory"


def _new_ledger() -> dict[str, Any]:
    return {"next_sequence": 1, "instances": {}, "reservations": {}}


def reconcile_asset_ledger(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        if state.entities.get(entity_id, ASSET_LEDGER) is None:
            state.entities.put(entity_id, ASSET_LEDGER, _new_ledger())


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(str(event.payload["entity_id"]), ASSET_LEDGER, _new_ledger())


def create_asset(
    context: SimulationContext,
    actor_id: str,
    *,
    kind: str,
    definition_id: str,
    name: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    sequence = int(ledger.get("next_sequence", 1))
    asset_id = f"asset:{actor_id}:{sequence}"
    instances = dict(ledger.get("instances", {}))
    instances[asset_id] = {
        "id": asset_id,
        "kind": kind,
        "definition_id": definition_id,
        "name": name,
        "created_year": context.state.clock.year,
        "metadata": dict(metadata or {}),
        "reservation_id": None,
    }
    ledger.update(next_sequence=sequence + 1, instances=instances)
    context.state.entities.put(actor_id, ASSET_LEDGER, ledger)
    return asset_id


def require_asset(state: WorldState, actor_id: str, asset_id: str) -> dict[str, Any]:
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    asset = dict(ledger.get("instances", {})).get(asset_id)
    if not isinstance(asset, dict):
        raise ValueError("实例资产不存在")
    return dict(asset)


def consume_asset(context: SimulationContext, actor_id: str, asset_id: str) -> dict[str, Any]:
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    instances = dict(ledger.get("instances", {}))
    asset = instances.get(asset_id)
    if not isinstance(asset, dict):
        raise ValueError("实例资产不存在")
    if asset.get("reservation_id"):
        raise ValueError("实例资产正在预留或托管中")
    removed = dict(instances.pop(asset_id))
    ledger["instances"] = instances
    context.state.entities.put(actor_id, ASSET_LEDGER, ledger)
    return removed


def reserve_asset(
    context: SimulationContext,
    actor_id: str,
    *,
    purpose: str,
    asset_id: str | None = None,
    item_id: str | None = None,
    quantity: int = 1,
) -> str:
    if (asset_id is None) == (item_id is None):
        raise ValueError("预留必须且只能指定一种资产")
    if not purpose.strip() or quantity <= 0:
        raise ValueError("预留用途或数量非法")
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    sequence = int(ledger.get("next_sequence", 1))
    reservation_id = f"reservation:{actor_id}:{sequence}"
    reservations = dict(ledger.get("reservations", {}))
    if asset_id is not None:
        instances = dict(ledger.get("instances", {}))
        asset = instances.get(asset_id)
        if not isinstance(asset, dict) or asset.get("reservation_id"):
            raise ValueError("实例资产不存在或已经预留")
        asset = dict(asset)
        asset["reservation_id"] = reservation_id
        instances[asset_id] = asset
        ledger["instances"] = instances
        reservations[reservation_id] = {
            "id": reservation_id, "kind": "instance", "asset_id": asset_id,
            "quantity": 1, "purpose": purpose, "created_year": context.state.clock.year,
        }
    else:
        inventory = context.state.entities.require(actor_id, INVENTORY)
        items = dict(inventory.get("items", {}))
        reserved = dict(inventory.get("reserved", {}))
        available = int(items.get(str(item_id), 0)) - int(reserved.get(str(item_id), 0))
        if available < quantity:
            raise ValueError("可用物品数量不足")
        reserved[str(item_id)] = int(reserved.get(str(item_id), 0)) + quantity
        inventory["reserved"] = reserved
        context.state.entities.put(actor_id, INVENTORY, inventory)
        reservations[reservation_id] = {
            "id": reservation_id, "kind": "stack", "item_id": str(item_id),
            "quantity": quantity, "purpose": purpose, "created_year": context.state.clock.year,
        }
    ledger.update(next_sequence=sequence + 1, reservations=reservations)
    context.state.entities.put(actor_id, ASSET_LEDGER, ledger)
    return reservation_id


def release_reservation(
    context: SimulationContext, actor_id: str, reservation_id: str,
) -> dict[str, Any]:
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    reservations = dict(ledger.get("reservations", {}))
    reservation = reservations.pop(reservation_id, None)
    if not isinstance(reservation, dict):
        raise ValueError("资产预留不存在")
    if reservation["kind"] == "instance":
        instances = dict(ledger.get("instances", {}))
        asset = dict(instances[str(reservation["asset_id"])])
        asset["reservation_id"] = None
        instances[asset["id"]] = asset
        ledger["instances"] = instances
    else:
        inventory = context.state.entities.require(actor_id, INVENTORY)
        reserved = dict(inventory.get("reserved", {}))
        item_id = str(reservation["item_id"])
        remaining = int(reserved.get(item_id, 0)) - int(reservation["quantity"])
        if remaining > 0:
            reserved[item_id] = remaining
        else:
            reserved.pop(item_id, None)
        inventory["reserved"] = reserved
        context.state.entities.put(actor_id, INVENTORY, inventory)
    ledger["reservations"] = reservations
    context.state.entities.put(actor_id, ASSET_LEDGER, ledger)
    return dict(reservation)


def settle_reservation(
    context: SimulationContext, actor_id: str, reservation_id: str,
) -> dict[str, Any]:
    """Consume the asset held by a reservation and remove the escrow record."""
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    reservations = dict(ledger.get("reservations", {}))
    reservation = reservations.pop(reservation_id, None)
    if not isinstance(reservation, dict):
        raise ValueError("资产预留不存在")
    if reservation["kind"] == "instance":
        instances = dict(ledger.get("instances", {}))
        asset_id = str(reservation["asset_id"])
        asset = instances.get(asset_id)
        if not isinstance(asset, dict) or asset.get("reservation_id") != reservation_id:
            raise ValueError("实例资产预留已经失效")
        instances.pop(asset_id)
        ledger["instances"] = instances
    else:
        inventory = context.state.entities.require(actor_id, INVENTORY)
        items = dict(inventory.get("items", {}))
        reserved = dict(inventory.get("reserved", {}))
        item_id = str(reservation["item_id"])
        quantity = int(reservation["quantity"])
        if int(items.get(item_id, 0)) < quantity or int(reserved.get(item_id, 0)) < quantity:
            raise ValueError("堆叠资产预留已经失效")
        remaining_items = int(items[item_id]) - quantity
        if remaining_items:
            items[item_id] = remaining_items
        else:
            items.pop(item_id, None)
        remaining_reserved = int(reserved[item_id]) - quantity
        if remaining_reserved:
            reserved[item_id] = remaining_reserved
        else:
            reserved.pop(item_id, None)
        inventory.update(items=items, reserved=reserved)
        context.state.entities.put(actor_id, INVENTORY, inventory)
    ledger["reservations"] = reservations
    context.state.entities.put(actor_id, ASSET_LEDGER, ledger)
    return dict(reservation)


def release_all_reservations(context: SimulationContext, actor_id: str) -> None:
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    for reservation_id in list(dict(ledger.get("reservations", {}))):
        release_reservation(context, actor_id, reservation_id)


def _on_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    release_all_reservations(context, actor_id)
    if event.event_type == "world.permanent_transition.requested":
        context.emit(
            "world.transition.acknowledged",
            source="assets",
            scope=event.scope,
            payload={
                "transaction_id": event.payload["transaction_id"],
                "actor_id": actor_id,
                "domain": "assets",
            },
        )


def asset_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    for entity_id in state.entities.with_component(IDENTITY):
        ledger = state.entities.get(entity_id, ASSET_LEDGER)
        if ledger is None:
            errors.append(f"角色 {entity_id} 缺少实例资产账本")
            continue
        instances = dict(ledger.get("instances", {}))
        reservations = dict(ledger.get("reservations", {}))
        for asset_id, asset in instances.items():
            if asset_id != asset.get("id") or not asset.get("kind") or not asset.get("name"):
                errors.append(f"角色 {entity_id} 的实例资产结构无效：{asset_id}")
            reservation_id = asset.get("reservation_id")
            if reservation_id and reservation_id not in reservations:
                errors.append(f"角色 {entity_id} 的实例资产引用失效预留：{asset_id}")
        stack_totals: dict[str, int] = {}
        for reservation_id, reservation in reservations.items():
            if reservation_id != reservation.get("id"):
                errors.append(f"角色 {entity_id} 的资产预留ID不一致")
            if reservation.get("kind") == "instance":
                asset = instances.get(str(reservation.get("asset_id")))
                if not asset or asset.get("reservation_id") != reservation_id:
                    errors.append(f"角色 {entity_id} 的实例预留引用无效")
            elif reservation.get("kind") == "stack":
                item_id = str(reservation.get("item_id", ""))
                stack_totals[item_id] = stack_totals.get(item_id, 0) + int(
                    reservation.get("quantity", 0)
                )
            else:
                errors.append(f"角色 {entity_id} 的资产预留类型无效")
        inventory = state.entities.get(entity_id, INVENTORY) or {}
        reserved = dict(inventory.get("reserved", {}))
        if stack_totals != {key: int(value) for key, value in reserved.items() if int(value)}:
            errors.append(f"角色 {entity_id} 的堆叠预留与资产账本不一致")
    return errors


def register_asset_domain(bus: CommandBus) -> None:
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("world.permanent_transition.requested", _on_world_transition)
    bus.event_bus.register("world.temporary_transition.committed", _on_world_transition)


def asset_view(state: WorldState, entity_id: str | None = None) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    return {
        "instances": [dict(value) for _, value in sorted(dict(ledger["instances"]).items())],
        "reservations": [
            dict(value) for _, value in sorted(dict(ledger["reservations"]).items())
        ],
    }
