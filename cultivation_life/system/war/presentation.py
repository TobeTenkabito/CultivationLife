from __future__ import annotations
from typing import Any
from ...models import GameState
from ...content_registry import RACE_DEFINITIONS
import copy
from .dependencies import WarPresentationDependencies


def _public_war_system(deps: WarPresentationDependencies, game: GameState) -> dict[str, Any]:
    wars = []
    visible_wars = [
        war for war in game.wars
        if game.debug_world_news or war.get("world") == game.player.world
    ]
    for war in reversed(visible_wars[-20:]):
        deps._ensure_war_shape(game, war)
        public = copy.deepcopy(war)
        public.pop("logistics", None)
        public["attacker_name"] = deps._war_side_name(game, war["kind"], war["attacker_id"])
        public["defender_name"] = deps._war_side_name(game, war["kind"], war["defender_id"])
        public["player_side"] = deps._player_war_side(game, war)
        from .logistics import public as public_logistics, action_quotes
        public["supplies"] = public_logistics(game, war, public["player_side"])
        public["supply_actions"] = action_quotes(game, war, public["player_side"])
        public["player_controls"] = war.get("status") in {"active", "peace_ready"} and deps._player_has_war_voice(game, war)
        public["can_participate"] = bool(
            war.get("status") == "active" and public["player_side"]
            and game.player.alive and not game.player.imprisonment and not game.pending_event
        )
        public["can_negotiate"] = int(war.get("battles", 0)) >= 2 or war.get("status") == "peace_ready"
        public["coalitions"] = {
            side: [{**row, "name": deps._war_side_name(game, war["kind"], row["id"])}
                   for row in war["coalitions"][side]]
            for side in ("attacker", "defender")
        }
        cooldown = int(deps._war_rules().get("ally_call_cooldown_units", 3))
        player_side = public["player_side"]
        callable_allies: list[dict[str, Any]] = []
        if player_side:
            for row in deps._allied_powers(game, war, player_side):
                prior = war["called_allies"].get(f"{player_side}:{row['id']}")
                if prior and (prior.get("accepted") or game.diplomacy_unit - int(prior.get("unit", 0)) < cooldown):
                    continue
                callable_allies.append({
                    **row, "name": deps._war_side_name(game, war["kind"], row["id"]),
                    "caller_name": deps._war_side_name(game, war["kind"], row["caller_id"]),
                    "chance_percent": round(float(row["chance"]) * 100),
                })
        public["callable_allies"] = callable_allies
        public["can_call_allies"] = bool(callable_allies)
        public["power_summary"] = {
            side: deps._war_power_profile(game, war, side) for side in ("attacker", "defender")
        }
        formation_contexts = deps._war_formation_contexts(game, war)
        public["formation_summary"] = {}
        for formation_side in ("attacker", "defender"):
            context = formation_contexts[formation_side]
            public["formation_summary"][formation_side] = {
                key: copy.deepcopy(context.get(key)) for key in (
                    "active", "name", "owner_name", "source_kind", "source_id", "integrity",
                    "modifier", "conditions", "stability", "core_nature", "metrics",
                )
            }
            public["power_summary"][formation_side]["formation_modifier"] = float(context["modifier"])
            public["power_summary"][formation_side]["effective_composite"] = round(
                float(public["power_summary"][formation_side]["composite"])
                * float(context["modifier"]), 1,
            )
        if war["kind"] == "race":
            public["third_parties"] = [
                {"id": race_id, "name": row["name"]} for race_id, row in RACE_DEFINITIONS.items()
                if war["world"] in row.get("worlds", []) and not deps._participant_side(war, race_id)
            ]
        else:
            public["third_parties"] = [
                {"id": sect.id, "name": sect.name} for sect in game.sects.values()
                if not sect.extinct and sect.world == war["world"] and not deps._participant_side(war, sect.id)
            ]
        public["roster"] = {
            side: [{"id": npc.id, "name": npc.name, "realm_name": deps._npc_realm_name(npc),
                    "combat_power": round(deps._npc_power(npc), 1), "alive": npc.alive,
                    "escaped": npc.id in set(war.get("escaped", {}).get(side, [])), "wounds": npc.wounds,
                    "owner_id": war["roster_owner"].get(npc.id, war[f"{side}_id"]),
                    "owner_name": deps._war_side_name(game, war["kind"], war["roster_owner"].get(npc.id, war[f"{side}_id"]))}
                   for npc_id in war.get("roster", {}).get(side, []) if (npc := deps._find_npc(game, npc_id))]
            for side in ("attacker", "defender")
        }
        if public.get("peace_offer"):
            for demand in public["peace_offer"].get("demands", []):
                demand["target_power_name"] = deps._war_side_name(game, war["kind"], demand.get("target_power_id", ""))
                victim = deps._find_npc(game, demand.get("target_id", ""))
                demand["target_name"] = victim.name if victim else ""
        wars.append(public)
    return {
        "wars": wars,
        "active_count": sum(
            war.get("status") in {"active", "peace_ready"} and war.get("world") == game.player.world
            for war in game.wars
        ),
        "terms": {
            key: {
                "name": value[0], "cost": value[1],
                "power_ratio": (
                    float(deps._war_rules().get("dissolve_power_ratio", 1.35)) if key == "dissolve"
                    else float(deps._war_rules().get("annex_power_ratio", 2.5)) if key == "annex" else None
                ),
            }
            for key, value in deps.WAR_TERM_DEFS.items()
        },
    }
