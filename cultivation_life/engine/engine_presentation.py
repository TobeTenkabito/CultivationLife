from __future__ import annotations

import copy
from typing import Any

from ..content_registry import (
    ACTIONS, FACTION_DEFINITIONS, FACTION_REWARDS, FACTION_SYSTEMS,
    ITEM_CATALOG, KARMA_FACTORS, PATH_NAMES, REALMS,
    RACE_DEFINITIONS, RACE_SYSTEMS, TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from ..models import GameState, HistoryRecord, Player, SectNpc, SectState
from ..npc_system import attitude_label
from ..rules import (
    combat_power_assessment_value,
    opportunity_required,
    public_player,
    technique_environment_multiplier,
    QI_NAMES,
    recommended_combat_power,
)
from ..transformation_system import (
    public_transformation_system,
)


from ..world_state import (
    RELATION_LABELS, race_pair, split_race_pair,
)
from ..monster_bloodline_system import (
    bloodline_content_available,
    public_monster_bloodline,
)
from ..concubine_system import gender_name
from ..possession_system import (
    current_body_age,
)


class EnginePresentationMixin:
    def present(self, game: GameState) -> dict[str, Any]:
        history = [entry for entry in game.history if self._history_visible_in_world(entry, game)]
        self._ensure_natal_artifact(game)
        player_data = public_player(game.player)
        natal_inventory_item = self._natal_artifact_inventory_item(game)
        if natal_inventory_item:
            player_data["inventory"].insert(0, natal_inventory_item)
        location_id = self.maps.normalize_location(game.player.world, game.player.location_id)
        player_data["location_id"] = location_id
        player_data["location_name"] = self.maps.location(game.player.world, location_id)["name"]
        player_data["qi_gain_efficiencies"] = self.maps.qi_gain_efficiencies(game.player.world, location_id)
        guixu_session = (
            game.guixu_state.get("player_session")
            if isinstance(game.guixu_state, dict) else None
        )
        if guixu_session:
            dungeon = self._guixu_definitions().get(str(guixu_session.get("dungeon_id", "")))
            layer = next(
                (
                    row for row in (dungeon or {}).get("layers", [])
                    if row.get("id") == guixu_session.get("layer_id")
                ),
                None,
            )
            if layer:
                concentrations = {
                    source: float(value)
                    for source, value in layer["qi_concentrations"].items()
                }
                player_data["qi_gain_efficiencies"] = {
                    source: float(value)
                    for source, value in layer["qi_gain_efficiencies"].items()
                }
                player_data["qi_environment"] = {
                    "concentrations": concentrations,
                    "display": [
                        {
                            "source": source,
                            "name": QI_NAMES[source],
                            "concentration": concentration,
                        }
                        for source, concentration in concentrations.items()
                    ],
                    "main_multiplier": (
                        round(technique_environment_multiplier(
                            game.player.technique, game.player.world, concentrations,
                        ), 4)
                        if game.player.technique else None
                    ),
                    "body_multiplier": (
                        round(technique_environment_multiplier(
                            game.player.body_technique, game.player.world, concentrations,
                        ), 4)
                        if game.player.body_technique else None
                    ),
                    "divine_sense_multiplier": (
                        round(technique_environment_multiplier(
                            game.player.divine_sense_technique, game.player.world, concentrations,
                        ), 4)
                        if game.player.divine_sense_technique else None
                    ),
                }
        for relation in [player_data.get("master"), *player_data.get("disciples", [])]:
            if relation:
                relation["can_invite_faction"] = self._relationship_can_join_faction(game, relation)
                relation["can_invite_guest"] = self._intrigue_can_invite_guest(
                    game, str(relation.get("id", "")),
                )
                relation["gender"] = str(relation.get("gender") or self._stable_gender(str(relation.get("id", ""))))
                relation["gender_name"] = gender_name(relation["gender"])
                relation["can_recruit_concubine"] = bool(
                    relation["gender"] == "female" and self._rank(relation) <= self._rank(game.player)
                    and not any(str(row.get("id")) == str(relation.get("id")) for row in game.player.concubines)
                )
        sealed = game.player.sealed_cultivation
        player_data["cultivation_suppressed"] = bool(sealed)
        if sealed:
            true_shell = SectNpc(
                "true-player", game.player.name, "", int(sealed["realm_index"]), int(sealed["layer"]),
                game.player.age, None,
            )
            player_data["true_realm_index"] = int(sealed["realm_index"])
            player_data["true_layer"] = int(sealed["layer"])
            player_data["true_realm_name"] = self._npc_realm_name(true_shell)
            lower_name = WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world)
            player_data["realm_name"] += f"（{lower_name}压制；真实{player_data['true_realm_name']}）"
        secret_arts = self._public_secret_arts(game.player)
        if game.player.cultivation_suppression:
            player_data["true_realm_name"] = secret_arts["true_realm_name"]
            player_data["realm_name"] += f"（秘法压制；原修为{secret_arts['true_realm_name']}）"
        player_data["external_realm_name"] = (
            secret_arts["concealment"]["realm_name"]
            if secret_arts["concealment"]["active"] else secret_arts["current_realm_name"]
        )
        fame_config = WORLD_SYSTEMS["fame"]
        coalition_threshold = float(
            WORLD_SYSTEMS["faction_conflict"]["demonic_coalition_fame_threshold"]
            if game.player.path == "demonic"
            else WORLD_SYSTEMS["faction_conflict"]["coalition_fame_threshold"]
        )
        player_data["fame_assessment"] = (
            "威压全界，本界围杀势力已经低头"
            if f"world_coalition_subdued:{game.player.world}" in game.player.story_flags else
            "凶名震世，各方势力正在酝酿包围网"
            if game.player.fame > coalition_threshold else
            "威名过盛，修仙界已经明显警觉"
            if game.player.fame >= float(fame_config["alarmed_threshold"]) else
            "声名足以使同道敬重"
            if game.player.fame >= float(fame_config["respected_threshold"]) else
            "尚未在修仙界留下显赫名声"
        )
        party = self._public_party(game)
        player_data["combat_power"] = self._player_intrinsic_combat_power(game.player)
        player_data["battle_power"] = self._player_battle_power(game)
        player_data["expected_combat_power"] = recommended_combat_power(game.player.realm_index, game.player.layer)
        player_data["combat_power_assessment"] = combat_power_assessment_value(
            player_data["combat_power"], player_data["expected_combat_power"],
        )
        if game.debug_world_news:
            player_data["heart_demon"] = round(game.player.heart_demon, 1)
        years_to_tribulation = (
            max(0, game.player.next_tribulation_age - game.player.age)
            if game.player.next_tribulation_age is not None else None
        )
        trial_data = {
            "active": bool(game.active_trial),
            "kind": game.active_trial.get("kind") if game.active_trial else None,
            "step": game.active_trial.get("step_index", 0) + 1 if game.active_trial else None,
            "total_steps": len(game.active_trial.get("event_ids", [])) if game.active_trial else None,
            "allows_recovery_items": bool(game.active_trial),
        }
        if game.active_trial and game.active_trial.get("kind") == "heavenly_demon":
            completed = int(game.active_trial.get("base_rounds_completed", 0))
            minimum = int(WORLD_SYSTEMS["demonic_cultivation"]["heavenly_demon_tribulation"]["base_rounds"])
            queued_soul = game.active_trial.get("battle_runtime", {}).get("battle_kind") == "foreign_soul"
            trial_data.update(
                step=int(game.active_trial.get("total_battles", 0)) + 1,
                total_steps=minimum + int(game.active_trial.get("soul_battles", 0)) + int(queued_soul),
                minimum_rounds=minimum,
                base_rounds_completed=completed,
                total_battles=int(game.active_trial.get("total_battles", 0)),
                soul_battles=int(game.active_trial.get("soul_battles", 0)),
            )
        ranking_data = self._public_spirit_ranking(game)
        new_achievements = self.achievements.evaluate(
            game, player_rank=ranking_data.get("player_rank"),
        )
        return {
            "id": game.id,
            "seed": game.seed,
            "created_at": game.created_at,
            "updated_at": game.updated_at,
            "player": player_data,
            "pending_event": game.pending_event,
            "last_combat_report": copy.deepcopy(game.last_combat_report),
            "settings": dict(game.settings),
            "new_achievements": new_achievements,
            "secret_arts": secret_arts,
            "transformation_system": public_transformation_system(game.player),
            "monster_bloodline": public_monster_bloodline(game.player),
            "history": [entry.to_dict() for entry in reversed(history[-80:])],
            "debug_world_news": game.debug_world_news,
            "actions": ACTIONS,
            "rules": {"karma_factors": KARMA_FACTORS},
            "faction": self._public_faction(game),
            "market": self._public_market(game),
            "auction_system": self._public_auction(game),
            "spirit_field": self._public_spirit_field(game.player),
            "art_skills": self._public_art_skills(game.player),
            "map": self._public_map_with_ghost_parade(game, location_id),
            "world_npcs": self._public_world_npcs(game),
            "spirit_ranking": ranking_data,
            "race_system": self._public_race_system(game),
            "war_system": self._public_war_system(game),
            "world_route": self._public_world_route(game),
            "heavenly_court": self._public_heavenly_court(game),
            "natal_artifact": self._public_natal_artifact(game),
            "crafting_system": self._public_crafting_system(game),
            "formation_system": self._public_formation_system(game),
            "intrigue_system": self._public_intrigue_system(game),
            "sage_system": self._public_sage_system(game),
            "guixu_tide": self._public_guixu(game),
            "family": self._public_family(game),
            "governance": self._public_governance(game),
            "dao_companion": self._public_dao_companion(game),
            "dao_friends": self._public_dao_friends(game),
            "personal_relations": self._public_personal_relations(game),
            "concubine_system": self._public_concubine_system(game),
            "party": party,
            "wanted": self._public_wanted(game),
            "imprisonment": copy.deepcopy(game.player.imprisonment),
            "demonic_system": self._public_demonic_system(game.player),
            "ghost_system": self._public_ghost_system(game),
            "breakthrough": self._public_major_breakthrough(game.player),
            "body_cultivation": self._public_body_cultivation(game.player),
            "world_travel": {
                "can_ascend_celestial": bool(
                    game.player.world == "spirit" and game.player.realm_index == 8
                    and game.player.layer == REALMS[8].layers
                    and game.player.opportunity >= opportunity_required(game.player)
                    and game.player.path in {"dao", "buddhist", "confucian"}
                    and not game.player.sealed_cultivation and not game.pending_event
                    and not game.active_trial and game.player.alive
                ),
                "can_ascend_asura": bool(
                    game.player.world == "true_demon" and game.player.realm_index == 8
                    and game.player.layer == REALMS[8].layers
                    and game.player.opportunity >= opportunity_required(game.player)
                    and game.player.path == "demonic"
                    and not game.player.sealed_cultivation and not game.pending_event
                    and not game.active_trial and game.player.alive
                ),
                "can_return_human": bool(
                    game.player.world in {"spirit", "hell"}
                    and game.player.realm_index == int(WORLD_SYSTEMS["world_travel"]["required_realm"])
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_spirit": bool(
                    game.player.world == "human" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "spirit" and game.player.alive
                ),
                "can_return_hell": bool(
                    game.player.world == "human" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "hell" and game.player.alive
                ),
                "can_return_demon": bool(
                    game.player.world == "true_demon"
                    and game.player.realm_index == int(WORLD_SYSTEMS["world_travel"]["required_realm"])
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_true_demon": bool(
                    game.player.world == "demon" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "true_demon" and game.player.alive
                ),
                "can_descend_spirit": bool(
                    game.player.world == "celestial" and game.player.realm_index >= 9
                    and game.player.immortal_power_converted
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_celestial": bool(
                    game.player.world == "spirit" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "celestial" and game.player.alive
                ),
                "can_descend_true_demon": bool(
                    game.player.world == "asura" and game.player.realm_index >= 9
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_asura": bool(
                    game.player.world == "true_demon" and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "asura" and game.player.alive
                ),
                "can_descend_phantom": bool(
                    game.player.world == "nether" and game.player.realm_index >= 9
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_descend_monster": bool(
                    game.player.world == "nether" and game.player.realm_index >= 9
                    and not game.player.sealed_cultivation and game.player.alive
                ),
                "can_return_nether": bool(
                    game.player.world in {"monster_realm", "phantom_underworld"} and game.player.sealed_cultivation
                    and game.player.sealed_cultivation.get("upper_world") == "nether" and game.player.alive
                ),
                "suppressed": bool(game.player.sealed_cultivation),
            },
            "trial": trial_data,
            "tribulation": {
                "active": bool(game.active_trial and game.active_trial.get("kind") == "periodic_thunder"),
                "count": game.player.tribulation_count,
                "power": game.player.tribulation_power,
                "world_base_power_cap": self._tribulation_base_power_cap(game.player.world),
                "next_age": game.player.next_tribulation_age,
                "years_remaining": years_to_tribulation,
            },
        }

    @staticmethod
    def _history_visible_in_world(record: HistoryRecord, game: GameState) -> bool:
        if game.debug_world_news:
            return True
        legacy_sect_news = record.event_id in {
            "SYS_SECT_NPC_FALL", "SYS_SECT_NPC_DEPART", "SYS_SECT_NPC_BREAKTHROUGH", "SYS_SECT_RECRUIT",
        }
        if "world_news" not in record.tags and not legacy_sect_news:
            return True
        world_tags = {tag for tag in record.tags if tag.startswith("world:")}
        if not world_tags and legacy_sect_news:
            inferred_worlds = {
                definition.get("world", "human") for definition in FACTION_DEFINITIONS.values()
                if definition["name"] in record.summary
            }
            return not inferred_worlds or game.player.world in inferred_worlds
        if not world_tags:
            # A legacy aggregate may contain mixed-world news and cannot be safely
            # projected. Debug mode still exposes the original record verbatim.
            return False
        return "world:global" in world_tags or f"world:{game.player.world}" in world_tags

    def _public_major_breakthrough(self, player: Player) -> dict[str, Any]:
        if player.cultivation_suppression:
            return {
                "kind": None, "ready": False, "enabled": False, "target_realm": None,
                "action_label": "突破瓶颈", "chance": None, "active_aids": [],
                "met": False, "reason": "当前修为受秘法压制，解除压制后方可继续修行与突破。",
                "missing_affinities": [],
            }
        if player.sealed_cultivation:
            upper_world = str(player.sealed_cultivation.get("upper_world", "spirit"))
            return {
                "kind": None, "ready": False, "enabled": False, "target_realm": None,
                "action_label": "突破瓶颈", "chance": None, "active_aids": [],
                "met": False, "reason": f"真实道果正受下界压制，返回{WORLD_SYSTEMS['world_names'].get(upper_world, upper_world)}后方可继续修行。",
                "missing_affinities": [],
            }
        kind = self._manual_breakthrough_kind(player)
        at_bottleneck = kind is not None
        major = kind == "major"
        deterministic_monster_evolution = bool(major and player.path == "monster" and bloodline_content_available())
        waiting = player.awaiting_major_breakthrough if major else player.awaiting_minor_breakthrough
        requirement = self._major_breakthrough_requirement(player) if major else {
            "met": True, "reason": "尚未抵达大境界瓶颈。", "missing_affinities": [],
        }
        chance = (
            None if deterministic_monster_evolution
            else self._breakthrough_chance(player, major=major) if at_bottleneck else None
        )
        active_aids = [
            {"id": item_id, "name": ITEM_CATALOG[item_id].name, "bonus": ITEM_CATALOG[item_id].breakthrough_bonus}
            for item_id in player.active_breakthrough_aids if item_id in ITEM_CATALOG
        ]
        if major:
            target_index = player.realm_index + 1
            target_name = (
                WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(str(target_index), REALMS[target_index].name)
                if target_index < len(REALMS) else None
            ) if player.path == "demonic" else (REALMS[target_index].name if target_index < len(REALMS) else None)
            action_label = "选择血脉进化" if deterministic_monster_evolution else "突破大境界"
        elif at_bottleneck:
            target_name = self._minor_layer_target(player)
            action_label = "突破小境界"
            requirement["reason"] = (
                "阶段关隘已经圆满，可以服丹整备后手动冲关。"
                if player.layer in {3, 6} else
                "层级瓶颈已经圆满；本层冲击失败会为下一次累积专属成功率。"
            )
        else:
            target_name = None
            action_label = "突破瓶颈"
        return {
            "kind": kind,
            "ready": bool(waiting and at_bottleneck and player.opportunity >= opportunity_required(player)),
            "enabled": bool(
                player.alive and waiting and at_bottleneck
                and player.opportunity >= opportunity_required(player) and requirement["met"]
            ),
            "target_realm": target_name,
            "action_label": action_label,
            "chance": chance,
            "active_aids": active_aids,
            **requirement,
        }

    def _public_body_cultivation(self, player: Player) -> dict[str, Any]:
        maximum = int(WORLD_SYSTEMS["body_cultivation"]["max_layer"])
        required = self._body_progress_required(player)
        ready = bool(
            player.body_technique and player.body_training < maximum
            and player.awaiting_body_breakthrough and player.body_progress >= required
        )
        return {
            "layer":player.body_training, "max_layer":maximum,
            "progress":round(player.body_progress, 1), "required":round(required, 1),
            "technique":copy.deepcopy(player.body_technique.__dict__) if player.body_technique else None,
            "ready":ready, "chance":self._body_breakthrough_chance(player) if ready else None,
            "target_layer":player.body_training + 1 if player.body_training < maximum else None,
            "tribulation_damage_reduction":self._body_tribulation_damage_reduction(player),
            "cultivation_breakthrough_bonus":player.body_training // 20 * float(WORLD_SYSTEMS["body_cultivation"]["cultivation_breakthrough_bonus_per_20_layers"]),
            "training_speed_multiplier":(
                float(WORLD_SYSTEMS.get("monster_cultivation", {}).get("body_training_multiplier", 1.5))
                if player.path == "monster" else 1.0
            ),
        }

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

    def _public_dao_companion(self, game: GameState) -> dict[str, Any] | None:
        companion = game.player.dao_companion
        if not companion:
            return None
        result = copy.deepcopy(companion)
        result["gender"] = str(result.get("gender") or self._stable_gender(str(result.get("id", ""))))
        result["gender_name"] = gender_name(result["gender"])
        result["can_recruit_concubine"] = bool(
            result["gender"] == "female" and self._rank(result) <= self._rank(game.player)
            and not any(str(row.get("id")) == str(result.get("id")) for row in game.player.concubines)
        )
        technique_id = result.get("main_technique_id")
        result["main_technique_name"] = (
            TECHNIQUE_CATALOG[technique_id].name if technique_id in TECHNIQUE_CATALOG else "尚无主修功法"
        )
        result["same_cultivation"] = bool(self._joint_companion_eligible(game.player))
        result["breakthrough_bonus"] = (
            float(WORLD_SYSTEMS["relationship"]["companion_breakthrough_bonus"])
            if result["same_cultivation"] else 0.0
        )
        result["combat_power"] = self._relationship_combat_power(companion)
        result["in_party"] = any(entry.get("id") == companion.get("id") for entry in game.player.party)
        result["can_invite_party"] = bool(
            companion.get("alive", True) and companion.get("world") == game.player.world
            and not result["in_party"]
            and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
        )
        result["can_invite_faction"] = self._relationship_can_join_faction(game, companion)
        result["can_invite_guest"] = self._intrigue_can_invite_guest(
            game, str(companion.get("id", "")),
        )
        return result

    def _public_dao_friends(self, game: GameState) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for friend in game.player.dao_friends:
            row = copy.deepcopy(friend)
            row["gender"] = str(row.get("gender") or self._stable_gender(str(row.get("id", ""))))
            row["gender_name"] = gender_name(row["gender"])
            row["can_recruit_concubine"] = bool(
                row["gender"] == "female" and self._rank(row) <= self._rank(game.player)
                and not any(str(entry.get("id")) == str(row.get("id")) for entry in game.player.concubines)
            )
            technique_id = str(row.get("main_technique_id", ""))
            row["main_technique_name"] = (
                TECHNIQUE_CATALOG[technique_id].name if technique_id in TECHNIQUE_CATALOG else "主修未明"
            )
            row["combat_power"] = self._relationship_combat_power(friend)
            row["in_party"] = any(entry.get("id") == row.get("id") for entry in game.player.party)
            row["can_invite_party"] = bool(
                row.get("alive", True) and row.get("world") == game.player.world and not row["in_party"]
                and len(game.player.party) < int(WORLD_SYSTEMS["party"]["max_companions"])
            )
            row["can_invite_faction"] = self._relationship_can_join_faction(game, friend)
            row["can_invite_guest"] = self._intrigue_can_invite_guest(
                game, str(friend.get("id", "")),
            )
            result.append(row)
        return result

    def _relationship_can_join_faction(self, game: GameState, relation: dict[str, Any]) -> bool:
        sect = game.sects.get(game.player.faction_id or "")
        return bool(
            sect and not sect.extinct and sect.world == game.player.world
            and relation.get("alive", True) and relation.get("world") == game.player.world
            and not self._npc_faction_id(game, str(relation.get("id", "")))
        )

    def _public_personal_relations(self, game: GameState) -> dict[str, list[dict[str, Any]]]:
        rules = WORLD_SYSTEMS["relationship"]
        high_threshold = float(rules["positive_affinity_threshold"])
        low_threshold = float(rules["hostile_affinity_threshold"])
        people = {npc.id:npc for npc in self._all_world_npcs(game) if npc.alive and npc.world == game.player.world}
        relationship_labels: dict[str, str] = {}
        for label, entries in (
            ("师父", [game.player.master] if game.player.master else []),
            ("道侣", [game.player.dao_companion] if game.player.dao_companion else []),
            ("道友", game.player.dao_friends), ("弟子", game.player.disciples),
        ):
            for relation in entries:
                if relation and relation.get("alive", True) and relation.get("world") == game.player.world:
                    relationship_labels[str(relation.get("id"))] = label
                    if str(relation.get("id")) not in people:
                        people[str(relation.get("id"))] = SectNpc(
                            str(relation.get("id")),str(relation.get("name","无名修士")),"旧识",
                            int(relation.get("realm_index",0)),int(relation.get("layer",1)),
                            int(relation.get("age",18)),relation.get("lifespan"),
                            spirit_root=str(relation.get("spirit_root","none")),path=str(relation.get("path","dao")),
                            race=str(relation.get("race","human")),world=str(relation.get("world",game.player.world)),
                            affinity=float(relation.get("affinity",0)),
                        )
        rows = [{
            "id":npc.id,"name":npc.name,"affinity":round(float(npc.affinity or 0),1),
            "attitude":attitude_label(npc.affinity or 0,0),"realm_name":self._npc_realm_name(npc),
            "gender":npc.gender,"gender_name":gender_name(npc.gender),
            "can_recruit_concubine":bool(
                npc.gender == "female" and self._rank(npc) <= self._rank(game.player)
                and not any(str(entry.get("id")) == npc.id for entry in game.player.concubines)
            ),
            "can_invite_guest":self._intrigue_can_invite_guest(game, npc.id),
            "relationship":relationship_labels.get(npc.id,"相识"),
            "faction_name":self._faction_meta(game, self._npc_faction_id(game,npc.id))["name"] if self._npc_faction_id(game,npc.id) else None,
        } for npc in people.values() if float(npc.affinity or 0) >= high_threshold or float(npc.affinity or 0) <= low_threshold]
        return {
            "high":sorted((row for row in rows if row["affinity"] >= high_threshold),key=lambda row:-row["affinity"]),
            "low":sorted((row for row in rows if row["affinity"] <= low_threshold),key=lambda row:row["affinity"]),
        }

    def _relationship_combat_power(self, relation: dict[str, Any]) -> float:
        shell = SectNpc(
            str(relation.get("id", "relation")), str(relation.get("name", "无名")), "",
            int(relation.get("realm_index", 0)), int(relation.get("layer", 1)),
            int(relation.get("age", 1)), relation.get("lifespan"),
            spirit_root=str(relation.get("spirit_root", "none")),
            path=str(relation.get("path", "dao")), race=str(relation.get("race", "human")),
            world=str(relation.get("world", "human")), affinity=float(relation.get("affinity", 0)),
        )
        base = self._npc_power(shell)
        technique = TECHNIQUE_CATALOG.get(str(relation.get("main_technique_id", "")))
        technique_bonus = technique.combat_bonus if technique else 0.0
        item_bonus = sum(
            ITEM_CATALOG[item_id].combat_bonus * int(quantity)
            for item_id, quantity in relation.get("items", {}).items() if item_id in ITEM_CATALOG
        )
        return round(base + technique_bonus + item_bonus, 1)

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

    def _public_party(self, game: GameState) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for reference in game.player.party:
            companion = game.player.dao_companion
            if companion and companion.get("id") == reference.get("id"):
                if companion.get("alive", True) and companion.get("world") == game.player.world:
                    perception = self._relationship_cultivation_perception(game, companion, "道侣")
                    result.append({
                        "id": companion["id"], "name": companion["name"],
                        "realm_index": perception["realm_index"], "layer": perception["layer"],
                        "realm_name": perception["realm_name"],
                        "combat_power": perception["display_power"] or self._relationship_combat_power(companion),
                        "cultivation_concealment": {
                            key: value for key, value in perception.items()
                            if key not in {"realm_index", "layer", "realm_name", "display_power"}
                        } if perception["concealed"] else None,
                        "affinity": round(float(companion.get("affinity", 0)), 1), "attitude": "道侣",
                        "can_interact":game.governance_actions.get(f"party_interaction:{companion['id']}") != game.player.age,
                        "can_cross_spirit":bool(self._party_crossing_candidate(game, str(companion["id"]))),
                        "selected_for_crossing":bool(
                            game.player.joint_spirit_crossing
                            and str(game.player.joint_spirit_crossing.get("id")) == str(companion["id"])
                            and not game.player.joint_spirit_crossing.get("declined")
                        ),
                    })
                continue
            npc = self._find_npc(game, str(reference.get("id", "")))
            relation = next((entry for entry in [game.player.master, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == str(reference.get("id"))), None)
            if npc and npc.alive and npc.world == game.player.world:
                perception = self._npc_cultivation_perception(game, npc)
                row = {
                    "id": npc.id, "name": npc.name,
                    "realm_index": perception["realm_index"], "layer": perception["layer"],
                    "realm_name": perception["realm_name"],
                    "combat_power": perception["display_power"] or self._npc_power(npc),
                    "cultivation_concealment": {
                        key: value for key, value in perception.items()
                        if key not in {"realm_index", "layer", "realm_name", "display_power"}
                    } if perception["concealed"] else None,
                    "affinity": round(npc.affinity or 0, 1), "attitude": attitude_label(npc.affinity or 0, 0),
                }
            elif relation and relation.get("alive", True) and relation.get("world") == game.player.world:
                perception = self._relationship_cultivation_perception(game, relation)
                row = {
                    "id":str(relation["id"]), "name":str(relation["name"]),
                    "realm_index": perception["realm_index"], "layer": perception["layer"],
                    "realm_name": perception["realm_name"],
                    "combat_power": perception["display_power"] or self._relationship_combat_power(relation),
                    "cultivation_concealment": {
                        key: value for key, value in perception.items()
                        if key not in {"realm_index", "layer", "realm_name", "display_power"}
                    } if perception["concealed"] else None,
                    "affinity":round(float(relation.get("affinity",0)),1),
                    "attitude":attitude_label(float(relation.get("affinity",0)),0),
                }
            else:
                continue
            row["can_interact"] = game.governance_actions.get(f"party_interaction:{row['id']}") != game.player.age
            row["can_cross_spirit"] = bool(self._party_crossing_candidate(game, row["id"]))
            row["selected_for_crossing"] = any(str(entry.get("id")) == row["id"] for entry in game.player.joint_friend_crossing)
            result.append(row)
        return result

    def _sync_party_state(self, game: GameState) -> bool:
        """Discard references that can no longer represent an active companion."""
        valid: list[dict[str, Any]] = []
        seen: set[str] = set()
        for reference in game.player.party:
            npc_id = str(reference.get("id", ""))
            companion = game.player.dao_companion
            if companion and companion.get("id") == npc_id:
                if npc_id and npc_id not in seen and companion.get("alive", True) and companion.get("world") == game.player.world:
                    seen.add(npc_id)
                    valid.append({"id": npc_id})
                continue
            npc = self._find_npc(game, npc_id)
            relation = next((entry for entry in [game.player.master, *game.player.dao_friends, *game.player.disciples] if entry and str(entry.get("id")) == npc_id), None)
            available = bool(
                (npc and npc.alive and npc.world == game.player.world)
                or (relation and relation.get("alive", True) and relation.get("world") == game.player.world)
            )
            if not npc_id or npc_id in seen or not available:
                continue
            seen.add(npc_id)
            valid.append({"id": npc_id})
        if valid == game.player.party:
            return False
        game.player.party = valid
        return True

    def _public_wanted(self, game: GameState) -> list[dict[str, Any]]:
        player = game.player
        threshold = float(WORLD_SYSTEMS["faction_conflict"]["wanted_threshold"])
        labels = {"sect": "宗门", "family": "家族", "race": "种族", "world": "修仙界包围网"}
        result = []
        for key, value in sorted(player.hostility.items()):
            if value <= threshold:
                continue
            kind, entity_id = key.split(":", 1)
            if self._hostility_entity_state(game, key).get("status") != "active":
                continue
            display_name = (
                self._hostility_name(key, game)
                if kind in {"sect", "family"} else
                RACE_DEFINITIONS.get(entity_id, {"name": entity_id})["name"]
                if kind == "race" else WORLD_SYSTEMS["world_names"].get(entity_id, entity_id) + "包围网"
            )
            result.append({
                "key": key, "kind": kind, "id": entity_id,
                "name": labels.get(kind, "势力"), "display_name": display_name,
                "hostility": round(value, 1),
            })
        return result

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

