from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from ...models import GameState
    from ..crafting_system import effective_tianji_combat_power, store_crafted_artifact
    from ..tianji_system import tianji_content_available, _stable_rng, _scaled_effects


class TianjiNpcMethods:
    def _tianji_persistent_npcs(self, game: GameState, world: str) -> list[Any]:
        values: list[Any] = [
            npc for npc in game.world_npcs.values() if npc.alive and npc.world == world
        ]
        values.extend(npc for npc in game.notable_npcs.values() if npc.alive and npc.world == world)
        for sect in game.sects.values():
            values.extend(npc for npc in sect.npcs if npc.alive and npc.world == world)
        unique: dict[str, Any] = {str(npc.id): npc for npc in values if getattr(npc, "id", None)}
        return list(unique.values())

    def _assign_tianji_holders_for_world(self, game: GameState, world: str) -> bool:
        state = game.tianji_state
        if not state.get("artifacts") or world in state.setdefault("holder_worlds_initialized", []):
            return False
        candidates = self._tianji_persistent_npcs(game, world)
        state["holder_worlds_initialized"].append(world)
        if not candidates:
            return True
        rng = _stable_rng(game.seed, f"holders:{world}")
        available = [
            row for row in state["artifacts"]
            if state.get("world_distribution", {}).get(row["id"], row["origin_world"]) == world
            and row["id"] not in state["holders"]
            and state["true_body_states"][row["id"]]["status"] == "unmanifested"
        ]
        rng.shuffle(available)
        rng.shuffle(candidates)
        count = min(len(candidates), len(available), max(1, min(4, len(candidates) // 4 + 1)))
        for index, (npc, artifact) in enumerate(zip(candidates[:count], available[:count])):
            true_body = index == 0 and int(artifact["rank"]) <= 30 and rng.random() < .42
            ratio = 1.0 if true_body else round(rng.uniform(.28, .86), 4)
            state["holders"][artifact["id"]] = {
                "npc_id": str(npc.id), "world": world,
                "kind": "true_body" if true_body else "replica", "replica_ratio": ratio,
            }
            if true_body:
                state["true_body_states"][artifact["id"]] = {
                    "status": "npc", "holder_ref": str(npc.id),
                }
        return True

    def _inject_tianji_npc_artifacts(self, game: GameState, target: dict[str, Any]) -> None:
        if not tianji_content_available():
            return
        if target.get("_tianji_injected"):
            return
        target["_tianji_injected"] = True
        self._ensure_tianji_state(game)
        holder_by_npc = {str(row["npc_id"]): (artifact_id, row) for artifact_id, row in game.tianji_state["holders"].items()}
        enemy_effects: list[dict[str, Any]] = list(target.get("enemy_artifact_effects", []))
        total_bonus = 0.0
        power_already_injected = bool(target.get("_tianji_power_injected"))
        ids = [str(target.get("npc_id", ""))]
        ids.extend(str(row.get("npc_id", "")) for row in target.get("members", []))
        for npc_id in dict.fromkeys(ids):
            held = holder_by_npc.get(npc_id)
            if not held:
                continue
            artifact_id, holder = held
            artifact = self._tianji_artifact(game.tianji_state, artifact_id)
            ratio = float(holder["replica_ratio"])
            bonus = effective_tianji_combat_power(
                int(artifact["base_combat_power"]) * ratio, game.player.world,
            )
            if not power_already_injected:
                total_bonus += bonus
            combat, _ = _scaled_effects(artifact["effects"], ratio)
            enemy_effects.extend(combat)
            self._tianji_reveal(game, artifact_id, 2, f"与持有者{npc_id}交战")
            for member in target.get("members", []):
                if str(member.get("npc_id", "")) == npc_id:
                    if not power_already_injected:
                        member["power"] = float(member.get("power", 0)) + bonus
                    member["tianji_artifact_name"] = artifact["name"]
        if total_bonus:
            target["target_power"] = float(target.get("target_power", 0)) + total_bonus
            target["enemy_artifact_effects"] = enemy_effects
        elif enemy_effects:
            target["enemy_artifact_effects"] = enemy_effects

    def _tianji_observe_npc(self, game: GameState, npc_id: str) -> None:
        if not tianji_content_available():
            return
        self._ensure_tianji_state(game)
        for artifact_id, holder in game.tianji_state["holders"].items():
            if str(holder.get("npc_id", "")) == str(npc_id):
                self._tianji_reveal(game, artifact_id, 1, f"目睹持宝者{npc_id}")

    def _tianji_preview_npc_power(self, game: GameState, target: dict[str, Any]) -> None:
        if not tianji_content_available() or target.get("_tianji_power_injected"):
            return
        self._ensure_tianji_state(game)
        holder_by_npc = {
            str(row["npc_id"]): (artifact_id, row)
            for artifact_id, row in game.tianji_state["holders"].items()
        }
        total = 0.0
        ids = [str(target.get("npc_id", ""))]
        ids.extend(str(row.get("npc_id", "")) for row in target.get("members", []))
        for npc_id in dict.fromkeys(ids):
            held = holder_by_npc.get(npc_id)
            if not held:
                continue
            artifact_id, holder = held
            artifact = self._tianji_artifact(game.tianji_state, artifact_id)
            bonus = effective_tianji_combat_power(
                int(artifact["base_combat_power"]) * float(holder["replica_ratio"]), game.player.world,
            )
            total += bonus
            for member in target.get("members", []):
                if str(member.get("npc_id", "")) == npc_id:
                    member["power"] = float(member.get("power", 0)) + bonus
        if total:
            target["target_power"] = float(target.get("target_power", 0)) + total
            target["target_power_display"] = float(target.get("target_power_display", target["target_power"])) + total
            target["_tianji_power_injected"] = True

    def _tianji_handle_npc_kill(self, game: GameState, npc_id: str) -> str:
        if not tianji_content_available() or not game.tianji_state:
            return ""
        found = next(((artifact_id, row) for artifact_id, row in game.tianji_state.get("holders", {}).items() if str(row.get("npc_id")) == str(npc_id)), None)
        if not found:
            return ""
        artifact_id, holder = found
        artifact = self._tianji_artifact(game.tianji_state, artifact_id)
        ratio = float(holder["replica_ratio"])
        is_true = holder["kind"] == "true_body"
        combat_effects, persistent = _scaled_effects(artifact["effects"], ratio)
        game.player.crafting_sequence += 1
        instance_id = f"tianji-loot-{game.id}-{game.player.crafting_sequence}"
        instance = {
            "id": instance_id, "name": artifact["name"] if is_true else f"仿·{artifact['name']}",
            "mold_id": artifact["mold_id"], "mold_name": self._tianji_config()["mold_nouns"][artifact["mold_id"]],
            "quality": "tianji_true" if is_true else "tianji_replica",
            "quality_name": "神机真体" if is_true else f"{ratio:.0%}仿品", "quality_multiplier": ratio,
            "creator_name": "未知古修", "created_year": game.player.age, "materials": [], "material_effects": [],
            "actual_stats": {"combat_power": round(int(artifact["base_combat_power"]) * ratio), **persistent},
            "combat_effects": combat_effects, "anchor_value": max(1, round(int(artifact["base_combat_power"]) * ratio / 12)),
            "description": f"你从持有者手中夺得的天工神机榜第 {artifact['rank']} 位法宝。",
            "is_natal": False, "tianji": {"definition_id": artifact_id, "kind": holder["kind"], "replica_ratio": ratio},
        }
        store_crafted_artifact(game.player, instance)
        game.tianji_state["player_artifacts"].append(instance_id)
        del game.tianji_state["holders"][artifact_id]
        if is_true:
            game.tianji_state["true_body_states"][artifact_id] = {"status": "player", "holder_ref": instance_id}
            self._tianji_reveal(game, artifact_id, 4, "击杀持有者并夺得真体")
        else:
            self._tianji_reveal(game, artifact_id, 3, "击杀持有者并取得仿品")
        return f" 你夺得天工神机【{instance['name']}】。"
