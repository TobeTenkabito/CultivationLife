from __future__ import annotations

import copy
import math
import random
import uuid
from typing import Any

from .content_registry import CONTENT_DOCUMENTS, REALMS, WORLD_SYSTEMS
from .models import GameState, HistoryRecord, Item, Player
from .rules import add_item, expected_combat_power, max_hp, max_mp, remove_item
from .runtime import decode_rng, encode_rng, now_iso


STAT_NAMES = {
    "combat_power": "战斗力", "max_hp": "最大HP", "max_mp": "最大MP",
    "opportunity_efficiency": "机缘效率", "body_training_efficiency": "炼体效率",
    "divine_sense_efficiency": "神识效率", "tribulation_reduction": "渡劫减伤",
    "breakthrough_bonus": "突破加成",
}


def crafting_config() -> dict[str, Any]:
    return CONTENT_DOCUMENTS.get("crafting.json", {})


def active_crafted_artifacts(player: Player) -> list[dict[str, Any]]:
    active_ids = {
        str(item.crafted_artifact_id)
        for item in player.inventory
        if item.quantity > 0 and item.crafted_artifact_id
    }
    # In-memory legacy fixtures may not have passed through Player.from_dict;
    # the new rule is that every owned crafted artifact is automatically live.
    if not active_ids and player.crafted_artifacts:
        active_ids = {str(row.get("id", "")) for row in player.crafted_artifacts}
    return [
        row for row in player.crafted_artifacts
        if isinstance(row, dict) and str(row.get("id")) in active_ids
    ]


def crafted_artifact_description(artifact: dict[str, Any]) -> str:
    preserved = str(artifact.get("description", "")).strip()
    if preserved:
        return preserved
    rule = str(artifact.get("mold_rule_description", "")).strip()
    material_lines = [
        str(row.get("description", "")).strip()
        for row in artifact.get("material_effects", [])
        if isinstance(row, dict) and str(row.get("description", "")).strip()
    ]
    pieces = [
        f"{artifact.get('quality_name', '')}{artifact.get('mold_name', '组合式法宝')}",
        f"常驻属性：{artifact_summary(artifact)}",
    ]
    if rule:
        pieces.append(f"胎模器纹：{rule}")
    if material_lines:
        pieces.append("材料器纹：" + "；".join(material_lines))
    pieces.append(
        f"由{artifact.get('creator_name', '无名器师')}炼于纪年 {artifact.get('created_year', '?')}，"
        f"锚定价值 {int(artifact.get('anchor_value', 1)):,} 灵石"
    )
    return "。".join(pieces) + "。"


def store_crafted_artifact(player: Player, artifact: dict[str, Any]) -> None:
    artifact_id = str(artifact.get("id", ""))
    if not artifact_id:
        raise ValueError("炼器法宝缺少唯一实例 ID")
    artifact["description"] = crafted_artifact_description(artifact)
    if not any(str(row.get("id")) == artifact_id for row in player.crafted_artifacts):
        player.crafted_artifacts.append(artifact)
    if not any(item.crafted_artifact_id == artifact_id for item in player.inventory):
        player.inventory.append(Item(
            id=artifact_id,
            name=str(artifact.get("name", "无名法宝")),
            quantity=1,
            crafted_artifact_id=artifact_id,
            description=str(artifact["description"]),
            tags=["artifact", "equipment", "crafted_artifact"],
        ))


def remove_crafted_artifact(player: Player, artifact: dict[str, Any]) -> None:
    artifact_id = str(artifact.get("id", ""))
    player.crafted_artifacts = [
        row for row in player.crafted_artifacts if str(row.get("id", "")) != artifact_id
    ]
    player.equipped_crafted_artifact_ids = [
        value for value in player.equipped_crafted_artifact_ids if value != artifact_id
    ]
    player.inventory = [
        item for item in player.inventory if item.crafted_artifact_id != artifact_id
    ]


def crafted_artifact_bonuses(player: Player) -> dict[str, float]:
    totals = {key: 0.0 for key in STAT_NAMES}
    breakthrough_values: list[float] = []
    for artifact in active_crafted_artifacts(player):
        stats = artifact.get("actual_stats", {})
        for key in totals:
            value = max(0.0, float(stats.get(key, 0.0)))
            if key == "breakthrough_bonus":
                breakthrough_values.append(min(0.05, value))
            else:
                totals[key] += value
    # 炼器法宝的突破属性永远只取当前生效法宝里的最高值，禁止多件叠加。
    totals["breakthrough_bonus"] = max(breakthrough_values, default=0.0)
    return totals


def crafted_combat_effects(player: Player) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for artifact in active_crafted_artifacts(player):
        for effect in artifact.get("combat_effects", []):
            if isinstance(effect, dict):
                effects.append(copy.deepcopy(effect) | {
                    "item_id": str(artifact.get("id", "")), "name": str(artifact.get("name", "法宝")),
                })
    return effects


def crafting_material_definitions() -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in crafting_config().get("materials", [])}


def make_crafting_material_instance(
    definition: dict[str, Any], rng: random.Random, *, source: str, origin_world: str,
) -> dict[str, Any]:
    condition = max(0.65, min(1.25, rng.triangular(0.65, 1.25, 1.0)))
    state = "灵韵天成" if condition >= 1.15 else "品相上佳" if condition >= 1.05 else "保存完好" if condition >= .9 else "略有损耗"
    base_value = max(1, int(definition["base_material_value"]))
    return {
        "id": f"material-{uuid.uuid4().hex}", "material_id": str(definition["id"]),
        "name": str(definition["name"]), "quality": round(condition, 4), "state": state,
        "source": source, "origin_world": origin_world,
        "material_value": max(1, round(base_value * condition)),
        "acquired_tier": int(definition.get("tier", 1)),
    }


class CraftingSystemMixin:
    @staticmethod
    def _crafting_rules() -> dict[str, Any]:
        return crafting_config().get("settings", {})

    @staticmethod
    def _crafting_molds() -> dict[str, dict[str, Any]]:
        return {str(row["id"]): row for row in crafting_config().get("molds", [])}

    @staticmethod
    def _crafting_material_defs() -> dict[str, dict[str, Any]]:
        return crafting_material_definitions()

    @staticmethod
    def _crafting_plant_defs() -> dict[str, dict[str, Any]]:
        return {str(row["plant_id"]): row for row in crafting_config().get("spirit_plants", [])}

    def _append_crafting_market_offers(
        self, game: GameState, rng: random.Random, offers: list[dict[str, Any]], *,
        tier: int, market_name: str, location_id: str,
    ) -> None:
        # New crafting stock must not move the story/combat RNG stream.  Its
        # condition remains deterministic for the same save, place and year.
        rng = random.Random(
            f"{game.seed}:crafting-market:{game.player.world}:{location_id}:{game.player.age}:{tier}"
        )
        definitions = [
            row for row in self._crafting_material_defs().values()
            if str(row.get("world")) == game.player.world
            and int(row.get("tier", 1)) <= max(tier, game.player.realm_index) + 1
        ]
        if not definitions:
            return
        count = min(int(self._crafting_rules().get("market_material_offers", 3)), len(definitions))
        selected = rng.sample(definitions, count)
        for index, definition in enumerate(selected):
            # Keep the public market tier contract (current or rare +1) even in
            # route worlds whose legacy market tier helper still reports five.
            offer_tier = tier + 1 if int(definition.get("tier", tier)) > tier else tier
            instance = make_crafting_material_instance(
                definition, rng, source=f"{market_name}购得", origin_world=game.player.world,
            )
            base_price = int(definition["base_material_value"])
            price = max(1, round(base_price * instance["quality"] * rng.uniform(.9, 1.1)))
            offers.append({
                "id": f"{game.player.world}-{location_id}-{game.player.age}-{tier}-craft-{index}-{definition['id']}",
                "kind": "crafting_material", "content_id": str(definition["id"]),
                "name": str(definition["name"]),
                "description": f"炼器材料 · {instance['state']} · 材料价值 {instance['material_value']:,}；可用位置：" + "、".join(
                    {"primary":"主材", "secondary":"辅材", "quench":"淬火"}[role]
                    for role in definition.get("roles", [])
                ),
                "price": price, "tier": offer_tier,
                "tier_name": REALMS[max(0, min(len(REALMS) - 1, offer_tier))].name,
                "market_name": market_name, "world": game.player.world, "location_id": location_id,
                "rare_next_tier": offer_tier > tier, "sold": False,
                "material_instance": instance,
            })

    def _buy_crafting_material_offer(self, game: GameState, offer: dict[str, Any], price: int) -> str:
        instance = copy.deepcopy(offer.get("material_instance"))
        if not isinstance(instance, dict):
            definition = self._crafting_material_defs().get(str(offer.get("content_id", "")))
            if not definition:
                raise ValueError("这份炼器材料已经失去灵性")
            rng = decode_rng(game.seed, game.rng_state)
            instance = make_crafting_material_instance(
                definition, rng, source=f"{offer.get('market_name', '坊市')}购得", origin_world=game.player.world,
            )
            game.rng_state = encode_rng(rng)
        game.player.crafting_materials.append(instance)
        return f"你在{offer['market_name']}支付 {price} 枚灵石，购得{instance['state']}的{instance['name']}。"

    def _crafting_material_candidates(self, player: Player) -> list[dict[str, Any]]:
        material_defs = self._crafting_material_defs()
        candidates: list[dict[str, Any]] = []
        for instance in player.crafting_materials:
            definition = material_defs.get(str(instance.get("material_id", "")))
            if not definition:
                continue
            candidates.append(copy.deepcopy(instance) | {
                "definition_id": str(definition["id"]), "roles": list(definition.get("roles", [])),
                "tags": list(definition.get("tags", [])),
                "allow_duplicate_type": bool(definition.get("allow_duplicate_type", False)),
                "role_effects": copy.deepcopy(definition.get("role_effects", {})),
                "source_kind": "material",
            })
        plant_defs = self._crafting_plant_defs()
        for item in player.inventory:
            definition = plant_defs.get(str(item.plant_id or ""))
            if not definition or item.quantity <= 0:
                continue
            candidates.append({
                "id": f"plant:{item.id}", "definition_id": f"plant:{item.plant_id}",
                "name": item.name, "quality": float(item.plant_quality or .5),
                "state": f"实生 {int(item.plant_years or 0):,} 年", "source": "洞府灵田采收",
                "origin_world": player.world, "material_value": int(item.plant_value or 1),
                "roles": list(definition.get("roles", [])), "tags": ["spirit_plant", str(item.plant_id)],
                "allow_duplicate_type": bool(definition.get("allow_duplicate_type", False)),
                "role_effects": copy.deepcopy(definition.get("role_effects", {})),
                "source_kind": "plant", "inventory_item_id": item.id, "quantity": item.quantity,
            })
        return candidates

    @staticmethod
    def _quality_probabilities(refining_level: int, average_quality: float) -> dict[str, float]:
        tiers = ("damaged", "rough", "normal", "excellent", "refined", "epic", "legendary")
        base = (8.0, 20.0, 50.0, 14.0, 6.0, 1.7, .3)
        shift = min(12.0, max(-4.0, refining_level * .75 + (average_quality - 1.0) * 10.0))
        weights = [weight * math.exp(shift * (index - 2) * .16) for index, weight in enumerate(base)]
        total = sum(weights)
        return {tier: round(weight / total, 6) for tier, weight in zip(tiers, weights)}

    @staticmethod
    def _weighted_choice(rng: random.Random, probabilities: dict[str, float]) -> str:
        roll = rng.random()
        elapsed = 0.0
        for key, probability in probabilities.items():
            elapsed += probability
            if roll <= elapsed:
                return key
        return next(reversed(probabilities))

    def _resolve_crafting_selection(self, player: Player, payload: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
        mold = self._crafting_molds().get(str(payload.get("mold_id", "")))
        if not mold:
            raise ValueError("请选择一种合法胎模")
        candidate_map = {str(row["id"]): row for row in self._crafting_material_candidates(player)}
        selected_ids = [
            str(payload.get("primary_id", "")), str(payload.get("secondary_a_id", "")),
            str(payload.get("secondary_b_id", "")), str(payload.get("quench_id", "")),
        ]
        if any(not value for value in selected_ids) or len(set(selected_ids)) != 4:
            raise ValueError("主材、两份辅材与淬火材料必须各选择一个不同实例")
        roles = ("primary", "secondary", "secondary", "quench")
        selected: list[tuple[str, dict[str, Any]]] = []
        for role, instance_id in zip(roles, selected_ids):
            candidate = candidate_map.get(instance_id)
            if not candidate or role not in candidate.get("roles", []):
                raise ValueError("材料不存在，或不能用于所选炼器位置")
            selected.append((role, candidate))
        secondary_defs = [selected[1][1]["definition_id"], selected[2][1]["definition_id"]]
        if secondary_defs[0] == secondary_defs[1] and not all(
            bool(selected[index][1].get("allow_duplicate_type")) for index in (1, 2)
        ):
            raise ValueError("这种材料不允许同时占用两个辅材位")
        return mold, selected

    def _crafting_preview(self, player: Player, payload: dict[str, Any]) -> dict[str, Any]:
        rules = self._crafting_rules()
        mold, selected = self._resolve_crafting_selection(player, payload)
        budget = int(rules["budget_by_realm"][max(0, min(12, player.realm_index))])
        raw_allocations = payload.get("allocations", {}) if isinstance(payload.get("allocations"), dict) else {}
        allocations = {key: max(0, int(raw_allocations.get(key, 0) or 0)) for key in STAT_NAMES}
        used = sum(allocations[key] * float(rules["stat_costs"][key]) for key in allocations)
        if used <= 0:
            raise ValueError("至少为法宝分配一项属性")
        if used > budget + 1e-9:
            raise ValueError(f"属性预算超出上限：已用 {used:.1f} / {budget}")
        primary_tier = int(selected[0][1].get("acquired_tier", player.realm_index))
        scaling_realm_index = max(0, min(player.realm_index, primary_tier, len(REALMS) - 1))
        scaling_layer = (
            player.layer if scaling_realm_index == player.realm_index
            else max(1, REALMS[scaling_realm_index].layers)
        )
        # Anchor absolute output to the recipe's main-material stage, not a
        # flat +1 and not the wearer's already-equipped bonuses.  This keeps
        # Qi artifacts legible while making immortal artifacts scale against
        # immortal combat numbers without recursive forge-to-forge inflation.
        benchmark = Player(
            "炼器境界基准", player.spirit_root,
            realm_index=scaling_realm_index, layer=scaling_layer, path=player.path,
        )
        expected = expected_combat_power(scaling_realm_index, scaling_layer)
        stat_bases = {
            "combat_power": expected, "max_hp": max_hp(benchmark), "max_mp": max_mp(benchmark),
            "opportunity_efficiency": 1.0, "body_training_efficiency": 1.0,
            "divine_sense_efficiency": 1.0, "tribulation_reduction": 1.0,
            "breakthrough_bonus": 1.0,
        }
        designed = {
            key: stat_bases[key] * float(rules["stat_caps"][key])
            * allocations[key] * float(rules["stat_costs"][key]) / max(1, budget)
            for key in STAT_NAMES
        }
        special_stats = {key: 0.0 for key in STAT_NAMES}
        combat_effects = [copy.deepcopy(mold["rule"].get("combat_effect", {})) | {"source": mold["rule"]["name"]}]
        material_effects = []
        for role, material in selected:
            effect = copy.deepcopy(material.get("role_effects", {}).get(role, {}))
            for key, multiplier in effect.get("design_multipliers", {}).items():
                if key in designed:
                    designed[key] *= max(0.0, float(multiplier))
            potency = min(1.25, max(.65, math.sqrt(max(1.0, float(material["material_value"])) / max(1.0, float(material["material_value"]) / max(.01, float(material["quality"])) ))))
            for key, value in effect.get("special_stats", {}).items():
                if key in special_stats:
                    special_stats[key] += float(value) * potency
            if effect.get("combat_effect"):
                combat_effects.append(copy.deepcopy(effect["combat_effect"]) | {
                    "source": f"{material['name']}·{role}",
                })
            material_effects.append({
                "role": role, "material_id": material["definition_id"], "instance_id": material["id"],
                "name": material["name"], "description": str(effect.get("description", "")),
            })
        average_quality = sum(float(row[1]["quality"]) for row in selected) / 4
        refining_exp = max(0.0, float(player.art_experience.get("refining", 0.0)))
        refining_level = int(math.sqrt(refining_exp / float(rules.get("refining_experience_base", 100))))
        probabilities = self._quality_probabilities(refining_level, average_quality)
        caps = rules["stat_caps"]
        theoretical = {}
        for quality, multiplier in rules["quality_multipliers"].items():
            stats = {}
            for key in STAT_NAMES:
                value = designed[key] * float(multiplier) + special_stats[key]
                if key == "breakthrough_bonus":
                    value = min(float(caps[key]), value)
                elif key == "tribulation_reduction":
                    value = min(.50, value)
                stats[key] = round(value, 4 if key not in {"combat_power", "max_hp", "max_mp"} else 1)
            theoretical[quality] = stats
        anchor = max(1, round(sum(int(row[1]["material_value"]) for row in selected) * float(rules["anchor_multiplier"])))
        return {
            "mold": copy.deepcopy(mold), "selected_materials": [copy.deepcopy(row) for _, row in selected],
            "material_effects": material_effects, "allocations": allocations,
            "budget": budget, "budget_used": round(used, 2), "designed_stats": {key: round(value, 4) for key, value in designed.items()},
            "scaling_realm_index": scaling_realm_index,
            "scaling_realm_name": REALMS[scaling_realm_index].name,
            "scaling_benchmarks": {
                "combat_power": round(expected, 1),
                "max_hp": max_hp(benchmark), "max_mp": max_mp(benchmark),
            },
            "special_stats": {key: round(value, 4) for key, value in special_stats.items()},
            "quality_probabilities": probabilities, "quality_names": copy.deepcopy(rules["quality_names"]),
            "quality_multipliers": copy.deepcopy(rules["quality_multipliers"]),
            "theoretical_stats": theoretical, "combat_effects": combat_effects,
            "anchor_value": anchor, "refining_level": refining_level,
        }

    def preview_crafting(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法开炉炼器")
        return self._crafting_preview(game.player, payload)

    def forge_crafted_artifact(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if game.pending_event or not player.alive or player.imprisonment:
            raise ValueError("当前状态无法开炉炼器")
        preview = self._crafting_preview(player, payload)
        # Preview has fully validated all four instance IDs. Consume only after every check passes.
        for material in preview["selected_materials"]:
            if material.get("source_kind") == "plant":
                if not remove_item(player, str(material["inventory_item_id"])):
                    raise ValueError("灵田材料数量发生变化，请重新确认配方")
            else:
                stored = next((row for row in player.crafting_materials if str(row.get("id")) == str(material["id"])), None)
                if not stored:
                    raise ValueError("炼器材料数量发生变化，请重新确认配方")
                player.crafting_materials.remove(stored)
        rng = decode_rng(game.seed, game.rng_state)
        quality = self._weighted_choice(rng, preview["quality_probabilities"])
        game.rng_state = encode_rng(rng)
        name = str(payload.get("name", "")).strip()[:20] or str(preview["mold"]["default_name"])
        player.crafting_sequence += 1
        artifact_id = f"crafted-{game.id}-{player.crafting_sequence}"
        artifact = {
            "id": artifact_id, "name": name, "mold_id": preview["mold"]["id"],
            "mold_name": preview["mold"]["name"], "quality": quality,
            "quality_name": preview["quality_names"][quality],
            "quality_multiplier": float(preview["quality_multipliers"][quality]),
            "creator_name": player.name, "creator_id": game.id, "created_year": player.age,
            "scaling_realm_index": preview["scaling_realm_index"],
            "scaling_realm_name": preview["scaling_realm_name"],
            "scaling_benchmarks": preview["scaling_benchmarks"],
            "materials": [{key: row.get(key) for key in (
                "id", "definition_id", "name", "quality", "state", "source", "origin_world", "material_value"
            )} for row in preview["selected_materials"]],
            "material_effects": preview["material_effects"], "allocations": preview["allocations"],
            "designed_stats": preview["designed_stats"],
            "actual_stats": preview["theoretical_stats"][quality],
            "combat_effects": preview["combat_effects"], "anchor_value": preview["anchor_value"],
            "mold_rule_description": str(preview["mold"]["rule"].get("description", "")),
            "is_natal": False,
        }
        store_crafted_artifact(player, artifact)
        self._grant_art_experience(player, "refining", float(self._crafting_rules().get("refining_experience_per_craft", 30)))
        game.history.append(HistoryRecord(
            "SYS_ARTIFACT_FORGE", 1, player.age, "组合炼器", artifact_id, "forged",
            f"你以{preview['mold']['name']}定形，炼成{artifact['quality_name']}法宝“{name}”；炼制不会失败，材料锚定价值为 {artifact['anchor_value']:,} 灵石。",
            {"artifact_id":artifact_id, "quality":quality, "anchor_value":artifact["anchor_value"]},
            ["system", "crafting", "art:refining"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def save_crafting_blueprint(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        game = self._load(game_id)
        preview = self._crafting_preview(game.player, payload)
        blueprint = {
            "id": f"blueprint-{uuid.uuid4().hex}",
            "name": (str(payload.get("blueprint_name", "")).strip()[:20] or f"{preview['mold']['default_name']}图谱"),
            "mold_id": preview["mold"]["id"],
            "material_types": [row["definition_id"] for row in preview["selected_materials"]],
            "allocations": preview["allocations"], "created_year": game.player.age,
        }
        game.player.crafting_blueprints.append(blueprint)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def crafted_artifact_action(self, game_id: str, artifact_id: str, action: str, start_price: int = 0) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        artifact = next((row for row in player.crafted_artifacts if str(row.get("id")) == artifact_id), None)
        if not artifact:
            raise ValueError("这件炼器法宝不存在")
        if action == "equip":
            raise ValueError("炼器法宝收入包裹后自动生效，无需另行装备")
        elif action == "unequip":
            raise ValueError("炼器法宝与普通装备相同，留在包裹中即自动生效")
        elif action == "natal":
            for row in player.crafted_artifacts:
                row["is_natal"] = False
            artifact["is_natal"] = True
        elif action == "unbind_natal":
            artifact["is_natal"] = False
        elif action == "sell":
            if artifact.get("is_natal"):
                raise ValueError("已设为本命的法宝不能出售")
            price = max(1, round(int(artifact["anchor_value"]) * float(self._crafting_rules()["ordinary_sell_ratio"])))
            remove_crafted_artifact(player, artifact)
            add_item(player, "spirit_stone", price)
            game.history.append(HistoryRecord(
                "SYS_ARTIFACT_SELL", 1, player.age, "坊市出售法宝", artifact_id, "sold",
                f"你将{name_or_artifact(artifact)}出售，获得 {price:,} 枚灵石；成品实例已离开存档，不会进入全局回收池。",
                {"spirit_stone":price}, ["system", "crafting", "market"],
            ))
        elif action == "consign":
            self._consign_crafted_artifact(game, artifact, int(start_price or 0))
        else:
            raise ValueError("未知炼器法宝操作")
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _consign_crafted_artifact(self, game: GameState, artifact: dict[str, Any], start_price: int) -> None:
        state = self._require_auction_access(game, {"scheduled", "open"})
        artifact_id = str(artifact["id"])
        if artifact.get("is_natal"):
            raise ValueError("已设为本命的法宝不能送拍")
        base_price = max(1, int(artifact["anchor_value"]))
        minimum = max(1, math.ceil(base_price * float(self._auction_rules()["consignment_min_price_ratio"])))
        maximum = max(minimum, math.floor(base_price * float(self._auction_rules()["consignment_max_price_ratio"])))
        start_price = int(start_price or round(base_price * .8))
        if not minimum <= start_price <= maximum:
            raise ValueError(f"起拍价须在 {minimum:,}—{maximum:,} 灵石之间")
        fee = max(1, math.ceil(base_price * float(self._auction_rules()["consignment_listing_fee_ratio"])))
        if not remove_item(game.player, "spirit_stone", fee):
            raise ValueError(f"上拍前须支付 {fee:,} 枚灵石占位费")
        snapshot = copy.deepcopy(artifact)
        remove_crafted_artifact(game.player, artifact)
        consignment = {
            "kind":"crafted_artifact", "content_id":artifact_id, "artifact":snapshot,
            "start_price":start_price, "tier":game.player.realm_index,
            "rated_price":base_price, "listing_fee":fee,
        }
        state.setdefault("consignments", []).append(consignment)
        if state["status"] == "open":
            rng = self._auction_rng(game, "crafted-consignment")
            state["lots"].append(self._make_crafted_auction_lot(
                game, rng, consignment, f"player-{len(state['consignments']) - 1}",
            ))
        game.history.append(HistoryRecord(
            "SYS_ARTIFACT_CONSIGN", 1, game.player.age, "法宝寄拍", artifact_id, "consigned",
            f"你支付 {fee:,} 枚占位费，将{name_or_artifact(snapshot)}以 {start_price:,} 灵石起拍。",
            {"listing_fee":-fee, "start_price":start_price}, ["system", "crafting", "auction"],
        ))

    def _make_crafted_auction_lot(self, game: GameState, rng: random.Random, consignment: dict[str, Any], suffix: str) -> dict[str, Any]:
        artifact = consignment["artifact"]
        rated = int(consignment["rated_price"])
        start = int(consignment["start_price"])
        return {
            "id":f"{game.auction_state['id']}-{suffix}", "kind":"crafted_artifact",
            "content_id":str(artifact["id"]), "artifact":copy.deepcopy(artifact),
            "name":str(artifact["name"]),
            "description":f"{artifact['quality_name']} · {artifact['mold_name']} · {artifact_summary(artifact)}",
            "tier":int(consignment.get("tier", 1)), "tier_name":REALMS[max(0, min(12, int(consignment.get("tier", 1))))].name,
            "start_price":start, "current_bid":start, "rated_price":rated,
            "maximum_bid":max(1, math.floor(rated * float(self._auction_rules()["consignment_max_price_ratio"]))),
            "current_bidder":"npc", "current_bidder_name":rng.choice(self._auction_rules()["bidder_aliases"]),
            "seller":"player", "closed":False,
        }

    def _public_crafting_system(self, game: GameState) -> dict[str, Any]:
        player = game.player
        rules = self._crafting_rules()
        candidates = self._crafting_material_candidates(player)
        return {
            "visible": bool(crafting_config()) and player.realm_index >= int(rules.get("minimum_realm", 1)),
            "molds": list(copy.deepcopy(self._crafting_molds()).values()),
            "materials": candidates, "artifacts":[
                copy.deepcopy(row) | {"equipped":True}
                for row in active_crafted_artifacts(player)
            ],
            "blueprints": copy.deepcopy(player.crafting_blueprints),
            "active_count": len(active_crafted_artifacts(player)),
            "budget": int(rules.get("budget_by_realm", [40] * 13)[max(0, min(12, player.realm_index))]),
            "stat_costs": copy.deepcopy(rules.get("stat_costs", {})),
            "stat_names": STAT_NAMES, "quality_names": copy.deepcopy(rules.get("quality_names", {})),
            "bonuses": crafted_artifact_bonuses(player),
            "auction_available": bool(game.auction_state.get("status") in {"scheduled", "open"} and self._auction_location_matches(game)),
        }


def artifact_summary(artifact: dict[str, Any]) -> str:
    stats = artifact.get("actual_stats", {})
    pieces = []
    for key, value in stats.items():
        number = float(value)
        if not number:
            continue
        shown = f"{number:.1%}" if key.endswith("efficiency") or key.endswith("reduction") or key == "breakthrough_bonus" else f"{number:,.0f}"
        pieces.append(f"{STAT_NAMES.get(key, key)} +{shown}")
    return "、".join(pieces) or "无常驻数值"


def name_or_artifact(artifact: dict[str, Any]) -> str:
    return f"{artifact.get('quality_name', '')}法宝“{artifact.get('name', '无名法宝')}”"
