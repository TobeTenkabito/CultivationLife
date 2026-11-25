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
    from .combat_attributes import read
    from .traits import SPECIAL_EFFECTS, active
    if isinstance(technique_element, str):
        if technique_element in {"neutral","sex"}:
            return True
    elif technique_element.element in {"neutral","sex"} and not technique_element.required_affinities:
        return True
    if isinstance(root_id, str):
        affinities = set(root_elements(root_id))
        confluence = False
    else:
        root = read(root_id, "spirit_root", "none")
        affinities = set(root_elements(root) if LEGACY_ROOTS.get(root, root) in ROOT_DEFINITIONS else ()) | set(read(root_id, "additional_roots", ()))
        confluence = SPECIAL_EFFECTS["interchangeable_five_roots"] in active(root_id)
    return _affinities_allow_technique(affinities, technique_element, confluence)


def player_affinities(player: Player) -> list[str]:
    return list(dict.fromkeys([*root_elements(player.spirit_root), *player.additional_roots]))


def _affinities_allow_technique(affinities, technique, confluence=False):
    from .combat_attributes import FIVE
    element = technique.element if isinstance(technique, Technique) else technique
    required = set(technique.required_affinities) if isinstance(technique, Technique) else set()
    if element == "five_elements":
        required.update(FIVE)
    elif element not in {"neutral", "sex"}:
        required.add(element)
    if confluence:
        five = set(FIVE)
        return required - five <= affinities and len(required & five) <= len(affinities & five)
    return required <= affinities


def can_player_practice_technique(player: Player, technique_element: str | Technique) -> bool:
    return can_practice_technique(player, technique_element)
