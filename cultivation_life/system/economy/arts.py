from __future__ import annotations
import math
from typing import Any
from ...content_registry import ITEM_CATALOG
from ...models import HistoryRecord, Item, Player
from ...runtime import decode_rng, encode_rng, now_iso
from ...rules import add_item, max_mp, remove_item
from .dependencies import ArtsDependencies


def _grant_art_experience(deps: ArtsDependencies, player: Player, art_id: str, amount: float) -> None:
    if art_id in deps._art_names() and amount > 0:
        if art_id in {"alchemy"}:
            amount *= 1 + max(0.0, float(player.sage_effects.get("field_alchemy_multiplier", 0.0)))
        if art_id in {"refining", "formation"}:
            amount *= 1 + max(0.0, float(player.sage_effects.get("crafting_formation_multiplier", 0.0)))
        amount *= 1 + max(0.0, float(player.sage_effects.get("art_experience_multiplier", 0.0)))
        player.art_experience[art_id] = float(player.art_experience.get(art_id, 0.0)) + float(amount)


def _public_art_skills(deps: ArtsDependencies, player: Player) -> list[dict[str, Any]]:
    base = float(deps._spirit_field_rules()["art_experience_base"])
    result = []
    for art_id, name in deps._art_names().items():
        experience = max(0.0, float(player.art_experience.get(art_id, 0.0)))
        level = int(math.sqrt(experience / base))
        current_threshold = base * level * level
        next_threshold = base * (level + 1) * (level + 1)
        result.append({
            "id":art_id, "name":name, "level":level, "experience":round(experience, 1),
            "level_experience":round(experience - current_threshold, 1),
            "next_level_experience":round(next_threshold - current_threshold, 1),
        })
    return result


def refine_pill(deps: ArtsDependencies, game_id: str, target_item_id: str, materials: list[dict[str, Any]]) -> dict[str, Any]:
    game = deps._load(game_id)
    player = game.player
    if game.pending_event or not player.alive or player.imprisonment:
        raise ValueError("当前状态无法开炉炼丹")
    target = ITEM_CATALOG.get(target_item_id)
    if not target or "pill" not in target.tags:
        raise ValueError("目标必须是一种可炼制丹药")
    recipe = deps._alchemy_targets(player).get(target_item_id)
    if recipe is None:
        raise ValueError("当前境界不能炼制此丹药，或该丹药须通过专属途径取得")
    requested: dict[str, int] = {}
    for row in materials or []:
        item_id = str(row.get("item_id", ""))
        quantity = max(0, int(row.get("quantity", 0)))
        if quantity:
            requested[item_id] = requested.get(item_id, 0) + quantity
    if not requested:
        raise ValueError("至少投入一株药材")
    exact=recipe.get('inputs')
    if exact is not None and requested!=exact:
        raise ValueError('标准丹药须投入完整的同阶配方，不能以一种药材替代全部原料')
    selected: list[tuple[Item, int]] = []
    for item_id, quantity in requested.items():
        item = next((entry for entry in player.inventory if entry.id == item_id), None)
        suitable=item and (item_id in exact if exact is not None else 'herb' in item.tags and 'seed' not in item.tags)
        if not suitable or item.quantity < quantity:
            raise ValueError("药材数量不足或混入了非药材物品")
        selected.append((item, quantity))
    mp_cost = max(1.0, max_mp(player) * 0.15)
    if player.mp < mp_cost:
        raise ValueError("炼丹需要至少 15% 最大 MP")
    tier = recipe['tier']
    total = sum(quantity for _, quantity in selected)
    average_quality = sum(float(item.plant_quality or 0.55) * quantity for item, quantity in selected) / total
    alchemy_level = next(row["level"] for row in deps._public_art_skills(player) if row["id"] == "alchemy")
    chance = max(0.05, min(0.95,
        0.22 + average_quality * 0.42 + alchemy_level * 0.065
        + math.log2(total + 1) * 0.045 - (tier - 1) * 0.085
    ))
    for item, quantity in selected:
        remove_item(player, item.id, quantity)
    player.mp -= mp_cost
    rng = decode_rng(game.seed, game.rng_state)
    success = rng.random() < chance
    if success:
        add_item(player, target_item_id)
    experience = (8 + tier * 7 + total * 2) * (1.35 if success else 1.0)
    deps._grant_art_experience(player, "alchemy", experience)
    summary = (
        f"你投入 {total} 株药材炼成{target.name}，成功率 {chance:.0%}，炼丹经验 +{experience:.0f}。"
        if success else
        f"你投入 {total} 株药材尝试炼制{target.name}，炉火失衡而失败（成功率 {chance:.0%}），炼丹经验 +{experience:.0f}。"
    )
    game.history.append(HistoryRecord(
        "SYS_ALCHEMY", 1, player.age, "开炉炼丹", target_item_id, "success" if success else "failed",
        summary, {"chance":round(chance, 4), "materials":requested, "mp":-round(mp_cost, 1)},
        ["system", "alchemy", "art:alchemy"],
    ))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)
