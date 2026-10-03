"""Explicit operations for catalog."""

from __future__ import annotations

import copy
import math

from ...content_registry import REALMS
from ...rules import expected_combat_power
from ..merchant_definitions import KINDS as KINDS
from ..path_modifiers import commission_duration
from .dependencies import MerchantCatalogDependencies


def _merchant_board(deps: MerchantCatalogDependencies, game, alliance):
    materials = deps._merchant_materials(alliance["world"])
    if not materials:
        return []
    cap = deps._merchant_realm_cap(alliance["world"])
    board = []
    for stars in range(1, 6):
        target_realm = max(0, cap - 5 + stars)
        power = expected_combat_power(target_realm, min(3, REALMS[target_realm].layers))
        definition = materials[min(len(materials) - 1, (stars - 1) * len(materials) // 5)]
        for kind_index, (kind, name) in enumerate(KINDS.items()):
            if kind in {"item", "spirit_manual"}:
                continue  # Item acquisition is a player-issued commission.
            identifier = f"{alliance['world']}:{alliance['id']}:{alliance['board_epoch']}:{kind}:{stars}"
            base_years = stars * 2 + kind_index % 3
            # Exact year durations, accelerated by realm without rounding to action units.
            years = max(1, math.ceil(base_years / (1 + max(0, game.player.realm_index - target_realm) * .7)))
            years = commission_duration(game, years)
            material_cost = int(definition["base_material_value"]) * stars
            value = max(100 * stars ** 2, int(power * .1), material_cost * 2)
            scale = 1 + min(.5, math.log10(max(1, deps._merchant_power(alliance))) / 20)
            reward = {
                "stones": round(value * scale * (1.8 if alliance["policy"] == "economy" else 1)),
                "materials": stars * (2 if alliance["policy"] == "materials" else 1),
                "opportunity": round((5 * stars + power ** .35) * (2 if alliance["policy"] == "cultivation" else 1), 1),
                "karma": stars * 3, "influence": stars * 12,
            }
            board.append({"id": identifier, "kind": kind, "name": name, "stars": stars,
                          "realm": target_realm, "power": round(power), "years": years,
                          "definition_id": definition["id"], "material_name": definition["name"],
                          "quantity": stars, "reward": reward, "policy": alliance["policy"],
                          "world": alliance["world"], "alliance_id": alliance["id"]})
    formation = sorted((row for row in deps._formation_material_defs().values() if row.get("world") == alliance["world"]), key=lambda row: (row["tier"], row["id"]))
    for original in list(board):
        if original["kind"] != "supply":
            continue
        original["material_category"] = "crafting"
        if formation:
            task = copy.deepcopy(original)
            definition = formation[min(len(formation) - 1, (task["stars"] - 1) * len(formation) // 5)]
            task.update(id=task["id"] + ":formation", material_category="formation",
                        reward_definition_id=task["definition_id"], definition_id=definition["id"], material_name=definition["name"])
            task["reward"]["stones"] = max(task["reward"]["stones"], math.ceil(definition["base_value"] * task["quantity"] * 1.2))
            board.append(task)
    return [row for row in board if row["id"] not in game.merchant_state["completed"]]
