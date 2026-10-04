"""Explicit operations for settlement."""

from __future__ import annotations

import copy
import random

from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ...rules import add_item
from ..crafting_system import make_crafting_material_instance, store_crafted_artifact
from ..formation_system import make_formation_material_instance
from ..merchant_definitions import KINDS as KINDS
from ..merchant_definitions import PROCUREMENT_KINDS
from .dependencies import MerchantSettlementDependencies


def _merchant_deliver_order(deps: MerchantSettlementDependencies, game, order):
    if order.get("commission_version", 1) >= 2 and order["kind"] in PROCUREMENT_KINDS:
        order["delivery"] = deps._merchant_deliver_commission(game, order)
        return
    rng = random.Random(f"merchant-delivery:{game.seed}:{order['id']}")
    kind, stars = order["kind"], order["stars"]
    if kind == "supply":
        definition = deps._crafting_material_defs()[order["definition_id"]]
        for _ in range(order["quantity"]):
            game.player.crafting_materials.append(make_crafting_material_instance(definition, rng, source="商盟委托", origin_world=order["source_world"]))
        order["delivery"] = f"获得{definition['name']} ×{order['quantity']}"
    elif kind == "weapon":
        power = order["principal"] * .08
        artifact = {"id": f"merchant-weapon-{game.id}-{order['id']}", "name": f"商盟订制灵刃·{stars}星",
                    "mold_id": "merchant_blade", "mold_name": "商盟灵刃", "quality": "normal", "quality_name": "合格",
                    "creator_name": order["worker"], "created_year": game.player.age,
                    "actual_stats": {"combat_power": power}, "designed_stats": {"combat_power": power},
                    "anchor_value": round(order["principal"] * .5), "materials": [], "combat_effects": [], "is_natal": False}
        store_crafted_artifact(game.player, artifact)
        order["delivery"] = f"获得订制灵刃，基础战力 {power:,.0f}"
    elif kind == "formation":
        definitions = [row for row in deps._formation_material_defs().values() if row.get("world") == order["source_world"]]
        definition = sorted(definitions, key=lambda row: row.get("base_value", 1))[min(len(definitions) - 1, stars - 1)]
        for _ in range(stars + 1):
            game.player.formation_materials.append(make_formation_material_instance(definition, source="商盟炼阵委托", origin_world=order["source_world"]))
        game.player.formation_sequence += 1
        game.player.formation_loadouts.append({"id": f"formation-{game.id}-{game.player.formation_sequence}",
            "name": f"商盟{stars}星护行阵", "slots": [definition["id"]] * (stars + 1) + [None] * (8 - stars),
            "created_year": game.player.age})
        order["delivery"] = f"获得{stars}星护行阵预设及{definition['name']}阵材套组 ×{stars + 1}，可在阵法面板启用"
    elif kind == "recruit":
        game.merchant_state.setdefault("hired_hands", 0)
        game.merchant_state["hired_hands"] += stars
        order["delivery"] = f"招得 {stars} 名商路人手，可协助后续护送、招募和情报任务"
    else:
        if kind == "bounty":
            target = deps._find_npc(game, order["target_id"])
            deps._apply_cultivator_kill(game, {"actor": "commission", "npc_id": target.id, "name": target.name,
                "realm_index": target.realm_index, "faction_id": target.faction_id, "race": target.race}, rng)
            target.death_reason = f"被{order['worker']}依商盟悬赏击杀"
            deps._tianji_handle_npc_kill(game, target.id)
        deps._add_opportunity(game.player, stars * 20)
        game.player.karma = max(0, game.player.karma - stars * 3)
        if kind == "intel":
            order["delivery"] = deps._merchant_intelligence(game, order["source_world"], stars, rng)
        else:
            order["delivery"] = f"{KINDS[kind]}完成，机缘 +{stars * 20}，因果 -{stars * 3}"


def _merchant_intelligence(deps: MerchantSettlementDependencies, game, world, stars, rng):
    """Report actual NPC ties; optional Tianji clues use the real knowledge ledger."""
    from ...world_state import race_pair
    from ..tianji_system import tianji_content_available
    npcs = [npc for npc in deps._all_world_npcs(game) if npc.alive and npc.world == world]
    rng.shuffle(npcs)
    facts, pairs = [], set()
    for first in npcs:
        peers = [npc for npc in npcs if npc.id != first.id and npc.faction_id and first.faction_id]
        peers.sort(key=lambda npc: npc.faction_id != first.faction_id)
        for second in peers[:3]:
            key = tuple(sorted((first.id, second.id)))
            if key in pairs:
                continue
            pairs.add(key)
            if first.faction_id == second.faction_id:
                fact = f'{first.name}与{second.name}同属一门，互为同门'
            else:
                relation = game.sect_relations.get(race_pair(first.faction_id, second.faction_id), {})
                label = {'war':'交战', 'alliance':'结盟', 'truce':'停战'}.get(relation.get('status'))
                if not label:
                    continue
                fact = f'{first.name}与{second.name}分属的宗门目前{label}'
            facts.append(fact)
            break
        if len(facts) >= stars:
            break
    if not facts:
        facts.append('未查到可核实的修士关系，商盟没有提供猜测')
    clues = []
    if tianji_content_available():
        deps._ensure_tianji_state(game)
        state = game.tianji_state
        candidates = [row for row in state.get('artifacts', []) if row.get('origin_world') == world
                      and int(state['knowledge'].get(row['id'], 0)) < 5]
        # One roll per star, without replacement: more stars improve both
        # the chance of any clue and the possible number of discoveries.
        for _ in range(stars):
            if not candidates or rng.random() >= .12 + stars * .08:
                continue
            artifact = rng.choice(candidates)
            candidates.remove(artifact)
            level = int(state['knowledge'].get(artifact['id'], 0)) + 1
            if deps._tianji_reveal(game, artifact['id'], level, f'{stars}星商盟情报委托'):
                clues.append(f"【{artifact['name']}】情报提升至 Lv{level}")
    return f"{WORLD_SYSTEMS['world_names'][world]}修士关系：" + '；'.join(facts) + ('；神机榜线索：' + '；'.join(clues) if clues else '')


def _merchant_deliver_commission(deps: MerchantSettlementDependencies, game, order):
    kind, world = order["kind"], order["source_world"]
    rng = random.Random(f"merchant-delivery:{game.seed}:{order['id']}")
    if kind == "talisman":
        from ..talismans import receive
        for _ in range(order["quantity"]):
            receive(game.player, order["spec"]["product"])
        return f"获得{order['spec']['quality_name']}{order['spec']['product']['name']} ×{order['quantity']}，四维符合验收概览"
    if kind == 'spirit_manual':
        from ..spirit_voisinage import grant
        for _ in range(order['quantity']):
            book = grant(game, order['definition_id'])
        return f"寻得{book.name}玉简 ×{order['quantity']}"
    if kind == "item":
        add_item(game.player, order["definition_id"], order["quantity"])
        return f"获得{ITEM_CATALOG[order['definition_id']].name} ×{order['quantity']}" + deps._merchant_procurement_bonus(game, order, rng)
    if kind == "supply":
        category = order["material_category"]
        if category == "talisman":
            add_item(game.player, order["definition_id"], order["quantity"])
            return f"获得{ITEM_CATALOG[order['definition_id']].name} ×{order['quantity']}" + deps._merchant_procurement_bonus(game, order, rng)
        definition = (deps._formation_material_defs() if category == "formation" else deps._crafting_material_defs())[order["definition_id"]]
        for _ in range(order["quantity"]):
            if category == "formation":
                game.player.formation_materials.append(make_formation_material_instance(definition, source="商盟委托", origin_world=world))
            else:
                game.player.crafting_materials.append(make_crafting_material_instance(definition, rng, source="商盟委托", origin_world=world))
        return f"获得{definition['name']} ×{order['quantity']}" + deps._merchant_procurement_bonus(game, order, rng)
    spec = order["spec"]
    if kind == "formation":
        for material_id in spec["slots"]:
            if material_id:
                game.player.formation_materials.append(make_formation_material_instance(deps._formation_material_defs()[material_id], source="商盟炼阵委托", origin_world=world))
        game.player.formation_sequence += 1
        game.player.formation_loadouts.append({"id": f"formation-{game.id}-{game.player.formation_sequence}",
            "name": f"商盟{order['stars']}星护行阵", "slots": list(spec["slots"]), "created_year": game.player.age})
        spares = int(spec.get('spare_material_count', 0))
        for _ in range(spares):
            material_id = rng.choice([key for key in spec['slots'] if key])
            game.player.formation_materials.append(make_formation_material_instance(deps._formation_material_defs()[material_id], source='商盟赠送备用阵材', origin_world=world))
        return f"获得{spec['material_tier']}阶原料定制阵法及全部独立阵材，可在阵法面板启用；另附{spares}份同阶备用阵材"
    artifact = {"id": f"merchant-weapon-{game.id}-{order['id']}", "name": f"商盟订制{spec['mold']['name']}",
        "mold_id": spec["mold"]["id"], "mold_name": spec["mold"]["name"], "quality": spec.get('quality', 'normal'), "quality_name": spec["quality_name"],
        "creator_name": order["worker"], "created_year": game.player.age, "scaling_realm_index": spec["material_tier"],
        "actual_stats": copy.deepcopy(spec["stats"]), "designed_stats": copy.deepcopy(spec["stats"]),
        "anchor_value": spec["anchor_value"], "materials": copy.deepcopy(spec["materials"]),
        "material_effects": copy.deepcopy(spec["material_effects"]), "combat_effects": copy.deepcopy(spec["combat_effects"]),
        "mold_rule_description": spec["mold"]["rule"].get("description", ""), "is_natal": False}
    store_crafted_artifact(game.player, artifact)
    return f"获得{artifact['quality_name']}品质{artifact['name']}，属性与委托验收概览一致"


def _merchant_procurement_bonus(deps: MerchantSettlementDependencies, game, order, rng):
    if order.get('commission_version', 1) < 3 or order['stars'] <= 1:
        return ''
    formation = order['kind'] == 'supply' and order['material_category'] == 'formation'
    talisman = order['kind'] == 'supply' and order['material_category'] == 'talisman'
    from ...talisman_content import catalog
    definitions = catalog()[0].values() if talisman else deps._formation_material_defs().values() if formation else deps._crafting_material_defs().values()
    value_key = 'base_value' if formation or talisman else 'base_material_value'
    budget = max(1, order['minimum'] * .08 / (order['stars'] - 1))
    candidates = [row for row in definitions if row['world'] == order['source_world']
                  and row['id'] != order['definition_id'] and row[value_key] <= budget]
    if not candidates:
        return '；本次未找到合适的附赠材料'
    rewards = []
    for _ in range(order['stars'] - 1):
        row = rng.choice(candidates)
        if talisman:
            add_item(game.player, row['id'])
        elif formation:
            game.player.formation_materials.append(make_formation_material_instance(row, source='商盟星级附赠', origin_world=order['source_world']))
        else:
            game.player.crafting_materials.append(make_crafting_material_instance(row, rng, source='商盟星级附赠', origin_world=order['source_world']))
        rewards.append(row['name'])
    order['bonus_items'] = rewards
    return '；额外获得：' + '、'.join(rewards)


def _merchant_log(order, age, message):
    order.setdefault('logs', []).append({'age': age, 'message': message})
    order['logs'] = order['logs'][-16:]


def _merchant_refund(deps: MerchantSettlementDependencies, game, order, status, reason, fee_refund=0):
    if order['status'] not in {'open', 'working'}:
        return
    order.update(status=status, settled_age=game.player.age, refund_principal=order['principal'], refund_fee=fee_refund)
    add_item(game.player, 'spirit_stone', order['principal'] + fee_refund)
    message = f"委托「{order['name']}」{'失败' if status == 'failed' else '取消'}：{reason}。退还全部本金 {order['principal']:,} 灵石、手续费 {fee_refund:,} 灵石。"
    deps._merchant_log(order, game.player.age, message)
    deps._merchant_notice(game, message)
