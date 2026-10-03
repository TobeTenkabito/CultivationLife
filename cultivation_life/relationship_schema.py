"""Pure relationship document conversion; no gameplay or model imports."""
from __future__ import annotations

import copy

SINGLE_RELATIONS = ('master', 'dao_companion')
LIST_RELATIONS = ('disciples', 'dao_friends', 'disciple_requests', 'concubines')
PERSON_FIELDS = frozenset('''name realm_index layer age lifespan spirit_root cultivation_progress
path race world alive death_reason affinity gender main_technique_id main_technique_level
combat_artifact_id combat_factor next_tribulation_age tribulation_count tribulation_power
concealed_realm_index concealed_layer transcendence body_training immortal_body_level
divine_sense_rank monster_species_id asura_route faction_id departed_age departure_reason
wounds treasure_item_id treasure_looted family_traits family_combat_bonus notorious notoriety
encountered_player social_profile'''.split())
LABEL_FIELDS = frozenset(('realm_name', 'spirit_root_name', 'path_name', 'race_name', 'gender_name'))


def relationship_rows(player):
    for field in SINGLE_RELATIONS:
        if player.get(field):
            yield field, player[field]
    for field in LIST_RELATIONS:
        for row in player.get(field, []):
            if row:
                yield field, row


def independent_captive(field, row):
    # Here alive=False on the original NPC means absent from the free roster,
    # not dead. Keep this separate lifecycle until captivity has its own state.
    return field == 'concubines' and row.get('source') == 'captive'


def person_seed(row, world='human'):
    identity = str(row.get('npc_id') or row.get('id') or '')
    if not identity or not PERSON_FIELDS.intersection(row):
        raise ValueError('关系记录缺少可解析的人物身份')
    return {
        'id': identity, 'name': '无名修士', 'title': '', 'realm_index': 0, 'layer': 1,
        'age': 18, 'lifespan': None, 'world': world,
        **{key: copy.deepcopy(value) for key, value in row.items() if key in PERSON_FIELDS},
    }


def normalize_relationship_document(document):
    """Replace snapshots with references; existing NPC facts always win."""
    player = document.get('player', {})
    registry = document.setdefault('relationship_npcs', {})
    # Preserve the established lookup priority. These containers retain their
    # simulation schedules; relationships no longer duplicate their facts.
    persons = {}
    family = document.get('family')
    if family and not family.get('extinct'):
        for npc in family.get('npcs', []):
            persons.setdefault(str(npc['id']), npc)
    for key in ('world_npcs', 'notable_npcs'):
        for npc in document.get(key, {}).values():
            persons.setdefault(str(npc['id']), npc)
    for sect in document.get('sects', {}).values():
        for npc in sect.get('npcs', []):
            persons.setdefault(str(npc['id']), npc)
    if family:
        for npc in family.get('npcs', []):
            persons.setdefault(str(npc['id']), npc)
    for identity, npc in list(registry.items()):
        if str(identity) in persons:
            del registry[identity]
        else:
            persons[str(identity)] = npc
    aliases = {}
    for field, row in relationship_rows(player):
        if independent_captive(field, row):
            continue
        identity = str(row.get('npc_id') or row.get('id') or '')
        if row.get('id'):
            aliases[str(row['id'])] = identity
        if identity not in persons:
            npc = person_seed(row, player.get('world', 'human'))
            registry[identity] = persons[identity] = npc
        for key in ('affinity', 'main_technique_id'):
            if persons[identity].get(key) is None and row.get(key) is not None:
                persons[identity][key] = copy.deepcopy(row[key])
        for key in PERSON_FIELDS | LABEL_FIELDS:
            row.pop(key, None)
        row['id'] = identity
        row['npc_id'] = identity
    # A party is a set of identity references, not another person snapshot.
    player['party'] = [{'id': aliases.get(str(row.get('npc_id') or row.get('id')),
                                        str(row.get('npc_id') or row.get('id')))}
                       for row in player.get('party', []) if row.get('npc_id') or row.get('id')]


def migrate_relationships_v6(document):
    normalize_relationship_document(document)
