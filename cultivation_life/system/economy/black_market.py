from __future__ import annotations
from ..path_modifiers import adjusted_cost
import copy
from typing import Any
from ...models import HistoryRecord
from ...runtime import now_iso
from ...rules import add_item, remove_item
from .dependencies import BlackMarketDependencies


from ...content_registry import MARKET_GOODS
from ...content_registry import REALMS
import random
import re


def buy_black_market_item(deps: BlackMarketDependencies, game_id: str, result_id: str, quantity: int = 1) -> dict[str, Any]:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 999:
        raise ValueError("购买数量必须为 1–999 的整数")
    game = deps._load(game_id)
    state = deps._require_auction_access(game, {"black_market"})
    result = next((row for row in state.get("black_market_results", []) if row["id"] == result_id), None)
    if not result:
        raise ValueError("请先检索并选择一件黑市商品")
    from cultivation_life.system.spirit_voisinage import secondary, catalog, grant
    spirit = result.get('kind') == 'spirit_manual'
    talisman = result.get('kind') == 'talisman'
    if spirit and (not secondary(game.player.world) or result.get('content_id') not in catalog(game)):
        raise ValueError('当前界面没有这份灵域传承')
    if talisman:
        from ...talisman_content import local_catalog
        recipe = local_catalog(game)[1].get(result.get('content_id'))
        product = result.get('talisman_instance')
        if not recipe or not isinstance(product, dict) or product.get('origin_world') != game.player.world or product.get('method_id') != recipe['id']:
            raise ValueError('这件符箓不属于当前界面的流通范围')
    if not spirit and not talisman and not deps._is_world_market_good(
        game.player.world, str(result.get("kind", "")), str(result.get("content_id", "")),
    ):
        raise ValueError("这件货物不属于当前世界的流通范围")
    kind = str(result["kind"])
    total_price = adjusted_cost(game, int(result["price"]), "black_market") * quantity
    instance_key = {"crafting_material": "material_instance", "formation_material": "formation_material_instance"}.get(kind)
    if instance_key and not isinstance(result.get(instance_key), dict):
        raise ValueError("这份黑市材料已经失去灵性")
    if not remove_item(game.player, "spirit_stone", total_price):
        raise ValueError(f"需要 {total_price} 枚下品灵石")
    if spirit:
        for _ in range(quantity):
            grant(game, result['content_id'])
    elif talisman:
        from ..talismans import receive
        for _ in range(quantity):
            receive(game.player, result['talisman_instance'])
    elif kind == "talisman_material":
        add_item(game.player, str(result["content_id"]), quantity)
    elif kind == "crafting_material":
        instance = copy.deepcopy(result.get("material_instance"))
        if not isinstance(instance, dict):
            raise ValueError("这份黑市炼器材料已经失去灵性")
        import uuid
        for _ in range(quantity):
            purchased = copy.deepcopy(instance)
            purchased["id"] = f"material-{uuid.uuid4().hex}"
            game.player.crafting_materials.append(purchased)
    elif kind == "formation_material":
        instance = copy.deepcopy(result.get("formation_material_instance"))
        if not isinstance(instance, dict):
            raise ValueError("这份黑市阵材已经失去阵性")
        import uuid
        for _ in range(quantity):
            purchased = copy.deepcopy(instance)
            purchased["id"] = f"formation-material-{uuid.uuid4().hex}"
            game.player.formation_materials.append(purchased)
    elif kind == "formation_supply":
        supply_id = str(result["content_id"])
        game.player.formation_repair_supplies[supply_id] = (
            int(game.player.formation_repair_supplies.get(supply_id, 0)) + quantity
        )
    else:
        for _ in range(quantity):
            deps._grant_auction_content(game.player, kind, str(result["content_id"]))
    from .local_market import black_market_receipt
    black_market_receipt(game, total_price, quantity)
    game.history.append(HistoryRecord(
        "SYS_BLACK_MARKET_BUY", 1, game.player.age, "黑市补缺", result_id, "purchased",
        f"你以严重溢价支付 {total_price} 枚灵石，购得{result['name']} ×{quantity}。",
        {"spirit_stone":-total_price, "content_id":result["content_id"], "quantity":quantity},
        ["system", "black_market", f"world:{game.player.world}"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def sell_black_market_asset(deps: BlackMarketDependencies, game_id: str, kind: str, asset_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    deps._require_auction_access(game, {"black_market"})
    ratio = float(deps._auction_rules()["black_market_sell_ratio"])
    if kind == "item":
        item = next((row for row in game.player.inventory if row.id == asset_id and row.quantity > 0), None)
        if not item or item.crafted_artifact_id or asset_id == "spirit_stone" or not remove_item(game.player, asset_id):
            raise ValueError("该物品无法在黑市出手")
        name = item.name
        plant_value = deps._plant_item_value(item)
        price = max(1, round(
            (plant_value or deps._catalog_price("item", asset_id)) * (
                float(deps._spirit_field_rules()["black_market_sell_ratio"])
                if plant_value is not None else ratio
            )
        ))
    elif kind == "talisman":
        from ..talismans import sale_rows
        quote = next((r for r in sale_rows(game.player, ratio) if r["id"] == asset_id), None)
        if not quote:
            raise ValueError("符箓不存在或次数已耗尽")
        row = next(r for r in game.player.talismans if r["id"] == asset_id)
        game.player.talismans.remove(row)
        name, price = quote["name"], quote["price"]
    elif kind == "puppet":
        puppet = next((row for row in game.player.puppets if str(row.get("id")) == asset_id), None)
        if not puppet or puppet.get("type") == "living":
            raise ValueError("黑市只接收机关傀儡与炼尸，不接收活傀")
        game.player.puppets.remove(puppet)
        name = str(puppet.get("name", "无名傀儡"))
        price = max(5, round(float(puppet.get("combat_power", 0)) * 0.08))
    else:
        raise ValueError("未知黑市资产类型")
    from .local_market import legacy_sale
    legacy_sale(game, price, '黑市收购', black_market=True)
    game.history.append(HistoryRecord(
        "SYS_BLACK_MARKET_SELL", 1, game.player.age, "黑市销赃", asset_id, "sold",
        f"你在黑市出手{name}，获得 {price} 枚下品灵石。", {"spirit_stone":price},
        ["system", "black_market", f"world:{game.player.world}"],
    ))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)


def leave_black_market(deps: BlackMarketDependencies, game_id: str) -> dict[str, Any]:
    game = deps._load(game_id)
    deps._require_auction_access(game, {"black_market"})
    game.auction_state = {"status":"cooldown", "actions_remaining":int(deps._auction_rules()["cooldown_actions"])}
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)




def search_black_market(deps: BlackMarketDependencies, game_id: str, pattern: str) -> dict[str, Any]:
    game = deps._load(game_id)
    state = deps._require_auction_access(game, {"black_market"})
    pattern = str(pattern).strip()
    if not pattern or len(pattern) > 40:
        raise ValueError("请输入1至40个字符的检索表达式")
    try:
        matcher = re.compile(pattern, re.IGNORECASE)
    except re.error as error:
        raise ValueError(f"正则表达式无效：{error}") from error
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in MARKET_GOODS:
        if row.get("world", "human") == game.player.world:
            unique[(str(row["kind"]), str(row["content_id"]))] = dict(row)
    # Material stalls are generated outside MARKET_GOODS because each
    # crafting/formation piece is a real unique instance. Black-market
    # search still exposes the complete world-local catalog and freezes
    # the generated instance in the saved search result until purchase.
    material_rng = random.Random(
        f"{game.seed}:black-market-material:{state.get('id', '')}:{pattern}"
    )
    material_rows: list[dict[str, Any]] = []
    from ...talisman_content import catalog
    material_rows.extend(dict(kind="talisman_material", content_id=r["id"], name=r["name"],
        description=r["description"], tier=r["tier"], base_price=r["base_value"])
        for r in catalog()[0].values() if r["world"] == game.player.world)
    from ..talismans import product, economic_value
    materials, methods = catalog()
    for recipe in methods.values():
        if recipe['world'] != game.player.world:
            continue
        ingredients = [m for m in materials.values() if m['world'] == recipe['world'] and m['tier'] == recipe['tier']][:2]
        # A saved, reproducible offer has exactly the same stats when purchased.
        quality = material_rng.choices(['poor', 'normal', 'fine', 'perfect'], weights=[15, 60, 22, 3])[0]
        instance = product(recipe, ingredients, quality)
        from ...talisman_content import QUALITIES
        material_rows.append(dict(kind='talisman', content_id=recipe['id'],
            name=f"{QUALITIES[quality][0]}{instance['name']}", tier=recipe['tier'],
            description=f"成品符箓 · 威力 {instance['power']:g} · 防护 {instance['protection']:g} · 辅助 {instance['assistance']:g} · {instance['uses']} 次",
            base_price=economic_value(instance), talisman_instance=instance))
    for definition in deps._crafting_material_defs().values():
        if str(definition.get("world")) != game.player.world:
            continue
        from ..crafting_system import make_crafting_material_instance
        instance = make_crafting_material_instance(
            definition, material_rng, source="黑市购得", origin_world=game.player.world,
        )
        material_rows.append({
            "kind":"crafting_material", "content_id":str(definition["id"]),
            "name":str(definition["name"]),
            "description":f"炼器材料 · {instance['state']} · 材料价值 {int(instance['material_value']):,}",
            "tier":int(definition.get("tier", 1)),
            "base_price":int(instance["material_value"]), "material_instance":instance,
        })
    for definition in deps._formation_material_defs().values():
        if str(definition.get("world")) != game.player.world:
            continue
        from ..formation_system import NATURE_NAMES, make_formation_material_instance
        instance = make_formation_material_instance(
            definition, source="黑市购得", origin_world=game.player.world,
        )
        material_rows.append({
            "kind":"formation_material", "content_id":str(definition["id"]),
            "name":str(definition["name"]),
            "description":f"阵法材料 · {NATURE_NAMES.get(str(definition.get('nature')), definition.get('nature'))}性 · 固有阵值 {float(definition.get('formation_value', 0)):g}",
            "tier":int(definition.get("tier", 1)),
            "base_price":int(definition.get("base_value", 1)), "formation_material_instance":instance,
        })
    for definition in deps._formation_maintenance_defs().values():
        if str(definition.get("world")) != game.player.world:
            continue
        material_rows.append({
            "kind":"formation_supply", "content_id":str(definition["id"]),
            "name":str(definition["name"]),
            "description":f"修阵材料 · 恢复 {float(definition.get('repair_value', 0)):g}% 镇地阵完整度",
            "tier":int(definition.get("tier", 1)),
            "base_price":int(definition.get("base_value", 1)),
        })
    results = []
    multiplier = float(deps._auction_rules()["black_market_buy_multiplier"])
    for (kind, content_id), row in unique.items():
        name, description = deps._auction_content(kind, content_id)
        if not matcher.search(f"{name} {description}"):
            continue
        results.append({
            "id":f"black-{kind}-{content_id}", "kind":kind, "content_id":content_id,
            "name":name, "description":description, "tier":int(row["tier"]),
            "tier_name":REALMS[int(row["tier"])].name,
            "price":max(1, round(deps._catalog_price(kind, content_id) * multiplier)),
        })
    for row in material_rows:
        if not matcher.search(f"{row['name']} {row['description']}"):
            continue
        tier = max(0, min(len(REALMS) - 1, int(row["tier"])))
        results.append({
            **row,
            "id":f"black-{row['kind']}-{row['content_id']}",
            "tier":tier, "tier_name":REALMS[tier].name,
            "price":max(1, round(int(row["base_price"]) * multiplier)),
        })
    from ..spirit_voisinage import offers
    for book in offers(game, 'black_market', state.get('id', game.player.age // 10)):
        description = '仙家传承的下界改本；合参至 Lv4 可修习灵域，无法通过道门修炼。'
        if matcher.search(book.name + ' ' + description):
            results.append(dict(id='black-' + book.id, kind='spirit_manual', content_id=book.id,
                name=book.name, description=description, tier=book.grade,
                tier_name=REALMS[book.grade].name, price=45000))
    results.sort(key=lambda row: (row['kind'] != 'spirit_manual', row["tier"], row["name"]))
    state["black_market_results"] = results[:int(deps._auction_rules()["black_market_result_limit"])]
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
