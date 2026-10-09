"""Paired real 100-year actions; run alone after functional acceptance."""
import argparse
import copy
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from test_heavens_settlement import local, site, ready, military, occupation, delegates, issue, load
from cultivation_life.content_registry import EXTENSION_REPORT
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens import operations


def prepare(folder, case):
    base = local.__wrapped__(Path(folder))
    if case == 'unmet':
        bundle = base
    else:
        bundle = military.__wrapped__(ready.__wrapped__(site.__wrapped__(base)))
        if case == 'occupation':
            occupation(bundle)
        else:
            delegates(bundle); issue(bundle, 'campaign_truce')
    engine = bundle[0]
    work = load(bundle)
    p = work.player
    p.world, p.location_id, p.realm_index = 'celestial', 'law_sea', 10
    p.immortal_power_converted = True
    p.lifespan, p.next_tribulation_age = None, 999999
    p.hp, p.mp = max_hp(p), max_mp(p)
    work.settings['silent_events'] = True
    work.heavens_state['watch'] = False
    work.heavens_state['runtime']['pause_on_opportunity'] = False
    engine.store.save(work)
    engine._load(work.id); engine._load(work.id)
    on = engine.store.load(work.id)
    off = copy.deepcopy(on)
    off.heavens_state = {}
    off.spatial_state['instances'] = {k: v for k, v in off.spatial_state.get('instances', {}).items() if not v.get('heavens_target')}
    return engine, off, on


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=10)
    args = parser.parse_args()
    results = []
    for case in ('unmet', 'occupation', 'truce'):
        with tempfile.TemporaryDirectory() as folder:
            engine, off, on = prepare(folder, case)
            samples = {'off': [], 'on': []}
            final = on
            with patch.object(engine, '_advance_guixu_calendar', return_value=False):
                for repeat in range(args.repeats):
                    for mode in (('on', 'off') if repeat % 2 else ('off', 'on')):
                        work = copy.deepcopy(on if mode == 'on' else off)
                        engine.store.save(work)
                        start = time.perf_counter()
                        engine.advance(work.id, 'cultivate', 1)
                        samples[mode].append((time.perf_counter()-start)*1000)
                        saved = engine.store.load(work.id)
                        assert saved.player.age-work.player.age == 100, (case, mode, 'interrupted')
                        if mode == 'on':
                            assert saved.heavens_state['runtime']['processed_years']-on.heavens_state['runtime']['processed_years'] == 100
                            final = saved
                    print(f'{case}: {repeat+1}/{args.repeats}', flush=True)
            before = on.to_dict()
            views = []
            for _ in range(100):
                start = time.perf_counter()
                operations.project(on, 'known', 'lanjiang_gate' if case != 'unmet' else None, deps=engine._dependencies.heavens)
                views.append((time.perf_counter()-start)*1000)
            assert on.to_dict() == before
            off_ms, on_ms = statistics.median(samples['off']), statistics.median(samples['on'])
            p95 = sorted(views)[94]
            size = max(len(json.dumps(g.heavens_state, ensure_ascii=False).encode()) for g in (on, final))
            row = dict(case=case, repeats=args.repeats, years=100, off_median_ms=off_ms, on_median_ms=on_ms,
                overhead_ms=on_ms-off_ms, limit_ms=max(100, off_ms*.2), view_p95_ms=p95, heavens_bytes=size,
                passed=on_ms-off_ms <= max(100, off_ms*.2) and p95 < 200 and size < 512*1024,
                samples_ms=samples)
            results.append(row)
            print(json.dumps({k:v for k,v in row.items() if k != 'samples_ms'}), flush=True)
    output = ROOT/'build/heavens-m3-benchmark.json'
    output.write_text(json.dumps(dict(cases=results, extensions=EXTENSION_REPORT,
        guixu_popup_disabled_in_both_modes=True, other_annual_simulation_unchanged=True), indent=2), encoding='utf-8')
    if not all(row['passed'] for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
