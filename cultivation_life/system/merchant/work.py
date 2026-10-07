"""Explicit operations for work."""

from __future__ import annotations

from ...rules import add_item, remove_item, has_item
from ..crafting_system import make_crafting_material_instance
from ..possession_system import advance_player_age
from .dependencies import MerchantWorkDependencies


def _merchant_task_ready(game, task):
    player = game.player
    if task["kind"] == "talisman":
        rows = [r for r in player.talismans if r.get("method_id") == task["method_id"]
                and r.get("creator_id") == game.id and r["id"] not in task.get("existing_talismans", [])
                and r["uses"] == r.get("max_uses") and not r["enabled"]]
        if not rows:
            raise ValueError(f"请在接单后亲自炼制{task['material_name']}，保留完整次数并停用后交付")
        return rows[:1]
    if task["kind"] == "supply":
        if task.get("material_category") == "talisman":
            if not has_item(player, task["definition_id"], task["quantity"]):
                raise ValueError(f"需准备 {task['material_name']} ×{task['quantity']}")
            return []
        bag = player.formation_materials if task.get("material_category") == "formation" else player.crafting_materials
        rows = [row for row in bag if row["material_id"] == task["definition_id"]]
        if len(rows) < task["quantity"]:
            raise ValueError(f"需准备 {task['material_name']} ×{task['quantity']}（对应分类的闲置材料）")
        return rows[:task["quantity"]]
    if task["kind"] == "weapon":
        rows = [row for row in player.crafted_artifacts if not row.get("is_natal") and not row.get("tianji")
                and row.get("creator_id") == game.id and row["id"] not in task["existing_artifacts"]
                and float(row.get("actual_stats", {}).get("combat_power", 0)) >= task["power"] * .1]
        if not rows:
            raise ValueError(f"需在接取后亲自炼制一件基础战力至少 {task['power'] * .1:,.0f} 的普通法宝，再提交委托")
        return rows[:1]
    if task["kind"] == "formation":
        rows = sorted(player.formation_materials, key=lambda row: row.get("base_value", 1), reverse=True)
        rows = [row for row in rows if row.get("acquired_tier", 1) >= max(1, task["realm"] - 1)]
        if len(rows) < task["stars"] + 1:
            raise ValueError(f"炼阵需 {task['stars'] + 1} 件至少 {max(1, task['realm'] - 1)} 阶闲置阵材，在商盟工坊炼制后交付雇主")
        return rows[:task["stars"] + 1]
    return []


def _merchant_work(deps: MerchantWorkDependencies, game, rng):
    state = game.merchant_state
    task = state["active"]
    if not task:
        raise ValueError("没有待完成的商盟任务")
    if game.player.world != task["world"]:
        raise ValueError("请返回任务所在界面")
    materials = deps._merchant_task_ready(game, task)
    news = []
    while task["worked"] < task["years"]:
        advance_player_age(game.player)
        task["worked"] += 1
        continue_world = deps._advance_world_year(game, rng, news, encounters=False)
        if game.player.alive:
            deps._advance_soul_erosion_time(game, 1)
        if not continue_world or not game.player.alive or game.pending_event:
            deps._merchant_notice(game, "商盟任务进度已保留，处理当前状况后可继续。")
            return
    kind = task["kind"]
    succeeded = True
    detail = ""
    if kind in {"bounty", "escort"}:
        target = {"target_name": "悬赏恶修" if kind == "bounty" else "劫道修士", "target_power": task["power"],
                  "target_realm_index": task["realm"], "target_layer": 3, "combat_type": "cultivator",
                  "kill_karma": False, "player_defending": kind == "escort"}
        outcome, detail = deps._combat(game, target, kind == "bounty", rng)
        succeeded = outcome == "killed" if kind == "bounty" else outcome in {"victory", "victory_escape", "killed"}
    elif kind in {"recruit", "intel"}:
        hands = state.get("hired_hands", 0)
        chance = min(.98, .65 + (game.player.realm_index - task["realm"]) * .06 + hands * .03)
        succeeded = rng.random() < max(.15, chance)
        if hands:
            state["hired_hands"] -= 1
    if not succeeded:
        state["active"] = None
        deps._merchant_notice(game, f"{task['stars']}星「{task['name']}」失败，未获得报酬。{detail}")
        return
    if kind == "intel":
        detail = deps._merchant_intelligence(game, task["world"], task["stars"], rng)
    if kind == "supply":
        if task.get("material_category") == "talisman":
            remove_item(game.player, task["definition_id"], task["quantity"])
        else:
            for row in materials:
                (game.player.formation_materials if task.get("material_category") == "formation" else game.player.crafting_materials).remove(row)
    elif kind == "talisman":
        game.player.talismans.remove(materials[0])
    elif kind == "weapon":
        artifact = materials[0]
        remove_item(game.player, artifact["id"])
        game.player.crafted_artifacts.remove(artifact)
    elif kind == "formation":
        for row in materials:
            game.player.formation_materials.remove(row)
        deps._grant_art_experience(game.player, "formation", task["stars"] * 20)
    reward = task["reward"]
    from ..economy.ledger import transfer_value
    from ..economy.caravans import treasury
    alliance = deps._merchant_alliance(game, task['world'], task['alliance_id'])
    paid = min(reward['stones'], alliance['reserves'])
    transfer_value(game, treasury(task['world'], task['alliance_id']), 'player', paid, '商盟委托报酬')
    definition = deps._crafting_material_defs()[task.get("reward_definition_id", task["definition_id"])]
    from ..economy.organizations import procure
    source = treasury(task['world'], task['alliance_id'])
    unit_cost = max(1, int(definition['base_material_value']))
    material_count = min(reward['materials'], alliance['reserves'] // unit_cost)
    procure(game, source, task['world'], material_count * unit_cost, '商盟委托材料采购')
    cultivation_cost = max(1, int(reward['opportunity'] * 100))
    funding = procure(game, source, task['world'], cultivation_cost, '商盟委托修炼供养', partial=True) / cultivation_cost
    opportunity = reward['opportunity'] * funding
    deps._add_opportunity(game.player, opportunity)
    game.player.karma = max(0, game.player.karma - reward["karma"])
    for _ in range(material_count):
        game.player.crafting_materials.append(make_crafting_material_instance(definition, rng, source="商盟报酬", origin_world=task["world"]))
    key = task["influence_key"]
    state["influence"][key] = state["influence"].get(key, 0) + reward["influence"]
    alliance = deps._merchant_alliance(game, task["world"], task["alliance_id"])
    state["completed"].append(task["id"])
    state["completed"] = state["completed"][-350:]
    state["active"] = None
    shortfall = f"商盟财政不足，本次现金报酬原额 {reward['stones']:,}，实付 {paid:,}。" if paid < reward['stones'] else ''
    deps._merchant_notice(game, f"完成{task['stars']}星「{task['name']}」，灵石 +{paid:,}，材料 +{material_count}（约定 {reward['materials']}），机缘 +{opportunity:g}（财政支付 {funding:.0%}），因果 -{reward['karma']}，商盟影响力 +{reward['influence']}。{shortfall}{detail}")
