"""Pure save 7 -> 8 migration for life/custody/roster separation."""
from __future__ import annotations

import copy

from .relationship_schema import PERSON_FIELDS, normalize_relationship_document, person_seed


def migrate_custody_v7(document):
    player = document.get('player', {})
    held = document.setdefault('inactive_npcs', {})
    persons, origins = {}, {}
    groups = []
    family = document.get('family')
    if family and not family.get('extinct'):
        groups.append(('family', family))
    for field in ('world_npcs', 'notable_npcs'):
        for identity, npc in document.get(field, {}).items():
            persons.setdefault(identity, npc)
            origins.setdefault(identity, []).append({'container': field})
    groups.extend(('sect', sect) for sect in document.get('sects', {}).values())
    for kind, group in groups:
        for index, npc in enumerate(group.get('npcs', [])):
            if kind == 'family':
                persons[npc['id']] = npc
            else:
                persons.setdefault(npc['id'], npc)
            origins.setdefault(npc['id'], []).append({'container': kind, 'id': group['id'], 'index': index})
    for identity, npc in document.get('relationship_npcs', {}).items():
        persons.setdefault(identity, npc)
        origins.setdefault(identity, []).append({'container': 'relationship_npcs'})
    rows = [('prisoner', row) for row in player.get('prisoners', [])]
    rows.extend(('concubine', row) for row in player.get('concubines', []) if row.get('source') == 'captive')
    aliases = {}
    for kind, row in rows:
        identity = str(row.get('npc_id') or row.get('id') or '')
        if row.get('id'):
            aliases[str(row['id'])] = identity
        npc = persons.get(identity) or held.get(identity)
        if npc is None:
            npc = person_seed(row, player.get('world', 'human'))
        reason = str(npc.get('death_reason') or '')
        # Correct only explicit legacy capture markers. Genuine deaths win.
        was_capture = reason.endswith(('生擒', '扣作议和人质'))
        if npc.get('alive', True) or was_capture:
            for key in PERSON_FIELDS:
                if key in row:
                    npc[key] = copy.deepcopy(row[key])
            npc['alive'] = bool(row.get('alive', True))
            npc['death_reason'] = row.get('death_reason') if not npc['alive'] else None
        npc['roster_state'] = 'held' if npc.get('alive', True) else 'retired'
        npc['custody'] = ({'kind': kind, 'holder_id': document['id'],
                          'since_age': row.get('captured_age', player.get('age', 0))}
                         if npc['roster_state'] == 'held' else None)
        npc['roster_origin'] = origins.get(identity, [])
        held[identity] = npc
        for field in ('world_npcs', 'notable_npcs', 'relationship_npcs'):
            document.get(field, {}).pop(identity, None)
        for _, group in groups:
            group['npcs'] = [entry for entry in group.get('npcs', []) if entry['id'] != identity]
        row['id'] = row['npc_id'] = identity
    # Old puppet creation discarded the source ID. Do not guess identity by name.
    # These bodies retain their dedicated gameplay records. Explicit false-death
    # markers still establish survival, but never permission to rejoin a roster.
    for identity, npc in persons.items():
        if identity in held or npc.get('alive', True):
            continue
        reason = str(npc.get('death_reason') or '')
        if not reason.endswith(('生擒', '扣作议和人质', '炼为活傀')):
            continue
        npc.update(alive=True, death_reason=None, roster_state='retired', custody=None,
                   roster_origin=origins.get(identity, []))
        held[identity] = npc
        for field in ('world_npcs', 'notable_npcs', 'relationship_npcs'):
            document.get(field, {}).pop(identity, None)
        for _, group in groups:
            group['npcs'] = [entry for entry in group.get('npcs', []) if entry['id'] != identity]
    for child in player.get("offspring", []):
        if child.get("id") in held:
            child.update(copy.deepcopy(held[child["id"]]))
    removed = set(held) | set(aliases)
    pending = document.get('pending_event') or {}
    if pending.get('id') == 'SYS_POST_BATTLE_POSSESSION':
        runtime = pending.get('runtime', {})
        runtime['prisoner_ids'] = [aliases.get(str(identity), str(identity))
                                   for identity in runtime.get('prisoner_ids', [])]
        for choice in pending.get('choices', []):
            if str(choice.get('id')) in aliases:
                choice['id'] = aliases[str(choice['id'])]
    player['party'] = [row for row in player.get('party', []) if str(row.get('id')) not in removed]
    document['encounter_npc_cache'] = [row for row in document.get('encounter_npc_cache', []) if str(row.get('id')) not in removed]
    normalize_relationship_document(document)
