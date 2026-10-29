"""Capabilities for each ordered preparation stage; no storage access."""
from dataclasses import dataclass
from random import Random
from typing import Any, Callable
from ...models import GameState, Player
from ...ports import MapPort
from ...time_dependencies import DeathPort


@dataclass(frozen=True, slots=True)
class FoundationsPreparationDependencies:
    _ensure_merchant: Callable[[GameState], bool]



@dataclass(frozen=True, slots=True)
class VitalityPreparationDependencies:
    _die: DeathPort



@dataclass(frozen=True, slots=True)
class CharacterPreparationDependencies:
    _body_progress_required: Callable[[Player], float]
    _clear_market: Callable[[GameState], None]
    _cultivation_sense_requirement: Callable[[int, int], int]
    _manual_breakthrough_kind: Callable[[Player], str | None]
    _manual_minor_layers: Callable[[Player], set[int]]
    bloodline_content_available: Callable[[], bool]
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


@dataclass(frozen=True, slots=True)
class WorldPreparationDependencies:
    _compact_world_history: Callable[[GameState], bool]
    _enforce_world_realm_caps: Callable[[GameState], bool]
    _ensure_doctrines: Callable[[GameState], bool]
    _ensure_guixu_state: Callable[[GameState], bool]
    _ensure_npc_formations: Callable[[GameState], bool]
    _ensure_race_relations: Callable[[GameState], bool]
    _ensure_sage_state: Callable[[GameState], bool]
    _ensure_sect_relations: Callable[[GameState], bool]
    _ensure_sects: Callable[[GameState], None]
    _ensure_tianji_state: Callable[[GameState], bool]
    _ensure_wars: Callable[[GameState], bool]
    _ensure_world_npcs: Callable[[GameState], bool]
    _migrate_true_demon_races: Callable[[GameState], bool]
    _refresh_sage_effects: Callable[[GameState], None]
    _sync_party_state: Callable[[GameState], bool]
    _sync_relationship_records: Callable[[GameState], bool]



@dataclass(frozen=True, slots=True)
class ServicesPreparationDependencies:
    _ensure_buddhist_state: Callable[[GameState], None]
    _ensure_heavenly_court: Callable[[GameState, Random], bool]
    _ensure_market: Callable[[GameState, Random], bool]
    _ensure_natal_artifact: Callable[[GameState], bool]



@dataclass(frozen=True, slots=True)
class EventsPreparationDependencies:
    _get_events_by_id: Callable[[], dict[str, dict[str, Any]]]
    _condition: Callable[[dict[str, Any], GameState], bool]

    @property
    def events_by_id(self) -> dict[str, dict[str, Any]]:
        return self._get_events_by_id()
