"""Interleaved reference/current decoding and cold/warm save-summary measurements."""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import content_identifiers, models, server
from cultivation_life.engine import GameEngine
from cultivation_life.storage import SaveStore
from scripts.release_evidence import inputs_digest


def reference(name, filename):
    spec = importlib.util.spec_from_file_location('cultivation_life.' + name, ROOT / 'tests/fixtures' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hashes(folder):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


def paired(callbacks, expected, runs, project=lambda value: value):
    samples = {key: [] for key in callbacks}
    keys = list(callbacks)
    for repeat in range(runs + 1):
        for key in (keys if repeat % 2 == 0 else keys[::-1]):
            start = time.perf_counter()
            result = callbacks[key]()
            elapsed = (time.perf_counter() - start) * 1000
            assert project(result) == expected, f'Reference/current output differs: {key}'
            if repeat:
                samples[key].append(round(elapsed, 3))
    medians = {key: round(statistics.median(values), 3) for key, values in samples.items()}
    return dict(samples_ms=samples, medians_ms=medians, outputs_equal=True,
                reduction_percent=round((1-medians['current']/medians['reference'])*100, 2))


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'input').exists() or (folder / 'gold.json').exists():
        raise SystemExit('Fixtures already exist; use a new output directory to preserve the baseline')
    old = reference('_prepare_reference_ids', 'content_identifiers_332.py')
    with patch.object(models, 'normalize_content_references', old.normalize_content_references):
        engine = GameEngine(ROOT, folder / 'input/saves')
        identities = {preset: engine.create_game('第二批基准', 'heavenly', 'dao', 280,
                      preset_id=preset)['id'] for preset in ('core', 'true_immortal')}
        for _ in range(2):
            for identity in identities.values():
                engine.get_game(identity)
        gold = {preset: dict(id=identity, model=engine.store.load(identity).to_dict(),
                view=json.loads(engine.get_game(identity, as_json=True).body))
                for preset, identity in identities.items()}
    (folder / 'gold.json').write_text(json.dumps(gold, ensure_ascii=False), encoding='utf-8')
    (folder / 'baseline-inputs.json').write_text(json.dumps(dict(
        inputs_sha256=inputs_digest(ROOT), save_hashes=hashes(folder / 'input'),
        scope='Prepared with the frozen reference normalizer under the current unchanged game rules.'), indent=2), encoding='utf-8')


def audit(folder, runs):
    signature = inputs_digest(ROOT)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    old_ids = reference('_benchmark_old_ids', 'content_identifiers_332.py')
    old_store = reference('_benchmark_old_list', 'storage_list_332.py')
    gold = json.loads((folder / 'gold.json').read_text(encoding='utf-8'))
    fixture_hashes = hashes(folder / 'input')
    initial = json.loads((folder / 'baseline-inputs.json').read_text(encoding='utf-8'))
    assert fixture_hashes == initial['save_hashes'], 'Original fixtures were modified'
    rows = []
    with tempfile.TemporaryDirectory(prefix='storage-benchmark-', dir=ROOT / 'build') as directory:
        location = Path(directory)
        shutil.copytree(folder / 'input', location, dirs_exist_ok=True)
        engine = GameEngine(ROOT, location / 'saves')
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', location):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                before = hashes(location)
                for preset, expected in gold.items():
                    gid = expected['id']
                    document = json.loads((location / 'saves' / f'{gid}.json').read_text(encoding='utf-8'))
                    def decoded(fn, export=True):
                        with patch.object(models, 'normalize_content_references', fn):
                            game = engine.store.load(gid)
                            return game.to_dict() if export else game
                    def fetched(fn):
                        with patch.object(models, 'normalize_content_references', fn):
                            with urlopen(f'http://127.0.0.1:{http.server_port}/api/games/{gid}') as response:
                                return json.loads(response.read())
                    row = dict(preset=preset,
                        normalize=paired({'reference': lambda: old_ids.normalize_content_references(document),
                                          'current': lambda: content_identifiers.normalize_content_references(document)},
                                         old_ids.normalize_content_references(document), runs),
                        store_load=paired({'reference': lambda: decoded(old_ids.normalize_content_references, False),
                                           'current': lambda: decoded(content_identifiers.normalize_content_references, False)},
                                          expected['model'], runs, project=lambda game: game.to_dict()),
                        load_and_project_model=paired({'reference': lambda: decoded(old_ids.normalize_content_references),
                                                       'current': lambda: decoded(content_identifiers.normalize_content_references)},
                                                      expected['model'], runs),
                        http_get=paired({'reference': lambda: fetched(old_ids.normalize_content_references),
                                         'current': lambda: fetched(content_identifiers.normalize_content_references)},
                                        expected['view'], runs))
                    rows.append(row)
                    print(json.dumps(row), flush=True)
                assert hashes(location) == before, 'Steady reads modified saves/metadata'
            finally:
                http.shutdown(); http.server_close()
        listing = []
        probe = location / 'list-probe'
        probe.mkdir()
        # Valid schema-11 copies, differing only in their test IDs; not user saves.
        template = document
        for count in (1, 10, 30):
            for index in range(count):
                path = probe / f'probe-{index}.json'
                if not path.exists():
                    path.write_text(json.dumps(dict(template, id=f'probe-{index}'), ensure_ascii=False,
                                               separators=(',', ':')), encoding='utf-8')
            old, current = old_store.SaveStore(probe), SaveStore(probe)
            expected = old.list_games()
            current.list_games()
            original = hashes(probe)
            row = dict(saves=count, bytes=sum(p.stat().st_size for p in probe.glob('*.json')),
                warm=paired({'reference': old.list_games, 'current': current.list_games}, expected, runs),
                cold_index=paired({'reference': lambda: old_store.SaveStore(probe).list_games(),
                                   'current': lambda: SaveStore(probe).list_games()}, expected, runs))
            assert hashes(probe) == original
            listing.append(row)
            print(json.dumps(row), flush=True)
    assert hashes(folder / 'input') == fixture_hashes
    assert signature == inputs_digest(ROOT), 'Runtime inputs changed during benchmark'
    assert script_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report = dict(inputs_sha256=signature, benchmark_script_sha256=script_hash, runs=runs,
        measurements=rows, list_games=listing, full_models_and_http_views_equal=True,
        saves_and_metadata_unchanged=True,
        scope='Same-process alternating order, medians after one warm-up. store_load excludes the model export used for checking; load_and_project_model includes it. HTTP includes loopback read/decode; reference swaps only the frozen old normalizer. Listing uses frozen old/current stores on identical files. Cold index means a fresh in-memory index with OS file cache warm; hashing still reads all save bytes. Isolated full-DLC seed-280 saves, not native-device or universal latency claims.')
    (folder / 'performance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'report': str(folder / 'performance.json')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/architecture-batch2-20261031')
    parser.add_argument('--runs', type=int, default=9)
    parser.add_argument('--prepare', action='store_true', help='Create reference fixtures in a new output directory first')
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    if args.prepare:
        prepare(args.output_dir.resolve())
    audit(args.output_dir.resolve(), args.runs)
