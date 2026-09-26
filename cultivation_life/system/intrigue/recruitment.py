from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import copy
    import random
    from typing import Any
    from ...content_registry import FACTION_SYSTEMS, PATH_NAMES, REALMS, ROOT_DEFINITIONS
    from ...models import GameState, HistoryRecord, SectNpc
    from ...rules import expected_combat_power
    from ...runtime import decode_rng, encode_rng, now_iso
    from ..intrigue_system import intrigue_rules
    from .. import intrigue_system as _source
    PLAYER_ID = _source.PLAYER_ID


class IntrigueRecruitmentMethods:
    @staticmethod
    def _intrigue_recruitment_config() -> dict[str, Any]:
        return dict(intrigue_rules().get("disciple_recruitment", {}))

    def _intrigue_recruitment_realm_options(self, world: str) -> list[int]:
        distributions = FACTION_SYSTEMS.get("recruitment_distribution_by_world", {})
        rows = distributions.get(world, FACTION_SYSTEMS.get("recruitment_distribution", []))
        threshold = self._intrigue_decision_threshold("sect")
        return sorted({
            int(row.get("realm_index", 0)) for row in rows
            if 0 <= int(row.get("realm_index", 0)) < threshold
        })

    def _normalize_intrigue_recruitment_filters(
        self, game: GameState, filters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        raw = filters if isinstance(filters, dict) else {}
        root = str(raw.get("spirit_root", "any"))
        if root not in {"any", "heavenly"}:
            raise ValueError("灵根筛选只能选择不筛选或天灵根")
        realm_raw = raw.get("realm_index", "any")
        if realm_raw in {None, "", "any"}:
            realm: int | None = None
        else:
            try:
                realm = int(realm_raw)
            except (TypeError, ValueError) as error:
                raise ValueError("修为筛选无效") from error
            allowed_realms = self._intrigue_recruitment_realm_options(game.player.world)
            if realm not in allowed_realms:
                raise ValueError("所选修为不属于当前界面可招收的弟子境界，或已经拥有决策权")
        path = str(raw.get("path", "any"))
        if path != "any" and path not in PATH_NAMES:
            raise ValueError("修炼功法路线筛选无效")
        combat = str(raw.get("combat", "any"))
        combat_filters = self._intrigue_recruitment_config().get("combat_filters", {})
        if combat not in combat_filters:
            raise ValueError("战斗力筛选无效")
        gender = str(raw.get("gender", "any"))
        if gender not in {"any", "male", "female"}:
            raise ValueError("性别筛选无效")
        return {
            "spirit_root": root, "realm_index": realm, "path": path,
            "combat": combat, "gender": gender,
        }

    def _intrigue_recruitment_filter_summary(self, filters: dict[str, Any]) -> str:
        combat_filters = self._intrigue_recruitment_config().get("combat_filters", {})
        realm = filters.get("realm_index")
        return " · ".join((
            "天灵根" if filters.get("spirit_root") == "heavenly" else "灵根不限",
            REALMS[int(realm)].name if realm is not None else "修为不限",
            PATH_NAMES.get(str(filters.get("path")), "功法不限"),
            str(combat_filters.get(str(filters.get("combat")), {}).get("name", "战力不限")),
            {"male": "男修", "female": "女修"}.get(str(filters.get("gender")), "性别不限"),
        ))

    def _generate_intrigue_recruitment_session(
        self, game: GameState, faction_id: str, filters: dict[str, Any], rng: random.Random,
    ) -> dict[str, Any]:
        sect = game.sects.get(faction_id)
        if not sect or sect.extinct:
            raise ValueError("当前宗门已经不存在")
        config = self._intrigue_recruitment_config()
        maximum = max(1, min(5, int(config.get("max_candidates", 5))))
        pool_low, pool_high = config.get("applicant_pool", [6, 12])
        applicant_count = rng.randint(max(1, int(pool_low)), max(int(pool_low), int(pool_high)))
        appearance_chance = max(0.05, min(1.0, float(config.get("appearance_chance", .78))))
        combat_spec = config.get("combat_filters", {}).get(str(filters.get("combat")), {})
        minimum_ratio = max(0.0, min(1.5, float(combat_spec.get("minimum_ratio", 0))))
        allowed_realms = set(self._intrigue_recruitment_realm_options(sect.world))
        state = self._intrigue_state(game)
        state["recruitment_sequence"] = int(state.get("recruitment_sequence", 0)) + 1
        sequence = int(state["recruitment_sequence"])
        surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "江", "闻", "苏", "沈"]
        given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚", "青", "禾"]
        candidates: list[dict[str, Any]] = []
        for attempt in range(applicant_count):
            if rng.random() >= appearance_chance:
                continue
            realm_index = self._recruit_realm_index(rng.random(), sect.world)
            if realm_index not in allowed_realms:
                continue
            if filters.get("realm_index") is not None and realm_index != int(filters["realm_index"]):
                continue
            path = self._random_npc_path(sect.id, rng)
            if filters.get("path") != "any" and path != filters.get("path"):
                continue
            spirit_root = self._random_npc_root(realm_index, rng) if realm_index else "none"
            if (
                filters.get("spirit_root") == "heavenly"
                and ROOT_DEFINITIONS.get(spirit_root, {}).get("tier") != "天灵根"
            ):
                continue
            gender = rng.choice(("male", "female"))
            if filters.get("gender") != "any" and gender != filters.get("gender"):
                continue
            layer = 1 if realm_index == 0 else rng.randint(1, REALMS[realm_index].layers)
            age, lifespan = self._roll_recruit_age_lifespan(realm_index, path, rng, young=True)
            npc = SectNpc(
                id=f"{sect.id}_disciple_{sequence}_{attempt}",
                name=rng.choice(surnames) + rng.choice(given), title="候选弟子",
                realm_index=realm_index, layer=layer, age=age, lifespan=lifespan,
                spirit_root=spirit_root, path=path,
                race=sect.allegiance_race or game.player.race, world=sect.world,
                affinity=rng.uniform(8, 26), combat_factor=rng.uniform(.68, 1.34),
                faction_id=sect.id, gender=gender,
            )
            npc.treasure_item_id = self._select_npc_treasure(npc, rng)
            power = self._npc_power(npc)
            ratio = power / max(1.0, expected_combat_power(realm_index, layer))
            if ratio < minimum_ratio:
                continue
            candidates.append({
                "npc": npc.to_dict(), "combat_power": round(power, 1),
                "combat_ratio": round(ratio, 3),
            })
            if len(candidates) >= maximum:
                break
        return {
            "id": f"disciple_recruitment_{sequence}",
            "created_unit": game.diplomacy_unit,
            "filters": copy.deepcopy(filters), "filter_summary": self._intrigue_recruitment_filter_summary(filters),
            "candidates": candidates,
            "message": (
                f"共有 {len(candidates)} 名散修通过初筛，请任意选择录取。"
                if candidates else "宗门要求太苛刻，暂无散修符合。"
            ),
        }

    def intrigue_recruitment_action(
        self, game_id: str, action: str, filters: dict[str, Any] | None = None,
        candidate_ids: list[str] | None = None, player_vote: bool = True,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if not self._intrigue_enabled():
            raise ValueError("《明争暗斗：合纵连横》DLC 尚未启用")
        if game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法处理宗门扩招")
        faction_id = self._intrigue_player_faction_id(game, "sect")
        if not faction_id or not self._intrigue_has_decision_authority(game, "sect", faction_id):
            raise ValueError("你没有当前宗门的决策权")
        sect = game.sects.get(faction_id)
        if not sect or sect.extinct:
            raise ValueError("当前宗门已经不存在")
        record = self._ensure_intrigue_faction(game, "sect", faction_id)
        rng = decode_rng(game.seed, game.rng_state)
        if action == "propose":
            if record.get("pending_recruitment"):
                raise ValueError("请先处理上一轮扩招候选人")
            normalized = self._normalize_intrigue_recruitment_filters(game, filters)
            self._intrigue_resolve(
                game, "sect", faction_id, "disciple_recruitment", "",
                bool(player_vote), PLAYER_ID, rng, context={"filters": normalized},
            )
        elif action == "confirm":
            pending = record.get("pending_recruitment")
            if not isinstance(pending, dict):
                raise ValueError("当前没有待选择的扩招候选人")
            raw_candidate_ids = candidate_ids if isinstance(candidate_ids, list) else []
            requested = list(dict.fromkeys(str(value) for value in raw_candidate_ids))
            available = {
                str(row.get("npc", {}).get("id", "")): row
                for row in pending.get("candidates", []) if row.get("npc", {}).get("id")
            }
            if any(candidate_id not in available for candidate_id in requested):
                raise ValueError("所选候选人不属于本轮扩招名单")
            maximum = min(5, int(self._intrigue_recruitment_config().get("max_candidates", 5)))
            if len(requested) > maximum:
                raise ValueError(f"每轮最多录取 {maximum} 名弟子")
            capacity = max(0, int(FACTION_SYSTEMS.get("max_members", 36)) - len([
                npc for npc in self._sect_members(game, sect) if npc.alive
            ]))
            if len(requested) > capacity:
                raise ValueError(f"宗门名册仅余 {capacity} 个空位")
            joined: list[SectNpc] = []
            for candidate_id in requested:
                npc = SectNpc.from_dict(copy.deepcopy(available[candidate_id]["npc"]))
                npc.title = "新入门弟子"
                npc.faction_id = faction_id
                sect.npcs.append(npc)
                self._ensure_intrigue_personality(game, npc)
                joined.append(npc)
            record["pending_recruitment"] = None
            names = "、".join(npc.name for npc in joined)
            result = "recruited" if joined else "closed"
            summary = (
                f"你从本轮候选中录取了 {len(joined)} 名弟子：{names}。"
                if joined else "本轮没有录取任何候选人，扩招名册已经关闭。"
            )
            game.history.append(HistoryRecord(
                "SYS_INTRIGUE_DISCIPLE_RECRUITMENT", 1, game.player.age,
                "宗门扩招", action, result, summary,
                {
                    "faction_id": faction_id, "candidate_ids": requested,
                    "filter_summary": pending.get("filter_summary"),
                },
                ["system", "intrigue", "sect", "recruitment", "disciple"],
            ))
        else:
            raise ValueError("未知的宗门扩招操作")
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
