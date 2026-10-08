"""Named dependencies for independently testable algorithms."""
from dataclasses import dataclass
from typing import Any, Callable
from ...ports import SavePort, MapPort
from ...models import GameState


@dataclass(frozen=True, slots=True)
class WarStateDependencies:
    _active_war: Callable[..., Any]
    _all_world_npcs: Callable[..., Any]
    _coalition_ids: Callable[..., Any]
    _ensure_war_shape: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _intrigue_is_imprisoned: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _participant_side: Callable[..., Any]
    _player_allegiance_race: Callable[..., Any]
    _sect_members: Callable[..., Any]
    _start_war: Callable[..., Any]
    _war_npc: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_sect: Callable[..., Any]
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class WarDiplomacyDependencies:
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    _active_war: Callable[..., Any]
    _add_war_participant: Callable[..., Any]
    _allied_powers: Callable[..., Any]
    _append_war_log: Callable[..., Any]
    _coalition_ids: Callable[..., Any]
    _ensure_war_shape: Callable[..., Any]
    _has_family_voice: Callable[..., Any]
    _has_race_voice: Callable[..., Any]
    _has_sect_voice: Callable[..., Any]
    _intrigue_defensive_guest_ids: Callable[..., Any]
    _intrigue_player_guest_side: Callable[..., Any]
    _participant_side: Callable[..., Any]
    _player_has_war_voice: Callable[..., Any]
    _player_war_side: Callable[..., Any]
    _power_exists_in_world: Callable[..., Any]
    _war_player_identity: Callable[..., Any]
    _war_relation: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_side_members: Callable[..., Any]
    _war_side_name: Callable[..., Any]
    _war_total_power: Callable[..., Any]
    _war_world: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class WarPowerDependencies:
    _available_warriors: Callable[..., Any]
    _coalition_ids: Callable[..., Any]
    _ground_profile: Callable[..., Any]
    _npc_formation_power_multiplier: Callable[..., Any]
    _npc_formation_profile: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _player_intrinsic_combat_power: Callable[..., Any]
    _sect_guard_array: Callable[..., Any]
    _sect_guard_power: Callable[..., Any]
    _war_formation_metric_score: Callable[..., Any]
    _war_formation_modifier: Callable[..., Any]
    _war_player_identity: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_side_formation: Callable[..., Any]
    _war_side_name: Callable[..., Any]
    _war_total_power: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class WarCombatDependencies:
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    _append_war_log: Callable[..., Any]
    _available_warriors: Callable[..., Any]
    _combat: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _finish_war_by_morale: Callable[..., Any]
    _maybe_transfer_player_dependency: Callable[..., Any]
    _npc_faction_id: Callable[..., Any]
    _npc_formation_power_multiplier: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _player_has_war_voice: Callable[..., Any]
    _player_war_side: Callable[..., Any]
    _resolve_field_attack: Callable[..., Any]
    _shift_war_morale: Callable[..., Any]
    _war_defeat_probabilities: Callable[..., Any]
    _war_formation_contexts: Callable[..., Any]
    _war_formation_text: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_side_name: Callable[..., Any]
    _wear_war_guard_arrays: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class WarLifecycleDependencies:
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    _append_war_log: Callable[..., Any]
    _available_warriors: Callable[..., Any]
    _call_war_allies: Callable[..., Any]
    _conclude_war: Callable[..., Any]
    _conclude_war_bundle: Callable[..., Any]
    _ensure_war_shape: Callable[..., Any]
    _finish_war_by_morale: Callable[..., Any]
    _generate_ai_peace_offer: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _player_has_war_voice: Callable[..., Any]
    _player_war_side: Callable[..., Any]
    _resolve_abstract_defeat: Callable[..., Any]
    _resolve_field_attack: Callable[..., Any]
    _shift_war_morale: Callable[..., Any]
    _war_formation_contexts: Callable[..., Any]
    _war_formation_text: Callable[..., Any]
    _war_power_profile: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_side_name: Callable[..., Any]
    _wear_war_guard_arrays: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class WarPeaceDependencies:
    _get_maps: Callable[[], MapPort]
    _append_war_log: Callable[..., Any]
    _available_warriors: Callable[..., Any]
    _coalition_ids: Callable[..., Any]
    _conclude_war: Callable[..., Any]
    _ensure_war_shape: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_resolve: Callable[..., Any]
    _load: Callable[[str], GameState]
    _player_has_war_voice: Callable[..., Any]
    _player_war_side: Callable[..., Any]
    _record_former_jailer_dissolved: Callable[..., Any]
    _sect_members: Callable[..., Any]
    _set_diplomatic_relation: Callable[..., Any]
    _war_entity_power: Callable[..., Any]
    _war_player_identity: Callable[..., Any]
    _war_relation: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_sect: Callable[..., Any]
    _war_side_name: Callable[..., Any]
    _war_total_power: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    decode_rng: Callable[..., Any]
    _get_WAR_TERM_DEFS: Callable[[], Any]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()

    @property
    def WAR_TERM_DEFS(self) -> Any:
        return self._get_WAR_TERM_DEFS()


@dataclass(frozen=True, slots=True)
class WarActionsDependencies:
    _append_war_log: Callable[..., Any]
    _available_warriors: Callable[..., Any]
    _call_war_allies: Callable[..., Any]
    _conclude_war_bundle: Callable[..., Any]
    _ensure_war_shape: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _finish_war_by_morale: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _load: Callable[[str], GameState]
    _npc_faction_id: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _npc_realm_name: Callable[..., Any]
    _participant_side: Callable[..., Any]
    _player_has_war_voice: Callable[..., Any]
    _player_war_side: Callable[..., Any]
    _resolve_field_attack: Callable[..., Any]
    _resolve_player_war_round: Callable[..., Any]
    _war_formation_contexts: Callable[..., Any]
    _war_formation_text: Callable[..., Any]
    _war_player_identity: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_side_name: Callable[..., Any]
    _wear_war_guard_arrays: Callable[..., Any]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _get_maps: Callable[[], MapPort]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    decode_rng: Callable[..., Any]

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
class WarPresentationDependencies:
    _allied_powers: Callable[..., Any]
    _ensure_war_shape: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _npc_realm_name: Callable[..., Any]
    _participant_side: Callable[..., Any]
    _player_has_war_voice: Callable[..., Any]
    _player_war_side: Callable[..., Any]
    _war_formation_contexts: Callable[..., Any]
    _war_power_profile: Callable[..., Any]
    _war_rules: Callable[..., Any]
    _war_side_name: Callable[..., Any]
    _get_WAR_TERM_DEFS: Callable[[], Any]

    @property
    def WAR_TERM_DEFS(self) -> Any:
        return self._get_WAR_TERM_DEFS()


@dataclass(frozen=True, slots=True)
class WarDependencies:
    state: WarStateDependencies
    diplomacy: WarDiplomacyDependencies
    power: WarPowerDependencies
    combat: WarCombatDependencies
    lifecycle: WarLifecycleDependencies
    peace: WarPeaceDependencies
    actions: WarActionsDependencies
    presentation: WarPresentationDependencies
