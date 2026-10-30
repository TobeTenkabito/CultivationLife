"""Differential decoding and non-authoritative, content-validated summary indexes."""
import copy
import hashlib
import importlib.util
import json
import os
import gc
import weakref
from pathlib import Path
import random
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from cultivation_life import content_identifiers as references
from cultivation_life import storage
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Item, Player

ROOT = Path(__file__).resolve().parents[1]


def released(name, filename):
    spec = importlib.util.spec_from_file_location('cultivation_life.' + name, ROOT / 'tests/fixtures' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old_references = released('_reference_ids_batch2', 'content_identifiers_332.py')
old_storage = released('_reference_list_batch2', 'storage_list_332.py')


@pytest.mark.parametrize('filename,expected', [
    ('content_identifiers_332.py', '23034e1d33ec5a3f22a798459d315c2ffba326e7445b217759fd40b485d9b3d5'),
    ('storage_list_332.py', '437457198fbdf9f8511b3e882342f9e46601afda44a328295b806dd3b58aa633'),
])
def test_released_oracles_are_unchanged(filename, expected):
    assert hashlib.sha256((ROOT / 'tests/fixtures' / filename).read_bytes().replace(b'\r\n', b'\n')).hexdigest() == expected


def test_reference_normalization_matches_released_random_documents():
    rng = random.Random(332)
    keys = ['id', 'name', 'item', 'inputs', 'description', 'items', 'value',
            'TECH_COMMON_CORE', 'nascent_incense', 'arbitrary', 'history']
    strings = [*references.LEGACY_CONTENT_IDS, *references.LEGACY_CONTENT_IDS.values(),
               'technique_manual::TECH_COMMON_CORE::lv7', 'unknown', '自命名 TECH_COMMON_CORE']
    def tree(depth):
        if depth == 0 or rng.randrange(3) == 0:
            return rng.choice([None, True, 12, 1.5, *strings])
        if rng.randrange(2):
            return [tree(depth - 1) for _ in range(rng.randrange(5))]
        return {rng.choice(keys): tree(depth - 1) for _ in range(rng.randrange(5))}
    for _ in range(600):
        source = tree(4)
        before = copy.deepcopy(source)
        field = rng.choice(keys)
        try:
            expected = old_references.normalize_content_references(source, field)
        except ValueError as error:
            with pytest.raises(ValueError) as actual:
                references.normalize_content_references(source, field)
            assert str(actual.value) == str(error)
        else:
            actual = references.normalize_content_references(source, field)
            assert actual == expected
            if expected is source:
                assert actual is source
        assert source == before


def test_equal_distinct_strings_and_untouched_branches_keep_identity():
    first = ''.join(['canonical', '-item'])
    second = ''.join(['canonical-', 'item'])
    assert first == second and first is not second
    source = [{'id': first}, {'id': second}, {'name': 'nascent_incense'}, (['nascent_incense'],)]
    assert references.normalize_content_references(source) is source
    changed = {'rows': source, 'item': 'nascent_incense', 'text': 'TECH_COMMON_CORE'}
    actual = references.normalize_content_references(changed)
    assert actual['rows'] is source and actual['text'] is changed['text']
    assert changed['item'] == 'nascent_incense' and actual['item'] == 'purple_mansion_incense'


def test_memo_boundaries_alias_changes_and_collision_rejection():
    source = {f'unknown-{i}': {'id': f'custom-{i}'} for i in range(5000)}
    source['item'] = 'nascent_incense'
    assert references.normalize_content_references(source) == old_references.normalize_content_references(source)
    with patch.dict(references.LEGACY_CONTENT_IDS, {'temporary-id': 'first'}):
        assert references.normalize_content_references({'id': 'temporary-id'})['id'] == 'first'
        references.LEGACY_CONTENT_IDS['temporary-id'] = 'second'
        assert references.normalize_content_references({'id': 'temporary-id'})['id'] == 'second'
    collision = {'inputs': {'nascent_incense': 1, 'purple_mansion_incense': 9}}
    before = copy.deepcopy(collision)
    with pytest.raises(ValueError, match='不能自动覆盖'):
        references.normalize_content_references(collision)
    assert collision == before


def test_standalone_item_and_player_decoders_still_normalize():
    assert Item.from_dict({'id': 'nascent_incense', 'name': '自定', 'quantity': 7}).id == 'purple_mansion_incense'
    player = Player.from_dict({'name': '自定', 'spirit_root': 'none', 'inventory': [
        {'id': 'nascent_incense', 'name': '自定', 'quantity': 7}]})
    assert player.inventory[0].id == 'purple_mansion_incense'


def test_normalization_does_not_retain_key_objects_until_cyclic_gc():
    class Key(str):
        pass
    enabled = gc.isenabled()
    gc.disable()
    try:
        key = Key('normalizer-scope-key')
        reference = weakref.ref(key)
        source = {key: [1, 2]}
        assert references.normalize_content_references(source) is source
        del key, source
        assert reference() is None
    finally:
        if enabled:
            gc.enable()


def document(identity='alpha', name='甲', version=11):
    return dict(id=identity, version=version, updated_at='2026-10-31',
        player=dict(name=name, age=90, realm_index=3, layer=2, world='human', path='dao', alive=True),
        authored_techniques={'own': {'one': {}}})


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def assert_list_matches(store):
    expected = old_storage.SaveStore(store.directory).list_games()
    actual = store.list_games()
    assert actual == expected
    assert [list(row) for row in actual] == [list(row) for row in expected]
    return actual


def test_summary_index_matches_all_fields_order_and_invalid_documents(tmp_path):
    store = storage.SaveStore(tmp_path)
    for index, version in enumerate([1, 9, 10, 11, 12, True, None, '11']):
        put(tmp_path / f'{index}.json', document(str(index), version=version))
    put(tmp_path / 'unknown-world.json', dict(document('unknown'), player={**document()['player'], 'world': 'unknown-world'}))
    (tmp_path / 'broken.json').write_bytes(b'{broken')
    (tmp_path / 'bom.json').write_bytes(b'\xef\xbb\xbf' + json.dumps(document('bom')).encode())
    put(tmp_path / 'global_metadata.json', {'schema_version': 1, 'achievements': {}})
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    for _ in range(2):
        rows = assert_list_matches(store)
        assert next(row for row in rows if row['id'] == 'unknown')['world_name'] == '未知界面'
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_same_size_same_mtime_edit_and_atomic_replacement_are_detected(tmp_path):
    store = storage.SaveStore(tmp_path)
    path = tmp_path / 'alpha.json'
    put(path, document(name='甲'))
    assert_list_matches(store)
    info = path.stat()
    put(path, document(name='乙', version=10))
    assert path.stat().st_size == info.st_size
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    row = assert_list_matches(store)[0]
    assert row['name'] == '乙' and not row['compatible']
    replacement = tmp_path / 'replacement.tmp'
    put(replacement, document(name='丙'))
    os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
    replacement.replace(path)
    assert assert_list_matches(store)[0]['name'] == '丙'


def test_changes_deletion_repair_and_multiple_stores(tmp_path):
    first, second = storage.SaveStore(tmp_path), storage.SaveStore(tmp_path)
    path = tmp_path / 'alpha.json'
    put(path, document())
    assert first.lock is second.lock
    assert_list_matches(first); assert_list_matches(second)
    second._write_document('alpha', document(name='新的'))
    assert assert_list_matches(first)[0]['name'] == '新的'
    path.write_bytes(b'{bad')
    assert_list_matches(first); assert_list_matches(first)
    put(path, document(name='修复'))
    assert assert_list_matches(first)[0]['name'] == '修复'
    second.delete('alpha')
    assert first.list_games() == [] and not first._summary_index
    put(path, document())
    assert assert_list_matches(first)[0]['id'] == 'alpha'


def test_cached_results_detach_nested_values_and_refresh_labels(tmp_path, monkeypatch):
    from cultivation_life.content_registry import WORLD_SYSTEMS, PATH_NAMES
    store = storage.SaveStore(tmp_path)
    put(tmp_path / 'alpha.json', document(name=['甲', {'field': 'value'}]))
    original = assert_list_matches(store)
    original[0]['name'][1]['field'] = 'changed'
    assert assert_list_matches(store)[0]['name'][1]['field'] == 'value'
    monkeypatch.setitem(WORLD_SYSTEMS['world_names'], 'human', '新显示名称')
    monkeypatch.setitem(PATH_NAMES, 'dao', '新道途名')
    row = assert_list_matches(store)[0]
    assert row['world_name'] == '新显示名称' and row['path_name'] == '新道途名'
    monkeypatch.setattr(storage, 'migration_path', lambda version: (_ for _ in ()).throw(ValueError('临时结构规则')))
    assert store.list_games()[0]['incompatibility'] == '临时结构规则'


def test_cache_is_bounded_and_oversize_metadata_is_not_rejected(tmp_path, monkeypatch):
    store = storage.SaveStore(tmp_path)
    monkeypatch.setattr(store, '_SUMMARY_ENTRIES', 3)
    monkeypatch.setattr(store, '_SUMMARY_TOTAL_BYTES', 650)
    for index in range(8):
        put(tmp_path / f'{index}.json', document(str(index)))
    for _ in range(2):
        assert len(assert_list_matches(store)) == 8
        assert len(store._summary_index) <= 3 and store._summary_bytes <= 650
        assert store._summary_bytes == sum(len(e.payload) for e in store._summary_index.values() if e.payload is not None)
    put(tmp_path / 'large.json', document('large', name='字' * 20000))
    assert len(assert_list_matches(store)) == 9
    assert 'large.json' not in store._summary_index


def test_index_does_not_bypass_reads_or_load_validation(tmp_path):
    store = storage.SaveStore(tmp_path)
    path = tmp_path / 'alpha.json'
    put(path, document())
    store.list_games()
    with patch.object(Path, 'read_bytes', side_effect=PermissionError('denied')):
        with pytest.raises(PermissionError):
            store.list_games()
    # A summary-compatible but invalid game still goes through the real decoder.
    with pytest.raises((KeyError, ValueError, TypeError)):
        store.load('alpha')
    for version in range(1, 11):
        put(path, document(version=version))
        raw = path.read_bytes()
        assert not store.list_games()[0]['compatible']
        with pytest.raises(ValueError, match='仅支持结构 11'):
            store.load('alpha')
        assert path.read_bytes() == raw


def test_warm_index_avoids_full_json_decoding_and_prunes_disappeared_files(tmp_path):
    store = storage.SaveStore(tmp_path)
    value = dict(document(), unused=['large payload'] * 10000)
    put(tmp_path / 'alpha.json', value)
    store.list_games()
    loads = json.loads
    sizes = []
    def observed(raw, *args, **kwargs):
        sizes.append(len(raw))
        return loads(raw, *args, **kwargs)
    with patch.object(storage.json, 'loads', observed):
        assert len(store.list_games()) == 1
    assert sizes and max(sizes) < store._SUMMARY_ENTRY_BYTES
    (tmp_path / 'alpha.json').unlink()
    assert store.list_games() == [] and store._summary_bytes == 0


def test_failed_atomic_save_keeps_old_file_and_summary(tmp_path):
    store = storage.SaveStore(tmp_path)
    store._write_document('alpha', document())
    expected = store.list_games()
    raw = (tmp_path / 'alpha.json').read_bytes()
    entry = store._summary_index['alpha.json']
    with patch.object(Path, 'replace', side_effect=OSError('commit failed')):
        with pytest.raises(OSError, match='commit failed'):
            store._write_document('alpha', document(name='未提交'))
    assert (tmp_path / 'alpha.json').read_bytes() == raw
    assert store.list_games() == expected and store._summary_index['alpha.json'] is entry
    assert not list(tmp_path.glob('*.tmp'))


def test_index_maintenance_cannot_change_save_or_delete_commit_results(tmp_path):
    store = storage.SaveStore(tmp_path)
    store._write_document('alpha', document())
    store.list_games()
    # Invalidation happens on the next read's byte comparison. A metadata
    # failure cannot make an already committed save/deletion report failure.
    with patch.object(store, '_discard_summary', side_effect=RuntimeError('index unavailable')):
        store._write_document('alpha', document(name='已提交'))
        store.delete('alpha')
    assert not (tmp_path / 'alpha.json').exists()
    assert store.list_games() == []


def test_concurrent_readers_and_second_store_writes_never_publish_partial_metadata(tmp_path):
    first, second = storage.SaveStore(tmp_path), storage.SaveStore(tmp_path)
    first._write_document('alpha', document())
    def writer():
        for number in range(20):
            second._write_document('alpha', document(name=f'第{number}版'))
    def reader(store):
        for _ in range(30):
            rows = store.list_games()
            assert len(rows) == 1 and rows[0]['id'] == 'alpha' and rows[0]['compatible']
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(writer), pool.submit(reader, first), pool.submit(reader, second)]
        for future in futures:
            future.result()
    assert assert_list_matches(first)[0]['name'] == '第19版'


def test_file_removed_between_enumeration_and_read_is_pruned(tmp_path):
    store = storage.SaveStore(tmp_path)
    put(tmp_path / 'alpha.json', document())
    store.list_games()
    with patch.object(Path, 'read_bytes', side_effect=FileNotFoundError('external deletion')):
        assert store.list_games() == [] and not store._summary_index
    assert len(assert_list_matches(store)) == 1
