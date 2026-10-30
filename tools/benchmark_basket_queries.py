"""Interleave released/cached baskets under one real controller and compare all state."""
import argparse
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.system.economy import basket_consumption
from tools.benchmark_economy_actions import normalize, SEEDS
from scripts.release_evidence import inputs_digest


def benchmark(inputs, output):
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    reference = ROOT / 'tests/fixtures/basket_consumption_332.py'
    spec = importlib.util.spec_from_file_location('cultivation_life.system.economy._reference_baskets', reference)
    released = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(released)
    cached_settle = basket_consumption.settle
    rows = []
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
        engine = GameEngine(ROOT, Path(directory) / 'saves')
        for seed in SEEDS:
            initial = json.loads((inputs / f'input-{seed}.json').read_text(encoding='utf-8'))
            expected = json.loads((inputs / f'expected-{seed}.json').read_text(encoding='utf-8'))
            samples = {'reference': [], 'cached': []}
            for mode in ('reference', 'cached', 'cached', 'reference'):
                game = GameState.from_dict(initial)
                engine.store.save(game)
                identifiers = itertools.count()
                def fresh_id():
                    value = f'benchmark:{seed}:{next(identifiers)}'.encode()
                    return uuid.UUID(bytes=hashlib.blake2s(value, digest_size=16).digest())
                algorithm = released.settle if mode == 'reference' else cached_settle
                start = time.perf_counter()
                with patch.object(basket_consumption, 'settle', algorithm), \
                     patch.object(engine, '_advance_guixu_calendar', return_value=False), \
                     patch('uuid.uuid4', side_effect=fresh_id):
                    engine.advance(game.id, 'rest', 1)
                actual = engine.store.load(game.id)
                elapsed = (time.perf_counter() - start) * 1000
                assert actual.player.age - game.player.age == 100
                assert normalize(actual) == expected, f'Full state differs: {seed}/{mode}'
                samples[mode].append(round(elapsed, 3))
            medians = {key: round(statistics.median(values), 3) for key, values in samples.items()}
            row = dict(seed=seed, samples_ms=samples, medians_ms=medians, full_state_equal=True,
                       reduction_percent=round((1-medians['cached']/medians['reference'])*100, 2))
            rows.append(row)
            print(json.dumps(row), flush=True)
    assert signature == inputs_digest(ROOT), 'Runtime changed during benchmark'
    reference_ms = statistics.median(row['medians_ms']['reference'] for row in rows)
    cached_ms = statistics.median(row['medians_ms']['cached'] for row in rows)
    report = dict(inputs_sha256=signature, measurements=rows,
        reference_median_ms=reference_ms, cached_median_ms=cached_ms,
        reduction_percent=round((1-cached_ms/reference_ms)*100, 2),
        scope='ABBA order per seed, 100 real years per action, same current controller. Only the basket algorithm is replaced with the frozen 3.3.2 implementation; current production defaults to uncached behavior for the reference. Same fixed hash seed/UUIDs/Guixu setup as benchmark_economy_actions. Full saved state including RNG compared to pre-change output, excluding updated_at only.')
    (output / 'comparison.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, '-X', 'utf8', *sys.argv],
                                         env=dict(os.environ, PYTHONHASHSEED='0')))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    benchmark(args.inputs.resolve(), args.output_dir.resolve())
