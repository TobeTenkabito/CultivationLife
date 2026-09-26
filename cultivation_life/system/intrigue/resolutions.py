from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import copy
    import random
    import uuid
    from typing import Any
    from ...content_registry import RACE_DEFINITIONS, REALMS, WORLD_SYSTEMS
    from ...models import GameState, HistoryRecord, SectNpc
    from ...runtime import decode_rng, encode_rng, now_iso
    from ...world_state import race_pair
    from .. import intrigue_system as _source
    PLAYER_ID = _source.PLAYER_ID
    PERSONALITY_LABELS = _source.PERSONALITY_LABELS
    STYLE_LABELS = _source.STYLE_LABELS
    RESOLUTION_LABELS = _source.RESOLUTION_LABELS


class IntrigueResolutionMethods:
    def _intrigue_vote_chance(
        self, game: GameState, npc: SectNpc, resolution_type: str, kind: str,
        faction_id: str, target_id: str, proposer_id: str,
    ) -> tuple[float, list[str]]:
        traits = self._ensure_intrigue_personality(game, npc)
        if resolution_type == "make_peace":
            return 1.0, ["战争已经发生，停战提案优先止损"]
        faction_record = self._ensure_intrigue_faction(game, kind, faction_id)
        style = self._intrigue_governance_style(game, npc) if npc.id == faction_record.get("controller_id") else traits.get("governance_style") or faction_record.get("policy")
        chance = 0.5
        reasons: list[str] = []
        style_bias = {
            "balance": {"make_peace": .14, "investment": .08, "declare_war": -.10},
            "internal": {"mass_recruitment": .18, "disciple_recruitment": .18, "investment": .16, "declare_war": -.12},
            "diplomacy": {"form_alliance": .20, "make_peace": .18, "declare_war": -.18, "break_alliance": -.10},
            "military": {"declare_war": .22, "intervene_war": .16, "make_peace": -.10},
        }
        if style in style_bias:
            chance += style_bias[style].get(resolution_type, 0)
            reasons.append(STYLE_LABELS[str(style)])
        if target_id and kind in {"sect", "race"} and resolution_type in {"declare_war", "form_alliance", "break_alliance"}:
            relations = game.sect_relations if kind == "sect" else game.race_relations
            relation_affinity = float(relations.get(race_pair(faction_id, target_id), {}).get("affinity", 0))
            relation_bias = max(-.22, min(.22, relation_affinity / 320.0))
            if resolution_type == "form_alliance":
                chance += relation_bias
            elif resolution_type == "declare_war":
                chance -= relation_bias
            else:
                chance -= relation_bias * .7
            if abs(relation_bias) >= .04:
                reasons.append("既有外交关系良好" if relation_affinity > 0 else "既有外交关系恶劣")
        primary = str(traits.get("primary"))
        if resolution_type in {"declare_war", "intervene_war"}:
            if primary in {"fanatical", "forceful", "warlike"}:
                chance += .16; reasons.append(PERSONALITY_LABELS[primary] + "倾向强硬")
            if primary in {"cautious", "restrained", "smooth"}:
                chance -= .15; reasons.append(PERSONALITY_LABELS[primary] + "厌恶冒险")
            if target_id and kind == "sect" and target_id in game.sects:
                own_power = sum(self._npc_power(row) for row in self._intrigue_members(game, kind, faction_id) if row.alive)
                target_power = sum(self._npc_power(row) for row in self._intrigue_members(game, kind, target_id) if row.alive)
                target_power += sum(self._npc_power(npc2) for npc2 in self._intrigue_guest_npcs(game, kind, target_id))
                if own_power < target_power:
                    chance -= min(.28, (target_power / max(1.0, own_power) - 1) * .12); reasons.append("敌强且有客卿威慑")
        elif resolution_type in {"form_alliance", "make_peace"} and primary in {"smooth", "generous", "open"}:
            chance += .12; reasons.append(PERSONALITY_LABELS[primary] + "重视关系")
        if float(npc.affinity or 0) > 40 and proposer_id == PLAYER_ID:
            chance += .08; reasons.append("与提案人交好")
        if self._intrigue_is_imprisoned(game, npc.id):
            chance = 0
        return max(.05, min(.95, chance)), reasons

    def _intrigue_resolve(
        self, game: GameState, kind: str, faction_id: str, resolution_type: str,
        target_id: str, player_vote: bool | None, proposer_id: str, rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if resolution_type not in RESOLUTION_LABELS:
            raise ValueError("未知重大决议")
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        ballots: list[dict[str, Any]] = []
        if self._intrigue_has_decision_authority(game, kind, faction_id) and player_vote is not None:
            ballots.append({"id": PLAYER_ID, "name": game.player.name, "vote": bool(player_vote), "player": True, "reasons": ["一人一票"]})
        voters = {npc.id: npc for npc in self._intrigue_members(game, kind, faction_id)}
        for guest in self._intrigue_guest_npcs(game, kind, faction_id):
            voters.setdefault(guest.id, guest)
        for npc in voters.values():
            if not self._intrigue_has_decision_authority(game, kind, faction_id, npc.id):
                continue
            chance, reasons = self._intrigue_vote_chance(game, npc, resolution_type, kind, faction_id, target_id, proposer_id)
            ballots.append({"id": npc.id, "name": npc.name, "vote": rng.random() < chance, "chance": round(chance, 3), "player": False, "reasons": reasons})
        if not ballots:
            raise ValueError("当前势力没有具备决策权的成员")
        yes = sum(bool(row["vote"]) for row in ballots)
        passed = yes > len(ballots) / 2
        state = self._intrigue_state(game)
        state["sequence"] = int(state.get("sequence", 0)) + 1
        resolution = {
            "id": f"resolution_{state['sequence']}", "faction_id": faction_id, "faction_name": self._intrigue_faction_name(game, kind, faction_id),
            "kind": kind, "type": resolution_type, "type_name": RESOLUTION_LABELS[resolution_type],
            "proposer_id": proposer_id, "target_id": target_id, "votes": ballots,
            "yes": yes, "total": len(ballots), "result": "passed" if passed else "rejected", "age": game.player.age,
        }
        if passed:
            self._intrigue_apply_resolution(game, record, resolution_type, target_id, rng, context=context)
            if resolution_type == "disciple_recruitment":
                pending = record.get("pending_recruitment") or {}
                resolution["candidate_count"] = len(pending.get("candidates", []))
        state["resolutions"].append(resolution)
        state["resolutions"] = state["resolutions"][-80:]
        summary = f"{resolution['faction_name']}就“{resolution['type_name']}”议决：{yes}/{len(ballots)} 票赞成，决议{'通过' if passed else '未通过'}。"
        diplomacy_resolution = resolution_type in {"declare_war", "make_peace", "form_alliance", "break_alliance"}
        event_id = (
            "SYS_PLAYER_SECT_VOTE" if diplomacy_resolution and proposer_id == PLAYER_ID and kind == "sect" else
            "SYS_PLAYER_RACE_VOTE" if diplomacy_resolution and proposer_id == PLAYER_ID and kind == "race" else
            "SYS_INTRIGUE_RESOLUTION"
        )
        state_diff = copy.deepcopy(resolution)
        if diplomacy_resolution and target_id:
            state_diff["races" if kind == "race" else "sects"] = [faction_id, target_id]
        entity = self._intrigue_entity(game, kind, faction_id)
        event_world = entity.world if entity else game.player.world
        game.history.append(HistoryRecord(
            event_id, 1, game.player.age, "势力决议", resolution_type,
            "passed" if passed else "rejected", summary, state_diff,
            ["system", "intrigue", "vote", kind, *( ["diplomacy"] if diplomacy_resolution else [] ), "world_news", f"world:{event_world}"],
        ))
        return resolution

    def _intrigue_apply_resolution(
        self, game: GameState, record: dict[str, Any], resolution_type: str,
        target_id: str, rng: random.Random, *, context: dict[str, Any] | None = None,
    ) -> None:
        kind, faction_id = str(record["kind"]), str(record["id"])
        if resolution_type in {"declare_war", "make_peace", "form_alliance", "break_alliance"}:
            status = {"declare_war": "war", "make_peace": "truce", "form_alliance": "alliance", "break_alliance": "neutral"}[resolution_type]
            relations = game.race_relations if kind == "race" else game.sect_relations
            if kind not in {"sect", "race"} or not target_id:
                return
            relation = relations.setdefault(race_pair(faction_id, target_id), {"affinity": 0.0, "status": "neutral", "since_age": game.player.age})
            if relation.get("status") == "war" and status != "war":
                # Field wars still use the established war-peace settlement flow.
                return
            self._set_diplomatic_relation(game, relation, status, faction_id, target_id, kind,
                                           {"war": -75.0, "truce": -5.0, "alliance": 80.0, "neutral": 0.0}[status])
        elif resolution_type == "mass_recruitment" and kind in {"sect", "family"}:
            entity = self._intrigue_entity(game, kind, faction_id)
            if not entity:
                return
            for _ in range(rng.randint(2, 4)):
                index = uuid.uuid4().hex[:10]
                realm_index = rng.choices([0, 1, 2], weights=[4, 5, 1], k=1)[0]
                lifespan_range = REALMS[realm_index].lifespan
                age = rng.randint(16, 42)
                lifespan = max(age + 1, rng.randint(*lifespan_range)) if lifespan_range else None
                npc = SectNpc(f"intrigue_recruit_{index}", rng.choice(["宁川", "苏砚", "沈禾", "顾霜", "陆迟", "叶青"]),
                              "新晋成员", realm_index, 1, age, lifespan, path=entity.path,
                              race=entity.allegiance_race or "human", world=entity.world,
                              affinity=rng.uniform(8, 28), faction_id=faction_id if kind == "sect" else None)
                entity.npcs.append(npc)
                self._ensure_intrigue_personality(game, npc)
            record["unrest"] = max(0.0, float(record.get("unrest", 0)) - 2)
        elif resolution_type == "disciple_recruitment" and kind == "sect":
            filters = self._normalize_intrigue_recruitment_filters(
                game, (context or {}).get("filters"),
            )
            record["pending_recruitment"] = self._generate_intrigue_recruitment_session(
                game, faction_id, filters, rng,
            )
            record["unrest"] = max(0.0, float(record.get("unrest", 0)) - 1)
        elif resolution_type == "investment":
            record["resources"] = int(record.get("resources", 0)) + 25
            record["unrest"] = max(0.0, float(record.get("unrest", 0)) - 4)
        elif resolution_type == "relocate" and kind in {"sect", "family"} and target_id in WORLD_SYSTEMS.get("world_profiles", {}):
            entity = self._intrigue_entity(game, kind, faction_id)
            if entity:
                entity.world = target_id
                for npc in entity.npcs:
                    npc.world = target_id
        elif resolution_type == "policy" and target_id in STYLE_LABELS:
            record["policy"] = target_id
        elif resolution_type == "intervene_war":
            record["intervention_target"] = target_id
            war = next((row for row in game.wars if row.get("id") == target_id and row.get("status") in {"active", "peace_ready"}), None)
            if war and war.get("kind") == kind and not self._participant_side(war, faction_id):
                self._add_war_participant(game, war, "defender", faction_id, str(war.get("defender_id", "")))
                self._append_war_log(
                    game, war, "介入战争",
                    f"{self._intrigue_faction_name(game, kind, faction_id)}经决议介入战局，加入防御阵营。",
                )

    def intrigue_propose_resolution(
        self, game_id: str, kind: str, resolution_type: str, target_id: str = "", player_vote: bool = True,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if not self._intrigue_enabled():
            raise ValueError("《明争暗斗：合纵连横》DLC 尚未启用")
        if game.pending_event or game.player.imprisonment:
            raise ValueError("当前状态无法召开势力议事")
        faction_id = self._intrigue_player_faction_id(game, kind)
        if not faction_id or not self._intrigue_has_decision_authority(game, kind, faction_id):
            raise ValueError("你没有该势力的决策权")
        if resolution_type == "disciple_recruitment":
            raise ValueError("扩招徒弟需要先设置筛选条件")
        if resolution_type in {"declare_war", "make_peace", "form_alliance", "break_alliance"}:
            if kind == "sect" and (target_id not in game.sects or target_id == faction_id):
                raise ValueError("目标宗门无效")
            if kind == "race" and (target_id not in RACE_DEFINITIONS or target_id == faction_id):
                raise ValueError("目标种族无效")
            if resolution_type == "make_peace" and self._active_war(game, kind, faction_id, target_id):
                raise ValueError("战争已经进入征伐阶段，请在战争窗口提交和约；和约仍会先经过势力表决")
        rng = decode_rng(game.seed, game.rng_state)
        self._intrigue_resolve(game, kind, faction_id, resolution_type, target_id, bool(player_vote), PLAYER_ID, rng)
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
