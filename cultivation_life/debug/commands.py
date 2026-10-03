"""Initial command vocabulary. Registration is the only command dispatch table."""
import copy
import math
import random
import re

from ..content_registry import REALMS, EXTENSION_REPORT, ITEM_CATALOG, WORLD_SYSTEMS
from ..runtime import encode_rng
from ..version import BASE_GAME_VERSION
from .registry import Argument, Command, CommandError, Registry
from .state import digest, differences, npc_rows, validate


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
    try:
        value = kind(text)
    except (TypeError, ValueError, OverflowError) as error:
        raise CommandError(f'{field} expects {kind.__name__}.') from error
    if not math.isfinite(value) or not minimum <= value <= maximum:
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
    return player_set(ctx, field, str(player_get(ctx, field)[field] + sign * amount))


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
                     'overrides': ctx.session['current']['overrides'] if ctx.session else {}},
        requires_session=False)
    add('debug start', 'session', 'Clone the selected save into an isolated debug session.',
        lambda ctx: ctx.services.start(), requires_session=False)
    add('debug stop', 'session', 'Return to the original game; retain the debug session on disk.',
        lambda ctx: {'session_id': None, 'game_id': ctx.session['source_game_id']})
    add('debug sessions', 'query', 'List saved debug sessions.',
        lambda ctx: ctx.services.sessions(), requires_session=False)
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
        player_set, (Argument('field', tuple(FIELDS)), Argument('value')))
    add('player reset breakthrough_chance', 'mutation', 'Remove the session probability override.',
        lambda ctx: {'removed': ctx.session['current']['overrides'].pop('breakthrough_chance', None)})
    add('give', 'mutation', 'Add a supported resource.',
        lambda ctx, resource, amount: resource_change(ctx, resource, amount, 1),
        (Argument('resource', RESOURCES), Argument('amount')))
    add('remove', 'mutation', 'Remove a supported resource without going below zero.',
        lambda ctx, resource, amount: resource_change(ctx, resource, amount, -1),
        (Argument('resource', RESOURCES), Argument('amount')))
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
    add('rng seed', 'mutation', 'Reset RNG in the isolated copy only.', rng_seed, (Argument('seed'),))
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
    return registry
