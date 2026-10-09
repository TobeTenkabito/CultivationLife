from __future__ import annotations
from typing import Any
from ...models import GameState
import copy
import random
from .dependencies import FormationNpcsDependencies


def _npc_formation_profile(
    deps: FormationNpcsDependencies,
    game: GameState,
    npc_id: str,
    *,
    detailed_spectrum: bool = False,
) -> dict[str, Any]:
    entry = game.npc_formations.get(str(npc_id), {})
    if not entry or float(entry.get("durability", 0.0)) <= 0:
        return deps.empty_formation_profile(str(entry.get("name", "")))
    slots = tuple(
        str(value) if value is not None else None
        for value in list(entry.get("slots", []))[:9]
    )
    return copy.deepcopy(
        deps._cached_npc_formation_profile(
            slots,
            round(float(entry.get("alpha", 0.55)), 8),
            str(entry.get("name", "无名九宫阵")),
            detailed_spectrum,
        )
    )


def _npc_formation_power_multiplier(
    deps: FormationNpcsDependencies, game: GameState, npc_id: str
) -> float:
    entry = game.npc_formations.get(str(npc_id), {})
    cap = float(deps._formation_rules().get("npc_formation_bonus_cap", 0.08))
    cached_bonus = entry.get("power_bonus")
    if cached_bonus is None:
        profile = deps._npc_formation_profile(game, npc_id)
        if not profile.get("active"):
            return 1.0
        bonuses = [
            max(0.0, float(value) - 1.0)
            for value in profile["static_player_multipliers"].values()
        ]
        raw = sum(bonuses) / max(1, len(bonuses)) + float(
            profile.get("round_rules", {}).get("dealt_bonus", 0.0)
        )
        cached_bonus = round(min(cap, raw), 6)
        # Persist only the compact derived scalar. Detailed matrices are
        # rebuilt for real combat, keeping both save size and off-screen
        # war simulation bounded.
        entry["power_bonus"] = cached_bonus
    bonus = max(0.0, min(cap, float(cached_bonus)))
    return 1.0 + bonus * max(0.0, min(1.0, float(entry.get("durability", 0.0)) / 100.0))


def _ensure_npc_formations(deps: FormationNpcsDependencies, game: GameState) -> bool:
    changed = False
    minimum = int(deps._formation_rules().get("npc_formation_min_realm", 2))
    living = {
        npc.id: npc
        for npc in deps._all_world_npcs(game)
        if npc.alive and npc.realm_index >= minimum
    }
    for npc_id in list(game.npc_formations):
        if npc_id not in living:
            game.npc_formations.pop(npc_id, None)
            changed = True
    definitions_by_world: dict[str, list[dict[str, Any]]] = {}
    for definition in deps._formation_material_defs().values():
        definitions_by_world.setdefault(
            str(definition.get("world", "human")), []
        ).append(definition)
    family_ids={n.id for n in game.family.npcs} if game.family else set()
    for npc_id, npc in living.items():
        existing = game.npc_formations.get(npc_id)
        if (
            existing
            and existing.get("world") == npc.world
            and int(existing.get("realm_index", -1)) == npc.realm_index
        ):
            # NPC arrays share the persistent-durability rule, but their
            # owners maintain them slowly while world time advances.  The
            # cap prevents a single century-long high-realm action from
            # instantly erasing all battle wear.
            last_year = int(existing.get("last_maintenance_year", game.player.age))
            elapsed = max(0, int(game.player.age) - last_year)
            if elapsed > 0:
                before = float(existing.get("durability", 0.0))
                # Repair is part of the organization's paid supply basket.
                # No separate per-NPC buying or free annual material recovery.
                organization = game.economy_v2.get('organizations', {}).get(f'organization:sect:{npc.faction_id}', {})
                if npc.id in family_ids:
                    organization = game.economy_v2.get('organizations', {}).get(f'organization:family:{game.family.id}', {})
                coverage = organization.get('maintenance_support',{}).get(str(npc.realm_index),0) if organization.get('last_year')==game.player.age else 0
                existing["durability"] = round(min(100.,before+min(12.,elapsed*.15)*coverage),4)
                existing["last_maintenance_year"] = int(game.player.age)
                changed = True
            continue
        pool = [
            row
            for row in definitions_by_world.get(npc.world, [])
            if int(row.get("tier", 1)) <= npc.realm_index + 2
        ] or definitions_by_world.get(npc.world, [])
        if not pool:
            continue
        rng = random.Random(
            f"{game.seed}:npc-formation-v2:{npc.id}:{npc.realm_index}:{npc.world}"
        )
        count = min(9, max(3, 2 + npc.realm_index // 2))
        positions = rng.sample(range(9), count)
        slots: list[str | None] = [None] * 9
        # Sampling with replacement is intentional: NPCs can own several
        # mundane nodes of one type, and equal natures guarantee a valid
        # relation even in worlds with a very small material catalogue.
        for position in positions:
            slots[position] = str(rng.choice(pool)["id"])
        alpha = float(deps._formation_rules().get("alpha_min", 0.5)) + min(
            0.30, npc.realm_index * 0.025
        )
        core_nature = str(pool[0].get("nature", "neutral"))
        durability = (
            float(existing.get("durability", rng.uniform(78.0, 100.0)))
            if existing
            else rng.uniform(78.0, 100.0)
        )
        game.npc_formations[npc_id] = {
            "name": f"{deps.NATURE_NAMES.get(core_nature, core_nature)}枢九宫阵",
            "world": npc.world,
            "realm_index": npc.realm_index,
            "slots": slots,
            "alpha": round(min(0.86, alpha), 4),
            "durability": round(max(0.0, min(100.0, durability)), 4),
            "battles": int(existing.get("battles", 0)) if existing else 0,
            "last_maintenance_year": int(game.player.age),
        }
        changed = True
    return changed
