"""M0 persistence, retry, isolation and closed-mode acceptance tests."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import request_games, request_scope
from cultivation_life.models import GameState, Player
from cultivation_life.runtime import decode_rng, encode_rng
from cultivation_life.save_schema import migrate_document, migration_path
from cultivation_life.storage import SaveStore
from cultivation_life.system.heavens import operations
from cultivation_life.system.heavens.definitions import HeavensDefinitions, validate_framework
from cultivation_life.system.heavens.dependencies import HeavensDependencies
from cultivation_life.system.heavens.schema import initial_state, validate_state
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def saved(tmp_path):
    store = SaveStore(tmp_path)
    game = GameState('heavens-test', 42, Player('诸天测试', 'none'), '', '')
    game.rng_state = encode_rng(decode_rng(42, ''))
    store.save(game)
    deps = HeavensDependencies(lambda _key: game, lambda: store, HeavensDefinitions,
                               lambda _work: None, lambda _key: None)
    return game, store, deps


@pytest.mark.parametrize('version', [8])
def test_migration_is_empty_pure_and_round_trips(saved, version):
    game, store, _deps = saved
    old = game.to_dict()
    old.pop('heavens_state')
    old['version'] = version
    before = copy.deepcopy(old)
    migrated = migrate_document(old)
    assert old == before
    assert migrated['version'] == 9 and migrated['heavens_state'] == {}
    assert migrated['rng_state'] == old['rng_state']
    store._path(game.id).write_text(json.dumps(old), encoding='utf-8')
    reloaded = store.load(game.id)
    assert reloaded.heavens_state == {}
    assert reloaded.rng_state == game.rng_state
    store.save(reloaded)
    assert store.load(game.id).to_dict() == reloaded.to_dict()
    with pytest.raises(ValueError, match='更高结构'):
        migration_path(9, target=8)


def test_v8_conflict_is_not_silently_deleted(saved):
    game, store, _deps = saved
    old = game.to_dict()
    old.update(version=8, heavens_state={'foreign_extension': True})
    store._path(game.id).write_text(json.dumps(old), encoding='utf-8')
    before = store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='冲突'):
        store.load(game.id)
    assert store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('corruption', [None, [], {'schema_version': 99},
    {**initial_state(), 'revision': float('nan')},
    {**initial_state(), 'revision': True},
    {**initial_state(), 'generation_enabled': True},
    {**initial_state(), 'person_refs': {'missing': 'npc'}},
    {**initial_state(), 'unit_credit': {'numerator': 1, 'denominator': 0}},
    {**initial_state(), 'command_seq': 1},
])
def test_invalid_state_rejected_without_rewriting(saved, corruption):
    game, store, _deps = saved
    original = store._path(game.id).read_bytes()
    game.heavens_state = corruption
    with pytest.raises(ValueError):
        store.save(game)
    assert store._path(game.id).read_bytes() == original
    raw = json.loads(original)
    raw['heavens_state'] = corruption
    store._path(game.id).write_text(json.dumps(raw), encoding='utf-8')
    corrupted = store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        store.load(game.id)
    assert store._path(game.id).read_bytes() == corrupted


def test_views_and_previews_never_create_state_or_consume_rng(saved):
    game, store, deps = saved
    before = copy.deepcopy(game.to_dict())
    durable = store._path(game.id).read_bytes()
    with patch.object(store, 'save', side_effect=AssertionError('query saved')):
        for view in ('known', 'opportunities', 'tasks', 'history'):
            result = operations.view(deps, game.id, view)
            assert result['records'] == [] and result['next_command_seq'] == 1
            result['records'].append('caller mutation')
        assert operations.preview(deps, game.id, 'configure', None, {'watch': False})['years'] == 0
    assert game.to_dict() == before and store._path(game.id).read_bytes() == durable


@pytest.mark.parametrize('action,target,options', [
    ('unknown', None, {}), ('observe', None, {}), ('maintain', None, {}),
    ('configure', 'hidden', {'watch': True}), ('configure', None, {'generation_enabled': True}),
    ('configure', None, {'reward': 100}), ('configure', None, {'watch': 1}),
    ('configure', None, {'watch': None}), ('configure', None, {}), ('configure', None, []),
])
def test_unsupported_commands_have_no_effects(saved, action, target, options):
    game, store, deps = saved
    before = game.to_dict()
    durable = store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        operations.command(deps, game.id, 1, 0, action, target, options)
    assert game.to_dict() == before and store._path(game.id).read_bytes() == durable


def test_retry_normalization_revision_and_high_water_mark(saved):
    game, store, deps = saved
    # This contract consumer reads durable state afresh on each call.
    deps = HeavensDependencies(store.load, lambda: store, HeavensDefinitions, Mock(), Mock())
    options = {'watch': False, 'generation_enabled': False}
    first = operations.command(deps, game.id, 1, 0, 'configure', None, options)
    saved_bytes = store._path(game.id).read_bytes()
    retry = operations.command(deps, game.id, 1, 0, 'configure', None, dict(reversed(list(options.items()))))
    assert first == retry and store._path(game.id).read_bytes() == saved_bytes
    retry['watch'] = True
    assert store.load(game.id).heavens_state['watch'] is False
    for seq, revision, opts, reason in [
        (1, 0, {'watch': True}, '参数不一致'), (1, 1, options, '参数不一致'),
        (3, 1, options, '下一连续'), (2, 0, options, '已过期'),
        (True, 1, options, '非负整数'),
    ]:
        with pytest.raises(ValueError, match=reason):
            operations.command(deps, game.id, seq, revision, 'configure', None, opts)
    for seq in range(2, 130):
        result = operations.command(deps, game.id, seq, 1, 'configure', None, options)
        assert result['revision'] == 1  # no-op commands don't advance state revision
    state = store.load(game.id).heavens_state
    assert len(state['receipts']) == 128 and state['command_seq'] == 129
    with pytest.raises(ValueError, match='回执已过期'):
        operations.command(deps, game.id, 1, 0, 'configure', None, options)
    validate_state(state)


def test_receipt_corruption_and_per_save_isolation(saved):
    game, store, _deps = saved
    deps = HeavensDependencies(store.load, lambda: store, HeavensDefinitions, Mock(), Mock())
    operations.command(deps, game.id, 1, 0, 'configure', None, {'watch': False})
    state = store.load(game.id).heavens_state
    for corruption in ('sequence', 'result', 'fingerprint'):
        invalid = copy.deepcopy(state)
        if corruption == 'sequence':
            invalid['receipts'][0]['command_seq'] = 2
        elif corruption == 'result':
            invalid['receipts'][0]['result']['watch'] = True
        else:
            invalid['receipts'][0]['fingerprint'] = 'not a digest'
        with pytest.raises(ValueError):
            validate_state(invalid)
    second = GameState('another-save', game.seed, Player('另一修士', 'none'), '', '')
    store.save(second)
    assert operations.view(deps, second.id, 'known')['next_command_seq'] == 1
    operations.command(deps, second.id, 1, 0, 'configure', None, {'watch': True})
    assert store.load(game.id).heavens_state['watch'] is False
    assert store.load(second.id).heavens_state['watch'] is True


@pytest.mark.parametrize('failure', ['execution', 'save', 'replace'])
def test_failed_segment_discards_whole_copy_and_can_retry(saved, failure):
    game, store, deps = saved
    before = copy.deepcopy(game.to_dict())
    durable = store._path(game.id).read_bytes()

    def mutate_and_fail(work, *_args):
        work.player.hp = 0
        work.player.mp = 0
        work.rng_state = 'not committed'
        work.intrigue_state['test'] = {'changed': True}
        raise OSError('injected failure')

    context = (patch.object(operations, 'apply_configuration', side_effect=mutate_and_fail)
               if failure == 'execution' else patch.object(store, 'save', side_effect=mutate_and_fail)
               if failure == 'save' else patch.object(Path, 'replace', side_effect=OSError('injected failure')))
    with context, pytest.raises(OSError, match='injected'):
        operations.command(deps, game.id, 1, 0, 'configure', None, {'watch': False})
    assert game.to_dict() == before
    assert store._path(game.id).read_bytes() == durable
    assert not list(store.directory.glob('*.tmp'))
    result = operations.command(deps, game.id, 1, 0, 'configure', None, {'watch': False})
    assert result['command_seq'] == 1 and result['revision'] == 1
    assert store.load(game.id).rng_state == before['rng_state']


@pytest.fixture
def engine(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    key = engine.create_game('诸天', 'supreme_metal', 'dao', 42, preset_id='core')['id']
    engine._load(key)
    return engine, key


def test_engine_cache_publication_and_failed_save_invalidation(engine):
    engine, key = engine
    with request_scope(engine):
        old = engine._load(key)
        original = copy.deepcopy(old.to_dict())
        result = engine.heavens_command(key, 1, 0, 'configure', options={'watch': False})
        assert old.to_dict() == original
        assert engine._load(key) is not old
        assert engine.heavens_view(key)['revision'] == result['revision'] == 1
        with patch.object(engine.store, 'save', side_effect=OSError('save failure')):
            with pytest.raises(OSError):
                engine.heavens_command(key, 2, 1, 'configure', options={'watch': True})
        assert key not in request_games(engine)
        assert engine._load(key).heavens_state['watch'] is False
        assert engine.heavens_command(key, 1, 0, 'configure', options={'watch': False}) == result


def test_concurrent_retries_commit_once_and_late_store_binding(engine, tmp_path):
    engine, key = engine
    other = GameEngine(ROOT, engine.store.directory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(e.heavens_command, key, 1, 0, 'configure', None, {'watch': False})
                   for e in (engine, other)]
        assert futures[0].result() == futures[1].result()
    assert engine.store.load(key).heavens_state['command_seq'] == 1
    replacement = SaveStore(tmp_path / 'replacement')
    replacement.save(engine.store.load(key))
    old_store = engine.store
    engine.store = replacement
    engine.heavens_command(key, 2, 1, 'configure', options={'watch': True})
    assert replacement.load(key).heavens_state['watch'] is True
    assert old_store.load(key).heavens_state['watch'] is False


def test_closed_configuration_changes_no_old_state(engine):
    engine, key = engine
    with request_scope(engine):
        game = engine._load(key)
        before = copy.deepcopy(game.to_dict())
        engine.heavens_command(key, 1, 0, 'configure', options={'generation_enabled': False})
        after = engine._load(key).to_dict()
    before.pop('heavens_state')
    after.pop('heavens_state')
    assert before == after


def test_definitions_and_import_boundaries():
    framework = dict(id='heavens', kind='cross_world_system', enabled=False, member_worlds=['celestial'])
    validate_framework(framework, {'celestial', 'human'})
    validate_framework({**framework, 'enabled': True}, {'celestial', 'human'})
    for invalid in ({**framework, 'enabled': 'true'}, {**framework, 'member_worlds': ['missing']},
                    {**framework, 'kind': 'world'}):
        with pytest.raises(ValueError):
            validate_framework(invalid, {'celestial'})
    edges = [(f'cultivation_life.system.heavens.{part}', target, 1)
             for part in ('schema', 'definitions')
             for target in ('cultivation_life.models', 'cultivation_life.engine', 'cultivation_life.content_registry')]
    assert len(violations(edges)) == len(edges)
