"""Explicit, narrow dependency contracts for engine domain functions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..models import GameState, SectNpc, SectState
from ..system.combat_system import BattleUnit
from .ports import AchievementPort, MapPort, SavePort



@dataclass(frozen=True, slots=True)
class WorldRuntimeDependencies:
    _compact_sect_roster: Callable[..., bool]
    _new_sects: Callable[..., dict[str, SectState]]
    _new_world_npcs: Callable[..., dict[str, SectNpc]]
    _random_npc_path: Callable[..., str]
    _random_npc_root: Callable[..., str]
    _select_npc_treasure: Callable[..., str | None]
    _world_realm_cap: Callable[..., int]


@dataclass(frozen=True, slots=True)
class EventDependencies:
    _base_affinities: Callable[..., list[str]]
    _cache_encounter_target: Callable[..., None]
    _combat: Callable[..., tuple[str, str]]
    _condition: Callable[..., bool]
    _die: Callable[..., None]
    _event_weight: Callable[..., float]
    _generate_cultivator_target: Callable[..., dict[str, Any]]
    _path: Callable[..., Any]
    _record_revenge_trigger: Callable[..., int]
    _revenge_ready: Callable[..., bool]
    _story_unit_full_power: Callable[..., float]
    _world_supports: Callable[..., bool]
    _get_events: Callable[[], list[dict[str, Any]]]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._get_events()

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class CombatDependencies:
    _apply_cultivator_kill: Callable[..., None]
    _apply_support_damage: Callable[..., None]
    _capture_cultivator: Callable[..., tuple[str, str]]
    _capture_defeated_ghost: Callable[..., bool]
    _check_sect_extinction: Callable[..., bool]
    _combat_battlefield_tags: Callable[..., list[str]]
    _combat_report_lead: Callable[..., str]
    _court_law_active: Callable[..., bool]
    _die: Callable[..., None]
    _ensure_war_shape: Callable[..., bool]
    _find_npc: Callable[..., SectNpc | None]
    _formation_rules: Callable[..., dict[str, Any]]
    _grant_art_experience: Callable[..., None]
    _grant_demonic_kill_opportunity: Callable[..., float]
    _ground_profile: Callable[..., dict[str, Any]]
    _handle_same_sect_kill: Callable[..., None]
    _hostility_key: Callable[..., str]
    _inject_tianji_npc_artifacts: Callable[..., None]
    _instantiate_event: Callable[..., dict[str, Any]]
    _is_wartime_opponent: Callable[..., bool]
    _kill_generates_hostility: Callable[..., bool]
    _local_ground_formation: Callable[..., dict[str, Any] | None]
    _natal_artifact_combat_effects: Callable[..., list[dict[str, Any]]]
    _npc_formation_power_multiplier: Callable[..., float]
    _npc_formation_profile: Callable[..., dict[str, Any]]
    _participant_side: Callable[..., str | None]
    _player_allegiance_race: Callable[..., str]
    _player_combat_units: Callable[..., list[BattleUnit]]
    _post_battle_possession_candidates: Callable[..., list[dict[str, Any]]]
    _prepare_post_battle_possession: Callable[..., bool]
    _public_party: Callable[..., list[dict[str, Any]]]
    _race_alliance: Callable[..., dict[str, Any] | None]
    _record_player_combat: Callable[..., None]
    _sage_scaled_gain: Callable[..., float]
    _story_unit_full_power: Callable[..., float]
    _tianji_handle_npc_kill: Callable[..., str]
    _world_supports: Callable[..., bool]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _get_maps: Callable[[], MapPort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class PresentationDependencies:
    _ensure_natal_artifact: Callable[..., bool]
    _guixu_definitions: Callable[..., dict[str, dict[str, Any]]]
    _history_visible_in_world: Callable[..., bool]
    _intrigue_can_invite_guest: Callable[..., bool]
    _natal_artifact_inventory_item: Callable[..., dict[str, Any] | None]
    _npc_realm_name: Callable[..., str]
    _player_battle_power: Callable[..., float]
    _player_intrinsic_combat_power: Callable[..., float]
    _public_art_skills: Callable[..., list[dict[str, Any]]]
    _public_auction: Callable[..., dict[str, Any]]
    _public_body_cultivation: Callable[..., dict[str, Any]]
    _public_concubine_system: Callable[..., dict[str, Any]]
    _public_crafting_system: Callable[..., dict[str, Any]]
    _public_dao_companion: Callable[..., dict[str, Any] | None]
    _public_dao_friends: Callable[..., list[dict[str, Any]]]
    _public_demonic_system: Callable[..., dict[str, Any]]
    _public_exchange: Callable[..., Any]
    _public_faction: Callable[..., dict[str, Any]]
    _public_family: Callable[..., dict[str, Any]]
    _public_formation_system: Callable[..., dict[str, Any]]
    _public_ghost_system: Callable[..., dict[str, Any]]
    _public_governance: Callable[..., dict[str, Any]]
    _public_guixu: Callable[..., dict[str, Any]]
    _public_heavenly_court: Callable[..., dict[str, Any]]
    _public_intrigue_system: Callable[..., dict[str, Any]]
    _public_major_breakthrough: Callable[..., dict[str, Any]]
    _public_map_with_ghost_parade: Callable[..., dict[str, Any]]
    _public_market: Callable[..., dict[str, Any]]
    _public_merchant: Callable[..., Any]
    _public_natal_artifact: Callable[..., dict[str, Any]]
    _public_party: Callable[..., list[dict[str, Any]]]
    _public_personal_relations: Callable[..., dict[str, list[dict[str, Any]]]]
    _public_race_system: Callable[..., dict[str, Any]]
    _public_sage_system: Callable[..., dict[str, Any]]
    _public_secret_arts: Callable[..., dict[str, Any]]
    _public_spirit_field: Callable[..., dict[str, Any]]
    _public_spirit_ranking: Callable[..., dict[str, Any]]
    _public_tianji: Callable[..., dict[str, Any]]
    _public_wanted: Callable[..., list[dict[str, Any]]]
    _public_war_system: Callable[..., dict[str, Any]]
    _public_world_npcs: Callable[..., list[dict[str, Any]]]
    _public_world_route: Callable[..., dict[str, Any]]
    _rank: Callable[..., tuple[int, int]]
    _relationship_can_join_faction: Callable[..., bool]
    _stable_gender: Callable[..., str]
    _tribulation_base_power_cap: Callable[..., float | None]
    _get_achievements: Callable[[], AchievementPort]
    _get_maps: Callable[[], MapPort]

    @property
    def achievements(self) -> AchievementPort:
        return self._get_achievements()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class PersistenceDependencies:
    _body_progress_required: Callable[..., float]
    _clear_market: Callable[..., None]
    _compact_world_history: Callable[..., bool]
    _cultivation_sense_requirement: Callable[..., int]
    _die: Callable[..., None]
    _enforce_world_realm_caps: Callable[..., bool]
    _ensure_guixu_state: Callable[..., bool]
    _ensure_heavenly_court: Callable[..., bool]
    _ensure_market: Callable[..., bool]
    _ensure_merchant: Callable[..., bool]
    _ensure_natal_artifact: Callable[..., bool]
    _ensure_npc_formations: Callable[..., bool]
    _ensure_race_relations: Callable[..., bool]
    _ensure_sage_state: Callable[..., bool]
    _ensure_sect_relations: Callable[..., bool]
    _ensure_sects: Callable[..., None]
    _ensure_tianji_state: Callable[..., bool]
    _ensure_wars: Callable[..., bool]
    _ensure_world_npcs: Callable[..., bool]
    _manual_breakthrough_kind: Callable[..., str | None]
    _manual_minor_layers: Callable[..., set[int]]
    _migrate_true_demon_races: Callable[..., bool]
    _refresh_sage_effects: Callable[..., None]
    _sync_party_state: Callable[..., bool]
    _sync_relationship_records: Callable[..., bool]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _get_maps: Callable[[], MapPort]
    _get_store: Callable[[], SavePort]
    bloodline_content_available: Callable[[], bool]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class SessionDependencies:
    _base_affinities: Callable[..., list[str]]
    _cultivation_sense_requirement: Callable[..., int]
    _ensure_ghost_parade: Callable[..., None]
    _ensure_guixu_state: Callable[..., bool]
    _ensure_heavenly_court: Callable[..., bool]
    _ensure_market: Callable[..., bool]
    _ensure_npc_formations: Callable[..., bool]
    _ensure_race_relations: Callable[..., bool]
    _ensure_sage_state: Callable[..., bool]
    _ensure_sect_relations: Callable[..., bool]
    _ensure_sects: Callable[..., None]
    _ensure_tianji_state: Callable[..., bool]
    _ensure_world_npcs: Callable[..., bool]
    _new_sects: Callable[..., dict[str, SectState]]
    _new_world_npcs: Callable[..., dict[str, SectNpc]]
    _npc_realm_name: Callable[..., str]
    _get_achievements: Callable[[], AchievementPort]
    _get_maps: Callable[[], MapPort]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]
    bloodline_content_available: Callable[[], bool]

    @property
    def achievements(self) -> AchievementPort:
        return self._get_achievements()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class AdvancementDependencies:
    _add_opportunity: Callable[..., float]
    _advance_auction_clock: Callable[..., None]
    _advance_concubine_aftermath: Callable[..., bool]
    _advance_concubine_status: Callable[..., float]
    _advance_diplomacy_unit: Callable[..., list[str]]
    _advance_exchange_clock: Callable[..., Any]
    _advance_heavenly_court_unit: Callable[..., list[str]]
    _advance_intrigue_unit: Callable[..., list[str]]
    _advance_natal_artifact: Callable[..., str | None]
    _advance_player_bounties: Callable[..., None]
    _advance_soul_erosion_time: Callable[..., bool]
    _advance_world_year: Callable[..., bool]
    _apply_action_resources: Callable[..., None]
    _body_progress_required: Callable[..., float]
    _body_training_step: Callable[..., float]
    _commission_step: Callable[..., str]
    _compact_world_history: Callable[..., bool]
    _condense_action_results: Callable[..., str]
    _court_law_active: Callable[..., bool]
    _ensure_market: Callable[..., bool]
    _finish_sage_action: Callable[..., None]
    _guixu_trapped_training: Callable[..., dict[str, Any]]
    _instantiate_event: Callable[..., dict[str, Any]]
    _load: Callable[..., GameState]
    _market_tier: Callable[..., int]
    _maybe_affinity_gift: Callable[..., bool]
    _maybe_concubine_proposal: Callable[..., bool]
    _maybe_faction_event: Callable[..., bool]
    _maybe_founded_sect_pressure: Callable[..., bool]
    _maybe_immortal_conversion_event: Callable[..., bool]
    _maybe_personal_revenge: Callable[..., bool]
    _maybe_probability_story_event: Callable[..., bool]
    _maybe_relationship_sanction: Callable[..., bool]
    _maybe_tianji_intelligence_event: Callable[..., str | None]
    _maybe_xiang_node_event: Callable[..., bool]
    _personal_combat_step: Callable[..., str]
    _prepare_sage_action: Callable[..., None]
    _prepare_treasure_reward_event: Callable[..., dict[str, Any]]
    _queue_followup_event: Callable[..., None]
    _record_era_summary: Callable[..., None]
    _select_event: Callable[..., dict[str, Any] | None]
    _sense_training_step: Callable[..., float]
    _treasure_step: Callable[..., str]
    _get_maps: Callable[[], MapPort]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class CultivationActionDependencies:
    _body_breakthrough_chance: Callable[..., dict[str, float]]
    _body_pity_key: Callable[..., str]
    _body_progress_required: Callable[..., float]
    _body_tribulation_damage_reduction: Callable[..., float]
    _breakthrough_chance: Callable[..., dict[str, float]]
    _clear_minor_pity: Callable[..., None]
    _complete_major_breakthrough: Callable[..., None]
    _complete_minor_breakthrough: Callable[..., None]
    _consume_breakthrough_aids: Callable[..., None]
    _cultivation_sense_requirement: Callable[..., int]
    _enforce_guixu_rank_boundary: Callable[..., str]
    _ensure_market: Callable[..., bool]
    _joint_companion_eligible: Callable[..., dict[str, Any] | None]
    _load: Callable[..., GameState]
    _major_breakthrough_requirement: Callable[..., dict[str, Any]]
    _manual_breakthrough_kind: Callable[..., str | None]
    _minor_layer_target: Callable[..., str]
    _npc_realm_name: Callable[..., str]
    _record_minor_pity_failure: Callable[..., float]
    _sage_scaled_gain: Callable[..., float]
    _secret_art_realm_name: Callable[..., str]
    _start_breakthrough_trial: Callable[..., None]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]
    bloodline_content_available: Callable[[], bool]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class WorldTravelDependencies:
    _ascension_destination: Callable[..., str]
    _cancel_auction_for_world_change: Callable[..., None]
    _clear_market: Callable[..., None]
    _complete_demonic_ascension: Callable[..., dict[str, Any]]
    _die: Callable[..., None]
    _ensure_market: Callable[..., bool]
    _find_npc: Callable[..., SectNpc | None]
    _handover_faction_for_ascension: Callable[..., dict[str, Any] | None]
    _instantiate_event: Callable[..., dict[str, Any]]
    _intrigue_key: Callable[..., str]
    _intrigue_position_specs: Callable[..., dict[str, dict[str, Any]]]
    _intrigue_state: Callable[..., dict[str, Any]]
    _intrigue_sync_player_prison: Callable[..., None]
    _load: Callable[..., GameState]
    _maybe_founder_return_event: Callable[..., bool]
    _party_crossing_candidate: Callable[..., dict[str, Any] | None]
    _prepare_permanent_world_transition: Callable[..., dict[str, Any]]
    _resolve_selected_ascension_entourage: Callable[..., tuple[bool, set[str], list[str], list[str]]]
    _sect_members: Callable[..., list[SectNpc]]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _get_maps: Callable[[], MapPort]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class FactionActionDependencies:
    _actual_player_realm: Callable[..., tuple[int, int]]
    _check_sect_extinction: Callable[..., bool]
    _ensure_sect_relations: Callable[..., bool]
    _governance_threshold: Callable[..., int]
    _has_race_voice: Callable[..., bool]
    _has_sect_voice: Callable[..., bool]
    _intrigue_enabled: Callable[..., bool]
    _intrigue_state: Callable[..., dict[str, Any]]
    _load: Callable[..., GameState]
    _player_allegiance_race: Callable[..., str]
    _power_name: Callable[..., str]
    _random_npc_root: Callable[..., str]
    _roll_recruit_age_lifespan: Callable[..., tuple[int, int | None]]
    _sect_members: Callable[..., list[SectNpc]]
    _select_npc_treasure: Callable[..., str | None]
    _set_diplomatic_relation: Callable[..., None]
    _stable_gender: Callable[..., str]
    _sync_relationship_records: Callable[..., bool]
    _vote_probability: Callable[..., float]
    intrigue_propose_resolution: Callable[..., dict[str, Any]]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class EncounterActionDependencies:
    _add_enemy_party: Callable[..., dict[str, Any]]
    _add_opportunity: Callable[..., float]
    _advance_concubine_status: Callable[..., float]
    _advance_soul_erosion_time: Callable[..., bool]
    _annual_sect_update: Callable[..., list[str]]
    _annual_world_npc_update: Callable[..., list[str]]
    _apply_combat_action_rewards: Callable[..., str]
    _available_bounty_authorities: Callable[..., list[dict[str, str]]]
    _cache_encounter_target: Callable[..., None]
    _check_tribulation: Callable[..., None]
    _combat: Callable[..., tuple[str, str]]
    _die: Callable[..., None]
    _generate_cultivator_target: Callable[..., dict[str, Any]]
    _has_family_voice: Callable[..., bool]
    _has_race_voice: Callable[..., bool]
    _has_sect_voice: Callable[..., bool]
    _instantiate_event: Callable[..., dict[str, Any]]
    _intrigue_sync_player_prison: Callable[..., None]
    _known_npc_encounter_target: Callable[..., dict[str, Any] | None]
    _load: Callable[..., GameState]
    _npc_cultivation_perception: Callable[..., dict[str, Any]]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _player_allegiance_race: Callable[..., str]
    _player_battle_power: Callable[..., float]
    _player_intrinsic_combat_power: Callable[..., float]
    _player_protected_npc_ids: Callable[..., set[str]]
    _promote_cached_npc: Callable[..., SectNpc | None]
    _record_world_coalition_amnesty: Callable[..., None]
    _remember_faction_prison_release: Callable[..., None]
    _sage_scaled_gain: Callable[..., float]
    _sect_members: Callable[..., list[SectNpc]]
    _tianji_observe_npc: Callable[..., None]
    _tianji_preview_npc_power: Callable[..., None]
    _world_supports: Callable[..., bool]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class InventoryDependencies:
    _add_opportunity: Callable[..., float]
    _base_affinities: Callable[..., list[str]]
    _buy_crafting_material_offer: Callable[..., str]
    _buy_formation_material_offer: Callable[..., str]
    _buy_formation_supply_offer: Callable[..., str]
    _load: Callable[..., GameState]
    _manual_minor_layers: Callable[..., set[int]]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]
    bloodline_content_available: Callable[[], bool]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class RelationshipActionDependencies:
    _add_opportunity: Callable[..., float]
    _adjust_person_affinity: Callable[..., float]
    _default_npc_main_technique: Callable[..., str | None]
    _find_npc: Callable[..., SectNpc | None]
    _hostility_key: Callable[..., str]
    _load: Callable[..., GameState]
    _market_tier: Callable[..., int]
    _npc_faction_id: Callable[..., str | None]
    _party_crossing_candidate: Callable[..., dict[str, Any] | None]
    _party_invitation_chance: Callable[..., float]
    _persist_relationship_npc: Callable[..., SectNpc]
    _promote_cached_npc: Callable[..., SectNpc | None]
    _relationship_snapshot: Callable[..., dict[str, Any]]
    _sage_affinity_gain: Callable[..., float]
    _sage_scaled_gain: Callable[..., float]
    _sect_members: Callable[..., list[SectNpc]]
    _set_person_affinity: Callable[..., float]
    _tianji_npc_conversation_clue: Callable[..., str]
    _try_conceive_child: Callable[..., str]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class ChoiceDependencies:
    _condition: Callable[..., bool]
    _diff: Callable[..., dict[str, Any]]
    _effect: Callable[..., tuple[str | None, str]]
    _enforce_guixu_rank_boundary: Callable[..., str]
    _ensure_market: Callable[..., bool]
    _load: Callable[..., GameState]
    _maybe_artifact_synthesis: Callable[..., bool]
    _queue_followup_event: Callable[..., None]
    _resolve_breakthroughs: Callable[..., None]
    _snapshot: Callable[..., dict[str, Any]]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    present: Callable[..., dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class BreakthroughDependencies:
    _add_opportunity: Callable[..., float]
    _breakthrough_chance: Callable[..., dict[str, float]]
    _combat: Callable[..., tuple[str, str]]
    _complete_joint_companion_breakthrough: Callable[..., None]
    _complete_major_breakthrough: Callable[..., None]
    _complete_minor_breakthrough: Callable[..., None]
    _die: Callable[..., None]
    _find_npc: Callable[..., SectNpc | None]
    _instantiate_event: Callable[..., dict[str, Any]]
    _joint_companion_eligible: Callable[..., dict[str, Any] | None]
    _manual_minor_layers: Callable[..., set[int]]
    _minor_layer_target: Callable[..., str]
    _minor_pity_bonus: Callable[..., float]
    _minor_pity_key: Callable[..., str]
    _npc_lifespan_multiplier: Callable[..., int]
    _npc_realm_name: Callable[..., str]
    _player_battle_power: Callable[..., float]
    _queue_heavenly_demon_battle: Callable[..., None]
    _raise_divine_sense_one_level: Callable[..., None]
    _root_probability_group: Callable[..., str]
    _sage_scaled_gain: Callable[..., float]
    _start_breakthrough_trial: Callable[..., None]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    bloodline_content_available: Callable[[], bool]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class TrialDependencies:
    _body_tribulation_damage_reduction: Callable[..., float]
    _clear_market: Callable[..., None]
    _complete_major_breakthrough: Callable[..., None]
    _complete_minor_breakthrough: Callable[..., None]
    _die: Callable[..., None]
    _ensure_heavenly_court: Callable[..., bool]
    _ensure_market: Callable[..., bool]
    _instantiate_event: Callable[..., dict[str, Any]]
    _player_intrinsic_combat_power: Callable[..., float]
    _prepare_permanent_world_transition: Callable[..., dict[str, Any]]
    _resolve_asura_ascension_step: Callable[..., tuple[str, str]]
    _resolve_celestial_ascension_step: Callable[..., tuple[str, str]]
    _resolve_heavenly_demon_battle: Callable[..., tuple[str, str]]
    _resolve_selected_ascension_entourage: Callable[..., tuple[bool, set[str], list[str], list[str]]]
    _sage_scaled_gain: Callable[..., float]
    _tribulation_base_power_cap: Callable[..., float | None]
    _tribulation_damage_reduction: Callable[..., float]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _get_maps: Callable[[], MapPort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class EncounterDependencies:
    _add_enemy_party: Callable[..., dict[str, Any]]
    _condition: Callable[..., bool]
    _encounter_person_name: Callable[..., str]
    _faction_meta: Callable[..., dict[str, Any]]
    _instantiate_event: Callable[..., dict[str, Any]]
    _intrigue_enabled: Callable[..., bool]
    _intrigue_pressure_position_occupied: Callable[..., bool]
    _npc_cultivation_perception: Callable[..., dict[str, Any]]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _player_allegiance_race: Callable[..., str]
    _player_intrinsic_combat_power: Callable[..., float]
    _promote_cached_npc: Callable[..., SectNpc | None]
    _random_npc_root: Callable[..., str]
    _record_revenge_trigger: Callable[..., int]
    _revenge_ready: Callable[..., bool]
    _roll_escalating_event: Callable[..., bool]
    _scale_npc_lifespan: Callable[..., int | None]
    _select_npc_treasure: Callable[..., str | None]
    _world_realm_cap: Callable[..., int]
    _world_supports: Callable[..., bool]
    _would_enter_spirit_ranking: Callable[..., bool]
    _get_events: Callable[[], list[dict[str, Any]]]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._get_events()

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class EffectDependencies:
    _add_court_merit: Callable[..., str]
    _add_opportunity: Callable[..., float]
    _adjust_person_affinity: Callable[..., float]
    _apply_combat_action_rewards: Callable[..., str]
    _ascension_destination: Callable[..., str]
    _body_progress_required: Callable[..., float]
    _cache_encounter_target: Callable[..., None]
    _claim_treasure_reward: Callable[..., tuple[str, str]]
    _clear_market: Callable[..., None]
    _combat: Callable[..., tuple[str, str]]
    _complete_ghost_reincarnation: Callable[..., dict[str, Any]]
    _complete_immortal_conversion_stage: Callable[..., tuple[str, str]]
    _court_law_active: Callable[..., bool]
    _die: Callable[..., None]
    _dissolve_player_sect: Callable[..., None]
    _ensure_intrigue_faction: Callable[..., dict[str, Any]]
    _find_npc: Callable[..., SectNpc | None]
    _formation_rules: Callable[..., dict[str, Any]]
    _generate_cultivator_target: Callable[..., dict[str, Any]]
    _generated_relationship: Callable[..., dict[str, Any]]
    _grant_art_experience: Callable[..., None]
    _ground_profile: Callable[..., dict[str, Any]]
    _hostility_key: Callable[..., str]
    _instantiate_event: Callable[..., dict[str, Any]]
    _intrigue_position_specs: Callable[..., dict[str, dict[str, Any]]]
    _intrigue_state: Callable[..., dict[str, Any]]
    _is_story_combat_check: Callable[..., bool]
    _npc_power: Callable[..., float]
    _player_intrinsic_combat_power: Callable[..., float]
    _prepare_permanent_world_transition: Callable[..., dict[str, Any]]
    _relationship_capture_step: Callable[..., tuple[str, str]]
    _resolve_concubine_escape: Callable[..., tuple[str, str]]
    _resolve_concubine_proposal: Callable[..., tuple[str, str]]
    _resolve_concubine_revenge: Callable[..., tuple[str, str]]
    _resolve_relationship_sanction: Callable[..., tuple[str, str]]
    _resolve_story_combat_check: Callable[..., tuple[str, str]]
    _resolve_trial_step: Callable[..., tuple[str, str]]
    _resolve_wanted_response: Callable[..., tuple[str, str]]
    _resolve_wanted_settlement: Callable[..., tuple[str, str]]
    _resolve_war_vanguard: Callable[..., tuple[str, str]]
    _sage_affinity_gain: Callable[..., float]
    _sage_scaled_gain: Callable[..., float]
    _sect_guard_array: Callable[..., dict[str, Any] | None]
    _sect_guard_power: Callable[..., float]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    grant_monster_imprint: Callable[..., bool]
    _get_maps: Callable[[], MapPort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class NpcDependencies:
    _advance_merchant_year: Callable[..., Any]
    _advance_npc_cultivation: Callable[..., dict[str, str] | None]
    _all_world_npcs: Callable[..., list[SectNpc]]
    _ascension_destination: Callable[..., str]
    _cultivation_sense_requirement: Callable[..., int]
    _ensure_npc_concealment: Callable[..., tuple[int, int] | None]
    _ensure_sect_relations: Callable[..., bool]
    _find_npc: Callable[..., SectNpc | None]
    _instantiate_event: Callable[..., dict[str, Any]]
    _intrigue_is_imprisoned: Callable[..., bool]
    _maybe_notorious_npc_killing: Callable[..., None]
    _mortal_root_completion_chance: Callable[..., float]
    _npc_breakthrough_probability: Callable[..., float]
    _npc_faction_id: Callable[..., str | None]
    _npc_lifespan_multiplier: Callable[..., int]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _npc_root_efficiency: Callable[..., float]
    _random_npc_path: Callable[..., str]
    _random_npc_root: Callable[..., str]
    _recruit_realm_index: Callable[..., int]
    _recruit_sect_npc: Callable[..., SectNpc]
    _resolve_npc_periodic_tribulation: Callable[..., str | None]
    _roll_recruit_age_lifespan: Callable[..., tuple[int, int | None]]
    _scale_npc_lifespan: Callable[..., int | None]
    _select_npc_treasure: Callable[..., str | None]
    _stable_secret_art_roll: Callable[..., int]
    _tribulation_base_power_cap: Callable[..., float | None]
    _world_realm_cap: Callable[..., int]
    _world_supports: Callable[..., bool]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class RelationshipDependencies:
    _actual_player_realm: Callable[..., tuple[int, int]]
    _advance_npc_cultivation: Callable[..., dict[str, str] | None]
    _all_world_npcs: Callable[..., list[SectNpc]]
    _filter_personal_revenge_by_protection: Callable[..., list[SectNpc]]
    _find_npc: Callable[..., SectNpc | None]
    _high_affinity_npcs: Callable[..., list[SectNpc]]
    _instantiate_event: Callable[..., dict[str, Any]]
    _npc_cultivation_perception: Callable[..., dict[str, Any]]
    _npc_faction_id: Callable[..., str | None]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _npc_root_name: Callable[..., str]
    _persist_relationship_npc: Callable[..., SectNpc]
    _personal_npcs: Callable[..., list[SectNpc]]
    _random_npc_root: Callable[..., str]
    _record_revenge_trigger: Callable[..., int]
    _recruit_sect_npc: Callable[..., SectNpc]
    _relationship_snapshot: Callable[..., dict[str, Any]]
    _resolve_npc_periodic_tribulation: Callable[..., str | None]
    _retaliatory_relationship_ids: Callable[..., set[str]]
    _revenge_cooldown_key: Callable[..., str]
    _revenge_ready: Callable[..., bool]
    _sage_affinity_gain: Callable[..., float]
    _scale_npc_lifespan: Callable[..., int | None]
    _sect_members: Callable[..., list[SectNpc]]
    _stable_gender: Callable[..., str]
    _sync_relationship_records: Callable[..., bool]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    bloodline_content_available: Callable[[], bool]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class FactionDependencies:
    _actual_player_realm: Callable[..., tuple[int, int]]
    _add_opportunity: Callable[..., float]
    _advance_diplomacy_unit: Callable[..., list[str]]
    _advance_npc_cultivation: Callable[..., dict[str, str] | None]
    _advance_wars_unit: Callable[..., list[str]]
    _all_world_npcs: Callable[..., list[SectNpc]]
    _annual_offspring_and_family_update: Callable[..., list[str]]
    _annual_relationship_update: Callable[..., None]
    _cache_encounter_target: Callable[..., None]
    _check_sect_extinction: Callable[..., bool]
    _compact_sect_roster: Callable[..., bool]
    _dynamic_sect_title: Callable[..., str]
    _ensure_race_relations: Callable[..., bool]
    _ensure_sect_relations: Callable[..., bool]
    _faction_meta: Callable[..., dict[str, Any]]
    _generate_cultivator_target: Callable[..., dict[str, Any]]
    _governance_threshold: Callable[..., int]
    _instantiate_event: Callable[..., dict[str, Any]]
    _intrigue_enabled: Callable[..., bool]
    _intrigue_has_decision_authority: Callable[..., bool]
    _intrigue_is_imprisoned: Callable[..., bool]
    _maybe_npc_found_power: Callable[..., None]
    _maybe_transfer_player_dependency: Callable[..., str]
    _npc_faction_id: Callable[..., str | None]
    _npc_lethal_chance: Callable[..., float]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _player_allegiance_race: Callable[..., str]
    _power_name: Callable[..., str]
    _pressure_weak_npc_powers: Callable[..., None]
    _race_power: Callable[..., float]
    _random_race_diplomacy_event: Callable[..., None]
    _random_sect_diplomacy_event: Callable[..., None]
    _record_revenge_trigger: Callable[..., int]
    _recruit_sect_npc: Callable[..., SectNpc]
    _resolve_npc_periodic_tribulation: Callable[..., str | None]
    _revenge_ready: Callable[..., bool]
    _sect_members: Callable[..., list[SectNpc]]
    _sect_power: Callable[..., float]
    _set_diplomatic_relation: Callable[..., None]
    _simulate_cultivator_duel: Callable[..., None]
    _start_war: Callable[..., dict[str, Any]]
    _world_supports: Callable[..., bool]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class HostilityDependencies:
    _actual_player_realm: Callable[..., tuple[int, int]]
    _add_enemy_party: Callable[..., dict[str, Any]]
    _all_world_npcs: Callable[..., list[SectNpc]]
    _available_bounty_authorities: Callable[..., list[dict[str, str]]]
    _cache_encounter_target: Callable[..., None]
    _check_sect_extinction: Callable[..., bool]
    _combat: Callable[..., tuple[str, str]]
    _default_npc_main_technique: Callable[..., str | None]
    _die: Callable[..., None]
    _find_npc: Callable[..., SectNpc | None]
    _generate_cultivator_target: Callable[..., dict[str, Any]]
    _hostility_entity_members: Callable[..., list[SectNpc]]
    _hostility_entity_state: Callable[..., dict[str, Any]]
    _hostility_key: Callable[..., str]
    _hostility_name: Callable[..., str]
    _imprison_or_execute: Callable[..., str]
    _instantiate_event: Callable[..., dict[str, Any]]
    _intrigue_record_player_prison: Callable[..., None]
    _npc_faction_id: Callable[..., str | None]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _player_allegiance_race: Callable[..., str]
    _player_battle_power: Callable[..., float]
    _player_protected_npc_ids: Callable[..., set[str]]
    _queue_wanted_settlement: Callable[..., None]
    _record_former_jailer_dissolved: Callable[..., bool]
    _record_revenge_trigger: Callable[..., int]
    _retaliatory_relationship_ids: Callable[..., set[str]]
    _revenge_ready: Callable[..., bool]
    _sect_members: Callable[..., list[SectNpc]]
    _wanted_target: Callable[..., dict[str, Any]]
    _world_coalition_amnesty_fame: Callable[..., float]
    _world_supports: Callable[..., bool]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class CharacterViewDependencies:
    _all_world_npcs: Callable[..., list[SectNpc]]
    _body_breakthrough_chance: Callable[..., dict[str, float]]
    _body_progress_required: Callable[..., float]
    _body_tribulation_damage_reduction: Callable[..., float]
    _breakthrough_chance: Callable[..., dict[str, float]]
    _faction_meta: Callable[..., dict[str, Any]]
    _find_npc: Callable[..., SectNpc | None]
    _hostility_entity_state: Callable[..., dict[str, Any]]
    _hostility_name: Callable[..., str]
    _intrigue_can_invite_guest: Callable[..., bool]
    _joint_companion_eligible: Callable[..., dict[str, Any] | None]
    _major_breakthrough_requirement: Callable[..., dict[str, Any]]
    _manual_breakthrough_kind: Callable[..., str | None]
    _minor_layer_target: Callable[..., str]
    _npc_cultivation_perception: Callable[..., dict[str, Any]]
    _npc_faction_id: Callable[..., str | None]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _party_crossing_candidate: Callable[..., dict[str, Any] | None]
    _rank: Callable[..., tuple[int, int]]
    _relationship_can_join_faction: Callable[..., bool]
    _relationship_combat_power: Callable[..., float]
    _relationship_cultivation_perception: Callable[..., dict[str, Any]]
    _stable_gender: Callable[..., str]
    bloodline_content_available: Callable[[], bool]


@dataclass(frozen=True, slots=True)
class WorldViewDependencies:
    _ensure_race_relations: Callable[..., bool]
    _has_race_voice: Callable[..., bool]
    _hostility_key: Callable[..., str]
    _intrigue_can_invite_guest: Callable[..., bool]
    _npc_cultivation_perception: Callable[..., dict[str, Any]]
    _npc_formation_power_multiplier: Callable[..., float]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _npc_root_name: Callable[..., str]
    _player_allegiance_race: Callable[..., str]
    _player_intrinsic_combat_power: Callable[..., float]
    _relationship_combat_power: Callable[..., float]
    _vassal_transfer_candidates: Callable[..., list[dict[str, Any]]]
    _world_supports: Callable[..., bool]


@dataclass(frozen=True, slots=True)
class FactionViewDependencies:
    _actual_player_realm: Callable[..., tuple[int, int]]
    _available_bounty_authorities: Callable[..., list[dict[str, str]]]
    _breakthrough_chance: Callable[..., dict[str, float]]
    _dynamic_sect_title: Callable[..., str]
    _faction_meta: Callable[..., dict[str, Any]]
    _governance_threshold: Callable[..., int]
    _has_family_voice: Callable[..., bool]
    _has_race_voice: Callable[..., bool]
    _has_sect_voice: Callable[..., bool]
    _hostility_key: Callable[..., str]
    _intrigue_state: Callable[..., dict[str, Any]]
    _manual_breakthrough_kind: Callable[..., str | None]
    _npc_breakthrough_probability: Callable[..., float]
    _npc_cultivation_perception: Callable[..., dict[str, Any]]
    _npc_power: Callable[..., float]
    _npc_realm_name: Callable[..., str]
    _npc_root_name: Callable[..., str]
    _player_intrinsic_combat_power: Callable[..., float]
    _public_sect_diplomacy: Callable[..., list[dict[str, Any]]]
    _sect_members: Callable[..., list[SectNpc]]
    _stable_gender: Callable[..., str]
    _vassal_transfer_candidates: Callable[..., list[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class NpcClassDependencies:
    _npc_lifespan_multiplier: Callable[..., int]



@dataclass(frozen=True, slots=True)
class EngineDependencies:
    world_runtime: WorldRuntimeDependencies
    event_runtime: EventDependencies
    combat_runtime: CombatDependencies
    presentation_runtime: PresentationDependencies
    persistence_runtime: PersistenceDependencies
    session: SessionDependencies
    advancement: AdvancementDependencies
    cultivation_actions: CultivationActionDependencies
    world_travel_actions: WorldTravelDependencies
    faction_actions: FactionActionDependencies
    encounter_actions: EncounterActionDependencies
    inventory_actions: InventoryDependencies
    relationship_actions: RelationshipActionDependencies
    choices: ChoiceDependencies
    breakthroughs: BreakthroughDependencies
    trials: TrialDependencies
    encounters: EncounterDependencies
    effects: EffectDependencies
    npcs: NpcDependencies
    world_relationships: RelationshipDependencies
    world_factions: FactionDependencies
    hostility: HostilityDependencies
    character_view: CharacterViewDependencies
    world_view: WorldViewDependencies
    faction_view: FactionViewDependencies
