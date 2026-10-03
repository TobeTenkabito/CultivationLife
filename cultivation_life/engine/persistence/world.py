from __future__ import annotations
from ...models import GameState
from .dependencies import WorldPreparationDependencies


def prepare_world(deps: WorldPreparationDependencies, game: GameState) -> bool:
    changed = False
    before_world_version = game.world_rules_version
    before_roster = {sect_id: tuple(npc.id for npc in sect.npcs) for sect_id, sect in game.sects.items()}
    before_world_npcs = tuple(game.world_npcs)
    deps._ensure_sects(game)
    changed = deps._ensure_world_npcs(game) or changed
    changed = deps._enforce_world_realm_caps(game) or changed
    changed = deps._ensure_npc_formations(game) or changed
    if deps._ensure_sage_state(game):
        changed = True
    if deps._ensure_guixu_state(game):
        changed = True
    if deps._ensure_tianji_state(game):
        changed = True
    if deps._ensure_doctrines(game):
        changed = True
    deps._refresh_sage_effects(game)
    changed = deps._migrate_true_demon_races(game) or changed
    if game.player.faction_id in game.sects:
        sect_allegiance = game.sects[game.player.faction_id].allegiance_race
        if sect_allegiance and game.player.allegiance_race != sect_allegiance:
            game.player.allegiance_race = sect_allegiance
            changed = True
    elif not game.player.allegiance_race:
        game.player.allegiance_race = game.player.lineage_race or game.player.race
        changed = True
    changed = deps._ensure_race_relations(game) or changed
    changed = deps._ensure_sect_relations(game) or changed
    changed = deps._ensure_wars(game) or changed
    changed = deps._compact_world_history(game) or changed
    after_roster = {sect_id: tuple(npc.id for npc in sect.npcs) for sect_id, sect in game.sects.items()}
    changed = (
        changed or after_roster != before_roster or tuple(game.world_npcs) != before_world_npcs
        or game.world_rules_version != before_world_version
    )
    changed = deps._sync_party_state(game) or changed
    changed = deps._sync_relationship_records(game) or changed
    return bool(changed)
