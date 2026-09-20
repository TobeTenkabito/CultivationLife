from __future__ import annotations

import copy
import math
import random
import re
from typing import Any

from .content_registry import (
    ITEM_CATALOG, MARKET_GOODS, MARKET_SETTINGS, REALMS, TECHNIQUE_CATALOG,
    TECHNIQUE_ELEMENT_NAMES, WORLD_SYSTEMS,
)
from .models import GameState, HistoryRecord, Item, Player
from .runtime import decode_rng, encode_rng, now_iso
from .possession_system import advance_player_age
from .rules import (
    QI_SOURCE_NAMES, acquire_technique, add_item, can_player_practice_technique,
    combat_requirement_display, max_hp, max_mp, remove_item,
)


class EconomySystemMixin:
    """坊市库存与探宝奖励的领域实现；主引擎只负责调用和持久化。"""

    @staticmethod
    def _market_tier(player: Player) -> int:
        if player.world == "celestial":
            return max(9, min(12, player.realm_index))
        if player.world in {"spirit", "true_demon"}:
            return max(5, min(8, player.realm_index))
        return min(5, max(1, player.realm_index))

    @staticmethod
    def _clear_market(game: GameState) -> None:
        game.market_realm_index = None
        game.market_world = None
        game.market_location_id = None
        game.market_age = None
        game.market_offers = []

    @staticmethod
    def _market_offer_group(offer: dict[str, Any]) -> str:
        return (
            "material"
            if offer.get("kind") in {"crafting_material", "formation_material", "formation_supply"}
            else "general"
        )

    def _ensure_market(self, game: GameState, rng: Any) -> bool:
        player = game.player
        if player.realm_index == 0:
            changed = bool(
                game.market_offers or game.market_realm_index is not None
                or game.market_world is not None or game.market_location_id is not None
            )
            self._clear_market(game)
            return changed
        tier = self._market_tier(player)
        location_id = self.maps.normalize_location(player.world, player.location_id)
        current_material_offers = [
            row for row in game.market_offers if self._market_offer_group(row) == "material"
        ]
        if (
            game.market_realm_index == tier and game.market_world == player.world
            and game.market_location_id == location_id
            and game.market_age == player.age and game.market_offers
            and (
                not current_material_offers
                or len(current_material_offers) == int(MARKET_SETTINGS.get("material_offer_count", 6))
            )
        ):
            return False
        same_market = (
            game.market_realm_index == tier and game.market_world == player.world
            and game.market_location_id == location_id
        )
        retained: list[dict[str, Any]] = []
        retained_groups: set[str] = set()
        if same_market:
            # Lock state lives on the existing offer row.  This keeps old saves
            # compatible while allowing exactly one retained item per shelf.
            for old_offer in game.market_offers:
                group = self._market_offer_group(old_offer)
                if (
                    bool(old_offer.get("locked")) and not bool(old_offer.get("sold"))
                    and group not in retained_groups
                ):
                    retained.append(copy.deepcopy(old_offer) | {"locked": True})
                    retained_groups.add(group)
        location_name = self.maps.location(player.world, location_id)["name"]
        market_name = f"{location_name}·{REALMS[tier].name}坊市"
        world_goods = self.maps.localize_goods(MARKET_GOODS, player.world, location_id, "market")
        general_locked = [row for row in retained if self._market_offer_group(row) == "general"]
        material_locked = [row for row in retained if self._market_offer_group(row) == "material"]
        offers: list[dict[str, Any]] = list(general_locked)
        general_count = int(MARKET_SETTINGS["offer_count"])
        fresh_general_count = max(0, general_count - len(general_locked))
        retained_content_ids = {str(row.get("content_id", "")) for row in retained}
        for index in range(fresh_general_count):
            seed_pool = [
                entry for entry in world_goods
                if entry["kind"] == "item" and "seed" in ITEM_CATALOG[entry["content_id"]].tags
                and str(entry["content_id"]) not in retained_content_ids
            ]
            if index == 0 and seed_pool:
                good = rng.choice(seed_pool)
                offer_tier = tier
                rare_next_tier = False
                price = max(1, round(good["price"] * rng.uniform(*MARKET_SETTINGS["price_multiplier"])))
                content = ITEM_CATALOG[good["content_id"]]
                offers.append({
                    "id":f"{player.world}-{location_id}-{player.age}-{tier}-{index}-{good['content_id']}",
                    "kind":"item", "content_id":good["content_id"], "name":content.name,
                    "description":content.description, "element":None, "price":price, "tier":offer_tier,
                    "tier_name":REALMS[offer_tier].name, "market_name":market_name,
                    "world":player.world, "location_id":location_id,
                    "rare_next_tier":False, "sold":False, "locked":False,
                })
                continue
            else:
                tier_cap = 5 if player.world == "human" else 12 if player.world == "celestial" else 8
                rare_next_tier = tier < tier_cap and rng.random() < float(MARKET_SETTINGS["next_tier_chance"])
                offer_tier = tier + 1 if rare_next_tier else tier
                pool = [
                    entry for entry in world_goods
                    if entry["tier"] == offer_tier
                    and str(entry["content_id"]) not in retained_content_ids
                ]
                if not pool:
                    pool = [
                        entry for entry in world_goods
                        if entry["tier"] == tier
                        and str(entry["content_id"]) not in retained_content_ids
                    ]
                    offer_tier = tier
                    rare_next_tier = False
                if not pool:
                    break
                good = rng.choice(pool)
            price = max(1, round(good["price"] * rng.uniform(*MARKET_SETTINGS["price_multiplier"])))
            if good["kind"] == "item":
                content = ITEM_CATALOG[good["content_id"]]
                name, description, element = content.name, content.description, None
            else:
                content = TECHNIQUE_CATALOG[good["content_id"]]
                name = content.name
                source_display = "、".join(
                    QI_SOURCE_NAMES[source] + (f" {weight:.0%}" if len(content.sources) > 1 else "")
                    for source, weight in content.sources.items()
                )
                description = (
                    f"{source_display} · 战斗门槛 {combat_requirement_display(content.combat_requirements)}；"
                    f"{TECHNIQUE_ELEMENT_NAMES[content.element]}功法；机缘 +{content.opportunity_bonus:.0%}，"
                    f"HP +{content.hp_bonus:.0%}，MP +{content.mp_bonus:.0%}，战力 +{content.combat_bonus:.0f}。"
                )
                if content.category == "transformation":
                    description += (
                        f" 变身容量 {content.transformation_capacity}，"
                        f"同时启用 {content.transformation_space} 个形态。"
                    )
                element = content.element
            offers.append({
                "id":f"{player.world}-{location_id}-{player.age}-{tier}-{index}-{good['content_id']}",
                "kind":good["kind"], "content_id":good["content_id"], "name":name,
                "description":description, "element":element, "price":price, "tier":offer_tier,
                "tier_name":REALMS[offer_tier].name, "market_name":market_name,
                "world":player.world, "location_id":location_id,
                "rare_next_tier":rare_next_tier, "sold":False, "locked":False,
            })
        material_candidates: list[dict[str, Any]] = []
        self._append_crafting_market_offers(
            game, rng, material_candidates, tier=tier, market_name=market_name, location_id=location_id,
        )
        self._append_formation_market_offers(
            game, rng, material_candidates, tier=tier, market_name=market_name, location_id=location_id,
        )
        for offer in material_candidates:
            offer["locked"] = False
        material_count = int(MARKET_SETTINGS.get("material_offer_count", 6))
        fresh_material_count = max(0, material_count - len(material_locked))
        locked_is_crafting = bool(material_locked and material_locked[0].get("kind") == "crafting_material")
        crafting_target = max(0, 3 - int(locked_is_crafting))
        formation_target = max(0, fresh_material_count - crafting_target)
        crafting_pool = [row for row in material_candidates if row.get("kind") == "crafting_material"]
        formation_materials = [row for row in material_candidates if row.get("kind") == "formation_material"]
        formation_supplies = [row for row in material_candidates if row.get("kind") == "formation_supply"]
        selected_materials = crafting_pool[:crafting_target]
        supply_count = min(1, formation_target, len(formation_supplies))
        selected_materials.extend(formation_materials[:max(0, formation_target - supply_count)])
        selected_materials.extend(formation_supplies[:supply_count])
        if len(selected_materials) < fresh_material_count:
            selected_ids = {row["id"] for row in selected_materials}
            selected_materials.extend(
                row for row in material_candidates
                if row["id"] not in selected_ids
            )
        offers.extend(material_locked)
        offers.extend(selected_materials[:fresh_material_count])
        game.market_realm_index = tier
        game.market_world = player.world
        game.market_location_id = location_id
        game.market_age = player.age
        game.market_offers = offers
        return True

    def _public_market(self, game: GameState) -> dict[str, Any]:
        player = game.player
        stones = next((item.quantity for item in player.inventory if item.id == "spirit_stone"), 0)
        if player.realm_index == 0:
            return {"available":False, "spirit_stones":stones, "offers":[]}
        location_id = self.maps.normalize_location(player.world, player.location_id)
        offers = []
        crafting_offers = []
        formation_offers = []
        for offer in game.market_offers:
            if offer.get("world", "human") != player.world or offer.get("location_id", location_id) != location_id:
                continue
            shown = dict(offer)
            shown["locked"] = bool(offer.get("locked", False))
            shown["market_group"] = self._market_offer_group(offer)
            shown["known"] = bool(
                offer["kind"] == "technique"
                and any(entry.id == offer["content_id"] for entry in player.known_techniques)
            )
            # Known techniques remain purchasable: every later copy becomes a
            # stackable inheritance manual used by the explicit upgrade action.
            shown["owned"] = False
            shown["compatible"] = (
                offer["kind"] != "technique"
                or can_player_practice_technique(player, TECHNIQUE_CATALOG[offer["content_id"]].element)
            )
            if offer.get("kind") == "crafting_material":
                crafting_offers.append(shown)
            elif offer.get("kind") in {"formation_material", "formation_supply"}:
                formation_offers.append(shown)
            else:
                offers.append(shown)
        location_name = self.maps.location(player.world, location_id)["name"]
        return {
            "available":True, "name":f"{location_name}·{REALMS[self._market_tier(player)].name}坊市",
            "realm_index":self._market_tier(player), "world":player.world,
            "location_id":location_id, "location_name":location_name,
            "spirit_stones":stones, "offers":offers, "crafting_material_offers":crafting_offers,
            "formation_material_offers":formation_offers,
            "material_offers":[*crafting_offers, *formation_offers],
            "general_offer_limit":int(MARKET_SETTINGS["offer_count"]),
            "material_offer_limit":int(MARKET_SETTINGS.get("material_offer_count", 6)),
            "sellable_plants":[
                {"id":item.id, "name":item.name, "quantity":item.quantity,
                 "price":max(1, round(int(self._plant_item_value(item) or 0) * float(self._spirit_field_rules()["market_sell_ratio"]))) }
                for item in player.inventory if self._plant_item_value(item) is not None and item.quantity > 0
            ],
            "next_tier_chance":float(MARKET_SETTINGS["next_tier_chance"]),
        }

    def toggle_market_offer_lock(self, game_id: str, offer_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法锁定坊市货物")
        location_id = self.maps.normalize_location(game.player.world, game.player.location_id)
        offer = next((entry for entry in game.market_offers if entry.get("id") == offer_id), None)
        if (
            not offer or offer.get("sold") or offer.get("world", "human") != game.player.world
            or offer.get("location_id", location_id) != location_id
        ):
            raise ValueError("该货物已经售出或不在当前坊市")
        group = self._market_offer_group(offer)
        locking = not bool(offer.get("locked"))
        if locking:
            for row in game.market_offers:
                if self._market_offer_group(row) == group:
                    row["locked"] = False
        offer["locked"] = locking
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    @staticmethod
    def _auction_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS["auction_system"]

    @staticmethod
    def _auction_rng(game: GameState, purpose: str) -> random.Random:
        """Use an isolated deterministic stream so auctions do not perturb story/combat RNG."""
        state = game.auction_state
        step = int(state.get("rng_step", 0)) if state else 0
        if state:
            state["rng_step"] = step + 1
        identity = state.get("id", f"pending-{game.auction_sequence}") if state else f"pending-{game.auction_sequence}"
        return random.Random(f"{game.seed}:auction:{identity}:{purpose}:{game.player.age}:{step}")

    @staticmethod
    def _spirit_stones(player: Player) -> int:
        return next((int(item.quantity) for item in player.inventory if item.id == "spirit_stone"), 0)

    @staticmethod
    def _spirit_field_rules() -> dict[str, Any]:
        return WORLD_SYSTEMS["spirit_field"]

    @staticmethod
    def _art_names() -> dict[str, str]:
        return {
            "alchemy":"炼丹", "refining":"炼器", "formation":"阵法",
            "talisman":"制符", "spirit_control":"御灵",
        }

    def _grant_art_experience(self, player: Player, art_id: str, amount: float) -> None:
        if art_id in self._art_names() and amount > 0:
            if art_id in {"alchemy"}:
                amount *= 1 + max(0.0, float(player.sage_effects.get("field_alchemy_multiplier", 0.0)))
            if art_id in {"refining", "formation"}:
                amount *= 1 + max(0.0, float(player.sage_effects.get("crafting_formation_multiplier", 0.0)))
            amount *= 1 + max(0.0, float(player.sage_effects.get("art_experience_multiplier", 0.0)))
            player.art_experience[art_id] = float(player.art_experience.get(art_id, 0.0)) + float(amount)

    def _public_art_skills(self, player: Player) -> list[dict[str, Any]]:
        base = float(self._spirit_field_rules()["art_experience_base"])
        result = []
        for art_id, name in self._art_names().items():
            experience = max(0.0, float(player.art_experience.get(art_id, 0.0)))
            level = int(math.sqrt(experience / base))
            current_threshold = base * level * level
            next_threshold = base * (level + 1) * (level + 1)
            result.append({
                "id":art_id, "name":name, "level":level, "experience":round(experience, 1),
                "level_experience":round(experience - current_threshold, 1),
                "next_level_experience":round(next_threshold - current_threshold, 1),
            })
        return result

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
            if "pill" in item.tags and item.id not in alchemy_targets:
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

    def refine_pill(self, game_id: str, target_item_id: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or not player.alive or player.imprisonment:
            raise ValueError("当前状态无法开炉炼丹")
        target = ITEM_CATALOG.get(target_item_id)
        if not target or "pill" not in target.tags:
            raise ValueError("目标必须是一种可炼制丹药")
        requested: dict[str, int] = {}
        for row in materials or []:
            item_id = str(row.get("item_id", ""))
            quantity = max(0, int(row.get("quantity", 0)))
            if quantity:
                requested[item_id] = requested.get(item_id, 0) + quantity
        if not requested:
            raise ValueError("至少投入一株药材")
        selected: list[tuple[Item, int]] = []
        for item_id, quantity in requested.items():
            item = next((entry for entry in player.inventory if entry.id == item_id), None)
            if not item or "herb" not in item.tags or "seed" in item.tags or item.quantity < quantity:
                raise ValueError("药材数量不足或混入了非药材物品")
            selected.append((item, quantity))
        mp_cost = max(1.0, max_mp(player) * 0.15)
        if player.mp < mp_cost:
            raise ValueError("炼丹需要至少 15% 最大 MP")
        tier = min((int(row["tier"]) for row in MARKET_GOODS if row["kind"] == "item" and row["content_id"] == target_item_id), default=1)
        total = sum(quantity for _, quantity in selected)
        average_quality = sum(float(item.plant_quality or 0.55) * quantity for item, quantity in selected) / total
        alchemy_level = next(row["level"] for row in self._public_art_skills(player) if row["id"] == "alchemy")
        chance = max(0.05, min(0.95,
            0.22 + average_quality * 0.42 + alchemy_level * 0.065
            + math.log2(total + 1) * 0.045 - (tier - 1) * 0.085
        ))
        for item, quantity in selected:
            remove_item(player, item.id, quantity)
        player.mp -= mp_cost
        rng = decode_rng(game.seed, game.rng_state)
        success = rng.random() < chance
        if success:
            add_item(player, target_item_id)
        experience = (8 + tier * 7 + total * 2) * (1.35 if success else 1.0)
        self._grant_art_experience(player, "alchemy", experience)
        summary = (
            f"你投入 {total} 株药材炼成{target.name}，成功率 {chance:.0%}，炼丹经验 +{experience:.0f}。"
            if success else
            f"你投入 {total} 株药材尝试炼制{target.name}，炉火失衡而失败（成功率 {chance:.0%}），炼丹经验 +{experience:.0f}。"
        )
        game.history.append(HistoryRecord(
            "SYS_ALCHEMY", 1, player.age, "开炉炼丹", target_item_id, "success" if success else "failed",
            summary, {"chance":round(chance, 4), "materials":requested, "mp":-round(mp_cost, 1)},
            ["system", "alchemy", "art:alchemy"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
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

    @staticmethod
    def _catalog_price(kind: str, content_id: str) -> int:
        prices = sorted(
            int(row["price"]) for row in MARKET_GOODS
            if row["kind"] == kind and row["content_id"] == content_id
        )
        if prices:
            return prices[len(prices) // 2]
        if kind == "technique" and content_id in TECHNIQUE_CATALOG:
            technique = TECHNIQUE_CATALOG[content_id]
            return max(10, round(technique.combat_bonus * 0.35 + technique.grade * 20))
        item = ITEM_CATALOG.get(content_id)
        if item:
            return max(5, round(
                item.combat_bonus * 0.25 + item.hp_bonus * 0.12 + item.mp_bonus * 0.12
                + item.opportunity_bonus * 500 + 5
            ))
        return 5

    @staticmethod
    def _auction_content(kind: str, content_id: str) -> tuple[str, str]:
        if kind == "technique":
            content = TECHNIQUE_CATALOG[content_id]
            return content.name, f"{content.grade}阶功法；战斗力 +{content.combat_bonus:.0f}"
        content = ITEM_CATALOG[content_id]
        return content.name, content.description

    def _auction_location_matches(self, game: GameState) -> bool:
        state = game.auction_state
        return bool(
            state and state.get("world") == game.player.world
            and state.get("location_id") == self.maps.normalize_location(game.player.world, game.player.location_id)
        )

    def _require_auction_access(self, game: GameState, statuses: set[str]) -> dict[str, Any]:
        if not game.player.alive or game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法参加交易集会")
        state = game.auction_state
        if state.get("status") not in statuses:
            raise ValueError("当前没有可参与的拍卖或黑市")
        if not self._auction_location_matches(game):
            raise ValueError(f"交易集会位于{state.get('location_name', '另一处地图')}，你尚未抵达")
        return state

    def _schedule_auction(self, game: GameState, rng: Any) -> None:
        locations = list(self.maps.worlds[game.player.world]["locations"])
        location = rng.choice(locations)
        game.auction_sequence += 1
        notice = int(self._auction_rules()["notice_actions"])
        game.auction_state = {
            "id":f"auction-{game.auction_sequence}", "status":"scheduled",
            "world":game.player.world, "location_id":location["id"], "location_name":location["name"],
            "announced_age":game.player.age, "actions_until_open":notice,
            "round":0, "lots":[], "consignments":[], "attendees":[], "black_market_results":[],
        }
        game.history.append(HistoryRecord(
            "SYS_AUCTION_NOTICE", 1, game.player.age, "拍卖会预告", location["id"], "scheduled",
            f"{location['name']}将在两个有时间消耗的操作节点后举行拍卖会。主办方已提前放出消息，受地图境界禁制阻隔者仍无法强行入场。",
            {"location_id":location["id"], "actions_until_open":notice},
            ["system", "auction", f"world:{game.player.world}"],
        ))

    def _auction_goods_pool(self, world: str) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in MARKET_GOODS:
            if str(row.get("world", "human")) != world:
                continue
            key = (str(row["kind"]), str(row["content_id"]))
            current = unique.get(key)
            if current is None or int(row["tier"]) > int(current["tier"]):
                unique[key] = dict(row)
        return list(unique.values())

    def _is_world_market_good(self, world: str, kind: str, content_id: str) -> bool:
        if any(
            str(row.get("world", "human")) == world
            and str(row.get("kind")) == kind
            and str(row.get("content_id")) == content_id
            for row in MARKET_GOODS
        ):
            return True
        if kind == "crafting_material":
            return any(
                str(row.get("world")) == world and str(row.get("id")) == content_id
                for row in self._crafting_material_defs().values()
            )
        if kind == "formation_material":
            return any(
                str(row.get("world")) == world and str(row.get("id")) == content_id
                for row in self._formation_material_defs().values()
            )
        if kind == "formation_supply":
            return any(
                str(row.get("world")) == world and str(row.get("id")) == content_id
                for row in self._formation_maintenance_defs().values()
            )
        return False

    def _auction_good_weight(self, world: str, tier: int) -> float:
        weight = 1.0 / max(1, tier)
        if world in {"human", "demon"}:
            if tier == 5:
                weight *= float(self._auction_rules()["lower_world_tier_five_weight"])
            elif tier > 5:
                weight *= float(self._auction_rules()["lower_world_higher_tier_weight"])
        return weight

    def _make_auction_lot(
        self, game: GameState, rng: Any, *, kind: str, content_id: str, tier: int,
        start_price: int, seller: str = "npc", suffix: str, rated_price: int | None = None,
    ) -> dict[str, Any]:
        name, description = self._auction_content(kind, content_id)
        bidder_names = list(self._auction_rules()["bidder_aliases"])
        rated_price = int(rated_price or self._catalog_price(kind, content_id))
        return {
            "id":f"{game.auction_state['id']}-{suffix}", "kind":kind, "content_id":content_id,
            "name":name, "description":description, "tier":tier,
            "tier_name":REALMS[max(0, min(len(REALMS) - 1, tier))].name,
            "start_price":int(start_price), "current_bid":int(start_price),
            "rated_price":rated_price,
            "maximum_bid":max(1, math.floor(rated_price * float(self._auction_rules()["consignment_max_price_ratio"]))),
            "current_bidder":"npc", "current_bidder_name":rng.choice(bidder_names),
            "seller":seller, "closed":False,
        }

    def _open_auction(self, game: GameState, rng: Any) -> None:
        state = game.auction_state
        pool = self._auction_goods_pool(game.player.world)
        lots: list[dict[str, Any]] = []
        count = min(int(self._auction_rules()["npc_lot_count"]), len(pool))
        for index in range(count):
            weights = [self._auction_good_weight(game.player.world, int(row["tier"])) for row in pool]
            selected = rng.choices(pool, weights=weights, k=1)[0]
            pool.remove(selected)
            base_price = self._catalog_price(str(selected["kind"]), str(selected["content_id"]))
            start = max(1, round(base_price * rng.uniform(*self._auction_rules()["starting_price_multiplier"])))
            lots.append(self._make_auction_lot(
                game, rng, kind=str(selected["kind"]), content_id=str(selected["content_id"]),
                tier=int(selected["tier"]), start_price=start, suffix=f"npc-{index}",
            ))
        for index, consignment in enumerate(state.get("consignments", [])):
            if consignment.get("kind") == "crafted_artifact" and isinstance(consignment.get("artifact"), dict):
                lots.append(self._make_crafted_auction_lot(game, rng, consignment, f"player-{index}"))
            else:
                lots.append(self._make_auction_lot(
                    game, rng, kind="item", content_id=str(consignment["content_id"]),
                    tier=int(consignment.get("tier", 1)), start_price=int(consignment["start_price"]),
                    seller="player", suffix=f"player-{index}", rated_price=int(consignment.get("rated_price", 0) or 0),
                ))
        candidates = [
            npc for npc in self._all_world_npcs(game)
            if npc.alive and npc.world == game.player.world
        ]
        rng.shuffle(candidates)
        trade_pool = self._auction_goods_pool(game.player.world)
        trade_count = int(self._auction_rules()["private_trade_offer_count"])
        state.update({
            "status":"open", "round":0, "lots":lots,
            "player_alias":state.get("player_alias") or self._auction_rules()["player_aliases"][0],
            "bid_logs":[],
            "attendees":[{
                "id":npc.id, "name":npc.name, "title":npc.title,
                "realm_name":self._npc_realm_name(npc), "affinity":round(float(npc.affinity or 0), 1),
                "interacted":False, "private_trade_unlocked":False,
                "trade_offers":[{
                    "id":f"private-{npc.id}-{trade_index}", "kind":good["kind"],
                    "content_id":good["content_id"], "name":self._auction_content(good["kind"], good["content_id"])[0],
                    "description":self._auction_content(good["kind"], good["content_id"])[1],
                    "price":max(1, round(self._catalog_price(good["kind"], good["content_id"]) * float(self._auction_rules()["private_trade_buy_multiplier"]))),
                    "sold":False, "bargained":False,
                } for trade_index, good in enumerate(rng.sample(trade_pool, min(trade_count, len(trade_pool))))],
                "sell_bargains":{},
            } for npc in candidates[:4]],
        })
        game.history.append(HistoryRecord(
            "SYS_AUCTION_OPEN", 1, game.player.age, "拍卖会开幕", state["location_id"], "open",
            f"{state['location_name']}拍卖会正式开幕，共有 {len(lots)} 件拍品登台。会内竞价与交涉不消耗时间。",
            {"lots":len(lots)}, ["system", "auction", f"world:{game.player.world}"],
        ))

    def _advance_auction_clock(self, game: GameState, rng: Any) -> None:
        rng = self._auction_rng(game, "clock")
        state = game.auction_state
        if not state:
            if game.player.realm_index > 0 and rng.random() < float(self._auction_rules()["trigger_chance_per_action"]):
                self._schedule_auction(game, rng)
            return
        status = state.get("status")
        if state.get("world") != game.player.world and status != "cooldown":
            self._cancel_auction_for_world_change(game)
            return
        if status == "scheduled":
            state["actions_until_open"] = max(0, int(state.get("actions_until_open", 1)) - 1)
            if state["actions_until_open"] == 0:
                self._open_auction(game, rng)
        elif status == "open":
            self._finish_auction(game, rng, reason="你选择继续消耗时间，拍卖会在此期间完成了结拍")
        elif status == "black_market":
            game.auction_state = {"status":"cooldown", "actions_remaining":int(self._auction_rules()["cooldown_actions"])}
        elif status == "cooldown":
            state["actions_remaining"] = max(0, int(state.get("actions_remaining", 1)) - 1)
            if state["actions_remaining"] == 0:
                game.auction_state = {}

    def _cancel_auction_for_world_change(self, game: GameState) -> None:
        state = game.auction_state
        if not state or state.get("status") == "cooldown":
            return
        # Only an unfinished auction has frozen bids or unsold consignments. Once the
        # black market opens, lots have already been delivered and sellers paid.
        if state.get("status") in {"scheduled", "open"}:
            for lot in state.get("lots", []):
                if lot.get("current_bidder") == "player":
                    add_item(game.player, "spirit_stone", int(lot.get("current_bid", 0)))
            for consignment in state.get("consignments", []):
                if consignment.get("kind") == "crafted_artifact" and isinstance(consignment.get("artifact"), dict):
                    from .crafting_system import store_crafted_artifact
                    store_crafted_artifact(game.player, copy.deepcopy(consignment["artifact"]))
                else:
                    add_item(game.player, str(consignment["content_id"]))
        game.auction_state = {
            "status":"cooldown", "actions_remaining":int(self._auction_rules()["cooldown_actions"]),
        }

    def _auction_increment(self, lot: dict[str, Any]) -> int:
        rules = self._auction_rules()
        return max(
            1,
            math.ceil(float(lot["start_price"]) * float(rules["minimum_increment_start_ratio"])),
            math.ceil(float(lot["current_bid"]) * float(rules["minimum_increment_current_ratio"])),
        )

    def _auction_bid_ceiling(self, lot: dict[str, Any]) -> int:
        rated = int(lot.get("rated_price", 0) or self._catalog_price(str(lot["kind"]), str(lot["content_id"])))
        return max(1, math.floor(rated * float(self._auction_rules()["consignment_max_price_ratio"])))

    def consign_auction_item(self, game_id: str, item_id: str, start_price: int = 0) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"scheduled", "open"})
        item = next((entry for entry in game.player.inventory if entry.id == item_id and entry.quantity > 0), None)
        if not item or item_id == "spirit_stone":
            raise ValueError("该物品无法送拍")
        if item.crafted_artifact_id:
            raise ValueError("组合炼器法宝请使用包裹内该物品自己的寄拍按钮")
        base_price = self._plant_item_value(item) or self._catalog_price("item", item_id)
        rules = self._auction_rules()
        minimum = max(1, math.ceil(base_price * float(rules["consignment_min_price_ratio"])))
        maximum = max(minimum, math.floor(base_price * float(rules["consignment_max_price_ratio"])))
        start_price = int(start_price or round(base_price * 0.8))
        if not minimum <= start_price <= maximum:
            raise ValueError(f"起拍价须在额定价的25%至5倍之间（{minimum}—{maximum}灵石）")
        listing_fee = max(1, math.ceil(base_price * float(rules["consignment_listing_fee_ratio"])))
        if not remove_item(game.player, "spirit_stone", listing_fee):
            raise ValueError(f"上拍前须支付 {listing_fee} 枚灵石占位费")
        if not remove_item(game.player, item_id):
            add_item(game.player, "spirit_stone", listing_fee)
            raise ValueError("行囊中没有该物品")
        tier = max((int(row["tier"]) for row in MARKET_GOODS if row["kind"] == "item" and row["content_id"] == item_id), default=1)
        consignment = {
            "content_id":item_id, "start_price":start_price, "tier":tier,
            "rated_price":base_price, "listing_fee":listing_fee,
        }
        state.setdefault("consignments", []).append(consignment)
        if state["status"] == "open":
            rng = self._auction_rng(game, "consignment")
            state["lots"].append(self._make_auction_lot(
                game, rng, kind="item", content_id=item_id, tier=tier, start_price=start_price,
                seller="player", suffix=f"player-{len(state['consignments']) - 1}", rated_price=base_price,
            ))
        game.history.append(HistoryRecord(
            "SYS_AUCTION_CONSIGN", 1, game.player.age, "寄送拍品", item_id, "consigned",
            f"你支付 {listing_fee} 枚灵石占位费，将{item.name}以 {start_price} 枚灵石起拍；成交服务费另计。",
            {"start_price":start_price, "rated_price":base_price, "listing_fee":-listing_fee},
            ["system", "auction"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def place_auction_bid(self, game_id: str, lot_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        lot = next((row for row in state.get("lots", []) if row["id"] == lot_id and not row.get("closed")), None)
        if not lot:
            raise ValueError("该拍品已经结拍或不存在")
        if lot.get("seller") == "player":
            raise ValueError("不能竞拍自己送拍的物品")
        if not self._is_world_market_good(
            game.player.world, str(lot.get("kind", "")), str(lot.get("content_id", "")),
        ):
            raise ValueError("该拍品不属于当前世界，已被交易会撤下")
        if lot.get("current_bidder") == "player":
            raise ValueError("你已经是当前最高出价者")
        bid = int(lot["current_bid"]) + self._auction_increment(lot)
        if bid > self._auction_bid_ceiling(lot):
            raise ValueError("该拍品已达到额定价五倍的竞价上限")
        if not remove_item(game.player, "spirit_stone", bid):
            raise ValueError(f"本次加价后需要冻结 {bid} 枚下品灵石")
        alias = str(state.get("player_alias") or self._auction_rules()["player_aliases"][0])
        lot.update({"current_bid":bid, "current_bidder":"player", "current_bidder_name":alias})
        state.setdefault("bid_logs", []).append(f"{alias}为{lot['name']}出价 {bid} 灵石。")
        state["bid_logs"] = state["bid_logs"][-18:]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def advance_auction_round(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        rng = self._auction_rng(game, "round")
        bidder_names = list(self._auction_rules()["bidder_aliases"])
        for lot in state.get("lots", []):
            if lot.get("closed"):
                continue
            increment = self._auction_increment(lot)
            next_bid = int(lot["current_bid"]) + increment
            if next_bid > self._auction_bid_ceiling(lot):
                continue
            if lot.get("current_bidder") == "player":
                if rng.random() < float(self._auction_rules()["npc_outbid_chance"]):
                    add_item(game.player, "spirit_stone", int(lot["current_bid"]))
                    lot.update({
                        "current_bid":next_bid,
                        "current_bidder":"npc", "current_bidder_name":rng.choice(bidder_names),
                    })
                    state.setdefault("bid_logs", []).append(
                        f"{lot['current_bidder_name']}压过{state.get('player_alias', '匿名修士')}，将{lot['name']}抬至 {lot['current_bid']} 灵石。"
                    )
            elif rng.random() < 0.68:
                lot["current_bid"] = next_bid
                lot["current_bidder_name"] = rng.choice(bidder_names)
                state.setdefault("bid_logs", []).append(
                    f"{lot['current_bidder_name']}为{lot['name']}出价 {lot['current_bid']} 灵石。"
                )
        state["bid_logs"] = state.get("bid_logs", [])[-18:]
        state["round"] = int(state.get("round", 0)) + 1
        if state["round"] >= int(self._auction_rules()["auction_rounds"]):
            self._finish_auction(game, rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _grant_auction_content(self, player: Player, kind: str, content_id: str) -> None:
        if kind == "item":
            add_item(player, content_id)
            return
        acquire_technique(player, TECHNIQUE_CATALOG[content_id])

    def _finish_auction(self, game: GameState, rng: Any, reason: str = "") -> None:
        state = game.auction_state
        purchased: list[str] = []
        sold: list[str] = []
        commission = float(self._auction_rules()["commission_rate"])
        for lot in state.get("lots", []):
            if lot.get("seller") != "player" and not self._is_world_market_good(
                game.player.world, str(lot.get("kind", "")), str(lot.get("content_id", "")),
            ):
                if lot.get("current_bidder") == "player":
                    add_item(game.player, "spirit_stone", int(lot.get("current_bid", 0)))
                lot["closed"] = True
                continue
            old_bid = int(lot.get("current_bid", 0))
            lot["current_bid"] = min(old_bid, self._auction_bid_ceiling(lot))
            if lot.get("current_bidder") == "player" and old_bid > int(lot["current_bid"]):
                add_item(game.player, "spirit_stone", old_bid - int(lot["current_bid"]))
            lot["closed"] = True
            if lot.get("current_bidder") == "player":
                self._grant_auction_content(game.player, str(lot["kind"]), str(lot["content_id"]))
                purchased.append(f"{lot['name']}（{lot['current_bid']}灵石）")
            if lot.get("seller") == "player":
                net = max(0, math.floor(int(lot["current_bid"]) * (1 - commission)))
                add_item(game.player, "spirit_stone", net)
                lot["seller_net"] = net
                sold.append(f"{lot['name']}（实得{net}灵石）")
        state.update({"status":"black_market", "black_market_results":[]})
        summary = reason or "拍卖会完成全部结拍"
        if purchased:
            summary += "；你拍得" + "、".join(purchased)
        if sold:
            summary += "；寄拍成交后扣除30%手续费，你获得" + "、".join(sold)
        summary += "。散场修士随即转入同地图黑市。"
        game.history.append(HistoryRecord(
            "SYS_AUCTION_FINISH", 1, game.player.age, "拍卖结清与黑市开启", state.get("location_id"),
            "black_market", summary, {"purchased":purchased, "sold":sold},
            ["system", "auction", "black_market", f"world:{game.player.world}"],
        ))

    def negotiate_at_auction(self, game_id: str, npc_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        attendee = next((row for row in state.get("attendees", []) if row["id"] == npc_id), None)
        if not attendee or attendee.get("interacted"):
            raise ValueError("本场已经没有新的交涉机会")
        npc = self._find_npc(game, npc_id)
        if not npc or not npc.alive:
            raise ValueError("对方已经离开拍卖会")
        rng = self._auction_rng(game, "negotiate")
        affinity_range = self._auction_rules()["negotiation_affinity_gain"]
        change = rng.randint(int(affinity_range[0]), int(affinity_range[1]))
        change = self._sage_affinity_gain(game.player, change)
        npc.affinity = float(npc.affinity or 0) + change
        attendee.update({
            "interacted":True, "affinity":round(npc.affinity, 1), "private_trade_unlocked":True,
        })
        game.history.append(HistoryRecord(
            "SYS_AUCTION_NEGOTIATE", 1, game.player.age, "拍卖场交涉", npc_id, "negotiated",
            f"你借拍卖间隙与{npc.name}交换消息，好感 +{change}。", {"affinity":change},
            ["system", "auction", "relationship", f"world:{game.player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def choose_auction_identity(self, game_id: str, alias: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"open"})
        if alias not in self._auction_rules()["player_aliases"]:
            raise ValueError("拍卖行不承认这个匿名身份")
        state["player_alias"] = alias
        state.setdefault("bid_logs", []).append(f"你以“{alias}”的身份入席。")
        state["bid_logs"] = state["bid_logs"][-18:]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _private_trade_attendee(self, game: GameState, npc_id: str) -> dict[str, Any]:
        state = self._require_auction_access(game, {"open"})
        attendee = next((row for row in state.get("attendees", []) if row["id"] == npc_id), None)
        if not attendee or not attendee.get("private_trade_unlocked"):
            raise ValueError("须先与对方交谈，取得信任后才能私下交易")
        return attendee

    def buy_private_trade_item(self, game_id: str, npc_id: str, offer_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        attendee = self._private_trade_attendee(game, npc_id)
        offer = next((row for row in attendee.get("trade_offers", []) if row["id"] == offer_id and not row.get("sold")), None)
        if not offer:
            raise ValueError("这件私人物品已经易主")
        if not self._is_world_market_good(
            game.player.world, str(offer.get("kind", "")), str(offer.get("content_id", "")),
        ):
            raise ValueError("这件货物不属于当前世界的流通范围")
        if not remove_item(game.player, "spirit_stone", int(offer["price"])):
            raise ValueError(f"私下交易需要 {offer['price']} 枚下品灵石")
        self._grant_auction_content(game.player, str(offer["kind"]), str(offer["content_id"]))
        offer["sold"] = True
        npc = self._find_npc(game, npc_id)
        affinity_range = self._auction_rules()["private_trade_buy_affinity_gain"]
        rng = self._auction_rng(game, f"private-buy:{npc_id}:{offer_id}")
        affinity_gain = rng.randint(int(affinity_range[0]), int(affinity_range[1]))
        if npc:
            affinity_gain = self._sage_affinity_gain(game.player, affinity_gain)
            npc.affinity = float(npc.affinity or 0) + affinity_gain
            attendee["affinity"] = round(npc.affinity, 1)
        else:
            attendee["affinity"] = round(float(attendee.get("affinity", 0)) + affinity_gain, 1)
        game.history.append(HistoryRecord(
            "SYS_AUCTION_PRIVATE_BUY", 1, game.player.age, "拍卖场私下交易", npc_id, "purchased",
            f"你以匿名身份向{attendee['name']}支付 {offer['price']} 枚灵石，购得{offer['name']}，好感 +{affinity_gain}。",
            {"content_id":offer["content_id"], "spirit_stone":-int(offer["price"]), "affinity":affinity_gain},
            ["system", "auction", "private_trade", "relationship"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def sell_private_trade_item(self, game_id: str, npc_id: str, item_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        attendee = self._private_trade_attendee(game, npc_id)
        item = next((row for row in game.player.inventory if row.id == item_id and row.quantity > 0), None)
        if not item or item_id == "spirit_stone":
            raise ValueError("这件物品无法私下出售")
        if item.crafted_artifact_id:
            raise ValueError("组合炼器法宝须按其唯一实例价值出售或寄拍")
        base = self._plant_item_value(item) or self._catalog_price("item", item_id)
        multiplier = float(self._auction_rules()["private_trade_sell_multiplier"])
        multiplier *= float(attendee.get("sell_bargains", {}).get(item_id, 1.0))
        price = max(1, round(base * multiplier))
        if not remove_item(game.player, item_id):
            raise ValueError("行囊中已没有这件物品")
        add_item(game.player, "spirit_stone", price)
        game.history.append(HistoryRecord(
            "SYS_AUCTION_PRIVATE_SELL", 1, game.player.age, "拍卖场私下交易", npc_id, "sold",
            f"{attendee['name']}私下收购{item.name}，向你支付 {price} 枚灵石。",
            {"content_id":item_id, "spirit_stone":price}, ["system", "auction", "private_trade"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def bargain_private_trade(self, game_id: str, npc_id: str, side: str, asset_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        attendee = self._private_trade_attendee(game, npc_id)
        rng = self._auction_rng(game, f"bargain:{npc_id}:{side}:{asset_id}")
        rules = self._auction_rules()
        chance = min(0.85, float(rules["bargain_success_base"]) + max(0.0, float(attendee.get("affinity", 0))) * float(rules["bargain_affinity_factor"]))
        success = rng.random() < chance
        if side == "buy":
            offer = next((row for row in attendee.get("trade_offers", []) if row["id"] == asset_id and not row.get("sold")), None)
            if not offer or offer.get("bargained"):
                raise ValueError("这件商品已经没有继续还价的余地")
            offer["bargained"] = True
            if success:
                discount = rng.uniform(*rules["bargain_buy_discount"])
                offer["price"] = max(1, round(int(offer["price"]) * (1 - discount)))
        elif side == "sell":
            item = next((row for row in game.player.inventory if row.id == asset_id and row.quantity > 0), None)
            attempts = attendee.setdefault("sell_bargain_attempts", [])
            if not item or item.crafted_artifact_id or asset_id in attempts:
                raise ValueError("这件物品已经没有继续还价的余地")
            attempts.append(asset_id)
            if success:
                bonus = rng.uniform(*rules["bargain_sell_bonus"])
                attendee.setdefault("sell_bargains", {})[asset_id] = 1 + bonus
        else:
            raise ValueError("未知还价方向")
        state = game.auction_state
        state.setdefault("bid_logs", []).append(
            f"你与{attendee['name']}私下还价，{'对方最终松口' if success else '对方不肯让步'}。"
        )
        state["bid_logs"] = state["bid_logs"][-18:]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def search_black_market(self, game_id: str, pattern: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"black_market"})
        pattern = str(pattern).strip()
        if not pattern or len(pattern) > 40:
            raise ValueError("请输入1至40个字符的检索表达式")
        try:
            matcher = re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"正则表达式无效：{error}") from error
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in MARKET_GOODS:
            if row.get("world", "human") == game.player.world:
                unique[(str(row["kind"]), str(row["content_id"]))] = dict(row)
        # Material stalls are generated outside MARKET_GOODS because each
        # crafting/formation piece is a real unique instance. Black-market
        # search still exposes the complete world-local catalog and freezes
        # the generated instance in the saved search result until purchase.
        material_rng = random.Random(
            f"{game.seed}:black-market-material:{state.get('id', '')}:{pattern}"
        )
        material_rows: list[dict[str, Any]] = []
        for definition in self._crafting_material_defs().values():
            if str(definition.get("world")) != game.player.world:
                continue
            from .crafting_system import make_crafting_material_instance
            instance = make_crafting_material_instance(
                definition, material_rng, source="黑市购得", origin_world=game.player.world,
            )
            material_rows.append({
                "kind":"crafting_material", "content_id":str(definition["id"]),
                "name":str(definition["name"]),
                "description":f"炼器材料 · {instance['state']} · 材料价值 {int(instance['material_value']):,}",
                "tier":int(definition.get("tier", 1)),
                "base_price":int(instance["material_value"]), "material_instance":instance,
            })
        for definition in self._formation_material_defs().values():
            if str(definition.get("world")) != game.player.world:
                continue
            from .formation_system import NATURE_NAMES, make_formation_material_instance
            instance = make_formation_material_instance(
                definition, source="黑市购得", origin_world=game.player.world,
            )
            material_rows.append({
                "kind":"formation_material", "content_id":str(definition["id"]),
                "name":str(definition["name"]),
                "description":f"阵法材料 · {NATURE_NAMES.get(str(definition.get('nature')), definition.get('nature'))}性 · 固有阵值 {float(definition.get('formation_value', 0)):g}",
                "tier":int(definition.get("tier", 1)),
                "base_price":int(definition.get("base_value", 1)), "formation_material_instance":instance,
            })
        for definition in self._formation_maintenance_defs().values():
            if str(definition.get("world")) != game.player.world:
                continue
            material_rows.append({
                "kind":"formation_supply", "content_id":str(definition["id"]),
                "name":str(definition["name"]),
                "description":f"修阵材料 · 恢复 {float(definition.get('repair_value', 0)):g}% 镇地阵完整度",
                "tier":int(definition.get("tier", 1)),
                "base_price":int(definition.get("base_value", 1)),
            })
        results = []
        multiplier = float(self._auction_rules()["black_market_buy_multiplier"])
        for (kind, content_id), row in unique.items():
            name, description = self._auction_content(kind, content_id)
            if not matcher.search(f"{name} {description}"):
                continue
            results.append({
                "id":f"black-{kind}-{content_id}", "kind":kind, "content_id":content_id,
                "name":name, "description":description, "tier":int(row["tier"]),
                "tier_name":REALMS[int(row["tier"])].name,
                "price":max(1, round(self._catalog_price(kind, content_id) * multiplier)),
            })
        for row in material_rows:
            if not matcher.search(f"{row['name']} {row['description']}"):
                continue
            tier = max(0, min(len(REALMS) - 1, int(row["tier"])))
            results.append({
                **row,
                "id":f"black-{row['kind']}-{row['content_id']}",
                "tier":tier, "tier_name":REALMS[tier].name,
                "price":max(1, round(int(row["base_price"]) * multiplier)),
            })
        results.sort(key=lambda row: (row["tier"], row["name"]))
        state["black_market_results"] = results[:int(self._auction_rules()["black_market_result_limit"])]
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def buy_black_market_item(self, game_id: str, result_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        state = self._require_auction_access(game, {"black_market"})
        result = next((row for row in state.get("black_market_results", []) if row["id"] == result_id), None)
        if not result:
            raise ValueError("请先检索并选择一件黑市商品")
        if not self._is_world_market_good(
            game.player.world, str(result.get("kind", "")), str(result.get("content_id", "")),
        ):
            raise ValueError("这件货物不属于当前世界的流通范围")
        if not remove_item(game.player, "spirit_stone", int(result["price"])):
            raise ValueError(f"需要 {result['price']} 枚下品灵石")
        kind = str(result["kind"])
        if kind == "crafting_material":
            instance = copy.deepcopy(result.get("material_instance"))
            if not isinstance(instance, dict):
                raise ValueError("这份黑市炼器材料已经失去灵性")
            game.player.crafting_materials.append(instance)
        elif kind == "formation_material":
            instance = copy.deepcopy(result.get("formation_material_instance"))
            if not isinstance(instance, dict):
                raise ValueError("这份黑市阵材已经失去阵性")
            game.player.formation_materials.append(instance)
        elif kind == "formation_supply":
            supply_id = str(result["content_id"])
            game.player.formation_repair_supplies[supply_id] = (
                int(game.player.formation_repair_supplies.get(supply_id, 0)) + 1
            )
        else:
            self._grant_auction_content(game.player, kind, str(result["content_id"]))
        game.history.append(HistoryRecord(
            "SYS_BLACK_MARKET_BUY", 1, game.player.age, "黑市补缺", result_id, "purchased",
            f"你以严重溢价支付 {result['price']} 枚灵石，购得{result['name']}。",
            {"spirit_stone":-int(result["price"]), "content_id":result["content_id"]},
            ["system", "black_market", f"world:{game.player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def sell_black_market_asset(self, game_id: str, kind: str, asset_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._require_auction_access(game, {"black_market"})
        ratio = float(self._auction_rules()["black_market_sell_ratio"])
        if kind == "item":
            item = next((row for row in game.player.inventory if row.id == asset_id and row.quantity > 0), None)
            if not item or item.crafted_artifact_id or asset_id == "spirit_stone" or not remove_item(game.player, asset_id):
                raise ValueError("该物品无法在黑市出手")
            name = item.name
            plant_value = self._plant_item_value(item)
            price = max(1, round(
                (plant_value or self._catalog_price("item", asset_id)) * (
                    float(self._spirit_field_rules()["black_market_sell_ratio"])
                    if plant_value is not None else ratio
                )
            ))
        elif kind == "puppet":
            puppet = next((row for row in game.player.puppets if str(row.get("id")) == asset_id), None)
            if not puppet or puppet.get("type") == "living":
                raise ValueError("黑市只接收机关傀儡与炼尸，不接收活傀")
            game.player.puppets.remove(puppet)
            name = str(puppet.get("name", "无名傀儡"))
            price = max(5, round(float(puppet.get("combat_power", 0)) * 0.08))
        else:
            raise ValueError("未知黑市资产类型")
        add_item(game.player, "spirit_stone", price)
        game.history.append(HistoryRecord(
            "SYS_BLACK_MARKET_SELL", 1, game.player.age, "黑市销赃", asset_id, "sold",
            f"你在黑市出手{name}，获得 {price} 枚下品灵石。", {"spirit_stone":price},
            ["system", "black_market", f"world:{game.player.world}"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def leave_black_market(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._require_auction_access(game, {"black_market"})
        game.auction_state = {"status":"cooldown", "actions_remaining":int(self._auction_rules()["cooldown_actions"])}
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_auction(self, game: GameState) -> dict[str, Any]:
        state = game.auction_state
        status = state.get("status")
        if status not in {"scheduled", "open", "black_market"} or state.get("world") != game.player.world:
            return {"available":False, "status":status or "none"}
        at_location = self._auction_location_matches(game)
        lots = []
        for row in state.get("lots", []):
            lot = dict(row)
            lot["rated_price"] = int(row.get("rated_price", 0) or self._catalog_price(str(row["kind"]), str(row["content_id"])))
            lot["maximum_bid"] = self._auction_bid_ceiling(row)
            lot["minimum_increment"] = self._auction_increment(row)
            lots.append(lot)
        inventory = [
            {"id":item.id, "name":item.name, "quantity":item.quantity,
             "rated_price":(rated := self._plant_item_value(item) or self._catalog_price("item", item.id)),
             "minimum_start_price":max(1, math.ceil(rated * float(self._auction_rules()["consignment_min_price_ratio"]))),
             "maximum_start_price":max(1, math.floor(rated * float(self._auction_rules()["consignment_max_price_ratio"]))),
             "listing_fee":max(1, math.ceil(rated * float(self._auction_rules()["consignment_listing_fee_ratio"]))),
             "suggested_start_price":max(1, round(rated * 0.8)),
             "private_base_price":max(1, round((self._plant_item_value(item) or self._catalog_price("item", item.id)) * float(self._auction_rules()["private_trade_sell_multiplier"]))),
             "black_market_price":max(1, round((self._plant_item_value(item) or self._catalog_price("item", item.id)) * (
                 float(self._spirit_field_rules()["black_market_sell_ratio"])
                 if self._plant_item_value(item) is not None else float(self._auction_rules()["black_market_sell_ratio"])
             ))) }
            for item in game.player.inventory
            if item.id != "spirit_stone" and item.quantity > 0 and not item.crafted_artifact_id
        ]
        consignable_inventory = [row for row in inventory if row["id"] in ITEM_CATALOG]
        sellable_puppets = [
            {"id":str(row.get("id")), "name":str(row.get("name", "无名傀儡")),
             "type":str(row.get("type")), "combat_power":round(float(row.get("combat_power", 0)), 1)}
            for row in game.player.puppets if row.get("type") in {"mechanical", "corpse"}
        ]
        return {
            **state, "available":True, "at_location":at_location,
            "spirit_stones":self._spirit_stones(game.player), "lots":lots,
            "consignable_items":consignable_inventory, "black_market_sellable_items":inventory,
            "private_sellable_items":inventory,
            "player_aliases":list(self._auction_rules()["player_aliases"]),
            "black_market_sellable_puppets":sellable_puppets,
            "commission_rate":float(self._auction_rules()["commission_rate"]),
            "listing_fee_rate":float(self._auction_rules()["consignment_listing_fee_ratio"]),
            "max_rounds":int(self._auction_rules()["auction_rounds"]),
            "black_market_buy_multiplier":float(self._auction_rules()["black_market_buy_multiplier"]),
        }

    def _treasure_reward_pool(self, game: GameState, category: str) -> list[dict[str, Any]]:
        player = game.player
        target_tier = max(1, player.realm_index)
        location_id = self.maps.normalize_location(player.world, player.location_id)
        world_goods = [row for row in MARKET_GOODS if int(row["tier"]) <= target_tier]
        if category == "technique":
            eligible = [row for row in world_goods if row["kind"] == "technique"]
        elif category == "pill":
            eligible = [row for row in world_goods if row["kind"] == "item" and "pill" in ITEM_CATALOG[row["content_id"]].tags]
        elif category == "artifact":
            eligible = [
                row for row in world_goods if row["kind"] == "item"
                and "pill" not in ITEM_CATALOG[row["content_id"]].tags
                and ITEM_CATALOG[row["content_id"]].combat_bonus > 0
            ]
        else:
            raise ValueError("未知探宝奖励类别")
        eligible = self.maps.localize_goods(eligible, player.world, location_id, "treasure")
        if not eligible:
            raise ValueError(f"{player.world}界缺少可用的{category}探宝奖励")
        return eligible

    def _treasure_step(self, game: GameState, rng: Any) -> str:
        player = game.player
        resource = "mp" if player.mp > 0 and rng.random() < 0.5 else "hp"
        if resource == "hp":
            cost = round(max_hp(player) * rng.uniform(0.07, 0.15), 1)
            player.hp = max(0, player.hp - cost)
            cost_text = f"HP -{cost:.0f}"
            if player.hp <= 0:
                self._die(game, "探宝时气血耗尽，埋骨荒野", "ACT_TREASURE")
                return f"探宝消耗 {cost_text}，未能生还。"
        else:
            cost = round(min(player.mp, max_mp(player) * rng.uniform(0.10, 0.22)), 1)
            player.mp = max(0, player.mp - cost)
            cost_text = f"MP -{cost:.0f}"
        return f"探宝消耗 {cost_text}，寻得三处灵光各异的遗藏。"

    def _prepare_treasure_reward_event(self, game: GameState, rng: Any) -> dict[str, Any]:
        event = self._instantiate_event(self.events_by_id["EVT_TREASURE_REWARD_SELECT_001"], game, rng)
        rewards: dict[str, dict[str, Any]] = {}
        category_names = {"artifact":"法器", "technique":"功法", "pill":"丹药"}
        for category in ("artifact", "technique", "pill"):
            pool = self._treasure_reward_pool(game, category)
            reward = rng.choices(pool, weights=[max(1, int(row["tier"])) for row in pool], k=1)[0]
            content_id = str(reward["content_id"])
            name = TECHNIQUE_CATALOG[content_id].name if category == "technique" else ITEM_CATALOG[content_id].name
            rewards[category] = {"content_id":content_id, "name":name, "tier":int(reward["tier"])}
        event["runtime"] = {"rewards":rewards}
        for choice in event["choices"]:
            category = choice["id"]
            reward = rewards[category]
            brackets = ("《", "》") if category == "technique" else ("“", "”")
            choice["text"] = f"选择{category_names[category]}：{brackets[0]}{reward['name']}{brackets[1]}（{reward['tier']}阶）"
        return event

    def _claim_treasure_reward(self, game: GameState, pending: dict[str, Any], category: str) -> tuple[str, str]:
        player = game.player
        reward = pending.get("runtime", {}).get("rewards", {}).get(category)
        if not reward:
            raise ValueError("这份探宝奖励已经失落")
        content_id = str(reward["content_id"])
        if category != "technique":
            add_item(player, content_id)
            category_name = "法器" if category == "artifact" else "丹药"
            return "treasure_claimed", f"你取走{category_name}“{ITEM_CATALOG[content_id].name}” ×1。"
        technique = TECHNIQUE_CATALOG[content_id]
        learned = acquire_technique(player, technique)
        if learned:
            return "technique_learned", f"你取走功法《{technique.name}》，已收入已悟功法。"
        return "technique_copy_gained", f"你取走《{technique.name}》传承玉简，已收入包裹，可用于升级。"
