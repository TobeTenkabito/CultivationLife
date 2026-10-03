"""Explicit life/custody/roster transitions, without gameplay or engine imports.

Held people leave free simulation containers but retain their identity. Only
kill_person may end their life; release never revives or copies a stale snapshot.
"""
from __future__ import annotations

import copy

from .relationship_records import bind_relationship, find_person
from .relationship_schema import person_seed


def is_free(person):
    if isinstance(person, dict):
        return bool(person.get('alive', True) and person.get('roster_state', 'active') == 'active')
    return bool(person.alive and person.roster_state == 'active')


def sync_offspring(game, npc):
    # Family growth records still have their own lifecycle. Never let that
    # snapshot re-enrol a held/dead person or undo a release.
    for child in game.player.offspring:
        if str(child.get('id')) == npc.id:
            child.update(npc.to_dict())


def _detach(game, npc):
    origins = []
    for field in ('world_npcs', 'notable_npcs', 'relationship_npcs'):
        registry = getattr(game, field)
        if npc.id in registry:
            del registry[npc.id]
            origins.append({'container': field})
    for kind, group in [('family', game.family), *[('sect', sect) for sect in game.sects.values()]]:
        if group is None:
            continue
        positions = [index for index, entry in enumerate(group.npcs) if entry.id == npc.id]
        if positions:
            origins.append({'container': kind, 'id': group.id, 'index': positions[0]})
            group.npcs[:] = [entry for entry in group.npcs if entry.id != npc.id]
    game.encounter_npc_cache[:] = [row for row in game.encounter_npc_cache if row.get('id') != npc.id]
    game.player.party[:] = [row for row in game.player.party if row.get('id') != npc.id]
    return origins


def detain_person(game, seed, npc_type, *, kind='prisoner'):
    if kind not in {'prisoner', 'concubine', 'living_puppet'}:
        raise ValueError('未知人物拘禁状态')
    identity = str(seed.get('npc_id') or seed.get('id') or '')
    npc = find_person(game, identity, include_inactive=True)
    if npc is None:
        child = next((row for row in game.player.offspring if str(row.get('id')) == identity), None)
        cached = next((row.get('npc') for row in game.encounter_npc_cache if str(row.get('id')) == identity), None)
        npc = npc_type(**person_seed(child or cached or seed, game.player.world))
    if not npc.alive:
        raise ValueError('已经陨落的人物不能被拘禁或复活')
    if npc.roster_state == 'retired':
        raise ValueError('该人物已经退出当前名册')
    if npc.roster_state == 'held' and (npc.custody or {}).get('holder_id') != game.id:
        raise ValueError('此人不受你控制')
    if npc.roster_state != 'held':
        npc.roster_origin = _detach(game, npc)
    npc.roster_state = 'held'
    npc.custody = {'kind': kind, 'holder_id': game.id,
                   'since_age': (npc.custody or {}).get('since_age', game.player.age)}
    npc.death_reason = None
    game.inactive_npcs[npc.id] = npc
    sync_offspring(game, npc)
    return bind_relationship(game, dict(seed, id=npc.id, npc_id=npc.id), npc_type)


def release_person(game, identity, *, affinity=None):
    npc = find_person(game, str(identity), include_inactive=True)
    if npc is None or npc.roster_state != 'held' or (npc.custody or {}).get('holder_id') != game.id:
        raise ValueError('此人不在你的拘禁名册中')
    if not npc.alive:
        raise ValueError('已经陨落的人物不能释放为活人')
    restored = False
    # Restore the former roster only when it still belongs to this world.
    for origin in npc.roster_origin:
        kind = origin['container']
        if kind in {'world_npcs', 'notable_npcs'}:
            getattr(game, kind)[npc.id] = npc
            restored = True
        elif kind in {'sect', 'family'}:
            group = game.family if kind == 'family' else game.sects.get(origin.get('id'))
            if group and not group.extinct and group.id == origin.get('id') and group.world == npc.world:
                group.npcs.insert(min(int(origin.get('index', len(group.npcs))), len(group.npcs)), npc)
                restored = True
    if not restored:
        game.notable_npcs[npc.id] = npc
        faction = game.sects.get(npc.faction_id or '')
        if faction is None or faction.extinct or faction.world != npc.world:
            npc.faction_id = None
    game.inactive_npcs.pop(npc.id, None)
    npc.roster_state, npc.custody, npc.roster_origin = 'active', None, []
    if affinity is not None:
        npc.affinity = affinity
    sync_offspring(game, npc)
    return npc


def kill_person(game, identity, reason):
    npc = find_person(game, str(identity), include_inactive=True)
    if npc is None:
        return None
    npc.alive, npc.death_reason = False, reason
    if npc.roster_state == 'held':
        npc.roster_state, npc.custody = 'retired', None
    game.player.party[:] = [row for row in game.player.party if row.get('id') != npc.id]
    sync_offspring(game, npc)
    return npc


def bind_custody(game, npc_type):
    """Register new in-memory records; existing authority always wins.

    Legacy false-death correction belongs only to the registered 7 -> 8 step.
    No save/load path is allowed to resurrect a dead authoritative NPC here.
    """
    for field in ('prisoners', 'concubines'):
        rows = getattr(game.player, field)
        for index, row in enumerate(rows):
            if field == 'concubines' and row.get('source') != 'captive':
                continue
            identity = str(row.get('npc_id') or row.get('id') or '')
            npc = find_person(game, identity, include_inactive=True)
            if npc is not None and (not npc.alive or npc.roster_state == 'retired'):
                rows[index] = bind_relationship(game, row, npc_type)
            else:
                rows[index] = detain_person(game, row, npc_type,
                    kind='prisoner' if field == 'prisoners' else 'concubine')


def settle_puppet_person(game, puppet, *, outcome, reason=''):
    """A puppet body has its own combat fields; its source person has one life."""
    identity = puppet.get('source_npc_id')
    npc = find_person(game, str(identity), include_inactive=True) if identity else None
    if npc is None or puppet.get('type') != 'living':
        return
    if outcome == 'released' and npc.alive and npc.roster_state == 'held':
        for key in ('realm_index', 'layer', 'body_training', 'immortal_body_level', 'divine_sense_rank', 'main_technique_id'):
            if key in puppet:
                setattr(npc, key, copy.deepcopy(puppet[key]))
        release_person(game, npc.id)
    elif outcome == 'dead':
        kill_person(game, npc.id, reason)


def retire_owned_people(game):
    """Permanent departure ends ownership without fabricating deaths/rewards."""
    for npc in game.inactive_npcs.values():
        if npc.roster_state == 'held' and (npc.custody or {}).get('holder_id') == game.id:
            npc.roster_state, npc.custody = 'retired', None
            sync_offspring(game, npc)

