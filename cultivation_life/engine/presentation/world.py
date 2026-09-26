from __future__ import annotations

import copy
from typing import Any
from ...content_registry import PATH_NAMES, RACE_DEFINITIONS, RACE_SYSTEMS, WORLD_SYSTEMS
from ...models import GameState, SectNpc
from ...system.npc_system import attitude_label
from ...world_state import RELATION_LABELS, race_pair, split_race_pair
from ...system.concubine_system import gender_name
from ...system.possession_system import current_body_age


class EngineWorldPresentationMixin:
    def _public_world_npcs(self, game: GameState) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        world_people = {**game.world_npcs, **game.notable_npcs}
        for cached in game.encounter_npc_cache:
            saved = cached.get("npc")
            if isinstance(saved, dict):
                npc = SectNpc.from_dict(saved)
                world_people.setdefault(npc.id, npc)
        for npc in sorted(world_people.values(), key=lambda value: (-value.realm_index, -value.layer, value.name)):
            same_world = npc.world == game.player.world
            if not same_world and npc.departed_age is None:
                continue
            perceived_alive = npc.alive and same_world
            if perceived_alive:
                status = "存活"
            elif not npc.alive:
                status = npc.death_reason or "已经陨落"
            elif npc.departure_reason:
                status = "魂灯熄灭，当前界面将其记录为死亡"
            else:
                status = "不在当前界面，生死不明"
            public_npc = npc.to_dict()
            perception = self._npc_cultivation_perception(game, npc) if same_world and npc.alive else None
            if not same_world:
                public_npc["departure_reason"] = None
            public_npc.pop("concealed_realm_index", None)
            public_npc.pop("concealed_layer", None)
            if perception:
                public_npc["realm_index"] = perception["realm_index"]
                public_npc["layer"] = perception["layer"]
            result.append({
                **public_npc,
                "realm_name": perception["realm_name"] if perception else self._npc_realm_name(npc),
                "cultivation_concealment": (
                    {
                        key: value for key, value in perception.items()
                        if key not in {"realm_index", "layer", "realm_name", "display_power"}
                    } if perception and perception["concealed"] else None
                ),
                "gender_name": gender_name(npc.gender),
                "spirit_root_name": self._npc_root_name(npc.spirit_root),
                "path_name": PATH_NAMES.get(npc.path, npc.path),
                "race_name": RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                "world": npc.world if same_world else None,
                "world_name": WORLD_SYSTEMS["world_names"].get(npc.world, npc.world) if same_world else "去向不明",
                "perceived_alive": perceived_alive, "status": status,
                "combat_power": (
                    float(perception["display_power"])
                    * self._npc_formation_power_multiplier(game, npc.id)
                    if same_world and npc.alive and perception and perception["display_power"] is not None
                    else None
                ),
                "formation": (
                    {
                        "name": game.npc_formations[npc.id]["name"],
                        "durability": round(float(game.npc_formations[npc.id].get("durability", 0.0)), 1),
                        "bonus": round((self._npc_formation_power_multiplier(game, npc.id) - 1.0) * 100.0, 2),
                    }
                    if same_world and npc.alive and npc.id in game.npc_formations else None
                ),
                "attitude": attitude_label(
                    npc.affinity or 0,
                    game.player.hostility.get(self._hostility_key("race", npc.race), 0),
                ) if same_world else "生死不明",
                "in_party": any(entry.get("id") == npc.id for entry in game.player.party),
                "can_invite_party": bool(
                    same_world and npc.alive
                    and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
                    and not any(entry.get("id") == npc.id for entry in game.player.party)
                ),
                "can_propose_companion": bool(
                    same_world and npc.alive
                    and not (game.player.dao_companion and game.player.dao_companion.get("alive", True))
                    and not (game.player.master and game.player.master.get("id") == npc.id)
                    and not any(entry.get("id") == npc.id for entry in game.player.disciples)
                    and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
                ),
                "can_befriend": bool(
                    same_world and npc.alive
                    and float(npc.affinity or 0) >= float(WORLD_SYSTEMS["relationship"]["friend_affinity_required"])
                    and not any(entry.get("id") == npc.id for entry in game.player.dao_friends)
                    and not (game.player.dao_companion and game.player.dao_companion.get("id") == npc.id)
                    and not (game.player.master and game.player.master.get("id") == npc.id)
                    and not any(entry.get("id") == npc.id for entry in game.player.disciples)
                    and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
                ),
                "can_recruit_concubine": bool(
                    same_world and npc.alive and npc.gender == "female"
                    and (npc.realm_index, npc.layer) <= (game.player.realm_index, game.player.layer)
                    and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
                ),
                "can_invite_guest": self._intrigue_can_invite_guest(game, npc.id),
            })
        return result

    def _public_spirit_ranking(self, game: GameState) -> dict[str, Any]:
        ranking_world = game.player.world
        if not self._world_supports(ranking_world, "ranking"):
            return {"available": False, "entries": [], "player_rank": None}
        rows: list[dict[str, Any]] = []
        npcs = [
            *game.world_npcs.values(),
            *game.notable_npcs.values(),
            *(npc for sect in game.sects.values() if sect.world == ranking_world for npc in sect.npcs),
        ]
        seen_ids: set[str] = set()
        for npc in npcs:
            if not npc.alive or npc.world != ranking_world or npc.id in seen_ids:
                continue
            seen_ids.add(npc.id)
            rows.append({
                "id": npc.id, "name": npc.name, "title": npc.title,
                "realm_index": npc.realm_index, "layer": npc.layer,
                "realm_name": self._npc_realm_name(npc), "race": npc.race,
                "race_name": RACE_DEFINITIONS.get(npc.race, {"name": npc.race})["name"],
                "combat_power": self._npc_power(npc), "is_player": False,
            })
        companion = game.player.dao_companion
        if companion and companion.get("alive", True) and companion.get("world") == ranking_world and companion.get("id") not in seen_ids:
            rows.append({
                "id": companion["id"], "name": companion["name"], "title": "玩家道侣",
                "realm_index": int(companion["realm_index"]), "layer": int(companion["layer"]),
                "realm_name": str(companion.get("realm_name", "修为未明")), "race": companion.get("race", "human"),
                "race_name": RACE_DEFINITIONS.get(companion.get("race", "human"), {"name": "种族未明"})["name"],
                "combat_power": self._relationship_combat_power(companion), "is_player": False,
            })
            seen_ids.add(str(companion["id"]))
        for friend in game.player.dao_friends:
            if not friend.get("alive", True) or friend.get("world") != ranking_world or friend.get("id") in seen_ids:
                continue
            seen_ids.add(str(friend["id"]))
            shell = SectNpc(
                str(friend["id"]), str(friend.get("name", "无名道友")), "玩家道友",
                int(friend.get("realm_index", 0)), int(friend.get("layer", 1)),
                int(friend.get("age", 1)), friend.get("lifespan"),
            )
            rows.append({
                "id": friend["id"], "name": friend.get("name", "无名道友"), "title": "玩家道友",
                "realm_index": int(friend.get("realm_index", 0)), "layer": int(friend.get("layer", 1)),
                "realm_name": self._npc_realm_name(shell), "race": friend.get("race", "human"),
                "race_name": RACE_DEFINITIONS.get(friend.get("race", "human"), {"name": "种族未明"})["name"],
                "combat_power": self._relationship_combat_power(friend), "is_player": False,
            })
        player_shell = SectNpc(
            "player", game.player.name, "", game.player.realm_index, game.player.layer,
            current_body_age(game.player), game.player.lifespan,
        )
        rows.append({
            "id": f"player:{game.id}", "name": game.player.name, "title": "玩家",
            "realm_index": game.player.realm_index, "layer": game.player.layer,
            "realm_name": self._npc_realm_name(player_shell), "race": game.player.race,
            "race_name": RACE_DEFINITIONS.get(game.player.race, {"name": game.player.race})["name"],
            "combat_power": self._player_intrinsic_combat_power(game.player), "is_player": True,
        })
        rows.sort(key=lambda entry: (-entry["combat_power"], -entry["realm_index"], -entry["layer"], entry["name"]))
        player_rank = next(index for index, entry in enumerate(rows, 1) if entry["is_player"])
        entries = [{**entry, "rank": index} for index, entry in enumerate(rows[:20], 1)]
        world_name = WORLD_SYSTEMS["world_names"].get(ranking_world, ranking_world)
        return {
            "available": True, "entries": entries, "player_rank": player_rank, "on_board": player_rank <= 20,
            "world": ranking_world, "world_name": world_name, "title": f"{world_name}天榜前二十",
        }

    def _public_race_system(self, game: GameState) -> dict[str, Any]:
        race_world = game.player.world
        available = self._world_supports(race_world, "races")
        player_race = self._player_allegiance_race(game.player)
        lineage_race = str(game.player.lineage_race or game.player.race)
        if not available:
            return {
                "available": False, "implemented": True, "player_race": player_race,
                "player_race_name": RACE_DEFINITIONS.get(player_race, {"name": player_race})["name"],
                "lineage_race": lineage_race,
                "lineage_race_name": RACE_DEFINITIONS.get(lineage_race, {"name":lineage_race})["name"],
                "races": {}, "alliances": [],
            }
        self._ensure_race_relations(game)
        diplomacy_history = [
            record for record in reversed(game.history)
            if "diplomacy" in record.tags and f"world:{race_world}" in record.tags
        ]
        races: dict[str, dict[str, Any]] = {}
        for race_id, definition in RACE_DEFINITIONS.items():
            if race_world not in definition.get("worlds", []):
                continue
            relations = []
            for other_id, other_definition in RACE_DEFINITIONS.items():
                if other_id == race_id or race_world not in other_definition.get("worlds", []):
                    continue
                relation = game.race_relations.get(race_pair(race_id, other_id), {})
                relations.append({
                    "race": other_id, "race_name": other_definition["name"],
                    "affinity": round(float(relation.get("affinity", 0)), 1),
                    "status": str(relation.get("status", "neutral")),
                    "status_name": RELATION_LABELS.get(str(relation.get("status", "neutral")), "中立"),
                    "overlord": relation.get("overlord"), "subject": relation.get("subject"),
                    "truce_units_remaining": max(0, max(int(relation.get("truce_until_unit", 0)), int(relation.get("war_truce_until_unit", 0))) - game.diplomacy_unit),
                    "transfer_candidates": self._vassal_transfer_candidates(game, "race", race_id, other_id, relation),
                })
            recent_events = [
                {"age": record.age, "title": record.title, "summary": record.summary, "result": record.result}
                for record in diplomacy_history
                if race_id in record.state_diff.get("races", [])
            ][:12]
            supported_factions: list[dict[str, Any]] = []
            seen_factions: set[str] = set()
            for sect in game.sects.values():
                allegiance = sect.allegiance_race or (sect.npcs[0].race if sect.npcs else "human")
                if sect.world != race_world or allegiance != race_id or sect.extinct:
                    continue
                elders = [
                    npc.name for npc in sorted(
                        (npc for npc in sect.npcs if npc.alive),
                        key=lambda npc: (-npc.realm_index, -npc.layer, npc.name),
                    )[:2]
                ]
                supported_factions.append({"id":sect.id, "name":sect.name, "elders":elders, "active":True})
                seen_factions.add(sect.id)
            for preset in RACE_SYSTEMS.get("faction_presets", {}).get(race_id, []):
                if preset.get("world") != race_world:
                    continue
                if preset["id"] not in seen_factions:
                    supported_factions.append({**copy.deepcopy(preset), "active":False})
            races[race_id] = {
                "id": race_id, **definition,
                "relations": sorted(relations, key=lambda row: (row["status"] == "neutral", -abs(row["affinity"]), row["race_name"])),
                "recent_events": recent_events,
                "supported_factions": supported_factions,
            }
        alliances = []
        races_in_world = set(races)
        for key, relation in game.race_relations.items():
            if relation.get("status") not in {"alliance", "vassal"}:
                continue
            first, second = split_race_pair(key)
            if first not in races_in_world or second not in races_in_world:
                continue
            alliances.append({
                "members": [first, second],
                "name": relation.get("name") or f"{RACE_DEFINITIONS[first]['name']}—{RACE_DEFINITIONS[second]['name']}盟约",
                "status": relation["status"],
                "overlord": relation.get("overlord"), "subject": relation.get("subject"),
            })
        return {
            "available": available, "implemented": True,
            "player_race": player_race,
            "player_race_name": RACE_DEFINITIONS.get(player_race, {"name": player_race})["name"],
            "lineage_race": lineage_race,
            "lineage_race_name": RACE_DEFINITIONS.get(lineage_race, {"name":lineage_race})["name"],
            "races": races, "alliances": alliances,
            "world": race_world,
            "world_name": WORLD_SYSTEMS["world_names"].get(race_world, race_world),
            "has_diplomatic_voice": self._has_race_voice(game),
            "vassal_transfers": [
                {"target_id": other_id, "target_name": RACE_DEFINITIONS[other_id]["name"], "candidates": self._vassal_transfer_candidates(game, "race", player_race, other_id, relation)}
                for key, relation in game.race_relations.items()
                for first, second in [split_race_pair(key)]
                for other_id in [second if first == player_race else first]
                if (
                    player_race in {first, second} and other_id in races_in_world
                    and self._vassal_transfer_candidates(game, "race", player_race, other_id, relation)
                )
            ],
        }

    def _public_world_route(self, game: GameState) -> dict[str, Any]:
        player = game.player
        route_id, route = next(
            (
                (route_id, definition)
                for route_id, definition in WORLD_SYSTEMS.get("cultivation_routes", {}).items()
                if player.path in definition.get("paths", [])
            ),
            ("orthodox", WORLD_SYSTEMS.get("cultivation_routes", {}).get("orthodox", {})),
        )
        stages = []
        for stage in route.get("stages", []):
            is_system = bool(stage.get("system"))
            profile = WORLD_SYSTEMS.get("world_profiles", {}).get(stage.get("world", ""), {})
            stages.append({
                **copy.deepcopy(stage),
                "current": not is_system and stage.get("world") == player.world,
                "kind": "system" if is_system else "world",
                "world_name": (
                    WORLD_SYSTEMS.get("world_names", {}).get(stage.get("world"), stage.get("label", "未知界面"))
                    if not is_system else WORLD_SYSTEMS.get("heavens_framework", {}).get("name", "诸天")
                ),
                "description": (
                    WORLD_SYSTEMS.get("heavens_framework", {}).get("description", "") if is_system else ""
                ),
                "supports": list(profile.get("supports", [])),
                "tier": profile.get("tier"),
            })
        return {
            "route_id": route_id,
            "name": route.get("name", PATH_NAMES.get(player.path, player.path)),
            "path": player.path,
            "path_name": PATH_NAMES.get(player.path, player.path),
            "current_world": player.world,
            "current_world_name": WORLD_SYSTEMS.get("world_names", {}).get(player.world, player.world),
            "lineage_race_name": RACE_DEFINITIONS.get(player.lineage_race or player.race, {"name":player.race})["name"],
            "allegiance_race_name": RACE_DEFINITIONS.get(self._player_allegiance_race(player), {"name":self._player_allegiance_race(player)})["name"],
            "stages": stages,
        }
