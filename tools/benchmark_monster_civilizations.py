"""Paired real 100-year commands with four activated ecology scopes and unchanged RNG."""
import copy,hashlib,itertools,json,os,statistics,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.content_registry import CONTENT_DOCUMENTS
from cultivation_life.system.monster_civilizations import core
from scripts.release_evidence import inputs_digest

def run():
    signature=inputs_digest(ROOT);rows=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder))
        for seed in (315,7701,9003):
            made=engine.create_game('万灵百年验收','supreme_metal','dao',seed,preset_id='true_immortal')
            original=engine._load(made['id']);original.pending_event=None;original.player.next_tribulation_age=None;original.settings['silent_events']=True;original.heavenly_court['open_election']=None
            actual_world,actual_location=original.player.world,original.player.location_id
            for world in core.config()['worlds']:
                original.player.world=world;original.player.location_id=core.config()['worlds'][world]['regions'][0]
                core.activate(original)
            original.player.world,original.player.location_id=actual_world,actual_location
            doc=original.to_dict();off_document=copy.copy(CONTENT_DOCUMENTS);off_document.pop(core.DOCUMENT)
            samples={False:[],True:[]};expected={};ecological=[]
            for repeat in range(3):
                for enabled in ([False,True] if repeat%2==0 else [True,False]):
                    engine.store.save(GameState.from_dict(doc));ids=itertools.count()
                    def fresh_id():return uuid.UUID(bytes=hashlib.blake2s(f'paired:{seed}:{next(ids)}'.encode(),digest_size=16).digest())
                    documents=CONTENT_DOCUMENTS.copy() if enabled else off_document
                    start=time.perf_counter()
                    with patch.dict(CONTENT_DOCUMENTS,documents,clear=True),patch.object(engine,'_advance_guixu_calendar',return_value=False),patch('uuid.uuid4',side_effect=fresh_id):
                        engine.advance(original.id,'rest',1)
                        final=engine.store.load(original.id)
                    elapsed=(time.perf_counter()-start)*1000;samples[enabled].append(elapsed)
                    assert final.player.age-original.player.age==100
                    normalized=final.to_dict();normalized.pop('updated_at');normalized.pop('monster_civilization_state')
                    if not expected:expected=normalized
                    assert normalized==expected,'DLC ecology altered base game settlement or random stream'
            off,on=map(statistics.median,(samples[False],samples[True]));difference=on-off
            rows.append(dict(seed=seed,off_ms=samples[False],on_ms=samples[True],off_median_ms=off,on_median_ms=on,overhead_ms=difference,base_state_exact=True,threshold_ms=max(50,off*.05),within_threshold=difference<=max(50,off*.05)))
            print(json.dumps(rows[-1]),flush=True)
        probe=GameState.from_dict(doc);start=time.perf_counter()
        for i in range(5000):probe.player.age+=1;core.advance_year(probe)
        duration=time.perf_counter()-start;size=len(json.dumps(probe.monster_civilization_state,ensure_ascii=False).encode())
    assert signature==inputs_digest(ROOT)
    result=dict(inputs_sha256=signature,paired_runs=rows,four_worlds_five_thousand_years_seconds=duration,dlc_state_bytes=size,scope='Same input; original controller, yearly settlement, save/load; four activated ecology scopes; Guixu interruption disabled and fresh IDs deterministic. All base fields and RNG identical; only DLC state and wall-clock updated_at excluded.',acceptance=all(r['within_threshold'] for r in rows))
    output=ROOT/'build/performance-2100';output.mkdir(exist_ok=True);(output/'civilizations.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0 if result['acceptance'] else 1

if __name__=='__main__':
    if os.environ.get('PYTHONHASHSEED')!='0':raise SystemExit(subprocess.call([sys.executable,'-X','utf8',*sys.argv],env=dict(os.environ,PYTHONHASHSEED='0')))
    raise SystemExit(run())
