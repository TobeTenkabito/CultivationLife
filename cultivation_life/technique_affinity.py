"""Shared root eligibility for cultivation, combat, and linked secrets."""
from typing import Any
from .models import Player, Technique
from .content_registry import ROOT_DEFINITIONS

LEGACY_ROOTS = {
    "metal": "supreme_metal", "wood": "supreme_wood", "water": "supreme_water",
    "fire": "supreme_fire", "earth": "supreme_earth", "mutated": "mutated_thunder",
    "heavenly": "heavenly_metal_wood",
}



def root_definition(root_id: str) -> dict[str, Any]:
    return ROOT_DEFINITIONS[LEGACY_ROOTS.get(root_id, root_id)]


def root_elements(root_id: str) -> list[str]:
    return list(root_definition(root_id)["elements"])


def can_practice_technique(root_id: str, technique_element: str | Technique) -> bool:
    """无属性功法不限灵根；五行功法必须命中灵根的五行属性。"""
    if (isinstance(technique_element, str) and technique_element in {'neutral', 'sex'}
            or isinstance(technique_element, Technique) and technique_element.element in {'neutral', 'sex'} and not technique_element.required_affinities):
        return True
    return _affinities_allow_technique(set(root_elements(root_id)), technique_element)


def player_affinities(player: Player) -> list[str]:
    return list(dict.fromkeys([*root_elements(player.spirit_root), *player.additional_roots]))


def _affinities_allow_technique(affinities: set[str], technique: str | Technique) -> bool:
    element = technique.element if isinstance(technique, Technique) else technique
    required = technique.required_affinities if isinstance(technique, Technique) else ()
    if not set(required) <= affinities:
        return False
    if element in {"neutral", "sex"}:
        return True
    if element == "five_elements":
        return {"metal", "wood", "water", "fire", "earth"} <= affinities
    return element in affinities


def can_player_practice_technique(player: Player, technique_element: str | Technique) -> bool:
    if (isinstance(technique_element, str) and technique_element in {'neutral', 'sex'}
            or isinstance(technique_element, Technique) and technique_element.element in {'neutral', 'sex'} and not technique_element.required_affinities):
        return True
    return _affinities_allow_technique(set(player_affinities(player)), technique_element)


