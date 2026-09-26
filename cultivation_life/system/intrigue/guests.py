from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from ...models import GameState, HistoryRecord, SectNpc
    from ...runtime import decode_rng, encode_rng, now_iso
    from ...world_state import race_pair
    from .. import intrigue_system as _source
    PLAYER_ID = _source.PLAYER_ID


class IntrigueGuestMethods:
    def _intrigue_can_invite_guest(
        self, game: GameState, npc_id: str, kind: str = "sect",
    ) -> bool:
        if not self._intrigue_enabled() or not npc_id or kind == "race":
            return False
        faction_id = self._intrigue_player_faction_id(game, kind)
        if not faction_id or not self._intrigue_has_control(game, kind, faction_id):
            return False
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        if any(str(row.get("npc_id", "")) == npc_id for row in record.get("guests", [])):
            return False
        if any(row.id == npc_id for row in self._intrigue_members(game, kind, faction_id)):
            return False
        npc = self._intrigue_find_npc(game, npc_id)
        relation = self._intrigue_player_relation(game, npc_id)
        source: Any = npc or relation
        if not source:
            return False
        alive = source.alive if isinstance(source, SectNpc) else bool(source.get("alive", True))
        world = source.world if isinstance(source, SectNpc) else str(source.get("world", game.player.world))
        if not alive or world != game.player.world or self._intrigue_is_imprisoned(game, npc_id):
            return False
        npc_affinity = float(npc.affinity or 0) if npc else -100.0
        relation_affinity = float(relation.get("affinity", 0)) if relation else -100.0
        is_friend = any(str(row.get("id", "")) == npc_id for row in game.player.dao_friends)
        return is_friend or max(npc_affinity, relation_affinity) >= 30.0

    def intrigue_guest_action(self, game_id: str, kind: str, action: str, npc_id: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        if not self._intrigue_enabled():
            raise ValueError("《明争暗斗：合纵连横》DLC 尚未启用")
        state = self._intrigue_state(game)
        rng = decode_rng(game.seed, game.rng_state)
        if action in {"accept_invitation", "decline_invitation"}:
            invitation = state.get("pending_guest_invitation")
            if not invitation:
                raise ValueError("当前没有待回应的客卿邀请")
            entity = self._intrigue_entity(game, str(invitation["kind"]), str(invitation["faction_id"]))
            if not entity or entity.extinct or entity.world != game.player.world:
                state["pending_guest_invitation"] = None
                game.updated_at = now_iso()
                self.store.save(game)
                raise ValueError("这份客卿邀请来自其他界面，已经失效")
            record = self._ensure_intrigue_faction(game, str(invitation["kind"]), str(invitation["faction_id"]))
            if action == "accept_invitation":
                record["guests"].append({"npc_id": PLAYER_ID, "name": game.player.name, "defense_required": True, "offense_opt_in": False})
                summary = f"你接受了{invitation['faction_name']}的{invitation['title']}之邀。"
            else:
                summary = f"你谢绝了{invitation['faction_name']}的{invitation['title']}之邀。"
            state["pending_guest_invitation"] = None
        elif action == "resign":
            faction_id = npc_id
            record = self._intrigue_state(game).get("factions", {}).get(self._intrigue_key(kind, faction_id))
            if not record:
                raise ValueError("没有找到这份客卿身份")
            before = len(record.get("guests", []))
            record["guests"] = [row for row in record.get("guests", []) if row.get("npc_id") != PLAYER_ID]
            if len(record["guests"]) == before:
                raise ValueError("你并非该势力客卿")
            summary = f"你辞去了{self._intrigue_faction_name(game, kind, faction_id)}的客卿身份。"
        else:
            faction_id = self._intrigue_player_faction_id(game, kind)
            if not faction_id or not self._intrigue_has_control(game, kind, faction_id):
                raise ValueError("你没有该势力的客卿任免权")
            record = self._ensure_intrigue_faction(game, kind, faction_id)
            guests = record["guests"]
            if action == "invite":
                if not self._intrigue_can_invite_guest(game, npc_id, kind):
                    raise ValueError("目标不是当前界面的高好感人物或道友，或其身份不符合客卿邀请条件")
                npc = self._intrigue_find_npc(game, npc_id)
                relation = self._intrigue_player_relation(game, npc_id)
                if not npc and relation:
                    npc = self._persist_relationship_npc(game, relation, "受邀担任客卿")
                if not npc:
                    raise ValueError("目标人物已经失联")
                if relation:
                    npc.affinity = max(float(npc.affinity or 0), float(relation.get("affinity", 0)))
                personality = self._ensure_intrigue_personality(game, npc)
                chance = 0.48 + float(npc.affinity or 0) / 180 + (0.08 if personality["primary"] in {"smooth", "open", "greedy"} else 0) - (0.12 if personality["primary"] in {"suspicious", "conservative"} else 0)
                source_faction = self._npc_faction_id(game, npc.id)
                if kind == "sect" and source_faction and source_faction != faction_id:
                    relation = game.sect_relations.get(race_pair(source_faction, faction_id), {})
                    if relation.get("status") == "war":
                        raise ValueError("目标对本势力负有敌对义务，不会接受客卿邀请")
                    chance += .06 if relation.get("status") == "alliance" else -.08
                chance = max(0.12, min(0.95, chance))
                if rng.random() >= chance:
                    npc.affinity = float(npc.affinity or 0) - 2
                    summary = f"{npc.name}权衡职责与旧有关系后，婉拒了客卿邀请（接受率 {chance:.0%}）。"
                else:
                    guests.append({"npc_id": npc.id, "name": npc.name, "defense_required": True, "offense_opt_in": False, "joined_age": game.player.age})
                    npc.affinity = min(
                        100.0, float(npc.affinity or 0) + self._sage_affinity_gain(game.player, 4),
                    )
                    for war in game.wars:
                        if (war.get("status") in {"active", "peace_ready"} and war.get("kind") == kind
                                and faction_id in self._coalition_ids(war, "defender")):
                            if npc.id not in war.get("roster", {}).get("defender", []):
                                war["roster"]["defender"].append(npc.id)
                                war.setdefault("roster_owner", {})[npc.id] = faction_id
                    summary = f"{npc.name}接受邀请，成为{self._intrigue_faction_name(game, kind, faction_id)}的{'供奉' if kind == 'family' else '客卿长老'}；防御战争必须出战，进攻战争可拒绝。"
            elif action == "remove":
                before = len(guests)
                guests[:] = [row for row in guests if row.get("npc_id") != npc_id]
                if len(guests) == before:
                    raise ValueError("目标不是本势力客卿")
                npc = self._intrigue_find_npc(game, npc_id)
                if npc:
                    npc.affinity = float(npc.affinity or 0) - 10
                for war in game.wars:
                    if war.get("status") in {"active", "peace_ready"} and war.get("roster_owner", {}).get(npc_id) == faction_id:
                        defender_roster = war.get("roster", {}).get("defender", [])
                        if npc_id in defender_roster:
                            defender_roster.remove(npc_id)
                        war.get("roster_owner", {}).pop(npc_id, None)
                summary = f"你撤销了{npc.name if npc else '该修士'}的客卿身份。"
            elif action == "regularize":
                guest = next((row for row in guests if row.get("npc_id") == npc_id), None)
                npc = self._intrigue_find_npc(game, npc_id)
                if not guest or not npc:
                    raise ValueError("目标客卿不存在")
                if game.player.faction_contribution < 30:
                    raise ValueError("转正需要消耗 30 点势力贡献")
                specs = self._intrigue_position_specs(kind)
                vacancy = next((pid for pid, spec in specs.items() if pid not in {"leader", "family_head"} and not record["positions"].get(pid) and npc.realm_index >= int(spec.get("minimum_realm", 0))), None)
                if not vacancy:
                    raise ValueError("没有符合其修为的正式职位空缺")
                game.player.faction_contribution -= 30
                guests.remove(guest)
                entity = self._intrigue_entity(game, kind, faction_id)
                if entity and not any(row.id == npc.id for row in entity.npcs):
                    entity.npcs.append(npc)
                npc.faction_id = faction_id if kind == "sect" else npc.faction_id
                record["positions"][vacancy] = npc.id
                summary = f"{npc.name}消耗举荐名额转为正式成员，并出任{specs[vacancy]['name']}。"
            else:
                raise ValueError("未知客卿操作")
        game.history.append(HistoryRecord(
            "SYS_INTRIGUE_GUEST", 1, game.player.age, "客卿往来", action, "resolved", summary,
            {"npc_id": npc_id}, ["system", "intrigue", "guest", "faction"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _intrigue_guest_npcs(self, game: GameState, kind: str, faction_id: str) -> list[SectNpc]:
        if not self._intrigue_enabled():
            return []
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        result = []
        for guest in record.get("guests", []):
            if guest.get("npc_id") == PLAYER_ID:
                continue
            npc = self._intrigue_find_npc(game, str(guest.get("npc_id", "")))
            if npc and npc.alive and not self._intrigue_is_imprisoned(game, npc.id):
                result.append(npc)
        return result

    def _intrigue_defensive_guest_ids(self, game: GameState, kind: str, faction_id: str, world: str) -> list[str]:
        return [npc.id for npc in self._intrigue_guest_npcs(game, kind, faction_id) if npc.world == world]

    def _intrigue_player_guest_side(self, game: GameState, war: dict[str, Any]) -> str | None:
        if not self._intrigue_enabled() or game.player.world != war.get("world"):
            return None
        for faction_id in self._coalition_ids(war, "defender"):
            record = self._ensure_intrigue_faction(game, str(war.get("kind")), faction_id)
            if any(row.get("npc_id") == PLAYER_ID and row.get("defense_required", True) for row in record.get("guests", [])):
                return "defender"
        return None
