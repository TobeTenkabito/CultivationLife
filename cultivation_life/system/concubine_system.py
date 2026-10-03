from __future__ import annotations

from ..npc_custody import is_free


from .semantic_events import emit

import copy
import random
from typing import Any

from ..content_registry import (
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS, ITEM_CATALOG, MARKET_GOODS, PATH_NAMES,
    RACE_DEFINITIONS, REALMS, TECHNIQUE_CATALOG, WORLD_SYSTEMS,
)
from ..models import GameState, HistoryRecord, Player, SectNpc
from .possession_system import current_body_age
from ..rules import (
    add_item, can_player_practice_technique, combat_power, learn_technique,
    max_hp, max_mp, opportunity_required, remove_item,
)
from ..runtime import decode_rng, encode_rng, now_iso


def gender_name(value: str) -> str:
    return "女" if value == "female" else "男"


class ConcubineSystemMixin:
    """Local relationship queries and probability rules; transitions are composed explicitly."""


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
            alive = is_free(npc) if npc else is_free(relation)
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
            alive = is_free(npc) if npc else is_free(relation)
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


    def _concubine_target(
        self, game: GameState, target_id: str,
    ) -> tuple[dict[str, Any] | None, str]:
        prisoner = next(
            (row for row in game.player.prisoners if str(row.get("id")) == target_id), None,
        )
        if prisoner:
            if not prisoner.get("alive", True) or prisoner.get("world", game.player.world) != game.player.world:
                return None, ""
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
        if relation and is_free(relation) and relation.get("world", game.player.world) == game.player.world:
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
            and technique_id not in GUIXU_EXCLUSIVE_TECHNIQUE_IDS
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


    def _public_concubine_system(self, game: GameState) -> dict[str, Any]:
        rows = []
        for entry in game.player.concubines:
            row = copy.deepcopy(entry)
            npc = self._find_npc(game, str(row.get("npc_id", row.get("id", ""))))
            if npc and row.get("source") != "captive":
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
