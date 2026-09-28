import base64
import copy
import json
import time
import zlib
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.save_transfer import export_snapshot, preview_snapshot, import_snapshot, decode_snapshot
from cultivation_life.storage import SaveStore
from cultivation_life.version import BASE_GAME_VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def snapshot(tmp_path):
    engine = GameEngine(ROOT, tmp_path/'source')
    made = engine.create_game('卷中人', 'supreme_wood', 'dao', seed=1450)
    return engine.store, made['id'], SaveStore(tmp_path/'target')


def encode(document):
    return base64.b64encode(zlib.compress(json.dumps(document).encode())).decode()


def test_lossless_roundtrip_keeps_rng_dlc_and_identity(snapshot):
    source, game_id, target = snapshot
    data = json.loads(source._path(game_id).read_bytes())
    data['opaque_mod_state'] = {'preserved': [True, '不能丢失', {'nested': 41}]}
    source._path(game_id).write_text(json.dumps(data), encoding='utf-8')
    exported = export_snapshot(source, game_id, [{'id':'example', 'version':'1.0.0', 'status':'loaded'}])
    preview = preview_snapshot(target, exported['payload'])
    assert preview['name'] == '卷中人' and preview['existing_hash'] is None
    assert preview['missing_extensions'] == ['example']
    import_snapshot(target, exported['payload'], None)
    assert json.loads(target._path(game_id).read_bytes()) == data
    assert source.load(game_id).rng_state == target.load(game_id).rng_state
    assert len(target.list_games()) == 1


def test_existing_save_requires_matching_preview_and_backs_up(snapshot):
    source, game_id, target = snapshot
    exported = export_snapshot(source, game_id)
    import_snapshot(target, exported['payload'], None)
    with pytest.raises(ValueError, match='发生变化'):
        import_snapshot(target, exported['payload'], None)
    preview = preview_snapshot(target, exported['payload'])
    old = target._path(game_id).read_bytes()
    import_snapshot(target, exported['payload'], preview['existing_hash'])
    backups = list((target.directory.parent/'save-backups').glob('*.json'))
    assert len(backups) == 1 and backups[0].read_bytes() == old
    assert len(target.list_games()) == 1


def test_export_does_not_migrate_or_touch_original(snapshot):
    source, game_id, _ = snapshot
    original = source._path(game_id).read_bytes()
    export_snapshot(source, game_id)
    assert source._path(game_id).read_bytes() == original


@pytest.mark.parametrize('mutation', ['future', 'path', 'rank', 'rng', 'missing_player', 'wrong_format'])
def test_invalid_data_never_creates_save(snapshot, mutation):
    source, game_id, target = snapshot
    doc, _ = decode_snapshot(export_snapshot(source, game_id)['payload'])
    if mutation == 'future': doc['game_version'] = '999.0.0'
    elif mutation == 'path': doc['save']['id'] = '../../escape'
    elif mutation == 'rank': doc['save']['player']['realm_index'] = 900
    elif mutation == 'rng': doc['save']['rng_state'] = '__import__("os").system("echo no")'
    elif mutation == 'missing_player': del doc['save']['player']
    else: doc['format'] = 'another-game'
    with pytest.raises(ValueError): import_snapshot(target, encode(doc), None)
    assert not list(target.directory.glob('*.json'))


def test_truncated_trailing_and_oversized_compression_rejected(snapshot, monkeypatch):
    import cultivation_life.save_transfer as module
    source, game_id, target = snapshot
    payload = export_snapshot(source, game_id)['payload']
    packed = base64.b64decode(payload)
    for bad in [packed[:-1], packed + b'extra']:
        with pytest.raises(ValueError): import_snapshot(target, base64.b64encode(bad).decode(), None)
    monkeypatch.setattr(module, 'MAX_RAW', 1024)
    with pytest.raises(ValueError, match='解压'):
        import_snapshot(target, base64.b64encode(zlib.compress(b' ' * 100_000)).decode(), None)
    assert not list(target.directory.glob('*.json'))


def test_large_ten_mb_journey_is_compressed_and_restored(snapshot):
    source, game_id, target = snapshot
    data = json.loads(source._path(game_id).read_bytes())
    template = data['history'][0]
    data['history'] = [{**copy.deepcopy(template), 'age': index,
                        'summary': f'第{index}年，修士于山门往返、闭关、游历，记录功法与人间事。' * 8,
                        'state_diff': {'npc_id': f'npc_{index % 1000}', 'opportunity': index * 3.2}}
                       for index in range(12000)]
    original = json.dumps(data, ensure_ascii=False, indent=2).encode()
    assert len(original) >= 10_000_000
    source._path(game_id).write_bytes(original)
    started = time.perf_counter()
    exported = export_snapshot(source, game_id)
    assert exported['packed_bytes'] < len(original) * .3
    import_snapshot(target, exported['payload'], None)
    assert json.loads(target._path(game_id).read_bytes()) == data
    print(f"Large save: {len(original)} -> {exported['packed_bytes']} bytes; {time.perf_counter()-started:.2f}s roundtrip")
