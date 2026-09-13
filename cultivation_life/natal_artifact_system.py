from __future__ import annotations

from typing import Any

from .content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from .models import GameState, HistoryRecord
from .rules import add_item, has_item, remove_item
from .runtime import now_iso


class NatalArtifactSystemMixin:
    """本命法宝：绑定一件实体法宝，并以轻量状态保存祭炼等级与镶嵌槽。"""

    @staticmethod
    def _natal_artifact_config() -> dict[str, Any]:
        return WORLD_SYSTEMS["natal_artifact"]

    def _natal_artifact_candidate(self, item: Any) -> bool:
        tags = set(item.tags)
        return item.combat_bonus > 0 and (
            bool(tags.intersection({"artifact", "equipment"}))
            or item.id in self._natal_artifact_config().get("eligible_item_ids", [])
        )

    def _natal_slots_for_level(self, level: int) -> int:
        unlocks = self._natal_artifact_config()["slot_unlocks"]
        return max(int(amount) for required, amount in unlocks.items() if int(required) <= level)

    def _natal_level_required(self, level: int) -> int:
        return int(self._natal_artifact_config()["experience_base"]) * max(1, level)

    def _ensure_natal_artifact(self, game: GameState) -> bool:
        artifact = game.natal_artifact
        changed = False
        if artifact:
            artifact.setdefault("level", 1)
            artifact.setdefault("experience", 0)
            slots = list(artifact.get("slots", []))[:7]
            if len(slots) < 7:
                slots.extend([None] * (7 - len(slots)))
            if slots != artifact.get("slots"):
                artifact["slots"] = slots
                changed = True
        self._sync_natal_artifact_bonuses(game)
        return changed

    def _sync_natal_artifact_bonuses(self, game: GameState) -> None:
        player = game.player
        player.natal_artifact_hp_bonus = 0.0
        player.natal_artifact_mp_bonus = 0.0
        player.natal_artifact_combat_bonus = 0.0
        player.natal_artifact_opportunity_bonus = 0.0
        player.natal_artifact_tribulation_reduction = 0.0
        artifact = game.natal_artifact
        if not artifact or artifact.get("item_id") not in ITEM_CATALOG:
            return
        base = ITEM_CATALOG[str(artifact["item_id"])]
        level = max(1, int(artifact.get("level", 1)))
        scale = 1.0 + float(self._natal_artifact_config()["level_scale_per_level"]) * (level - 1)
        totals = {
            "hp_bonus": float(base.hp_bonus) * scale,
            "mp_bonus": float(base.mp_bonus) * scale,
            "combat_bonus": float(base.combat_bonus) * scale,
            "opportunity_bonus": float(base.opportunity_bonus) * scale,
            "tribulation_reduction": float(base.tribulation_damage_reduction) * scale,
        }
        definitions = {row["item_id"]: row for row in self._natal_artifact_config()["materials"]}
        for material_id in artifact.get("slots", []):
            definition = definitions.get(material_id)
            if not definition:
                continue
            for stat, amount in definition.get("effect", {}).items():
                totals[stat] = totals.get(stat, 0.0) + float(amount)
        player.natal_artifact_hp_bonus = totals["hp_bonus"]
        player.natal_artifact_mp_bonus = totals["mp_bonus"]
        player.natal_artifact_combat_bonus = totals["combat_bonus"]
        player.natal_artifact_opportunity_bonus = totals["opportunity_bonus"]
        player.natal_artifact_tribulation_reduction = min(0.50, totals["tribulation_reduction"])

    def _natal_artifact_combat_effects(self, game: GameState) -> list[dict[str, Any]]:
        """Return data-driven socket effects for the automatic player combat resolver."""
        artifact = game.natal_artifact
        if not artifact:
            return []
        definitions = {row["item_id"]: row for row in self._natal_artifact_config()["materials"]}
        effects = []
        for material_id in artifact.get("slots", []):
            definition = definitions.get(material_id)
            if not definition or not definition.get("combat_effect"):
                continue
            effects.append({
                "item_id": material_id,
                "name": definition["name"],
                **definition["combat_effect"],
            })
        return effects

    def _add_natal_artifact_experience(self, game: GameState, amount: int) -> tuple[int, int]:
        artifact = game.natal_artifact
        if not artifact or amount <= 0:
            return 0, 0
        old_level = int(artifact["level"])
        maximum = int(self._natal_artifact_config()["max_level"])
        artifact["experience"] = int(artifact.get("experience", 0)) + int(amount)
        while int(artifact["level"]) < maximum:
            required = self._natal_level_required(int(artifact["level"]))
            if int(artifact["experience"]) < required:
                break
            artifact["experience"] -= required
            artifact["level"] = int(artifact["level"]) + 1
        if int(artifact["level"]) >= maximum:
            artifact["experience"] = 0
        self._sync_natal_artifact_bonuses(game)
        return old_level, int(artifact["level"])

    def _advance_natal_artifact(self, game: GameState, action: str, units: int) -> str | None:
        if action != "cultivate" or not game.natal_artifact:
            return None
        old_level, new_level = self._add_natal_artifact_experience(game, max(1, int(units)))
        if new_level <= old_level:
            return None
        unlocked = self._natal_slots_for_level(new_level)
        game.history.append(HistoryRecord(
            "SYS_NATAL_ARTIFACT_LEVEL", 1, game.player.age, "本命法宝晋阶", None, "leveled",
            f"{game.natal_artifact['name']}随周天祭炼升至 {new_level} 级，现有 {unlocked} 个镶嵌槽位。",
            {"level": [old_level, new_level], "slots": unlocked},
            ["system", "natal_artifact", "cultivation"],
        ))
        return f"本命法宝升至 {new_level} 级"

    def natal_artifact_action(
        self, game_id: str, action: str, item_id: str = "", slot_index: int = -1,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法祭炼本命法宝")
        if player.realm_index < int(self._natal_artifact_config()["minimum_realm"]):
            raise ValueError("结丹期方可修炼本命法宝")
        self._ensure_natal_artifact(game)

        if action == "bind":
            if game.natal_artifact:
                raise ValueError("已有本命法宝，不能重新认主")
            item = next((row for row in player.inventory if row.id == item_id and row.quantity > 0), None)
            if not item or not self._natal_artifact_candidate(item):
                raise ValueError("必须选择背包中的法宝或装备认主")
            if not remove_item(player, item_id):
                raise ValueError("法宝已经不在背包中")
            game.natal_artifact = {
                "item_id": item_id, "name": item.name, "level": 1,
                "experience": 0, "bound_age": player.age, "slots": [None] * 7,
            }
            summary = f"你将{item.name}收入丹田，以精血和金丹真火炼为本命法宝。"
            result = "bound"
        elif action == "refine":
            if not game.natal_artifact:
                raise ValueError("尚未选择本命法宝")
            level = int(game.natal_artifact["level"])
            if level >= int(self._natal_artifact_config()["max_level"]):
                raise ValueError("本命法宝已祭炼至当前上限")
            cost = int(self._natal_artifact_config()["manual_refine_stone_base"]) * level
            if not remove_item(player, "spirit_stone", cost):
                raise ValueError(f"本次温养需要 {cost} 枚灵石")
            old_level, new_level = self._add_natal_artifact_experience(
                game, int(self._natal_artifact_config()["manual_refine_xp"]),
            )
            summary = f"你耗费 {cost} 枚灵石温养{game.natal_artifact['name']}，祭炼经验增加。"
            if new_level > old_level:
                summary += f" 法宝升至 {new_level} 级。"
            result = "refined"
        elif action in {"socket", "unsocket"}:
            if not game.natal_artifact:
                raise ValueError("尚未选择本命法宝")
            unlocked = self._natal_slots_for_level(int(game.natal_artifact["level"]))
            if slot_index < 0 or slot_index >= unlocked:
                raise ValueError("该镶嵌槽尚未解锁")
            slots = game.natal_artifact["slots"]
            old_material = slots[slot_index]
            if action == "unsocket":
                if not old_material:
                    raise ValueError("该槽位为空")
                add_item(player, old_material)
                slots[slot_index] = None
                summary, result = f"你取回了{ITEM_CATALOG[old_material].name}。", "unsocketed"
            else:
                definitions = {row["item_id"]: row for row in self._natal_artifact_config()["materials"]}
                definition = definitions.get(item_id)
                if not definition or player.realm_index < int(definition["minimum_realm"]):
                    raise ValueError("当前境界无法驾驭这种镶嵌材料")
                if item_id in slots:
                    raise ValueError("同种材料只能镶嵌一枚")
                if not has_item(player, item_id) or not remove_item(player, item_id):
                    raise ValueError("背包中没有这种镶嵌材料")
                if old_material:
                    add_item(player, old_material)
                slots[slot_index] = item_id
                summary, result = f"你将{definition['name']}镶入第 {slot_index + 1} 槽。", "socketed"
        else:
            raise ValueError("未知本命法宝操作")

        self._sync_natal_artifact_bonuses(game)
        game.history.append(HistoryRecord(
            "SYS_NATAL_ARTIFACT", 1, player.age, "本命法宝", item_id or None, result,
            summary, {"artifact": dict(game.natal_artifact)}, ["system", "natal_artifact"],
        ))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_natal_artifact(self, game: GameState) -> dict[str, Any]:
        player = game.player
        visible = player.realm_index >= int(self._natal_artifact_config()["minimum_realm"]) or bool(game.natal_artifact)
        if not visible:
            return {"visible": False}
        self._ensure_natal_artifact(game)
        candidates = [
            {"id": item.id, "name": item.name, "quantity": item.quantity,
             "combat_bonus": item.combat_bonus, "description": item.description}
            for item in player.inventory if self._natal_artifact_candidate(item)
        ]
        artifact = game.natal_artifact
        if not artifact:
            return {"visible": True, "bound": False, "candidates": candidates}
        level = int(artifact["level"])
        unlocked = self._natal_slots_for_level(level)
        definitions = {row["item_id"]: row for row in self._natal_artifact_config()["materials"]}
        materials = []
        for definition in self._natal_artifact_config()["materials"]:
            item = next((row for row in player.inventory if row.id == definition["item_id"]), None)
            materials.append({
                **definition, "quantity": int(item.quantity) if item else 0,
                "available": bool(item) and player.realm_index >= int(definition["minimum_realm"])
                and definition["item_id"] not in artifact["slots"],
            })
        slots = []
        for index, material_id in enumerate(artifact["slots"]):
            definition = definitions.get(material_id)
            slots.append({
                "index": index, "unlocked": index < unlocked, "material_id": material_id,
                "name": definition["name"] if definition else None,
                "description": definition["description"] if definition else None,
            })
        base = ITEM_CATALOG[artifact["item_id"]]
        maximum = int(self._natal_artifact_config()["max_level"])
        return {
            "visible": True, "bound": True, "item_id": artifact["item_id"], "name": artifact["name"],
            "description": base.description, "level": level, "max_level": maximum,
            "experience": int(artifact["experience"]),
            "experience_required": self._natal_level_required(level) if level < maximum else 0,
            "unlocked_slots": unlocked, "slots": slots, "materials": materials,
            "refine_cost": int(self._natal_artifact_config()["manual_refine_stone_base"]) * level,
            "can_refine": level < maximum and has_item(
                player, "spirit_stone", int(self._natal_artifact_config()["manual_refine_stone_base"]) * level,
            ),
            "bonuses": {
                "combat_bonus": round(player.natal_artifact_combat_bonus, 1),
                "hp_bonus": round(player.natal_artifact_hp_bonus, 1),
                "mp_bonus": round(player.natal_artifact_mp_bonus, 1),
                "opportunity_bonus": round(player.natal_artifact_opportunity_bonus, 4),
                "tribulation_reduction": round(player.natal_artifact_tribulation_reduction, 4),
            },
        }

    def _natal_artifact_inventory_item(self, game: GameState) -> dict[str, Any] | None:
        if not game.natal_artifact or game.natal_artifact.get("item_id") not in ITEM_CATALOG:
            return None
        item = ITEM_CATALOG[game.natal_artifact["item_id"]].to_dict()
        item.update(
            quantity=1, is_natal_artifact=True,
            description=f"本命法宝 · {game.natal_artifact['level']}级。已收入丹田，不可交易。",
        )
        item["tags"] = list(dict.fromkeys([*item.get("tags", []), "natal_artifact"]))
        return item
