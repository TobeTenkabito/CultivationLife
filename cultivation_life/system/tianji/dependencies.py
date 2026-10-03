"""Named collaborators for independently executable tianji algorithms."""

from dataclasses import dataclass
from typing import Any, Callable

from ...ports import SavePort


@dataclass(frozen=True, slots=True)
class TianjiForgingDependencies:
    _get_SLOT_WEIGHTS: Callable[[], Any]
    _ensure_tianji_state: Callable[..., Any]
    _load: Callable[..., Any]
    _resolve_crafting_selection: Callable[..., Any]
    _scaled_effects: Callable[..., Any]
    _stable_rng: Callable[..., Any]
    _tianji_artifact: Callable[..., Any]
    _tianji_closeness_factor: Callable[..., Any]
    _tianji_config: Callable[..., Any]
    _tianji_material_instance: Callable[..., Any]
    _tianji_public_effect: Callable[..., Any]
    _tianji_reveal: Callable[..., Any]
    _tianji_tag_similarity: Callable[..., Any]
    _tianji_target_preview: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]
    tianji_content_available: Callable[..., Any]

    @property
    def SLOT_WEIGHTS(self) -> Any:
        return self._get_SLOT_WEIGHTS()

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class TianjiGenerationDependencies:
    _get_PRIMITIVES: Callable[[], Any]
    _get_TIANJI_GENERATION_VERSION: Callable[[], Any]
    _next_tianji_buff_name: Callable[..., Any]
    _next_tianji_name: Callable[..., Any]
    _stable_rng: Callable[..., Any]
    _tianji_config: Callable[..., Any]
    _tianji_effect_description: Callable[..., Any]
    _tianji_rule_effects: Callable[..., Any]

    @property
    def PRIMITIVES(self) -> Any:
        return self._get_PRIMITIVES()

    @property
    def TIANJI_GENERATION_VERSION(self) -> Any:
        return self._get_TIANJI_GENERATION_VERSION()


@dataclass(frozen=True, slots=True)
class TianjiIntelligenceDependencies:
    _ensure_tianji_state: Callable[..., Any]
    _load: Callable[..., Any]
    _tianji_artifact: Callable[..., Any]
    _tianji_config: Callable[..., Any]
    _tianji_reveal: Callable[..., Any]
    present: Callable[..., Any]
    _get_store: Callable[[], SavePort]
    tianji_content_available: Callable[..., Any]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class TianjiNpcsDependencies:
    _ensure_tianji_state: Callable[..., Any]
    _scaled_effects: Callable[..., Any]
    _stable_rng: Callable[..., Any]
    _tianji_artifact: Callable[..., Any]
    _tianji_config: Callable[..., Any]
    _tianji_persistent_npcs: Callable[..., Any]
    _tianji_reveal: Callable[..., Any]
    tianji_content_available: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class TianjiPresentationDependencies:
    _ensure_tianji_state: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _load: Callable[..., Any]
    _natal_artifact_candidate: Callable[..., Any]
    _tianji_config: Callable[..., Any]
    _tianji_public_effect: Callable[..., Any]
    tianji_content_available: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class TianjiStateDependencies:
    _get_PRIMITIVES: Callable[[], Any]
    _get_TIANJI_GENERATION_VERSION: Callable[[], Any]
    _get_TIANJI_WINDOW_SCHEDULES: Callable[[], Any]
    _assign_tianji_holders_for_world: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _generate_tianji_artifacts: Callable[..., Any]
    _generate_tianji_materials: Callable[..., Any]
    _next_tianji_buff_name: Callable[..., Any]
    _next_tianji_name: Callable[..., Any]
    _refresh_tianji_artifact_names: Callable[..., Any]
    _refresh_tianji_buff_names: Callable[..., Any]
    _stable_rng: Callable[..., Any]
    _tianji_config: Callable[..., Any]
    tianji_content_available: Callable[..., Any]

    @property
    def PRIMITIVES(self) -> Any:
        return self._get_PRIMITIVES()

    @property
    def TIANJI_GENERATION_VERSION(self) -> Any:
        return self._get_TIANJI_GENERATION_VERSION()

    @property
    def TIANJI_WINDOW_SCHEDULES(self) -> Any:
        return self._get_TIANJI_WINDOW_SCHEDULES()


@dataclass(frozen=True, slots=True)
class TianjiDependencies:
    forging: TianjiForgingDependencies
    generation: TianjiGenerationDependencies
    intelligence: TianjiIntelligenceDependencies
    npcs: TianjiNpcsDependencies
    presentation: TianjiPresentationDependencies
    state: TianjiStateDependencies
