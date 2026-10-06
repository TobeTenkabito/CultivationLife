"""M2 acceptance benchmark: paired actual 500-year actions, ten repeats/case.

Both modes retain identical pre-existing player/NPC facts. Off removes only the
heavens container and its owned, empty anomaly instances. Guixu popups are disabled
in both modes to finish all 500 years; ordinary annual simulation is unchanged.
Run without other heavy tests for the final measurements.
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import EXTENSION_REPORT
from cultivation_life.rules import add_item,max_hp,max_mp
from cultivation_life.system.formation_system import make_formation_material_instance
from cultivation_life.system.heavens import operations,omens
from cultivation_life.system.heavens.definitions import CONTACT_SITES
from cultivation_life.system.heavens.state import create_echo,get_echo


def command(engine,key,action,target='sea_echo',options=None):
    state=engine.store.load(key).heavens_state
    return engine.heavens_command(key,state['command_seq']+1,state['revision'],action,target,options or {})


def item(engine,game,world,tier):
    definition=next(d for d in engine._formation_material_defs().values() if d.get('world')==world and d.get('tier')==tier)
    material=make_formation_material_instance(definition,source='M2 固定性能输入',origin_world=world)
    game.player.formation_materials.append(material)
    return material['id']


def fixture(engine,case,seed):
    key=engine.create_game('M2Benchmark','heavenly','dao',seed,preset_id='core')['id']
    game=engine.store.load(key)
    p=game.player
    p.lifespan,p.next_tribulation_age=None,999999
    game.settings['silent_events']=True
    add_item(p,'spirit_stone',1000000)
    p.world,p.location_id,p.realm_index='human','muling_desert',4
    p.hp,p.mp=max_hp(p),max_mp(p)
    material=item(engine,game,'human',4)
    engine.store.save(game)
    if case=='bounded_m2':
        for action,options in [('mirror_enter',{}),('mirror_probe',{}),('mirror_repair',{'material_id':material}),('mirror_leave',{})]:
            command(engine,key,action,'mirror_field',options)
        game=engine.store.load(key)
        game.player.location_id='wudi_plain'
        game.player.mp=max_mp(game.player)
        material=item(engine,game,'human',4)
        engine.store.save(game)
        for action in ('ruins_enter','ruins_observe','ruins_verify','ruins_read','ruins_replace','ruins_leave'):
            command(engine,key,action,'causal_ruins',{'material_id':material} if action=='ruins_replace' else {})
    game=engine.store.load(key)
    p=game.player
    p.world,p.location_id,p.realm_index='celestial','law_sea',10
    p.immortal_power_converted=True
    p.hp,p.mp=max_hp(p),max_mp(p)
    if case=='bounded_m2':
        # Fixed historical input: all earlier facts are before this actual window.
        game.heavens_state['runtime'].update(processed_years=100,last_year_key=100,last_discovery_window=0)
        for target in ('sand_glimmer','stone_resonance'): omens.discover(engine._dependencies.heavens,game,target)
    engine.store.save(game)
    if case!='unmet':
        for site in CONTACT_SITES:
            game=engine.store.load(key)
            p=game.player
            p.world,p.location_id=site.world,site.location_id
            p.mp=max_mp(p)
            echo=create_echo(engine._dependencies.heavens,game,site.id)
            # Finite, prepaid history used as fixture input, no generated income.
            echo.update(observed_cycle=0,history_checked=True,exchanged=True,correspondence_completed=True,project_stones=17500)
            material=item(engine,game,site.world,9)
            engine.store.save(game)
            command(engine,key,'upkeep_start',site.id,{'material_id':material})
    game=engine.store.load(key)
    game.player.world,game.player.location_id='celestial','law_sea'
    game.player.hp,game.player.mp=max_hp(game.player),max_mp(game.player)
    engine.store.save(game)
    if case=='bounded_m2':
        for action in ('visit_depart','visit_study','visit_return','mission_start'):
            command(engine,key,action)
        game=engine.store.load(key)
        runtime=game.heavens_state['runtime']
        runtime['history']=[dict(year=runtime['processed_years'],text='已核验的有限历史记录。'*10) for _ in range(128)]
        engine.store.save(game)
    # Normalize legacy load additions before copying identical starting documents.
    engine._load(key)
    engine._load(key)
    enabled=engine.store.load(key)
    disabled=copy.deepcopy(enabled)
    disabled.heavens_state={}
    disabled.spatial_state['instances']={identity:scene for identity,scene in disabled.spatial_state.get('instances',{}).items() if not scene.get('heavens_target')}
    engine.store.save(disabled)
    engine.store.save(enabled)
    return disabled,enabled


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats',type=int,default=10)
    parser.add_argument('--output',type=Path,default=ROOT/'build/heavens-m2-benchmark.json')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    rows=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        for case,seed in [('unmet',17),('four_contacts',9901),('bounded_m2',44001)]:
            with patch.object(engine,'_advance_guixu_calendar',return_value=False):
                off,on=fixture(engine,case,seed)
                samples={'off':[],'on':[]}
                if args.prepare_only:
                    print(json.dumps(dict(case=case,years=on.heavens_state['runtime']['processed_years'],bytes=len(json.dumps(on.heavens_state).encode()))),flush=True)
                    continue
                final=on
                for repeat in range(args.repeats):
                    for mode in (('off','on') if repeat%2==0 else ('on','off')):
                        work=copy.deepcopy(on if mode=='on' else off)
                        engine.store.save(work)
                        start=time.perf_counter()
                        engine.advance(work.id,'cultivate',1)
                        samples[mode].append((time.perf_counter()-start)*1000)
                        saved=engine.store.load(work.id)
                        assert saved.player.age-work.player.age==500,(case,mode,'incomplete action')
                        if mode=='on':
                            assert saved.heavens_state['runtime']['processed_years']-on.heavens_state['runtime']['processed_years']==500
                            if case!='unmet':
                                for site in CONTACT_SITES:
                                    row=get_echo(saved.heavens_state['runtime'],site.id)['upkeep']
                                    assert row['status']=='completed' and row['escrow']['spent']==30000
                            if case=='bounded_m2': assert get_echo(saved.heavens_state['runtime'])['mission']['status']=='completed'
                            final=saved
                    print(f'{case}: {repeat+1}/{args.repeats} paired samples',flush=True)
            view_times=[]
            before=copy.deepcopy(on.to_dict())
            for target in [None,*[s.id for s in CONTACT_SITES],'mirror_field','causal_ruins']:
                for _ in range(20):
                    start=time.perf_counter()
                    operations.project(on,'known',target,deps=engine._dependencies.heavens)
                    view_times.append((time.perf_counter()-start)*1000)
            assert on.to_dict()==before
            off_ms,on_ms=statistics.median(samples['off']),statistics.median(samples['on'])
            p95=sorted(view_times)[int(len(view_times)*.95)-1]
            size=max(len(json.dumps(g.heavens_state,ensure_ascii=False).encode()) for g in (on,final))
            row=dict(case=case,seed=seed,repeats=args.repeats,years=500,off_median_ms=off_ms,on_median_ms=on_ms,
                overhead_ms=on_ms-off_ms,limit_ms=max(off_ms*.2,100),view_p95_ms=p95,heavens_bytes=size,samples_ms=samples,
                passed=on_ms-off_ms<=max(off_ms*.2,100) and p95<200 and size<512*1024)
            rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='samples_ms'}),flush=True)
    if args.prepare_only:return
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(cases=rows,extensions=EXTENSION_REPORT,guixu_popup_disabled_in_both_modes=True,
        other_annual_simulation_unchanged=True),ensure_ascii=False,indent=2),encoding='utf-8')
    if not all(row['passed'] for row in rows):raise SystemExit(1)


if __name__=='__main__':main()
