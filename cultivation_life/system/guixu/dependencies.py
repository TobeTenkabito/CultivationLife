"""Named dependencies for independently testable algorithms."""
from dataclasses import dataclass
from typing import Any, Callable
from ...ports import SavePort, MapPort
from ...models import GameState


@dataclass(frozen=True, slots=True)
class GuixuStateDependencies:
    _guixu_definitions: Callable[..., Any]
    _load: Callable[[str], GameState]
    _next_guixu_open: Callable[..., Any]
    guixu_content_available: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class GuixuCalendarDependencies:
    _announce_guixu_cycle: Callable[..., Any]
    _assign_due_guixu_entries: Callable[..., Any]
    _close_guixu_cycle: Callable[..., Any]
    _ensure_guixu_state: Callable[..., Any]
    _form_guixu_npc_teams: Callable[..., Any]
    _generate_guixu_roster: Callable[..., Any]
    _guixu_definitions: Callable[..., Any]
    _guixu_elapsed_days: Callable[..., Any]
    _guixu_entry_definition: Callable[..., Any]
    _guixu_settings: Callable[..., Any]
    _guixu_weighted_key: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _open_guixu_cycle: Callable[..., Any]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _get_maps: Callable[[], MapPort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class GuixuNpcsDependencies:
    _all_world_npcs: Callable[..., Any]
    _dissolve_guixu_npc_team: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _form_guixu_npc_teams: Callable[..., Any]
    _guixu_entry_definition: Callable[..., Any]
    _guixu_npc_claim_entry: Callable[..., Any]
    _guixu_relation_ids: Callable[..., Any]
    _guixu_settings: Callable[..., Any]
    _npc_power: Callable[..., Any]
    _resolve_guixu_npc_kill: Callable[..., Any]
    _simulate_guixu_npc_conflict: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class GuixuRewardsDependencies:
    _dissolve_guixu_npc_team: Callable[..., Any]
    _guixu_entry_definition: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class GuixuEncountersDependencies:
    _break_guixu_relationship: Callable[..., Any]
    _combat: Callable[..., Any]
    _consume_guixu_days: Callable[..., Any]
    _dissolve_guixu_npc_team: Callable[..., Any]
    _guixu_active_team: Callable[..., Any]
    _guixu_fight: Callable[..., Any]
    _guixu_grant_entry: Callable[..., Any]
    _guixu_relationship_role: Callable[..., Any]
    _guixu_settings: Callable[..., Any]
    _guixu_transferable_player_entries: Callable[..., Any]



@dataclass(frozen=True, slots=True)
class GuixuActionsDependencies:
    _add_opportunity: Callable[..., Any]
    _advance_soul_erosion_time: Callable[..., Any]
    _advance_world_year: Callable[..., Any]
    _apply_action_resources: Callable[..., Any]
    _body_progress_required: Callable[..., Any]
    _body_training_step: Callable[..., Any]
    _consume_guixu_days: Callable[..., Any]
    _dissolve_guixu_npc_team: Callable[..., Any]
    _ensure_guixu_state: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _guixu_actor: Callable[..., Any]
    _guixu_cycle_and_definition: Callable[..., Any]
    _guixu_elapsed_days: Callable[..., Any]
    _guixu_entry_definition: Callable[..., Any]
    _guixu_fight: Callable[..., Any]
    _guixu_grant_entry: Callable[..., Any]
    _guixu_offer_team: Callable[..., Any]
    _guixu_relationship_role: Callable[..., Any]
    _guixu_return_days: Callable[..., Any]
    _guixu_settings: Callable[..., Any]
    _guixu_team_tick: Callable[..., Any]
    _guixu_transferable_player_entries: Callable[..., Any]
    _load: Callable[[str], GameState]
    _maybe_guixu_npc_threat: Callable[..., Any]
    _sense_training_step: Callable[..., Any]
    _surrender_guixu_treasure: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    decode_rng: Callable[..., Any]
    guixu_content_available: Callable[..., Any]
    _get_MOVE_COSTS: Callable[[], Any]

    @property
    def store(self) -> SavePort:
        return self._get_store()

    @property
    def MOVE_COSTS(self) -> Any:
        return self._get_MOVE_COSTS()


@dataclass(frozen=True, slots=True)
class GuixuPresentationDependencies:
    _ensure_guixu_state: Callable[..., Any]
    _guixu_cycle_and_definition: Callable[..., Any]
    _guixu_definitions: Callable[..., Any]
    _guixu_entry_definition: Callable[..., Any]
    _guixu_return_days: Callable[..., Any]
    _guixu_transferable_player_entries: Callable[..., Any]
    _npc_realm_name: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    guixu_content_available: Callable[..., Any]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class GuixuDependencies:
    state: GuixuStateDependencies
    calendar: GuixuCalendarDependencies
    npcs: GuixuNpcsDependencies
    rewards: GuixuRewardsDependencies
    encounters: GuixuEncountersDependencies
    actions: GuixuActionsDependencies
    presentation: GuixuPresentationDependencies
