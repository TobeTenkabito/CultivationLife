from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .assets import ASSET_LEDGER, consume_asset, create_asset, require_asset
from .character import IDENTITY, LIFE
from .combat import CONDITION
from .cultivation import CULTIVATION
from .definitions import GameDefinitions
from .economy import CURRENCY_ID, change_inventory_item, inventory_quantity
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


SPIRIT_FIELD = "economy.spirit_field"


@dataclass(frozen=True, slots=True)
class ReclaimSpiritField:
    actor_id: str


@dataclass(frozen=True, slots=True)
class PlantSpiritCrop:
    actor_id: str
    plant_id: str
    slot: int | None = None


@dataclass(frozen=True, slots=True)
class IrrigateSpiritCrop:
    actor_id: str
    plot_id: str
    mp_ratio: float = 0.0
    booster_id: str = ""


@dataclass(frozen=True, slots=True)
class HarvestSpiritCrop:
    actor_id: str
    plot_id: str


@dataclass(frozen=True, slots=True)
class SellSpiritPlant:
    actor_id: str
    asset_id: str
    venue: str = "market"


@dataclass(frozen=True, slots=True)
class UseHarvestedPlant:
    actor_id: str
    asset_id: str


@dataclass(frozen=True, slots=True)
class RefinePill:
    actor_id: str
    target_item_id: str
    materials: tuple[tuple[str, int], ...]


def _new_field() -> dict[str, Any]:
    return {
        "reclaimed_qing": 0,
        "next_plot_sequence": 1,
        "plots": [],
        "art_experience": {
            "alchemy": 0.0,
            "refining": 0.0,
            "formation": 0.0,
            "talisman": 0.0,
            "spirit_control": 0.0,
        },
    }


def reconcile_production_state(state: WorldState) -> None:
    for entity_id in state.entities.with_component(IDENTITY):
        existing = state.entities.get(entity_id, SPIRIT_FIELD)
        if existing is None:
            state.entities.put(entity_id, SPIRIT_FIELD, _new_field())
            continue
        field = dict(existing)
        experience = dict(field.get("art_experience", {}))
        if "alchemy_experience" in field:
            experience.setdefault("alchemy", float(field.pop("alchemy_experience")))
        for art_id in (
            "alchemy", "refining", "formation", "talisman", "spirit_control"
        ):
            experience.setdefault(art_id, 0.0)
        field["art_experience"] = experience
        state.entities.put(entity_id, SPIRIT_FIELD, field)


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(str(event.payload["entity_id"]), SPIRIT_FIELD, _new_field())


def _rules(definitions: GameDefinitions) -> dict[str, Any]:
    return dict(definitions.systems["spirit_field"])


def _grant_art_experience(field: dict[str, Any], art_id: str, amount: float) -> None:
    experience = dict(field.get("art_experience", {}))
    experience[art_id] = max(0.0, float(experience.get(art_id, 0))) + max(
        0.0, float(amount)
    )
    field["art_experience"] = experience


def _art_level(field: dict[str, Any], definitions: GameDefinitions, art_id: str) -> int:
    base = float(_rules(definitions)["art_experience_base"])
    experience = float(dict(field.get("art_experience", {})).get(art_id, 0))
    return int(math.sqrt(max(0.0, experience) / base))


def _ensure_available(context: SimulationContext, actor_id: str) -> None:
    if actor_id != context.state.controlled_entity_id:
        raise ValueError("只能管理当前角色的生产资产")
    if not bool(context.state.entities.require(actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色不能进行生产")
    if context.state.relations.find(target_id=actor_id, kind="combat_prisoner"):
        raise ValueError("服刑期间不能进行生产")


def _rounded_years(years: float) -> int:
    years = max(0.0, float(years))
    if years <= 0:
        return 0
    if years < 10:
        return max(1, int(math.floor(years)))
    magnitude = 10 ** int(math.floor(math.log10(years)))
    unit = max(10, min(10_000, magnitude))
    return int(math.floor(years / unit) * unit)


def _quality(years: int, optimal: int) -> float:
    if years <= 0 or optimal <= 0:
        return 0.0
    distance = abs(math.log10(years / optimal))
    return round(max(0.15, 1.0 - distance * 0.45), 4)


def _plant_value(plant: dict[str, Any], years: int, quality: float) -> int:
    return max(
        1,
        round(
            float(plant["base_value"])
            * max(1.0, (max(1, years) / 10) ** 0.55)
            * max(0.15, quality)
        ),
    )


def _reclaim(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ReclaimSpiritField):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        if definitions.realm_index(str(cultivation["realm_id"])) == 0:
            raise ValueError("凡人尚无能力布置灵田禁制")
        field = context.state.entities.require(command.actor_id, SPIRIT_FIELD)
        rules = _rules(definitions)
        reclaimed = int(field["reclaimed_qing"])
        if reclaimed >= int(rules["max_qing"]):
            raise ValueError("灵田已经全部开垦")
        cost = max(
            1,
            round(
                float(rules["reclaim_base_stones"])
                * float(rules["reclaim_stone_growth"]) ** reclaimed
            ),
        )
        if inventory_quantity(
            context.state, command.actor_id, CURRENCY_ID, spendable=True
        ) < cost:
            raise ValueError(f"开垦下一顷灵田需要 {cost} 枚下品灵石")
        change_inventory_item(
            context, definitions, command.actor_id, CURRENCY_ID, -cost,
            "spirit_field:reclaim",
        )
        field["reclaimed_qing"] = reclaimed + 1
        _grant_art_experience(field, "formation", 12 + 4 * reclaimed)
        context.state.entities.put(command.actor_id, SPIRIT_FIELD, field)
        context.emit(
            "economy.spirit_field.reclaimed",
            source="production",
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "qing": reclaimed + 1, "cost": cost},
        )

    return handler


def _plant(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, PlantSpiritCrop):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        rules = _rules(definitions)
        plant = dict(rules["plants"].get(command.plant_id, {}))
        if not plant:
            raise ValueError("未知灵植")
        field = context.state.entities.require(command.actor_id, SPIRIT_FIELD)
        reclaimed = int(field["reclaimed_qing"])
        plots = [dict(row) for row in field.get("plots", [])]
        occupied = {int(row["slot"]) for row in plots}
        if len(occupied) >= reclaimed:
            raise ValueError("没有空闲灵田")
        slot = command.slot
        if slot is None:
            slot = next(index for index in range(reclaimed) if index not in occupied)
        if slot < 0 or slot >= reclaimed or slot in occupied:
            raise ValueError("所选田块并非空闲沃土")
        seed_id = str(plant["seed_id"])
        if inventory_quantity(
            context.state, command.actor_id, seed_id, spendable=True
        ) < 1:
            raise ValueError("行囊中没有对应灵植种子")
        change_inventory_item(
            context, definitions, command.actor_id, seed_id, -1,
            f"spirit_field:plant:{command.plant_id}",
        )
        sequence = int(field.get("next_plot_sequence", 1))
        plots.append({
            "id": f"crop:{command.actor_id}:{sequence}",
            "plant_id": command.plant_id,
            "slot": slot,
            "growth_years": 0.0,
            "planted_year": context.state.clock.year,
            "booster_unlocked": False,
        })
        _grant_art_experience(field, "alchemy", 2)
        field.update(next_plot_sequence=sequence + 1, plots=plots)
        context.state.entities.put(command.actor_id, SPIRIT_FIELD, field)

    return handler


def _irrigate(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, IrrigateSpiritCrop):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        field = context.state.entities.require(command.actor_id, SPIRIT_FIELD)
        plots = [dict(row) for row in field.get("plots", [])]
        index = next(
            (i for i, row in enumerate(plots) if row.get("id") == command.plot_id), None
        )
        if index is None:
            raise ValueError("灵田中没有这株灵植")
        rules = _rules(definitions)
        minimum = float(rules["irrigation_min_mp_ratio"])
        maximum = float(rules["irrigation_max_mp_ratio"])
        ratio = float(command.mp_ratio or rules["irrigation_mp_ratio"])
        if not minimum <= ratio <= maximum:
            raise ValueError(f"单次灌溉须投入最大 MP 的 {minimum:.0%} 至 {maximum:.0%}")
        condition = context.state.entities.require(command.actor_id, CONDITION)
        if float(condition["mp_ratio"]) < ratio:
            raise ValueError("当前 MP 不足以灌溉灵植")
        plot = plots[index]
        plant = dict(rules["plants"][str(plot["plant_id"])])
        multiplier = 1.0
        if command.booster_id:
            booster = definitions.items.get(command.booster_id)
            if (
                booster is None
                or "spirit_plant_booster" not in booster.tags
                or inventory_quantity(
                    context.state, command.actor_id, command.booster_id, spendable=True
                ) < 1
            ):
                raise ValueError("没有可用于培育的造化灵液")
            change_inventory_item(
                context, definitions, command.actor_id, command.booster_id, -1,
                f"spirit_field:booster:{command.plot_id}",
            )
            plot["booster_unlocked"] = True
            multiplier = 2.0 if command.booster_id == "creation_heaven_dew" else 1.6
        if plant.get("requires_booster") and not plot.get("booster_unlocked"):
            raise ValueError("这株灵植须先吸收造化灵液，才能承受 MP 催熟")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        realm_index = definitions.realm_index(str(cultivation["realm_id"]))
        spirit_level = _art_level(field, definitions, "spirit_control")
        gain = max(
            0.1,
            float(rules["irrigation_years_by_realm"][str(realm_index)])
            * ratio * (1 + spirit_level * 0.04) * multiplier,
        )
        plot["growth_years"] = float(plot.get("growth_years", 0)) + gain
        plots[index] = plot
        field["plots"] = plots
        _grant_art_experience(field, "spirit_control", max(2.0, min(40.0, 4 + math.sqrt(gain))))
        context.state.entities.put(command.actor_id, SPIRIT_FIELD, field)
        context.emit(
            "combat.condition.drain.requested",
            source="production",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "hp_ratio": 0.0,
                "mp_ratio": ratio, "reason": "spirit_field:irrigation",
            },
        )

    return handler


def _harvest(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, HarvestSpiritCrop):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        field = context.state.entities.require(command.actor_id, SPIRIT_FIELD)
        plots = [dict(row) for row in field.get("plots", [])]
        plot = next((row for row in plots if row.get("id") == command.plot_id), None)
        if plot is None or float(plot.get("growth_years", 0)) <= 0:
            raise ValueError("这株灵植尚未形成可收获的药性")
        plant = dict(_rules(definitions)["plants"][str(plot["plant_id"])])
        years = _rounded_years(float(plot["growth_years"]))
        quality = _quality(years, int(plant["optimal_years"]))
        value = _plant_value(plant, years, quality)
        asset_id = create_asset(
            context,
            command.actor_id,
            kind="harvested_spirit_plant",
            definition_id=str(plot["plant_id"]),
            name=f"{years:,}年{plant['name']}",
            metadata={
                "plant_id": plot["plant_id"], "years": years,
                "quality": quality, "value": value,
                "plant_kind": plant.get("kind", "medicinal"),
            },
        )
        field["plots"] = [row for row in plots if row.get("id") != command.plot_id]
        _grant_art_experience(
            field, "alchemy", max(4, min(120, round(5 + math.log10(max(10, years)) * 15)))
        )
        context.state.entities.put(command.actor_id, SPIRIT_FIELD, field)
        context.emit(
            "economy.spirit_field.harvested",
            source="production",
            scope=EventScope.entity(command.actor_id),
            payload={"entity_id": command.actor_id, "plot_id": command.plot_id, "asset_id": asset_id},
        )

    return handler


def _sell(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, SellSpiritPlant):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        if command.venue not in {"market", "black_market"}:
            raise ValueError("未知灵植交易场所")
        if command.venue == "black_market":
            raise ValueError("需先进入黑市交易会话")
        cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
        if definitions.realm_index(str(cultivation["realm_id"])) == 0:
            raise ValueError("凡人无法进入坊市出售灵植")
        asset = require_asset(context.state, command.actor_id, command.asset_id)
        if asset.get("kind") != "harvested_spirit_plant":
            raise ValueError("只有采收后的灵植能够出售")
        ratio_key = (
            "black_market_sell_ratio" if command.venue == "black_market"
            else "market_sell_ratio"
        )
        ratio = float(_rules(definitions)[ratio_key])
        price = max(1, round(float(asset["metadata"]["value"]) * ratio))
        consume_asset(context, command.actor_id, command.asset_id)
        change_inventory_item(
            context, definitions, command.actor_id, CURRENCY_ID, price,
            f"spirit_plant:sell:{command.venue}",
        )
        context.emit(
            "economy.spirit_plant.sold",
            source="production",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "asset_id": command.asset_id,
                "venue": command.venue, "price": price,
            },
        )

    return handler


def _use_harvested(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, UseHarvestedPlant):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        asset = require_asset(context.state, command.actor_id, command.asset_id)
        if asset.get("kind") != "harvested_spirit_plant":
            raise ValueError("这不是可直接使用的灵植")
        metadata = dict(asset["metadata"])
        plant_id, years = str(metadata["plant_id"]), int(metadata["years"])
        plant = dict(_rules(definitions)["plants"][plant_id])
        if plant_id == "mystic_heaven_vine" and years >= int(plant["use_years"]):
            consume_asset(context, command.actor_id, command.asset_id)
            change_inventory_item(
                context, definitions, command.actor_id, str(plant["use_reward"]), 1,
                "spirit_plant:use",
            )
        elif plant_id == "nebula_manjushaka" and years >= int(plant["use_years"]):
            consume_asset(context, command.actor_id, command.asset_id)
            cultivation = context.state.entities.require(command.actor_id, CULTIVATION)
            cultivation["next_thunder_damage_reduction"] = max(
                float(cultivation.get("next_thunder_damage_reduction", 0)),
                float(plant["thunder_reduction"]),
            )
            context.state.entities.put(command.actor_id, CULTIVATION, cultivation)
        else:
            raise ValueError("这株灵植尚未达到可使用年份，或其效果为持有生效")

    return handler


def _refine(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, RefinePill):
            raise TypeError("命令类型错误")
        _ensure_available(context, command.actor_id)
        target = definitions.items.get(command.target_item_id)
        if target is None or "pill" not in target.tags:
            raise ValueError("目标必须是一种可炼制丹药")
        if not command.materials:
            raise ValueError("至少投入一株药材")
        seen: set[str] = set()
        instance_materials: list[dict[str, Any]] = []
        stack_materials: list[tuple[str, int]] = []
        qualities: list[tuple[float, int]] = []
        total = 0
        for material_id, quantity in command.materials:
            if material_id in seen or quantity <= 0:
                raise ValueError("炼丹材料重复或数量非法")
            seen.add(material_id)
            ledger = context.state.entities.require(command.actor_id, ASSET_LEDGER)
            raw_asset = dict(ledger.get("instances", {})).get(material_id)
            if isinstance(raw_asset, dict):
                if quantity != 1 or raw_asset.get("kind") != "harvested_spirit_plant":
                    raise ValueError("实例药材数量非法")
                if raw_asset.get("reservation_id"):
                    raise ValueError("药材正在预留或托管中")
                if raw_asset.get("metadata", {}).get("plant_kind") != "medicinal":
                    raise ValueError("特殊灵植不能作为普通炼丹药材")
                instance_materials.append(dict(raw_asset))
                qualities.append((float(raw_asset["metadata"].get("quality", 0.55)), 1))
            else:
                definition = definitions.items.get(material_id)
                if definition is None or "herb" not in definition.tags or "seed" in definition.tags:
                    raise ValueError("炼丹材料中混入了非药材物品")
                if inventory_quantity(
                    context.state, command.actor_id, material_id, spendable=True
                ) < quantity:
                    raise ValueError("药材数量不足")
                stack_materials.append((material_id, quantity))
                qualities.append((0.55, quantity))
            total += quantity
        condition = context.state.entities.require(command.actor_id, CONDITION)
        if float(condition["mp_ratio"]) < 0.15:
            raise ValueError("炼丹需要至少 15% 最大 MP")
        tier = min(
            (
                good.tier for good in definitions.market_goods
                if good.kind == "item" and good.content_id == command.target_item_id
            ),
            default=1,
        )
        field = context.state.entities.require(command.actor_id, SPIRIT_FIELD)
        level = _art_level(field, definitions, "alchemy")
        average = sum(value * count for value, count in qualities) / total
        chance = max(
            0.05,
            min(
                0.95,
                0.22 + average * 0.42 + level * 0.065
                + math.log2(total + 1) * 0.045 - (tier - 1) * 0.085,
            ),
        )
        for asset in instance_materials:
            consume_asset(context, command.actor_id, str(asset["id"]))
        for item_id, quantity in stack_materials:
            change_inventory_item(
                context, definitions, command.actor_id, item_id, -quantity,
                f"alchemy:{command.target_item_id}",
            )
        context.emit(
            "combat.condition.drain.requested",
            source="production",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "hp_ratio": 0.0,
                "mp_ratio": 0.15, "reason": "alchemy",
            },
        )
        success = context.rng.random() < chance
        if success:
            change_inventory_item(
                context, definitions, command.actor_id, command.target_item_id, 1,
                "alchemy:product",
            )
        experience = (8 + tier * 7 + total * 2) * (1.35 if success else 1.0)
        _grant_art_experience(field, "alchemy", experience)
        context.state.entities.put(command.actor_id, SPIRIT_FIELD, field)
        context.emit(
            "crafting.alchemy.resolved",
            source="production",
            scope=EventScope.entity(command.actor_id),
            payload={
                "entity_id": command.actor_id, "target_item_id": command.target_item_id,
                "success": success, "chance": chance, "materials": total,
            },
        )

    return handler


def _on_time_advanced(context: SimulationContext, event: EventEnvelope) -> None:
    elapsed = int(event.payload["to_year"]) - int(event.payload["from_year"])
    if elapsed <= 0:
        return
    for entity_id in context.state.entities.with_component(SPIRIT_FIELD):
        field = context.state.entities.require(entity_id, SPIRIT_FIELD)
        plots = [dict(row) for row in field.get("plots", [])]
        for plot in plots:
            plot["growth_years"] = float(plot.get("growth_years", 0)) + elapsed
        field["plots"] = plots
        context.state.entities.put(entity_id, SPIRIT_FIELD, field)


def production_invariants(definitions: GameDefinitions):
    def validate(state: WorldState) -> list[str]:
        errors: list[str] = []
        plants = dict(_rules(definitions)["plants"])
        maximum = int(_rules(definitions)["max_qing"])
        for entity_id in state.entities.with_component(IDENTITY):
            field = state.entities.get(entity_id, SPIRIT_FIELD)
            if field is None:
                errors.append(f"角色 {entity_id} 缺少灵田组件")
                continue
            reclaimed = int(field.get("reclaimed_qing", -1))
            if not 0 <= reclaimed <= maximum:
                errors.append(f"角色 {entity_id} 的灵田面积非法")
            experience = field.get("art_experience")
            if not isinstance(experience, dict) or any(
                not isinstance(experience.get(art_id), (int, float))
                or float(experience[art_id]) < 0
                for art_id in (
                    "alchemy", "refining", "formation", "talisman", "spirit_control"
                )
            ):
                errors.append(f"角色 {entity_id} 的百艺经验无效")
            slots: set[int] = set()
            plot_ids: set[str] = set()
            for plot in field.get("plots", []):
                plot_id = str(plot.get("id", ""))
                slot = int(plot.get("slot", -1))
                if not plot_id or plot_id in plot_ids or slot in slots:
                    errors.append(f"角色 {entity_id} 的灵田地块重复")
                plot_ids.add(plot_id)
                slots.add(slot)
                if (
                    plot.get("plant_id") not in plants
                    or not 0 <= slot < reclaimed
                    or float(plot.get("growth_years", -1)) < 0
                ):
                    errors.append(f"角色 {entity_id} 的灵田作物非法：{plot_id}")
        return errors

    return validate


def register_production_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(ReclaimSpiritField, _reclaim(definitions))
    bus.register(PlantSpiritCrop, _plant(definitions))
    bus.register(IrrigateSpiritCrop, _irrigate(definitions))
    bus.register(HarvestSpiritCrop, _harvest(definitions))
    bus.register(SellSpiritPlant, _sell(definitions))
    bus.register(UseHarvestedPlant, _use_harvested(definitions))
    bus.register(RefinePill, _refine(definitions))
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("core.time.advanced", _on_time_advanced)


def production_view(
    state: WorldState, definitions: GameDefinitions, entity_id: str | None = None,
) -> dict[str, Any]:
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    field = state.entities.require(actor_id, SPIRIT_FIELD)
    rules = _rules(definitions)
    plots = []
    for raw in field.get("plots", []):
        plot = dict(raw)
        plant = dict(rules["plants"][str(plot["plant_id"])])
        years = _rounded_years(float(plot["growth_years"]))
        quality = _quality(years, int(plant["optimal_years"])) if years else 0.0
        plots.append({
            **plot,
            "name": plant["name"],
            "display_years": years,
            "quality": quality,
            "value": _plant_value(plant, max(1, years), quality),
            "optimal_years": int(plant["optimal_years"]),
            "can_harvest": float(plot["growth_years"]) > 0,
        })
    reclaimed = int(field["reclaimed_qing"])
    next_cost = max(
        1,
        round(
            float(rules["reclaim_base_stones"])
            * float(rules["reclaim_stone_growth"]) ** reclaimed
        ),
    )
    experience = dict(field.get("art_experience", {}))
    art_names = {
        "alchemy": "炼丹", "refining": "炼器", "formation": "阵法",
        "talisman": "制符", "spirit_control": "御灵",
    }
    base = float(rules["art_experience_base"])
    art_skills = []
    for art_id, name in art_names.items():
        amount = max(0.0, float(experience.get(art_id, 0)))
        level = int(math.sqrt(amount / base))
        current = base * level * level
        following = base * (level + 1) * (level + 1)
        art_skills.append({
            "id": art_id, "name": name, "level": level,
            "experience": round(amount, 1),
            "level_experience": round(amount - current, 1),
            "next_level_experience": round(following - current, 1),
        })
    return {
        "max_qing": int(rules["max_qing"]),
        "reclaimed_qing": reclaimed,
        "free_qing": max(0, reclaimed - len(plots)),
        "reclaim_cost": next_cost,
        "reclaim_years": 0,
        "plots": plots,
        "art_skills": art_skills,
        "alchemy_experience": float(experience.get("alchemy", 0)),
        "alchemy_level": _art_level(field, definitions, "alchemy"),
    }
