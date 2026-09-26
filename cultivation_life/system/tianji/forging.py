from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import copy
    import random
    import uuid
    from typing import Any
    from ...content_registry import REALMS, WORLD_SYSTEMS
    from ...models import GameState, HistoryRecord
    from ...rules import remove_item
    from ...runtime import now_iso
    from ..crafting_system import (
        effective_tianji_combat_power,
        store_crafted_artifact,
        tianji_world_combat_power_cap,
    )
    from ..tianji_system import tianji_content_available, _stable_rng, _scaled_effects
    from .. import tianji_system as _source
    SLOT_WEIGHTS = _source.SLOT_WEIGHTS


class TianjiForgingMethods:
    def _tianji_material_instance(self, game: GameState, definition: dict[str, Any], rng: random.Random, source: str) -> dict[str, Any]:
        quality = round(rng.uniform(.72, 1.25), 4)
        embedded = copy.deepcopy(definition)
        return {
            "id": f"tianji-material-{uuid.uuid4().hex}", "material_id": definition["id"],
            "name": definition["name"], "quality": quality,
            "state": "道韵圆满" if quality >= 1.15 else "灵机充盈" if quality >= .95 else "灵性稍损",
            "source": source, "origin_world": game.player.world,
            "material_value": max(1, round(int(definition["base_material_value"]) * quality)),
            "acquired_tier": int(definition["tier"]), "dynamic_definition": embedded,
            "tianji_tags": copy.deepcopy(definition["tianji_tags"]),
        }

    def _append_tianji_market_offers(self, game: GameState, offers: list[dict[str, Any]], *, tier: int, market_name: str, location_id: str) -> None:
        if not tianji_content_available():
            return
        self._ensure_tianji_state(game)
        rng = _stable_rng(game.seed, f"material-market:{game.player.world}:{location_id}:{game.player.age}")
        definitions = [
            row for row in game.tianji_state["materials"]
            if (row["world"] == game.player.world or game.player.world in game.tianji_state.get("material_extra_worlds", {}).get(row["id"], []))
            and int(row["tier"]) <= max(tier, game.player.realm_index) + 1
        ]
        if not definitions:
            return
        for index, definition in enumerate(rng.sample(definitions, min(2, len(definitions)))):
            instance = self._tianji_material_instance(game, definition, rng, f"{market_name}购得")
            offers.append({
                "id": f"{game.player.world}-{location_id}-{game.player.age}-tianji-{index}-{definition['id']}",
                "kind": "crafting_material", "content_id": definition["id"], "name": definition["name"],
                "description": f"神机材料 · {instance['state']} · 可参与普通炼器和神机目标炼制。",
                "price": max(1, round(instance["material_value"] * rng.uniform(.9, 1.15))),
                "tier": tier, "tier_name": REALMS[max(0, min(len(REALMS) - 1, tier))].name,
                "market_name": market_name, "world": game.player.world, "location_id": location_id,
                "rare_next_tier": False, "sold": False, "material_instance": instance,
                "tianji_material_id": definition["id"],
            })

    def _tianji_material_bought(self, game: GameState, instance: dict[str, Any]) -> None:
        material_id = str(instance.get("material_id", ""))
        known = game.tianji_state.setdefault("discovered_material_ids", [])
        if material_id.startswith("tianji-mat-") and material_id not in known:
            known.append(material_id)

    @staticmethod
    def _tianji_tag_similarity(required: dict[str, float], supplied: dict[str, float]) -> float:
        if not required or not supplied:
            return 0.0
        shared = set(required).intersection(supplied)
        if not shared:
            return 0.0
        numerator = sum(min(float(required[key]), float(supplied[key])) for key in shared)
        denominator = max(1e-9, sum(float(value) for value in required.values()))
        return min(1.0, numerator / denominator)

    @staticmethod
    def _tianji_closeness_factor(closeness: float) -> float:
        points = ((0.0, .15), (.2, .30), (.4, .55), (.6, .80), (.8, 1.0), (1.0, 1.20))
        value = max(0.0, min(1.0, closeness))
        for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
            if value <= right_x:
                progress = (value - left_x) / max(.0001, right_x - left_x)
                return left_y + (right_y - left_y) * progress
        return 1.20

    def _tianji_target_preview(self, game: GameState, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_tianji_state(game)
        artifact = self._tianji_artifact(game.tianji_state, str(payload.get("target_artifact_id", "")))
        knowledge = int(game.tianji_state["knowledge"].get(artifact["id"], 0))
        if knowledge < 3:
            raise ValueError("目标法宝情报至少达到 Lv3 才能进行目标炼制")
        mold, selected = self._resolve_crafting_selection(game.player, payload)
        if mold["id"] != artifact["mold_id"]:
            raise ValueError("胎模错误，无法形成该神机法宝的结构；材料尚未消耗")
        definitions = {row["id"]: row for row in game.tianji_state["materials"]}
        exact = []
        similarities = []
        for (_, supplied), required_id in zip(selected, artifact["recipe"]):
            supplied_id = str(supplied["definition_id"])
            required = definitions[required_id]
            supplied_tags = supplied.get("tianji_tags")
            if not isinstance(supplied_tags, dict):
                embedded = supplied.get("dynamic_definition", {})
                supplied_tags = embedded.get("tianji_tags", {}) if isinstance(embedded, dict) else {}
            is_exact = supplied_id == required_id
            exact.append(is_exact)
            similarities.append(1.0 if is_exact else self._tianji_tag_similarity(required["tianji_tags"], supplied_tags))
        closeness = sum(weight * value for weight, value in zip(SLOT_WEIGHTS, similarities))
        world_cap = float(self._tianji_config()["world_replica_caps"].get(game.player.world, .20))
        quality_factor = max(.82, min(1.0, sum(float(row[1].get("quality", 1.0)) for row in selected) / 4))
        replica_ratio = min(world_cap * 1.20, world_cap * self._tianji_closeness_factor(closeness) * quality_factor)
        forge_kind = str(payload.get("forge_kind", "replica"))
        if forge_kind == "true_body":
            if knowledge < 4:
                raise ValueError("掌握 Lv4 完整真方后才能炼制本体")
            if not all(exact):
                raise ValueError("炼制本体要求四份材料与真方完全一致")
            body = game.tianji_state["true_body_states"][artifact["id"]]
            if body.get("status") not in {"unmanifested", "destroyed"}:
                raise ValueError("此宝真体尚存，天地间无法再铸第二本体")
            minimum_tier = 3 if int(artifact["rank"]) <= 40 else 2
            current_tier = int(WORLD_SYSTEMS["world_profiles"].get(game.player.world, {}).get("tier", 1))
            if current_tier < minimum_tier:
                raise ValueError("当前世界法则不足以承载这件神机真体")
            replica_ratio = 1.0
        elif forge_kind != "replica":
            raise ValueError("未知的目标炼制类型")
        raw_combat_power = round(int(artifact["base_combat_power"]) * replica_ratio)
        combat_power_cap = tianji_world_combat_power_cap(game.player.world)
        return {
            "target": {"id": artifact["id"], "rank": artifact["rank"], "name": artifact["name"], "mold_id": artifact["mold_id"]},
            "selected_materials": [copy.deepcopy(row) | {"role": role} for role, row in selected],
            "slot_similarities": [round(value, 4) for value in similarities],
            "exact_slots": exact, "recipe_closeness": round(closeness, 4),
            "world_cap": world_cap, "quality_factor": round(quality_factor, 4),
            "replica_ratio": round(replica_ratio, 4), "forge_kind": forge_kind,
            "combat_power": raw_combat_power,
            "effective_combat_power":round(effective_tianji_combat_power(raw_combat_power, game.player.world)),
            "combat_power_cap":round(combat_power_cap) if combat_power_cap is not None else None,
            "effects": [self._tianji_public_effect(row) for row in artifact["effects"]],
        }

    def preview_tianji_forge(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._tianji_target_preview(self._load(game_id), payload)

    def forge_tianji_artifact(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        game = self._load(game_id)
        if game.pending_event or not game.player.alive or game.player.imprisonment:
            raise ValueError("当前状态无法开炉炼制神机")
        preview = self._tianji_target_preview(game, payload)
        artifact_def = self._tianji_artifact(game.tianji_state, preview["target"]["id"])
        # Preview validates every condition before a single material is spent.
        for material in preview["selected_materials"]:
            if material.get("source_kind") in {"plant", "inventory"}:
                if not remove_item(game.player, str(material["inventory_item_id"])):
                    raise ValueError("材料数量发生变化，请重新确认配方")
            else:
                stored = next((row for row in game.player.crafting_materials if str(row.get("id")) == str(material["id"])), None)
                if not stored:
                    raise ValueError("材料数量发生变化，请重新确认配方")
                game.player.crafting_materials.remove(stored)
        ratio = float(preview["replica_ratio"])
        is_true = preview["forge_kind"] == "true_body"
        combat_effects, persistent = _scaled_effects(artifact_def["effects"], ratio)
        game.player.crafting_sequence += 1
        instance_id = f"tianji-crafted-{game.id}-{game.player.crafting_sequence}"
        suffix = "真体" if is_true else f"{ratio:.0%}仿品"
        instance = {
            "id": instance_id, "name": artifact_def["name"] if is_true else f"仿·{artifact_def['name']}",
            "mold_id": artifact_def["mold_id"], "mold_name": self._tianji_config()["mold_nouns"][artifact_def["mold_id"]],
            "quality": "tianji_true" if is_true else "tianji_replica", "quality_name": suffix,
            "quality_multiplier": ratio, "creator_name": game.player.name, "creator_id": game.id,
            "created_year": game.player.age, "materials": [
                {key: row.get(key) for key in ("id", "definition_id", "name", "quality", "state", "source", "origin_world", "material_value")}
                for row in preview["selected_materials"]
            ],
            "material_effects": [], "actual_stats": {"combat_power": preview["combat_power"], **persistent},
            "combat_effects": combat_effects, "anchor_value": max(1, round(preview["combat_power"] / 12)),
            "description": f"天工神机榜第 {artifact_def['rank']} 位【{artifact_def['name']}】之{suffix}。目标炼制只继承目标法宝规则，不继承材料普通 Buff。",
            "is_natal": False,
            "tianji": {"definition_id": artifact_def["id"], "kind": "true_body" if is_true else "replica", "replica_ratio": ratio},
        }
        store_crafted_artifact(game.player, instance)
        game.tianji_state["player_artifacts"].append(instance_id)
        if is_true:
            game.tianji_state["true_body_states"][artifact_def["id"]] = {"status": "player", "holder_ref": instance_id}
            self._tianji_reveal(game, artifact_def["id"], 4, "亲手炼成真体")
        game.history.append(HistoryRecord(
            "SYS_TIANJI_FORGE", 1, game.player.age, "巧夺天工", artifact_def["id"],
            "true_body" if is_true else "replica",
            f"你以目标炼制法炼成【{instance['name']}】，配方接近度 {preview['recipe_closeness']:.0%}，最终发挥 {ratio:.1%}。",
            {"artifact_id": instance_id, "replica_ratio": ratio}, ["system", "tianji", "crafting"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
