from __future__ import annotations

import copy
import random
from typing import Any

from .content_registry import (
    ITEM_CATALOG, MARKET_GOODS, PATH_NAMES, RACE_DEFINITIONS, REALMS,
    TECHNIQUE_CATALOG, WORLD_SYSTEMS,
)
from .models import GameState, HistoryRecord, Player, SectNpc
from .possession_system import current_body_age
from .rules import (
    add_item, can_player_practice_technique, combat_power, learn_technique,
    max_hp, max_mp, opportunity_required, remove_item,
)
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

    def _retaliatory_relationship_ids(self, game: GameState) -> set[str]:
        """Relationships retaliate through role-specific events, never ambushes."""
        player = game.player
        values = [
            player.master, player.dao_companion, player.concubine_status,
            player.ghost_captor,
        ]
        return {
            str(row.get("id") or row.get("owner_id") or row.get("npc_id"))
            for row in values if row and (row.get("id") or row.get("owner_id") or row.get("npc_id"))
        }

    def _relationship_sanction_candidates(self, game: GameState) -> list[dict[str, Any]]:
        player = game.player
        threshold = float(WORLD_SYSTEMS["relationship"]["hostile_affinity_threshold"])
        candidates: list[dict[str, Any]] = []
        for role, relation in (("master", player.master), ("companion", player.dao_companion)):
            if not relation:
                continue
            npc = self._find_npc(game, str(relation.get("id", "")))
            alive = npc.alive if npc else bool(relation.get("alive", True))
            world = npc.world if npc else str(relation.get("world", player.world))
            if not alive or world != player.world:
                continue
            affinity = float(npc.affinity or 0) if npc else float(relation.get("affinity", 0))
            relation["affinity"] = affinity
            if affinity <= threshold:
                candidates.append({
                    "role": role, "id": str(relation.get("id", "")),
                    "name": str(relation.get("name", "故人")), "affinity": affinity,
                    "realm_index": npc.realm_index if npc else int(relation.get("realm_index", 0)),
                })
        status = player.concubine_status
        if status:
            owner = self._find_npc(game, str(status.get("owner_id", "")))
            affinity = float(owner.affinity or 0) if owner else float(status.get("owner_affinity", 0))
            if affinity <= threshold:
                candidates.append({
                    "role": "concubine_owner", "id": str(status.get("owner_id", "")),
                    "name": str(status.get("owner_name", "正主")), "affinity": affinity,
                    "realm_index": int(status.get("owner_realm_index", 0)),
                })
        captor = player.ghost_captor
        if captor:
            captor_id = str(captor.get("npc_id") or captor.get("id", ""))
            captor_npc = self._find_npc(game, captor_id)
            affinity = float(captor_npc.affinity or 0) if captor_npc else float(captor.get("affinity", 0))
            captor["affinity"] = affinity
            if affinity <= threshold:
                candidates.append({
                    "role": "ghost_captor", "id": captor_id,
                    "name": captor_npc.name if captor_npc else str(captor.get("name", "拘魂者")),
                    "affinity": affinity,
                    "realm_index": captor_npc.realm_index if captor_npc else int(captor.get("realm_index", 0)),
                })
        return [
            row for row in candidates
            if game.diplomacy_unit >= int(game.governance_actions.get(
                f"relationship_sanction:{row['role']}:{row['id']}", -1,
            ))
            and self._revenge_ready(game, "relationship_sanction", str(row["id"]))
        ]

    def _maybe_relationship_sanction(self, game: GameState, rng: random.Random) -> bool:
        if game.pending_event:
            return False
        candidates = self._relationship_sanction_candidates(game)
        if not candidates:
            return False
        threshold = float(WORLD_SYSTEMS["relationship"]["hostile_affinity_threshold"])
        severity = max(0.0, max(threshold - float(row["affinity"]) for row in candidates))
        chance = min(0.68, 0.18 + severity * 0.006)
        if rng.random() >= chance:
            return False
        selected = rng.choices(
            candidates, weights=[max(1.0, abs(float(row["affinity"]))) for row in candidates], k=1,
        )[0]
        event_id = {
            "master": "EVT_MASTER_SANCTION_001",
            "companion": "EVT_COMPANION_SANCTION_001",
            "concubine_owner": "EVT_OWNER_SANCTION_001",
            "ghost_captor": "EVT_OWNER_SANCTION_001",
        }[str(selected["role"])]
        event = self._instantiate_event(self.events_by_id[event_id], game, rng)
        event["body"] = event["body"].replace("{npc_name}", str(selected["name"]))
        demand = max(5, (int(selected["realm_index"]) + 1) ** 2 * 4)
        event["runtime"] = {**copy.deepcopy(selected), "demand": demand}
        if selected["role"] in {"concubine_owner", "ghost_captor"}:
            event["body"] += f" 对方开出的价码是下品灵石 ×{demand}；不足部分会以机缘抵偿。"
        interval = self._record_revenge_trigger(
            game, "relationship_sanction", str(selected["id"]),
        )
        event["runtime"]["revenge_cooldown_units"] = interval
        game.pending_event = event
        return True

    def _end_sanctioned_relationship(
        self, game: GameState, role: str, name: str,
    ) -> tuple[str, str]:
        player = game.player
        if role == "master":
            relation = player.master
            if relation:
                player.party = [row for row in player.party if str(row.get("id")) != str(relation.get("id"))]
                self._set_person_affinity(
                    game, str(relation.get("id", "")),
                    float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)),
                )
            player.master = None
            return "expelled", f"{name}将你逐出门墙；师徒关系就此解除，双方好感重置为中立。"
        relation = player.dao_companion
        if relation:
            player.party = [row for row in player.party if str(row.get("id")) != str(relation.get("id"))]
            self._set_person_affinity(
                game, str(relation.get("id", "")),
                float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)),
            )
        player.dao_companion = None
        player.heart_demon += float(WORLD_SYSTEMS["relationship"]["companion_separation_heart_demon"])
        return "separated", f"{name}收回道侣信物、解散誓约；双方好感重置为中立，心魔随之增长。"

    def _resolve_relationship_sanction(
        self, game: GameState, pending: dict[str, Any], role: str, mode: str,
        rng: random.Random,
    ) -> tuple[str, str]:
        runtime = pending.get("runtime", {})
        actual_role = str(runtime.get("role", role))
        name = str(runtime.get("name", "对方"))
        target_id = str(runtime.get("id", ""))
        threshold = float(WORLD_SYSTEMS["relationship"]["hostile_affinity_threshold"])
        if actual_role in {"master", "companion"}:
            relation = game.player.master if actual_role == "master" else game.player.dao_companion
            if not relation or str(relation.get("id", "")) != target_id:
                return "relationship_absent", "这段关系已经先一步结束，问罪之事自然作罢。"
            if mode == "accept":
                return self._end_sanctioned_relationship(game, actual_role, name)
            if mode != "appease":
                raise ValueError("未知的关系问罪应对")
            affinity = float(relation.get("affinity", 0))
            chance = max(0.08, min(0.72, 0.34 + affinity / 250 + game.player.realm_index * 0.025))
            if rng.random() < chance:
                relation["affinity"] = threshold + 6
                npc = self._find_npc(game, target_id)
                if npc:
                    npc.affinity = relation["affinity"]
                return "appeased", f"你暂时平息{name}的怒意（成功率 {chance:.0%}）；关系得以保留。"
            return self._end_sanctioned_relationship(game, actual_role, name)

        if actual_role not in {"concubine_owner", "ghost_captor"}:
            raise ValueError("未知的主仆问罪来源")
        status = game.player.concubine_status if actual_role == "concubine_owner" else game.player.ghost_captor
        if not status:
            return "relationship_absent", "主仆约束已经解除，这次索偿自然作罢。"
        npc = self._find_npc(game, target_id)
        affinity = float(npc.affinity or 0) if npc else float(status.get("affinity", 0))
        if mode == "comply":
            demand = max(1, int(runtime.get("demand", 5)))
            stones = next((item.quantity for item in game.player.inventory if item.id == "spirit_stone"), 0)
            paid = min(demand, stones)
            if paid:
                remove_item(game.player, "spirit_stone", paid)
            shortfall = demand - paid
            opportunity_paid = 0.0
            if shortfall:
                opportunity_paid = min(
                    game.player.opportunity,
                    opportunity_required(game.player) * min(0.08, 0.02 + shortfall / max(1, demand) * 0.04),
                )
                game.player.opportunity -= opportunity_paid
            new_affinity = min(100.0, affinity + (18 if not shortfall else 10))
            if npc:
                npc.affinity = new_affinity
            status["affinity"] = new_affinity
            return "complied", (
                f"你向{name}交出下品灵石 ×{paid}"
                + (f"，并以机缘 {opportunity_paid:.1f} 抵偿不足" if shortfall else "")
                + "；对方暂且收回威胁。"
            )
        if mode == "appease":
            chance = max(0.08, min(0.70, 0.30 + affinity / 260 + game.player.realm_index * 0.02))
            if rng.random() < chance:
                new_affinity = threshold + 5
                if npc:
                    npc.affinity = new_affinity
                status["affinity"] = new_affinity
                return "appeased", f"你的解释暂时说动{name}（成功率 {chance:.0%}），这次索偿被撤回。"
            mode = "defy"
        if mode == "defy":
            relief = float(WORLD_SYSTEMS["relationship"].get("sanction_affinity_relief", 8))
            new_affinity = min(100.0, affinity + relief)
            if npc:
                npc.affinity = new_affinity
            status["affinity"] = new_affinity
            status["angered_until_unit"] = game.diplomacy_unit + 2
            game.player.hp = max(1.0, game.player.hp - max_hp(game.player) * 0.10)
            return "defied", f"{name}以主仆约束惩戒于你；HP 损失 10%，震怒持续两个行动单位。怒气宣泄后，双方好感缓和 {relief:g} 点。"
        raise ValueError("未知的主仆问罪应对")

    def _relationship_protectors(
        self, game: GameState, enemy: SectNpc,
    ) -> list[dict[str, Any]]:
        player = game.player
        threshold = float(WORLD_SYSTEMS["relationship"]["hostile_affinity_threshold"])
        protectors: list[dict[str, Any]] = []

        def add_relation(role: str, relation: dict[str, Any] | None, *, unconditional: bool = False) -> None:
            if not relation:
                return
            identity = str(relation.get("id") or relation.get("owner_id") or "")
            if not identity or identity == enemy.id:
                return
            npc = self._find_npc(game, identity)
            alive = npc.alive if npc else bool(relation.get("alive", True))
            world = npc.world if npc else str(
                relation.get("world", relation.get("owner_world", player.world))
            )
            if not alive or world != player.world:
                return
            affinity = (
                float(npc.affinity or 0) if npc
                else float(relation.get("affinity", relation.get("owner_affinity", 20)))
            )
            if not unconditional and affinity <= threshold:
                return
            rank = (
                self._rank(npc) if npc else (
                    int(relation.get("realm_index", relation.get("owner_realm_index", 0))),
                    int(relation.get("layer", relation.get("owner_layer", 1))),
                )
            )
            if rank > self._rank(enemy):
                protectors.append({
                    "id": identity,
                    "name": npc.name if npc else str(relation.get("name") or relation.get("owner_name") or role),
                    "role": role, "rank": rank,
                })

        add_relation("正主", player.concubine_status, unconditional=True)
        add_relation("道侣", player.dao_companion)
        add_relation("师父", player.master)
        sect = game.sects.get(player.faction_id or "")
        if sect and not sect.extinct:
            members = [
                npc for npc in self._sect_members(game, sect)
                if npc.alive and npc.world == player.world and npc.id != enemy.id
                and self._rank(npc) > self._rank(enemy)
            ]
            if members:
                strongest = max(members, key=self._rank)
                protectors.append({"id": strongest.id, "name": strongest.name, "role": "师门", "rank": self._rank(strongest)})
        unique: dict[str, dict[str, Any]] = {}
        for row in protectors:
            unique.setdefault(str(row["id"]), row)
        return list(unique.values())

    def _filter_personal_revenge_by_protection(
        self, game: GameState, enemies: list[SectNpc], rng: random.Random,
    ) -> list[SectNpc]:
        remaining: list[SectNpc] = []
        threshold = float(WORLD_SYSTEMS["relationship"]["hostile_affinity_threshold"])
        for enemy in enemies:
            protectors = self._relationship_protectors(game, enemy)
            if not protectors:
                remaining.append(enemy)
                continue
            protector = max(protectors, key=lambda row: row["rank"])
            realm_gap = max(1, int(protector["rank"][0]) - enemy.realm_index)
            chance = min(0.82, 0.30 + realm_gap * 0.09)
            if rng.random() < chance:
                enemy.affinity = max(threshold + 8, -10.0)
                summary = (
                    f"{enemy.name}本欲寻仇，却因{protector['role']}{protector['name']}修为更高而退让；"
                    "对方出面斡旋，暂时化解了这桩私怨。"
                )
                game.history.append(HistoryRecord(
                    "SYS_RELATION_PROTECTS_FROM_REVENGE", 1, game.player.age, "强援解怨",
                    enemy.id, "resolved", summary,
                    {"enemy_id": enemy.id, "protector_id": protector["id"], "chance": chance},
                    ["system", "relationship", "protection", "revenge"],
                ))
            # A weaker enemy never attacks while a stronger protector remains,
            # even when this unit's mediation roll does not clear the feud.
        return remaining

    def _maybe_transfer_player_dependency(
        self, game: GameState, loser: SectNpc, winner: SectNpc, rng: random.Random,
        *, context: str,
    ) -> str:
        if not winner.alive or winner.id == loser.id:
            return ""
        player = game.player
        relationship = ""
        if player.concubine_status and str(player.concubine_status.get("owner_id", "")) == loser.id:
            relationship = "侍妾"
        elif player.ghost_captor and str(player.ghost_captor.get("npc_id") or player.ghost_captor.get("id", "")) == loser.id:
            relationship = str(player.ghost_captor.get("controlled_form", "魂仆"))
        if not relationship:
            return ""
        ratio = self._npc_power(winner) / max(1.0, self._npc_power(loser))
        chance = max(0.12, min(0.62, 0.24 + max(0.0, ratio - 1.0) * 0.12))
        if rng.random() >= chance:
            return ""
        if player.concubine_status and str(player.concubine_status.get("owner_id", "")) == loser.id:
            self._set_concubine_status(game, {
                "owner_id": winner.id, "owner_name": winner.name,
                "owner_realm_index": winner.realm_index, "owner_layer": winner.layer,
                "owner_realm_name": self._npc_realm_name(winner), "owner_world": winner.world,
            }, forced=True)
        else:
            old_form = str(player.ghost_captor.get("controlled_form", "魂仆"))
            player.ghost_captor = {
                "id": winner.id, "npc_id": winner.id, "name": winner.name,
                "realm_index": winner.realm_index, "layer": winner.layer,
                "path": winner.path, "race": winner.race, "spirit_root": winner.spirit_root,
                "combat_power": self._npc_power(winner),
                "main_technique_id": self._default_npc_main_technique(winner),
                "location_id": player.location_id, "source": f"transfer:{context}",
                "followed_years": 0, "controlled_form": old_form,
                "capture_chance": 1.0, "affinity": 0.0,
            }
        summary = (
            f"{loser.name}败给{winner.name}后，将身为{relationship}的你作为战后筹码转交给对方；"
            f"你的正主已经变为{winner.name}。"
        )
        game.history.append(HistoryRecord(
            "SYS_DEPENDENT_TRANSFERRED", 1, player.age, "败后易主", winner.id,
            "transferred", summary,
            {"old_owner_id": loser.id, "new_owner_id": winner.id, "chance": chance, "context": context},
            ["system", "relationship", "owner", "transfer", "negative"],
        ))
        return summary

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
            npc = self._find_npc(game, str(existing.get("npc_id", target_id)))
            alive = bool(npc.alive) if npc else bool(existing.get("alive", True))
            world = str(npc.world) if npc else str(existing.get("world", ""))
            if action in {"cauldron", "corpse"} and (not alive or world != player.world):
                raise ValueError("此人已经陨落或不在当前界面，无法处置")
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
                self._set_person_affinity(
                    game, str(existing.get("npc_id", target_id)),
                    float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0)),
                )
                result, summary = "dismissed", f"你遣散了{name}，双方好感重置为中立，此后不再以侍妾名分相待。"
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
        if owner and (not owner.alive or owner.world != game.player.world):
            game.player.concubine_status = None
            return 0.0
        if not owner and str(status.get("owner_world", game.player.world)) != game.player.world:
            game.player.concubine_status = None
            return 0.0
        angered = int(status.get("angered_until_unit", -1)) >= game.diplomacy_unit
        drain = min(
            game.player.opportunity,
            opportunity_required(game.player) * (0.03 if angered else 0.02) * units,
        )
        game.player.opportunity = max(0.0, game.player.opportunity - drain)
        status["last_drain"] = round(drain, 1)
        status["turns"] = int(status.get("turns", 0)) + units
        return drain

    def _maybe_concubine_proposal(self, game: GameState, rng: random.Random) -> bool:
        player = game.player
        if (
            player.gender != "female" or player.concubine_status
            or player.concubine_rejection_aftermath
            or player.realm_index >= self._world_realm_cap(player.world) - 1
        ):
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
        reputation_multiplier = max(0.01, 0.20 ** player.concubine_escape_reputation)
        chance = min(0.32, 0.05 + gap * 0.035) * reputation_multiplier
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
            player = game.player
            player.concubine_rejection_aftermath = [
                row for row in player.concubine_rejection_aftermath
                if str(row.get("owner_id", "")) != owner.id
            ]
            player.concubine_rejection_aftermath.append({
                **copy.deepcopy(runtime),
                "declined_unit": game.diplomacy_unit,
                "expires_unit": game.diplomacy_unit + 2,
                "last_checked_unit": game.diplomacy_unit,
            })
            return "refused", (
                f"你拒绝成为{name}的侍妾；对方心意难测。若其意图报复，只会在接下来的两个行动单位内发作。"
            )
        self._set_concubine_status(game, runtime)
        return "accepted", (
            f"你接受{name}的拉拢，成为其侍妾。此后每回合会被抽取机缘，机缘获取效率降至 80%；"
            "修为仍低于对方时，基础突破概率 +2%。"
        )

    @staticmethod
    def _personality_score(personality: dict[str, Any], scores: dict[str, float], default: float = 0.0) -> float:
        primary = scores.get(str(personality.get("primary")), default)
        secondary = scores.get(str(personality.get("secondary")), default)
        return primary + secondary * 0.35

    def _owner_personality(self, game: GameState, owner: SectNpc) -> dict[str, Any]:
        return self._ensure_intrigue_personality(game, owner) if self._intrigue_enabled() else {}

    def _proposal_revenge_chance(self, game: GameState, owner: SectNpc) -> float:
        if not self._intrigue_enabled():
            return 0.30
        scores = {
            "fanatical": 0.68, "warlike": 0.64, "forceful": 0.56,
            "paranoid": 0.49, "suspicious": 0.42, "greedy": 0.36,
            "smooth": 0.25, "conservative": 0.23, "cautious": 0.16,
            "open": 0.13, "restrained": 0.10, "generous": 0.07,
        }
        chance = self._personality_score(self._owner_personality(game, owner), scores, 0.25)
        chance -= max(-0.05, min(0.05, float(owner.affinity or 0) / 1000))
        return max(0.04, min(0.78, chance))

    def _advance_concubine_aftermath(self, game: GameState, rng: random.Random) -> bool:
        """Roll a rejected suitor once per unit, and only for the next two units."""
        if game.pending_event or not game.player.concubine_rejection_aftermath:
            return False
        current_unit = game.diplomacy_unit
        kept: list[dict[str, Any]] = []
        triggered: tuple[dict[str, Any], SectNpc] | None = None
        for record in game.player.concubine_rejection_aftermath:
            declined = int(record.get("declined_unit", current_unit))
            expires = int(record.get("expires_unit", declined + 2))
            if current_unit <= int(record.get("last_checked_unit", declined)):
                kept.append(record)
                continue
            owner = self._find_npc(game, str(record.get("owner_id", "")))
            if not owner or not owner.alive or owner.world != game.player.world or current_unit > expires:
                continue
            record["last_checked_unit"] = current_unit
            if (
                triggered is None
                and self._revenge_ready(game, "rejected_suitor", owner.id)
                and rng.random() < self._proposal_revenge_chance(game, owner)
            ):
                triggered = record, owner
                continue
            if current_unit < expires:
                kept.append(record)
        game.player.concubine_rejection_aftermath = kept
        if not triggered:
            return False
        record, owner = triggered
        event = self._instantiate_event(self.events_by_id["SYS_CONCUBINE_REVENGE"], game, rng)
        event["body"] = event["body"].replace("{owner_name}", owner.name)
        event["runtime"] = copy.deepcopy(record)
        event["runtime"]["revenge_cooldown_units"] = self._record_revenge_trigger(
            game, "rejected_suitor", owner.id,
        )
        game.pending_event = event
        return True

    @staticmethod
    def _runtime_from_status(status: dict[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(status[key])
            for key in (
                "owner_id", "owner_name", "owner_realm_index", "owner_layer",
                "owner_realm_name", "owner_world",
            )
            if key in status
        }

    def _set_concubine_status(
        self, game: GameState, runtime: dict[str, Any], *, forced: bool = False,
    ) -> None:
        game.player.concubine_status = {
            **self._runtime_from_status(runtime),
            "started_age": game.player.age, "turns": 0, "last_drain": 0.0,
            "dependent": False, "forced": forced, "failed_escape_count": 0,
            "last_requests": {}, "angered_until_unit": -1,
        }

    def _resolve_concubine_revenge(
        self, game: GameState, pending: dict[str, Any], method: str, rng: random.Random,
    ) -> tuple[str, str]:
        runtime = pending.get("runtime", {})
        owner = self._find_npc(game, str(runtime.get("owner_id", "")))
        name = str(runtime.get("owner_name", "一位高阶修士"))
        if not owner or not owner.alive or owner.world != game.player.world:
            return "owner_absent", "追来之人已经离开当前界面，这场逼迫不了了之。"
        relief = float(WORLD_SYSTEMS["relationship"].get("sanction_affinity_relief", 8))
        if method == "submit":
            owner.affinity = min(100.0, float(owner.affinity or 0) + relief)
            self._set_concubine_status(game, runtime, forced=True)
            return "submitted", f"你暂时向{name}低头，被强行带回府中；对方怒意缓和 {relief:g} 点，仍可在“缘·侍妾”中谋求脱身。"
        if method != "resist":
            raise ValueError("未知的逼迫应对方式")
        player_power = max(1.0, combat_power(game.player))
        owner_power = max(1.0, self._npc_power(owner))
        chance = max(0.08, min(0.75, 0.16 + 0.42 * player_power / (player_power + owner_power)))
        if rng.random() < chance:
            owner.affinity = min(100.0, float(owner.affinity or 0) + relief)
            game.player.concubine_escape_reputation += 1
            return "escaped_revenge", (
                f"你拼死突破{name}的围堵，保住自由（成功率 {chance:.0%}）。冲突过后双方好感缓和 {relief:g} 点；"
                "此事传开，往后高阶修士强取你的概率大幅降低。"
            )
        owner.affinity = min(100.0, float(owner.affinity or 0) + relief)
        game.player.hp = max(1.0, game.player.hp - max_hp(game.player) * 0.22)
        self._set_concubine_status(game, runtime, forced=True)
        game.player.concubine_status["angered_until_unit"] = game.diplomacy_unit + 2
        return "captured", f"反抗失败，你负伤后被{name}强行带走；冲突令双方好感缓和 {relief:g} 点，但两个行动单位内机缘抽取仍会更重。"

    def _escape_chance(
        self, game: GameState, owner: SectNpc, status: dict[str, Any], method: str,
    ) -> float:
        if method == "plead":
            scores = {
                "generous": 0.30, "open": 0.25, "restrained": 0.19,
                "smooth": 0.14, "cautious": 0.08, "conservative": 0.04,
                "greedy": -0.02, "suspicious": -0.08, "paranoid": -0.12,
                "forceful": -0.14, "warlike": -0.16, "fanatical": -0.20,
            }
            chance = 0.18 + float(owner.affinity or 0) / 300
            if self._intrigue_enabled():
                chance += self._personality_score(self._owner_personality(game, owner), scores)
            if status.get("dependent"):
                chance += 0.10
            return max(0.05, min(0.82, chance))
        player_power = max(1.0, combat_power(game.player))
        owner_power = max(1.0, self._npc_power(owner))
        chance = 0.10 + 0.52 * player_power / (player_power + owner_power)
        chance += min(0.12, int(status.get("turns", 0)) * 0.015)
        if status.get("dependent"):
            chance -= 0.06
        return max(0.06, min(0.78, chance))

    def _resolve_concubine_escape(
        self, game: GameState, pending: dict[str, Any], method: str, rng: random.Random,
    ) -> tuple[str, str]:
        status = game.player.concubine_status
        if not status:
            return "already_free", "你已经不再受侍妾名分约束。"
        if method == "abandon":
            return "abandoned", "你按下念头，继续等待更合适的脱身时机。"
        owner = self._find_npc(game, str(status.get("owner_id", "")))
        if not owner or not owner.alive or owner.world != game.player.world:
            game.player.concubine_status = None
            return "owner_absent", "正主已无法再约束你，你顺势恢复自由。"
        if method not in {"covert", "plead"}:
            raise ValueError("未知的脱身方式")
        chance = self._escape_chance(game, owner, status, method)
        if rng.random() < chance:
            owner.affinity = float(WORLD_SYSTEMS["relationship"].get("relationship_release_affinity", 0))
            game.player.concubine_status = None
            game.player.concubine_escape_reputation += 1
            return "escaped", (
                f"你成功{'说服' if method == 'plead' else '逃离'}{owner.name}，重获自由（成功率 {chance:.0%}）。"
                "双方好感重置为中立；消息传开，高阶修士顾忌名声，今后强取你的概率大幅降低。"
            )
        owner.affinity = float(owner.affinity or 0) - 18
        status["failed_escape_count"] = int(status.get("failed_escape_count", 0)) + 1
        status["angered_until_unit"] = game.diplomacy_unit + 2
        return "escape_failed", (
            f"脱身失败（成功率 {chance:.0%}），{owner.name}被彻底激怒；两个行动单位内每期机缘抽取由 2% 提高至 3%。"
        )

    def _owner_request_chance(
        self, game: GameState, owner: SectNpc, status: dict[str, Any], kind: str,
    ) -> float:
        base = {"technique": 0.27, "stones": 0.55, "equipment": 0.34}[kind]
        base += float(owner.affinity or 0) / 350
        if status.get("dependent"):
            base += 0.22
        if self._intrigue_enabled():
            scores = {
                "generous": 0.16, "open": 0.10, "smooth": 0.07,
                "greedy": -0.14, "suspicious": -0.08, "paranoid": -0.09,
                "restrained": -0.03,
            }
            base += self._personality_score(self._owner_personality(game, owner), scores)
        return max(0.08, min(0.92, base))

    def _owner_technique_candidates(self, player: Player, owner: SectNpc) -> list[str]:
        return [
            technique_id for technique_id, technique in TECHNIQUE_CATALOG.items()
            if technique.grade <= max(1, owner.realm_index + 1)
            and can_player_practice_technique(player, technique.element)
            and all(known.id != technique_id for known in player.known_techniques)
        ]

    @staticmethod
    def _owner_equipment_candidates(owner: SectNpc) -> list[str]:
        market_ids = {
            str(row["content_id"]) for row in MARKET_GOODS
            if row.get("kind") == "item" and int(row.get("tier", 1)) <= max(1, owner.realm_index + 1)
        }
        return sorted(
            item_id for item_id in market_ids
            if item_id in ITEM_CATALOG and ITEM_CATALOG[item_id].combat_bonus > 0
            and not {"currency", "pill", "material", "formation_material", "crafting_material"}.intersection(
                ITEM_CATALOG[item_id].tags
            )
        )

    def manage_concubine_status(self, game_id: str, action: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        status = player.concubine_status
        if not player.alive or game.pending_event or player.imprisonment:
            raise ValueError("当前状态无法处理侍妾处境")
        if not status:
            raise ValueError("你当前并非他人的侍妾")
        owner = self._find_npc(game, str(status.get("owner_id", "")))
        if not owner or not owner.alive or owner.world != player.world:
            player.concubine_status = None
            game.updated_at = now_iso()
            self.store.save(game)
            return self.present(game)
        rng = decode_rng(game.seed, game.rng_state)
        result: str
        summary: str
        details: dict[str, Any] = {"action": action, "owner_id": owner.id}
        if action == "escape":
            event = self._instantiate_event(self.events_by_id["SYS_CONCUBINE_ESCAPE"], game, rng)
            event["body"] = event["body"].replace("{owner_name}", owner.name)
            event["runtime"] = self._runtime_from_status(status)
            game.pending_event = event
            result, summary = "escape_planned", "你开始寻找脱身机会；具体方式将在游戏内事件中选择。"
        elif action == "depend":
            if status.get("dependent"):
                raise ValueError("你已经选择依附正主")
            status["dependent"] = True
            owner.affinity = float(owner.affinity or 0) + 10
            result, summary = "dependent", f"你主动依附{owner.name}，对方好感提高；今后索取资源与请求放手更容易获准。"
        elif action in {"request_technique", "request_stones", "request_equipment"}:
            kind = action.removeprefix("request_")
            last_requests = status.setdefault("last_requests", {})
            if int(last_requests.get(kind, -1)) == game.diplomacy_unit:
                raise ValueError("本行动单位已经索要过这类资源")
            technique_candidates = self._owner_technique_candidates(player, owner) if kind == "technique" else []
            equipment_candidates = self._owner_equipment_candidates(owner) if kind == "equipment" else []
            if kind == "technique" and not technique_candidates:
                raise ValueError("正主手中已无适合你的新功法")
            if kind == "equipment" and not equipment_candidates:
                raise ValueError("正主手中没有适合赐下的装备")
            last_requests[kind] = game.diplomacy_unit
            chance = self._owner_request_chance(game, owner, status, kind)
            details["accept_chance"] = chance
            if rng.random() >= chance:
                owner.affinity = float(owner.affinity or 0) - 3
                result, summary = "request_refused", f"{owner.name}拒绝了你的索求（同意率 {chance:.0%}），并对你的贪求略感不悦。"
            elif kind == "technique":
                content_id = rng.choice(technique_candidates)
                learn_technique(player, TECHNIQUE_CATALOG[content_id])
                details["content_id"] = content_id
                result, summary = "technique_given", f"{owner.name}传下《{TECHNIQUE_CATALOG[content_id].name}》，功法已收入已悟列表。"
            elif kind == "equipment":
                content_id = rng.choice(equipment_candidates)
                add_item(player, content_id)
                details["content_id"] = content_id
                result, summary = "equipment_given", f"{owner.name}赐下{ITEM_CATALOG[content_id].name}，装备已放入包裹。"
            else:
                amount = max(3, int(4 * (max(1, owner.realm_index) ** 2) * rng.uniform(0.8, 1.25)))
                add_item(player, "spirit_stone", amount)
                details["quantity"] = amount
                result, summary = "stones_given", f"{owner.name}赐下下品灵石 ×{amount}。"
        else:
            raise ValueError("未知侍妾处境操作")
        game.history.append(HistoryRecord(
            "SYS_CONCUBINE_STATUS", 1, player.age, "侍妾处境", action, result, summary,
            details, ["system", "relationship", "concubine"],
        ))
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)

    def _public_concubine_system(self, game: GameState) -> dict[str, Any]:
        rows = []
        for entry in game.player.concubines:
            row = copy.deepcopy(entry)
            npc = self._find_npc(game, str(row.get("npc_id", row.get("id", ""))))
            if npc:
                row.update(
                    realm_index=npc.realm_index, layer=npc.layer,
                    realm_name=self._npc_realm_name(npc), age=npc.age,
                    lifespan=npc.lifespan, spirit_root=npc.spirit_root,
                    path=npc.path, path_name=PATH_NAMES.get(npc.path, npc.path),
                    race=npc.race,
                    race_name=RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                    world=npc.world, alive=npc.alive, death_reason=npc.death_reason,
                    combat_power=round(self._npc_power(npc), 1),
                )
            row["gender_name"] = gender_name(str(row.get("gender", "female")))
            row["spirit_root_name"] = self._npc_root_name(str(row.get("spirit_root", "none")))
            row["same_world"] = str(row.get("world", "")) == game.player.world
            row["can_use_cauldron"] = bool(
                row.get("alive", True) and row["same_world"]
                and row.get("last_cauldron_unit") != game.diplomacy_unit
            )
            rows.append(row)
        status = copy.deepcopy(game.player.concubine_status)
        if status:
            status["breakthrough_bonus_active"] = self._rank(game.player) < (
                int(status.get("owner_realm_index", 0)), int(status.get("owner_layer", 1)),
            )
            status["angered"] = int(status.get("angered_until_unit", -1)) >= game.diplomacy_unit
            status["request_available"] = {
                kind: int(status.get("last_requests", {}).get(kind, -1)) != game.diplomacy_unit
                for kind in ("technique", "stones", "equipment")
            }
        reputation = game.player.concubine_escape_reputation
        return {
            "concubines": rows, "status": status,
            "cauldron_breakthrough_bonus": round(game.player.concubine_breakthrough_bonus, 4),
            "opportunity_efficiency_multiplier": 0.8 if status else 1.0,
            "escape_reputation": reputation,
            "future_proposal_multiplier": round(max(0.01, 0.20 ** reputation), 4),
            "rejection_aftermath": copy.deepcopy(game.player.concubine_rejection_aftermath),
        }
