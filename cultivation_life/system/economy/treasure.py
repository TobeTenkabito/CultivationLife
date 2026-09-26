from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from ...content_registry import ITEM_CATALOG, MARKET_GOODS, TECHNIQUE_CATALOG
    from ...models import GameState
    from ...rules import acquire_technique, add_item, max_hp, max_mp


class EconomyTreasureMethods:
    def _treasure_reward_pool(self, game: GameState, category: str) -> list[dict[str, Any]]:
        player = game.player
        target_tier = max(1, player.realm_index)
        location_id = self.maps.normalize_location(player.world, player.location_id)
        world_goods = [row for row in MARKET_GOODS if int(row["tier"]) <= target_tier]
        if category == "technique":
            eligible = [row for row in world_goods if row["kind"] == "technique"]
        elif category == "pill":
            eligible = [row for row in world_goods if row["kind"] == "item" and "pill" in ITEM_CATALOG[row["content_id"]].tags]
        elif category == "artifact":
            eligible = [
                row for row in world_goods if row["kind"] == "item"
                and "pill" not in ITEM_CATALOG[row["content_id"]].tags
                and ITEM_CATALOG[row["content_id"]].combat_bonus > 0
            ]
        else:
            raise ValueError("未知探宝奖励类别")
        eligible = self.maps.localize_goods(eligible, player.world, location_id, "treasure")
        if not eligible:
            raise ValueError(f"{player.world}界缺少可用的{category}探宝奖励")
        return eligible

    def _treasure_step(self, game: GameState, rng: Any) -> str:
        player = game.player
        resource = "mp" if player.mp > 0 and rng.random() < 0.5 else "hp"
        if resource == "hp":
            cost = round(max_hp(player) * rng.uniform(0.07, 0.15), 1)
            player.hp = max(0, player.hp - cost)
            cost_text = f"HP -{cost:.0f}"
            if player.hp <= 0:
                self._die(game, "探宝时气血耗尽，埋骨荒野", "ACT_TREASURE")
                return f"探宝消耗 {cost_text}，未能生还。"
        else:
            cost = round(min(player.mp, max_mp(player) * rng.uniform(0.10, 0.22)), 1)
            player.mp = max(0, player.mp - cost)
            cost_text = f"MP -{cost:.0f}"
        return f"探宝消耗 {cost_text}，寻得三处灵光各异的遗藏。"

    def _prepare_treasure_reward_event(self, game: GameState, rng: Any) -> dict[str, Any]:
        event = self._instantiate_event(self.events_by_id["EVT_TREASURE_REWARD_SELECT_001"], game, rng)
        rewards: dict[str, dict[str, Any]] = {}
        category_names = {"artifact":"法器", "technique":"功法", "pill":"丹药"}
        for category in ("artifact", "technique", "pill"):
            pool = self._treasure_reward_pool(game, category)
            reward = rng.choices(pool, weights=[max(1, int(row["tier"])) for row in pool], k=1)[0]
            content_id = str(reward["content_id"])
            name = TECHNIQUE_CATALOG[content_id].name if category == "technique" else ITEM_CATALOG[content_id].name
            rewards[category] = {"content_id":content_id, "name":name, "tier":int(reward["tier"])}
        event["runtime"] = {"rewards":rewards}
        for choice in event["choices"]:
            category = choice["id"]
            reward = rewards[category]
            brackets = ("《", "》") if category == "technique" else ("“", "”")
            choice["text"] = f"选择{category_names[category]}：{brackets[0]}{reward['name']}{brackets[1]}（{reward['tier']}阶）"
        return event

    def _claim_treasure_reward(self, game: GameState, pending: dict[str, Any], category: str) -> tuple[str, str]:
        player = game.player
        reward = pending.get("runtime", {}).get("rewards", {}).get(category)
        if not reward:
            raise ValueError("这份探宝奖励已经失落")
        content_id = str(reward["content_id"])
        if category != "technique":
            add_item(player, content_id)
            category_name = "法器" if category == "artifact" else "丹药"
            return "treasure_claimed", f"你取走{category_name}“{ITEM_CATALOG[content_id].name}” ×1。"
        technique = TECHNIQUE_CATALOG[content_id]
        learned = acquire_technique(player, technique)
        if learned:
            return "technique_learned", f"你取走功法《{technique.name}》，已收入已悟功法。"
        return "technique_copy_gained", f"你取走《{technique.name}》传承玉简，已收入包裹，可用于升级。"
