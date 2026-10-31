"""Compare snapshot copying and complete HTTP requests on identical isolated saves."""
import argparse
import copy
from contextlib import contextmanager, nullcontext
import hashlib
from http.server import ThreadingHTTPServer
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
from cultivation_life import models, server
from cultivation_life.engine import GameEngine, engine_presentation
from cultivation_life.visual_assets import catalog_scope
from scripts.release_evidence import inputs_digest


def hashes(folder):
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob('*') if path.is_file()}


@contextmanager
def copying(mode):
    # The frozen AST contract verifies these boundaries differ only in copier
    # calls. No process-global monkeypatch of copy.deepcopy or rules is used.
    if mode == 'reference':
        with patch.object(models, 'copy_plain_data', copy.deepcopy, create=True), \
             patch.object(engine_presentation, 'copy_plain_data', copy.deepcopy, create=True):
            yield
    else:
        yield


def json_value(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def measure(callback, expected, runs, *, setup=lambda: None, project=lambda value: value,
            scope=nullcontext):
    samples = dict(reference=[], current=[])
    for repeat in range(runs + 1):
        for mode in (('reference', 'current') if repeat % 2 == 0 else ('current', 'reference')):
            with scope():
                state = setup()
                with copying(mode):
                    start = time.perf_counter()
                    result = callback(state)
                    elapsed = (time.perf_counter() - start) * 1000
            assert project(result) == expected, f'{mode} output mismatch'
            if repeat:
                samples[mode].append(round(elapsed, 3))
    medians = {key: round(statistics.median(values), 3) for key, values in samples.items()}
    return dict(samples_ms=samples, medians_ms=medians, outputs_equal=True,
        reduction_percent=round((1-medians['current']/medians['reference'])*100, 2))


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'input').exists() or (folder/'gold.json').exists():
        raise SystemExit('Fixtures exist; choose a new directory to retain the baseline')
    with copying('reference'):
        engine = GameEngine(ROOT, folder/'input/saves')
        identities = {preset: engine.create_game('快照基准', 'heavenly', 'dao', 280,
            preset_id=preset)['id'] for preset in ('core', 'true_immortal')}
        identity = engine.create_game('长战报基准', 'heavenly', 'dao', 280, preset_id='core')['id']
        game = engine.store.load(identity)
        # Extra ordinary JSON exercises large explicit view snapshots; no new
        # rules or production saves. Unknown report details remain untouched.
        game.last_combat_report = dict(kind='benchmark', rounds=[dict(index=n,
            details=[dict(actor=f'actor-{j}', events=['招式', n, j], damage=n+j)
                for j in range(12)]) for n in range(300)])
        engine.store.save(game)
        identities['large_report'] = identity
        for _ in range(2):
            for identity in identities.values():
                engine.get_game(identity, as_json=True)
        gold = {preset: dict(id=identity, model=engine.store.load(identity).to_dict(),
            view=json.loads(engine.get_game(identity, as_json=True).body),
            deferred_view=json.loads(engine.get_game(identity, as_json=True, defer_order_goods=True).body))
            for preset, identity in identities.items()}
    (folder/'gold.json').write_text(json.dumps(gold, ensure_ascii=False), encoding='utf-8')
    (folder/'baseline-inputs.json').write_text(json.dumps(dict(inputs_sha256=inputs_digest(ROOT),
        save_hashes=hashes(folder/'input')), indent=2), encoding='utf-8')


def audit(folder, runs):
    signature = inputs_digest(ROOT)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    gold = json.loads((folder/'gold.json').read_text(encoding='utf-8'))
    initial = json.loads((folder/'baseline-inputs.json').read_text(encoding='utf-8'))
    assert hashes(folder/'input') == initial['save_hashes']
    rows = []
    with tempfile.TemporaryDirectory(prefix='snapshot-http-', dir=ROOT/'build') as directory:
        location = Path(directory)
        shutil.copytree(folder/'input', location, dirs_exist_ok=True)
        engine = GameEngine(ROOT, location/'saves')
        @contextmanager
        def view_scope():
            # As in real requests, preparation shares the static catalog scope
            # warmed by session loading. Do not benchmark an unscoped shortcut.
            with engine.store.lock, catalog_scope():
                yield
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', location):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                before = hashes(location)
                for preset, expected in gold.items():
                    identity = expected['id']
                    raw = (location/'saves'/f'{identity}.json').read_text(encoding='utf-8')
                    def fetched(deferred):
                        suffix = '?fleet_goods=deferred' if deferred else ''
                        with urlopen(f'http://127.0.0.1:{http.server_port}/api/games/{identity}{suffix}') as response:
                            return json.loads(response.read())
                    row = dict(preset=preset,
                        model_decode=measure(lambda document: models.GameState.from_dict(document),
                            expected['model'], runs, setup=lambda: json.loads(raw), project=lambda game: game.to_dict()),
                        view_prepare=measure(lambda game: engine._dependencies.response.prepare_view(game),
                            expected['view'], runs, setup=lambda: engine._load(identity), project=json_value,
                            scope=view_scope),
                        http_full=measure(lambda _: fetched(False), expected['view'], runs),
                        http_deferred=measure(lambda _: fetched(True), expected['deferred_view'], runs))
                    rows.append(row)
                    print(json.dumps(row), flush=True)
                assert hashes(location) == before, 'Queries modified saves or account metadata'
            finally:
                http.shutdown(); http.server_close()
    assert hashes(folder/'input') == initial['save_hashes']
    assert inputs_digest(ROOT) == signature, 'Runtime changed during measurement'
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == script_hash
    report = dict(inputs_sha256=signature, baseline_inputs_sha256=initial['inputs_sha256'],
        script_sha256=script_hash, runs=runs, measurements=rows,
        full_models_and_http_views_equal=True, saves_and_metadata_unchanged=True,
        scope='Same process, alternating order after one warmup; production GC retained. Reference substitutes builtin deepcopy only at AST-verified boundaries. HTTP timings include loopback I/O and client JSON decode. View preparation loads outside the timer. Isolated full-DLC seed-280 core/true-immortal and synthetic long-report saves; no native-device claims.')
    (folder/'performance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(report=str(folder/'performance.json'))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'build/architecture-batch3-20261031')
    parser.add_argument('--runs', type=int, default=21)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    folder = args.output_dir.resolve()
    if args.prepare or args.prepare_only:
        prepare(folder)
    if not args.prepare_only:
        audit(folder, args.runs)
