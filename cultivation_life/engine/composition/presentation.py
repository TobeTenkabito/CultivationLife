"""Named dependency builders for presentation."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..dependencies import (
    PresentationDependencies,
    CharacterViewDependencies,
    WorldViewDependencies,
    FactionViewDependencies,
)

if TYPE_CHECKING:
    from .. import GameEngine


def bind_presentation_runtime(engine: GameEngine) -> PresentationDependencies:
    return PresentationDependencies(
        _ensure_natal_artifact=lambda *args, **kwargs: engine._ensure_natal_artifact(*args, **kwargs),
        _guixu_definitions=lambda *args, **kwargs: engine._guixu_definitions(*args, **kwargs),
        _history_visible_in_world=lambda *args, **kwargs: engine._history_visible_in_world(*args, **kwargs),
        _intrigue_can_invite_guest=lambda *args, **kwargs: engine._intrigue_can_invite_guest(*args, **kwargs),
        _natal_artifact_inventory_item=lambda *args, **kwargs: engine._natal_artifact_inventory_item(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _player_battle_power=lambda *args, **kwargs: engine._player_battle_power(*args, **kwargs),
        _player_intrinsic_combat_power=lambda *args, **kwargs: engine._player_intrinsic_combat_power(*args, **kwargs),
        _public_art_skills=lambda *args, **kwargs: engine._public_art_skills(*args, **kwargs),
        _public_auction=lambda *args, **kwargs: engine._public_auction(*args, **kwargs),
        _public_body_cultivation=lambda *args, **kwargs: engine._public_body_cultivation(*args, **kwargs),
        _public_concubine_system=lambda *args, **kwargs: engine._public_concubine_system(*args, **kwargs),
        _public_crafting_system=lambda *args, **kwargs: engine._public_crafting_system(*args, **kwargs),
        _public_dao_companion=lambda *args, **kwargs: engine._public_dao_companion(*args, **kwargs),
        _public_dao_friends=lambda *args, **kwargs: engine._public_dao_friends(*args, **kwargs),
        _public_demonic_system=lambda *args, **kwargs: engine._public_demonic_system(*args, **kwargs),
        _public_exchange=lambda *args, **kwargs: engine._public_exchange(*args, **kwargs),
        _public_faction=lambda *args, **kwargs: engine._public_faction(*args, **kwargs),
        _public_family=lambda *args, **kwargs: engine._public_family(*args, **kwargs),
        _public_formation_system=lambda *args, **kwargs: engine._public_formation_system(*args, **kwargs),
        _public_ghost_system=lambda *args, **kwargs: engine._public_ghost_system(*args, **kwargs),
        _public_governance=lambda *args, **kwargs: engine._public_governance(*args, **kwargs),
        _public_guixu=lambda *args, **kwargs: engine._public_guixu(*args, **kwargs),
        _public_heavenly_court=lambda *args, **kwargs: engine._public_heavenly_court(*args, **kwargs),
        _public_yaochi=lambda *args, **kwargs: engine._public_yaochi(*args, **kwargs),
        _public_golden_light=lambda *args, **kwargs: engine._public_golden_light(*args, **kwargs),
        _public_intrigue_system=lambda *args, **kwargs: engine._public_intrigue_system(*args, **kwargs),
        _public_major_breakthrough=lambda *args, **kwargs: engine._public_major_breakthrough(*args, **kwargs),
        _public_map_with_ghost_parade=lambda *args, **kwargs: engine._public_map_with_ghost_parade(*args, **kwargs),
        _public_market=lambda *args, **kwargs: engine._public_market(*args, **kwargs),
        _public_merchant=lambda *args, **kwargs: engine._public_merchant(*args, **kwargs),
        _public_natal_artifact=lambda *args, **kwargs: engine._public_natal_artifact(*args, **kwargs),
        _public_party=lambda *args, **kwargs: engine._public_party(*args, **kwargs),
        _public_personal_relations=lambda *args, **kwargs: engine._public_personal_relations(*args, **kwargs),
        _public_race_system=lambda *args, **kwargs: engine._public_race_system(*args, **kwargs),
        _public_sage_system=lambda *args, **kwargs: engine._public_sage_system(*args, **kwargs),
        _public_secret_arts=lambda *args, **kwargs: engine._public_secret_arts(*args, **kwargs),
        _public_spirit_field=lambda *args, **kwargs: engine._public_spirit_field(*args, **kwargs),
        _public_spirit_ranking=lambda *args, **kwargs: engine._public_spirit_ranking(*args, **kwargs),
        _public_tianji=lambda *args, **kwargs: engine._public_tianji(*args, **kwargs),
        _public_doctrines=lambda *args, **kwargs: engine._public_doctrines(*args, **kwargs),
        _public_wanted=lambda *args, **kwargs: engine._public_wanted(*args, **kwargs),
        _public_war_system=lambda *args, **kwargs: engine._public_war_system(*args, **kwargs),
        _public_world_npcs=lambda *args, **kwargs: engine._public_world_npcs(*args, **kwargs),
        _public_world_route=lambda *args, **kwargs: engine._public_world_route(*args, **kwargs),
        _rank=lambda *args, **kwargs: engine._rank(*args, **kwargs),
        _relationship_can_join_faction=lambda *args, **kwargs: engine._relationship_can_join_faction(*args, **kwargs),
        _stable_gender=lambda *args, **kwargs: engine._stable_gender(*args, **kwargs),
        _tribulation_base_power_cap=lambda *args, **kwargs: engine._tribulation_base_power_cap(*args, **kwargs),
        _get_achievements=lambda: engine.achievements,
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
