from __future__ import annotations
from .definition_data import definition as _content_definition

from typing import Any, Final


# Bloodline traits are permanent bodily instincts. Their identifiers,
# presentation and combat hooks are deliberately separate from temporary
# transformation traits.
BLOODLINE_TRAIT_REGISTRY: Final[dict[str, dict[str, Any]]] = _content_definition(__name__, "BLOODLINE_TRAIT_REGISTRY")


# Every biological species receives its own sixteen-entry awakening library.
# The shared shapes keep balance auditable, while names and descriptions retain
# the species identity.  A full route has only twelve major evolutions, leaving
# at least four unrolled entries even at the current Da Luo cap.
_SPECIES_POOL_FLAVOR: Final[dict[str, tuple[str, str]]] = _content_definition(__name__, "_SPECIES_POOL_FLAVOR")
_POOL_ARCHETYPES: Final[tuple[tuple[str, str, str, dict[str, float]], ...]] = _content_definition(__name__, "_POOL_ARCHETYPES")


def _modifier_description(condition: str, multipliers: dict[str, float]) -> str:
    stat_names = {
        "might": "威能", "guard": "防护", "mobility": "身法",
        "sense": "神识", "sustain": "续航", "breach": "破法",
    }
    condition_text = {
        "always": "",
        "terrain_open": "在开阔战场中，",
        "terrain_narrow": "在狭窄战场中，",
        "terrain_dangerous": "在险要战场中，",
        "artificial_field": "战场存在禁空、禁神识或大阵时，",
    }[condition]
    bonuses = "、".join(
        f"{stat_names[stat]}提高{(multiplier - 1):.1%}"
        for stat, multiplier in multipliers.items()
    )
    return f"{condition_text}{bonuses}。"


for _species_id, (_prefix, _body) in _SPECIES_POOL_FLAVOR.items():
    for _slot, _suffix, _condition, _multipliers in _POOL_ARCHETYPES:
        _trait_id = f"bloodline_{_species_id}_pool_{_slot}"
        BLOODLINE_TRAIT_REGISTRY[_trait_id] = {
            "name": f"{_prefix}·{_suffix}",
            "description": f"{_body}进一步觉醒；{_modifier_description(_condition, _multipliers)}",
            "combat_hook": f"species_pool_{_species_id}_{_slot}",
            "condition": _condition,
            "multipliers": dict(_multipliers),
            "pool_species": _species_id,
        }


def public_bloodline_trait(trait_id: str) -> dict[str, str]:
    definition = BLOODLINE_TRAIT_REGISTRY.get(trait_id)
    if not definition:
        return {"id": trait_id, "name": trait_id, "description": ""}
    return {
        "id": trait_id,
        "name": str(definition["name"]),
        "description": str(definition["description"]),
    }


def bloodline_grants_hook(traits: set[str], combat_hook: str) -> bool:
    return any(
        BLOODLINE_TRAIT_REGISTRY.get(trait_id, {}).get("combat_hook") == combat_hook
        for trait_id in traits
    )


def bloodline_hook_names(traits: set[str], combat_hook: str) -> list[str]:
    return [
        str(BLOODLINE_TRAIT_REGISTRY[trait_id]["name"])
        for trait_id in traits
        if BLOODLINE_TRAIT_REGISTRY.get(trait_id, {}).get("combat_hook") == combat_hook
    ]


def bloodline_stat_modifiers(
    traits: set[str], *, natural_terrain: str, artificial_conditions: list[str],
) -> tuple[dict[str, float], list[str]]:
    factors = {stat: 1.0 for stat in ("might", "guard", "mobility", "sense", "sustain", "breach")}
    conditions = {
        "always": True,
        "terrain_open": natural_terrain == "开阔",
        "terrain_narrow": natural_terrain == "狭窄",
        "terrain_dangerous": natural_terrain == "险要",
        "artificial_field": bool(artificial_conditions),
    }
    triggered: list[str] = []
    for trait_id in sorted(traits):
        definition = BLOODLINE_TRAIT_REGISTRY.get(trait_id, {})
        multipliers = definition.get("multipliers", {})
        if not multipliers or not conditions.get(str(definition.get("condition")), False):
            continue
        for stat, multiplier in multipliers.items():
            if stat in factors:
                factors[stat] *= float(multiplier)
        triggered.append(trait_id)
    return factors, triggered
