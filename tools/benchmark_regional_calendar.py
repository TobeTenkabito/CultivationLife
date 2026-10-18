"""Current production entry benchmark; synthetic saves only, never player data."""
import argparse
import copy
import json
import random
import statistics
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from cultivation_life.engine import GameEngine
from cultivation_life.engine.world import regions
from cultivation_life.models import GameState
from cultivation_life.version import BASE_GAME_VERSION
from cultivation_life.content_registry import WORLD_SYSTEMS
from regional_scenario import prepare, check, canonical
from scripts.release_evidence import inputs_digest


def run(engine, initial, all_live, years):
    game = copy.deepcopy(initial)
    rng = random.Random(20261018)
    start = time.perf_counter()
    for index in range(years):
        game.player.age += 1
        if all_live: regions.synchronize(engine, game, regions.worlds())
        engine._advance_world_year(game, rng, [], encounters=False)
        if (index+1) % WORLD_SYSTEMS['time_units'][str(game.player.realm_index)] == 0:
            game.diplomacy_unit += 1
            engine._advance_wars_unit(game, rng)
        if (index+1)%25 == 0:
            print(dict(mode='all-live' if all_live else 'frozen', year=index+1, seconds=round(time.perf_counter()-start,3)), flush=True)
    elapsed = time.perf_counter()-start
    before = check(game)
    clocks = {w:r['year'] for w,r in game.world_simulation['regions'].items()}
    start = time.perf_counter()
    regions.synchronize(engine, game, ['celestial'])
    catchup = time.perf_counter()-start
    regions.synchronize(engine, game, regions.worlds())
    snapshot = canonical(game)
    regions.synchronize(engine, game, regions.worlds())
    assert canonical(game) == snapshot
    assert canonical(GameState.from_dict(game.to_dict())) == snapshot
    return game, dict(away_seconds=elapsed, upper_reentry_seconds=catchup,
                      before_reentry=before, after_reentry=check(game), clocks=clocks)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--years',type=int,default=100)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    output=ROOT/'build/regional-calendar-performance';output.mkdir(exist_ok=True)
    digest=inputs_digest(ROOT)
    engine=GameEngine(ROOT,output/'disposable-saves')
    initial=prepare(engine)
    rows=[]
    for repeat in range(args.repeats):
        outcomes={}
        for mode in (('all-live','frozen') if repeat%2==0 else ('frozen','all-live')):
            game, stats=run(engine,initial,mode=='all-live',args.years)
            outcomes[mode]=canonical(game)
            rows.append(dict(repeat=repeat,mode=mode,**stats))
        if outcomes['all-live'] != outcomes['frozen']:
            for mode,value in outcomes.items():
                (output/(mode+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
            raise AssertionError('Full state differs: see comparison JSON')
    assert inputs_digest(ROOT)==digest, 'Production inputs changed during benchmark'
    report=dict(version=BASE_GAME_VERSION,source_sha256=digest,years=args.years,repeats=args.repeats,
        full_state_equal=True,runs=rows,medians={mode:{key:statistics.median(r[key] for r in rows if r['mode']==mode)
        for key in ('away_seconds','upper_reentry_seconds')} for mode in ('all-live','frozen')})
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report['medians'],ensure_ascii=False),flush=True)


if __name__=='__main__':main()
