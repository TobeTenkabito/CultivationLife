"""Profile architecture costs with isolated saves; prototypes never enter runtime."""
from __future__ import annotations

import argparse
import copy
import cProfile
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cultivation_life.content_identifiers import normalize_content_references
from cultivation_life.engine import GameEngine
from cultivation_life.engine.presentation.projection import PreparedGameView, project_game
from cultivation_life.engine.transactions import request_scope
from cultivation_life.models import GameState
from cultivation_life.storage import SaveStore
from cultivation_life.version import BASE_GAME_VERSION
from scripts.release_evidence import inputs_digest


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def timed(callback, samples):
    callback()  # Warm up outside the measured samples.
    values = []
    for _ in range(samples):
        start = time.perf_counter()
        callback()
        values.append(round((time.perf_counter() - start) * 1000, 3))
    return {'median_ms': round(statistics.median(values), 3), 'samples_ms': values}


def profile(output, name, callback):
    profiler = cProfile.Profile()
    profiler.runcall(callback)
    profiler.dump_stats(str(output / f'{name}.prof'))


def file_hashes(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file()}


def measure(engine, preset, samples, output, annual):
    view = engine.create_game('架构审计', 'heavenly', 'dao', 280, preset_id=preset)
    gid = view['id']

    def response():
        with request_scope(engine):
            return engine.get_game(gid)

    view = response()
    response()  # Finish legitimate first-observation preparation before purity checks.
    before = file_hashes(engine.store.directory.parent)
    result = {'preset': preset, 'get_game': timed(response, samples)}
    profile(output, f'{preset}-get', response)
    after = file_hashes(engine.store.directory.parent)
    assert before == after, 'Repeated prepared GET changed isolated persistence'
    result['steady_get_persistence_unchanged'] = True

    game = engine.store.load(gid)
    document = game.to_dict()
    raw_save = encode(document)
    prepared = PreparedGameView(view)
    payload = encode(view)
    stages = {
        'json_save_decode': lambda: json.loads(raw_save),
        'normalize_references': lambda: normalize_content_references(document),
        'hydrate_game': lambda: GameState.from_dict(document),
        'clone_game': lambda: copy.deepcopy(game),
        'game_to_dict': game.to_dict,
        'freeze_view': lambda: PreparedGameView(view),
        'thaw_view': lambda: project_game(prepared),
        'json_view_encode': lambda: encode(view),
        'current_view_codec': lambda: encode(project_game(PreparedGameView(view))),
        'bytes_snapshot_prototype': lambda: encode(view),
        'gzip_level1': lambda: gzip.compress(payload, compresslevel=1, mtime=0),
        'store_load': lambda: engine.store.load(gid),
    }
    result['stages'] = {name: timed(callback, samples) for name, callback in stages.items()}
    # HTTP-only prototype: bytes are detached and immutable, but JSON converts
    # tuple/list and integer/string keys. It cannot replace the Python dict API.
    snapshot = encode(view)
    assert json.loads(snapshot) == json.loads(encode(project_game(prepared)))
    original_name = view['player']['name']
    view['player']['name'] = '修改调用方数据'
    assert json.loads(snapshot)['player']['name'] == original_name
    assert project_game(prepared)['player']['name'] == original_name
    view['player']['name'] = original_name
    result['prototype_json_equivalent_and_detached'] = True
    result['save_bytes'] = len(raw_save)
    result['payload_bytes'] = len(payload)
    result['gzip_level1_bytes'] = len(gzip.compress(payload, compresslevel=1, mtime=0))
    result['largest_response_fields'] = sorted(
        ({'field': key, 'bytes': len(encode(value))} for key, value in view.items()),
        key=lambda row: row['bytes'], reverse=True)[:12]

    if annual:
        # Match the existing economic benchmark's uninterrupted rest scenario.
        # This is a bounded real controller profile, not a gameplay equivalence test.
        game = engine.store.load(gid)
        game.pending_event = None
        game.player.next_tribulation_age = None
        game.settings['silent_events'] = True
        if game.heavenly_court:
            game.heavenly_court['open_election'] = None
        engine.store.save(game)
        start_age = game.player.age
        start = time.perf_counter()
        with patch.object(engine, '_advance_guixu_calendar', return_value=False):
            profile(output, f'{preset}-annual', lambda: engine.advance(gid, 'rest', 1))
        elapsed = (time.perf_counter() - start) * 1000
        final_document = json.loads(engine.store._path(gid).read_text(encoding='utf-8'))
        result['annual_profile'] = {
            'elapsed_with_profiler_ms': round(elapsed, 3),
            'years': final_document['player']['age'] - start_age,
            'scope': 'One real rest unit; pending events/election/tribulation cleared; Guixu interruption disabled. Profiler overhead included.',
        }
        try:
            engine.store.load(gid)
            result['annual_profile']['reload_ok'] = True
        except ValueError as error:
            failure = output / f'{preset}-annual-reload-failure.json'
            failure.write_bytes(encode(final_document))
            result['annual_profile'].update(reload_ok=False, error=str(error),
                                           evidence=str(failure))
    result['_document'] = document
    return result


def audit(output, samples, annual):
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='architecture-audit-', dir=ROOT / 'build') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        rows = []
        for preset in ('core', 'true_immortal'):
            row = measure(engine, preset, samples, output, annual)
            document = row.pop('_document')
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        index_store = SaveStore(Path(folder) / 'list-probe')
        listing = []
        for count in (1, 10, 30):
            for index in range(count):
                target = index_store.directory / f'probe-{index}.json'
                if not target.exists():
                    target.write_bytes(encode(dict(document, id=f'probe-{index}')))
            listing.append({'saves': count, 'total_bytes': sum(
                path.stat().st_size for path in index_store.directory.glob('*.json')),
                **timed(index_store.list_games, samples)})
    assert signature == inputs_digest(ROOT), 'Runtime inputs changed during audit'
    assert script_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'Audit script changed during measurement'
    report = {
        'version': BASE_GAME_VERSION, 'inputs_sha256': signature,
        'audit_script_sha256': script_hash, 'samples': samples,
        'measurements': rows, 'list_games_scaling': listing,
        'scope': 'Warm-cache desktop timings, isolated seed-280 full-DLC saves. Stage medians are microbenchmarks, not additive GET percentages. Bytes prototype only validates HTTP JSON equality/isolation; legacy tuple semantics and preparation/commit orchestration remain separate requirements. No production save or runtime code changed.',
    }
    (output / 'architecture.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(output / 'architecture.json'),
                      'list_games_scaling': listing}, ensure_ascii=False), flush=True)
    return all(row.get('annual_profile', {}).get('reload_ok', True) for row in rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'build/architecture-audit')
    parser.add_argument('--samples', type=int, default=7)
    parser.add_argument('--annual', action='store_true', help='Also profile one rest unit per preset')
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples must be positive')
    if not audit(args.output_dir.resolve(), args.samples, args.annual):
        raise SystemExit('Annual action produced an unloadable isolated save; see report')
