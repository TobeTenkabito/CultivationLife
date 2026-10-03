"""Schema boundaries, atomic migrations and ordered live-session preparation."""
import base64
import copy
import json
import zlib
from dataclasses import fields
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life import storage
from cultivation_life.engine import GameEngine, engine_persistence
from cultivation_life.engine.dependencies import PersistenceDependencies
from cultivation_life.engine.persistence import character, services
from cultivation_life.engine.persistence.dependencies import ServicesPreparationDependencies
from cultivation_life.models import GameState, Player
from cultivation_life.runtime import decode_rng, encode_rng
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION, migrate_document
from cultivation_life.save_transfer import import_snapshot, preview_snapshot
from cultivation_life.storage import SaveStore
from cultivation_life.version import BASE_GAME_VERSION
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def saved(tmp_path):
    store = SaveStore(tmp_path)
    game = GameState('schema', 42, Player('Player', 'none'), '', '')
    game.rng_state = encode_rng(decode_rng(42, ''))
    store.save(game)
    return store, game


@pytest.mark.parametrize('version', [None, True, '6', 6.0, 0, 1, 2, 3, 4, 5, 8, 999])
def test_unsupported_versions_never_decode_or_rewrite(saved, monkeypatch, version):
    store, game = saved
    path = store._path(game.id)
    document = json.loads(path.read_bytes())
    document['version'] = version
    path.write_text(json.dumps(document), encoding='utf-8')
    original = path.read_bytes()
    decode = Mock(side_effect=AssertionError('Unsupported schema reached model decoder'))
    monkeypatch.setattr(storage.GameState, 'from_dict', decode)
    with pytest.raises(ValueError):
        store.load(game.id)
    assert path.read_bytes() == original
    assert store.list_games() == []
    decode.assert_not_called()


def test_current_schema_read_is_pure_and_no_copy_migration_is_needed(saved, monkeypatch):
    store, game = saved
    original = store._path(game.id).read_bytes()
    document = json.loads(original)
    assert migrate_document(document) is document
    commit = Mock(side_effect=AssertionError('Current schema read attempted a commit'))
    monkeypatch.setattr(store, '_write_document', commit)
    loaded = store.load(game.id)
    assert loaded.version == SAVE_SCHEMA_VERSION
    assert loaded.rng_state == game.rng_state
    assert store._path(game.id).read_bytes() == original
    commit.assert_not_called()


def test_migrations_run_in_order_on_a_copy_and_only_once():
    document = {'id': 'game', 'version': 6, 'nested': {'values': []}}
    calls = []
    def step(data):
        calls.append(data['version'])
        data['nested']['values'].append(data['version'])
    converted = migrate_document(document, target=8, steps={6: step, 7: step})
    assert calls == [6, 7]
    assert converted == {'id': 'game', 'version': 8, 'nested': {'values': [6, 7]}}
    assert document == {'id': 'game', 'version': 6, 'nested': {'values': []}}
    assert migrate_document(converted, target=8, steps={6: step, 7: step}) is converted
    assert calls == [6, 7]


def test_missing_migration_is_rejected_before_any_step_runs():
    step = Mock()
    with pytest.raises(ValueError, match='缺少'):
        migrate_document({'version': 6}, target=8, steps={6: step})
    step.assert_not_called()


@pytest.mark.parametrize('corruption', ['raises', 'identity', 'version'])
def test_failed_migrations_preserve_the_original_document(corruption):
    document = {'id': 'game', 'version': 6, 'nested': []}
    original = copy.deepcopy(document)
    def step(data):
        data['nested'].append('changed')
        if corruption == 'raises':
            raise RuntimeError('Interrupted')
        data['id' if corruption == 'identity' else 'version'] = 'changed'
    with pytest.raises(RuntimeError):
        migrate_document(document, target=7, steps={6: step})
    assert document == original


def test_migration_commit_preserves_opaque_extensions_and_is_not_repeated(saved, monkeypatch):
    store, game = saved
    path = store._path(game.id)
    document = json.loads(path.read_bytes())
    document['version'] = 6
    document['opaque_mod_state'] = {'value': [1, 2]}
    path.write_text(json.dumps(document), encoding='utf-8')
    step = Mock(side_effect=lambda data: data.update(new_schema_field=True))
    monkeypatch.setattr(storage, 'migrate_document', lambda data: migrate_document(data, target=7, steps={6: step}))
    assert store.load(game.id).version == 7
    converted = json.loads(path.read_bytes())
    assert converted['opaque_mod_state'] == document['opaque_mod_state']
    assert converted['new_schema_field'] is True
    store.load(game.id)
    step.assert_called_once()


@pytest.mark.parametrize('failure', ['migration', 'decode', 'write'])
def test_failed_migration_load_keeps_original_file(saved, monkeypatch, failure):
    store, game = saved
    path = store._path(game.id)
    document = json.loads(path.read_bytes())
    document['version'] = 6
    path.write_text(json.dumps(document), encoding='utf-8')
    original = path.read_bytes()
    def step(data):
        data['player']['name'] = 'Migrated'
        if failure == 'migration':
            raise RuntimeError('Interrupted migration')
    monkeypatch.setattr(storage, 'migrate_document', lambda data: migrate_document(data, target=7, steps={6: step}))
    if failure == 'decode':
        monkeypatch.setattr(storage.GameState, 'from_dict', Mock(side_effect=RuntimeError('Decode failed')))
    if failure == 'write':
        monkeypatch.setattr(Path, 'replace', Mock(side_effect=OSError('Disk unavailable')))
    with pytest.raises((RuntimeError, OSError)):
        store.load(game.id)
    assert path.read_bytes() == original
    assert not list(store.directory.glob('*.tmp'))


def test_save_identity_must_match_requested_file(saved):
    store, game = saved
    path = store._path(game.id)
    document = json.loads(path.read_bytes())
    document['id'] = 'another-game'
    path.write_text(json.dumps(document), encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(ValueError, match='编号'):
        store.load(game.id)
    assert path.read_bytes() == original
    assert not store._path('another-game').exists()


@pytest.mark.parametrize('operation', [preview_snapshot, import_snapshot])
def test_transfer_rejects_retired_schema_without_creating_files(saved, tmp_path, operation):
    source, game = saved
    document = {'format': 'fusheng-save', 'format_version': 1, 'game_version': BASE_GAME_VERSION,
                'save': json.loads(source._path(game.id).read_bytes())}
    document['save']['version'] = 5
    payload = base64.b64encode(zlib.compress(json.dumps(document).encode())).decode()
    target = SaveStore(tmp_path / 'target')
    with pytest.raises(ValueError, match='停止支持'):
        operation(target, payload, None)
    assert not list(target.directory.iterdir())


@pytest.mark.parametrize('changed', [False, True])
def test_preparation_runs_every_stage_and_commits_at_most_once(saved, monkeypatch, changed):
    store, game = saved
    calls = []
    values = {'_get_store': lambda: store}
    for index, name in enumerate(('foundations', 'vitality', 'character', 'world', 'services', 'events')):
        token = object()
        values[name] = token
        def stage(deps, state, name=name, token=token, index=index):
            assert deps is token and state.id == game.id
            calls.append(name)
            return changed and index == 0
        monkeypatch.setattr(getattr(engine_persistence, name), 'prepare_' + name, stage)
    commit = Mock(wraps=store.save)
    monkeypatch.setattr(store, 'save', commit)
    engine_persistence._load(PersistenceDependencies(**values), game.id)
    assert calls == ['foundations', 'vitality', 'character', 'world', 'services', 'events']
    assert commit.call_count == int(changed)


def test_failed_preparation_does_not_commit_partial_state(saved, monkeypatch):
    store, game = saved
    original = store._path(game.id).read_bytes()
    def fail(deps, state):
        state.player.name = 'Unsaved'
        raise RuntimeError('Preparation failed')
    monkeypatch.setattr(engine_persistence.foundations, 'prepare_foundations', fail)
    deps = PersistenceDependencies(**{f.name: (lambda: store) if f.name == '_get_store' else None
                                      for f in fields(PersistenceDependencies)})
    with pytest.raises(RuntimeError):
        engine_persistence._load(deps, game.id)
    assert store._path(game.id).read_bytes() == original


def test_buddhist_preparation_is_detected_without_consuming_rng(saved):
    _, game = saved
    before = game.rng_state
    deps = ServicesPreparationDependencies(
        _ensure_natal_artifact=lambda game: False, _ensure_heavenly_court=lambda *args: False,
        _ensure_market=lambda *args: False,
        _ensure_buddhist_state=lambda game: game.buddhist_state.setdefault('initialized', True))
    assert services.prepare_services(deps, game)
    assert not services.prepare_services(deps, game)
    assert game.rng_state == before


def test_restoring_demonic_sense_starter_marks_character_changed(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game_id = engine.create_game('Sense', 'none', 'demonic', 125)['id']
    game = engine._load(game_id)
    game.player.divine_sense_technique = None
    assert character.prepare_character(engine._dependencies.persistence_runtime.character, game)
    assert game.player.divine_sense_technique.id == 'TECH_BLOOD_SOUL_SENSE'


@pytest.mark.parametrize('path', ['dao', 'demonic', 'buddhist', 'ghost', 'monster'])
def test_new_current_saves_can_resume_without_repeated_rng_or_history_changes(tmp_path, path):
    engine = GameEngine(ROOT, tmp_path)
    game_id = engine.create_game('Resume', 'none', path, 1024, monster_species_id='serpent' if path == 'monster' else None)['id']
    first = engine._load(game_id)
    second = engine._load(game_id)
    assert first.version == second.version == SAVE_SCHEMA_VERSION
    assert first.rng_state == second.rng_state
    assert [row.to_dict() for row in first.history] == [row.to_dict() for row in second.history]
    assert first.player.age == second.player.age
    assert first.buddhist_state == second.buddhist_state


@pytest.mark.parametrize('source,target', [
    ('save_schema', 'engine'),
    ('save_schema', 'system.ghost_system'),
    ('save_schema', 'models'),
    ('engine.persistence.character', 'storage'),
    ('engine.persistence.services', 'engine.engine_persistence'),
])
def test_schema_and_preparation_layers_cannot_import_orchestrators(source, target):
    source, target = 'cultivation_life.' + source, 'cultivation_life.' + target
    assert violations([(source, target, 9)]) == [{'source': source, 'target': target, 'line': 9}]

