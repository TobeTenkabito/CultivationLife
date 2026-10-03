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
from .dependencies import CraftingPreviewDependencies


def _crafting_preview(
    deps: CraftingPreviewDependencies, player: Player, payload: dict[str, Any]
) -> dict[str, Any]:
    rules = deps._crafting_rules()
    mold, selected = deps._resolve_crafting_selection(player, payload)
    mold = deps._resolve_mold_rule(player, mold, selected)
    budget = int(rules["budget_by_realm"][max(0, min(12, player.realm_index))])
    raw_allocations = (
        payload.get("allocations", {})
        if isinstance(payload.get("allocations"), dict)
        else {}
    )
    allocations = {
        key: max(0, int(raw_allocations.get(key, 0) or 0)) for key in STAT_NAMES
    }
    used = sum(
        allocations[key] * float(rules["stat_costs"][key]) for key in allocations
    )
    if used <= 0:
        raise ValueError("至少为法宝分配一项属性")
    if used > budget + 1e-9:
        raise ValueError(f"属性预算超出上限：已用 {used:.1f} / {budget}")
    primary_tier = int(selected[0][1].get("acquired_tier", player.realm_index))
    scaling_realm_index = max(0, min(player.realm_index, primary_tier, len(REALMS) - 1))
    scaling_layer = (
        player.layer
        if scaling_realm_index == player.realm_index
        else max(1, REALMS[scaling_realm_index].layers)
    )
    # Anchor absolute output to the recipe's main-material stage, not a
    # flat +1 and not the wearer's already-equipped bonuses.  This keeps
    # Qi artifacts legible while making immortal artifacts scale against
    # immortal combat numbers without recursive forge-to-forge inflation.
    benchmark = Player(
        "炼器境界基准",
        player.spirit_root,
        realm_index=scaling_realm_index,
        layer=scaling_layer,
        path=player.path,
    )
    expected = expected_combat_power(scaling_realm_index, scaling_layer)
    stat_bases = {
        "combat_power": expected,
        "max_hp": max_hp(benchmark),
        "max_mp": max_mp(benchmark),
        "opportunity_efficiency": 1.0,
        "body_training_efficiency": 1.0,
        "divine_sense_efficiency": 1.0,
        "tribulation_reduction": 1.0,
        "breakthrough_bonus": 1.0,
    }
    designed = {
        key: stat_bases[key]
        * float(rules["stat_caps"][key])
        * allocations[key]
        * float(rules["stat_costs"][key])
        / max(1, budget)
        for key in STAT_NAMES
    }
    special_stats = {key: 0.0 for key in STAT_NAMES}
    combat_effects = [
        copy.deepcopy(mold["rule"].get("combat_effect", {}))
        | {"source": mold["rule"]["name"]}
    ]
    material_effects = []
    for role, material in selected:
        effect = copy.deepcopy(material.get("role_effects", {}).get(role, {}))
        for key, multiplier in effect.get("design_multipliers", {}).items():
            if key in designed:
                designed[key] *= max(0.0, float(multiplier))
        potency = min(
            1.25,
            max(
                0.65,
                math.sqrt(
                    max(1.0, float(material["material_value"]))
                    / max(
                        1.0,
                        float(material["material_value"])
                        / max(0.01, float(material["quality"])),
                    )
                ),
            ),
        )
        for key, value in effect.get("special_stats", {}).items():
            if key in special_stats:
                special_stats[key] += float(value) * potency
        if effect.get("combat_effect"):
            combat_effects.append(
                copy.deepcopy(effect["combat_effect"])
                | {
                    "source": f"{material['name']}·{role}",
                }
            )
        material_effects.append(
            {
                "role": role,
                "material_id": material["definition_id"],
                "instance_id": material["id"],
                "name": material["name"],
                "description": str(effect.get("description", "")),
            }
        )
    average_quality = sum(float(row[1]["quality"]) for row in selected) / 4
    refining_exp = max(0.0, float(player.art_experience.get("refining", 0.0)))
    refining_level = int(
        math.sqrt(refining_exp / float(rules.get("refining_experience_base", 100)))
    )
    probabilities = deps._quality_probabilities(refining_level, average_quality)
    caps = rules["stat_caps"]
    theoretical = {}
    for quality, multiplier in rules["quality_multipliers"].items():
        stats = {}
        for key in STAT_NAMES:
            value = designed[key] * float(multiplier) + special_stats[key]
            if key == "breakthrough_bonus":
                value = min(float(caps[key]), value)
            elif key == "tribulation_reduction":
                value = min(0.50, value)
            stats[key] = round(
                value, 4 if key not in {"combat_power", "max_hp", "max_mp"} else 1
            )
        theoretical[quality] = stats
    anchor = max(
        1,
        round(
            sum(int(row[1]["material_value"]) for row in selected)
            * float(rules["anchor_multiplier"])
        ),
    )
    return {
        "mold": copy.deepcopy(mold),
        "selected_materials": [copy.deepcopy(row) for _, row in selected],
        "material_effects": material_effects,
        "allocations": allocations,
        "budget": budget,
        "budget_used": round(used, 2),
        "designed_stats": {key: round(value, 4) for key, value in designed.items()},
        "scaling_realm_index": scaling_realm_index,
        "scaling_realm_name": REALMS[scaling_realm_index].name,
        "scaling_benchmarks": {
            "combat_power": round(expected, 1),
            "max_hp": max_hp(benchmark),
            "max_mp": max_mp(benchmark),
        },
        "special_stats": {key: round(value, 4) for key, value in special_stats.items()},
        "quality_probabilities": probabilities,
        "quality_names": copy.deepcopy(rules["quality_names"]),
        "quality_multipliers": copy.deepcopy(rules["quality_multipliers"]),
        "theoretical_stats": theoretical,
        "combat_effects": combat_effects,
        "anchor_value": anchor,
        "refining_level": refining_level,
    }


def preview_crafting(
    deps: CraftingPreviewDependencies, game_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    game = deps._load(game_id)
    if game.pending_event or not game.player.alive or game.player.imprisonment:
        raise ValueError("当前状态无法开炉炼器")
    return deps._crafting_preview(game.player, payload)
