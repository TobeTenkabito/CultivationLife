"""Named ports for relationships workflows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...models import GameState
from ...ports import SavePort


@dataclass(frozen=True, slots=True)
class CaptivityDependencies:
    _break_capture_relationship: Callable[..., Any]
    _convert_to_puppet: Callable[..., Any]
    _demonic_rules: Callable[..., Any]
    _die: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _load: Callable[[str], GameState]
    _npc_realm_name: Callable[..., Any]
    _player_intrinsic_combat_power: Callable[..., Any]
    _relationship_combat_power: Callable[..., Any]
    _remove_conversion_target: Callable[..., Any]
    _restore_captive_npc: Callable[..., Any]
    _stable_gender: Callable[..., Any]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    present: Callable[[GameState], dict[str, Any]]
    relationship_violence: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class RelationshipSanctionDependencies:
    _end_sanctioned_relationship: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _record_revenge_trigger: Callable[..., Any]
    _relationship_sanction_candidates: Callable[..., Any]
    _sage_scaled_gain: Callable[..., Any]
    _set_person_affinity: Callable[..., Any]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()


@dataclass(frozen=True, slots=True)
class DependentLifecycleDependencies:
    _all_world_npcs: Callable[..., Any]
    _default_npc_main_technique: Callable[..., Any]
    _escape_chance: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _instantiate_event: Callable[..., Any]
    _load: Callable[[str], GameState]
    _npc_power: Callable[..., Any]
    _npc_realm_name: Callable[..., Any]
    _owner_equipment_candidates: Callable[..., Any]
    _owner_request_chance: Callable[..., Any]
    _owner_technique_candidates: Callable[..., Any]
    _proposal_revenge_chance: Callable[..., Any]
    _rank: Callable[..., Any]
    _record_revenge_trigger: Callable[..., Any]
    _revenge_ready: Callable[..., Any]
    _runtime_from_status: Callable[..., Any]
    _set_concubine_status: Callable[..., Any]
    _world_realm_cap: Callable[..., Any]
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class ConcubineActionDependencies:
    _add_opportunity: Callable[..., Any]
    _concubine_target: Callable[..., Any]
    _convert_to_puppet: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _load: Callable[[str], GameState]
    _normalize_concubine: Callable[..., Any]
    _rank: Callable[..., Any]
    _set_person_affinity: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class RelationshipViolenceDependencies:
    _apply_cultivator_kill: Callable[..., Any]
    _combat: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _load: Callable[[str], GameState]
    _npc_power: Callable[..., Any]
    _promote_cached_npc: Callable[..., Any]
    _public_party: Callable[..., Any]
    assert_buddhist_operation_allowed: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class RelationshipFlowDependencies:
    captivity: CaptivityDependencies
    sanctions: RelationshipSanctionDependencies
    dependents: DependentLifecycleDependencies
    concubines: ConcubineActionDependencies
    violence: RelationshipViolenceDependencies

