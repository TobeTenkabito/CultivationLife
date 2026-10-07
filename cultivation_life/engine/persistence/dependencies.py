"""Capabilities for each ordered preparation stage; no storage access."""
from dataclasses import dataclass
from typing import Any, Callable
from ...models import GameState
from ...ports import MapPort


@dataclass(frozen=True, slots=True)
class FoundationsPreparationDependencies:
    _ensure_merchant: Callable[..., bool]



@dataclass(frozen=True, slots=True)
class VitalityPreparationDependencies:
    _die: Callable[..., None]



@dataclass(frozen=True, slots=True)
class CharacterPreparationDependencies:
    _body_progress_required: Callable[..., float]
    _clear_market: Callable[..., None]
    _cultivation_sense_requirement: Callable[..., int]
    _manual_breakthrough_kind: Callable[..., str | None]
    _manual_minor_layers: Callable[..., set[int]]
    bloodline_content_available: Callable[[], bool]
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class WorldPreparationDependencies:
    _compact_world_history: Callable[..., bool]
    _enforce_world_realm_caps: Callable[..., bool]
    _ensure_doctrines: Callable[..., bool]
    _ensure_guixu_state: Callable[..., bool]
    _ensure_npc_formations: Callable[..., bool]
    _ensure_race_relations: Callable[..., bool]
    _ensure_sage_state: Callable[..., bool]
    _ensure_sect_relations: Callable[..., bool]
    _ensure_sects: Callable[..., None]
    _ensure_tianji_state: Callable[..., bool]
    _ensure_wars: Callable[..., bool]
    _ensure_world_npcs: Callable[..., bool]
    _migrate_true_demon_races: Callable[..., bool]
    _refresh_sage_effects: Callable[..., None]
    _sync_party_state: Callable[..., bool]
    _sync_relationship_records: Callable[..., bool]



@dataclass(frozen=True, slots=True)
class ServicesPreparationDependencies:
    _ensure_buddhist_state: Callable[[GameState], None]
    _ensure_heavenly_court: Callable[..., bool]
    _ensure_market: Callable[..., bool]
    _ensure_natal_artifact: Callable[..., bool]



@dataclass(frozen=True, slots=True)
class EventsPreparationDependencies:
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _condition: Callable[..., bool]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()
