from __future__ import annotations
from typing import Any
from ...models import GameState
from ..crafted_artifact_rules import STAT_NAMES as STAT_NAMES
from ..crafted_artifact_rules import (
    active_crafted_artifacts as active_crafted_artifacts,
)
import copy
from ..crafted_artifact_rules import (
    crafted_artifact_bonuses as crafted_artifact_bonuses,
)
from ..crafted_artifact_rules import (
    effective_tianji_combat_power as effective_tianji_combat_power,
)
from ..crafted_artifact_rules import (
    tianji_world_combat_power_cap as tianji_world_combat_power_cap,
)
from .dependencies import CraftingPresentationDependencies


def _public_crafting_system(
    deps: CraftingPresentationDependencies, game: GameState
) -> dict[str, Any]:
    player = game.player
    rules = deps._crafting_rules()
    candidates = deps._crafting_material_candidates(player)
    active_ids = {str(active.get("id")) for active in active_crafted_artifacts(player)}
    world_combat_cap = tianji_world_combat_power_cap(player.world)
    artifacts = []
    for row in player.crafted_artifacts:
        if not any(
            item.crafted_artifact_id == str(row.get("id")) and item.quantity > 0
            for item in player.inventory
        ):
            continue
        public = copy.deepcopy(row)
        public["equipped"] = str(row.get("id")) in active_ids
        if row.get("tianji"):
            raw_power = max(
                0.0, float(row.get("actual_stats", {}).get("combat_power", 0.0))
            )
            if row.get("is_natal"):
                raw_power += max(0.0, float(player.natal_artifact_combat_bonus))
            public["raw_combat_power"] = round(raw_power, 1)
            public["effective_combat_power"] = round(
                effective_tianji_combat_power(raw_power, player.world),
                1,
            )
            public["world_combat_power_cap"] = (
                round(world_combat_cap) if world_combat_cap is not None else None
            )
        artifacts.append(public)
    return {
        "visible": bool(deps.crafting_config())
        and player.realm_index >= int(rules.get("minimum_realm", 1)),
        "molds": list(copy.deepcopy(deps._crafting_molds()).values()),
        "materials": candidates,
        "artifacts": artifacts,
        "blueprints": copy.deepcopy(player.crafting_blueprints),
        "active_count": len(active_crafted_artifacts(player)),
        "budget": int(
            rules.get("budget_by_realm", [40] * 13)[max(0, min(12, player.realm_index))]
        ),
        "stat_costs": copy.deepcopy(rules.get("stat_costs", {})),
        "stat_names": STAT_NAMES,
        "quality_names": copy.deepcopy(rules.get("quality_names", {})),
        "bonuses": crafted_artifact_bonuses(player),
        "auction_available": bool(
            game.auction_state.get("status") in {"scheduled", "open"}
            and deps._auction_location_matches(game)
        ),
    }
