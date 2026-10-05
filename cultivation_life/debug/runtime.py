"""Atomic isolated sessions, command execution and bounded reproduction records.

One envelope commits the save, overrides, achievements, snapshots and journal.
Gameplay requests run in a temporary store; neither failed requests nor debug
achievements can write to the original game's save directory.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import tempfile
import threading
import traceback
import uuid

from ..content_registry import CONTENT_DOCUMENTS, EXTENSION_REPORT
from ..errors import NotFoundError
from ..engine.transactions import request_scope
from ..runtime import now_iso
from ..save_schema import migrate_document
from ..version import BASE_GAME_VERSION
from .commands import build_registry, snapshot_name
from .engine_adapter import SessionEngine
from .registry import CommandError, Context, Services
from .state import digest, differences, validate, read_pointer
from .capabilities import BY_OPERATION
from .dlc import available


FORMAT = 'CultivationLife.debug.v1'
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
_locks = {}
_locks_guard = threading.Lock()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_json(path, value):
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(data.encode()) > MAX_BUNDLE_BYTES:
        raise CommandError('Debug session exceeds 64 MiB; delete snapshots or start a fresh session.')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8',
                                         suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_current(current):
    validate(current['game'])
    overrides = current['overrides']
    if not isinstance(overrides, dict) or set(overrides) - {'breakthrough_chance'}:
        raise CommandError('Unknown session override.')
    if 'breakthrough_chance' in overrides:
        chance = overrides['breakthrough_chance']
        if type(chance) not in (int, float) or not 0 <= chance <= 1:
            raise CommandError('breakthrough_chance must be within [0, 1].')
    achievements = current['achievements']
    if (not isinstance(achievements, dict) or achievements.get('schema_version') != 1
            or not isinstance(achievements.get('achievements'), dict)
            or any(not isinstance(record, dict) for record in achievements['achievements'].values())):
        raise CommandError('Invalid isolated achievements.')


class Runtime:
    def __init__(self, project_root, directory, source_store):
        self.project_root = Path(project_root)
        self.directory = Path(directory)
        self.source_store = source_store
        self.registry = build_registry()
        with _locks_guard:
            self.lock = _locks.setdefault(str(self.directory.resolve()), threading.RLock())

    def _path(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch(r'[a-f0-9]{32}', session_id):
            raise CommandError('Invalid debug session ID.')
        return self.directory / f'{session_id}.json'

    def load(self, session_id):
        path = self._path(session_id)
        if not path.is_file():
            raise NotFoundError('Debug session not found; start a new session.')
        return read_json(path)

    def identity(self):
        checksum = hashlib.sha256()
        build_sha256 = os.environ.get('CULTIVATION_BUILD_FINGERPRINT')
        if build_sha256:
            # Android code lives in an AssetFinder archive, not an on-disk .py tree.
            checksum.update(build_sha256.encode())
        # Source/frozen builds both have their Python code under the engine root.
        # The executable hash covers frozen code when .py files are not present.
        code_root = Path(__file__).resolve().parents[2]
        for folder, suffixes in (('cultivation_life', {'.py', '.pyc'}), ('web', {'.js', '.css', '.html'})):
            root = code_root if folder == 'cultivation_life' else self.project_root
            for path in sorted((root / folder).rglob('*')):
                if path.is_file() and path.suffix in suffixes and '__pycache__' not in path.parts:
                    checksum.update(path.relative_to(root).as_posix().encode())
                    checksum.update(path.read_bytes())
        import sys
        if getattr(sys, 'frozen', False):
            checksum.update(Path(sys.executable).read_bytes())
        preferences = self.directory.parent / 'ui_preferences.json'
        return {'base_game_version': BASE_GAME_VERSION, 'code_sha256': checksum.hexdigest(),
                'build_sha256': build_sha256,
                'ui_preferences': read_json(preferences) if preferences.is_file() else {},
                'content_sha256': digest(CONTENT_DOCUMENTS), 'extensions': copy.deepcopy(EXTENSION_REPORT),
                'python': platform.python_version(), 'platform': platform.platform(),
                'python_hash_seed': os.environ.get('PYTHONHASHSEED', 'process-random'),
                'replay_scope': 'manual retry from last_before; time and UUID are not deterministic'}

    def start(self, game_id):
        if not isinstance(game_id, str) or not game_id.replace('-', '').isalnum():
            raise CommandError('Select a game before debug start.')
        with self.source_store.lock:
            path = self.source_store.directory / f'{game_id}.json'
            if not path.is_file():
                raise NotFoundError('Source game not found.')
            source = read_json(path)
            document = migrate_document(copy.deepcopy(source))
            if document['id'] != game_id:
                raise CommandError('Source game ID does not match its filename.')
            metadata = self.source_store.directory / 'global_metadata.json'
            achievements = read_json(metadata) if metadata.exists() else {'schema_version': 1, 'achievements': {}}
        validate(document)
        current = {'game': document, 'overrides': {}, 'achievements': achievements}
        session = {'format': FORMAT, 'id': uuid.uuid4().hex, 'source_game_id': game_id,
                   'source_sha256': digest(source), 'created_at': now_iso(), 'environment': self.identity(),
                   'current': current, 'initial': copy.deepcopy(current), 'last_before': None,
                   'snapshots': {}, 'journal': [], 'revision': 0, 'receipts': {}}
        atomic_json(self._path(session['id']), session)
        return {'session_id': session['id'], 'game_id': game_id, 'isolated': True, 'revision': 0}

    def sources(self):
        rows = []
        with self.source_store.lock:
            for path in sorted(self.source_store.directory.glob('*.json')):
                if path.name == 'global_metadata.json':
                    continue
                try:
                    document = read_json(path)
                    if isinstance(document, dict) and isinstance(document.get('player'), dict) and document.get('id') == path.stem:
                        rows.append({'game_id': document['id'], 'name': document['player'].get('name'),
                                     'save_schema': document.get('version')})
                except (OSError, ValueError):
                    rows.append({'file': path.name, 'error': 'unreadable source'})
        return rows

    def create_scene(self, options):
        with tempfile.TemporaryDirectory(prefix='cultivation-debug-scene-') as directory:
            engine = SessionEngine(self.project_root, Path(directory), {})
            game = engine.create_game(**options)
            current = self.staged_result(Path(directory), {'game': game, 'overrides': {}})
        session = {'format': FORMAT, 'id': uuid.uuid4().hex, 'source_game_id': game['id'],
                   'source_kind': 'generated', 'source_sha256': digest(current['game']),
                   'created_at': now_iso(), 'environment': self.identity(),
                   'current': current, 'initial': copy.deepcopy(current), 'last_before': None,
                   'snapshots': {}, 'journal': [], 'revision': 0, 'receipts': {}}
        atomic_json(self._path(session['id']), session)
        return {'session_id': session['id'], 'game_id': game['id'], 'isolated': True, 'revision': 0}

    def sessions(self):
        return [{'session_id': row['id'], 'game_id': row['current']['game']['id'],
                 'name': row['current']['game']['player']['name'], 'created_at': row['created_at']}
                for row in (read_json(path) for path in sorted(self.directory.glob('*.json')))]

    def resume(self, session_id):
        session = self.load(session_id)
        return {'session_id': session_id, 'game_id': session['current']['game']['id'], 'isolated': True,
                'revision': session.get('revision', 0)}

    def export(self, session):
        bundle = copy.deepcopy(session)
        bundle['export_environment'] = self.identity()
        return {'download': {'filename': f'repro-{session["id"]}.json',
                             'content': json.dumps(bundle, ensure_ascii=False, separators=(',', ':'))}}

    def import_bundle(self, bundle):
        if not isinstance(bundle, dict) or bundle.get('format') != FORMAT:
            raise CommandError('Expected a CultivationLife.debug.v1 reproduction bundle.')
        if len(json.dumps(bundle).encode()) > MAX_BUNDLE_BYTES:
            raise CommandError('Reproduction bundle is too large.')
        try:
            if not isinstance(bundle.get('environment'), dict) or not isinstance(bundle.get('source_sha256'), str):
                raise CommandError('Missing source environment or fingerprint.')
            if not isinstance(bundle.get('snapshots'), dict) or not isinstance(bundle.get('journal'), list):
                raise CommandError('Snapshots must be an object; journal must be a list.')
            if any(not isinstance(record, dict) for record in bundle['journal']):
                raise CommandError('Invalid journal entry.')
            validate_current(bundle['current'])
            validate_current(bundle['initial'])
            if bundle['last_before'] is not None:
                validate_current(bundle['last_before'])
            if len(bundle['snapshots']) > 8 or len(bundle['journal']) > 100:
                raise CommandError('Too many snapshots or journal entries.')
            for name, snapshot in bundle['snapshots'].items():
                snapshot_name(name)
                if name in {'initial', 'last_before'}:
                    raise CommandError('Reserved snapshot name.')
                validate_current(snapshot)
            game_id = bundle['current']['game']['id']
            if not isinstance(game_id, str) or not game_id.replace('-', '').isalnum():
                raise CommandError('Invalid game ID in bundle.')
            if bundle.get('source_game_id') != game_id:
                raise CommandError('Source game ID must match the isolated copy.')
            if any(value['game']['id'] != game_id for value in [bundle['initial'],
                   *(bundle['snapshots'].values()), *([bundle['last_before']] if bundle['last_before'] else [])]):
                raise CommandError('Snapshots must reference the same isolated game.')
        except (KeyError, TypeError, ValueError) as error:
            raise CommandError(f'Invalid reproduction bundle: {error}') from error
        session = {key: copy.deepcopy(bundle[key]) for key in (
            'format', 'source_game_id', 'source_sha256', 'environment', 'current', 'initial',
            'last_before', 'snapshots', 'journal')}
        session.update(id=uuid.uuid4().hex, created_at=now_iso(), revision=0, receipts={},
                       source_kind='generated' if bundle.get('source_kind') == 'generated' else 'save')
        atomic_json(self._path(session['id']), session)
        identity = self.identity()
        return {'session_id': session['id'], 'game_id': game_id, 'isolated': True, 'revision': 0,
                'environment_matches': all(session['environment'].get(key) == identity[key]
                    for key in ('base_game_version', 'code_sha256', 'content_sha256'))}

    def record(self, session, before, operation, error=None, request_id=None):
        session['revision'] = session.get('revision', 0) + 1
        session['last_before'] = copy.deepcopy(before)
        session['journal'].append({'at': now_iso(), 'operation': operation, 'request_id': request_id,
            'before_sha256': digest(before), 'after_sha256': digest(session['current']),
            'diff': differences(before, session['current']), 'error': error})
        session['journal'] = session['journal'][-100:]

    def execute(self, text, game_id=None, session_id=None, bundle=None, *, arguments=None,
                expected_revision=None, request_key=None):
        with self.lock:
            command, values = (self.registry.parse(text) if arguments is None
                               else self.registry.structured(text, arguments))
            session = self.load(session_id) if session_id else None
            if command.requires_session and session is None:
                raise CommandError('Start an isolated copy first: debug start')
            writes = command.kind in {'mutation', 'snapshot', 'simulation'}
            if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
                raise CommandError('expected_revision must be a nonnegative integer.')
            if request_key is not None and (not isinstance(request_key, str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', request_key)):
                raise CommandError('request_key must contain 1–64 letters, digits, _ or -.')
            if request_key is not None and not writes:
                raise CommandError('request_key is supported only for mutation, snapshot and simulation commands.')
            if request_key is not None and expected_revision is None:
                raise CommandError('request_key requires expected_revision, including text commands.')
            if arguments is not None and writes and (expected_revision is None or request_key is None):
                raise CommandError('Structured writes require expected_revision and request_key.')
            fingerprint = digest({'command': command.name, 'arguments': values,
                                  'expected_revision': expected_revision})
            receipt = session.get('receipts', {}).get(request_key) if session and request_key else None
            if receipt:
                if receipt['fingerprint'] != fingerprint:
                    raise CommandError('request_key was already used for a different request.')
                return {**receipt['result'], 'replayed': True, 'catalog': self.registry.catalog()}
            if expected_revision is not None and (session is None or session.get('revision', 0) != expected_revision):
                raise CommandError('Session revision conflict; inspect debug status before issuing a new request.')
            original = copy.deepcopy(session)
            ctx = Context(session, Services(start=lambda: self.start(game_id), resume=self.resume,
                sessions=self.sessions, export=self.export, import_bundle=lambda: self.import_bundle(bundle),
                sources=self.sources, simulate=self.simulate, preview=self.preview, create_scene=self.create_scene))
            operation = {'command': command.name, 'arguments': dict(zip((a.name for a in command.arguments), values))}
            try:
                data = command.handler(ctx, *values)
                if command.kind in {'query', 'preview'} and session != original:
                    raise RuntimeError('Query command modified the detached session.')
                diff = {'changes': [], 'total': 0, 'truncated': False}
                if writes:
                    validate_current(session['current'])
                    diff = differences(original['current'], session['current'])
                    self.record(session, original['current'], operation, request_id=request_key)
                result = {'ok': True, 'type': command.kind, 'command': command.name, 'data': data,
                          'revision': session.get('revision', 0) if session else None,
                          'changed': bool(diff['total']), 'diff': diff}
                if writes:
                    if request_key:
                        receipts = session.setdefault('receipts', {})
                        receipts[request_key] = {'fingerprint': fingerprint, 'result': copy.deepcopy(result)}
                        session['receipts'] = dict(list(receipts.items())[-64:])
                    atomic_json(self._path(session['id']), session)
                return {**result, 'catalog': self.registry.catalog()}
            except Exception as error:
                if original is not None and command.kind not in {'query', 'preview'}:
                    self.record(original, original['current'], operation,
                                {'type': type(error).__name__, 'message': str(error),
                                 'traceback': traceback.format_exc()}, request_id=request_key)
                    atomic_json(self._path(original['id']), original)
                if isinstance(error, (CommandError, NotFoundError)):
                    raise
                raise RuntimeError(f'Debug command failed: {command.name}') from error

    @contextmanager
    def staged(self, current):
        """One storage boundary shared by UI gameplay and tool simulations."""
        with tempfile.TemporaryDirectory(prefix='cultivation-debug-') as directory:
            store = Path(directory)
            game_id = current['game']['id']
            atomic_json(store / f'{game_id}.json', current['game'])
            atomic_json(store / 'global_metadata.json', current['achievements'])
            engine = SessionEngine(self.project_root, store, current['overrides'])
            yield engine, store

    def staged_result(self, store, before):
        current = {'game': read_json(store / f'{before["game"]["id"]}.json'),
                   'achievements': read_json(store / 'global_metadata.json'),
                   'overrides': copy.deepcopy(before['overrides'])}
        validate_current(current)
        return current

    def simulate(self, session, operation, payload):
        before = session['current']
        if operation in {'advance', 'choice'} and not before['game']['player']['alive']:
            raise CommandError('The player is dead; ordinary actions are unavailable.')
        pending = before['game'].get('pending_event')
        if operation == 'advance' and pending:
            raise CommandError('Resolve pending_event first with event choose.')
        if operation == 'choice' and not pending:
            raise CommandError('No pending_event to resolve.')
        if operation == 'choice' and payload['choice_id'] not in {c['id'] for c in pending.get('choices', [])}:
            raise CommandError('Unknown choice_id; inspect the pending event first.')
        with self.staged(before) as (engine, store), request_scope(engine):
            game_id = before['game']['id']
            if operation == 'view':
                view = engine.get_game(game_id)
                pointer = payload.get('pointer')
                result = {'sections': sorted(view)} if not pointer else read_pointer(view, pointer)
            else:
                capability = BY_OPERATION.get(operation)
                if capability is None or capability.preview:
                    raise RuntimeError('Unregistered simulation capability.')
                self.guard(engine, game_id, operation)
                capability.invoke(engine, game_id, payload)
            session['current'] = self.staged_result(store, before)
        if operation == 'view':
            return {'view': result, 'pointer': payload.get('pointer'), 'prepared': True}
        game = session['current']['game']
        return {'operation': operation, 'player_alive': game['player']['alive'],
                'age': game['player']['age'], 'pending_event': copy.deepcopy(game.get('pending_event')),
                'active_trial': copy.deepcopy(game.get('active_trial'))}

    @staticmethod
    def guard(engine, game_id, operation):
        capability = BY_OPERATION.get(operation)
        if capability and capability.dlc:
            if not available(capability.dlc):
                raise CommandError(f'Required DLC is not enabled: {capability.dlc}.')
        if operation not in {'heavens-view', 'heavens-preview', 'heavens-command'}:
            engine.assert_ghost_operation_allowed(game_id, operation)
            engine.assert_guixu_operation_allowed(game_id, operation)
            engine.assert_buddhist_operation_allowed(game_id, operation)

    def preview(self, session, operation, payload):
        capability = BY_OPERATION.get(operation)
        if capability is None or not capability.preview:
            raise RuntimeError('Unregistered preview capability.')
        with self.staged(session['current']) as (engine, _store), request_scope(engine):
            game_id = session['current']['game']['id']
            self.guard(engine, game_id, operation)
            return capability.invoke(engine, game_id, payload)

    @contextmanager
    def gameplay(self, session_id, operation, request_id):
        """Stage an ordinary engine request. The caller marks success explicitly."""
        with self.lock:
            session = self.load(session_id)
            before = copy.deepcopy(session['current'])
            with self.staged(before) as (engine, store):
                outcome = {'ok': False, 'error': None}
                try:
                    yield engine, outcome
                    if outcome['ok']:
                        session['current'] = self.staged_result(store, before)
                except Exception as error:
                    outcome['error'] = {'type': type(error).__name__, 'message': str(error),
                                        'traceback': traceback.format_exc()}
                    raise
                finally:
                    # Pure GETs with unchanged saves do not evict the last action checkpoint.
                    if operation['method'] != 'GET' or before != session['current'] or outcome['error']:
                        self.record(session, before, operation, outcome['error'], request_id)
                        atomic_json(self._path(session_id), session)
