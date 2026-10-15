from __future__ import annotations
from typing import Any
from ...models import Player
import copy
import math
from functools import lru_cache
from collections import Counter
from ...content_registry import CONTENT_DOCUMENTS, GUIXU_TIDE_CONTENT
from .dependencies import CraftingMaterialsDependencies


@lru_cache(maxsize=1)
def _guixu_material_tiers() -> dict[str, tuple[int, str]]:
    """Immutable content lookup, built once; never infer origin from the holder."""
    ranks = {}
    for dungeon in GUIXU_TIDE_CONTENT.get("dungeons", []):
        tier = int(dungeon["max_entry_rank"][0])
        for entry in dungeon["treasure_pool"]:
            if entry["category"] in {"material", "plant"}:
                identity = str(entry["content_id"])
                previous = ranks.get(identity)
                if previous is None or tier < previous[0]:
                    ranks[identity] = (tier, str(dungeon["world"]))
    return ranks


def _plant_material_tier(years: int) -> int:
    rows = CONTENT_DOCUMENTS["crafting.json"]["settings"]["plant_tiers_by_years"]
    return next(tier for threshold, tier in reversed(rows) if years >= threshold)


def _crafting_material_candidates(
    deps: CraftingMaterialsDependencies, player: Player
) -> list[dict[str, Any]]:
    material_defs = deps._crafting_material_defs()
    candidates: list[dict[str, Any]] = []
    for instance in player.crafting_materials:
        embedded = instance.get("dynamic_definition")
        definition = (
            copy.deepcopy(embedded)
            if isinstance(embedded, dict)
            else material_defs.get(str(instance.get("material_id", "")))
        )
        if not definition:
            continue
        tier = definition.get("tier")
        if type(tier) is not int or not 1 <= tier <= 12:
            continue
        candidates.append(
            copy.deepcopy(instance)
            | {
                "definition_id": str(definition["id"]),
                "acquired_tier": tier,
                "roles": list(definition.get("roles", [])),
                "tags": list(definition.get("tags", [])),
                "allow_duplicate_type": bool(
                    definition.get("allow_duplicate_type", False)
                ),
                "role_effects": copy.deepcopy(definition.get("role_effects", {})),
                "tianji_tags": copy.deepcopy(definition.get("tianji_tags", {})),
                "dynamic_definition": copy.deepcopy(definition)
                if isinstance(embedded, dict)
                else None,
                "source_kind": "material",
            }
        )
    plant_defs = deps._crafting_plant_defs()
    for item in player.inventory:
        definition = plant_defs.get(str(item.plant_id or ""))
        if not definition or item.quantity <= 0:
            continue
        # Four recipe positions need at most four representatives of a stack.
        # Keep the first address for existing selections; these are not items.
        for index in range(min(4, int(item.quantity))):
            candidates.append({
                "id": f"plant:{item.id}" + (f":{index}" if index else ''),
                "definition_id": f"plant:{item.plant_id}",
                "name": item.name,
                "quality": float(item.plant_quality or 0.5),
                "state": f"实生 {int(item.plant_years or 0):,} 年",
                "source": "洞府灵田采收",
                "origin_world": player.world,
                "material_value": int(item.plant_value or 1),
                "acquired_tier": _plant_material_tier(max(0, int(item.plant_years or 0))),
                "roles": list(definition.get("roles", [])),
                "tags": ["spirit_plant", str(item.plant_id)],
                "allow_duplicate_type": bool(
                    definition.get("allow_duplicate_type", False)
                ),
                "role_effects": copy.deepcopy(definition.get("role_effects", {})),
                "source_kind": "plant",
                "inventory_item_id": item.id,
                "quantity": item.quantity,
            })
    for item in player.inventory:
        tags = set(item.tags)
        source_rank = _guixu_material_tiers().get(item.id)
        if (
            item.quantity <= 0
            or "guixu_tide" not in tags
            or not tags.intersection({"crafting_material", "spirit_plant"})
            or source_rank is None
        ):
            continue
        potency = max(
            0.02,
            min(
                0.30,
                math.log10(
                    max(10.0, float(item.plant_value or item.combat_bonus or 10))
                )
                * 0.035,
            ),
        )
        roles = ["primary", "secondary", "quench"]
        role_effects = {
            "primary": {
                "design_multipliers": {"combat_power": 1.0 + potency},
                "description": f"主材：归墟灵性令战力设计值提高 {potency:.0%}。",
            },
            "secondary": {
                "design_multipliers": {
                    "max_hp": 1.0 + potency / 2,
                    "max_mp": 1.0 + potency / 2,
                },
                "description": f"辅材：HP 与 MP 设计值各提高 {potency / 2:.0%}。",
            },
            "quench": {
                "combat_effect": {
                    "player_stat_multipliers": {"breach": 1.0 + potency / 3}
                },
                "description": f"淬火：破法提高 {potency / 3:.0%}。",
            },
        }
        material_value = max(1, int(item.plant_value or max(10, item.combat_bonus)))
        # A recipe has four positions; stacked units share one definition and
        # condition. Four selectable representatives retain all legal recipes.
        for index in range(min(4, int(item.quantity))):
            candidates.append(
                {
                    "id": f"guixu:{item.id}:{index}",
                    "definition_id": item.id,
                    "name": item.name,
                    "quality": float(item.plant_quality or 1.0),
                    "state": "归墟天成",
                    "source": "归墟之潮",
                    "origin_world": source_rank[1],
                    "acquired_tier": source_rank[0],
                    "material_value": material_value,
                    "roles": roles,
                    "tags": list(tags),
                    "allow_duplicate_type": True,
                    "role_effects": role_effects,
                    "source_kind": "inventory",
                    "inventory_item_id": item.id,
                    "quantity": item.quantity,
                }
            )
    return candidates


def _resolve_crafting_selection(
    deps: CraftingMaterialsDependencies, player: Player, payload: dict[str, Any]
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    mold = deps._crafting_molds().get(str(payload.get("mold_id", "")))
    if not mold:
        raise ValueError("请选择一种合法胎模")
    candidate_map = {
        str(row["id"]): row for row in deps._crafting_material_candidates(player)
    }
    selected_ids = [
        str(payload.get("primary_id", "")),
        str(payload.get("secondary_a_id", "")),
        str(payload.get("secondary_b_id", "")),
        str(payload.get("quench_id", "")),
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
    inventory_costs = Counter(row['inventory_item_id'] for _, row in selected if row.get('inventory_item_id'))
    holdings = {item.id: item.quantity for item in player.inventory}
    if any(count > holdings.get(identity, 0) for identity, count in inventory_costs.items()):
        raise ValueError('行囊材料数量不足，不能重复占用同一份材料')
    secondary_defs = [selected[1][1]["definition_id"], selected[2][1]["definition_id"]]
    if secondary_defs[0] == secondary_defs[1] and not all(
        bool(selected[index][1].get("allow_duplicate_type")) for index in (1, 2)
    ):
        raise ValueError("这种材料不允许同时占用两个辅材位")
    return mold, selected
