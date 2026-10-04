"""Pure inspection and bounded validation of detached documents."""
import copy
import hashlib
import json
import math
import re

from ..content_registry import REALMS, WORLD_SYSTEMS
from ..models import GameState
from ..runtime import decode_rng
from ..save_schema import SAVE_SCHEMA_VERSION
from .registry import CommandError


def read_pointer(document, pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/') or len(pointer) > 256:
        raise CommandError('Expected a JSON Pointer beginning with /, up to 256 characters.')
    value = document
    for part in pointer[1:].split('/'):
        if re.search(r'~(?![01])', part):
            raise CommandError('Invalid JSON Pointer escape.')
        key = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r'0|[1-9][0-9]*', key) and int(key) < len(value):
            value = value[int(key)]
        else:
            raise CommandError(f'Unknown state pointer: {pointer}')
    return copy.deepcopy(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def differences(before, after, limit=100):
    rows = []
    total = 0

    def walk(left, right, path):
        nonlocal total
        if type(left) is type(right) and left == right:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() | right.keys()):
                walk(left.get(key), right.get(key), f'{path}.{key}' if path else key)
        else:
            total += 1
            if len(rows) < limit:
                def summary(value):
                    text = json.dumps(value, ensure_ascii=False)
                    return value if len(text) < 600 else {'sha256': digest(value), 'preview': text[:250]}
                rows.append({'field': path, 'before': summary(left), 'after': summary(right)})
    walk(before, after, '')
    return {'changes': rows, 'total': total, 'truncated': total > limit}


def npc_rows(document):
    for container in ('world_npcs', 'notable_npcs', 'relationship_npcs', 'inactive_npcs'):
        values = document.get(container, {})
        for npc in values.values() if isinstance(values, dict) else values:
            yield container, npc
    for sect in document.get('sects', {}).values():
        for npc in sect.get('npcs', []):
            yield f'sects.{sect["id"]}.npcs', npc
    for npc in (document.get('family') or {}).get('npcs', []):
        if isinstance(npc, dict) and 'id' in npc:
            yield 'family.npcs', npc


def validate(document):
    """Validate supported invariants without invoking read preparation or saving."""
    if document.get('version') != SAVE_SCHEMA_VERSION:
        raise CommandError('Expected current save schema.')
    p = document['player']
    index, layer = p['realm_index'], p['layer']
    if type(index) is not int or not 0 <= index < len(REALMS):
        raise CommandError('Invalid realm_index.')
    if type(layer) is not int or not 1 <= layer <= REALMS[index].layers:
        raise CommandError('layer is outside the selected realm.')
    if p['world'] not in WORLD_SYSTEMS['world_names']:
        raise CommandError('Unknown player world.')
    # This is a light validator, not a claim that every DLC invariant is covered.
    for key in ('opportunity', 'hp', 'mp', 'age', 'heart_demon'):
        value = p.get(key, 0)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise CommandError(f'Invalid player.{key}.')
    decode_rng(document['seed'], document['rng_state'])
    GameState.from_dict(copy.deepcopy(document))
    return {'valid': True, 'scope': 'model decode, realm/layer, world, numeric fields, RNG',
            'save_schema': SAVE_SCHEMA_VERSION}
