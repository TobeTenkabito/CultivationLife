"""Named dependency builders for lifecycle."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..persistence.dependencies import (
    FoundationsPreparationDependencies,
    VitalityPreparationDependencies,
    CharacterPreparationDependencies,
    WorldPreparationDependencies,
    ServicesPreparationDependencies,
    EventsPreparationDependencies,
)

from .travel import bind_elapsed_year, bind_settlement

from ..dependencies import (
    WorldRuntimeDependencies,
    PersistenceDependencies,
    SessionDependencies,
    AdvancementDependencies,
)

if TYPE_CHECKING:
    from .. import GameEngine


def bind_world_runtime(engine: GameEngine) -> WorldRuntimeDependencies:
    return WorldRuntimeDependencies(
        _compact_sect_roster=lambda *args, **kwargs: engine._compact_sect_roster(*args, **kwargs),
        _new_sects=lambda *args, **kwargs: engine._new_sects(*args, **kwargs),
        _new_world_npcs=lambda *args, **kwargs: engine._new_world_npcs(*args, **kwargs),
        _random_npc_path=lambda *args, **kwargs: engine._random_npc_path(*args, **kwargs),
        _random_npc_root=lambda *args, **kwargs: engine._random_npc_root(*args, **kwargs),
        _select_npc_treasure=lambda *args, **kwargs: engine._select_npc_treasure(*args, **kwargs),
        _world_realm_cap=lambda *args, **kwargs: engine._world_realm_cap(*args, **kwargs),
    )


def bind_persistence_runtime(engine: GameEngine, *, bloodline_content_available: Callable[[], bool]) -> PersistenceDependencies:
    return PersistenceDependencies(
        foundations=FoundationsPreparationDependencies(
            _ensure_merchant=lambda *args, **kwargs: engine._ensure_merchant(*args, **kwargs),
        ),
        vitality=VitalityPreparationDependencies(
            _die=lambda *args, **kwargs: engine._die(*args, **kwargs),
        ),
        character=CharacterPreparationDependencies(
            _body_progress_required=lambda *args, **kwargs: engine._body_progress_required(*args, **kwargs),
            _clear_market=lambda *args, **kwargs: engine._clear_market(*args, **kwargs),
            _cultivation_sense_requirement=lambda *args, **kwargs: engine._cultivation_sense_requirement(*args, **kwargs),
            _manual_breakthrough_kind=lambda *args, **kwargs: engine._manual_breakthrough_kind(*args, **kwargs),
            _manual_minor_layers=lambda *args, **kwargs: engine._manual_minor_layers(*args, **kwargs),
            bloodline_content_available=bloodline_content_available,
            _get_maps=lambda: engine.maps,
        ),
        world=WorldPreparationDependencies(
            _compact_world_history=lambda *args, **kwargs: engine._compact_world_history(*args, **kwargs),
            _enforce_world_realm_caps=lambda *args, **kwargs: engine._enforce_world_realm_caps(*args, **kwargs),
            _ensure_doctrines=lambda *args, **kwargs: engine._ensure_doctrines(*args, **kwargs),
            _ensure_guixu_state=lambda *args, **kwargs: engine._ensure_guixu_state(*args, **kwargs),
            _ensure_npc_formations=lambda *args, **kwargs: engine._ensure_npc_formations(*args, **kwargs),
            _ensure_race_relations=lambda *args, **kwargs: engine._ensure_race_relations(*args, **kwargs),
            _ensure_sage_state=lambda *args, **kwargs: engine._ensure_sage_state(*args, **kwargs),
            _ensure_sect_relations=lambda *args, **kwargs: engine._ensure_sect_relations(*args, **kwargs),
            _ensure_sects=lambda *args, **kwargs: engine._ensure_sects(*args, **kwargs),
            _ensure_tianji_state=lambda *args, **kwargs: engine._ensure_tianji_state(*args, **kwargs),
            _ensure_wars=lambda *args, **kwargs: engine._ensure_wars(*args, **kwargs),
            _ensure_world_npcs=lambda *args, **kwargs: engine._ensure_world_npcs(*args, **kwargs),
            _migrate_true_demon_races=lambda *args, **kwargs: engine._migrate_true_demon_races(*args, **kwargs),
            _refresh_sage_effects=lambda *args, **kwargs: engine._refresh_sage_effects(*args, **kwargs),
            _sync_party_state=lambda *args, **kwargs: engine._sync_party_state(*args, **kwargs),
            _sync_relationship_records=lambda *args, **kwargs: engine._sync_relationship_records(*args, **kwargs),
        ),
        services=ServicesPreparationDependencies(
            _ensure_buddhist_state=lambda *args, **kwargs: engine._ensure_buddhist_state(*args, **kwargs),
            _ensure_heavenly_court=lambda *args, **kwargs: engine._ensure_heavenly_court(*args, **kwargs),
            _ensure_market=lambda *args, **kwargs: engine._ensure_market(*args, **kwargs),
            _ensure_natal_artifact=lambda *args, **kwargs: engine._ensure_natal_artifact(*args, **kwargs),
        ),
        events=EventsPreparationDependencies(
            _get_events_by_id=lambda: engine.events_by_id,
        ),
        _get_store=lambda: engine.store,
    )


def bind_session(engine: GameEngine, *, bloodline_content_available: Callable[[], bool]) -> SessionDependencies:
    return SessionDependencies(
        _base_affinities=lambda *args, **kwargs: engine._base_affinities(*args, **kwargs),
        _cultivation_sense_requirement=lambda *args, **kwargs: engine._cultivation_sense_requirement(*args, **kwargs),
        _ensure_ghost_parade=lambda *args, **kwargs: engine._ensure_ghost_parade(*args, **kwargs),
        _ensure_guixu_state=lambda *args, **kwargs: engine._ensure_guixu_state(*args, **kwargs),
        _ensure_heavenly_court=lambda *args, **kwargs: engine._ensure_heavenly_court(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: engine._ensure_market(*args, **kwargs),
        _ensure_npc_formations=lambda *args, **kwargs: engine._ensure_npc_formations(*args, **kwargs),
        _ensure_race_relations=lambda *args, **kwargs: engine._ensure_race_relations(*args, **kwargs),
        _ensure_sage_state=lambda *args, **kwargs: engine._ensure_sage_state(*args, **kwargs),
        _ensure_sect_relations=lambda *args, **kwargs: engine._ensure_sect_relations(*args, **kwargs),
        _ensure_sects=lambda *args, **kwargs: engine._ensure_sects(*args, **kwargs),
        _ensure_tianji_state=lambda *args, **kwargs: engine._ensure_tianji_state(*args, **kwargs),
        _ensure_doctrines=lambda *args, **kwargs: engine._ensure_doctrines(*args, **kwargs),
        _ensure_world_npcs=lambda *args, **kwargs: engine._ensure_world_npcs(*args, **kwargs),
        _new_sects=lambda *args, **kwargs: engine._new_sects(*args, **kwargs),
        _new_world_npcs=lambda *args, **kwargs: engine._new_world_npcs(*args, **kwargs),
        _npc_realm_name=lambda *args, **kwargs: engine._npc_realm_name(*args, **kwargs),
        _get_achievements=lambda: engine.achievements,
        _get_maps=lambda: engine.maps,
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
        bloodline_content_available=bloodline_content_available,
    )


def bind_advancement(engine: GameEngine) -> AdvancementDependencies:
    from ...system.heavens.cultivation import activity_gain
    from ...system.heavens.calendar import take_pause
    return AdvancementDependencies(
        heavens_activity_gain=lambda game, gain, action: activity_gain(engine._dependencies.heavens, game, gain, action),
        heavens_take_pause=take_pause,
        _spatial_training=lambda *args, **kwargs: engine._spatial_training(*args, **kwargs),
        year=bind_elapsed_year(engine),
        settlement=bind_settlement(engine),
        _begin_doctrine_action=lambda *args, **kwargs: engine._begin_doctrine_action(*args, **kwargs),
        _begin_yaochi_action=lambda *args, **kwargs: engine._begin_yaochi_action(*args, **kwargs),
        _finish_yaochi_action=lambda *args, **kwargs: engine._finish_yaochi_action(*args, **kwargs),
        _finish_doctrine_action=lambda *args, **kwargs: engine._finish_doctrine_action(*args, **kwargs),
        _add_opportunity=lambda *args, **kwargs: engine._add_opportunity(*args, **kwargs),
        _apply_action_resources=lambda *args, **kwargs: engine._apply_action_resources(*args, **kwargs),
        _body_progress_required=lambda *args, **kwargs: engine._body_progress_required(*args, **kwargs),
        _body_training_step=lambda *args, **kwargs: engine._body_training_step(*args, **kwargs),
        _commission_step=lambda *args, **kwargs: engine._commission_step(*args, **kwargs),
        _compact_world_history=lambda *args, **kwargs: engine._compact_world_history(*args, **kwargs),
        _condense_action_results=lambda *args, **kwargs: engine._condense_action_results(*args, **kwargs),
        _court_law_active=lambda *args, **kwargs: engine._court_law_active(*args, **kwargs),
        _ensure_market=lambda *args, **kwargs: engine._ensure_market(*args, **kwargs),
        _finish_sage_action=lambda *args, **kwargs: engine._finish_sage_action(*args, **kwargs),
        _guixu_trapped_training=lambda *args, **kwargs: engine._guixu_trapped_training(*args, **kwargs),
        _instantiate_event=lambda *args, **kwargs: engine._instantiate_event(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _market_tier=lambda *args, **kwargs: engine._market_tier(*args, **kwargs),
        _maybe_affinity_gift=lambda *args, **kwargs: engine._maybe_affinity_gift(*args, **kwargs),
        _maybe_concubine_proposal=lambda *args, **kwargs: engine._maybe_concubine_proposal(*args, **kwargs),
        _maybe_faction_event=lambda *args, **kwargs: engine._maybe_faction_event(*args, **kwargs),
        _maybe_founded_sect_pressure=lambda *args, **kwargs: engine._maybe_founded_sect_pressure(*args, **kwargs),
        _maybe_immortal_conversion_event=lambda *args, **kwargs: engine._maybe_immortal_conversion_event(*args, **kwargs),
        _maybe_personal_revenge=lambda *args, **kwargs: engine._maybe_personal_revenge(*args, **kwargs),
        _maybe_probability_story_event=lambda *args, **kwargs: engine._maybe_probability_story_event(*args, **kwargs),
        _maybe_relationship_sanction=lambda *args, **kwargs: engine._maybe_relationship_sanction(*args, **kwargs),
        _maybe_xiang_node_event=lambda *args, **kwargs: engine._maybe_xiang_node_event(*args, **kwargs),
        _personal_combat_step=lambda *args, **kwargs: engine._personal_combat_step(*args, **kwargs),
        _prepare_sage_action=lambda *args, **kwargs: engine._prepare_sage_action(*args, **kwargs),
        _prepare_treasure_reward_event=lambda *args, **kwargs: engine._prepare_treasure_reward_event(*args, **kwargs),
        _queue_followup_event=lambda *args, **kwargs: engine._queue_followup_event(*args, **kwargs),
        _select_event=lambda *args, **kwargs: engine._select_event(*args, **kwargs),
        _sense_training_step=lambda *args, **kwargs: engine._sense_training_step(*args, **kwargs),
        _treasure_step=lambda *args, **kwargs: engine._treasure_step(*args, **kwargs),
        _get_maps=lambda: engine.maps,
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        _get_store=lambda: engine.store,
    )
