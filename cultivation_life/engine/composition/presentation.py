"""Named dependency builders for presentation."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..dependencies import (
    ViewPreparationDependencies,
    CharacterViewDependencies,
    WorldViewDependencies,
    FactionViewDependencies,
)

if TYPE_CHECKING:
    from .. import GameEngine


def bind_view_preparation(engine: GameEngine) -> ViewPreparationDependencies:
    return ViewPreparationDependencies(
        _ensure_natal_artifact=lambda game: engine._ensure_natal_artifact(game),
        _guixu_definitions=lambda: engine._guixu_definitions(),
        _history_visible_in_world=lambda record, game: engine._history_visible_in_world(record, game),
        _intrigue_can_invite_guest=lambda game, npc_id: engine._intrigue_can_invite_guest(game, npc_id),
        _natal_artifact_inventory_item=lambda game: engine._natal_artifact_inventory_item(game),
        _npc_realm_name=lambda npc: engine._npc_realm_name(npc),
        _player_battle_power=lambda game: engine._player_battle_power(game),
        _player_intrinsic_combat_power=lambda player: engine._player_intrinsic_combat_power(player),
        _public_art_skills=lambda player: engine._public_art_skills(player),
        _public_auction=lambda game: engine._public_auction(game),
        _public_body_cultivation=lambda player: engine._public_body_cultivation(player),
        _public_concubine_system=lambda game: engine._public_concubine_system(game),
        _public_crafting_system=lambda game: engine._public_crafting_system(game),
        _public_dao_companion=lambda game: engine._public_dao_companion(game),
        _public_dao_friends=lambda game: engine._public_dao_friends(game),
        _public_demonic_system=lambda player, game: engine._public_demonic_system(player, game),
        _public_exchange=lambda game: engine._public_exchange(game),
        _public_faction=lambda game: engine._public_faction(game),
        _public_family=lambda game: engine._public_family(game),
        _public_formation_system=lambda game: engine._public_formation_system(game),
        _public_ghost_system=lambda game: engine._public_ghost_system(game),
        _public_governance=lambda game: engine._public_governance(game),
        _public_guixu=lambda game: engine._public_guixu(game),
        _public_heavenly_court=lambda game: engine._public_heavenly_court(game),
        _public_yaochi=lambda game: engine._public_yaochi(game),
        _public_golden_light=lambda game: engine._public_golden_light(game),
        _public_intrigue_system=lambda game: engine._public_intrigue_system(game),
        _public_major_breakthrough=lambda player: engine._public_major_breakthrough(player),
        _public_map_with_ghost_parade=lambda game, location_id: engine._public_map_with_ghost_parade(game, location_id),
        _public_market=lambda game: engine._public_market(game),
        _public_merchant=lambda game: engine._public_merchant(game),
        _public_natal_artifact=lambda game: engine._public_natal_artifact(game),
        _public_party=lambda game: engine._public_party(game),
        _public_personal_relations=lambda game: engine._public_personal_relations(game),
        _public_race_system=lambda game: engine._public_race_system(game),
        _public_sage_system=lambda game: engine._public_sage_system(game),
        _public_secret_arts=lambda player: engine._public_secret_arts(player),
        _public_spirit_field=lambda player: engine._public_spirit_field(player),
        _public_spirit_ranking=lambda game: engine._public_spirit_ranking(game),
        _public_tianji=lambda game: engine._public_tianji(game),
        _public_doctrines=lambda game: engine._public_doctrines(game),
        _public_wanted=lambda game: engine._public_wanted(game),
        _public_war_system=lambda game: engine._public_war_system(game),
        _public_world_npcs=lambda game: engine._public_world_npcs(game),
        _public_world_route=lambda game: engine._public_world_route(game),
        _rank=lambda subject: engine._rank(subject),
        _relationship_can_join_faction=lambda game, person: engine._relationship_can_join_faction(game, person),
        _stable_gender=lambda npc_id: engine._stable_gender(npc_id),
        _tribulation_base_power_cap=lambda world: engine._tribulation_base_power_cap(world),
        _evaluate_achievements=lambda game, player_rank: engine.achievements.evaluate(game, player_rank=player_rank),
        _public_buddhist=lambda game: engine._public_buddhist(game),
        _public_heavens=lambda game: engine._public_heavens(game),
        _get_maps=lambda: engine.maps,
    )


def bind_character_view(engine: GameEngine, *, bloodline_content_available: Callable[[], bool]) -> CharacterViewDependencies:
    return CharacterViewDependencies(
        _all_world_npcs=lambda *args, **kwargs: engine._all_world_npcs(*args, **kwargs),
        _body_breakthrough_chance=lambda *args, **kwargs: engine._body_breakthrough_chance(*args, **kwargs),
        _body_progress_required=lambda *args, **kwargs: engine._body_progress_required(*args, **kwargs),
        _body_tribulation_damage_reduction=lambda *args, **kwargs: engine._body_tribulation_damage_reduction(*args, **kwargs),
        _breakthrough_chance=lambda *args, **kwargs: engine._breakthrough_chance(*args, **kwargs),
        _faction_meta=lambda *args, **kwargs: engine._faction_meta(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: engine._find_npc(*args, **kwargs),
        _hostility_entity_state=lambda *args, **kwargs: engine._hostility_entity_state(*args, **kwargs),
        _hostility_name=lambda *args, **kwargs: engine._hostility_name(*args, **kwargs),
        _intrigue_can_invite_guest=lambda *args, **kwargs: engine._intrigue_can_invite_guest(*args, **kwargs),
        _joint_companion_eligible=lambda *args, **kwargs: engine._joint_companion_eligible(*args, **kwargs),
        _major_breakthrough_requirement=lambda *args, **kwargs: engine._major_breakthrough_requirement(*args, **kwargs),
        _manual_breakthrough_kind=lambda *args, **kwargs: engine._manual_breakthrough_kind(*args, **kwargs),
        _minor_layer_target=lambda *args, **kwargs: engine._minor_layer_target(*args, **kwargs),
        _npc_cultivation_perception=lambda *args, **kwargs: engine._npc_cultivation_perception(*args, **kwargs),
        _npc_faction_id=lambda *args, **kwargs: engine._npc_faction_id(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: engine._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _party_crossing_candidate=lambda *args, **kwargs: engine._party_crossing_candidate(*args, **kwargs),
        _rank=lambda *args, **kwargs: engine._rank(*args, **kwargs),
        _relationship_can_join_faction=lambda *args, **kwargs: engine._relationship_can_join_faction(*args, **kwargs),
        _relationship_combat_power=lambda *args, **kwargs: engine._relationship_combat_power(*args, **kwargs),
        _relationship_cultivation_perception=lambda *args, **kwargs: engine._relationship_cultivation_perception(*args, **kwargs),
        _stable_gender=lambda *args, **kwargs: engine._stable_gender(*args, **kwargs),
        bloodline_content_available=bloodline_content_available,
    )


def bind_world_view(engine: GameEngine) -> WorldViewDependencies:
    return WorldViewDependencies(
        _ensure_race_relations=lambda *args, **kwargs: engine._ensure_race_relations(*args, **kwargs),
        _has_race_voice=lambda *args, **kwargs: engine._has_race_voice(*args, **kwargs),
        _hostility_key=lambda *args, **kwargs: engine._hostility_key(*args, **kwargs),
        _intrigue_can_invite_guest=lambda *args, **kwargs: engine._intrigue_can_invite_guest(*args, **kwargs),
        _npc_cultivation_perception=lambda *args, **kwargs: engine._npc_cultivation_perception(*args, **kwargs),
        _npc_formation_power_multiplier=lambda *args, **kwargs: engine._npc_formation_power_multiplier(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: engine._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _npc_root_name=lambda *args, **kwargs: engine._npc_root_name(*args, **kwargs),
        _player_allegiance_race=lambda *args, **kwargs: engine._player_allegiance_race(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: engine._player_intrinsic_combat_power(*args, **kwargs),
        _relationship_combat_power=lambda *args, **kwargs: engine._relationship_combat_power(*args, **kwargs),
        _vassal_transfer_candidates=lambda *args, **kwargs: engine._vassal_transfer_candidates(*args, **kwargs),
        _world_supports=lambda *args, **kwargs: engine._world_supports(*args, **kwargs),
    )


def bind_faction_view(engine: GameEngine) -> FactionViewDependencies:
    return FactionViewDependencies(
        _actual_player_realm=lambda *args, **kwargs: engine._actual_player_realm(*args, **kwargs),
        _available_bounty_authorities=lambda *args, **kwargs: engine._available_bounty_authorities(*args, **kwargs),
        _breakthrough_chance=lambda *args, **kwargs: engine._breakthrough_chance(*args, **kwargs),
        _dynamic_sect_title=lambda *args, **kwargs: engine._dynamic_sect_title(*args, **kwargs),
        _faction_meta=lambda *args, **kwargs: engine._faction_meta(*args, **kwargs),
        _governance_threshold=lambda *args, **kwargs: engine._governance_threshold(*args, **kwargs),
        _has_family_voice=lambda *args, **kwargs: engine._has_family_voice(*args, **kwargs),
        _has_race_voice=lambda *args, **kwargs: engine._has_race_voice(*args, **kwargs),
        _has_sect_voice=lambda *args, **kwargs: engine._has_sect_voice(*args, **kwargs),
        _hostility_key=lambda *args, **kwargs: engine._hostility_key(*args, **kwargs),
        _intrigue_state=lambda *args, **kwargs: engine._intrigue_state(*args, **kwargs),
        _manual_breakthrough_kind=lambda *args, **kwargs: engine._manual_breakthrough_kind(*args, **kwargs),
        _npc_breakthrough_probability=lambda *args, **kwargs: engine._npc_breakthrough_probability(*args, **kwargs),
        _npc_cultivation_perception=lambda *args, **kwargs: engine._npc_cultivation_perception(*args, **kwargs),
        _npc_power=lambda *args, **kwargs: engine._npc_power(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _npc_root_name=lambda *args, **kwargs: engine._npc_root_name(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: engine._player_intrinsic_combat_power(*args, **kwargs),
        _public_sect_diplomacy=lambda *args, **kwargs: engine._public_sect_diplomacy(*args, **kwargs),
        _sect_members=lambda *args, **kwargs: engine._sect_members(*args, **kwargs),
        _stable_gender=lambda *args, **kwargs: engine._stable_gender(*args, **kwargs),
        _vassal_transfer_candidates=lambda *args, **kwargs: engine._vassal_transfer_candidates(*args, **kwargs),
    )
