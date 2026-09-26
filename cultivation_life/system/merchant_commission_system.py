"""Server-priced procurement and reproducible, physically realizable commissions."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from functools import lru_cache

from ..content_registry import ITEM_CATALOG, MARKET_GOODS, REALMS, WORLD_SYSTEMS
from ..models import Player
from ..rules import add_item
from ..runtime import now_iso
from .crafting_system import make_crafting_material_instance, store_crafted_artifact
from .formation_system import calculate_formation_profile, formation_alpha, make_formation_material_instance, formation_config


METRICS = {"growth": "生势", "kill": "杀势", "focus": "聚势", "balance": "均势", "cycle": "环势", "change": "变势"}
PROCUREMENT_KINDS = {"supply", "item", "formation", "weapon"}


@lru_cache(maxsize=48)
def _formation_designs(serialized, config_json, alpha):
    definitions = json.loads(serialized)
    config = json.loads(config_json)
    rng = random.Random("merchant-formation:" + serialized)
    layouts = [[row, row] + [None] * 7 for row in definitions]
    # Diverse real nine-palace layouts. Each accepted contract records a
    # concrete layout, not six independently invented combat multipliers.
    for count in (3, 5, 7, 9):
        for _ in range(16):
            nodes = [rng.choice(definitions) for _ in range(count)] + [None] * (9 - count)
            rng.shuffle(nodes)
            layouts.append(nodes)
    results = []
    for nodes in layouts:
        profile = calculate_formation_profile(nodes, alpha=alpha, config=config)
        if profile["active"]:
            results.append({"slots": [row["id"] if row else None for row in nodes],
                            "value": sum(int(row["base_value"]) for row in nodes if row), "profile": profile})
    return results


class MerchantCommissionMixin:
    def _merchant_commission_available(self, order):
        if order.get("commission_version") != 2:
            return True
        if order["kind"] == "item":
            return order["definition_id"] in ITEM_CATALOG
        if order["kind"] == "supply":
            definitions = self._formation_material_defs() if order["material_category"] == "formation" else self._crafting_material_defs()
            return order["definition_id"] in definitions
        if order["kind"] == "formation":
            return all(key in self._formation_material_defs() for key in order["spec"]["slots"] if key)
        return True

    def _merchant_items(self, world):
        catalog = {}
        for good in MARKET_GOODS:
            if good.get("world") != world or good.get("kind") != "item":
                continue
            item = ITEM_CATALOG.get(str(good.get("content_id", "")))
            if item and item.id != "spirit_stone" and not set(item.tags) & {"unique", "quest", "tianji"}:
                catalog[item.id] = {"id": item.id, "name": item.name, "value": max(1, int(good["price"])),
                                    "tier": int(good.get("tier", 1)), "description": item.description}
        # Rare root manuals are acquired from human-world ruins rather than
        # market stock. Keep their acquisition source explicit and DLC-safe.
        if world == "human":
            for item in ITEM_CATALOG.values():
                if "jinque" in item.tags:
                    catalog[item.id] = {"id": item.id, "name": item.name, "value": 50000, "tier": 4, "description": item.description}
        return sorted(catalog.values(), key=lambda row: (row["tier"], row["id"]))

    def _merchant_procurement_catalog(self, game, alliance):
        result = []
        for world, profile in WORLD_SYSTEMS["world_profiles"].items():
            if not profile.get("enabled", True) or not self._merchant_route_exists(game, alliance, world):
                continue
            formation = [row for row in self._formation_material_defs().values() if row.get("world") == world]
            crafting = self._merchant_materials(world)
            linked = world in alliance["linked_worlds"]
            result.append({"world": world, "world_name": WORLD_SYSTEMS["world_names"][world], "linked": linked,
                "targets": [{"id": npc.id, "name": npc.name, "realm": REALMS[npc.realm_index].name,
                             "power": self._npc_power(npc)} for npc in self._all_world_npcs(game)
                            if npc.alive and npc.world == world][:60] if linked else [],
                "materials": [{"id": row["id"], "name": row["name"], "value": row["base_material_value"], "tier": row["tier"]} for row in crafting],
                "formation_materials": [{"id": row["id"], "name": row["name"], "value": row["base_value"], "tier": row["tier"]} for row in formation],
                "items": self._merchant_items(world),
                "formation_tiers": sorted({int(row["tier"]) for row in formation}),
                "weapon_tiers": sorted({int(row["tier"]) for row in crafting if "primary" in row.get("roles", [])}),
            })
        return result

    def _merchant_formation_spec(self, game, world, payload):
        available = [row for row in self._formation_material_defs().values() if row.get("world") == world]
        if not available:
            raise ValueError("该界面没有可用于炼阵的材料")
        tier = int(payload.get("material_tier", min(int(row["tier"]) for row in available)))
        definitions = sorted((row for row in available if int(row["tier"]) == tier), key=lambda row: row["id"])
        if not definitions:
            raise ValueError("该界面没有此等级的阵法原料")
        raw = payload.get("metrics", {})
        if not isinstance(raw, dict) or set(raw) - METRICS.keys():
            raise ValueError("阵法六维要求无效")
        targets = {key: float(raw.get(key, 0)) for key in METRICS}
        if any(not math.isfinite(value) or not 0 <= value <= 100 for value in targets.values()):
            raise ValueError("阵法六维必须为0–100之间的有限数值")
        designs = _formation_designs(json.dumps(definitions, sort_keys=True),
                                     json.dumps(formation_config(), sort_keys=True), formation_alpha(game.player))
        limits = {key: max((row["profile"]["metrics"][key] for row in designs), default=0) for key in METRICS}
        feasible = [row for row in designs if all(row["profile"]["metrics"][key] + .001 >= value for key, value in targets.items())]
        if not feasible:
            raise ValueError("此原料等级无法同时满足六维要求，请降低要求。单维可选上限：" + "、".join(f"{METRICS[key]} {value:g}" for key, value in limits.items()))
        design = min(feasible, key=lambda row: (row["value"], sum(row["profile"]["metrics"].values())))
        spec = copy.deepcopy(design)
        spec.update(material_tier=tier, requirements=targets, limits=limits, metric_names=METRICS,
                    materials=[{"id": row["id"], "name": row["name"], "tier": row["tier"]} for row in definitions if row["id"] in design["slots"]])
        return spec

    def _merchant_weapon_spec(self, world, payload):
        definitions = self._merchant_materials(world)
        primary = [row for row in definitions if "primary" in row.get("roles", [])]
        if not primary:
            raise ValueError("该界面没有可用炼器主材")
        tier = int(payload.get("material_tier", min(int(row["tier"]) for row in primary)))
        primary = [row for row in primary if int(row["tier"]) == tier]
        if not primary:
            raise ValueError("该界面没有所选等级的炼器主材")
        mold_id = str(payload.get("mold_id", "sword"))
        if mold_id not in self._crafting_molds():
            raise ValueError("请选择有效炼器模具")
        selected = [primary[0]]
        for role in ("secondary", "secondary", "quench"):
            options = sorted((row for row in definitions if role in row.get("roles", []) and int(row["tier"]) <= tier),
                             key=lambda row: (-int(row["tier"]), row["id"]))
            if role == "secondary" and len(selected) == 2:
                options = [row for row in options if row["id"] != selected[1]["id"] or row.get("allow_duplicate_type")]
            if not options:
                raise ValueError("本界该等级缺少完整的主材、辅材或淬火配方")
            selected.append(options[0])
        smith = Player("商盟工匠", "heavenly", realm_index=tier, layer=REALMS[tier].layers)
        for index, definition in enumerate(selected):
            smith.crafting_materials.append({"id": f"commission-material-{index}", "material_id": definition["id"],
                "name": definition["name"], "quality": 1.0, "material_value": definition["base_material_value"],
                "acquired_tier": int(definition["tier"]), "state": "验收标准料", "origin_world": world, "source": "商盟工坊"})
        budget = int(self._crafting_rules()["budget_by_realm"][tier])
        hp = budget // 6
        preview = self._crafting_preview(smith, {"mold_id": mold_id, "primary_id": "commission-material-0",
            "secondary_a_id": "commission-material-1", "secondary_b_id": "commission-material-2", "quench_id": "commission-material-3",
            "allocations": {"combat_power": budget - hp * 2, "max_hp": hp, "max_mp": hp}})
        return {"material_tier": tier, "mold": preview["mold"], "materials": preview["selected_materials"],
                "stats": preview["theoretical_stats"]["normal"], "combat_effects": preview["combat_effects"],
                "material_effects": preview["material_effects"], "anchor_value": preview["anchor_value"],
                "value": sum(row["material_value"] for row in preview["selected_materials"]), "quality_name": preview["quality_names"]["normal"]}

    def _merchant_quote(self, game, alliance, payload):
        from .merchant_system import KINDS
        kind = str(payload.get("kind", "supply"))
        stars, quantity = int(payload.get("stars", 1)), int(payload.get("quantity", 1))
        if kind not in KINDS or not 1 <= stars <= 5 or not 1 <= quantity <= 99:
            raise ValueError("任务类型、星级或数量无效")
        world = str(payload.get("source_world") or game.player.world)
        profile = WORLD_SYSTEMS["world_profiles"].get(world)
        if not profile or not profile.get("enabled", True):
            raise ValueError("目标界面尚未开放")
        linked, cross = self._merchant_route_exists(game, alliance, world), world != game.player.world
        if not linked:
            raise ValueError("该界面没有本商盟总部或分总部，无法发布委托")
        price_factor = 4 if cross else 1
        time_factor = 15 if cross else 1
        spec, definition_id, target_id = None, "", None
        category = str(payload.get("material_category", "crafting"))
        if category not in {"crafting", "formation"}:
            raise ValueError("请选择阵法材料或炼器材料")
        value = 2000 * stars ** 3
        name = KINDS[kind]
        if kind == "supply":
            definitions = self._formation_material_defs() if category == "formation" else self._crafting_material_defs()
            definition = definitions.get(str(payload.get("definition_id", "")))
            if not definition or definition.get("world") != world:
                raise ValueError("请选择该界面及材料分类下的具体材料")
            definition_id = definition["id"]
            value = int(definition["base_value" if category == "formation" else "base_material_value"]) * quantity * 3
            name = f"收集{definition['name']} ×{quantity}"
        elif kind == "item":
            item = next((row for row in self._merchant_items(world) if row["id"] == payload.get("definition_id")), None)
            if not item:
                raise ValueError("请选择目标界面可委托获取的道具")
            definition_id = item["id"]
            value = item["value"] * quantity * 3
            name = f"获取{item['name']} ×{quantity}"
        elif kind in {"weapon", "formation"}:
            spec = self._merchant_weapon_spec(world, payload) if kind == "weapon" else self._merchant_formation_spec(game, world, payload)
            value = max(value, spec["value"] * 3)
            name += f" · {spec['material_tier']}阶原料" + (f" · {spec['mold']['name']}" if kind == "weapon" else "")
        elif kind == "bounty":
            target = self._find_npc(game, str(payload.get("target_id", "")))
            if not target or not target.alive or target.world != world:
                raise ValueError("请选择目标界面内仍存活的悬赏修士")
            value = max(value, math.ceil(self._npc_power(target) * 4))
            target_id, name = target.id, name + f" · {target.name}"
        minimum = math.ceil(max(100 * stars, value) * price_factor)
        principal = int(payload.get("principal", minimum))
        if principal < minimum or principal > 10 ** 15:
            raise ValueError(f"此委托悬赏本金至少 {minimum:,} 灵石")
        fee = max(1, math.ceil(principal * (.06 if alliance["policy"] == "economy" else .1)))
        years = max(stars * 3, int((spec or {}).get("material_tier", 0)) ** 2) * time_factor
        quote = {"kind": kind, "name": name, "stars": stars, "quantity": quantity, "source_world": world,
                 "definition_id": definition_id, "target_id": target_id, "material_category": category,
                 "minimum": minimum, "principal": principal, "fee": fee, "total": principal + fee, "years": years,
                 "cross_world": cross, "unlinked": not linked, "spec": spec, "commission_version": 2,
                 "route_description": "跨界商路：时间×15、基础费用×4" if cross else "本界商路"}
        quote["preview_token"] = hashlib.sha256(json.dumps(quote, sort_keys=True).encode()).hexdigest()
        return quote

    def preview_merchant_commission(self, game_id, payload):
        game = self._load(game_id)
        member = game.merchant_state["membership"]
        alliance = self._merchant_alliance(game, game.player.world, str(payload.get("alliance_id", "")))
        if not member or not alliance or alliance["id"] != member["alliance_id"]:
            raise ValueError("请先加入该商盟")
        return self._merchant_quote(game, alliance, payload)

    def _merchant_deliver_commission(self, game, order):
        kind, world = order["kind"], order["source_world"]
        rng = random.Random(f"merchant-delivery:{game.seed}:{order['id']}")
        if kind == "item":
            add_item(game.player, order["definition_id"], order["quantity"])
            return f"获得{ITEM_CATALOG[order['definition_id']].name} ×{order['quantity']}"
        if kind == "supply":
            category = order["material_category"]
            definition = (self._formation_material_defs() if category == "formation" else self._crafting_material_defs())[order["definition_id"]]
            for _ in range(order["quantity"]):
                if category == "formation":
                    game.player.formation_materials.append(make_formation_material_instance(definition, source="商盟委托", origin_world=world))
                else:
                    game.player.crafting_materials.append(make_crafting_material_instance(definition, rng, source="商盟委托", origin_world=world))
            return f"获得{definition['name']} ×{order['quantity']}"
        spec = order["spec"]
        if kind == "formation":
            for material_id in spec["slots"]:
                if material_id:
                    game.player.formation_materials.append(make_formation_material_instance(self._formation_material_defs()[material_id], source="商盟炼阵委托", origin_world=world))
            game.player.formation_sequence += 1
            game.player.formation_loadouts.append({"id": f"formation-{game.id}-{game.player.formation_sequence}",
                "name": f"商盟{order['stars']}星护行阵", "slots": list(spec["slots"]), "created_year": game.player.age})
            return f"获得{spec['material_tier']}阶原料定制阵法及全部独立阵材，可在阵法面板启用"
        artifact = {"id": f"merchant-weapon-{game.id}-{order['id']}", "name": f"商盟订制{spec['mold']['name']}",
            "mold_id": spec["mold"]["id"], "mold_name": spec["mold"]["name"], "quality": "normal", "quality_name": spec["quality_name"],
            "creator_name": order["worker"], "created_year": game.player.age, "scaling_realm_index": spec["material_tier"],
            "actual_stats": copy.deepcopy(spec["stats"]), "designed_stats": copy.deepcopy(spec["stats"]),
            "anchor_value": spec["anchor_value"], "materials": copy.deepcopy(spec["materials"]),
            "material_effects": copy.deepcopy(spec["material_effects"]), "combat_effects": copy.deepcopy(spec["combat_effects"]),
            "mold_rule_description": spec["mold"]["rule"].get("description", ""), "is_natal": False}
        store_crafted_artifact(game.player, artifact)
        return f"获得{artifact['name']}，属性与委托验收概览一致"

    def debug_merchant_hq(self, game_id, alliance_id):
        """Only exposed by a runtime-Debug-gated server operation."""
        game = self._load(game_id)
        if not game.player.alive or game.pending_event or game.merchant_state["active"]:
            raise ValueError("请先结束当前事件或商盟任务")
        alliance = self._merchant_alliance(game, game.player.world, alliance_id)
        if not alliance:
            raise ValueError("本界没有该商盟总部")
        member = {"alliance_id": alliance_id, "world": game.player.world, "site": "hq", "rank": 2}
        game.merchant_state["membership"] = member
        key = self._merchant_influence_key(member)
        game.merchant_state["influence"][key] = max(360, game.merchant_state["influence"].get(key, 0))
        self._merchant_notice(game, f"Debug：已获得{alliance['name']}本界总部特使身份。")
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
