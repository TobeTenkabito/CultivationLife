from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import copy
    from typing import Any
    from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS
    from ...models import GameState
    from ...tianji_theme_rules import gameplay_debug_row
    from ..crafting_system import effective_tianji_combat_power, tianji_world_combat_power_cap
    from ..tianji_system import tianji_content_available, _tianji_effect_description


class TianjiPresentationMethods:
    @staticmethod
    def _tianji_public_effect(effect: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(effect["name"]), "description": _tianji_effect_description(effect),
            "trigger": str(effect.get("trigger", "combat_start")),
            "replica_scaling": str(effect.get("replica_scaling", "numeric")),
        }

    def _public_tianji(self, game: GameState) -> dict[str, Any]:
        if not tianji_content_available():
            return {"available": False}
        self._ensure_tianji_state(game)
        state = game.tianji_state
        material_names = {row["id"]: row["name"] for row in state["materials"]}
        world_combat_cap = tianji_world_combat_power_cap(game.player.world)
        rows = []
        for artifact in state["artifacts"]:
            level = int(state["knowledge"].get(artifact["id"], 0))
            public: dict[str, Any] = {
                "id": artifact["id"], "rank": artifact["rank"], "knowledge_level": level,
                "name": artifact["name"] if level >= 1 else "???",
                "mold_id": artifact["mold_id"] if level >= 1 else None,
                "mold_name": self._tianji_config()["mold_nouns"].get(artifact["mold_id"], "未知") if level >= 1 else "???",
                "base_combat_power": artifact["base_combat_power"] if level >= 2 else None,
                "current_world_combat_power": (
                    round(effective_tianji_combat_power(artifact["base_combat_power"], game.player.world))
                    if level >= 2 else None
                ),
                "effects": [self._tianji_public_effect(row) for row in artifact["effects"]] if level >= 2 else None,
                "description": artifact["description"] if level >= 2 else "???",
                "gameplay_tendency": (
                    str(artifact.get("gameplay_blueprint", {}).get("tendency", "")) or None
                ) if level >= 2 else None,
                "effect_groups": ({
                    "foundation": [self._tianji_public_effect(artifact["effects"][0])] if artifact.get("effects") else [],
                    "core": [self._tianji_public_effect(row) for row in artifact.get("effects", [])[1:4]],
                    "derived": [self._tianji_public_effect(row) for row in artifact.get("effects", [])[4:]],
                } if level >= 2 else None),
                "recipe_clues": (
                    [state["materials"][next(i for i, row in enumerate(state["materials"]) if row["id"] == mid)]["tags"][1:3] for mid in artifact["recipe"]]
                    if level == 3 else None
                ),
                "recipe": [material_names[mid] for mid in artifact["recipe"]] if level >= 4 else None,
                "recipe_ids": list(artifact["recipe"]) if level >= 4 else None,
                "origin_world_name": WORLD_SYSTEMS["world_names"].get(artifact["origin_world"], artifact["origin_world"]) if level >= 2 else "???",
                "true_body_status": copy.deepcopy(state["true_body_states"].get(artifact["id"])) if level >= 4 else None,
                "holder": None,
            }
            if level >= 5:
                holder = state["holders"].get(artifact["id"])
                if holder:
                    npc = self._find_npc(game, str(holder["npc_id"]))
                    public["holder"] = {
                        "name": npc.name if npc else "行踪不明", "world_name": WORLD_SYSTEMS["world_names"].get(holder["world"], holder["world"]),
                        "kind": holder["kind"], "replica_ratio": holder["replica_ratio"],
                    }
                else:
                    public["holder"] = {"name": "暂无可追踪持有人"}
            rows.append(public)
        # Rankings use frozen divine-artifact power; cultivation must never
        # rewrite a world's original hundred definitions or recipes.
        ranking_power = {a["id"]: float(a["base_combat_power"]) for a in state["artifacts"]}
        player_artifacts = list(game.player.crafted_artifacts)
        for item in game.player.inventory:
            if not item.crafted_artifact_id and self._natal_artifact_candidate(item):
                player_artifacts.append({"id": f"inventory:{item.id}", "name": item.name,
                                         "description": item.description, "actual_stats": {"combat_power": item.combat_bonus}})
        natal = game.natal_artifact
        if natal and not natal.get("crafted_artifact_id") and natal.get("item_id") in ITEM_CATALOG:
            item = ITEM_CATALOG[natal["item_id"]]
            player_artifacts.append({"id": f"natal:{item.id}", "name": natal["name"],
                                     "description": item.description,
                                     "actual_stats": {"combat_power": game.player.natal_artifact_combat_bonus}})
        for artifact in player_artifacts:
            if artifact.get("tianji"):
                continue
            power = float(artifact.get("actual_stats", {}).get("combat_power", 0))
            if artifact.get("is_natal"):
                power += game.player.natal_artifact_combat_bonus
            if power < min(ranking_power.values(), default=float("inf")):
                continue
            ranking_power[artifact["id"]] = power
            rows.append({"id": artifact["id"], "rank": 0, "knowledge_level": 2,
                         "name": artifact["name"], "base_combat_power": round(power),
                         "current_world_combat_power": round(power), "mold_name": "自炼法宝",
                         "description": artifact.get("description", ""), "effects": [],
                         "origin_world_name": WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
                         "holder": {"name": game.player.name}, "player_crafted": True})
        rows.sort(key=lambda row: (-ranking_power[row["id"]], row["id"]))
        for index, row in enumerate(rows, 1):
            row["rank"] = index
        # Falling out of the top hundred must not remove a learned recipe.
        targets = [{"id": row["id"], "rank": row["rank"], "name": row["name"],
                    "knowledge_level": row["knowledge_level"]}
                   for row in rows if row["knowledge_level"] >= 3 and not row.get("player_crafted")]
        rows = rows[:int(self._tianji_config()["artifact_count"])]
        discovered = set(state.get("discovered_material_ids", []))
        owned_definitions = {
            str(row.get("tianji", {}).get("definition_id"))
            for row in game.player.crafted_artifacts if row.get("tianji")
        }
        active_instance = str(state.get("activated_artifact_id") or "")
        active_definition = next((
            str(row.get("tianji", {}).get("definition_id"))
            for row in game.player.crafted_artifacts if str(row.get("id")) == active_instance
        ), None)
        return {
            "available": True, "name": "神机百变：巧夺天工", "generation_version": state["generation_version"],
            "world_name":WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world),
            "world_combat_power_cap":round(world_combat_cap) if world_combat_cap is not None else None,
            "artifacts": rows, "known_count": sum(int(level) > 0 for level in state["knowledge"].values()),
            "targets": targets,
            "activated_artifact_id": state.get("activated_artifact_id"),
            "owned_artifact_ids": list(state.get("player_artifacts", [])),
            "owned_definition_ids": sorted(owned_definitions),
            "active_definition_id": active_definition,
            "materials": [copy.deepcopy(row) for row in state["materials"] if row["id"] in discovered],
            "discovery_log": copy.deepcopy(state.get("discovery_log", [])[-20:]),
        }

    def debug_tianji_gameplay(self, game_id: str) -> list[dict[str, Any]]:
        """Return blueprint diagnostics without mutating the frozen definitions."""
        game = self._load(game_id)
        if not tianji_content_available():
            return []
        self._ensure_tianji_state(game)
        return [gameplay_debug_row(artifact) for artifact in game.tianji_state.get("artifacts", [])]
