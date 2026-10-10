"""Compare real 100-year actions with identical input saves and full output state."""
import argparse
import cProfile
import hashlib
import itertools
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.version import BASE_GAME_VERSION

OUTPUT = ROOT / 'build/economy-performance'
SEEDS = (315, 7701, 9003)


def normalize(game):
    document = game.to_dict()
    # Only wall-clock save metadata varies. Keep all simulation clocks, RNG,
    # people, cargo, money, inventories and histories in the comparison.
    document.pop('updated_at')
    return document


def benchmark(phase, runs=3, profile=False):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    measurements = []
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory))
        for seed in SEEDS:
            before_path = OUTPUT / f'input-{seed}.json'
            expected_path = OUTPUT / f'expected-{seed}.json'
            if phase == 'baseline':
                made = engine.create_game('百年算法验收', 'supreme_metal', 'dao', seed,
                                          preset_id='true_immortal')
                original = engine._load(made['id'])
                original.pending_event = None
                original.player.next_tribulation_age = None
                original.settings['silent_events'] = True
                original.heavenly_court['open_election'] = None
                before_path.write_text(json.dumps(original.to_dict(), ensure_ascii=False), encoding='utf8')
            else:
                original = GameState.from_dict(json.loads(before_path.read_text(encoding='utf8')))
            expected = None if phase == 'baseline' else json.loads(expected_path.read_text(encoding='utf8'))
            if expected is not None:
                # Saving intentionally stamps the current release. Keep every
                # simulation field; compare this metadata to its required value.
                expected['last_saved_with_game_version'] = BASE_GAME_VERSION
            samples = []
            for repeat in range(runs + int(profile)):
                engine.store.save(GameState.from_dict(original.to_dict()))
                profiler = cProfile.Profile() if profile and repeat == runs else None
                identifiers = itertools.count()
                def fresh_id():
                    data = f'benchmark:{seed}:{next(identifiers)}'.encode()
                    return uuid.UUID(bytes=hashlib.blake2s(data, digest_size=16).digest())
                start = time.perf_counter()
                # Reproduce fresh object IDs too; keep the game's own RNG untouched.
                with patch.object(engine, '_advance_guixu_calendar', return_value=False), \
                        patch('uuid.uuid4', side_effect=fresh_id):
                    if profiler:
                        profiler.enable()
                    engine.advance(original.id, 'rest', 1)
                    if profiler:
                        profiler.disable()
                final = engine.store.load(original.id)
                elapsed = (time.perf_counter() - start) * 1000
                assert final.player.age - original.player.age == 100
                actual = normalize(final)
                assert actual['last_saved_with_game_version'] == BASE_GAME_VERSION
                if expected is None:
                    expected = actual
                    expected_path.write_text(json.dumps(actual, ensure_ascii=False), encoding='utf8')
                if actual != expected:
                    (OUTPUT / f'mismatch-{seed}.json').write_text(json.dumps(actual, ensure_ascii=False), encoding='utf8')
                    raise AssertionError(f'Full simulated state differs: seed {seed}, repeat {repeat}')
                if profiler:
                    profiler.dump_stats(str(OUTPUT / f'{phase}-{seed}.prof'))
                else:
                    samples.append(round(elapsed, 3))
            row = dict(seed=seed, samples_ms=samples, median_ms=round(statistics.median(samples), 3),
                       exact_state_match=True)
            measurements.append(row)
            print(json.dumps(row), flush=True)
    result = dict(phase=phase, runs=runs, measurements=measurements,
                  median_ms=round(statistics.median(r['median_ms'] for r in measurements), 3),
                  saved_with_version_asserted=BASE_GAME_VERSION,
                  state_comparison='All fields compared; wall-clock updated_at excluded; last_saved_with_game_version required to equal the current release.',
                  scope='Real controller + annual simulation + save/load; Guixu interruption disabled, fresh UUIDs reproducible; simulation RNG unchanged.')
    if phase != 'baseline':
        baseline = json.loads((OUTPUT / 'baseline.json').read_text(encoding='utf8'))
        result['baseline_median_ms'] = baseline['median_ms']
        result['speedup'] = round(baseline['median_ms'] / result['median_ms'], 3)
        result['reduction_percent'] = round((1 - result['median_ms'] / baseline['median_ms']) * 100, 2)
    (OUTPUT / f'{phase}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        # Set iteration must match across baseline and optimized subprocesses.
        raise SystemExit(subprocess.call([sys.executable, '-X', 'utf8', *sys.argv],
                         env=dict(os.environ, PYTHONHASHSEED='0')))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('baseline', 'optimized'))
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--output-dir',type=Path,default=OUTPUT)
    options = parser.parse_args()
    OUTPUT=options.output_dir.resolve()
    if options.runs < 1:
        parser.error('--runs must be positive')
    benchmark(options.phase, options.runs, options.profile)
