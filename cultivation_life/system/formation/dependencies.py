"""Named dependencies for independently testable algorithms."""

from dataclasses import dataclass
from typing import Any, Callable
from ...models import GameState
from ...ports import SavePort, MapPort


@dataclass(frozen=True, slots=True)
class FormationMarketDependencies:
    _formation_maintenance_defs: Callable[..., Any]
    _formation_material_defs: Callable[..., Any]
    _formation_rules: Callable[..., Any]
    make_formation_material_instance: Callable[..., Any]
    _get_NATURE_NAMES: Callable[[], Any]

    @property
    def NATURE_NAMES(self) -> Any:
        return self._get_NATURE_NAMES()


@dataclass(frozen=True, slots=True)
class FormationLoadoutsDependencies:
    _activate_loadout: Callable[..., Any]
    _extract_candidate: Callable[..., Any]
    _formation_candidate: Callable[..., Any]
    _formation_candidates: Callable[..., Any]
    _formation_material_defs: Callable[..., Any]
    _load: Callable[[str], GameState]
    _nodes_from_candidate_ids: Callable[..., Any]
    _release_active_formation: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    _profile_from_bindings: Callable[..., Any]
    active_formation_profile: Callable[..., Any]
    calculate_formation_profile: Callable[..., Any]
    ensure_formation_state: Callable[..., Any]
    formation_alpha: Callable[..., Any]
    formation_shared_definitions: Callable[..., Any]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class FormationGroundDependencies:
    _coalition_ids: Callable[..., Any]
    _formation_maintenance_defs: Callable[..., Any]
    _formation_rules: Callable[..., Any]
    _ground_array_public: Callable[..., Any]
    _ground_profile: Callable[..., Any]
    _has_sect_voice: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_has_control: Callable[..., Any]
    _load: Callable[[str], GameState]
    _release_bindings: Callable[..., Any]
    _require_ground_array_access: Callable[..., Any]
    _sect_guard_array: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    active_formation_profile: Callable[..., Any]
    ensure_formation_state: Callable[..., Any]
    ground_formation_power: Callable[..., Any]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class FormationNpcsDependencies:
    _all_world_npcs: Callable[..., Any]
    _formation_material_defs: Callable[..., Any]
    _formation_rules: Callable[..., Any]
    _npc_formation_profile: Callable[..., Any]
    _cached_npc_formation_profile: Callable[..., Any]
    empty_formation_profile: Callable[..., Any]
    _get_NATURE_NAMES: Callable[[], Any]

    @property
    def NATURE_NAMES(self) -> Any:
        return self._get_NATURE_NAMES()


@dataclass(frozen=True, slots=True)
class FormationPresentationDependencies:
    _formation_candidates: Callable[..., Any]
    _formation_maintenance_defs: Callable[..., Any]
    _ground_array_public: Callable[..., Any]
    _has_sect_voice: Callable[..., Any]
    _intrigue_enabled: Callable[..., Any]
    _intrigue_has_control: Callable[..., Any]
    _get_maps: Callable[[], MapPort]
    active_formation_profile: Callable[..., Any]
    ensure_formation_state: Callable[..., Any]
    formation_alpha: Callable[..., Any]
    formation_config: Callable[..., Any]
    formation_level: Callable[..., Any]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class FormationDependencies:
    market: FormationMarketDependencies
    loadouts: FormationLoadoutsDependencies
    ground: FormationGroundDependencies
    npcs: FormationNpcsDependencies
    presentation: FormationPresentationDependencies
