from __future__ import annotations
from typing import Any
from ...models import HistoryRecord
from ...models import Player
from ...content_registry import REALMS
from ..crafted_artifact_rules import STAT_NAMES as STAT_NAMES
import copy
from ...runtime import decode_rng
from ...runtime import encode_rng
from ...rules import expected_combat_power
import math
from ...rules import max_hp
from ...rules import max_mp
from ...runtime import now_iso
from ...rules import remove_item
import uuid
from .dependencies import CraftingForgingDependencies


def forge_crafted_artifact(
    deps: CraftingForgingDependencies, game_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or not player.alive or player.imprisonment:
        raise ValueError("当前状态无法开炉炼器")
    preview = deps._crafting_preview(player, payload)
    # Preview has fully validated all four instance IDs. Consume only after every check passes.
    for material in preview["selected_materials"]:
        if material.get("source_kind") in {"plant", "inventory"}:
            if not remove_item(player, str(material["inventory_item_id"])):
                raise ValueError("行囊材料数量发生变化，请重新确认配方")
        else:
            stored = next(
                (
                    row
                    for row in player.crafting_materials
                    if str(row.get("id")) == str(material["id"])
                ),
                None,
            )
            if not stored:
                raise ValueError("炼器材料数量发生变化，请重新确认配方")
            player.crafting_materials.remove(stored)
    rng = decode_rng(game.seed, game.rng_state)
    quality = deps._weighted_choice(rng, preview["quality_probabilities"])
    game.rng_state = encode_rng(rng)
    name = str(payload.get("name", "")).strip()[:20] or str(
        preview["mold"]["default_name"]
    )
    player.crafting_sequence += 1
    artifact_id = f"crafted-{game.id}-{player.crafting_sequence}"
    artifact = {
        "id": artifact_id,
        "name": name,
        "mold_id": preview["mold"]["id"],
        "mold_name": preview["mold"]["name"],
        "quality": quality,
        "quality_name": preview["quality_names"][quality],
        "quality_multiplier": float(preview["quality_multipliers"][quality]),
        "creator_name": player.name,
        "creator_id": game.id,
        "created_year": player.age,
        "scaling_realm_index": preview["scaling_realm_index"],
        "scaling_realm_name": preview["scaling_realm_name"],
        "scaling_benchmarks": preview["scaling_benchmarks"],
        "materials": [
            {
                key: row.get(key)
                for key in (
                    "id",
                    "definition_id",
                    "name",
                    "quality",
                    "state",
                    "source",
                    "origin_world",
                    "material_value",
                )
            }
            for row in preview["selected_materials"]
        ],
        "material_effects": preview["material_effects"],
        "allocations": preview["allocations"],
        "designed_stats": preview["designed_stats"],
        "actual_stats": preview["theoretical_stats"][quality],
        "combat_effects": preview["combat_effects"],
        "anchor_value": preview["anchor_value"],
        "mold_rule_description": str(preview["mold"]["rule"].get("description", "")),
        "is_natal": False,
    }
    deps.store_crafted_artifact(player, artifact)
    deps._grant_art_experience(
        player,
        "refining",
        float(deps._crafting_rules().get("refining_experience_per_craft", 30)),
    )
    game.history.append(
        HistoryRecord(
            "SYS_ARTIFACT_FORGE",
            1,
            player.age,
            "组合炼器",
            artifact_id,
            "forged",
            f"你以{preview['mold']['name']}定形，炼成{artifact['quality_name']}法宝“{name}”；炼制不会失败，材料锚定价值为 {artifact['anchor_value']:,} 灵石。",
            {
                "artifact_id": artifact_id,
                "quality": quality,
                "anchor_value": artifact["anchor_value"],
            },
            ["system", "crafting", "art:refining"],
        )
    )
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def save_crafting_blueprint(
    deps: CraftingForgingDependencies, game_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    game = deps._load(game_id)
    preview = deps._crafting_preview(game.player, payload)
    blueprint = {
        "id": f"blueprint-{uuid.uuid4().hex}",
        "name": (
            str(payload.get("blueprint_name", "")).strip()[:20]
            or f"{preview['mold']['default_name']}图谱"
        ),
        "mold_id": preview["mold"]["id"],
        "material_types": [
            row["definition_id"] for row in preview["selected_materials"]
        ],
        "allocations": preview["allocations"],
        "created_year": game.player.age,
    }
    game.player.crafting_blueprints.append(blueprint)
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
