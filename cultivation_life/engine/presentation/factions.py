from __future__ import annotations

import copy
from typing import Any
from ...content_registry import (
    FACTION_REWARDS,
    FACTION_SYSTEMS,
    ITEM_CATALOG,
    PATH_NAMES,
    RACE_DEFINITIONS,
    WORLD_SYSTEMS,
)
from ...models import GameState, SectNpc, SectState
from ...system.npc_system import attitude_label
from ...rules import public_player
from ...world_state import RELATION_LABELS, race_pair
from ...system.concubine_system import gender_name
from ...system.possession_system import current_body_age


class EngineFactionPresentationMixin:
    def _public_family(self, game: GameState) -> dict[str, Any]:
        player = game.player
        offspring = [
            {
                **copy.deepcopy(child),
                "gender_name": gender_name(str(child.get("gender") or self._stable_gender(str(child.get("id", ""))))),
                "spirit_root_name": self._npc_root_name(str(child.get("spirit_root", "none"))),
                "realm_name": (
                    self._npc_realm_name(SectNpc(
                        str(child.get("id", "child")), str(child.get("name", "后代")), "",
                        int(child.get("realm_index", 0)), int(child.get("layer", 1)),
                        int(child.get("age", 0)), child.get("lifespan"),
                    )) if child.get("cultivation_started") else "尚未踏入仙途"
                ),
            }
            for child in player.offspring
        ]
        family = game.family
        if not family:
            return {
                "exists":False, "can_found":any(child.get("cultivation_started") for child in player.offspring),
                "offspring":offspring, "world":player.world, "has_voice":False, "roster":[],
            }
        roster = []
        visible_family = family.world == player.world or game.debug_world_news
        for npc in sorted(family.npcs if visible_family else [], key=lambda row:(-row.realm_index,-row.layer,row.name)):
            roster.append({
                **npc.to_dict(), "realm_name":self._npc_realm_name(npc),
                "spirit_root_name":self._npc_root_name(npc.spirit_root),
                "combat_power":self._npc_power(npc) if npc.alive else 0,
                "member_type":"本家" if npc.id in {child.get('id') for child in player.offspring} else "外姓门人",
            })
        return {
            "exists":True, "id":family.id, "name":family.name, "description":family.description,
            "world":family.world, "same_world":family.world == player.world, "extinct":family.extinct,
            "has_voice":self._has_family_voice(game), "offspring":offspring, "roster":roster,
            "living_count":sum(npc.alive for npc in family.npcs) if visible_family else None,
        }

    def _public_governance(self, game: GameState) -> dict[str, Any]:
        candidates: dict[str, dict[str, Any]] = {}
        for npc in [*game.world_npcs.values(), *game.notable_npcs.values()]:
            if npc.alive and npc.world == game.player.world:
                candidates[npc.id] = {
                    "id":npc.id,"name":npc.name,"realm_name":self._npc_realm_name(npc),
                    "source":"固定人物" if npc.id in game.world_npcs else "留名人物",
                    "combat_power":round(self._npc_power(npc),1),
                }
        for row in game.encounter_npc_cache:
            raw = row.get("npc", {})
            if raw.get("alive", True) and raw.get("world") == game.player.world:
                npc = SectNpc.from_dict(raw)
                candidates[npc.id] = {
                    "id":npc.id,"name":npc.name,"realm_name":self._npc_realm_name(npc),
                    "source":"路人缓存池","combat_power":round(float(row.get("combat_power",self._npc_power(npc))),1),
                }
        race_voice = self._has_race_voice(game)
        sect_voice = self._has_sect_voice(game)
        family_voice = self._has_family_voice(game)
        authorities = self._available_bounty_authorities(game)
        return {
            "race_voice":race_voice,"sect_voice":sect_voice,"family_voice":family_voice,
            "can_issue_bounty":bool(authorities), "bounty_authorities":authorities,
            "bounty_candidates":sorted(candidates.values(),key=lambda row:(-row["combat_power"],row["name"])),
            "bounties":copy.deepcopy(game.player_bounties),
            "diplomacy_statuses":{
                "war":"宣战","alliance":"结盟","truce":"停战","neutral":"恢复中立","vassal":"确立依附",
            },
        }

    def _public_faction(self, game: GameState) -> dict[str, Any]:
        player = game.player
        world_name = WORLD_SYSTEMS["world_names"].get(player.world, player.world)
        available = [
            {"id": sect.id, **self._faction_meta(game, sect.id), "extinct": sect.extinct}
            for sect in game.sects.values()
            if sect.world == player.world and not sect.extinct
        ]
        if not player.faction_id:
            return {
                "member": False, "available": available, "world": player.world,
                "world_name": world_name, "system_available": bool(available),
                "departed_human_world": player.world != "human",
                "can_found": player.alive, "founding_threshold": self._governance_threshold(player.world),
            }
        if (
            player.faction_id not in game.sects or game.sects[player.faction_id].extinct
            or self._faction_meta(game, player.faction_id).get("world", "human") != player.world
        ):
            return {
                "member": False, "available": available, "world": player.world,
                "world_name": world_name, "system_available": bool(available),
                "departed_human_world": player.world != "human",
                "can_found": False, "founding_threshold": self._governance_threshold(player.world),
            }
        sect = game.sects[player.faction_id]
        definition = self._faction_meta(game, sect.id)
        unlocked = player.realm_index >= 4
        sect_members = self._sect_members(game, sect)
        roster = []
        for npc in sect_members:
            if not npc.alive or npc.world != sect.world:
                continue
            perception = self._npc_cultivation_perception(game, npc)
            public_npc = npc.to_dict()
            public_npc.pop("concealed_realm_index", None)
            public_npc.pop("concealed_layer", None)
            roster.append({
                **public_npc,
                "title": self._dynamic_sect_title(npc, sect),
                "realm_index": perception["realm_index"],
                "layer": perception["layer"],
                "realm_name": perception["realm_name"],
                "cultivation_concealment": {
                    key: value for key, value in perception.items()
                    if key not in {"realm_index", "layer", "realm_name", "display_power"}
                } if perception["concealed"] else None,
                "spirit_root_name": self._npc_root_name(npc.spirit_root),
                "race_name": RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                "is_player": False,
            })
        sect_hostility = player.hostility.get(self._hostility_key("sect", sect.id), 0)
        npc_by_id = {npc.id: npc for npc in sect_members}
        player_rank = (player.realm_index, player.layer)
        master_id = player.master["id"] if player.master else None
        disciple_ids = {entry["id"] for entry in player.disciples}
        friend_ids = {entry["id"] for entry in player.dao_friends}
        concubine_ids = {str(entry.get("id")) for entry in player.concubines}
        for entry in roster:
            npc = npc_by_id[entry["id"]]
            # Relationship permissions always use the NPC's true cultivation;
            # secret arts only affect what the player can see.
            npc_rank = (npc.realm_index, npc.layer)
            entry["is_master"] = entry["id"] == master_id
            entry["is_disciple"] = entry["id"] in disciple_ids
            entry["is_friend"] = entry["id"] in friend_ids
            entry["path_name"] = PATH_NAMES.get(entry.get("path", "dao"), entry.get("path", "dao"))
            entry["affinity"] = round(npc.affinity or 0, 1)
            entry["attitude"] = attitude_label(npc.affinity or 0, sect_hostility)
            perception = self._npc_cultivation_perception(game, npc)
            entry["combat_power"] = perception["display_power"] or self._npc_power(npc)
            entry["breakthrough_chance"] = self._npc_breakthrough_probability(npc)
            entry["treasure_name"] = ITEM_CATALOG[npc.treasure_item_id].name if npc.treasure_item_id in ITEM_CATALOG else None
            entry["in_party"] = any(member.get("id") == npc.id for member in player.party)
            entry["can_invite_party"] = bool(
                not entry["in_party"]
                and len(player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
            )
            entry["can_propose_companion"] = bool(
                not (player.dao_companion and player.dao_companion.get("alive", True))
                and not entry["is_master"] and not entry["is_disciple"]
                and entry["id"] not in concubine_ids
            )
            unrelated = not entry["is_master"] and not entry["is_disciple"]
            entry["can_befriend"] = bool(
                unrelated and not entry["is_friend"] and entry["id"] not in concubine_ids
                and not (player.dao_companion and player.dao_companion.get("id") == entry["id"])
                and float(npc.affinity or 0) >= float(WORLD_SYSTEMS["relationship"]["friend_affinity_required"])
            )
            entry["gender_name"] = gender_name(npc.gender)
            entry["can_recruit_concubine"] = bool(
                npc.gender == "female" and npc_rank <= player_rank
                and not any(str(row.get("id")) == npc.id for row in player.concubines)
            )
            entry["can_intercept"] = True
            entry["can_request_master"] = (
                unrelated and entry["id"] not in concubine_ids
                and player.master is None and npc_rank > player_rank
                and f"master:{entry['id']}" not in player.relationship_attempts
            )
            entry["can_accept_disciple"] = (
                unrelated and entry["id"] not in concubine_ids
                and len(player.disciples) + len(player.disciple_requests) < int(WORLD_SYSTEMS["relationship"]["max_disciples"])
                and npc_rank < player_rank
                and f"disciple:{entry['id']}" not in player.relationship_attempts
            )
        roster.append({
            "id": f"player:{game.id}",
            "name": player.name,
            "gender": player.gender,
            "gender_name": gender_name(player.gender),
            "title": "议事长老" if unlocked else "门下弟子",
            "realm_index": player.realm_index,
            "layer": player.layer,
            "age": current_body_age(player),
            "lifespan": player.lifespan,
            "alive": player.alive,
            "death_reason": player.death_reason,
            "realm_name": public_player(player)["realm_name"],
            "spirit_root": player.spirit_root,
            "spirit_root_name": public_player(player)["spirit_root_display"],
            "path": player.technique.path if player.technique else player.path,
            "path_name": public_player(player)["path_name"],
            "race": player.race,
            "race_name": RACE_DEFINITIONS.get(player.race, {"name": player.race})["name"],
            "is_player": True,
            "is_master": False,
            "is_disciple": False,
            "is_friend": False,
            "can_request_master": False,
            "can_accept_disciple": False,
            "affinity": None,
            "attitude": "自身",
            "combat_power": self._player_intrinsic_combat_power(player),
            "breakthrough_chance": self._breakthrough_chance(player, self._manual_breakthrough_kind(player) == "major")["final"] if self._manual_breakthrough_kind(player) else None,
            "treasure_name": None,
            "in_party": False,
            "can_invite_party": False,
            "can_propose_companion": False,
            "can_befriend": False,
            "can_invite_faction": False,
            "can_intercept": False,
        })
        roster.sort(key=lambda entry: (-entry["realm_index"], -entry["layer"], entry["name"]))
        return {
            "member": True,
            "world": player.world,
            "world_name": world_name,
            "id": sect.id,
            "name": sect.name,
            "description": definition["description"],
            "allegiance_race": sect.allegiance_race or definition.get("allegiance_race", "human"),
            "allegiance_race_name": RACE_DEFINITIONS.get(
                sect.allegiance_race or definition.get("allegiance_race", "human"),
                {"name":sect.allegiance_race or definition.get("allegiance_race", "human")},
            )["name"],
            "role": "开山祖师" if sect.founded_by_player else "议事长老" if unlocked else "宗门弟子",
            "join_age": player.faction_join_age,
            "contribution": player.faction_contribution,
            "fixed_reward_unlocked": unlocked,
            "can_dispatch": unlocked,
            "dispatch_used": player.last_disciple_dispatch_age == player.age,
            "dispatch_cost": int(FACTION_SYSTEMS["disciple_dispatch_cost"]),
            "dispatch_success": float(FACTION_SYSTEMS["disciple_dispatch_success"]),
            "reward_preference": player.faction_reward_preference,
            "reward_options": FACTION_REWARDS,
            "roster": roster,
            "fallen_count": sum(not npc.alive or npc.world != sect.world for npc in sect_members),
            "can_leave": True,
            "hostility": round(sect_hostility, 1),
            "founded_by_player": sect.founded_by_player,
            "can_arrange_succession": bool(
                sect.founded_by_player and sect.founder_player_id == game.id
                and any(npc.alive and npc.world == sect.world for npc in sect_members)
            ),
            "succession_plan": copy.deepcopy(
                self._intrigue_state(game).get("succession_plans", {}).get(sect.id)
            ),
            "pressure": sect.pressure,
            "pressure_limit": int(WORLD_SYSTEMS["player_faction"]["pressure_limit"]),
            "has_diplomatic_voice": self._has_sect_voice(game),
            "diplomacy": self._public_sect_diplomacy(game, sect),
            "diplomacy_events": [
                entry.to_dict() for entry in reversed(game.history)
                if "faction" in entry.tags and "diplomacy" in entry.tags
                and (sect.id in entry.state_diff.get("sects", []) or sect.name in entry.summary)
            ][:12],
        }

    def _public_sect_diplomacy(self, game: GameState, sect: SectState) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for other in game.sects.values():
            if other.id == sect.id or other.world != sect.world or other.extinct:
                continue
            relation = game.sect_relations.get(race_pair(sect.id, other.id), {})
            status = str(relation.get("status", "neutral"))
            living = [npc for npc in other.npcs if npc.alive and npc.world == other.world]
            living.sort(key=lambda npc: (-self._npc_power(npc), -npc.realm_index, -npc.layer))
            recent = [
                record.to_dict() for record in reversed(game.history)
                if "faction" in record.tags and "diplomacy" in record.tags
                and (
                    set(record.state_diff.get("sects", [])) >= {sect.id, other.id}
                    or (sect.name in record.summary and other.name in record.summary)
                )
            ][:4]
            rows.append({
                "target_id": other.id, "target_name": other.name,
                "status": status, "status_name": RELATION_LABELS.get(status, "中立"),
                "affinity": round(float(relation.get("affinity", 0)), 1),
                "overlord": relation.get("overlord"), "subject": relation.get("subject"),
                "since_age": relation.get("since_age"), "last_vote": copy.deepcopy(relation.get("last_vote")),
                "truce_units_remaining": max(0, max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))) - game.diplomacy_unit),
                "living_count": len(living),
                "combined_power": round(sum(self._npc_power(npc) for npc in living), 1),
                "leaders": [f"{npc.name}（{self._npc_realm_name(npc)}）" for npc in living[:3]],
                "recent_events": recent,
                "transfer_candidates": self._vassal_transfer_candidates(game, "sect", sect.id, other.id, relation),
            })
        return rows

    def _vassal_transfer_candidates(
        self, game: GameState, kind: str, own_id: str, target_id: str, relation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if relation.get("status") != "vassal" or relation.get("overlord") != own_id or relation.get("subject") != target_id:
            return []
        player_rank = self._actual_player_realm(game.player)
        if kind == "sect":
            source = game.sects.get(target_id)
            members = list(source.npcs) if source else []
        else:
            members = [
                npc for sect in game.sects.values() for npc in sect.npcs
                if npc.race == target_id
            ]
        return [
            {"id":npc.id,"name":npc.name,"realm_name":self._npc_realm_name(npc)}
            for npc in members
            if npc.alive and npc.world == game.player.world and (npc.realm_index, npc.layer) <= player_rank
        ]
