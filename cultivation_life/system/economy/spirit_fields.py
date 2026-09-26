from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import math
    from typing import Any
    from ...content_registry import GUIXU_EXCLUSIVE_ITEM_IDS, ITEM_CATALOG, MARKET_GOODS, WORLD_SYSTEMS
    from ...models import HistoryRecord, Item, Player
    from ...runtime import now_iso
    from ...rules import add_item, max_mp, remove_item


class EconomySpiritFieldMethods:
    @staticmethod
    def _spirit_field_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS["spirit_field"]

    @staticmethod
    def _rounded_plant_years(years: float) -> int:
        years = max(0.0, float(years))
        if years <= 0:
            return 0
        if years < 10:
            return max(1, int(math.floor(years)))
        magnitude = 10 ** int(math.floor(math.log10(years)))
        unit = max(10, min(10000, magnitude))
        return int(math.floor(years / unit) * unit)

    @staticmethod
    def _plant_quality(years: int, optimal_years: int) -> float:
        if years <= 0 or optimal_years <= 0:
            return 0.0
        distance = abs(math.log10(years / optimal_years))
        return round(max(0.15, 1.0 - distance * 0.45), 4)

    def _plant_item_value(self, item_or_id: Item | str) -> int | None:
        if isinstance(item_or_id, Item) and item_or_id.plant_id:
            return int(item_or_id.plant_value or 1)
        item_id = item_or_id.id if isinstance(item_or_id, Item) else item_or_id
        for plant in self._spirit_field_rules()["plants"].values():
            for harvest in plant["harvest"].values():
                if harvest["item_id"] == item_id:
                    return int(harvest["value"])
        return None

    def _add_harvested_plant(self, player: Player, plant_id: str, actual_years: float) -> Item:
        plant = self._spirit_field_rules()["plants"][plant_id]
        rounded_years = self._rounded_plant_years(actual_years)
        optimal = int(plant["optimal_years"])
        quality = self._plant_quality(rounded_years, optimal)
        value = max(1, round(float(plant["base_value"]) * max(1.0, (rounded_years / 10) ** 0.55) * quality))
        item_id = f"harvest:{plant_id}:{rounded_years}"
        existing = next((item for item in player.inventory if item.id == item_id), None)
        if existing:
            existing.quantity += 1
            return existing
        kind = str(plant.get("kind", "medicinal"))
        effect_text = ""
        if plant_id == "mystic_heaven_vine":
            effect_text = "达到一万年后可使用并炼成枯荣天剑。"
        elif plant_id == "golden_thunder_bamboo":
            effect_text = "达到一万年后，持有至少一株即可使最终战斗力提高 1%。"
        elif plant_id == "nebula_manjushaka":
            effect_text = "达到五千年后可使用，使下一次三千年雷劫伤害降低 10%。"
        item = Item(
            id=item_id, name=f"{rounded_years:,}年{plant['name']}",
            description=(
                f"实际采收年份向下记作 {rounded_years:,} 年；品质 {quality:.0%}，"
                f"最佳年份为 {optimal:,} 年。{effect_text}"
            ),
            tags=["spirit_plant", "herb" if kind == "medicinal" else "special_plant"],
            plant_id=plant_id, plant_years=rounded_years, plant_quality=quality,
            plant_kind=kind, plant_value=value,
        )
        player.inventory.append(item)
        return item

    def _annual_spirit_field_update(self, player: Player) -> None:
        # Bounded by max_qing, so multi-century actions stay O(years * 8) with no logs.
        growth = 1.0 + max(0.0, float(player.sage_effects.get("field_alchemy_multiplier", 0.0)))
        for plot in player.spirit_field.get("plots", []):
            plot["growth_years"] = float(plot.get("growth_years", 0.0)) + growth

    def _public_spirit_field(self, player: Player) -> dict[str, Any]:
        rules = self._spirit_field_rules()
        field = player.spirit_field
        reclaimed = min(int(rules["max_qing"]), max(0, int(field.get("reclaimed_qing", 0))))
        next_qing = reclaimed + 1
        reclaim_cost = max(1, round(float(rules["reclaim_base_stones"]) * float(rules["reclaim_stone_growth"]) ** reclaimed))
        plots = []
        used_slots: set[int] = set()
        for plot_index, plot in enumerate(field.get("plots", [])):
            plant = rules["plants"].get(str(plot.get("plant_id")))
            if not plant:
                continue
            slot = int(plot.get("slot", plot_index))
            if slot < 0 or slot >= reclaimed or slot in used_slots:
                slot = next((candidate for candidate in range(reclaimed) if candidate not in used_slots), plot_index)
            plot["slot"] = slot
            used_slots.add(slot)
            actual_years = float(plot.get("growth_years", 0))
            rounded_years = self._rounded_plant_years(actual_years)
            quality = self._plant_quality(rounded_years, int(plant["optimal_years"])) if rounded_years else 0.0
            value = max(1, round(float(plant["base_value"]) * max(1.0, (max(10, rounded_years) / 10) ** 0.55) * max(0.15, quality)))
            plots.append({
                **plot, "name":plant["name"], "kind":plant.get("kind", "medicinal"),
                "display_years":rounded_years, "value":value, "quality":quality,
                "optimal_years":int(plant["optimal_years"]),
                "best":rounded_years == int(plant["optimal_years"]), "can_harvest":actual_years > 0,
                "requires_booster":bool(plant.get("requires_booster")),
                "booster_unlocked":bool(plot.get("booster_unlocked")),
            })
        seeds = []
        for plant_id, plant in rules["plants"].items():
            quantity = next((item.quantity for item in player.inventory if item.id == plant["seed_id"]), 0)
            if quantity:
                seeds.append({"plant_id":plant_id, "seed_id":plant["seed_id"], "name":plant["name"], "quantity":quantity})
        alchemy_targets: dict[str, dict[str, Any]] = {}
        for row in MARKET_GOODS:
            item = ITEM_CATALOG.get(str(row.get("content_id"))) if row.get("kind") == "item" else None
            if not item or "pill" not in item.tags or int(row["tier"]) > min(8, player.realm_index + 1):
                continue
            current = alchemy_targets.get(item.id)
            if current is None or int(row["tier"]) < current["tier"]:
                alchemy_targets[item.id] = {"id":item.id, "name":item.name, "tier":int(row["tier"]), "description":item.description}
        for item in ITEM_CATALOG.values():
            if (
                "pill" in item.tags and item.id not in alchemy_targets
                and item.id not in GUIXU_EXCLUSIVE_ITEM_IDS
            ):
                alchemy_targets[item.id] = {"id":item.id, "name":item.name, "tier":1, "description":item.description}
        materials = [
            {"id":item.id, "name":item.name, "quantity":item.quantity,
             "years":item.plant_years, "quality":item.plant_quality or 0.55}
            for item in player.inventory
            if "herb" in item.tags and "seed" not in item.tags and item.quantity > 0
        ]
        return {
            "max_qing":int(rules["max_qing"]), "reclaimed_qing":reclaimed,
            "free_qing":max(0, reclaimed - len(plots)), "plots":plots, "seeds":seeds,
            "can_reclaim":reclaimed < int(rules["max_qing"]), "reclaim_cost":reclaim_cost,
            "reclaim_years":0,
            "spirit_stones":self._spirit_stones(player), "mp":round(player.mp, 1),
            "max_mp":round(max_mp(player), 1),
            "irrigation_min_mp":round(max(1.0, max_mp(player) * float(rules["irrigation_min_mp_ratio"])), 1),
            "irrigation_max_mp":round(max(1.0, max_mp(player) * float(rules["irrigation_max_mp_ratio"])), 1),
            "irrigation_years_at_full_mp":float(rules["irrigation_years_by_realm"][str(player.realm_index)]),
            "boosters":[
                {"id":item.id, "name":item.name, "quantity":item.quantity}
                for item in player.inventory if "spirit_plant_booster" in item.tags and item.quantity > 0
            ],
            "alchemy":{"materials":materials, "targets":sorted(alchemy_targets.values(), key=lambda row: (row["tier"], row["name"]))},
        }

    def reclaim_spirit_field(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法开垦灵田")
        if player.realm_index == 0:
            raise ValueError("凡人尚无能力布置灵田禁制")
        rules = self._spirit_field_rules()
        reclaimed = int(player.spirit_field.get("reclaimed_qing", 0))
        if reclaimed >= int(rules["max_qing"]):
            raise ValueError("灵田已经全部开垦")
        cost = max(1, round(float(rules["reclaim_base_stones"]) * float(rules["reclaim_stone_growth"]) ** reclaimed))
        if not remove_item(player, "spirit_stone", cost):
            raise ValueError(f"开垦下一顷灵田需要 {cost} 枚下品灵石")
        player.spirit_field["reclaimed_qing"] = reclaimed + 1
        self._grant_art_experience(player, "formation", 12 + 4 * reclaimed)
        summary = f"你耗费 {cost} 枚灵石布置聚灵、沃土诸阵，立即开垦了第 {reclaimed + 1} 顷灵田。"
        game.history.append(HistoryRecord(
            "SYS_SPIRIT_FIELD_RECLAIM", 1, player.age, "开垦灵田", None,
            "reclaimed", summary,
            {"cost":-cost, "years":0}, ["system", "spirit_field"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def plant_spirit_crop(self, game_id: str, plant_id: str, slot: int | None = None) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive:
            raise ValueError("当前状态无法播种")
        rules = self._spirit_field_rules()
        plant = rules["plants"].get(plant_id)
        field = game.player.spirit_field
        if not plant:
            raise ValueError("未知灵植")
        if len(field.get("plots", [])) >= int(field.get("reclaimed_qing", 0)):
            raise ValueError("没有空闲灵田")
        occupied = {int(row.get("slot", index)) for index, row in enumerate(field.get("plots", []))}
        chosen_slot = int(slot) if slot is not None else next(
            candidate for candidate in range(int(field.get("reclaimed_qing", 0))) if candidate not in occupied
        )
        if chosen_slot < 0 or chosen_slot >= int(field.get("reclaimed_qing", 0)) or chosen_slot in occupied:
            raise ValueError("所选田块并非空闲沃土")
        if not remove_item(game.player, plant["seed_id"]):
            raise ValueError("行囊中没有对应灵植种子")
        field["sequence"] = int(field.get("sequence", 0)) + 1
        field.setdefault("plots", []).append({
            "id":f"crop-{field['sequence']}", "plant_id":plant_id,
            "slot":chosen_slot, "growth_years":0.0, "planted_age":game.player.age, "booster_unlocked":False,
        })
        self._grant_art_experience(game.player, "alchemy", 2)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def irrigate_spirit_crop(
        self, game_id: str, plot_id: str, mp_amount: float = 0, booster_id: str = "",
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive:
            raise ValueError("当前状态无法灌溉")
        plot = next((row for row in game.player.spirit_field.get("plots", []) if row.get("id") == plot_id), None)
        if not plot:
            raise ValueError("灵田中没有这株灵植")
        rules = self._spirit_field_rules()
        maximum_mp = max_mp(game.player)
        minimum = max(1.0, maximum_mp * float(rules["irrigation_min_mp_ratio"]))
        maximum = max(minimum, maximum_mp * float(rules["irrigation_max_mp_ratio"]))
        cost = float(mp_amount or max(minimum, maximum_mp * float(rules["irrigation_mp_ratio"])))
        if cost < minimum or cost > maximum:
            raise ValueError(f"单次灌溉须投入 {minimum:.0f} 至 {maximum:.0f} MP")
        if game.player.mp < cost:
            raise ValueError("当前 MP 不足以灌溉灵植")
        plant = rules["plants"][plot["plant_id"]]
        booster_multiplier = 1.0
        if booster_id:
            booster = ITEM_CATALOG.get(booster_id)
            if not booster or "spirit_plant_booster" not in booster.tags or not remove_item(game.player, booster_id):
                raise ValueError("没有可用于培育的造化灵液")
            plot["booster_unlocked"] = True
            booster_multiplier = 2.0 if booster_id == "creation_heaven_dew" else 1.6
        if plant.get("requires_booster") and not plot.get("booster_unlocked"):
            raise ValueError("这株灵植须先吸收岁华灵露或太虚灵泉，才能承受 MP 催熟")
        spirit_level = next((row["level"] for row in self._public_art_skills(game.player) if row["id"] == "spirit_control"), 0)
        realm_yield = float(rules["irrigation_years_by_realm"][str(game.player.realm_index)])
        gain = max(
            0.1,
            realm_yield * (cost / maximum_mp) * (1 + spirit_level * 0.04) * booster_multiplier
            * (1 + max(0.0, float(game.player.sage_effects.get("field_alchemy_multiplier", 0.0)))),
        )
        game.player.mp -= cost
        plot["growth_years"] = float(plot.get("growth_years", 0)) + gain
        art_gain = max(2.0, min(40.0, 4 + math.sqrt(gain)))
        self._grant_art_experience(game.player, "spirit_control", art_gain)
        game.history.append(HistoryRecord(
            "SYS_SPIRIT_FIELD_IRRIGATE", 1, game.player.age, "法力灌溉", plot_id, "irrigated",
            f"你消耗 {cost:.0f} MP 引气润田，使{plant['name']}等效生长 {gain:.1f} 年"
            f"{'，造化灵液令催熟效果进一步增强' if booster_id else ''}。",
            {"mp":-round(cost, 1), "growth_years":round(gain, 2), "booster_id":booster_id or None}, ["system", "spirit_field", "art:spirit_control"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def harvest_spirit_crop(self, game_id: str, plot_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        plot = next((row for row in game.player.spirit_field.get("plots", []) if row.get("id") == plot_id), None)
        if not plot or float(plot.get("growth_years", 0)) <= 0:
            raise ValueError("这株灵植尚未形成可收获的药性")
        plant = self._spirit_field_rules()["plants"][plot["plant_id"]]
        harvested = self._add_harvested_plant(game.player, plot["plant_id"], float(plot["growth_years"]))
        game.player.spirit_field["plots"].remove(plot)
        rounded_years = int(harvested.plant_years or 10)
        exp_gain = max(4, min(120, round(5 + math.log10(max(10, rounded_years)) * 15)))
        self._grant_art_experience(game.player, "alchemy", exp_gain)
        game.history.append(HistoryRecord(
            "SYS_SPIRIT_FIELD_HARVEST", 1, game.player.age, "采收灵植", plot_id, "harvested",
            f"你采收生长 {plot['growth_years']:.1f} 年的{plant['name']}，按数量级向下记作 {rounded_years:,} 年，品质 {harvested.plant_quality:.0%}。",
            {"item_id":harvested.id, "alchemy_experience":exp_gain}, ["system", "spirit_field", "art:alchemy"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def use_harvested_plant(self, game_id: str, item_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        item = next((row for row in player.inventory if row.id == item_id and row.quantity > 0), None)
        if not item or not item.plant_id:
            raise ValueError("这不是可直接使用的灵植")
        plant = self._spirit_field_rules()["plants"].get(item.plant_id, {})
        years = int(item.plant_years or 0)
        if item.plant_id == "mystic_heaven_vine" and years >= int(plant.get("use_years", 10000)):
            remove_item(player, item_id)
            add_item(player, "mystic_heaven_sword")
            result = "mystic_sword"
            summary = "你以万年枯荣藤祭炼本命灵根，藤心化作一柄枯荣天剑。"
        elif item.plant_id == "nebula_manjushaka" and years >= int(plant.get("use_years", 5000)):
            remove_item(player, item_id)
            reduction = float(plant.get("thunder_reduction", 0.10))
            player.next_thunder_damage_reduction = max(player.next_thunder_damage_reduction, reduction)
            result = "thunder_guard"
            summary = f"你炼化五千年以上的渡劫花，下次三千年雷劫伤害降低 {reduction:.0%}。"
        else:
            raise ValueError("这株灵植尚未达到可使用年份，或其效果为持有生效")
        game.history.append(HistoryRecord(
            "SYS_USE_SPIRIT_PLANT", 1, player.age, "灵植造化", item_id, result, summary,
            {"plant_id":item.plant_id, "years":years}, ["system", "spirit_plant"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def sell_spirit_plant(self, game_id: str, item_id: str, *, black_market: bool = False) -> dict[str, Any]:
        game = self._load(game_id)
        item = next((row for row in game.player.inventory if row.id == item_id and row.quantity > 0), None)
        value = self._plant_item_value(item) if item else None
        if value is None or item is None:
            raise ValueError("只有采收后的灵植能够在这里出售")
        if black_market:
            self._require_auction_access(game, {"black_market"})
            ratio = float(self._spirit_field_rules()["black_market_sell_ratio"])
            title, venue = "黑市灵植交易", "黑市"
        else:
            if game.pending_event or game.player.realm_index == 0:
                raise ValueError("当前无法进入坊市出售灵植")
            ratio = float(self._spirit_field_rules()["market_sell_ratio"])
            title, venue = "坊市灵植交易", "坊市"
        if not remove_item(game.player, item_id):
            raise ValueError("行囊中没有这株灵植")
        price = max(1, round(value * ratio))
        add_item(game.player, "spirit_stone", price)
        name = item.name
        game.history.append(HistoryRecord(
            "SYS_SPIRIT_PLANT_SELL", 1, game.player.age, title, item_id, "sold",
            f"你在{venue}出售{name}，获得 {price} 枚下品灵石。",
            {"spirit_stone":price, "black_market":black_market}, ["system", venue, "spirit_plant"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
