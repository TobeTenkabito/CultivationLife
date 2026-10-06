"""Bounded all-world save/view sizes and paired real 500-year advancement."""
import copy
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from test_heavens_incidents import local, quiet, finish
from cultivation_life.system.heavens.incident_definitions import INCIDENTS
from cultivation_life.system.heavens import operations
from cultivation_life.rules import max_hp, max_mp


def main():
    with tempfile.TemporaryDirectory() as folder:
        bundle = quiet(local.__wrapped__(Path(folder)))
        for desc in INCIDENTS:
            work = finish(bundle, desc, 'incident_preserve')
        engine = bundle[0]
        p = work.player
        p.world, p.location_id, p.realm_index = 'celestial', 'jade_capital', 10
        p.lifespan, p.next_tribulation_age = None, 999999
        p.hp, p.mp = max_hp(p), max_mp(p)
        work.settings['silent_events'] = True
        work.heavens_state['watch'] = False
        engine.store.save(work)
        engine._load(work.id); engine._load(work.id)
        on = engine.store.load(work.id)
        off = copy.deepcopy(on); off.heavens_state = {}
        samples = dict(on=[], off=[])
        with patch.object(engine, '_advance_guixu_calendar', return_value=False):
            for repeat in range(5):
                for mode in (('on','off') if repeat%2 else ('off','on')):
                    original = copy.deepcopy(on if mode=='on' else off)
                    engine.store.save(original)
                    started = time.perf_counter()
                    engine.advance(original.id, 'cultivate', 1)
                    samples[mode].append((time.perf_counter()-started)*1000)
                    current = engine.store.load(original.id)
                    assert current.player.age-original.player.age == 500
                    if mode=='on':
                        assert current.heavens_state['runtime']['incidents']['celestial_seal']['remaining'] == 0
                print(f'500-year pair {repeat+1}/5 passed',flush=True)
        baseline = on.to_dict()
        views = []
        for _ in range(200):
            started = time.perf_counter()
            projected = operations.project(on, 'known', deps=engine._dependencies.heavens)
            views.append((time.perf_counter()-started)*1000)
        assert on.to_dict() == baseline
        medians = {key:statistics.median(value) for key,value in samples.items()}
        result = dict(years=500,repeats=5,medians_ms=medians,samples_ms=samples,
            view_p95_ms=sorted(views)[189],state_bytes=len(json.dumps(on.heavens_state,ensure_ascii=False).encode()),
            view_bytes=len(json.dumps(projected,ensure_ascii=False).encode()),pure_projection=True)
        result['passed'] = (medians['on']-medians['off'] <= max(100,medians['off']*.2)
                            and result['view_p95_ms']<200 and result['state_bytes']<512*1024)
        (ROOT/'build/heavens-all-worlds-benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
        assert result['passed']


if __name__ == '__main__':
    main()
