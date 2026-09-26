from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random
    from typing import Any
    from ...models import GameState, HistoryRecord
    from ...runtime import now_iso
    from ..tianji_system import tianji_content_available


class TianjiIntelligenceMethods:
    def _tianji_reveal(self, game: GameState, artifact_id: str, level: int, source: str) -> bool:
        state = game.tianji_state
        old = int(state["knowledge"].get(artifact_id, 0))
        new = max(old, min(5, int(level)))
        if new == old:
            return False
        state["knowledge"][artifact_id] = new
        artifact = self._tianji_artifact(state, artifact_id)
        state["discovery_log"].append({
            "artifact_id": artifact_id, "name": artifact["name"], "from": old,
            "to": new, "source": source, "age": game.player.age,
        })
        state["discovery_log"] = state["discovery_log"][-200:]
        return True

    def _tianji_npc_conversation_clue(
        self, game: GameState, npc_id: str, rng: random.Random,
    ) -> str:
        """Occasionally turn an actual NPC conversation into persistent intel."""
        if not tianji_content_available():
            return ""
        self._ensure_tianji_state(game)
        state = game.tianji_state
        held = next((
            (artifact_id, holder) for artifact_id, holder in state.get("holders", {}).items()
            if str(holder.get("npc_id", "")) == str(npc_id)
        ), None)
        artifact: dict[str, Any] | None = None
        chance = .12
        if held:
            artifact = self._tianji_artifact(state, held[0])
            chance = .72
        else:
            candidates = [
                row for row in state.get("artifacts", [])
                if int(state["knowledge"].get(row["id"], 0)) < 3
                and row.get("origin_world") == game.player.world
            ]
            if candidates:
                artifact = rng.choice(candidates)
        if not artifact or rng.random() >= chance:
            return ""
        old = int(state["knowledge"].get(artifact["id"], 0))
        target = min(3, old + 1)
        if target <= old or not self._tianji_reveal(
            game, str(artifact["id"]), target, f"与{npc_id}交谈所得口述线索",
        ):
            return ""
        return f" 对方谈及一则不肯写入玉简的秘闻，你对【{artifact['name']}】的情报提升至 Lv{target}。"

    def _maybe_tianji_intelligence_event(
        self, game: GameState, rng: random.Random,
    ) -> str | None:
        """Resolve a rare, non-clickable clue event after a real time action."""
        if not tianji_content_available():
            return None
        self._ensure_tianji_state(game)
        settings = self._tianji_config().get("intelligence_events", {})
        if rng.random() >= float(settings.get("chance_per_action_unit", .018)):
            return None
        state = game.tianji_state
        realm = game.player.realm_index
        max_level = 5 if realm >= int(settings.get("minimum_realm_for_level_5", 8)) else 4
        if realm < int(settings.get("minimum_realm_for_level_4", 6)):
            max_level = 3
        partial = [
            row for row in state.get("artifacts", [])
            if 0 < int(state["knowledge"].get(row["id"], 0)) < max_level
        ]
        unknown = [
            row for row in state.get("artifacts", [])
            if int(state["knowledge"].get(row["id"], 0)) == 0
        ]
        use_partial = bool(partial) and (
            not unknown or rng.random() < float(settings.get("partial_chain_chance", .68))
        )
        candidates = partial if use_partial else unknown
        if not candidates:
            return None
        weights = []
        for artifact in candidates:
            local = 5.0 if artifact.get("origin_world") == game.player.world else 1.0
            rank = int(artifact.get("rank", 100))
            secrecy = .28 if rank <= 10 else .55 if rank <= 30 else 1.0
            current = int(state["knowledge"].get(artifact["id"], 0))
            depth = (1.0, 1.0, .48, .16, .035)[min(4, current)]
            weights.append(local * secrecy * depth)
        artifact = rng.choices(candidates, weights=weights, k=1)[0]
        old = int(state["knowledge"].get(artifact["id"], 0))
        new = min(max_level, old + 1)
        fallback_sources = {
            1: ("残卷露名", "你在一卷残破游记的夹层里发现了器名与模糊形制。"),
            2: ("斗痕辨器", "一处古战场残留的器痕，与坊间密谈相互印证。"),
            3: ("器纹拓影", "流散黑市的器纹拓片补全了关键材料方向。"),
            4: ("真方残页", "一页被多重禁制封存的古方，显出了完整材料次序。"),
            5: ("天机落点", "跨界行商与古阵星图的数处记录，终于指向同一条踪迹。"),
        }
        event_pool = settings.get("event_pool", {}).get(str(new), [])
        source = rng.choice(event_pool) if event_pool else None
        title, body = (
            (str(source["title"]), str(source["body"]))
            if isinstance(source, dict) and source.get("title") and source.get("body")
            else fallback_sources[new]
        )
        if not self._tianji_reveal(game, str(artifact["id"]), new, f"随机事件：{title}"):
            return None
        summary = f"{body}【{artifact['name']}】情报提升至 Lv{new}。"
        game.history.append(HistoryRecord(
            "SYS_TIANJI_INTELLIGENCE", 1, game.player.age, title,
            str(artifact["id"]), f"knowledge_lv{new}", summary,
            {"artifact_id": artifact["id"], "from": old, "to": new},
            ["system", "tianji", "intelligence", "random_event"],
        ))
        return f"{game.player.age}岁：{summary}"

    def tianji_action(self, game_id: str, action: str, artifact_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        self._ensure_tianji_state(game)
        self._tianji_artifact(game.tianji_state, artifact_id)
        if action in {"activate", "deactivate"}:
            owned_rows = [
                row for row in game.player.crafted_artifacts
                if row.get("tianji", {}).get("definition_id") == artifact_id
            ]
            owned = max(
                owned_rows,
                key=lambda row: float(row.get("tianji", {}).get("replica_ratio", 0.0)),
                default=None,
            )
            if action == "deactivate":
                active_instance = str(game.tianji_state.get("activated_artifact_id") or "")
                active_owned = next((row for row in owned_rows if str(row.get("id")) == active_instance), None)
                owned = active_owned or owned
            if not owned:
                raise ValueError("你尚未持有这件神机的真体或仿品")
            if action == "activate":
                old_ids = {str(row.get("id")) for row in game.player.crafted_artifacts if row.get("tianji")}
                game.player.equipped_crafted_artifact_ids = [value for value in game.player.equipped_crafted_artifact_ids if value not in old_ids]
                game.player.equipped_crafted_artifact_ids.append(str(owned["id"]))
                game.tianji_state["activated_artifact_id"] = str(owned["id"])
            else:
                game.player.equipped_crafted_artifact_ids = [value for value in game.player.equipped_crafted_artifact_ids if value != str(owned["id"])]
                if game.tianji_state.get("activated_artifact_id") == owned["id"]:
                    game.tianji_state["activated_artifact_id"] = None
        else:
            raise ValueError("未知神机操作")
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def debug_reveal_all_tianji(self, game_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        if not tianji_content_available():
            raise ValueError("神机百变 DLC 当前未加载")
        self._ensure_tianji_state(game)
        game.tianji_state["knowledge"] = {
            str(artifact["id"]): 5 for artifact in game.tianji_state.get("artifacts", [])
        }
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
