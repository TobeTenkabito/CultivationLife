from __future__ import annotations
from typing import Any
from ...models import GameState
import copy
from ..formation_system import formation_config
from ..npc_system import npc_team_combat_power
from .dependencies import WarPowerDependencies


def _war_total_power(
    deps: WarPowerDependencies, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
) -> float:
    members = deps._available_warriors(game, war, side)
    powers = [
        deps._npc_power(npc) * deps._npc_formation_power_multiplier(game, npc.id) * (
            .5 + .5 * game.economy_v2.get('organizations', {}).get(
                f'organization:{"family" if game.family and npc.faction_id == game.family.id else "sect"}:{npc.faction_id}', {}).get('war_funding', 1.))
        for npc in members
    ]
    own_id = deps._war_player_identity(game, war)
    if (
        include_player and game.player.alive and game.player.world == war.get("world")
        and own_id in deps._coalition_ids(war, side)
    ):
        powers.append(deps._player_intrinsic_combat_power(game.player))
    guard_power = 0.0
    if side == "defender" and war.get("kind") == "sect":
        for sect_id in deps._coalition_ids(war, side):
            guard_power += deps._sect_guard_power(game, sect_id)
    # Guard arrays are anchored battlefield infrastructure, not a fourth
    # cultivator competing for one of the aggregate roster's three slots.
    power = (npc_team_combat_power(powers) if powers else 0.0) + guard_power
    if side == "defender":
        power *= 1 + float(deps._war_rules().get("defender_power_bonus", 0.10))
    return power


def _war_side_formation(deps: WarPowerDependencies, game: GameState, war: dict[str, Any], side: str) -> dict[str, Any]:
    """Pick one command array for the side; formations never stack by headcount."""
    candidates: list[dict[str, Any]] = []
    for npc in deps._available_warriors(game, war, side):
        entry = game.npc_formations.get(npc.id, {})
        profile = deps._npc_formation_profile(game, npc.id)
        if profile.get("active") and float(entry.get("durability", 0.0)) > 0:
            candidates.append({
                "profile": profile, "name": profile.get("name", "九宫阵"),
                "owner_name": npc.name, "source_kind": "npc", "source_id": npc.id,
                "integrity": max(0.0, min(1.0, float(entry.get("durability", 0.0)) / 100.0)),
            })
    if side == "defender" and war.get("kind") == "sect":
        for sect_id in deps._coalition_ids(war, side):
            array = deps._sect_guard_array(game, sect_id)
            if not array:
                continue
            profile = deps._ground_profile(game.player, array)
            if profile.get("active"):
                candidates.append({
                    "profile": profile, "name": profile.get("name", "护山阵"),
                    "owner_name": deps._war_side_name(game, war["kind"], sect_id),
                    "source_kind": "sect_guard", "source_id": str(array.get("id", "")),
                    "integrity": max(0.0, min(1.0, float(array.get("durability", 0.0)) / 100.0)),
                })
    if not candidates:
        return {
            "active": False, "name": "无阵", "owner_name": "", "source_kind": "none",
            "source_id": "", "integrity": 0.0, "modifier": 1.0, "conditions": [],
            "stability": "未成阵", "core_nature": "", "metrics": {}, "profile": {},
        }

    def command_score(row: dict[str, Any]) -> float:
        profile = row["profile"]
        static = sum(
            max(0.0, float(value) - 1.0)
            for value in profile.get("static_player_multipliers", {}).values()
        ) / 6.0
        return row["integrity"] * (
            deps._war_formation_metric_score(profile, side) + min(.14, static)
        )

    selected = max(candidates, key=command_score)
    profile = selected["profile"]
    selected.update({
        "active": True,
        "conditions": [
            str(value) for value in profile.get("artificial_conditions", []) if str(value) != "大阵"
        ],
        "stability": str(profile.get("stability", "低")),
        "core_nature": str((profile.get("core_node") or {}).get("nature", "")),
        "metrics": copy.deepcopy(profile.get("metrics", {})),
    })
    return selected


def _war_formation_modifier(
    deps: WarPowerDependencies, own: dict[str, Any], opponent: dict[str, Any], side: str,
) -> float:
    if not own.get("active"):
        return 1.0
    profile = own["profile"]
    rules = deps._war_rules()
    metric_score = deps._war_formation_metric_score(profile, side)
    static_score = min(1.0, sum(
        max(0.0, float(value) - 1.0)
        for value in profile.get("static_player_multipliers", {}).values()
    ) / (6.0 * .14))
    round_rules = profile.get("round_rules", {})
    rule_score = min(1.0, (
        float(round_rules.get("dealt_bonus", 0.0)) / .025
        + float(round_rules.get("enemy_morale_loss", 0.0)) / 2.4
        + float(round_rules.get("player_morale_loss_reduction", 0.0)) / .20
    ) / 3.0)
    integrity = max(0.0, min(1.0, float(own.get("integrity", 0.0))))
    bonus = integrity * (
        float(rules.get("formation_metric_weight", .075)) * metric_score
        + float(rules.get("formation_static_weight", .025)) * static_score
        + float(rules.get("formation_round_rule_weight", .015)) * rule_score
        + float(rules.get("formation_condition_weight", .010)) * len(own.get("conditions", []))
    )
    stability = own.get("stability")
    bonus += integrity * ({"高": .008, "中": .004, "低": 0.0}.get(stability, 0.0))
    if opponent.get("active") and own.get("core_nature") and opponent.get("core_nature"):
        relation = float(
            formation_config().get("relations", {})
            .get(own["core_nature"], {})
            .get(opponent["core_nature"], 0.0)
        )
        bonus += (
            float(rules.get("formation_relation_weight", .015))
            * relation * integrity * float(opponent.get("integrity", 0.0))
        )
    cap = max(0.0, float(rules.get("formation_war_bonus_cap", .12)))
    return round(1.0 + max(-cap, min(cap, bonus)), 6)


def _war_formation_contexts(deps: WarPowerDependencies, game: GameState, war: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contexts = {
        side: deps._war_side_formation(game, war, side) for side in ("attacker", "defender")
    }
    contexts["attacker"]["modifier"] = deps._war_formation_modifier(
        contexts["attacker"], contexts["defender"], "attacker",
    )
    contexts["defender"]["modifier"] = deps._war_formation_modifier(
        contexts["defender"], contexts["attacker"], "defender",
    )
    return contexts


def _war_power_profile(
    deps: WarPowerDependencies, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
) -> dict[str, float | int]:
    members = deps._available_warriors(game, war, side)
    total = deps._war_total_power(game, war, side, include_player=include_player)
    elite_rows = [(
        npc.realm_index,
        deps._npc_power(npc) * deps._npc_formation_power_multiplier(game, npc.id),
    ) for npc in members]
    own_id = deps._war_player_identity(game, war)
    if (
        include_player and game.player.alive and game.player.world == war.get("world")
        and own_id in deps._coalition_ids(war, side)
    ):
        elite_rows.append((game.player.realm_index, deps._player_intrinsic_combat_power(game.player)))
    elites = sorted(elite_rows, reverse=True)[:3]
    elite = npc_team_combat_power(power for _, power in elites) if elites else 0.0
    if side == "defender":
        elite *= 1 + float(deps._war_rules().get("defender_power_bonus", 0.10))
    total_weight = float(deps._war_rules().get("ai_total_power_weight", 0.68))
    composite = total * total_weight + elite * (1 - total_weight)
    return {
        "total": round(total, 1), "elite": round(elite, 1), "composite": round(composite, 1),
        "highest_realm": max((realm_index for realm_index, _ in elite_rows), default=0), "members": len(elite_rows),
    }


def _war_entity_power(deps: WarPowerDependencies, game: GameState, war: dict[str, Any], side: str, power_id: str) -> float:
    powers = [
        deps._npc_power(npc) * deps._npc_formation_power_multiplier(game, npc.id)
        for npc in deps._available_warriors(game, war, side, power_id)
    ]
    own_id = deps._war_player_identity(game, war)
    if game.player.alive and game.player.world == war.get("world") and own_id == power_id:
        powers.append(deps._player_intrinsic_combat_power(game.player))
    guard_power = (
        deps._sect_guard_power(game, power_id)
        if side == "defender" and war.get("kind") == "sect" else 0.0
    )
    return (npc_team_combat_power(powers) if powers else 0.0) + guard_power
