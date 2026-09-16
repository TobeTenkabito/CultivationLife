from __future__ import annotations

import copy
import random
from typing import Any

from .content_registry import PATH_NAMES, RACE_DEFINITIONS, REALMS, WORLD_SYSTEMS
from .models import GameState, HistoryRecord, Player, SectNpc
from .possession_system import current_body_age
from .rules import max_hp, max_mp, opportunity_required
from .runtime import decode_rng, encode_rng, now_iso


def gender_name(value: str) -> str:
    return "女" if value == "female" else "男"


class ConcubineSystemMixin:
    """Base-game concubine relationships and the player's dependent state."""

    @staticmethod
    def _rank(value: Player | SectNpc | dict[str, Any]) -> tuple[int, int]:
        if isinstance(value, dict):
            return int(value.get("realm_index", 0)), int(value.get("layer", 1))
        return int(value.realm_index), int(value.layer)

    @staticmethod
    def _stable_gender(identity: str, name: str = "") -> str:
        return "female" if sum(ord(char) for char in (identity or name)) % 2 else "male"

    def _relation_by_id(self, player: Player, target_id: str) -> dict[str, Any] | None:
        relations = [
            player.master, player.dao_companion,
            *player.dao_friends, *player.disciples,
        ]
        return next(
            (row for row in relations if row and str(row.get("id")) == target_id), None,
        )

    def _concubine_target(
        self, game: GameState, target_id: str,
    ) -> tuple[dict[str, Any] | None, str]:
        prisoner = next(
            (row for row in game.player.prisoners if str(row.get("id")) == target_id), None,
        )
        if prisoner:
            return prisoner, "captive"
        npc = self._find_npc(game, target_id) or self._promote_cached_npc(game, target_id, "侍妾之请")
        if npc and npc.alive and npc.world == game.player.world:
            return npc.to_dict() | {
                "realm_name": self._npc_realm_name(npc),
                "path_name": PATH_NAMES.get(npc.path, npc.path),
                "race_name": RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                "combat_power": self._npc_power(npc),
                "npc_id": npc.id,
            }, "world"
        relation = self._relation_by_id(game.player, target_id)
        if relation and relation.get("alive", True) and relation.get("world", game.player.world) == game.player.world:
            return relation, "relationship"
        return None, ""

    def _normalize_concubine(self, target: dict[str, Any], source: str) -> dict[str, Any]:
        target_id = str(target.get("id") or target.get("npc_id") or "")
        gender = str(target.get("gender") or self._stable_gender(target_id, str(target.get("name", ""))))
        realm_index = int(target.get("realm_index", 0))
        layer = int(target.get("layer", 1))
        shell = SectNpc(
            target_id, str(target.get("name", "无名修士")), "", realm_index, layer,
            int(target.get("age", 18)), target.get("lifespan"),
            spirit_root=str(target.get("spirit_root", "none")), path=str(target.get("path", "dao")),
            race=str(target.get("race", "human")), world=str(target.get("world", "human")),
            gender=gender,
        )
        return {
            "id": target_id, "npc_id": str(target.get("npc_id") or target_id),
            "name": str(target.get("name", "无名修士")), "gender": gender,
            "gender_name": gender_name(gender), "realm_index": realm_index, "layer": layer,
            "realm_name": str(target.get("realm_name") or self._npc_realm_name(shell)),
            "age": int(target.get("age", 18)), "lifespan": target.get("lifespan"),
            "spirit_root": str(target.get("spirit_root", "none")),
            "path": str(target.get("path", "dao")),
            "path_name": PATH_NAMES.get(str(target.get("path", "dao")), str(target.get("path", "dao"))),
            "race": str(target.get("race", "human")),
            "world": str(target.get("world", "human")),
            "affinity": float(target.get("affinity", 0)),
            "combat_power": round(float(target.get("combat_power", 1.0) or 1.0), 1),
            "main_technique_id": target.get("main_technique_id"),
            "source": source, "joined_age": None, "last_cauldron_unit": None,
            "cauldron_uses": 0, "alive": True,
        }

    def manage_concubine(
        self, game_id: str, target_id: str, action: str,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法处理侍妾事务")
        rng = decode_rng(game.seed, game.rng_state)
        existing = next((row for row in player.concubines if str(row.get("id")) == target_id), None)

        if action == "recruit":
            if existing:
                raise ValueError("此人已经在侍妾名册中")
            target, source = self._concubine_target(game, target_id)
            if not target:
                raise ValueError("目标人物当前无法回应")
            normalized = self._normalize_concubine(target, source)
            normalized["world"] = player.world
            if normalized["gender"] != "female":
                raise ValueError("侍妾名分只可向女性修士提出")
            if self._rank(normalized) > self._rank(player):
                raise ValueError("修为高于你的修士必定拒绝侍妾之请")
            gap = player.realm_index - int(normalized["realm_index"])
            layer_gap = player.layer - int(normalized["layer"]) if gap == 0 else 0
            chance = 1.0 if source == "captive" else max(
                0.12, min(0.96, 0.34 + gap * 0.14 + layer_gap * 0.025 + float(normalized["affinity"]) / 300),
            )
            if rng.random() >= chance:
                npc = self._find_npc(game, normalized["npc_id"])
                if npc:
                    npc.affinity = float(npc.affinity or 0) - 6
                result = "refused"
                summary = f"{normalized['name']}拒绝了侍妾之请（同意率 {chance:.0%}）。"
            else:
                normalized["joined_age"] = player.age
                player.concubines.append(normalized)
                if source == "captive":
                    player.prisoners = [row for row in player.prisoners if row is not target]
                player.party = [row for row in player.party if str(row.get("id")) != target_id]
                if player.master and str(player.master.get("id")) == target_id:
                    player.master = None
                if player.dao_companion and str(player.dao_companion.get("id")) == target_id:
                    player.dao_companion = None
                player.dao_friends = [row for row in player.dao_friends if str(row.get("id")) != target_id]
                player.disciples = [row for row in player.disciples if str(row.get("id")) != target_id]
                result = "joined"
                summary = f"{normalized['name']}进入侍妾名册（同意率 {chance:.0%}）；侍妾数量没有上限。"
        else:
            if not existing:
                raise ValueError("侍妾名册中没有此人")
            name = str(existing.get("name", "无名修士"))
            if action == "cauldron":
                if existing.get("last_cauldron_unit") == game.diplomacy_unit:
                    raise ValueError("本行动单位已经以此人作过炉鼎")
                scale = 0.8 if player.concubine_status else 1.0
                gain = round(opportunity_required(player) * (0.018 + int(existing.get("realm_index", 0)) * 0.003) * scale, 1)
                actual = self._add_opportunity(player, gain)
                hp_gain = min(max_hp(player) - player.hp, max_hp(player) * 0.24)
                mp_gain = min(max_mp(player) - player.mp, max_mp(player) * 0.24)
                player.hp += hp_gain
                player.mp += mp_gain
                existing["last_cauldron_unit"] = game.diplomacy_unit
                existing["cauldron_uses"] = int(existing.get("cauldron_uses", 0)) + 1
                existing["affinity"] = float(existing.get("affinity", 0)) - 8
                hehuan = bool(player.technique and player.technique.element == "sex")
                if hehuan:
                    player.concubine_breakthrough_bonus = min(0.02, player.concubine_breakthrough_bonus + 0.01)
                result = "cauldron"
                summary = (
                    f"你以{name}作炉鼎，机缘 +{actual:.1f}，HP +{hp_gain:.0f}，MP +{mp_gain:.0f}。"
                    + (f" 合欢功法使下次突破基础概率累计 +{player.concubine_breakthrough_bonus:.0%}。" if hehuan else "")
                )
            elif action == "corpse":
                if player.path != "demonic":
                    raise ValueError("只有魔修能够将侍妾炼尸")
                from .demonic_system import puppet_capacity
                if len(player.puppets) >= puppet_capacity(player):
                    raise ValueError("神识可控傀儡数量已经达到上限")
                captive = copy.deepcopy(existing) | {"source": "relationship:concubine"}
                player.concubines = [row for row in player.concubines if row is not existing]
                player.prisoners.append(captive)
                result, summary = self._convert_to_puppet(game, captive, "corpse", rng, False)
            elif action == "dismiss":
                player.concubines = [row for row in player.concubines if row is not existing]
                npc = self._find_npc(game, str(existing.get("npc_id", target_id)))
                if npc and existing.get("source") == "captive":
                    npc.alive = True
                    npc.death_reason = None
                    npc.affinity = float(existing.get("affinity", 0))
                result, summary = "dismissed", f"你遣散了{name}，此后不再以侍妾名分相待。"
            else:
                raise ValueError("未知侍妾操作")

        game.history.append(HistoryRecord(
            "SYS_CONCUBINE_ACTION", 1, player.age, "侍妾名册", action, result, summary,
            {"target_id": target_id, "action": action}, ["system", "relationship", "concubine"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _advance_concubine_status(self, game: GameState, units: int = 1) -> float:
        status = game.player.concubine_status
        if not status or units <= 0:
            return 0.0
        owner = self._find_npc(game, str(status.get("owner_id", "")))
        if owner and not owner.alive:
            game.player.concubine_status = None
            return 0.0
        drain = min(
            game.player.opportunity,
            opportunity_required(game.player) * 0.02 * units,
        )
        game.player.opportunity = max(0.0, game.player.opportunity - drain)
        status["last_drain"] = round(drain, 1)
        status["turns"] = int(status.get("turns", 0)) + units
        return drain

    def _maybe_concubine_proposal(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if player.gender != "female" or player.concubine_status or player.realm_index >= self._world_realm_cap(player.world) - 1:
            return False
        candidates = [
            npc for npc in self._all_world_npcs(game)
            if npc.alive and npc.world == player.world and npc.gender == "male"
            and self._rank(npc) > self._rank(player)
        ]
        if not candidates:
            return False
        candidates.sort(key=lambda npc: (npc.realm_index, npc.layer), reverse=True)
        owner = rng.choice(candidates[: min(8, len(candidates))])
        gap = max(1, owner.realm_index - player.realm_index)
        chance = min(0.32, 0.05 + gap * 0.035)
        if rng.random() >= chance:
            return False
        event = self._instantiate_event(self.events_by_id["SYS_CONCUBINE_PROPOSAL"], game, rng)
        event["body"] = event["body"].replace("{owner_name}", owner.name).replace(
            "{owner_realm}", self._npc_realm_name(owner),
        )
        event["runtime"] = {
            "owner_id": owner.id, "owner_name": owner.name,
            "owner_realm_index": owner.realm_index, "owner_layer": owner.layer,
            "owner_realm_name": self._npc_realm_name(owner), "owner_world": owner.world,
        }
        game.pending_event = event
        return True

    def _resolve_concubine_proposal(
        self, game: GameState, pending: dict[str, Any], accept: bool,
    ) -> tuple[str, str]:
        runtime = pending.get("runtime", {})
        owner = self._find_npc(game, str(runtime.get("owner_id", "")))
        name = str(runtime.get("owner_name", "一位高阶修士"))
        if not owner or not owner.alive or owner.world != game.player.world:
            return "owner_absent", "提议者已经离开当前界面，这桩拉拢自然作罢。"
        if not accept:
            owner.affinity = float(owner.affinity or 0) - 8
            return "refused", f"你拒绝成为{name}的侍妾；对方虽有不悦，却暂未强留。"
        game.player.concubine_status = {
            **copy.deepcopy(runtime), "started_age": game.player.age, "turns": 0, "last_drain": 0.0,
        }
        return "accepted", (
            f"你接受{name}的拉拢，成为其侍妾。此后每回合会被抽取机缘，机缘获取效率降至 80%；"
            "修为仍低于对方时，基础突破概率 +2%。"
        )

    def _public_concubine_system(self, game: GameState) -> dict[str, Any]:
        rows = []
        for entry in game.player.concubines:
            row = copy.deepcopy(entry)
            row["gender_name"] = gender_name(str(row.get("gender", "female")))
            row["can_use_cauldron"] = row.get("last_cauldron_unit") != game.diplomacy_unit
            rows.append(row)
        status = copy.deepcopy(game.player.concubine_status)
        if status:
            status["breakthrough_bonus_active"] = self._rank(game.player) < (
                int(status.get("owner_realm_index", 0)), int(status.get("owner_layer", 1)),
            )
        return {
            "concubines": rows, "status": status,
            "cauldron_breakthrough_bonus": round(game.player.concubine_breakthrough_bonus, 4),
            "opportunity_efficiency_multiplier": 0.8 if status else 1.0,
        }
