from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from .assets import (
    ASSET_LEDGER,
    consume_asset,
    create_asset,
    release_reservation,
    require_asset,
    reserve_asset,
)
from .character import IDENTITY, LIFE
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .economy import CURRENCY_ID, change_inventory_item, inventory_quantity
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


CRAFTING = "crafting.artifacts"
FORMATION = "formation.nine_palace"
NATAL = "artifact.natal"
SPIRIT_FIELD = "economy.spirit_field"
STAT_KEYS = ("might", "guard", "mobility", "sense", "sustain", "breach")
CRAFT_STATS = (
    "combat_power", "max_hp", "max_mp", "opportunity_efficiency",
    "body_training_efficiency", "divine_sense_efficiency",
    "tribulation_reduction", "breakthrough_bonus",
)
CRAFT_STAT_NAMES = {
    "combat_power": "战斗力", "max_hp": "最大HP", "max_mp": "最大MP",
    "opportunity_efficiency": "机缘效率",
    "body_training_efficiency": "炼体效率",
    "divine_sense_efficiency": "神识效率",
    "tribulation_reduction": "渡劫减伤", "breakthrough_bonus": "突破加成",
}
FORMATION_NATURE_NAMES = {
    "metal": "金", "wood": "木", "water": "水", "fire": "火",
    "earth": "土", "yin": "阴", "yang": "阳", "wind": "风",
    "thunder": "雷", "soul": "魂", "space": "空", "star": "星",
    "law": "律", "neutral": "中",
}


@dataclass(frozen=True, slots=True)
class PreviewCrafting:
    actor_id: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ForgeArtifact:
    actor_id: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SaveCraftingBlueprint:
    actor_id: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SellCraftedArtifact:
    actor_id: str
    asset_id: str


@dataclass(frozen=True, slots=True)
class PreviewFormation:
    actor_id: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SaveFormation:
    actor_id: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ActivateFormation:
    actor_id: str
    loadout_id: str


@dataclass(frozen=True, slots=True)
class DeactivateFormation:
    actor_id: str


@dataclass(frozen=True, slots=True)
class DeleteFormation:
    actor_id: str
    loadout_id: str


@dataclass(frozen=True, slots=True)
class DeployGroundFormation:
    actor_id: str
    owner_kind: str = "player"


@dataclass(frozen=True, slots=True)
class WithdrawGroundFormation:
    actor_id: str
    ground_id: str


@dataclass(frozen=True, slots=True)
class RepairGroundFormation:
    actor_id: str
    ground_id: str
    supply_ref: str
    quantity: int = 1


@dataclass(frozen=True, slots=True)
class ManageNatalArtifact:
    actor_id: str
    action: str
    item_id: str = ""
    slot_index: int = -1


def _new_crafting() -> dict[str, Any]:
    return {"next_blueprint_sequence": 1, "blueprints": []}


def _new_formation() -> dict[str, Any]:
    return {
        "next_sequence": 1, "next_ground_sequence": 1,
        "loadouts": [], "active": None, "ground_arrays": [],
    }


def _new_natal() -> dict[str, Any]:
    return {"artifact": None}


def reconcile_artifact_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        if state.entities.get(entity_id, CRAFTING) is None:
            state.entities.put(entity_id, CRAFTING, _new_crafting())
        if state.entities.get(entity_id, FORMATION) is None:
            state.entities.put(entity_id, FORMATION, _new_formation())
        if state.entities.get(entity_id, NATAL) is None:
            state.entities.put(entity_id, NATAL, _new_natal())


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["entity_id"])
    context.state.entities.put(actor_id, CRAFTING, _new_crafting())
    context.state.entities.put(actor_id, FORMATION, _new_formation())
    context.state.entities.put(actor_id, NATAL, _new_natal())


def _ensure_state_available(state: WorldState, actor_id: str) -> None:
    if actor_id != state.controlled_entity_id:
        raise ValueError("只能管理当前角色的法宝与阵法")
    if not bool(state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能进行炼器或布阵")
    if state.relations.find(target_id=actor_id, kind="combat_prisoner"):
        raise ValueError("服刑期间不能进行炼器或布阵")


def _ensure_available(context: SimulationContext, actor_id: str) -> None:
    _ensure_state_available(context.state, actor_id)


def _crafting_rules(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems["crafting"]["settings"])


def _crafting_molds(definitions: GameDefinitions) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): dict(row)
        for row in definitions.systems["crafting"]["molds"]
    }


def _crafting_materials(definitions: GameDefinitions) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): dict(row)
        for row in definitions.systems["crafting"]["materials"]
    }


def _crafting_plants(definitions: GameDefinitions) -> dict[str, dict[str, Any]]:
    return {
        str(row["plant_id"]): dict(row)
        for row in definitions.systems["crafting"]["spirit_plants"]
    }


def _material_candidate(
    state: WorldState, definitions: GameDefinitions, actor_id: str, asset_id: str,
) -> dict[str, Any]:
    asset = require_asset(state, actor_id, asset_id)
    if asset.get("reservation_id"):
        raise ValueError("炼器材料正在被其他系统占用")
    metadata = dict(asset.get("metadata", {}))
    if asset["kind"] == "crafting_material":
        definition = _crafting_materials(definitions).get(str(asset["definition_id"]))
    elif asset["kind"] == "harvested_spirit_plant":
        definition = _crafting_plants(definitions).get(str(asset["definition_id"]))
    else:
        definition = None
    if not definition:
        raise ValueError("所选实例不能作为炼器材料")
    quality = float(metadata.get("quality_multiplier", metadata.get("quality", 1.0)))
    value = int(metadata.get("material_value", metadata.get("value", 1)))
    state_name = str(metadata.get("state", "")).strip()
    if not state_name:
        state_name = (
            "灵韵天成" if quality >= 1.15 else "品相上佳" if quality >= 1.05
            else "保存完好" if quality >= 0.9 else "略有损耗"
        )
    return {
        **asset, "roles": list(definition.get("roles", [])),
        "tags": list(definition.get("tags", [])),
        "allow_duplicate_type": bool(definition.get("allow_duplicate_type", False)),
        "role_effects": copy.deepcopy(definition.get("role_effects", {})),
        "quality": max(0.01, quality), "material_value": max(1, value),
        "acquired_tier": int(metadata.get("tier", definition.get("tier", 1))),
        "state": state_name,
        "source": str(metadata.get("source", "行囊")),
    }


def _crafting_selection(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    mold = _crafting_molds(definitions).get(str(payload.get("mold_id", "")))
    if not mold:
        raise ValueError("请选择一种合法胎模")
    ids = [
        str(payload.get("primary_id", "")), str(payload.get("secondary_a_id", "")),
        str(payload.get("secondary_b_id", "")), str(payload.get("quench_id", "")),
    ]
    if any(not value for value in ids) or len(set(ids)) != 4:
        raise ValueError("主材、两份辅材与淬火材料必须各选择一个不同实例")
    selected = []
    for role, asset_id in zip(("primary", "secondary", "secondary", "quench"), ids):
        material = _material_candidate(state, definitions, actor_id, asset_id)
        if role not in material["roles"]:
            raise ValueError("材料不能用于所选炼器位置")
        selected.append((role, material))
    if (
        selected[1][1]["definition_id"] == selected[2][1]["definition_id"]
        and not all(row[1]["allow_duplicate_type"] for row in selected[1:3])
    ):
        raise ValueError("这种材料不允许同时占用两个辅材位")
    return mold, selected


def _quality_probabilities(level: int, average_quality: float) -> dict[str, float]:
    tiers = ("damaged", "rough", "normal", "excellent", "refined", "epic", "legendary")
    base = (8.0, 20.0, 50.0, 14.0, 6.0, 1.7, 0.3)
    shift = min(12.0, max(-4.0, level * 0.75 + (average_quality - 1.0) * 10.0))
    weights = [weight * math.exp(shift * (index - 2) * 0.16) for index, weight in enumerate(base)]
    total = sum(weights)
    return {tier: weight / total for tier, weight in zip(tiers, weights)}


def _weighted_choice(context: SimulationContext, probabilities: dict[str, float]) -> str:
    roll = context.rng.random()
    elapsed = 0.0
    for key, probability in probabilities.items():
        elapsed += probability
        if roll <= elapsed:
            return key
    return next(reversed(probabilities))


def _crafting_preview(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    cultivation = state.entities.require(actor_id, CULTIVATION)
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    rules = _crafting_rules(definitions)
    if realm_index < int(rules["minimum_realm"]):
        raise ValueError("练气期方可开炉炼器")
    mold, selected = _crafting_selection(state, definitions, actor_id, payload)
    budget = int(rules["budget_by_realm"][min(realm_index, len(rules["budget_by_realm"]) - 1)])
    raw = payload.get("allocations", {}) if isinstance(payload.get("allocations"), dict) else {}
    allocations = {key: max(0, int(raw.get(key, 0))) for key in CRAFT_STATS}
    used = sum(allocations[key] * float(rules["stat_costs"][key]) for key in CRAFT_STATS)
    if used <= 0:
        raise ValueError("至少为法宝分配一项属性")
    if used > budget + 1e-9:
        raise ValueError(f"属性预算超出上限：已用 {used:.1f} / {budget}")
    primary_tier = int(selected[0][1]["acquired_tier"])
    scaling_index = max(0, min(realm_index, primary_tier, len(definitions.realms) - 1))
    realm = definitions.realms[scaling_index]
    layer = int(cultivation["layer"]) if scaling_index == realm_index else realm.layers
    power = float(realm.base_power) * (1 + 0.12 * (layer - 1))
    bases = {
        "combat_power": power, "max_hp": 100 + math.sqrt(power) * 18,
        "max_mp": 80 + math.sqrt(power) * 15,
        "opportunity_efficiency": 1.0, "body_training_efficiency": 1.0,
        "divine_sense_efficiency": 1.0, "tribulation_reduction": 1.0,
        "breakthrough_bonus": 1.0,
    }
    designed = {
        key: bases[key] * float(rules["stat_caps"][key])
        * allocations[key] * float(rules["stat_costs"][key]) / max(1, budget)
        for key in CRAFT_STATS
    }
    special = {key: 0.0 for key in CRAFT_STATS}
    effects = [copy.deepcopy(mold["rule"].get("combat_effect", {})) | {"source": mold["rule"]["name"]}]
    material_effects = []
    for role, material in selected:
        effect = copy.deepcopy(material["role_effects"].get(role, {}))
        for key, multiplier in dict(effect.get("design_multipliers", {})).items():
            if key in designed:
                designed[key] *= max(0.0, float(multiplier))
        potency = min(1.25, max(0.65, math.sqrt(float(material["quality"]))))
        for key, value in dict(effect.get("special_stats", {})).items():
            if key in special:
                special[key] += float(value) * potency
        if effect.get("combat_effect"):
            effects.append(copy.deepcopy(effect["combat_effect"]) | {"source": f"{material['name']}·{role}"})
        material_effects.append({
            "role": role, "material_id": material["definition_id"],
            "instance_id": material["id"], "name": material["name"],
            "description": str(effect.get("description", "")),
        })
    field = state.entities.require(actor_id, SPIRIT_FIELD)
    experience = float(dict(field.get("art_experience", {})).get("refining", 0))
    level = int(math.sqrt(experience / float(rules.get("refining_experience_base", 100))))
    probabilities = _quality_probabilities(
        level, sum(float(row[1]["quality"]) for row in selected) / 4
    )
    theoretical = {}
    for quality, multiplier in dict(rules["quality_multipliers"]).items():
        stats = {}
        for key in CRAFT_STATS:
            value = designed[key] * float(multiplier) + special[key]
            if key == "breakthrough_bonus":
                value = min(float(rules["stat_caps"][key]), value)
            elif key == "tribulation_reduction":
                value = min(0.50, value)
            stats[key] = round(value, 4)
        theoretical[quality] = stats
    anchor = max(1, round(sum(int(row[1]["material_value"]) for row in selected) * float(rules["anchor_multiplier"])))
    return {
        "mold": mold, "selected_materials": [dict(row) for _, row in selected],
        "material_effects": material_effects, "allocations": allocations,
        "budget": budget, "budget_used": round(used, 2),
        "designed_stats": {key: round(value, 4) for key, value in designed.items()},
        "scaling_realm_index": scaling_index, "scaling_realm_name": realm.name,
        "special_stats": special, "quality_probabilities": probabilities,
        "quality_names": dict(rules["quality_names"]),
        "quality_multipliers": dict(rules["quality_multipliers"]),
        "theoretical_stats": theoretical, "combat_effects": effects,
        "anchor_value": anchor, "refining_level": level,
    }


def preview_crafting_view(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a preview without advancing the save revision.

    The frozen client previews on input changes.  Treating that read as a
    persisted command makes two nearby previews race each other and can reject
    a later real save with a stale revision.
    """
    _ensure_state_available(state, actor_id)
    return _crafting_preview(state, definitions, actor_id, payload)


def _preview_crafting_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PreviewCrafting):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        preview = _crafting_preview(context.state, definitions, command.actor_id, command.payload)
        component = context.state.entities.require(command.actor_id, CRAFTING)
        component["last_preview"] = preview
        context.state.entities.put(command.actor_id, CRAFTING, component)
    return handler


def _forge_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ForgeArtifact):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        preview = _crafting_preview(context.state, definitions, command.actor_id, command.payload)
        quality = _weighted_choice(context, preview["quality_probabilities"])
        for material in preview["selected_materials"]:
            consume_asset(context, command.actor_id, str(material["id"]))
        name = str(command.payload.get("name", "")).strip()[:20] or str(preview["mold"]["default_name"])
        metadata = {
            "mold_id": preview["mold"]["id"], "mold_name": preview["mold"]["name"],
            "quality": quality, "quality_name": preview["quality_names"][quality],
            "quality_multiplier": preview["quality_multipliers"][quality],
            "materials": [{key: row.get(key) for key in (
                "id", "definition_id", "name", "quality", "material_value"
            )} for row in preview["selected_materials"]],
            "material_effects": preview["material_effects"],
            "allocations": preview["allocations"],
            "actual_stats": preview["theoretical_stats"][quality],
            "combat_effects": preview["combat_effects"],
            "anchor_value": preview["anchor_value"], "tier": preview["scaling_realm_index"],
            "value": preview["anchor_value"], "is_natal": False,
        }
        asset_id = create_asset(
            context, command.actor_id, kind="crafted_artifact",
            definition_id=str(preview["mold"]["id"]), name=name, metadata=metadata,
        )
        field = context.state.entities.require(command.actor_id, SPIRIT_FIELD)
        experience = dict(field.get("art_experience", {}))
        experience["refining"] = float(experience.get("refining", 0)) + float(
            _crafting_rules(definitions).get("refining_experience_per_craft", 30)
        )
        field["art_experience"] = experience
        context.state.entities.put(command.actor_id, SPIRIT_FIELD, field)
        context.emit(
            "crafting.artifact.forged", source="crafting",
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "asset_id": asset_id, "quality": quality},
        )
    return handler


def _save_blueprint_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SaveCraftingBlueprint):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        preview = _crafting_preview(context.state, definitions, command.actor_id, command.payload)
        component = context.state.entities.require(command.actor_id, CRAFTING)
        sequence = int(component.get("next_blueprint_sequence", 1))
        blueprints = list(component.get("blueprints", []))
        blueprints.append({
            "id": f"blueprint:{command.actor_id}:{sequence}",
            "name": str(command.payload.get("blueprint_name", "")).strip()[:20]
            or f"{preview['mold']['default_name']}图谱",
            "mold_id": preview["mold"]["id"],
            "material_types": [row["definition_id"] for row in preview["selected_materials"]],
            "allocations": preview["allocations"], "created_year": context.state.clock.year,
        })
        component.update(next_blueprint_sequence=sequence + 1, blueprints=blueprints)
        context.state.entities.put(command.actor_id, CRAFTING, component)
    return handler


def _sell_artifact_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SellCraftedArtifact):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        asset = require_asset(context.state, command.actor_id, command.asset_id)
        if asset["kind"] != "crafted_artifact":
            raise ValueError("这不是炼器法宝")
        if dict(asset.get("metadata", {})).get("is_natal"):
            raise ValueError("已设为本命的法宝不能出售")
        price = max(1, round(
            int(dict(asset.get("metadata", {})).get("anchor_value", 1))
            * float(_crafting_rules(definitions)["ordinary_sell_ratio"])
        ))
        consume_asset(context, command.actor_id, command.asset_id)
        change_inventory_item(context, definitions, command.actor_id, CURRENCY_ID, price, "crafted-artifact-sale")
    return handler


def _formation_config(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems["formations"])


def _formation_defs(definitions: GameDefinitions) -> dict[str, dict[str, Any]]:
    config = _formation_config(definitions)
    result = {
        str(row["id"]): {**dict(row), "source_kind": "formation_material"}
        for row in config["materials"]
    }
    for group, source_kind in (
        ("crafting_materials", "crafting_material"),
        ("inventory_items", "inventory"),
        ("spirit_plants", "harvested_spirit_plant"),
    ):
        for row in config.get(group, []):
            result[str(row["id"])] = {
                **dict(row), "source_kind": source_kind,
            }
    return result


def _formation_definition_for_asset(
    definitions: GameDefinitions, asset: dict[str, Any]
) -> dict[str, Any] | None:
    all_definitions = _formation_defs(definitions)
    kind = str(asset.get("kind", ""))
    content_id = str(asset.get("definition_id", ""))
    if kind == "formation_material":
        return all_definitions.get(content_id)
    source_key = {
        "crafting_material": "crafting_material_id",
        "harvested_spirit_plant": "plant_id",
    }.get(kind)
    if source_key:
        return next((
            row for row in all_definitions.values()
            if row.get("source_kind") == kind
            and str(row.get(source_key, "")) == content_id
        ), None)
    return None


def _formation_candidate_from_definition(
    definition: dict[str, Any], *, candidate_id: str,
    source_kind: str, source: str, acquired_tier: int,
    asset_id: str | None = None, item_id: str | None = None,
) -> dict[str, Any]:
    nature = str(definition.get("nature", "neutral"))
    return {
        "id": candidate_id, "asset_id": asset_id,
        "item_id": item_id,
        "definition_id": str(definition["id"]),
        "name": str(definition.get("name", "阵材")),
        "nature": nature,
        "nature_name": FORMATION_NATURE_NAMES.get(nature, nature),
        "formation_value": float(definition.get("formation_value", 0)),
        "relation_overrides": dict(definition.get("relation_overrides", {})),
        "field_hook": definition.get("field_hook"),
        "source_kind": source_kind, "source": source,
        "acquired_tier": acquired_tier,
    }


def _formation_candidate(
    state: WorldState, definitions: GameDefinitions, actor_id: str, asset_id: str,
    *, allow_reserved: bool = False,
) -> dict[str, Any]:
    asset = require_asset(state, actor_id, asset_id)
    if asset.get("reservation_id") and not allow_reserved:
        raise ValueError("阵材已经被其他阵法占用")
    definition = _formation_definition_for_asset(definitions, asset)
    if not definition:
        raise ValueError("阵材定义已经失效")
    metadata = dict(asset.get("metadata", {}))
    return _formation_candidate_from_definition(
        definition, candidate_id=asset_id,
        asset_id=asset_id, item_id=None,
        source_kind=str(asset.get("kind")),
        source=str(metadata.get("source", "行囊")),
        acquired_tier=int(metadata.get("tier", definition.get("tier", 1))),
    )


def _formation_candidates(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> list[dict[str, Any]]:
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    instances = dict(ledger.get("instances", {}))
    reservations = dict(ledger.get("reservations", {}))
    candidates: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for asset_id, asset in sorted(instances.items()):
        if _formation_definition_for_asset(definitions, asset) is None:
            continue
        row = _formation_candidate(
            state, definitions, actor_id, asset_id, allow_reserved=True
        )
        reservation = reservations.get(str(asset.get("reservation_id") or ""), {})
        purpose = str(reservation.get("purpose", ""))
        row.update(
            occupied=bool(asset.get("reservation_id")),
            locked=bool(asset.get("reservation_id"))
            and not purpose.startswith("formation:active:"),
            occupied_scope=(
                "ground" if purpose.startswith("formation:ground:")
                else "active" if purpose.startswith("formation:active:") else None
            ),
        )
        candidates.append(row)
        by_id[str(row["id"])] = row

    inventory_definitions = [
        row for row in _formation_defs(definitions).values()
        if row.get("source_kind") == "inventory"
    ]
    for definition in inventory_definitions:
        item_id = str(definition.get("item_id", ""))
        quantity = inventory_quantity(
            state, actor_id, item_id, spendable=True
        )
        for index in range(quantity):
            candidate_id = f"inventory:{item_id}:{index}"
            row = _formation_candidate_from_definition(
                definition, candidate_id=candidate_id,
                source_kind="inventory", source="行囊",
                acquired_tier=int(definition.get("tier", 1)),
                item_id=item_id,
            )
            row.update(occupied=False, locked=False, occupied_scope=None)
            candidates.append(row)
            by_id[candidate_id] = row

    component = state.entities.require(actor_id, FORMATION)
    active = component.get("active")
    if isinstance(active, dict):
        for slot, binding in enumerate(active.get("bindings", [])):
            if not binding:
                continue
            row = dict(binding)
            candidate_id = str(
                row.get("asset_id") or row.get("reservation_id") or row.get("id")
            )
            row.update(
                id=candidate_id, slot=slot, occupied=True,
                locked=False, occupied_scope="active",
            )
            if candidate_id in by_id:
                by_id[candidate_id].update(row)
            else:
                candidates.append(row)
                by_id[candidate_id] = row
    for ground in component.get("ground_arrays", []):
        for binding in ground.get("bindings", []):
            if not binding:
                continue
            row = dict(binding)
            candidate_id = str(
                row.get("asset_id") or row.get("reservation_id") or row.get("id")
            )
            row.update(
                id=candidate_id, occupied=True, locked=True,
                occupied_scope="ground", ground_array_id=ground.get("id"),
                source=f"镇于{ground.get('owner_name', '阵域')}",
            )
            if candidate_id in by_id:
                by_id[candidate_id].update(row)
            else:
                candidates.append(row)
                by_id[candidate_id] = row
    return sorted(
        candidates,
        key=lambda row: (
            bool(row.get("occupied")), str(row.get("name")), str(row.get("id"))
        ),
    )


def _formation_nodes(
    state: WorldState, definitions: GameDefinitions, actor_id: str, slots: list[Any],
) -> list[dict[str, Any] | None]:
    values = list(slots[:9]) + [None] * max(0, 9 - len(slots))
    candidates = {
        str(row["id"]): row
        for row in _formation_candidates(state, definitions, actor_id)
    }
    used: set[str] = set()
    nodes = []
    for raw in values[:9]:
        if not raw:
            nodes.append(None)
            continue
        asset_id = str(raw)
        if asset_id in used:
            raise ValueError("同一阵材实例不能重复放入九宫")
        used.add(asset_id)
        candidate = candidates.get(asset_id)
        if candidate is None or candidate.get("locked"):
            raise ValueError("九宫中的阵材实例不存在，或正在被镇地阵占用")
        nodes.append(dict(candidate))
    return nodes


def _formation_level(state: WorldState, definitions: GameDefinitions, actor_id: str) -> int:
    field = state.entities.require(actor_id, SPIRIT_FIELD)
    experience = float(dict(field.get("art_experience", {})).get("formation", 0))
    base = float(_formation_config(definitions)["settings"].get("experience_base", 100))
    return int(math.sqrt(max(0.0, experience) / base))


def _formation_alpha(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> float:
    settings = dict(_formation_config(definitions).get("settings", {}))
    low = float(settings.get("alpha_min", 0.5))
    high = float(settings.get("alpha_max", 0.9))
    scale = max(1.0, float(settings.get("alpha_level_scale", 12)))
    return low + (high - low) * (
        1 - math.exp(-_formation_level(state, definitions, actor_id) / scale)
    )


def _formation_profile(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    nodes: list[dict[str, Any] | None], name: str,
) -> dict[str, Any]:
    occupied = [(index, row) for index, row in enumerate(nodes) if row]
    empty = {
        "active": False, "name": name, "occupied_count": len(occupied),
        "metrics": {key: 0.0 for key in ("growth", "kill", "focus", "balance", "cycle", "change")},
        "static_player_multipliers": {key: 1.0 for key in STAT_KEYS},
        "static_enemy_multipliers": {key: 1.0 for key in STAT_KEYS},
        "artificial_conditions": [], "effects": [], "stability": "未成阵",
    }
    if len(occupied) < 2:
        return empty
    config = _formation_config(definitions)
    relations = dict(config.get("relations", {}))
    alpha = _formation_alpha(state, definitions, actor_id)
    positive = negative = 0.0
    incoming = {index: 0.0 for index, _ in occupied}
    edges = 0
    for left, source in occupied:
        lr, lc = divmod(left, 3)
        for right, target in occupied:
            if left >= right:
                continue
            rr, rc = divmod(right, 3)
            distance = abs(lr - rr) + abs(lc - rc)
            if distance > 2:
                continue
            relation = float(dict(relations.get(source["nature"], {})).get(target["nature"], 0))
            relation = float(source["relation_overrides"].get(target["nature"], relation))
            strength = relation * math.sqrt(source["formation_value"] * target["formation_value"]) * alpha ** max(0, distance - 1)
            positive += max(0.0, strength)
            negative += max(0.0, -strength)
            incoming[left] += abs(strength)
            incoming[right] += abs(strength)
            edges += 1
    total = positive + negative
    if total <= 1e-9 or edges == 0:
        return empty
    count = len(occupied)
    activity = min(1.0, math.tanh(total / max(1.0, 50.0 * count)))
    core_index = max(incoming, key=lambda index: (incoming[index], -index))
    shares = [value / sum(incoming.values()) for value in incoming.values() if value > 0]
    balance = 0.0 if len(shares) < 2 else -sum(value * math.log(value) for value in shares) / math.log(count)
    focus = max(incoming.values()) / max(1e-9, sum(incoming.values()))
    growth = activity * (positive / total) ** 0.65
    kill = activity * (negative / total) ** 0.65
    cycle = activity * min(1.0, edges / max(1, count))
    change = activity * min(1.0, (positive + negative) / max(1.0, count * 10))
    ratios = {"growth": growth, "kill": kill, "focus": focus * activity, "balance": balance * activity, "cycle": cycle, "change": change}
    bonuses = {key: 0.0 for key in STAT_KEYS}
    bonuses["sustain"] += 0.075 * growth
    bonuses["might"] += 0.065 * kill
    bonuses["breach"] += 0.052 * kill
    bonuses["guard"] += 0.070 * ratios["balance"]
    core = nodes[core_index] or {}
    for stat in config.get("nature_channels", {}).get(str(core.get("nature", "neutral")), []):
        if stat in bonuses:
            bonuses[stat] += 0.055 * ratios["focus"]
    cap = float(config["settings"].get("stat_bonus_cap", 0.14))
    player = {key: 1 + min(cap, max(0.0, value)) for key, value in bonuses.items()}
    enemy = {key: 1.0 for key in STAT_KEYS}
    if core.get("nature") == "space":
        enemy["mobility"] -= min(0.06, 0.03 * ratios["focus"])
    if core.get("nature") == "soul":
        enemy["sense"] -= min(0.06, 0.025 * ratios["focus"])
    conditions = ["大阵"]
    hooks = {row.get("field_hook") for _, row in occupied if row.get("field_hook")}
    if activity >= 0.15 and (ratios["focus"] >= 0.35 or cycle >= 0.35):
        if "forbidden_air" in hooks:
            conditions.append("禁空")
        if "forbidden_sense" in hooks:
            conditions.append("禁神识")
    effects = [f"{key}+{value - 1:.1%}" for key, value in player.items() if value > 1.00005]
    return {
        "active": True, "name": name, "occupied_count": count, "alpha": round(alpha, 6),
        "metrics": {key: round(value * 100, 2) for key, value in ratios.items()},
        "static_player_multipliers": player, "static_enemy_multipliers": enemy,
        "artificial_conditions": conditions, "effects": effects,
        "core_node": {
            "index": core_index, "position": core_index + 1,
            "name": core.get("name"), "nature": core.get("nature"),
            "nature_name": FORMATION_NATURE_NAMES.get(
                str(core.get("nature", "neutral")),
                str(core.get("nature", "neutral")),
            ),
        },
        "stability": "高" if ratios["balance"] >= 0.45 else "中" if ratios["balance"] >= 0.05 else "低",
    }


def preview_formation_view(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    _ensure_state_available(state, actor_id)
    nodes = _formation_nodes(
        state, definitions, actor_id, list(payload.get("slots", []))
    )
    name = str(payload.get("name", "无名阵")).strip()[:20] or "无名阵"
    return _formation_profile(state, definitions, actor_id, nodes, name)


def _release_bindings(context: SimulationContext, actor_id: str, bindings: list[dict[str, Any]]) -> None:
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    existing = set(dict(ledger.get("reservations", {})))
    for binding in bindings:
        reservation_id = str(binding.get("reservation_id", ""))
        if reservation_id in existing:
            release_reservation(context, actor_id, reservation_id)


def _bind_definitions(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str,
    definition_ids: list[str | None], purpose: str,
) -> list[dict[str, Any] | None]:
    bindings: list[dict[str, Any] | None] = []
    for definition_id in definition_ids:
        if not definition_id:
            bindings.append(None)
            continue
        candidate = next((
            row for row in _formation_candidates(
                context.state, definitions, actor_id
            )
            if row.get("definition_id") == definition_id
            and not row.get("occupied")
        ), None)
        if candidate is None:
            raise ValueError(f"缺少可用阵材实例：{definition_id}")
        asset_id = candidate.get("asset_id")
        item_id = candidate.get("item_id")
        if asset_id:
            reservation_id = reserve_asset(
                context, actor_id, purpose=purpose, asset_id=str(asset_id)
            )
            binding_id = str(asset_id)
        elif item_id:
            reservation_id = reserve_asset(
                context, actor_id, purpose=purpose,
                item_id=str(item_id), quantity=1,
            )
            binding_id = reservation_id
        else:
            raise ValueError(f"阵材来源已经失效：{definition_id}")
        bindings.append({
            **dict(candidate), "id": binding_id,
            "reservation_id": reservation_id,
        })
    return bindings


def _preview_formation_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PreviewFormation):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        nodes = _formation_nodes(context.state, definitions, command.actor_id, list(command.payload.get("slots", [])))
        profile = _formation_profile(context.state, definitions, command.actor_id, nodes, str(command.payload.get("name", "无名阵"))[:20] or "无名阵")
        component = context.state.entities.require(command.actor_id, FORMATION)
        component["last_preview"] = profile
        context.state.entities.put(command.actor_id, FORMATION, component)
    return handler


def _save_formation_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SaveFormation):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        nodes = _formation_nodes(context.state, definitions, command.actor_id, list(command.payload.get("slots", [])))
        name = str(command.payload.get("name", "无名阵")).strip()[:20] or "无名阵"
        profile = _formation_profile(context.state, definitions, command.actor_id, nodes, name)
        if not profile["active"]:
            raise ValueError("至少需要两份能够建立灵流关系的阵材才能成阵")
        component = context.state.entities.require(command.actor_id, FORMATION)
        loadouts = [dict(row) for row in component.get("loadouts", [])]
        loadout_id = str(command.payload.get("loadout_id", ""))
        index = next((i for i, row in enumerate(loadouts) if row["id"] == loadout_id), None)
        definition_slots = [row["definition_id"] if row else None for row in nodes]
        if index is None:
            sequence = int(component.get("next_sequence", 1))
            loadout = {"id": f"formation:{command.actor_id}:{sequence}", "name": name, "slots": definition_slots, "created_year": context.state.clock.year}
            component["next_sequence"] = sequence + 1
            loadouts.append(loadout)
        else:
            loadout = {**loadouts[index], "name": name, "slots": definition_slots}
            loadouts[index] = loadout
        component["loadouts"] = loadouts
        context.state.entities.put(command.actor_id, FORMATION, component)
        if bool(command.payload.get("activate")):
            _activate(context, definitions, command.actor_id, str(loadout["id"]))
    return handler


def _activate(
    context: SimulationContext, definitions: GameDefinitions, actor_id: str, loadout_id: str,
) -> None:
    component = context.state.entities.require(actor_id, FORMATION)
    loadout = next((dict(row) for row in component.get("loadouts", []) if row["id"] == loadout_id), None)
    if not loadout:
        raise ValueError("未找到这份阵法预设")
    current = component.get("active")
    if isinstance(current, dict):
        _release_bindings(context, actor_id, [row for row in current.get("bindings", []) if row])
    bindings = _bind_definitions(context, definitions, actor_id, list(loadout["slots"]), f"formation:active:{loadout_id}")
    profile = _formation_profile(context.state, definitions, actor_id, bindings, str(loadout["name"]))
    component = context.state.entities.require(actor_id, FORMATION)
    component["active"] = {"loadout_id": loadout_id, "name": loadout["name"], "bindings": bindings, "profile": profile}
    context.state.entities.put(actor_id, FORMATION, component)


def _activate_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ActivateFormation):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        _activate(context, definitions, command.actor_id, command.loadout_id)
    return handler


def _deactivate(context: SimulationContext, actor_id: str) -> None:
    component = context.state.entities.require(actor_id, FORMATION)
    active = component.get("active")
    if isinstance(active, dict):
        _release_bindings(context, actor_id, [row for row in active.get("bindings", []) if row])
    component = context.state.entities.require(actor_id, FORMATION)
    component["active"] = None
    context.state.entities.put(actor_id, FORMATION, component)


def _deactivate_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, DeactivateFormation):
        raise TypeError("命令类型错误")
    _ensure_available(context, command.actor_id)
    _deactivate(context, command.actor_id)


def _delete_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, DeleteFormation):
        raise TypeError("命令类型错误")
    _ensure_available(context, command.actor_id)
    component = context.state.entities.require(command.actor_id, FORMATION)
    loadouts = list(component.get("loadouts", []))
    if not any(row["id"] == command.loadout_id for row in loadouts):
        raise ValueError("未找到这份阵法预设")
    if isinstance(component.get("active"), dict) and component["active"].get("loadout_id") == command.loadout_id:
        _deactivate(context, command.actor_id)
        component = context.state.entities.require(command.actor_id, FORMATION)
    component["loadouts"] = [row for row in loadouts if row["id"] != command.loadout_id]
    context.state.entities.put(command.actor_id, FORMATION, component)


def _sect_formation_authority(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> tuple[bool, str | None, str | None]:
    # Keep the formation domain's authorization identical to the faction
    # command path.  The import is local to avoid coupling domain startup.
    from .factions import (
        FACTION_GOVERNANCE,
        FACTION_PROFILE,
        _active_membership,
        _has_faction_voice,
    )

    membership = _active_membership(state, actor_id)
    if membership is None:
        return False, None, None
    profile = state.entities.get(membership.target_id, FACTION_PROFILE)
    governance = state.entities.get(membership.target_id, FACTION_GOVERNANCE)
    location = state.entities.require(actor_id, LOCATION)
    if (
        not isinstance(profile, dict)
        or not isinstance(governance, dict)
        or not bool(profile.get("active"))
        or profile.get("world_id") != location.get("world_id")
    ):
        return False, None, None
    permitted = _has_faction_voice(
        state, definitions, actor_id, membership.target_id
    )
    return permitted, membership.target_id, str(profile.get("name", "宗门"))


def _deploy_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, DeployGroundFormation):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        component = context.state.entities.require(command.actor_id, FORMATION)
        active = component.get("active")
        if not isinstance(active, dict):
            raise ValueError("请先启用一座有效的随身九宫阵")
        if command.owner_kind not in {"player", "sect"}:
            raise ValueError("未知镇地阵归属")
        location = context.state.entities.require(command.actor_id, LOCATION)
        if command.owner_kind == "sect":
            permitted, owner_id, owner_name = _sect_formation_authority(
                context.state, definitions, command.actor_id
            )
            if not permitted or not owner_id:
                raise ValueError("只有拥有宗门话语权者才能更换护山阵")
        else:
            identity = context.state.entities.require(command.actor_id, IDENTITY)
            owner_id = command.actor_id
            owner_name = str(identity.get("name", "自身"))
        if any(
            row.get("world_id") == location["world_id"]
            and row.get("location_id") == location["location_id"]
            and row.get("owner_kind") == command.owner_kind
            and row.get("owner_id", owner_id) == owner_id
            for row in component.get("ground_arrays", [])
        ):
            raise ValueError("此地已经存在同归属的镇地阵")
        sequence = int(component.get("next_ground_sequence", 1))
        ground = {
            "id": f"ground-formation:{command.actor_id}:{sequence}",
            "name": active["name"], "loadout_id": active["loadout_id"],
            "owner_kind": command.owner_kind,
            "owner_id": owner_id, "owner_name": owner_name,
            "creator_id": command.actor_id,
            "creator_name": str(
                context.state.entities.require(command.actor_id, IDENTITY).get(
                    "name", "无名修士"
                )
            ),
            "world_id": location["world_id"],
            "location_id": location["location_id"], "bindings": active["bindings"],
            "profile": active["profile"], "durability": 100.0,
            "created_year": context.state.clock.year,
            "last_repaired_year": context.state.clock.year, "battles": 0,
        }
        component.update(next_ground_sequence=sequence + 1, active=None)
        component["ground_arrays"] = [*component.get("ground_arrays", []), ground]
        context.state.entities.put(command.actor_id, FORMATION, component)
    return handler


def _require_ground(
    context: SimulationContext, actor_id: str, ground_id: str,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    component = context.state.entities.require(actor_id, FORMATION)
    arrays = [dict(row) for row in component.get("ground_arrays", [])]
    index = next((i for i, row in enumerate(arrays) if row["id"] == ground_id), None)
    if index is None:
        raise ValueError("未找到这座镇地阵")
    location = context.state.entities.require(actor_id, LOCATION)
    if arrays[index]["world_id"] != location["world_id"] or arrays[index]["location_id"] != location["location_id"]:
        raise ValueError("必须亲临镇地阵所在地域才能维护或撤除")
    return component, arrays[index], index


def _withdraw_handler(context: SimulationContext, command: object) -> None:
    if not isinstance(command, WithdrawGroundFormation):
        raise TypeError("命令类型错误")
    _ensure_available(context, command.actor_id)
    component, ground, _ = _require_ground(context, command.actor_id, command.ground_id)
    _release_bindings(context, command.actor_id, [row for row in ground.get("bindings", []) if row])
    component = context.state.entities.require(command.actor_id, FORMATION)
    component["ground_arrays"] = [row for row in component.get("ground_arrays", []) if row["id"] != command.ground_id]
    context.state.entities.put(command.actor_id, FORMATION, component)


def _repair_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RepairGroundFormation):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        component, ground, index = _require_ground(context, command.actor_id, command.ground_id)
        if float(ground.get("durability", 0)) >= 99.999:
            raise ValueError("镇地阵完整度已满，无需修复")
        supplies = {
            str(row["id"]): dict(row)
            for row in _formation_config(definitions)["maintenance_resources"]
        }
        quantity = max(1, min(10, int(command.quantity)))
        ledger = context.state.entities.require(command.actor_id, ASSET_LEDGER)
        instances = dict(ledger.get("instances", {}))
        candidates = []
        if command.supply_ref in instances:
            candidates = [command.supply_ref]
        else:
            candidates = [
                asset_id for asset_id, asset in sorted(instances.items())
                if asset.get("kind") == "formation_supply"
                and asset.get("definition_id") == command.supply_ref
                and not asset.get("reservation_id")
            ][:quantity]
        if len(candidates) < quantity:
            raise ValueError("持有的修阵资源不足")
        definition_id = str(instances[candidates[0]]["definition_id"])
        definition = supplies.get(definition_id)
        if not definition or definition.get("world") != ground["world_id"]:
            raise ValueError("这份修阵资源无法与当前界面的地脉相合")
        for asset_id in candidates[:quantity]:
            consume_asset(context, command.actor_id, asset_id)
        ground["durability"] = round(min(100.0, float(ground["durability"]) + quantity * float(definition["repair_value"])), 4)
        ground["last_repaired_year"] = context.state.clock.year
        arrays = [dict(row) for row in component.get("ground_arrays", [])]
        arrays[index] = ground
        component["ground_arrays"] = arrays
        context.state.entities.put(command.actor_id, FORMATION, component)
    return handler


def _natal_config(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems["natal_artifact"])


def _natal_slots(definitions: GameDefinitions, level: int) -> int:
    unlocks = dict(_natal_config(definitions)["slot_unlocks"])
    return max(int(amount) for required, amount in unlocks.items() if int(required) <= level)


def _natal_materials(definitions: GameDefinitions) -> dict[str, dict[str, Any]]:
    return {str(row["item_id"]): dict(row) for row in _natal_config(definitions)["materials"]}


def _set_crafted_natal(
    context: SimulationContext, actor_id: str, asset_id: str, value: bool,
) -> None:
    ledger = context.state.entities.require(actor_id, ASSET_LEDGER)
    instances = dict(ledger.get("instances", {}))
    asset = dict(instances[asset_id])
    metadata = dict(asset.get("metadata", {}))
    metadata["is_natal"] = value
    asset["metadata"] = metadata
    instances[asset_id] = asset
    ledger["instances"] = instances
    context.state.entities.put(actor_id, ASSET_LEDGER, ledger)


def _manage_natal_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ManageNatalArtifact):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        config = _natal_config(definitions)
        if realm_index < int(config["minimum_realm"]):
            raise ValueError("结丹期方可修炼本命法宝")
        component = context.state.entities.require(command.actor_id, NATAL)
        artifact = component.get("artifact")
        if command.action == "bind":
            if isinstance(artifact, dict):
                raise ValueError("已有本命法宝，不能重新认主")
            ledger = context.state.entities.require(command.actor_id, ASSET_LEDGER)
            asset = dict(ledger.get("instances", {})).get(command.item_id)
            if isinstance(asset, dict) and asset.get("kind") == "crafted_artifact":
                if asset.get("reservation_id"):
                    raise ValueError("法宝正在托管中")
                _set_crafted_natal(context, command.actor_id, command.item_id, True)
                artifact = {
                    "asset_id": command.item_id, "item_id": command.item_id,
                    "name": asset["name"], "level": 1, "experience": 0,
                    "bound_year": context.state.clock.year, "slots": [None] * 7,
                }
            else:
                item = definitions.items.get(command.item_id)
                eligible = set(map(str, config.get("eligible_item_ids", [])))
                if item is None or command.item_id not in eligible:
                    raise ValueError("必须选择背包中的法宝或装备认主")
                change_inventory_item(context, definitions, command.actor_id, command.item_id, -1, "natal-bind")
                artifact = {
                    "asset_id": None, "item_id": command.item_id, "name": item.name,
                    "level": 1, "experience": 0, "bound_year": context.state.clock.year,
                    "slots": [None] * 7,
                }
        elif command.action == "unbind":
            if not isinstance(artifact, dict) or artifact.get("asset_id") != command.item_id:
                raise ValueError("这件法宝并非当前本命法宝")
            for material_id in artifact.get("slots", []):
                if material_id:
                    change_inventory_item(context, definitions, command.actor_id, str(material_id), 1, "natal-unsocket-all")
            _set_crafted_natal(context, command.actor_id, command.item_id, False)
            artifact = None
        elif command.action == "refine":
            if not isinstance(artifact, dict):
                raise ValueError("尚未选择本命法宝")
            level = int(artifact["level"])
            if level >= int(config["max_level"]):
                raise ValueError("本命法宝已祭炼至当前上限")
            cost = int(config["manual_refine_stone_base"]) * level
            change_inventory_item(context, definitions, command.actor_id, CURRENCY_ID, -cost, "natal-refine")
            artifact["experience"] = int(artifact.get("experience", 0)) + int(config["manual_refine_xp"])
            while int(artifact["level"]) < int(config["max_level"]):
                required = int(config["experience_base"]) * int(artifact["level"])
                if int(artifact["experience"]) < required:
                    break
                artifact["experience"] -= required
                artifact["level"] += 1
        elif command.action in {"socket", "unsocket"}:
            if not isinstance(artifact, dict):
                raise ValueError("尚未选择本命法宝")
            unlocked = _natal_slots(definitions, int(artifact["level"]))
            if command.slot_index < 0 or command.slot_index >= unlocked:
                raise ValueError("该镶嵌槽尚未解锁")
            slots = list(artifact.get("slots", [None] * 7))
            old = slots[command.slot_index]
            if command.action == "unsocket":
                if not old:
                    raise ValueError("该槽位为空")
                change_inventory_item(context, definitions, command.actor_id, str(old), 1, "natal-unsocket")
                slots[command.slot_index] = None
            else:
                definition = _natal_materials(definitions).get(command.item_id)
                if not definition or realm_index < int(definition["minimum_realm"]):
                    raise ValueError("当前境界无法驾驭这种镶嵌材料")
                if command.item_id in slots:
                    raise ValueError("同种材料只能镶嵌一枚")
                change_inventory_item(context, definitions, command.actor_id, command.item_id, -1, "natal-socket")
                if old:
                    change_inventory_item(context, definitions, command.actor_id, str(old), 1, "natal-replace")
                slots[command.slot_index] = command.item_id
            artifact["slots"] = slots
        else:
            raise ValueError("未知本命法宝操作")
        component["artifact"] = artifact
        context.state.entities.put(command.actor_id, NATAL, component)
    return handler


def _on_action_completed(definitions: GameDefinitions):
    def handler(context: SimulationContext, event: EventEnvelope) -> None:
        if event.payload.get("action") != "cultivate":
            return
        actor_id = str(event.payload["actor_id"])
        component = context.state.entities.require(actor_id, NATAL)
        artifact = component.get("artifact")
        if not isinstance(artifact, dict):
            return
        config = _natal_config(definitions)
        if int(artifact["level"]) >= int(config["max_level"]):
            return
        artifact["experience"] = int(artifact.get("experience", 0)) + max(1, int(event.payload.get("years", 1)))
        while int(artifact["level"]) < int(config["max_level"]):
            required = int(config["experience_base"]) * int(artifact["level"])
            if int(artifact["experience"]) < required:
                break
            artifact["experience"] -= required
            artifact["level"] += 1
        component["artifact"] = artifact
        context.state.entities.put(actor_id, NATAL, component)
    return handler


def _on_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    component = context.state.entities.require(actor_id, FORMATION)
    active = component.get("active")
    if isinstance(active, dict):
        component["active"] = None
    # The asset domain releases every escrow first. Ground arrays are persistent
    # world objects, so immediately restore their exact-instance reservations.
    arrays = []
    for raw_ground in component.get("ground_arrays", []):
        ground = dict(raw_ground)
        bindings = []
        for raw_binding in ground.get("bindings", []):
            if not raw_binding:
                bindings.append(None)
                continue
            binding = dict(raw_binding)
            asset_id = binding.get("asset_id")
            item_id = binding.get("item_id")
            if asset_id:
                binding["reservation_id"] = reserve_asset(
                    context, actor_id,
                    purpose=f"formation:ground:{ground['id']}",
                    asset_id=str(asset_id),
                )
                binding["id"] = str(asset_id)
            elif item_id:
                binding["reservation_id"] = reserve_asset(
                    context, actor_id,
                    purpose=f"formation:ground:{ground['id']}",
                    item_id=str(item_id), quantity=1,
                )
                binding["id"] = binding["reservation_id"]
            else:
                raise ValueError("镇地阵的阵材来源已经失效")
            bindings.append(binding)
        ground["bindings"] = bindings
        arrays.append(ground)
    component["ground_arrays"] = arrays
    context.state.entities.put(actor_id, FORMATION, component)
    if event.event_type == "world.permanent_transition.requested":
        context.emit(
            "world.transition.acknowledged", source="artifacts", scope=event.scope,
            payload={
                "transaction_id": event.payload["transaction_id"],
                "actor_id": actor_id, "domain": "artifacts",
            },
        )


def artifact_static_bonuses(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
) -> dict[str, Any]:
    result = {
        "combat_power": 0.0, "max_hp": 0.0, "max_mp": 0.0,
        "opportunity_efficiency": 0.0, "body_training_efficiency": 0.0,
        "divine_sense_efficiency": 0.0, "tribulation_reduction": 0.0,
        "breakthrough_bonus": 0.0,
        "player_multipliers": {key: 1.0 for key in STAT_KEYS},
        "enemy_multipliers": {key: 1.0 for key in STAT_KEYS}, "traits": [],
    }
    ledger = state.entities.get(actor_id, ASSET_LEDGER) or {}
    active_artifacts = [
        asset for asset in dict(ledger.get("instances", {})).values()
        if asset.get("kind") == "crafted_artifact"
        and not asset.get("reservation_id")
    ]
    breakthrough_values = []
    for asset in active_artifacts:
        metadata = dict(asset.get("metadata", {}))
        stats = dict(metadata.get("actual_stats", {}))
        for key in CRAFT_STATS:
            value = max(0.0, float(stats.get(key, 0)))
            if key == "breakthrough_bonus":
                breakthrough_values.append(min(0.05, value))
            else:
                result[key] += value
        for effect in metadata.get("combat_effects", []):
            for key, value in dict(effect.get("player_stat_multipliers", {})).items():
                if key in result["player_multipliers"]:
                    result["player_multipliers"][key] *= float(value)
            for key, value in dict(effect.get("enemy_stat_multipliers", {})).items():
                if key in result["enemy_multipliers"]:
                    result["enemy_multipliers"][key] *= float(value)
            result["traits"].extend(map(str, effect.get("traits", [])))
    result["breakthrough_bonus"] = max(breakthrough_values, default=0.0)
    formation = state.entities.get(actor_id, FORMATION) or {}
    location = state.entities.get(actor_id, LOCATION) or {}
    profiles = []
    if isinstance(formation.get("active"), dict):
        profiles.append(dict(formation["active"].get("profile", {})))
    profiles.extend(
        dict(row.get("profile", {})) | {"integrity": float(row.get("durability", 0)) / 100}
        for row in formation.get("ground_arrays", [])
        if row.get("world_id") == location.get("world_id")
        and row.get("location_id") == location.get("location_id")
    )
    for profile in profiles:
        integrity = float(profile.get("integrity", 1.0))
        for key, value in dict(profile.get("static_player_multipliers", {})).items():
            if key in result["player_multipliers"]:
                result["player_multipliers"][key] *= 1 + (float(value) - 1) * integrity
        for key, value in dict(profile.get("static_enemy_multipliers", {})).items():
            if key in result["enemy_multipliers"]:
                result["enemy_multipliers"][key] *= 1 + (float(value) - 1) * integrity
    natal = state.entities.get(actor_id, NATAL) or {}
    artifact = natal.get("artifact")
    if isinstance(artifact, dict):
        level = max(1, int(artifact.get("level", 1)))
        scale = 1 + float(_natal_config(definitions)["level_scale_per_level"]) * (level - 1)
        asset_id = artifact.get("asset_id")
        if asset_id and asset_id in dict(ledger.get("instances", {})):
            base_stats = dict(dict(ledger["instances"][asset_id].get("metadata", {})).get("actual_stats", {}))
            growth = scale - 1
            result["combat_power"] += float(base_stats.get("combat_power", 0)) * growth
            result["max_hp"] += float(base_stats.get("max_hp", 0)) * growth
            result["max_mp"] += float(base_stats.get("max_mp", 0)) * growth
            result["opportunity_efficiency"] += float(base_stats.get("opportunity_efficiency", 0)) * growth
            result["tribulation_reduction"] += float(base_stats.get("tribulation_reduction", 0)) * growth
        else:
            item = definitions.items.get(str(artifact.get("item_id", "")))
            if item:
                result["combat_power"] += item.combat_bonus * scale
                result["max_hp"] += item.hp_bonus * scale
                result["max_mp"] += item.mp_bonus * scale
                result["opportunity_efficiency"] += item.opportunity_bonus * scale
                result["tribulation_reduction"] += item.tribulation_damage_reduction * scale
        material_defs = _natal_materials(definitions)
        for material_id in artifact.get("slots", []):
            definition = material_defs.get(str(material_id))
            if not definition:
                continue
            for key, value in dict(definition.get("effect", {})).items():
                mapping = {
                    "combat_bonus": "combat_power", "hp_bonus": "max_hp",
                    "mp_bonus": "max_mp", "opportunity_bonus": "opportunity_efficiency",
                    "tribulation_reduction": "tribulation_reduction",
                }
                if key in mapping:
                    result[mapping[key]] += float(value)
            effect = dict(definition.get("combat_effect", {}))
            for key, value in dict(effect.get("player_stat_multipliers", {})).items():
                if key in result["player_multipliers"]:
                    result["player_multipliers"][key] *= float(value)
            for key, value in dict(effect.get("enemy_stat_multipliers", {})).items():
                if key in result["enemy_multipliers"]:
                    result["enemy_multipliers"][key] *= float(value)
            result["traits"].extend(map(str, effect.get("traits", [])))
    result["tribulation_reduction"] = min(0.50, result["tribulation_reduction"])
    return result


def artifact_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors = []
        for actor_id in state.entities.with_component(IDENTITY):
            crafting = state.entities.get(actor_id, CRAFTING)
            formation = state.entities.get(actor_id, FORMATION)
            natal = state.entities.get(actor_id, NATAL)
            if crafting is None or formation is None or natal is None:
                errors.append(f"角色 {actor_id} 缺少炼器、阵法或本命法宝组件")
                continue
            ledger = state.entities.require(actor_id, ASSET_LEDGER)
            reservations = dict(ledger.get("reservations", {}))
            referenced = set()
            active = formation.get("active")
            groups = [active] if isinstance(active, dict) else []
            groups.extend(formation.get("ground_arrays", []))
            for group in groups:
                for binding in group.get("bindings", []):
                    if not binding:
                        continue
                    reservation_id = str(binding.get("reservation_id", ""))
                    referenced.add(reservation_id)
                    if reservation_id not in reservations:
                        errors.append(f"角色 {actor_id} 的阵法引用失效预留")
            actual = {
                key for key, row in reservations.items()
                if str(row.get("purpose", "")).startswith("formation:")
            }
            if referenced != actual:
                errors.append(f"角色 {actor_id} 的阵法托管集合不一致")
            artifact = natal.get("artifact")
            if isinstance(artifact, dict):
                slots = list(artifact.get("slots", []))
                if len(slots) != 7 or len([row for row in slots if row]) != len(set(row for row in slots if row)):
                    errors.append(f"角色 {actor_id} 的本命法宝槽位非法")
                asset_id = artifact.get("asset_id")
                if asset_id:
                    asset = dict(ledger.get("instances", {})).get(asset_id)
                    if not asset or not dict(asset.get("metadata", {})).get("is_natal"):
                        errors.append(f"角色 {actor_id} 的本命炼器法宝引用失效")
        return errors
    return validate


def register_artifact_domains(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(PreviewCrafting, _preview_crafting_handler(definitions))
    bus.register(ForgeArtifact, _forge_handler(definitions))
    bus.register(SaveCraftingBlueprint, _save_blueprint_handler(definitions))
    bus.register(SellCraftedArtifact, _sell_artifact_handler(definitions))
    bus.register(PreviewFormation, _preview_formation_handler(definitions))
    bus.register(SaveFormation, _save_formation_handler(definitions))
    bus.register(ActivateFormation, _activate_handler(definitions))
    bus.register(DeactivateFormation, _deactivate_handler)
    bus.register(DeleteFormation, _delete_handler)
    bus.register(DeployGroundFormation, _deploy_handler(definitions))
    bus.register(WithdrawGroundFormation, _withdraw_handler)
    bus.register(RepairGroundFormation, _repair_handler(definitions))
    bus.register(ManageNatalArtifact, _manage_natal_handler(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("core.action.completed", _on_action_completed(definitions))
    bus.event_bus.register("world.permanent_transition.requested", _on_world_transition)
    bus.event_bus.register("world.temporary_transition.committed", _on_world_transition)


def _crafted_artifact_description(asset: dict[str, Any]) -> str:
    metadata = dict(asset.get("metadata", {}))
    stats = dict(metadata.get("actual_stats", {}))
    pieces = []
    for key, value in stats.items():
        number = float(value)
        if not number:
            continue
        shown = (
            f"{number:.1%}"
            if key.endswith("efficiency")
            or key.endswith("reduction")
            or key == "breakthrough_bonus"
            else f"{number:,.0f}"
        )
        pieces.append(f"{CRAFT_STAT_NAMES.get(key, key)} +{shown}")
    summary = "、".join(pieces) or "无常驻数值"
    effect_lines = [
        str(row.get("description", "")).strip()
        for row in metadata.get("material_effects", [])
        if str(row.get("description", "")).strip()
    ]
    description = (
        f"{metadata.get('quality_name', '')}{metadata.get('mold_name', '组合式法宝')}。"
        f"常驻属性：{summary}。"
    )
    if effect_lines:
        description += "材料器纹：" + "；".join(effect_lines) + "。"
    description += (
        f"炼于纪年 {asset.get('created_year', '?')}，锚定价值 "
        f"{int(metadata.get('anchor_value', 1)):,} 灵石。"
    )
    return description


def _crafted_artifact_public(asset: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(asset.get("metadata", {}))
    return {
        **dict(asset), **metadata,
        "id": str(asset["id"]), "name": str(asset["name"]),
        "description": _crafted_artifact_description(asset),
        "is_natal": bool(metadata.get("is_natal")),
        "equipped": not bool(asset.get("reservation_id")),
    }


def _crafted_only_bonuses(artifacts: list[dict[str, Any]]) -> dict[str, float]:
    result = {key: 0.0 for key in CRAFT_STATS}
    breakthroughs = []
    for artifact in artifacts:
        stats = dict(artifact.get("actual_stats", {}))
        for key in CRAFT_STATS:
            value = max(0.0, float(stats.get(key, 0)))
            if key == "breakthrough_bonus":
                breakthroughs.append(min(0.05, value))
            else:
                result[key] += value
    result["breakthrough_bonus"] = max(breakthroughs, default=0.0)
    return result


def crafting_view(
    state: WorldState, definitions: GameDefinitions,
    actor_id: str | None = None,
) -> dict[str, Any]:
    actor_id = actor_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    component = state.entities.require(actor_id, CRAFTING)
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    cultivation = state.entities.require(actor_id, CULTIVATION)
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    rules = _crafting_rules(definitions)
    crafting_material_ids = set(_crafting_materials(definitions))
    crafting_plant_ids = set(_crafting_plants(definitions))
    materials = [
        _material_candidate(state, definitions, actor_id, asset_id)
        for asset_id, asset in sorted(dict(ledger.get("instances", {})).items())
        if not asset.get("reservation_id") and (
            (
                asset.get("kind") == "crafting_material"
                and str(asset.get("definition_id")) in crafting_material_ids
            )
            or (
                asset.get("kind") == "harvested_spirit_plant"
                and str(asset.get("definition_id")) in crafting_plant_ids
            )
        )
    ]
    artifacts = [
        _crafted_artifact_public(asset)
        for _, asset in sorted(dict(ledger.get("instances", {})).items())
        if asset.get("kind") == "crafted_artifact"
        and not asset.get("reservation_id")
    ]
    auction = state.entities.get(actor_id, "economy.auction") or {}
    session = auction.get("session")
    location = state.entities.require(actor_id, LOCATION)
    auction_available = bool(
        isinstance(session, dict)
        and session.get("status") in {"scheduled", "open"}
        and session.get("world_id") == location.get("world_id")
        and session.get("location_id") == location.get("location_id")
    )
    budgets = list(rules.get("budget_by_realm", [40]))
    return {
        "visible": bool(definitions.systems.get("crafting"))
        and realm_index >= int(rules.get("minimum_realm", 1)),
        "molds": list(_crafting_molds(definitions).values()),
        "materials": materials,
        "artifacts": artifacts,
        "blueprints": list(component.get("blueprints", [])),
        "last_preview": component.get("last_preview"),
        "active_count": len(artifacts),
        "budget": int(budgets[min(realm_index, len(budgets) - 1)]),
        "stat_costs": dict(rules.get("stat_costs", {})),
        "stat_names": dict(CRAFT_STAT_NAMES),
        "quality_names": dict(rules.get("quality_names", {})),
        "bonuses": _crafted_only_bonuses(artifacts),
        "auction_available": auction_available,
    }


def _ground_defense_power(
    definitions: GameDefinitions, ground: dict[str, Any]
) -> float:
    if float(ground.get("durability", 0)) <= 0:
        return 0.0
    bindings = [
        dict(row) for row in ground.get("bindings", []) if isinstance(row, dict)
    ]
    if not bindings:
        return 0.0
    tiers = sorted(max(0, min(
        len(definitions.realms) - 1, int(row.get("acquired_tier", 1))
    )) for row in bindings)
    realm = definitions.realms[tiers[len(tiers) // 2]]
    profile = dict(ground.get("profile", {}))
    metrics = dict(profile.get("metrics", {}))
    structure = min(1.0, sum(
        float(metrics.get(key, 0)) for key in ("focus", "balance", "cycle")
    ) / 300)
    settings = dict(_formation_config(definitions).get("settings", {}))
    low = float(settings.get("ground_power_ratio_min", 0.18))
    high = float(settings.get("ground_power_ratio_max", 0.52))
    ratio = min(
        float(settings.get("ground_power_hard_cap_ratio", 0.58)),
        low + (high - low) * structure,
    )
    return round(
        float(realm.base_power) * ratio
        * math.sqrt(float(ground.get("durability", 0)) / 100),
        2,
    )


def formation_view(
    state: WorldState, definitions: GameDefinitions,
    actor_id: str | None = None,
) -> dict[str, Any]:
    actor_id = actor_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    component = state.entities.require(actor_id, FORMATION)
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    instances = dict(ledger.get("instances", {}))
    materials = _formation_candidates(state, definitions, actor_id)
    active = component.get("active")
    active_data = dict(active) if isinstance(active, dict) else {}
    active_bindings = []
    for slot, binding in enumerate(active_data.get("bindings", [])):
        if not binding:
            active_bindings.append(None)
            continue
        row = dict(binding)
        row.update(
            id=row.get("asset_id") or row.get("reservation_id") or row.get("id"),
            slot=slot,
        )
        active_bindings.append(row)
    location = state.entities.require(actor_id, LOCATION)
    world_id = str(location["world_id"])
    location_id = str(location["location_id"])
    world = definitions.worlds[world_id]
    ground_arrays = []
    for raw in component.get("ground_arrays", []):
        ground = dict(raw)
        ground_world_id = str(ground.get("world_id", ""))
        ground_location_id = str(ground.get("location_id", ""))
        ground_world = definitions.worlds.get(ground_world_id)
        location_name = ground_location_id
        if ground_world and ground_location_id in ground_world.locations:
            location_name = ground_world.locations[ground_location_id].name
        ground_arrays.append({
            **ground,
            "world": ground_world_id,
            "world_name": ground_world.name if ground_world else ground_world_id,
            "location_name": location_name,
            "owner_name": ground.get("owner_name", "自身"),
            "defense_power": _ground_defense_power(definitions, ground),
            "local": ground_world_id == world_id
            and ground_location_id == location_id,
        })
    supply_definitions = {
        str(row["id"]): dict(row)
        for row in _formation_config(definitions).get(
            "maintenance_resources", []
        )
    }
    supply_counts: dict[str, int] = {}
    for asset in instances.values():
        if asset.get("kind") == "formation_supply" and not asset.get(
            "reservation_id"
        ):
            definition_id = str(asset.get("definition_id", ""))
            supply_counts[definition_id] = supply_counts.get(definition_id, 0) + 1
    repair_supplies = [
        {
            **definition, "id": definition_id, "quantity": quantity,
            "world_name": definitions.worlds[definition["world"]].name
            if definition.get("world") in definitions.worlds
            else definition.get("world"),
        }
        for definition_id, quantity in sorted(supply_counts.items())
        if (definition := supply_definitions.get(definition_id))
    ]
    profile = dict(active_data.get("profile", {}))
    permitted, _, _ = _sect_formation_authority(
        state, definitions, actor_id
    )
    level = _formation_level(state, definitions, actor_id)
    field = state.entities.require(actor_id, SPIRIT_FIELD)
    return {
        **dict(component),
        "visible": bool(definitions.systems.get("formations")),
        "system_version": int(
            _formation_config(definitions).get("system_version", 1)
        ),
        "grid_size": 9,
        "level": level,
        "formation_level": level,
        "experience": round(float(
            dict(field.get("art_experience", {})).get("formation", 0)
        ), 2),
        "alpha": round(_formation_alpha(state, definitions, actor_id), 6),
        "materials": materials,
        "loadouts": list(component.get("loadouts", [])),
        "active_formation_id": active_data.get("loadout_id"),
        "active_bindings": active_bindings,
        "profile": profile,
        "ground_arrays": ground_arrays,
        "repair_supplies": repair_supplies,
        "supplies": repair_supplies,
        "current_location": {
            "world": world_id, "world_name": world.name,
            "location_id": location_id,
            "location_name": world.locations[location_id].name,
        },
        "can_deploy_personal": bool(profile.get("active")),
        "can_deploy_sect": bool(profile.get("active") and permitted),
    }


def _natal_display_bonuses(
    state: WorldState, definitions: GameDefinitions, actor_id: str,
    artifact: dict[str, Any],
) -> dict[str, float]:
    level = max(1, int(artifact.get("level", 1)))
    scale = 1 + float(_natal_config(definitions)["level_scale_per_level"]) * (
        level - 1
    )
    result = {
        "combat_bonus": 0.0, "hp_bonus": 0.0, "mp_bonus": 0.0,
        "opportunity_bonus": 0.0, "tribulation_reduction": 0.0,
    }
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    asset = dict(ledger.get("instances", {})).get(str(artifact.get("asset_id", "")))
    if isinstance(asset, dict):
        stats = dict(dict(asset.get("metadata", {})).get("actual_stats", {}))
        result.update({
            "combat_bonus": float(stats.get("combat_power", 0)) * scale,
            "hp_bonus": float(stats.get("max_hp", 0)) * scale,
            "mp_bonus": float(stats.get("max_mp", 0)) * scale,
            "opportunity_bonus": float(
                stats.get("opportunity_efficiency", 0)
            ) * scale,
            "tribulation_reduction": float(
                stats.get("tribulation_reduction", 0)
            ) * scale,
        })
    else:
        item = definitions.items.get(str(artifact.get("item_id", "")))
        if item:
            result.update({
                "combat_bonus": float(item.combat_bonus) * scale,
                "hp_bonus": float(item.hp_bonus) * scale,
                "mp_bonus": float(item.mp_bonus) * scale,
                "opportunity_bonus": float(item.opportunity_bonus) * scale,
                "tribulation_reduction": float(
                    item.tribulation_damage_reduction
                ) * scale,
            })
    material_defs = _natal_materials(definitions)
    for material_id in artifact.get("slots", []):
        definition = material_defs.get(str(material_id))
        if not definition:
            continue
        for key, value in dict(definition.get("effect", {})).items():
            if key in result:
                result[key] += float(value)
    result["tribulation_reduction"] = min(
        0.5, result["tribulation_reduction"]
    )
    return result


def natal_view(
    state: WorldState, definitions: GameDefinitions,
    actor_id: str | None = None,
) -> dict[str, Any]:
    actor_id = actor_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    cultivation = state.entities.require(actor_id, CULTIVATION)
    realm_index = definitions.realm_index(str(cultivation["realm_id"]))
    artifact = state.entities.require(actor_id, NATAL).get("artifact")
    if realm_index < int(_natal_config(definitions)["minimum_realm"]) and not artifact:
        return {"visible": False}
    if not isinstance(artifact, dict):
        ledger = state.entities.require(actor_id, ASSET_LEDGER)
        candidates = [
            {
                "id": asset["id"], "name": asset["name"],
                "kind": "crafted_artifact",
                "quantity": 1,
                "combat_bonus": float(dict(asset.get("metadata", {})).get(
                    "actual_stats", {}
                ).get("combat_power", 0)),
                "description": _crafted_artifact_description(asset),
            }
            for asset in dict(ledger.get("instances", {})).values()
            if asset.get("kind") == "crafted_artifact" and not asset.get("reservation_id")
        ]
        inventory = state.entities.require(actor_id, "economy.inventory")
        candidates.extend(
            {
                "id": item_id, "name": definitions.items[item_id].name,
                "kind": "item", "quantity": int(quantity),
                "combat_bonus": float(definitions.items[item_id].combat_bonus),
                "description": definitions.items[item_id].description,
            }
            for item_id, quantity in dict(inventory.get("items", {})).items()
            if quantity > 0 and item_id in set(_natal_config(definitions).get("eligible_item_ids", []))
        )
        return {"visible": True, "bound": False, "candidates": candidates}
    level = int(artifact["level"])
    config = _natal_config(definitions)
    ledger = state.entities.require(actor_id, ASSET_LEDGER)
    source_asset = dict(ledger.get("instances", {})).get(
        str(artifact.get("asset_id", ""))
    )
    source_item = definitions.items.get(str(artifact.get("item_id", "")))
    description = (
        _crafted_artifact_description(source_asset)
        if isinstance(source_asset, dict)
        else source_item.description if source_item else "本命法宝"
    )
    raw_slots = list(artifact.get("slots", []))[:7]
    raw_slots.extend([None] * (7 - len(raw_slots)))
    material_definitions = _natal_materials(definitions)
    materials = []
    for material_id, definition in material_definitions.items():
        quantity = inventory_quantity(state, actor_id, material_id, spendable=True)
        materials.append({
            **definition, "item_id": material_id, "quantity": quantity,
            "available": quantity > 0
            and realm_index >= int(definition["minimum_realm"])
            and material_id not in raw_slots,
        })
    slots = []
    unlocked = _natal_slots(definitions, level)
    for index, material_id in enumerate(raw_slots):
        definition = material_definitions.get(str(material_id))
        slots.append({
            "index": index, "unlocked": index < unlocked,
            "material_id": material_id,
            "name": definition.get("name") if definition else None,
            "description": definition.get("description") if definition else None,
        })
    bonuses = _natal_display_bonuses(
        state, definitions, actor_id, artifact
    )
    maximum = int(config["max_level"])
    refine_cost = int(config["manual_refine_stone_base"]) * level
    return {
        "visible": True, "bound": True, **dict(artifact),
        "description": description,
        "crafted_artifact_id": artifact.get("asset_id"),
        "max_level": maximum,
        "unlocked_slots": unlocked,
        "experience_required": int(config["experience_base"]) * level
        if level < maximum else 0,
        "refine_cost": refine_cost,
        "can_refine": level < maximum and inventory_quantity(
            state, actor_id, CURRENCY_ID, spendable=True
        ) >= refine_cost,
        # Keep the canonical slot IDs stable for V2 callers and expose the
        # richer V1 rendering contract separately.  The frozen facade maps
        # slot_details back to `slots` for the legacy UI.
        "slots": raw_slots,
        "slot_details": slots,
        "materials": materials,
        "bonuses": {
            **bonuses,
            "combat_power": bonuses["combat_bonus"],
            "max_hp": bonuses["hp_bonus"],
            "max_mp": bonuses["mp_bonus"],
            "opportunity_efficiency": bonuses["opportunity_bonus"],
        },
    }
