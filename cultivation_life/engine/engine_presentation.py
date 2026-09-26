from __future__ import annotations

import copy
from typing import Any
from ..content_registry import ACTIONS, FACTION_DEFINITIONS, KARMA_FACTORS, REALMS, WORLD_SYSTEMS
from ..models import GameState, HistoryRecord, SectNpc
from ..rules import (
    combat_power_assessment_value,
    opportunity_required,
    public_player,
    technique_environment_multiplier,
    QI_NAMES,
    recommended_combat_power,
)
from ..system.transformation_system import public_transformation_system
from ..system.monster_bloodline_system import public_monster_bloodline
from ..system.concubine_system import gender_name
from .dependencies import PresentationDependencies


def present(deps: PresentationDependencies, game: GameState) -> dict[str, Any]:
    history = [entry for entry in game.history if deps._history_visible_in_world(entry, game)]
    deps._ensure_natal_artifact(game)
    player_data = public_player(game.player)
    natal_inventory_item = deps._natal_artifact_inventory_item(game)
    if natal_inventory_item:
        player_data["inventory"].insert(0, natal_inventory_item)
    location_id = deps.maps.normalize_location(game.player.world, game.player.location_id)
    player_data["location_id"] = location_id
    player_data["location_name"] = deps.maps.location(game.player.world, location_id)["name"]
    player_data["qi_gain_efficiencies"] = deps.maps.qi_gain_efficiencies(game.player.world, location_id)
    guixu_session = (
        game.guixu_state.get("player_session")
        if isinstance(game.guixu_state, dict) else None
    )
    if guixu_session:
        dungeon = deps._guixu_definitions().get(str(guixu_session.get("dungeon_id", "")))
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
            relation["can_invite_faction"] = deps._relationship_can_join_faction(game, relation)
            relation["can_invite_guest"] = deps._intrigue_can_invite_guest(
                game, str(relation.get("id", "")),
            )
            relation["gender"] = str(relation.get("gender") or deps._stable_gender(str(relation.get("id", ""))))
            relation["gender_name"] = gender_name(relation["gender"])
            relation["can_recruit_concubine"] = bool(
                relation["gender"] == "female" and deps._rank(relation) <= deps._rank(game.player)
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
        player_data["true_realm_name"] = deps._npc_realm_name(true_shell)
        lower_name = WORLD_SYSTEMS["world_names"].get(game.player.world, game.player.world)
        player_data["realm_name"] += f"（{lower_name}压制；真实{player_data['true_realm_name']}）"
    secret_arts = deps._public_secret_arts(game.player)
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
    party = deps._public_party(game)
    player_data["combat_power"] = deps._player_intrinsic_combat_power(game.player)
    player_data["battle_power"] = deps._player_battle_power(game)
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
    ranking_data = deps._public_spirit_ranking(game)
    new_achievements = deps.achievements.evaluate(
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
        "faction": deps._public_faction(game),
        "market": deps._public_market(game),
        "auction_system": deps._public_auction(game),
        "exchange_system": deps._public_exchange(game),
        "merchant_system": deps._public_merchant(game),
        "spirit_field": deps._public_spirit_field(game.player),
        "art_skills": deps._public_art_skills(game.player),
        "map": deps._public_map_with_ghost_parade(game, location_id),
        "world_npcs": deps._public_world_npcs(game),
        "spirit_ranking": ranking_data,
        "race_system": deps._public_race_system(game),
        "war_system": deps._public_war_system(game),
        "world_route": deps._public_world_route(game),
        "heavenly_court": deps._public_heavenly_court(game),
        "natal_artifact": deps._public_natal_artifact(game),
        "crafting_system": deps._public_crafting_system(game),
        "formation_system": deps._public_formation_system(game),
        "intrigue_system": deps._public_intrigue_system(game),
        "sage_system": deps._public_sage_system(game),
        "guixu_tide": deps._public_guixu(game),
        "tianji_artifacts": deps._public_tianji(game),
        "family": deps._public_family(game),
        "governance": deps._public_governance(game),
        "dao_companion": deps._public_dao_companion(game),
        "dao_friends": deps._public_dao_friends(game),
        "personal_relations": deps._public_personal_relations(game),
        "concubine_system": deps._public_concubine_system(game),
        "party": party,
        "wanted": deps._public_wanted(game),
        "imprisonment": copy.deepcopy(game.player.imprisonment),
        "demonic_system": deps._public_demonic_system(game.player),
        "ghost_system": deps._public_ghost_system(game),
        "breakthrough": deps._public_major_breakthrough(game.player),
        "body_cultivation": deps._public_body_cultivation(game.player),
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
            "world_base_power_cap": deps._tribulation_base_power_cap(game.player.world),
            "next_age": game.player.next_tribulation_age,
            "years_remaining": years_to_tribulation,
        },
    }


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
