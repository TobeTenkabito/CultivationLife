"""Compare real HTTP game views using the same isolated saves and full JSON."""
import argparse
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
from contextlib import nullcontext
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.release_evidence import inputs_digest


def hashes(folder):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


def benchmark(output, phase, runs):
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fixture = output / 'input'
    with tempfile.TemporaryDirectory(prefix='http-views-', dir=ROOT / 'build') as directory:
        folder = Path(directory)
        if phase == 'optimized':
            shutil.copytree(fixture, folder, dirs_exist_ok=True)
        engine = GameEngine(ROOT, folder / 'saves')
        identities = {}
        if phase == 'baseline':
            for preset in ('core', 'true_immortal'):
                identities[preset] = engine.create_game('HTTP基准', 'heavenly', 'dao',
                                                       280, preset_id=preset)['id']
            for identity in identities.values():
                engine.get_game(identity)
            shutil.copytree(folder, fixture)
            (output / 'identities.json').write_text(json.dumps(identities), encoding='utf-8')
        else:
            identities = json.loads((output / 'identities.json').read_text(encoding='utf-8'))
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', folder):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            def fetch(path):
                start = time.perf_counter()
                with urlopen(f'http://127.0.0.1:{http.server_port}{path}') as response:
                    body = response.read()
                return json.loads(body), len(body), (time.perf_counter() - start) * 1000
            try:
                before = hashes(folder)
                rows = []
                for preset, identity in identities.items():
                    expected_path = output / f'{preset}-expected.json'
                    if phase == 'baseline':
                        expected = fetch(f'/api/games/{identity}')[0]
                        expected_path.write_text(json.dumps(expected, ensure_ascii=False), encoding='utf-8')
                    else:
                        expected = json.loads(expected_path.read_text(encoding='utf-8'))
                    row = {'preset': preset}
                    modes = ['legacy', 'full', 'deferred'] if phase == 'optimized' else ['full', 'deferred']
                    samples = {name: [] for name in modes}
                    sizes = {}
                    catalog_samples = []
                    legacy_read = engine.get_game
                    for repeat in range(runs + 1):
                        # Reverse order on alternate rounds to limit drift.
                        for name in (modes if repeat % 2 == 0 else modes[::-1]):
                            suffix = '?fleet_goods=deferred' if name == 'deferred' else ''
                            context = (patch.object(engine, 'get_game', lambda identity: legacy_read(identity))
                                       if name == 'legacy' else nullcontext())
                            with context:
                                actual, size, elapsed = fetch(f'/api/games/{identity}{suffix}')
                            sizes[name] = size
                            if actual.get('fleet_network', {}).get('order_goods_deferred'):
                                catalog, _, catalog_elapsed = fetch('/api/fleet-goods')
                                goods = catalog['goods']
                                if repeat:
                                    catalog_samples.append(round(catalog_elapsed, 3))
                                actual['fleet_network'].pop('order_goods_deferred')
                                actual['fleet_network']['order_goods'] = goods
                            assert actual == expected, f'HTTP JSON changed: {preset}/{name}'
                            if repeat:
                                samples[name].append(round(elapsed, 3))
                    for name in modes:
                        row[name] = dict(median_ms=round(statistics.median(samples[name]), 3),
                                         samples_ms=samples[name], wire_bytes=sizes[name], full_json_equal=True)
                    if catalog_samples:
                        row['deferred']['catalog_followup_median_ms'] = round(statistics.median(catalog_samples), 3)
                    rows.append(row)
                assert hashes(folder) == before, 'Steady HTTP GET modified persistence'
            finally:
                http.shutdown()
                http.server_close()
    assert signature == inputs_digest(ROOT), 'Runtime changed during benchmark'
    assert script_hash == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'Benchmark changed while running'
    report = dict(phase=phase, inputs_sha256=signature, measurements=rows,
                  benchmark_script_sha256=script_hash,
                  steady_get_persistence_unchanged=True,
                  scope='Real loopback HTTP read and JSON decode, same full-DLC saves. Alternating order each round, excluding warm-up. The optimized report also interleaves a legacy dictionary-reader adapter under the same current server/controller. Catalog follow-up is outside deferred response timing and measured separately. Deferred JSON is reconstructed and compared in full; no fields ignored.')
    (output / f'{phase}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('baseline', 'optimized'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=7)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    benchmark(args.output_dir.resolve(), args.phase, args.runs)
