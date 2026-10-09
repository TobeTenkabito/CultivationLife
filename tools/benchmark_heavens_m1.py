"""Paired M1 benchmark: 100-year cultivation, identical fixed input per repetition.

Guixu popup interruption is disabled in BOTH modes to measure all 100 years;
other annual simulation and ordinary cultivation/settlement remain in use.
"""
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
sys.path.insert(0, str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens.operations import project
from cultivation_life.system.heavens.state import initialize, create_echo


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats',type=int,default=10)
    parser.add_argument('--output',type=Path,default=ROOT/'build/heavens-m1-benchmark.json')
    args=parser.parse_args()
    rows=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        for case,seed in [('unmet',17),('evidence',9901),('bounded_history',44001)]:
            key=engine.create_game('HeavensBenchmark','heavenly','dao',seed,preset_id='core')['id']
            base=engine.store.load(key)
            p=base.player
            p.world,p.location_id,p.realm_index='celestial','law_sea',10
            p.immortal_power_converted=True
            p.lifespan=None
            p.next_tribulation_age=999999
            p.hp,p.mp=max_hp(p),max_mp(p)
            base.pending_event=None
            base.settings['silent_events']=True
            base.heavens_state={}
            enabled=copy.deepcopy(base)
            initialize(enabled)
            if case!='unmet':
                echo=create_echo(engine._dependencies.heavens,enabled)
                echo.update(observed_cycle=0,history_checked=True,exchanged=True)
                if case=='bounded_history':
                    runtime=enabled.heavens_state['runtime']
                    runtime['history']=[dict(year=0,text='已核验的历史记录。'*10) for _ in range(128)]
                    runtime['tasks']=[dict(id=f'heavens-task-{i}',action='observe',status='completed',cycle=0,
                        duration=20,progress=20,escrow=dict(total=0,spent=0,refunded=0,material=None,mp_paid=0),person_id=None) for i in range(1,5)]
                    runtime['next_task_seq']=5
            samples={'off':[],'on':[]}
            with patch.object(engine,'_advance_guixu_calendar',return_value=False):
                for repeat in range(args.repeats):
                    # Alternate pair order to reduce warmup/order bias.
                    for mode in (['off','on'] if repeat%2==0 else ['on','off']):
                        work=copy.deepcopy(enabled if mode=='on' else base)
                        engine.store.save(work)
                        start=time.perf_counter()
                        result=engine.advance(key,'cultivate',1)
                        elapsed=time.perf_counter()-start
                        actual=engine.store.load(key)
                        if actual.player.age-work.player.age!=100:
                            raise AssertionError(f'{case}/{mode}: interrupted at {actual.player.age-work.player.age} years')
                        samples[mode].append(elapsed*1000)
            view_times=[]
            for _ in range(100):
                start=time.perf_counter(); project(enabled,'known',deps=engine._dependencies.heavens)
                view_times.append((time.perf_counter()-start)*1000)
            off,on=statistics.median(samples['off']),statistics.median(samples['on'])
            size=len(json.dumps(enabled.heavens_state,ensure_ascii=False).encode())
            row=dict(case=case,seed=seed,repeats=args.repeats,years=100,off_median_ms=off,on_median_ms=on,
                overhead_ms=on-off,limit_ms=max(off*.2,100),view_p95_ms=sorted(view_times)[94],
                heavens_bytes=size,samples_ms=samples,passed=on-off<=max(off*.2,100) and sorted(view_times)[94]<200 and size<512*1024)
            rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='samples_ms'}),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(rows,indent=2),encoding='utf-8')
    if not all(row['passed'] for row in rows):raise SystemExit(1)


if __name__=='__main__':main()
