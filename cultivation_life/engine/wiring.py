"""Composition root: select explicit builders for each engine responsibility."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from .dependencies import EngineDependencies, NpcClassDependencies
from ..system.court import wiring as court_wiring
from .composition import actions, asura, combat, contacts, events, lifecycle, presentation, world

if TYPE_CHECKING:
    from . import GameEngine


def bind_dependencies(
    engine: GameEngine, *, bloodline_content_available: Callable[[], bool],
) -> EngineDependencies:
    """Resolve callbacks and resource getters on use, preserving late overrides."""
    return EngineDependencies(
        court_state=court_wiring.bind_state(engine),
        court_governance=court_wiring.bind_governance(engine),
        court_lifecycle=court_wiring.bind_lifecycle(engine),
        court_yaochi=court_wiring.bind_yaochi(engine),
        npc_contacts=contacts.bind_contacts(engine),
        asura_actions=asura.bind_asura_actions(engine),
        asura_trials=asura.bind_asura_trials(engine),
        immortal_trials=combat.bind_immortal_trials(engine),
        world_runtime=lifecycle.bind_world_runtime(engine),
        event_runtime=events.bind_event_runtime(engine),
        combat_runtime=combat.bind_combat_runtime(engine),
        presentation_runtime=presentation.bind_presentation_runtime(engine),
        persistence_runtime=lifecycle.bind_persistence_runtime(engine, bloodline_content_available=bloodline_content_available),
        session=lifecycle.bind_session(engine, bloodline_content_available=bloodline_content_available),
        advancement=lifecycle.bind_advancement(engine),
        cultivation_actions=actions.bind_cultivation_actions(engine, bloodline_content_available=bloodline_content_available),
        world_travel_actions=actions.bind_world_travel_actions(engine),
        faction_actions=actions.bind_faction_actions(engine),
        encounter_actions=actions.bind_encounter_actions(engine),
        inventory_actions=actions.bind_inventory_actions(engine, bloodline_content_available=bloodline_content_available),
        relationship_actions=actions.bind_relationship_actions(engine),
        choices=events.bind_choices(engine),
        breakthroughs=combat.bind_breakthroughs(engine, bloodline_content_available=bloodline_content_available),
        trials=combat.bind_trials(engine),
        encounters=events.bind_encounters(engine),
        effects=events.bind_effects(engine),
        npcs=world.bind_npcs(engine),
        world_relationships=world.bind_world_relationships(engine, bloodline_content_available=bloodline_content_available),
        world_factions=world.bind_world_factions(engine),
        hostility=world.bind_hostility(engine),
        character_view=presentation.bind_character_view(engine, bloodline_content_available=bloodline_content_available),
        world_view=presentation.bind_world_view(engine),
        faction_view=presentation.bind_faction_view(engine),
    )


def bind_npc_class_dependencies(engine_class: type[GameEngine]) -> NpcClassDependencies:
    return NpcClassDependencies(
        _npc_lifespan_multiplier=lambda *args, **kwargs: engine_class._npc_lifespan_multiplier(*args, **kwargs),
    )
