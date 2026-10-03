"""Named collaborators for independently executable intrigue algorithms."""

from dataclasses import dataclass
from typing import Any, Callable

from ...ports import SavePort


@dataclass(frozen=True, slots=True)
class IntrigueGovernanceDependencies:
    _get_PLAYER_ID: Callable[[], Any]
    _actual_player_realm: Callable[..., Any]
    _ensure_intrigue_faction: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_entity: Callable[..., Any]
    _intrigue_faction_name: Callable[..., Any]
    _intrigue_find_npc: Callable[..., Any]
    _intrigue_has_control: Callable[..., Any]
    _intrigue_is_imprisoned: Callable[..., Any]
    _intrigue_key: Callable[..., Any]
    _intrigue_members: Callable[..., Any]
    _intrigue_player_faction_id: Callable[..., Any]
    _intrigue_position_specs: Callable[..., Any]
    _intrigue_state: Callable[..., Any]
    _load: Callable[..., Any]
    _player_intrinsic_combat_power: Callable[..., Any]
    _sage_affinity_gain: Callable[..., Any]
    intrigue_rules: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def PLAYER_ID(self) -> Any:
        return self._get_PLAYER_ID()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class IntrigueGuestsDependencies:
    _get_PLAYER_ID: Callable[[], Any]
    _coalition_ids: Callable[..., Any]
    _ensure_intrigue_faction: Callable[..., Any]
    _ensure_intrigue_personality: Callable[..., Any]
    _intrigue_can_invite_guest: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_entity: Callable[..., Any]
    _intrigue_faction_name: Callable[..., Any]
    _intrigue_find_npc: Callable[..., Any]
    _intrigue_guest_npcs: Callable[..., Any]
    _intrigue_has_control: Callable[..., Any]
    _intrigue_is_imprisoned: Callable[..., Any]
    _intrigue_key: Callable[..., Any]
    _intrigue_members: Callable[..., Any]
    _intrigue_player_faction_id: Callable[..., Any]
    _intrigue_player_relation: Callable[..., Any]
    _intrigue_position_specs: Callable[..., Any]
    _intrigue_state: Callable[..., Any]
    _load: Callable[..., Any]
    _npc_faction_id: Callable[..., Any]
    _persist_relationship_npc: Callable[..., Any]
    _sage_affinity_gain: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def PLAYER_ID(self) -> Any:
        return self._get_PLAYER_ID()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class IntriguePresentationDependencies:
    _get_PERSONALITY_LABELS: Callable[[], Any]
    _get_PLAYER_ID: Callable[[], Any]
    _get_RESOLUTION_LABELS: Callable[[], Any]
    _get_STYLE_LABELS: Callable[[], Any]
    _actual_player_realm: Callable[..., Any]
    _all_world_npcs: Callable[..., Any]
    _ensure_intrigue_faction: Callable[..., Any]
    _ensure_intrigue_personality: Callable[..., Any]
    _intrigue_can_invite_guest: Callable[..., Any]
    _intrigue_decision_threshold: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_entity: Callable[..., Any]
    _intrigue_faction_name: Callable[..., Any]
    _intrigue_find_npc: Callable[..., Any]
    _intrigue_has_control: Callable[..., Any]
    _intrigue_has_decision_authority: Callable[..., Any]
    _intrigue_is_imprisoned: Callable[..., Any]
    _intrigue_members: Callable[..., Any]
    _intrigue_player_faction_id: Callable[..., Any]
    _intrigue_player_relation: Callable[..., Any]
    _intrigue_position_specs: Callable[..., Any]
    _intrigue_public_member: Callable[..., Any]
    _intrigue_recruitment_config: Callable[..., Any]
    _intrigue_recruitment_realm_options: Callable[..., Any]
    _intrigue_state: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _npc_root_name: Callable[..., Any]
    _public_guest_invitation: Callable[..., Any]
    _public_intrigue_recruitment: Callable[..., Any]
    _world_supports: Callable[..., Any]

    @property
    def PERSONALITY_LABELS(self) -> Any:
        return self._get_PERSONALITY_LABELS()

    @property
    def PLAYER_ID(self) -> Any:
        return self._get_PLAYER_ID()

    @property
    def RESOLUTION_LABELS(self) -> Any:
        return self._get_RESOLUTION_LABELS()

    @property
    def STYLE_LABELS(self) -> Any:
        return self._get_STYLE_LABELS()


@dataclass(frozen=True, slots=True)
class IntrigueRecruitmentDependencies:
    _get_PLAYER_ID: Callable[[], Any]
    _ensure_intrigue_faction: Callable[..., Any]
    _ensure_intrigue_personality: Callable[..., Any]
    _intrigue_decision_threshold: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_has_decision_authority: Callable[..., Any]
    _intrigue_player_faction_id: Callable[..., Any]
    _intrigue_recruitment_config: Callable[..., Any]
    _intrigue_recruitment_filter_summary: Callable[..., Any]
    _intrigue_recruitment_realm_options: Callable[..., Any]
    _intrigue_resolve: Callable[..., Any]
    _intrigue_state: Callable[..., Any]
    _load: Callable[..., Any]
    _normalize_intrigue_recruitment_filters: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _random_npc_path: Callable[..., Any]
    _random_npc_root: Callable[..., Any]
    _recruit_realm_index: Callable[..., Any]
    _roll_recruit_age_lifespan: Callable[..., Any]
    _sect_members: Callable[..., Any]
    _select_npc_treasure: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def PLAYER_ID(self) -> Any:
        return self._get_PLAYER_ID()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class IntrigueResolutionsDependencies:
    _get_PERSONALITY_LABELS: Callable[[], Any]
    _get_PLAYER_ID: Callable[[], Any]
    _get_RESOLUTION_LABELS: Callable[[], Any]
    _get_STYLE_LABELS: Callable[[], Any]
    _active_war: Callable[..., Any]
    _add_war_participant: Callable[..., Any]
    _append_war_log: Callable[..., Any]
    _ensure_intrigue_faction: Callable[..., Any]
    _ensure_intrigue_personality: Callable[..., Any]
    _generate_intrigue_recruitment_session: Callable[..., Any]
    _intrigue_apply_resolution: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_entity: Callable[..., Any]
    _intrigue_faction_name: Callable[..., Any]
    _intrigue_governance_style: Callable[..., Any]
    _intrigue_guest_npcs: Callable[..., Any]
    _intrigue_has_decision_authority: Callable[..., Any]
    _intrigue_is_imprisoned: Callable[..., Any]
    _intrigue_members: Callable[..., Any]
    _intrigue_player_faction_id: Callable[..., Any]
    _intrigue_resolve: Callable[..., Any]
    _intrigue_state: Callable[..., Any]
    _intrigue_vote_chance: Callable[..., Any]
    _load: Callable[..., Any]
    _normalize_intrigue_recruitment_filters: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _participant_side: Callable[..., Any]
    _set_diplomatic_relation: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def PERSONALITY_LABELS(self) -> Any:
        return self._get_PERSONALITY_LABELS()

    @property
    def PLAYER_ID(self) -> Any:
        return self._get_PLAYER_ID()

    @property
    def RESOLUTION_LABELS(self) -> Any:
        return self._get_RESOLUTION_LABELS()

    @property
    def STYLE_LABELS(self) -> Any:
        return self._get_STYLE_LABELS()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class IntrigueRuntimeDependencies:
    _get_PLAYER_ID: Callable[[], Any]
    _get_RESOLUTION_LABELS: Callable[[], Any]
    _get_STYLE_LABELS: Callable[[], Any]
    _actual_player_realm: Callable[..., Any]
    _all_world_npcs: Callable[..., Any]
    _ensure_intrigue_faction: Callable[..., Any]
    _intrigue_decision_threshold: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_find_npc: Callable[..., Any]
    _intrigue_governance_style: Callable[..., Any]
    _intrigue_has_decision_authority: Callable[..., Any]
    _intrigue_members: Callable[..., Any]
    _intrigue_player_faction_id: Callable[..., Any]
    _intrigue_resolve: Callable[..., Any]
    _intrigue_state: Callable[..., Any]
    _intrigue_sync_player_prison: Callable[..., Any]
    _player_allegiance_race: Callable[..., Any]
    _sect_members: Callable[..., Any]
    _war_relation: Callable[..., Any]
    _world_supports: Callable[..., Any]

    @property
    def PLAYER_ID(self) -> Any:
        return self._get_PLAYER_ID()

    @property
    def RESOLUTION_LABELS(self) -> Any:
        return self._get_RESOLUTION_LABELS()

    @property
    def STYLE_LABELS(self) -> Any:
        return self._get_STYLE_LABELS()


@dataclass(frozen=True, slots=True)
class IntrigueStateDependencies:
    _get_PERSONALITY_LABELS: Callable[[], Any]
    _get_PLAYER_ID: Callable[[], Any]
    _get_STYLE_LABELS: Callable[[], Any]
    _actual_player_realm: Callable[..., Any]
    _all_world_npcs: Callable[..., Any]
    _ensure_intrigue_personality: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _intrigue_auto_appoint_player: Callable[..., Any]
    _intrigue_entity: Callable[..., Any]
    _intrigue_governance_style: Callable[..., Any]
    _intrigue_key: Callable[..., Any]
    _intrigue_members: Callable[..., Any]
    _intrigue_player_faction_id: Callable[..., Any]
    _intrigue_position_specs: Callable[..., Any]
    _intrigue_state: Callable[..., Any]
    _player_allegiance_race: Callable[..., Any]
    _sect_members: Callable[..., Any]
    intrigue_rules: Callable[..., Any]

    @property
    def PERSONALITY_LABELS(self) -> Any:
        return self._get_PERSONALITY_LABELS()

    @property
    def PLAYER_ID(self) -> Any:
        return self._get_PLAYER_ID()

    @property
    def STYLE_LABELS(self) -> Any:
        return self._get_STYLE_LABELS()


@dataclass(frozen=True, slots=True)
class IntrigueDependencies:
    governance: IntrigueGovernanceDependencies
    guests: IntrigueGuestsDependencies
    presentation: IntriguePresentationDependencies
    recruitment: IntrigueRecruitmentDependencies
    resolutions: IntrigueResolutionsDependencies
    runtime: IntrigueRuntimeDependencies
    state: IntrigueStateDependencies
