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


def run(engine, initial, mode, years):
    game = copy.deepcopy(initial)
    rng = random.Random(20261018)
    start = time.perf_counter()
    for index in range(years):
        game.player.age += 1
        if mode == 'all-live': regions.synchronize(engine, game, regions.worlds())
        engine._advance_world_year(game, rng, [], encounters=False)
        if (index+1) % WORLD_SYSTEMS['time_units'][str(game.player.realm_index)] == 0:
            game.diplomacy_unit += 1
            engine._advance_wars_unit(game, rng)
        if mode == 'frozen-reloaded' and index+1 == years//2:
            game = GameState.from_dict(game.to_dict())
            regions.attach(engine, game)
        if (index+1)%25 == 0:
            print(dict(mode=mode, year=index+1, seconds=round(time.perf_counter()-start,3)), flush=True)
    elapsed = time.perf_counter()-start
    before = check(game)
    clocks = {w:r['year'] for w,r in game.world_simulation['regions'].items()}
    if mode != 'all-live':
        assert all(y == (game.player.age if w == game.player.world else initial.world_simulation['regions'][w]['year']) for w,y in clocks.items())
        assert game.heavens_state['runtime']['campaign'] == initial.heavens_state['runtime']['campaign']
        assert game.merchant_state['posted'] == initial.merchant_state['posted']
        assert game.economy_v2['transport']['worlds']['spirit'] == initial.economy_v2['transport']['worlds']['spirit']
    entry_times = {}
    entered = ('human', 'spirit', 'true_demon', 'demon')
    for world in entered:
        start = time.perf_counter()
        regions.synchronize(engine, game, [world])
        entry_times[world] = time.perf_counter()-start
        print(dict(mode=mode, entered=world, seconds=round(entry_times[world],3)), flush=True)
        check(game)
    # Only the actual campaign/freight destinations are entered. The other
    # societies and their pending receipts must remain frozen in this scenario.
    snapshot = canonical(game)
    regions.synchronize(engine, game, [game.player.world, *entered])
    assert canonical(game) == snapshot
    assert canonical(GameState.from_dict(game.to_dict())) == snapshot
    return game, dict(away_seconds=elapsed, reentry_seconds=sum(entry_times.values()), entry_times=entry_times,
                      before_reentry=before, after_reentry=check(game), clocks=clocks,
                      repeat_and_reload_equal=True, supply_conserved=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--years',type=int,default=100)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    output=ROOT/'build/regional-calendar-performance';output.mkdir(exist_ok=True)
    digest=inputs_digest(ROOT)
    engine=GameEngine(ROOT,output/'disposable-saves')
    from cultivation_life.system.economy.deferred import posting
    with posting():
        initial=prepare(engine,fixed_routes=True)
    initial.player.world='celestial'  # Isolated fixture's departure observation.
    rows=[]
    for repeat in range(args.repeats):
        outcomes={}
        for mode in (('all-live','frozen','frozen-reloaded') if repeat%2==0 else ('frozen-reloaded','frozen','all-live')):
            game, stats=run(engine,initial,mode,args.years)
            outcomes[mode]=canonical(game)
            rows.append(dict(repeat=repeat,mode=mode,**stats))
        if outcomes['frozen-reloaded'] != outcomes['frozen']:
            for mode,value in outcomes.items():
                (output/(mode+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
            raise AssertionError('Reload changed settlement: see comparison JSON')
    assert inputs_digest(ROOT)==digest, 'Production inputs changed during benchmark'
    report=dict(version=BASE_GAME_VERSION,source_sha256=digest,years=args.years,repeats=args.repeats,
        fixture='Player in celestial; existing spirit/true-demon freight, human campaign, war and order. Enter human, spirit, true_demon and demon (campaign front) separately. Other worlds remain frozen. All-live is timing reference only: deferred advances intentionally change trade opportunities. Frozen continuous and reload runs must match full authoritative state.',
        resume_state_equal=True,settlement_checks=True,runs=rows,medians={mode:{key:statistics.median(r[key] for r in rows if r['mode']==mode)
        for key in ('away_seconds','reentry_seconds')} for mode in ('all-live','frozen','frozen-reloaded')})
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report['medians'],ensure_ascii=False),flush=True)


if __name__=='__main__':main()
