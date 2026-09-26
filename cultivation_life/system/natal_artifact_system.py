from __future__ import annotations

import math
from typing import Any

from ..content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ..models import GameState, HistoryRecord
from ..rules import add_item, has_item, remove_item
from ..runtime import now_iso


class NatalArtifactSystemMixin:
    """本命法宝：绑定一件实体法宝，并以轻量状态保存祭炼等级与镶嵌槽。"""

    @staticmethod
    def _natal_artifact_config() -> dict[str, Any]:
        return WORLD_SYSTEMS["natal_artifact"]

    def _natal_artifact_material_definitions(self) -> dict[str, dict[str, Any]]:
        """Merge base socket gems with Guixu materials without duplicating inventory state."""
        definitions = {
            str(row["item_id"]): dict(row)
            for row in self._natal_artifact_config()["materials"]
        }
        realm_by_source = {
            "canghai": 3, "bloodriver": 3, "weir": 6,
            "demon_grave": 6, "beast_vortex": 6, "yellow_spring": 6,
            "monster_realm": 6, "celestial": 9, "asura": 9, "nether": 9, "reincarnation": 9,
        }
        for item in ITEM_CATALOG.values():
            tags = set(item.tags)
            if not {"guixu_tide", "crafting_material"} <= tags:
                continue
            source = next((key for key in realm_by_source if key in tags), "canghai")
            socket_power = max(1.0, float(item.combat_bonus) * 2.0)
            definitions[item.id] = {
                "item_id": item.id, "name": item.name,
                "minimum_realm": realm_by_source[source],
                "effect": {"combat_bonus": socket_power},
                "description": (
                    f"归墟专属镶材；嵌入本命法宝后战斗力 +{socket_power:,.0f}，"
                    "取下时完整返还。"
                ),
            }
        return definitions

    def _natal_artifact_candidate(self, item: Any) -> bool:
        tags = set(item.tags)
        return bool(getattr(item, "crafted_artifact_id", None)) or item.combat_bonus > 0 and (
            bool(tags.intersection({"artifact", "equipment"}))
            or item.id in self._natal_artifact_config().get("eligible_item_ids", [])
        )

    @staticmethod
    def _crafted_natal_source(game: GameState) -> dict[str, Any] | None:
        artifact_id = str(game.natal_artifact.get("crafted_artifact_id", "")) if game.natal_artifact else ""
        if not artifact_id and game.natal_artifact and game.natal_artifact.get("item_id") not in ITEM_CATALOG:
            artifact_id = str(game.natal_artifact.get("item_id", ""))
        return next(
            (row for row in game.player.crafted_artifacts if str(row.get("id", "")) == artifact_id),
            None,
        )

    def _bind_crafted_natal_artifact(self, game: GameState, artifact: dict[str, Any]) -> None:
        artifact_id = str(artifact.get("id", ""))
        current_id = str(game.natal_artifact.get("crafted_artifact_id", "")) if game.natal_artifact else ""
        if game.natal_artifact and current_id != artifact_id:
            raise ValueError("已有本命法宝，不能重新认主")
        if current_id == artifact_id:
            return
        for row in game.player.crafted_artifacts:
            row["is_natal"] = str(row.get("id", "")) == artifact_id
        game.natal_artifact = {
            "item_id":artifact_id, "crafted_artifact_id":artifact_id,
            "name":str(artifact.get("name", "无名法宝")), "level":1,
            "experience":0, "bound_age":game.player.age, "slots":[],
            "slot_rule_version":2,
        }
        self._sync_natal_artifact_bonuses(game)

    def _unbind_crafted_natal_artifact(self, game: GameState, artifact_id: str) -> None:
        current = str(game.natal_artifact.get("crafted_artifact_id", "")) if game.natal_artifact else ""
        if current != str(artifact_id):
            raise ValueError("这件法宝并非当前本命法宝")
        for material_id in game.natal_artifact.get("slots", []):
            if material_id:
                add_item(game.player, str(material_id))
        for row in game.player.crafted_artifacts:
            if str(row.get("id", "")) == str(artifact_id):
                row["is_natal"] = False
        game.natal_artifact = {}
        game.player.natal_origin_penalty += 0.10
        self._sync_natal_artifact_bonuses(game)

    def _natal_slots_for_level(self, level: int) -> int:
        interval = max(1, int(self._natal_artifact_config().get("slot_interval", 10)))
        return max(0, int(level)) // interval

    def _natal_level_scale(self, level: int) -> float:
        """Unbounded quadratic stat growth with increasing per-level returns."""
        config = self._natal_artifact_config()
        steps = max(0, int(level) - 1)
        return (
            1.0
            + float(config.get("level_growth_linear", 0.25)) * steps
            + float(config.get("level_growth_quadratic", 0.02)) * steps * steps
        )

    def _natal_flat_combat_growth(self, level: int) -> float:
        """Let a humble bonded artifact eventually outgrow its original base item."""
        steps = max(0, int(level) - 1)
        coefficient = float(self._natal_artifact_config().get("combat_growth_cubic", 5.0))
        return coefficient * steps * steps * steps

    def _natal_refine_cost(self, level: int, game: GameState | None = None) -> int:
        base_cost = int(self._natal_artifact_config()["manual_refine_stone_base"])
        if game and game.natal_artifact:
            crafted = self._crafted_natal_source(game)
            if crafted:
                stats = crafted.get("actual_stats", {})
                power, hp, mp = (max(0.0, float(stats.get(key, 0))) for key in ("combat_power", "max_hp", "max_mp"))
                if crafted.get("tianji"):
                    hp = mp = 0.0  # Persistent buff effects are not raw base attributes.
            else:
                item = ITEM_CATALOG[str(game.natal_artifact["item_id"])]
                power, hp, mp = item.combat_bonus, item.hp_bonus, item.mp_bonus
            # Price raw permanent stats, excluding level growth, sockets, buffs
            # and temporary world suppression. Humble artifacts retain the floor.
            base_cost = max(base_cost, math.ceil((power + (hp + mp) * .25) / 30))
        return base_cost * max(1, int(level))

    def _natal_level_required(self, level: int) -> int:
        return int(self._natal_artifact_config()["experience_base"]) * max(1, level)

    def _ensure_natal_artifact(self, game: GameState) -> bool:
        artifact = game.natal_artifact
        changed = False
        if not artifact:
            # v1.10 briefly stored combination-artifact natal status only on
            # the forge record. Promote that state into the unified natal
            # system without touching the save location or losing the item.
            legacy = next((row for row in game.player.crafted_artifacts if row.get("is_natal")), None)
            if legacy:
                self._bind_crafted_natal_artifact(game, legacy)
                artifact = game.natal_artifact
                changed = True
        if artifact:
            crafted = self._crafted_natal_source(game)
            crafted_id = str(artifact.get("crafted_artifact_id", ""))
            if not crafted_id and crafted and artifact.get("item_id") not in ITEM_CATALOG:
                crafted_id = str(crafted.get("id", ""))
                artifact["crafted_artifact_id"] = crafted_id
                changed = True
            if crafted_id and not crafted:
                game.natal_artifact = {}
                self._sync_natal_artifact_bonuses(game)
                return True
            elif crafted:
                for row in game.player.crafted_artifacts:
                    expected = str(row.get("id", "")) == crafted_id
                    if bool(row.get("is_natal")) != expected:
                        row["is_natal"] = expected
                        changed = True
            else:
                for row in game.player.crafted_artifacts:
                    if row.get("is_natal"):
                        row["is_natal"] = False
                        changed = True
            artifact.setdefault("level", 1)
            artifact.setdefault("experience", 0)
            unlocked = self._natal_slots_for_level(int(artifact["level"]))
            slots = list(artifact.get("slots", []))
            if int(artifact.get("slot_rule_version", 1)) < 2:
                # The former system granted up to seven slots by level 12.
                # Return now-locked materials instead of deleting or trapping
                # them when the unbounded ten-level cadence is introduced.
                for material_id in slots[unlocked:]:
                    if material_id:
                        add_item(game.player, str(material_id))
                slots = slots[:unlocked]
                artifact["slot_rule_version"] = 2
                changed = True
            if len(slots) < unlocked:
                slots.extend([None] * (unlocked - len(slots)))
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
        if not artifact:
            return
        level = max(1, int(artifact.get("level", 1)))
        scale = self._natal_level_scale(level)
        flat_combat_growth = self._natal_flat_combat_growth(level)
        crafted = self._crafted_natal_source(game)
        if crafted:
            stats = crafted.get("actual_stats", {})
            # The base forge stats already apply while the unique item remains
            # in the bag. Natal fields therefore carry only level growth plus
            # socket bonuses, avoiding accidental double application.
            growth = max(0.0, scale - 1.0)
            totals = {
                "hp_bonus":float(stats.get("max_hp", 0.0)) * growth,
                "mp_bonus":float(stats.get("max_mp", 0.0)) * growth,
                "combat_bonus":float(stats.get("combat_power", 0.0)) * growth + flat_combat_growth,
                "opportunity_bonus":float(stats.get("opportunity_efficiency", 0.0)) * growth,
                "tribulation_reduction":float(stats.get("tribulation_reduction", 0.0)) * growth,
            }
        elif artifact.get("item_id") in ITEM_CATALOG:
            base = ITEM_CATALOG[str(artifact["item_id"])]
            totals = {
                "hp_bonus":float(base.hp_bonus) * scale,
                "mp_bonus":float(base.mp_bonus) * scale,
                "combat_bonus":float(base.combat_bonus) * scale + flat_combat_growth,
                "opportunity_bonus":float(base.opportunity_bonus) * scale,
                "tribulation_reduction":float(base.tribulation_damage_reduction) * scale,
            }
        else:
            return
        definitions = self._natal_artifact_material_definitions()
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
        definitions = self._natal_artifact_material_definitions()
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
        artifact["experience"] = int(artifact.get("experience", 0)) + int(amount)
        while True:
            required = self._natal_level_required(int(artifact["level"]))
            if int(artifact["experience"]) < required:
                break
            artifact["experience"] -= required
            artifact["level"] = int(artifact["level"]) + 1
        unlocked = self._natal_slots_for_level(int(artifact["level"]))
        slots = list(artifact.get("slots", []))
        if len(slots) < unlocked:
            slots.extend([None] * (unlocked - len(slots)))
            artifact["slots"] = slots
        self._sync_natal_artifact_bonuses(game)
        return old_level, int(artifact["level"])

    def _natal_refine_all_plan(self, game: GameState) -> tuple[int, int]:
        artifact = game.natal_artifact
        if not artifact:
            return 0, 0
        stone_item = next((row for row in game.player.inventory if row.id == "spirit_stone"), None)
        stones = max(0, int(stone_item.quantity)) if stone_item else 0
        level = max(1, int(artifact.get("level", 1)))
        experience = max(0, int(artifact.get("experience", 0)))
        base_cost = self._natal_refine_cost(1, game)
        refine_xp = int(self._natal_artifact_config()["manual_refine_xp"])
        count = total_cost = 0
        while True:
            cost = base_cost * level
            affordable = stones // cost
            if affordable <= 0:
                break
            required = self._natal_level_required(level)
            refinements_needed = max(1, math.ceil((required - experience) / refine_xp))
            batch = min(affordable, refinements_needed)
            batch_cost = batch * cost
            stones -= batch_cost
            total_cost += batch_cost
            count += batch
            experience += refine_xp * batch
            if experience >= required:
                experience -= required
                level += 1
            else:
                break
        return count, total_cost

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
            if item.crafted_artifact_id:
                crafted = next(
                    (row for row in player.crafted_artifacts if str(row.get("id", "")) == item.crafted_artifact_id),
                    None,
                )
                if not crafted:
                    raise ValueError("这件炼器法宝的唯一实例已经损坏")
                self._bind_crafted_natal_artifact(game, crafted)
            else:
                if not remove_item(player, item_id):
                    raise ValueError("法宝已经不在背包中")
                game.natal_artifact = {
                    "item_id":item_id, "name":item.name, "level":1,
                    "experience":0, "bound_age":player.age, "slots":[],
                    "slot_rule_version":2,
                }
            summary = f"你将{item.name}收入丹田，以精血和金丹真火炼为本命法宝。"
            result = "bound"
        elif action == "unbind":
            if not game.natal_artifact:
                raise ValueError("尚未选择本命法宝")
            old = dict(game.natal_artifact)
            if old.get("crafted_artifact_id"):
                self._unbind_crafted_natal_artifact(game, old["crafted_artifact_id"])
            else:
                add_item(player, str(old["item_id"]))
                for material_id in old.get("slots", []):
                    if material_id:
                        add_item(player, str(material_id))
                game.natal_artifact = {}
                player.natal_origin_penalty += .10
            summary = f"你解除{old['name']}的本命联系，法宝与镶材归还，温养散去。本源受损，下次修为突破概率降低10个百分点。"
            result = "unbound"
        elif action in {"refine", "refine_all"}:
            if not game.natal_artifact:
                raise ValueError("尚未选择本命法宝")
            level = int(game.natal_artifact["level"])
            if action == "refine_all":
                refine_count, cost = self._natal_refine_all_plan(game)
                if refine_count <= 0:
                    raise ValueError("灵石不足以继续温养本命法宝")
            else:
                refine_count = 1
                cost = self._natal_refine_cost(level, game)
            if not remove_item(player, "spirit_stone", cost):
                raise ValueError(f"本次温养需要 {cost} 枚灵石")
            old_level, new_level = self._add_natal_artifact_experience(
                game, int(self._natal_artifact_config()["manual_refine_xp"]) * refine_count,
            )
            summary = (
                f"你耗费 {cost} 枚灵石"
                + (f"连续温养 {refine_count} 次" if action == "refine_all" else "温养")
                + f"{game.natal_artifact['name']}，祭炼经验增加。"
            )
            if new_level > old_level:
                summary += f" 法宝升至 {new_level} 级。"
            result = "refined_all" if action == "refine_all" else "refined"
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
                definitions = self._natal_artifact_material_definitions()
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
             "combat_bonus": (
                 float(crafted.get("actual_stats", {}).get("combat_power", 0.0))
                 if item.crafted_artifact_id and (crafted := next((
                     row for row in player.crafted_artifacts
                     if str(row.get("id", "")) == item.crafted_artifact_id
                 ), None)) else item.combat_bonus
             ), "description": item.description}
            for item in player.inventory if self._natal_artifact_candidate(item)
        ]
        artifact = game.natal_artifact
        if not artifact:
            return {"visible": True, "bound": False, "candidates": candidates}
        level = int(artifact["level"])
        unlocked = self._natal_slots_for_level(level)
        definitions = self._natal_artifact_material_definitions()
        materials = []
        for definition in definitions.values():
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
        crafted = self._crafted_natal_source(game)
        if crafted:
            description = str(crafted.get("description", "组合式炼器本命法宝"))
            stats = crafted.get("actual_stats", {})
            displayed_base = {
                "combat_bonus":float(stats.get("combat_power", 0.0)),
                "hp_bonus":float(stats.get("max_hp", 0.0)),
                "mp_bonus":float(stats.get("max_mp", 0.0)),
                "opportunity_bonus":float(stats.get("opportunity_efficiency", 0.0)),
                "tribulation_reduction":float(stats.get("tribulation_reduction", 0.0)),
            }
        else:
            base = ITEM_CATALOG[artifact["item_id"]]
            description = base.description
            displayed_base = {key:0.0 for key in (
                "combat_bonus", "hp_bonus", "mp_bonus", "opportunity_bonus", "tribulation_reduction",
            )}
        refine_all_count, refine_all_cost = self._natal_refine_all_plan(game)
        if crafted:
            growth_base_combat = float(crafted.get("actual_stats", {}).get("combat_power", 0.0))
        else:
            growth_base_combat = float(ITEM_CATALOG[str(artifact["item_id"])].combat_bonus)
        next_level_combat_gain = (
            growth_base_combat * (self._natal_level_scale(level + 1) - self._natal_level_scale(level))
            + self._natal_flat_combat_growth(level + 1) - self._natal_flat_combat_growth(level)
        )
        raw_combat_bonus = player.natal_artifact_combat_bonus + displayed_base["combat_bonus"]
        combat_cap = None
        if crafted and crafted.get("tianji"):
            from .crafting_system import effective_tianji_combat_power, tianji_world_combat_power_cap
            combat_cap = tianji_world_combat_power_cap(player.world)
            effective_combat_bonus = effective_tianji_combat_power(raw_combat_bonus, player.world)
            next_level_combat_gain = max(0.0, (
                effective_tianji_combat_power(raw_combat_bonus + next_level_combat_gain, player.world)
                - effective_combat_bonus
            ))
        else:
            effective_combat_bonus = raw_combat_bonus
        slot_interval = max(1, int(self._natal_artifact_config().get("slot_interval", 10)))
        return {
            "visible": True, "bound": True, "item_id": artifact["item_id"], "name": artifact["name"],
            "crafted_artifact_id":artifact.get("crafted_artifact_id"),
            "description":description, "level": level, "max_level": None, "unbounded": True,
            "is_tianji":bool(crafted and crafted.get("tianji")),
            "experience": int(artifact["experience"]),
            "experience_required": self._natal_level_required(level),
            "unlocked_slots": unlocked, "slots": slots, "materials": materials,
            "next_slot_level": (unlocked + 1) * slot_interval,
            "refine_cost": self._natal_refine_cost(level, game),
            "refine_all_count": refine_all_count, "refine_all_cost": refine_all_cost,
            "can_refine_all": refine_all_count > 0,
            "can_refine": has_item(player, "spirit_stone", self._natal_refine_cost(level, game)),
            "bonuses": {
                "base_combat_bonus": round(growth_base_combat, 1),
                "cultivation_combat_bonus": round(raw_combat_bonus - growth_base_combat, 1),
                "combat_bonus":round(effective_combat_bonus, 1),
                "raw_combat_bonus":round(raw_combat_bonus, 1),
                "combat_cap":round(combat_cap) if combat_cap is not None else None,
                "combat_capped":combat_cap is not None and raw_combat_bonus > combat_cap,
                "hp_bonus":round(player.natal_artifact_hp_bonus + displayed_base["hp_bonus"], 1),
                "mp_bonus":round(player.natal_artifact_mp_bonus + displayed_base["mp_bonus"], 1),
                "opportunity_bonus":round(player.natal_artifact_opportunity_bonus + displayed_base["opportunity_bonus"], 4),
                "tribulation_reduction":round(player.natal_artifact_tribulation_reduction + displayed_base["tribulation_reduction"], 4),
                "next_level_combat_gain":round(next_level_combat_gain, 1),
            },
        }

    def _natal_artifact_inventory_item(self, game: GameState) -> dict[str, Any] | None:
        if game.natal_artifact.get("crafted_artifact_id"):
            return None
        if not game.natal_artifact or game.natal_artifact.get("item_id") not in ITEM_CATALOG:
            return None
        item = ITEM_CATALOG[game.natal_artifact["item_id"]].to_dict()
        item.update(
            quantity=1, is_natal_artifact=True,
            description=f"本命法宝 · {game.natal_artifact['level']}级。已收入丹田，不可交易。",
        )
        item["tags"] = list(dict.fromkeys([*item.get("tags", []), "natal_artifact"]))
        return item
