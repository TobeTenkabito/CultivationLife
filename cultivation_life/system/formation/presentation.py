from __future__ import annotations
from typing import Any
from ...models import GameState
from ...content_registry import WORLD_SYSTEMS
import copy
from .dependencies import FormationPresentationDependencies


def _public_formation_system(
    deps: FormationPresentationDependencies, game: GameState
) -> dict[str, Any]:
    player = game.player
    deps.ensure_formation_state(player)
    profile = deps.active_formation_profile(player)
    supplies = []
    for supply_id, quantity in player.formation_repair_supplies.items():
        definition = deps._formation_maintenance_defs().get(supply_id)
        if definition and quantity > 0:
            supplies.append(
                {
                    **copy.deepcopy(definition),
                    "quantity": int(quantity),
                    "world_name": WORLD_SYSTEMS.get("world_names", {}).get(
                        str(definition.get("world")), str(definition.get("world"))
                    ),
                }
            )
    return {
        "visible": bool(deps.formation_config()),
        "system_version": int(deps.formation_config().get("system_version", 1)),
        "grid_size": 9,
        "level": deps.formation_level(player),
        "experience": round(float(player.art_experience.get("formation", 0.0)), 2),
        "alpha": round(deps.formation_alpha(player), 6),
        "materials": deps._formation_candidates(player),
        "loadouts": copy.deepcopy(player.formation_loadouts),
        "active_formation_id": player.active_formation_id,
        "active_bindings": [
            (
                {
                    key: binding.get(key)
                    for key in (
                        "id",
                        "definition_id",
                        "name",
                        "nature",
                        "nature_name",
                        "formation_value",
                        "source_kind",
                        "source",
                        "slot",
                    )
                }
                if binding
                else None
            )
            for binding in player.formation_active_bindings
        ],
        "profile": profile,
        "ground_arrays": [
            deps._ground_array_public(player, row)
            for row in player.formation_ground_arrays
        ],
        "repair_supplies": supplies,
        "current_location": {
            "world": player.world,
            "world_name": WORLD_SYSTEMS.get("world_names", {}).get(
                player.world, player.world
            ),
            "location_id": player.location_id,
            "location_name": deps.maps.location(player.world, player.location_id)[
                "name"
            ],
        },
        "can_deploy_personal": bool(profile.get("active")),
        "can_deploy_sect": bool(
            profile.get("active")
            and game.player.faction_id
            and (
                deps._intrigue_has_control(game, "sect", str(game.player.faction_id))
                if deps._intrigue_enabled()
                else deps._has_sect_voice(game)
            )
        ),
    }
