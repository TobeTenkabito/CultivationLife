"""Save-state adapter for celestial doctrine sources, shared by both battle callers."""
from __future__ import annotations

from ..combat.contracts import CapabilitySource
from ..combat.npc_lifecycle import read
from .generation import rng_for
from .progression import source

from .state import (
    config as config,
    ensure as ensure,
    player_record as player_record,
)


from .npc_progression import record as _npc_record


def battle_sources(game, owners) -> dict[str, CapabilitySource]:
    # Do not generate a celestial catalog for unrelated lower-world battles.
    ensure(game, celestial_context=any(read(owner, "world") == "celestial" and read(owner, "transcendence") for owner in owners.values()))
    from ..spirit_voisinage import player_source, npc_source, diminished
    from ..aperture_resources import lower_world
    definitions = game.doctrine_state.get("definitions", {})
    results = {}
    for key, owner in owners.items():
        if key == 'player':
            from ..asura import source as asura_source
            asura_value = asura_source(game.player)
            if asura_value.voisinages:
                results[key] = asura_value
                continue
            from ..upper_voisinage_rules import available, player_source as upper_source
            if available(game.player):
                results[key] = upper_source(game.player)
                continue
        if key == 'player' and lower_world(game.player):
            value = player_source(game)
            if value.voisinages:
                results[key] = value
            continue
        if key != 'player' and lower_world(game.player):
            spirit = npc_source(game, owner)
            if spirit.voisinages:
                results[key] = spirit
                continue
        if key!='player':
            from ..npc_development.domains import source as trained_source
            trained=trained_source(owner)
            if trained.voisinages:
                results[key]=trained
                continue
        record = player_record(game) if key == "player" else _npc_record(game, owner)
        if record:
            domain_world = 'celestial' if lower_world(game.player) else read(owner, 'world')
            value = source(record, definitions, domain_world, training_gain=config()["cultivation"]["voisinage_training_gain"])
            if lower_world(game.player):
                value = diminished(value)
            if value.voisinages:
                results[key] = value
    from ..combat_loadout import project_loadout
    from ..tianji_system import tianji_content_available
    held = {}
    if tianji_content_available():
        definitions_by_id = {d['id']: d for d in game.tianji_state.get('artifacts', ())}
        for artifact_id, holder in game.tianji_state.get('holders', {}).items():
            npc_id = holder.get('npc_id')
            if npc_id and artifact_id in definitions_by_id:
                held.setdefault(npc_id, []).append(definitions_by_id[artifact_id])
    for key, owner in owners.items():
        value = project_loadout(game, owner, results.get(key), player=key == 'player', tianji_artifacts=held.get(read(owner, 'id'), ()))
        if (value.voisinages or value.technique_tier > 1 or value.artifact_tier > 1
                or value.passive_ward_tier == 2 or value.interventions or value.semantic_rules):
            results[key] = value
    return results


def conversion_state(player):
    from ..aperture_resources import energy_state
    return energy_state(player)
