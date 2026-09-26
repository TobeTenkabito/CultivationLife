from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any

from ..models import HistoryRecord
from ..runtime import decode_rng, encode_rng, now_iso
from ..rules import remove_item
from .crafting_system import make_crafting_material_instance


EXCHANGE_VENUES = {
    "human": "wudi_plain", "spirit": "hundred_race_city",
    "demon": "red_marrow_city", "true_demon": "black_lotus_city",
    "monster_realm": "myriad_beast_city", "phantom_underworld": "nine_tail_dream_city",
    "hell": "yin_market_capital", "celestial": "jade_capital",
    "asura": "ten_thousand_battle_city", "nether": "ancestral_beast_garden",
    "reincarnation": "karma_city",
}
EXCHANGE_ALIASES = ["青笠客", "无名散人", "听雨客", "灰衣道人", "照夜人"]


class ExchangeSystemMixin:
    """Anonymous, material-only barter; all valuations are server-owned."""

    def _exchange_location(self, world):
        location = self.maps.location(world, EXCHANGE_VENUES[world])
        if int(location.get("min_realm_index", 0)):
            raise ValueError("交换会地点不能有境界要求")
        return location

    def _schedule_exchange(self, game, rng):
        location = self._exchange_location(game.player.world)
        game.exchange_sequence += 1
        game.exchange_state = {
            "id": f"exchange-{game.exchange_sequence}", "world": game.player.world,
            "location_id": location["id"], "location_name": location["name"],
            "status": "scheduled", "actions_until_open": 2, "offers": [], "alias": "",
        }
        game.history.append(HistoryRecord(
            "SYS_EXCHANGE_NOTICE", 1, game.player.age, "交换会预告", None, "scheduled",
            f"{location['name']}将在两个时间单位后举办匿名交换会，只收材料，不收灵石。",
            {}, ["system", "exchange"],
        ))

    def _open_exchange(self, game, rng):
        state = game.exchange_state
        definitions = [d for d in self._crafting_material_defs().values()
                       if d.get("world") == state["world"]]
        if not definitions:
            state.update(status="cooldown", remaining=3)
            return
        tier = max(1, game.player.realm_index)
        eligible = [d for d in definitions if int(d.get("tier", 1)) <= tier + 1] or definitions
        rare_count = max(1, min(4, len(eligible) // 3))
        rare = sorted(eligible, key=lambda d: int(d["base_material_value"]), reverse=True)[:rare_count]
        offers = []
        for index in range(3):
            reward_def = rng.choice(rare)
            reward = make_crafting_material_instance(reward_def, rng, source="匿名交换会", origin_world=state["world"])
            wanted = rng.choice([d for d in eligible if d["id"] != reward_def["id"]
                                 and int(d["base_material_value"]) <= reward["material_value"]] or eligible)
            unit_value = int(wanted["base_material_value"])
            quantity = max(1, math.ceil(reward["material_value"] / unit_value))
            offers.append({
                "id": f"{state['id']}-{index}", "npc_alias": ["玄面客", "白玉面具", "竹笠修士"][index],
                "reward": reward, "reward_value": int(reward["material_value"]),
                "demands": [{"definition_id": wanted["id"], "name": wanted["name"],
                             "quantity": quantity, "unit_value": unit_value}],
                "demand_value": quantity * unit_value, "completed": False,
                "substitution_attempted": False,
            })
        state.update(status="open", remaining=2, offers=offers)

    def _advance_exchange_clock(self, game, rng):
        state = game.exchange_state
        if not state:
            if game.player.realm_index > 0 and rng.random() < .12:
                self._schedule_exchange(game, rng)
        elif state.get("world") != game.player.world and state.get("status") != "cooldown":
            game.exchange_state = {"status": "cooldown", "remaining": 3}
        elif state["status"] == "scheduled":
            state["actions_until_open"] -= 1
            if state["actions_until_open"] <= 0:
                self._open_exchange(game, rng)
        elif state["status"] in {"open", "cooldown"}:
            state["remaining"] -= 1
            if state["remaining"] <= 0:
                game.exchange_state = {"status": "cooldown", "remaining": 3} if state["status"] == "open" else {}

    def _exchange_materials(self, game):
        rows = {}
        for material in self._crafting_material_candidates(game.player):
            key = str(material["id"])
            # Inventory materials are exposed as one stack, physical crafting
            # materials as one selectable entry per instance.
            inventory_id = material.get("inventory_item_id")
            if inventory_id:
                key = f"inventory:{inventory_id}"
            rows[key] = {
                "id": key, "name": material["name"], "definition_id": material["definition_id"],
                "value": int(material["material_value"]),
                "quantity": int(material.get("quantity", 1)) if inventory_id else 1,
                "inventory_item_id": inventory_id, "kind": "inventory" if inventory_id else "crafting",
            }
        definitions = self._formation_material_defs()
        for material in game.player.formation_materials:
            definition = definitions.get(str(material.get("material_id", "")), {})
            rows[material["id"]] = {
                "id": material["id"], "name": material["name"], "definition_id": material.get("material_id"),
                "value": max(1, int(definition.get("base_value", 1))), "quantity": 1, "kind": "formation",
            }
        return list(rows.values())

    def exchange_action(self, game_id: str, action: str, payload: dict[str, Any]):
        game = self._load(game_id)
        state = game.exchange_state
        if not game.player.alive or game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法参加交换会")
        if state.get("status") != "open" or state.get("world") != game.player.world or state.get("location_id") != game.player.location_id:
            raise ValueError("请在交换会开放时抵达固定会址")
        if action == "identity":
            alias = str(payload.get("alias", ""))
            if alias not in EXCHANGE_ALIASES:
                raise ValueError("请选择有效的匿名身份")
            state["alias"] = alias
        elif action == "trade":
            if not state.get("alias"):
                raise ValueError("请先选择匿名身份")
            offer = next((x for x in state["offers"] if x["id"] == payload.get("offer_id")), None)
            if not offer or offer["completed"]:
                raise ValueError("这项交换已经结束")
            materials = {x["id"]: x for x in self._exchange_materials(game)}
            selected = payload.get("materials", [])
            if not isinstance(selected, list) or not selected or len(selected) > 999:
                raise ValueError("请选择交换材料")
            counts = Counter()
            for entry in selected:
                if not isinstance(entry, dict):
                    raise ValueError("无效的材料清单")
                count = entry.get("quantity", 1)
                if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                    raise ValueError("材料数量必须为正整数")
                counts[str(entry.get("id", ""))] += count
            for key, count in counts.items():
                if key not in materials or count > materials[key]["quantity"]:
                    raise ValueError("材料不存在或数量不足，灵石不能参与交换")
            by_definition = Counter()
            total = 0
            for key, count in counts.items():
                by_definition[materials[key]["definition_id"]] += count
                total += materials[key]["value"] * count
            exact = all(by_definition[d["definition_id"]] >= d["quantity"] for d in offer["demands"])
            if not exact and total < offer["demand_value"]:
                raise ValueError("替代材料总价值不足，不能用灵石补差")
            rng = decode_rng(game.seed, game.rng_state)
            if not exact and offer["substitution_attempted"]:
                raise ValueError("对方已拒绝替代材料，请备齐所需材料再来")
            success = exact or rng.random() < .65
            if not exact:
                offer["substitution_attempted"] = True
            if success:
                for key, count in counts.items():
                    material = materials[key]
                    if material["kind"] == "inventory":
                        remove_item(game.player, material["inventory_item_id"], count)
                    else:
                        bag = game.player.crafting_materials if material["kind"] == "crafting" else game.player.formation_materials
                        bag[:] = [x for x in bag if x["id"] != key]
                game.player.crafting_materials.append(copy.deepcopy(offer["reward"]))
                offer["completed"] = True
            summary = (f"{state['alias']}与{offer['npc_alias']}匿名交换，取得{offer['reward']['name']}。"
                       if success else f"{offer['npc_alias']}拒绝了替代材料；你的材料完整保留。")
            state["last_result"] = summary
            game.rng_state = encode_rng(rng)
            game.history.append(HistoryRecord("SYS_EXCHANGE_TRADE", 1, game.player.age, "匿名交换", offer["id"],
                                              "traded" if success else "refused", summary, {"value": total}, ["system", "exchange"]))
        else:
            raise ValueError("未知交换会操作")
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _public_exchange(self, game):
        state = game.exchange_state
        visible = state.get("status") in {"scheduled", "open"} and state.get("world") == game.player.world
        location = self._exchange_location(game.player.world)
        if not visible:
            return {"available": False, "venue": location["name"], "location_id": location["id"]}
        return copy.deepcopy(state) | {
            "available": True, "at_location": game.player.location_id == state["location_id"],
            "aliases": EXCHANGE_ALIASES, "materials": self._exchange_materials(game),
        }
