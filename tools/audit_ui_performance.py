"""Measure real presentation and browser rendering using isolated saves."""
import argparse
import cProfile
import json
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.release_evidence import inputs_digest
from playwright.sync_api import sync_playwright

def audit(output,phase):
    output.mkdir(parents=True,exist_ok=True)
    signature=inputs_digest(ROOT)
    rows=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args): pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for preset in ('core','true_immortal'):
                        view=engine.create_game('呈现采样','heavenly','dao',280,preset_id=preset)
                        gid=view['id']
                        page=browser.new_page(viewport=dict(width=412,height=915))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData && !!window.GameThemes')
                        page.evaluate('async id=>loadGame(id)',gid)
                        samples=[]
                        for _ in range(11):
                            start=time.perf_counter();view=engine.get_game(gid)
                            samples.append((time.perf_counter()-start)*1000)
                        profile=cProfile.Profile();profile.runcall(engine.get_game,gid)
                        profile.dump_stats(str(output/f'{phase}-{preset}-presentation.prof'))
                        payload=json.dumps(view,ensure_ascii=False,separators=(',',':')).encode()
                        render_samples=page.evaluate('''async data=>{
                          const samples=[];
                          for(let i=0;i<11;i++){
                            const start=performance.now();render(data);
                            document.documentElement.scrollWidth;
                            const sync=performance.now()-start;
                            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                            if(i)samples.push(sync);
                          }
                          return samples;
                        }''',view)
                        row=dict(preset=preset,presentation_ms=samples[1:],
                            presentation_median_ms=round(statistics.median(samples[1:]),3),
                            render_layout_ms=render_samples,
                            render_layout_median_ms=round(statistics.median(render_samples),3),
                            payload_bytes=len(payload),dom_elements=page.locator('*').count())
                        row['deferred_panel_open_ms']=page.evaluate('''()=>{
                          const result={};
                          for(const name of ['inventory','map','spirit-field']){
                            const start=performance.now();UtilityPanels.open(name);
                            document.documentElement.scrollWidth;
                            result[name]=performance.now()-start;UtilityPanels.close(name);
                          }
                          return result;
                        }''')
                        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
                        page.close()
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    assert signature==inputs_digest(ROOT),'Production changed during measurement'
    report=dict(phase=phase,inputs_sha256=signature,measurements=rows,
        scope='Desktop Chromium 412x915; synchronous actual render plus forced layout; two animation frames between samples; isolated full-DLC saves. Not a phone frame-rate claim.')
    (output/f'{phase}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['baseline','optimized'])
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/performance-280/ui')
    args=parser.parse_args();audit(args.output_dir.resolve(),args.phase)
