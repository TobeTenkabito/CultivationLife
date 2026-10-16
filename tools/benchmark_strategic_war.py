"""Serial, isolated full hundred-year commands; never touches a player's saves."""
import copy
import hashlib
import json
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.system.strategic_war import lifecycle
from cultivation_life.system.strategic_war.materialization import materialize
from test_strategic_war import scenario


def main():
    def fingerprint():
        digest=hashlib.sha256()
        for path in sorted([*ROOT.glob('cultivation_life/**/*.py'),ROOT/'web/app.js',ROOT/'web/strategic-war-panel.js',ROOT/'web/strategic-war-panel.css']):
            digest.update(str(path.relative_to(ROOT)).encode());digest.update(path.read_bytes())
        return digest.hexdigest()
    source_hash=fingerprint()
    results=[]
    with tempfile.TemporaryDirectory(prefix='strategic-war-benchmark-') as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        template,_=scenario(engine)
        template.settings['silent_events']=True
        template.player.next_tribulation_age=None
        unit=int(WORLD_SYSTEMS['time_units'][str(template.player.realm_index)])
        assert 100%unit==0 and 1<=100//unit<=10,(unit,'Need an ordinary 100-year command')
        original=engine._advance_strategic_wars
        samples_by_mode={mode:[] for mode in ('no-war-baseline','no-war-current','war-marching','war-engaged')}
        for index in range(3):
            for mode,samples in samples_by_mode.items():
                game=copy.deepcopy(template)
                if mode.startswith('no-war'):
                    game.strategic_war_state={}
                    from cultivation_life.race_diplomacy import relations_for
                    relations_for(game)['human|woodborn']['status']='neutral'
                else:
                    if mode=='war-engaged':
                        # Isolated initial placement fixture: both armies start
                        # at a real common site, so this sample measures actual
                        # combat instead of a century spent only on the road.
                        from cultivation_life.system.war.logistics import cash
                        for race in ('human','woodborn'):
                            funded=sum(o.world=='spirit' and o.allegiance_race==race and cash(game,o)>0 for o in game.sects.values())
                            for reserve_index in range(max(0,3-funded)):
                                materialize(bind(engine),game,'spirit',race,random.Random(641+reserve_index))
                        place=next(o.location_id for o in game.sects.values() if o.allegiance_race=='woodborn')
                        for org in game.sects.values():
                            if org.world=='spirit' and org.allegiance_race in {'human','woodborn'}:
                                org.location_id=place
                                for person in org.npcs:
                                    if person.world=='spirit':person.location_id=place
                    game.player.age+=1
                    lifecycle.advance(bind(engine),game,random.Random(641))
                engine.store.save(game)
                # Reconcile first read outside timed command, matching a loaded UI.
                engine.get_game(game.id)
                game=engine._load(game.id)
                parent_time=0.;child_time=0.
                def measured(g,rng):
                    nonlocal parent_time
                    start=time.perf_counter();original(g,rng);parent_time+=time.perf_counter()-start
                old_battle=engine._resolve_field_attack
                def battle(*a,**kw):
                    nonlocal child_time
                    start=time.perf_counter();result=old_battle(*a,**kw);child_time+=time.perf_counter()-start
                    return result
                callback=(lambda *a:None) if mode=='no-war-baseline' else measured
                with patch.object(engine,'_advance_strategic_wars',side_effect=callback),patch.object(engine,'_resolve_field_attack',side_effect=battle):
                    start=time.perf_counter();engine.advance(game.id,'rest',100//unit);elapsed=time.perf_counter()-start
                after=engine._load(game.id)
                assert after.player.age-game.player.age==100,(mode,after.player.age-game.player.age)
                sample=dict(seconds=round(elapsed,6),strategic_seconds=round(parent_time,6),
                    field_combat_seconds=round(child_time,6),save_bytes=engine.store._path(game.id).stat().st_size,
                    parent_bytes=len(json.dumps(after.strategic_war_state,ensure_ascii=False).encode()),
                    actual_battles=sum(w.get('battles',0) for w in after.wars if w.get('strategic_war_id')),
                    reinforcement_count=sum(len(w.get('reinforcements',[])) for w in after.wars if w.get('strategic_war_id')),
                    max_coalition_size=max((len(rows) for w in after.wars if w.get('strategic_war_id') for rows in w['coalitions'].values()),default=0))
                if mode=='war-engaged':
                    assert sample['actual_battles']>0
                    assert sample['reinforcement_count']>0 and sample['max_coalition_size']>1
                samples.append(sample)
                print(mode,index+1,sample,flush=True)
        for mode,samples in samples_by_mode.items():
            results.append(dict(mode=mode,median_seconds=statistics.median(s['seconds'] for s in samples),samples=samples))
    try:
        import psutil
        memory=psutil.Process().memory_info()
        peak=getattr(memory,'peak_wset',memory.rss)
    except ImportError:
        peak=None
    assert source_hash==fingerprint(),'Source changed during benchmark; rerun serially'
    report=dict(source_sha256=source_hash,results=results,peak_process_rss_bytes=peak,
        note='Full public rest commands, 3 serial isolated runs per scene. Strategic timer includes deployment, elections, logistics and combat; field combat is a subset, not an identical-work baseline. No packaging or user saves.')
    destination=ROOT/'build'/'strategic-war-performance.json'
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Report:',destination,flush=True)


if __name__=='__main__':main()
