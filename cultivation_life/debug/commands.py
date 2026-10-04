"""Initial command vocabulary. Registration is the only command dispatch table."""
import copy
import math
import random
import re

from ..content_registry import ACTIONS, REALMS, EXTENSION_REPORT, ITEM_CATALOG, WORLD_SYSTEMS, ROOT_NAMES, PATH_NAMES
from ..models import Player
from ..rules import add_item, remove_item
from ..runtime import encode_rng
from ..version import BASE_GAME_VERSION
from .registry import Argument, Command, CommandError, Registry
from .state import digest, differences, npc_rows, validate, read_pointer
from .capabilities import CAPABILITIES, EXCLUDED_OPERATIONS, register as register_capabilities


# Exact authoritative field names. Values are (type, minimum, maximum).
FIELDS = {
    'spirit_stones': (int, 0, 10**15), 'opportunity': (float, 0, 10**15),
    'age': (int, 0, 10**9), 'lifespan': (int, 1, 10**9),
    'hp': (float, 0, 10**15), 'mp': (float, 0, 10**15),
    'heart_demon': (float, 0, 10**9), 'karma': (float, -10**9, 10**9),
    'sha_qi': (int, 0, 10**9), 'realm_index': (int, 0, len(REALMS) - 1),
    'layer': (int, 1, max(realm.layers for realm in REALMS)),
    'breakthrough_chance': (float, 0, 1),
}
RESOURCES = ('spirit_stone', 'opportunity')


def number(field, text):
    kind, minimum, maximum = FIELDS[field]
    if kind is int and isinstance(text, float) and not text.is_integer():
        raise CommandError(f'{field} expects int.')
    try:
        value = kind(text)
    except (TypeError, ValueError, OverflowError) as error:
        raise CommandError(f'{field} expects {kind.__name__}.') from error
    if not minimum <= value <= maximum or type(value) is float and not math.isfinite(value):
        raise CommandError(f'{field} must be within [{minimum}, {maximum}].')
    return value


def player_get(ctx, field):
    if field == 'spirit_stones':
        return {field: sum(item['quantity'] for item in ctx.document['player']['inventory']
                           if item['id'] == 'spirit_stone')}
    if field == 'breakthrough_chance':
        return {'override': ctx.session['current']['overrides'].get(field),
                'scope': 'ordinary major/minor cultivation checks; null means normal rules'}
    if field not in ctx.document['player']:
        raise CommandError(f'Unknown player field: {field}')
    return {field: copy.deepcopy(ctx.document['player'][field])}


def player_set(ctx, field, text):
    value = number(field, text)
    if field == 'breakthrough_chance':
        ctx.session['current']['overrides'][field] = value
        return player_get(ctx, field)
    player = ctx.document['player']
    if field == 'spirit_stones':
        inventory = player['inventory']
        inventory[:] = [item for item in inventory if item['id'] != 'spirit_stone']
        if value:
            inventory.append(ITEM_CATALOG['spirit_stone'].to_dict() | {'quantity': value})
        return {field: value}
    if field in {'realm_index', 'layer'}:
        if ctx.document.get('pending_event') or ctx.document.get('active_trial'):
            raise CommandError('Finish the pending event/trial before changing realm or layer.')
        if field == 'realm_index':
            player['layer'] = 1
        player.update(awaiting_major_breakthrough=False, awaiting_minor_breakthrough=False,
                      awaiting_ascension=False, awaiting_spirit_realm_crossing=False)
        player['joint_companion_breakthrough'] = None
    player[field] = value
    if field in {'realm_index', 'layer'}:
        ceiling = WORLD_SYSTEMS.get('world_profiles', {}).get(player['world'], {}).get('cultivation_ceiling')
        if ceiling and (player['realm_index'], player['layer']) > (ceiling['realm_index'], ceiling['layer']):
            raise CommandError('Realm exceeds the current world ceiling; use a suitable quick-start world first.')
    return {field: value}


def resource_change(ctx, field, text, sign):
    field = 'spirit_stones' if field == 'spirit_stone' else field
    amount = number(field, text)
    return player_set(ctx, field, player_get(ctx, field)[field] + sign * amount)


def snapshot_name(name):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', name):
        raise CommandError('Snapshot name: 1–48 English letters, digits, _ or -; start with a letter.')
    return name


def snapshot_create(ctx, name):
    snapshot_name(name)
    if name in {'initial', 'last_before'}:
        raise CommandError('initial and last_before are reserved checkpoints.')
    snapshots = ctx.session['snapshots']
    if name in snapshots:
        raise CommandError('Snapshot already exists; use a different name.')
    if len(snapshots) >= 8:
        raise CommandError('At most 8 snapshots per session; delete an old snapshot first.')
    snapshots[name] = copy.deepcopy(ctx.session['current'])
    return {'snapshot': name, 'sha256': digest(snapshots[name])}


def snapshot_get(ctx, name):
    snapshot_name(name)
    if name in {'initial', 'last_before'}:
        if ctx.session[name] is None:
            raise CommandError('No previous action checkpoint is available.')
        return ctx.session[name]
    if name not in ctx.session['snapshots']:
        raise CommandError(f'Unknown snapshot: {name}')
    return ctx.session['snapshots'][name]


def snapshot_restore(ctx, name):
    ctx.session['current'] = copy.deepcopy(snapshot_get(ctx, name))
    return {'restored': name}


def snapshot_delete(ctx, name):
    if name in {'initial', 'last_before'}:
        raise CommandError('Cannot delete a reserved checkpoint.')
    snapshot_get(ctx, name)
    del ctx.session['snapshots'][name]
    return {'deleted': name}


def npc_inspect(ctx, npc_id):
    matches = [{'source': source, 'npc': copy.deepcopy(npc)}
               for source, npc in npc_rows(ctx.document) if npc.get('id') == npc_id]
    if not matches:
        raise CommandError(f'Unknown NPC: {npc_id}')
    return {'id': npc_id, 'records': matches}


def rng_seed(ctx, seed):
    try:
        value = int(seed)
    except ValueError as error:
        raise CommandError('seed expects an integer.') from error
    if not 0 <= value <= 2**53 - 1:
        raise CommandError('seed must be within [0, 9007199254740991].')
    ctx.document.update(seed=value, rng_state=encode_rng(random.Random(value)))
    return {'seed': value, 'note': 'Resets future RNG draws; does not regenerate the existing world.'}


def state_get(ctx, pointer):
    """Read JSON Pointer paths only; never evaluate attributes or synthesize aliases."""
    return read_pointer(ctx.document, pointer)


def page(rows, offset):
    return {'total': len(rows), 'offset': offset, 'next_offset': offset + 50 if offset + 50 < len(rows) else None,
            'rows': rows[offset:offset + 50]}


def item_change(ctx, item_id, quantity, remove=False):
    if item_id not in ITEM_CATALOG:
        raise CommandError('Unknown item_id; use item list to discover catalog IDs.')
    if item_id == 'immortal_trace':
        raise CommandError('immortal_trace is a dedicated progression resource, not a normal inventory item.')
    player = Player.from_dict(copy.deepcopy(ctx.document['player']))
    if remove:
        if not remove_item(player, item_id, quantity):
            raise CommandError('Insufficient item quantity.')
    else:
        held = sum(item.quantity for item in player.inventory if item.id == item_id)
        if held + quantity > 10**15:
            raise CommandError('Item quantity would exceed 1000000000000000.')
        add_item(player, item_id, quantity)
    # Copy only the authoritative inventory; decoding must not normalize other fields.
    ctx.document['player']['inventory'] = [item.to_dict() for item in player.inventory]
    return {'item_id': item_id, 'quantity': sum(i.quantity for i in player.inventory if i.id == item_id)}


def build_registry():
    registry = Registry()
    def add(name, kind, description, handler, arguments=(), requires_session=True):
        registry.register(Command(name, kind, description, handler, arguments, requires_session))
    add('help', 'query', 'List commands or help <command/group>.',
        lambda ctx, prefix='': registry.catalog(prefix), requires_session=False)
    add('version', 'query', 'Show the base game version.',
        lambda ctx: {'base_game': BASE_GAME_VERSION}, requires_session=False)
    add('debug status', 'query', 'Show isolated session and active overrides.',
        lambda ctx: {'session_id': ctx.session['id'] if ctx.session else None,
                     'revision': ctx.session.get('revision', 0) if ctx.session else None,
                     'overrides': ctx.session['current']['overrides'] if ctx.session else {}},
        requires_session=False)
    add('debug start', 'session', 'Clone the selected save into an isolated debug session.',
        lambda ctx: ctx.services.start(), requires_session=False)
    add('debug stop', 'session', 'Return to the original game; retain the debug session on disk.',
        lambda ctx: {'session_id': None,
                     'game_id': None if ctx.session.get('source_kind') == 'generated' else ctx.session['source_game_id'],
                     'return_to_title': ctx.session.get('source_kind') == 'generated'})
    add('debug sessions', 'query', 'List saved debug sessions.',
        lambda ctx: ctx.services.sessions(), requires_session=False)
    add('save list', 'query', 'List source save IDs without loading or modifying them.',
        lambda ctx: ctx.services.sources(), requires_session=False)
    add('debug resume', 'session', 'Resume an isolated session.',
        lambda ctx, session_id: ctx.services.resume(session_id),
        (Argument('session_id'),), False)
    add('player', 'query', 'Inspect the detached player document.',
        lambda ctx: copy.deepcopy(ctx.document['player']))
    add('player get', 'query', 'Read an exact player field; breakthrough_chance is a session override.',
        player_get, (Argument('field'),))
    add('player fields', 'query', 'List writable fields, types and limits.',
        lambda ctx: {key: {'type': value[0].__name__, 'min': value[1], 'max': value[2]}
                     for key, value in FIELDS.items()}, requires_session=False)
    add('player set', 'mutation', 'Set a supported field. Realm changes reset layer and pending flags.',
        player_set, (Argument('field', tuple(FIELDS)), Argument('value', type='number')))
    add('player reset breakthrough_chance', 'mutation', 'Remove the session probability override.',
        lambda ctx: {'removed': ctx.session['current']['overrides'].pop('breakthrough_chance', None)})
    add('give', 'mutation', 'Add a supported resource.',
        lambda ctx, resource, amount: resource_change(ctx, resource, amount, 1),
        (Argument('resource', RESOURCES), Argument('amount', type='number', minimum=0, maximum=10**15)))
    add('remove', 'mutation', 'Remove a supported resource without going below zero.',
        lambda ctx, resource, amount: resource_change(ctx, resource, amount, -1),
        (Argument('resource', RESOURCES), Argument('amount', type='number', minimum=0, maximum=10**15)))
    add('realm list', 'query', 'List authoritative realm IDs, indexes and layer counts.',
        lambda ctx: [{'realm_index': i, 'id': realm.id, 'name': realm.name, 'layers': realm.layers}
                     for i, realm in enumerate(REALMS)], requires_session=False)
    add('npc list', 'query', 'List NPC IDs and recorded state containers (first 200).',
        lambda ctx: [{'source': source, 'id': npc.get('id'), 'name': npc.get('name'),
                      'alive': npc.get('alive'), 'custody': npc.get('custody'),
                      'roster_state': npc.get('roster_state')}
                     for source, npc in list(npc_rows(ctx.document))[:200]])
    add('npc inspect', 'query', 'Inspect every recorded source for this NPC ID.',
        npc_inspect, (Argument('npc_id'),))
    add('rng state', 'query', 'Show stored seed and complete RNG state without drawing.',
        lambda ctx: {key: ctx.document[key] for key in ('seed', 'rng_state')})
    add('rng seed', 'mutation', 'Reset RNG in the isolated copy only.', rng_seed,
        (Argument('seed', type='integer', minimum=0, maximum=2**53 - 1),))
    add('state get', 'query', 'Read a saved JSON Pointer using exact field names; no preparation or RNG.',
        state_get, (Argument('pointer'),))
    add('state summary', 'query', 'Inspect scene, blockers and current state fingerprint.',
        lambda ctx: {'sha256': digest(ctx.session['current']),
                     'player': {key: ctx.document['player'].get(key) for key in
                         ('name', 'alive', 'age', 'world', 'realm_index', 'layer', 'hp', 'mp')},
                     'pending_event': copy.deepcopy(ctx.document.get('pending_event')),
                     'active_trial': copy.deepcopy(ctx.document.get('active_trial'))})
    add('journal list', 'query', 'Read the latest bounded action records and failures.',
        lambda ctx: copy.deepcopy(ctx.session['journal']))
    add('npc find', 'query', 'Find NPC records by exact ID/name substring; use an empty query to page all.',
        lambda ctx, query, offset: page([{'source': source, 'id': npc.get('id'), 'name': npc.get('name'),
            'alive': npc.get('alive'), 'custody': npc.get('custody'), 'roster_state': npc.get('roster_state')}
            for source, npc in npc_rows(ctx.document)
            if query in str(npc.get('id', '')) or query in str(npc.get('name', ''))], offset),
        (Argument('query'), Argument('offset', type='integer', minimum=0, maximum=10**9)))
    add('item list', 'query', 'Find catalog items by ID/name substring; page size 50, empty query lists all.',
        lambda ctx, query, offset: page([item.to_dict() for key, item in sorted(ITEM_CATALOG.items())
                                       if query in key or query in item.name], offset),
        (Argument('query'), Argument('offset', type='integer', minimum=0, maximum=10**9)), False)
    add('inventory', 'query', 'Read the isolated inventory.',
        lambda ctx: copy.deepcopy(ctx.document['player']['inventory']))
    item_args = (Argument('item_id'),
                 Argument('quantity', type='integer', minimum=1, maximum=10**9))
    add('item give', 'mutation', 'Add a catalog inventory item using ordinary inventory rules.', item_change, item_args)
    add('item remove', 'mutation', 'Remove an inventory item; reject insufficient quantities.',
        lambda ctx, item_id, quantity: item_change(ctx, item_id, quantity, True), item_args)
    add('action list', 'query', 'List action IDs and settings; availability still follows ordinary rules.',
        lambda ctx: copy.deepcopy(ACTIONS), requires_session=False)
    add('event inspect', 'query', 'Read the saved pending event and choice IDs; enabled flags reflect stored state.',
        lambda ctx: copy.deepcopy(ctx.document.get('pending_event')))
    add('action advance', 'simulation', 'Perform 1–10 action units through ordinary rules; events can interrupt.',
        lambda ctx, action, units: ctx.services.simulate(ctx.session, 'advance', {'action': action, 'years': units}),
        (Argument('action', tuple(ACTIONS)), Argument('units', type='integer', minimum=1, maximum=10)))
    add('event choose', 'simulation', 'Resolve a pending event choice through ordinary rules.',
        lambda ctx, choice_id: ctx.services.simulate(ctx.session, 'choice', {'choice_id': choice_id}),
        (Argument('choice_id'),))
    add('save validate', 'query', 'Run lightweight, non-mutating validation.', lambda ctx: validate(ctx.document))
    add('snapshot create', 'snapshot', 'Save game, overrides and isolated achievements.',
        snapshot_create, (Argument('name'),))
    add('snapshot list', 'query', 'List named snapshots and reserved checkpoints.',
        lambda ctx: ['initial', 'last_before', *ctx.session['snapshots']])
    add('snapshot diff', 'query', 'Compare a named snapshot with current state.',
        lambda ctx, name: differences(snapshot_get(ctx, name), ctx.session['current']), (Argument('name'),))
    add('snapshot restore', 'mutation', 'Restore game, RNG, overrides and achievements atomically.',
        snapshot_restore, (Argument('name'),))
    add('snapshot delete', 'snapshot', 'Delete one named debug snapshot.', snapshot_delete, (Argument('name'),))
    add('extensions', 'query', 'Inspect the currently loaded extension report.',
        lambda ctx: copy.deepcopy(EXTENSION_REPORT), requires_session=False)
    add('repro export', 'export', 'Export current, pre-action and initial snapshots plus bounded action records.',
        lambda ctx: ctx.services.export(ctx.session))
    add('repro import', 'session', 'Import an attached reproduction bundle into a new isolated session.',
        lambda ctx: ctx.services.import_bundle(), requires_session=False)
    add('game view', 'simulation', 'Prepare and commit the isolated game as the UI does, then read a public JSON Pointer. '
        'Omit pointer to list sections. This may settle state or consume RNG; use state get for pure saved data.',
        lambda ctx, pointer=None: ctx.services.simulate(ctx.session, 'view', {'pointer': pointer}),
        (Argument('pointer', required=False),))
    add('scenario list', 'query', 'List real quick-start presets, spirit roots, paths and allowed starting worlds.',
        lambda ctx: {'presets': copy.deepcopy(WORLD_SYSTEMS.get('quick_start_presets', [])),
                     'spirit_roots': ROOT_NAMES, 'paths': PATH_NAMES,
                     'start_worlds': copy.deepcopy(WORLD_SYSTEMS.get('start_worlds', {}))}, requires_session=False)
    scene_args = (Argument('name'), Argument('spirit_root', tuple(ROOT_NAMES)), Argument('path', tuple(PATH_NAMES)),
                  Argument('seed', type='integer', minimum=0, maximum=2**53-1),
                  Argument('preset_id', required=False), Argument('start_world', required=False),
                  Argument('gender', ('male', 'female'), required=False),
                  Argument('technique_element', required=False), Argument('monster_species_id', required=False))
    add('scenario create', 'session', 'Create a new isolated test character using ordinary creation and quick-start rules; '
        'never creates a normal save. Seed does not fix runtime clock or UUIDs.',
        lambda ctx, *values: ctx.services.create_scene({a.name: v for a, v in zip(scene_args, values) if v is not None}),
        scene_args, False)
    add('capability list', 'query', 'List covered ordinary operations and explicitly excluded specialized routes.',
        lambda ctx: {'covered': [{'command': c.name, 'operation': c.operation,
                                  'type': 'preview' if c.preview else 'simulation'} for c in CAPABILITIES],
                     'excluded': EXCLUDED_OPERATIONS}, requires_session=False)
    register_capabilities(registry)
    return registry
