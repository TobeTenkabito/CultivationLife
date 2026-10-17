"""Matched original saves; real timed actions, economic profile, cache equivalence."""
import argparse
import cProfile
import hashlib
import itertools
import json
import os
import platform
from pathlib import Path
import pstats
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--create-inputs', action='store_true')
    parser.add_argument('--uncached', action='store_true')
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    root = args.source_root.resolve()
    sys.path.insert(0, str(root))
    from cultivation_life.engine import GameEngine
    from cultivation_life.models import GameState
    from cultivation_life.version import BASE_GAME_VERSION
    from cultivation_life.system import economy_system
    from scripts.release_evidence import inputs_digest
    import psutil
    fingerprint = inputs_digest(root)
    args.inputs.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scenarios = [('human','nascent',4,'rest'), ('spirit','mahayana',8,'cultivate'),
                 ('celestial','true_immortal',9,'rest')]
    rows = []
    with tempfile.TemporaryDirectory(prefix='goods-perf-') as folder:
        engine = GameEngine(root, Path(folder)/'saves')
        for index, (world,preset,rank,action) in enumerate(scenarios):
            path = args.inputs/f'{world}.json'
            if args.create_inputs:
                made = engine.create_game('通用商品性能验收','supreme_metal','dao',21510+index,
                    custom_start=dict(world=world, realm_index=rank))
                game = engine._load(made['id'])
                game.pending_event = game.active_trial = None
                game.player.next_tribulation_age = None
                game.settings.update(silent_events=True,guixu_event_popup=False)
                if game.heavenly_court:
                    game.heavenly_court['open_election'] = None
                path.write_text(json.dumps(game.to_dict(),ensure_ascii=False),encoding='utf-8')
            raw = json.loads(path.read_text(encoding='utf-8'))
            samples, digests = [], []
            for repeat in range(args.runs+1):
                engine.store.save(GameState.from_dict(raw))
                sequence = itertools.count()
                def fresh_id():
                    return uuid.UUID(bytes=hashlib.blake2s(f'{index}:{next(sequence)}'.encode(),digest_size=16).digest())
                profiler = cProfile.Profile() if repeat == args.runs else None
                from contextlib import ExitStack
                with ExitStack() as stack:
                    stack.enter_context(patch.object(engine,'_advance_guixu_calendar',return_value=False))
                    stack.enter_context(patch('uuid.uuid4',side_effect=fresh_id))
                    if args.uncached:
                        stack.enter_context(patch.object(economy_system,'_listed_price',economy_system._listed_price.__wrapped__))
                    start, cpu = time.perf_counter(), time.process_time()
                    if profiler: profiler.enable()
                    engine.advance(raw['id'], action, 1)
                    if profiler: profiler.disable()
                    elapsed, cpu_ms = (time.perf_counter()-start)*1000, (time.process_time()-cpu)*1000
                final = engine.store.load(raw['id'])
                document = final.to_dict()
                document.pop('updated_at')
                digest = hashlib.sha256(json.dumps(document,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                if digests and digest != digests[0]: raise AssertionError('Non-deterministic full-state settlement')
                digests.append(digest)
                if profiler:
                    profiler.dump_stats(str(args.output.with_name(f'{args.label}-{world}.prof')))
                    stats = pstats.Stats(profiler)
                    economic = sorted([dict(file=k[0].split('CultivationLife')[-1],line=k[1],function=k[2],
                        primitive_calls=v[0],calls=v[1],self_seconds=v[2],cumulative_seconds=v[3])
                        for k,v in stats.stats.items() if '/economy/' in k[0].replace('\\','/')],
                        key=lambda r:r['cumulative_seconds'],reverse=True)[:15]
                else:
                    samples.append(dict(wall_ms=round(elapsed,2),cpu_ms=round(cpu_ms,2),
                        rss_mib=round(psutil.Process().memory_info().rss/1048576,2)))
            row = dict(world=world,action=action,years=final.player.age-raw['player']['age'],samples=samples,
                median_ms=statistics.median(s['wall_ms'] for s in samples),
                median_cpu_ms=statistics.median(s['cpu_ms'] for s in samples),
                full_state_sha256=digests[0],economic_profile=economic,
                market_count=len(final.economy_v2['markets']),
                commodity_rows=sum(len(m['commodities']) for m in final.economy_v2['markets'].values()))
            rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k not in {'economic_profile','samples'}}),flush=True)
    if fingerprint != inputs_digest(root): raise AssertionError('Source changed during performance measurement')
    result = dict(label=args.label,version=BASE_GAME_VERSION,source_sha256=fingerprint,runs=args.runs,
        cache_disabled=args.uncached,scenarios=rows,
        environment=dict(os=platform.platform(),python=platform.python_version(),logical_cpus=os.cpu_count(),
            host_memory_mib=round(psutil.virtual_memory().total/1048576)),
        scope='Original identical schema-10 saves; real controller/load/save and yearly economy, NPCs and all loaded DLCs; only optional Guixu interruption suppressed. Profiles excluded from timing. RSS is process retained memory, not device peak. Full-state hashes exclude only wall-clock updated_at.')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable,'-X','utf8',*sys.argv],env=os.environ|{'PYTHONHASHSEED':'0'}))
    main()
