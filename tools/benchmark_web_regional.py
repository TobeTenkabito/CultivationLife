"""Matched real browser clicks in isolated all-DLC release source copies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def worker(args):
    root = args.output / args.worker
    os.environ['CULTIVATION_APP_ROOT'] = str(root)
    sys.path.insert(0, str(root))
    from http.server import ThreadingHTTPServer
    from playwright.sync_api import sync_playwright
    from cultivation_life import server
    from cultivation_life.content_registry import EXTENSION_REPORT
    from cultivation_life.version import BASE_GAME_VERSION
    assert all(r['status'] == 'loaded' for r in EXTENSION_REPORT if r['kind'] == 'dlc')
    responses = []
    class Handler(server.Handler):
        def log_message(self, *items): pass
        def do_POST(self):
            start = time.perf_counter()
            try: super().do_POST()
            finally:
                if self.path.endswith('/advance'):
                    responses.append(time.perf_counter()-start)
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    rows = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width':1440,'height':960})
            page.set_default_timeout(600000)
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{http.server_port}')
            page.wait_for_function('!!configData')
            page.locator('#new-game-form [name=seed]').fill('20261018')
            button = page.locator('[data-preset-id=mahayana]')
            button.evaluate("b=>b.closest('details').open=true")
            button.click()
            page.wait_for_function('!busy && !!game')
            for setting, enabled in [('silent_events',True),('guixu_event_popup',False)]:
                page.evaluate('async ([s,v])=>mutate(`/api/games/${game.id}/settings`,{setting:s,enabled:v})', [setting, enabled])
            identity = page.evaluate('game.id')
            assert page.evaluate('game.player.realm_index') == 8
            for action in range(2):
                start_age = page.evaluate('game.player.world_age')
                start = time.perf_counter()
                page.locator('[data-action=cultivate]').click()
                page.wait_for_function('!busy')
                page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                elapsed = time.perf_counter()-start
                end_age = page.evaluate('game.player.world_age')
                assert end_age-start_age == 100, (args.worker, action, start_age, end_age)
                assert not errors, errors
                row = dict(action=action+1,seconds=elapsed,server_seconds=responses[-1],years=end_age-start_age)
                rows.append(row)
                print(json.dumps(dict(label=args.worker,repeat=args.repeat,**row)),flush=True)
            page.reload();page.wait_for_function('!!configData')
            page.evaluate('async id=>loadGame(id)', identity)
            assert page.evaluate('game.player.world_age') == end_age
            final = server.ENGINE.store.load(identity)
            detail = dict(region_clocks={w:r['year'] for w,r in getattr(final,'world_simulation',{}).get('regions',{}).items()},
                          organizations=len(final.economy_v2.get('organizations',{})))
            browser.close()
    finally: http.shutdown();http.server_close()
    result = dict(version=BASE_GAME_VERSION,label=args.worker,repeat=args.repeat,seed=20261018,preset='mahayana',
                  dlcs=[r['id'] for r in EXTENSION_REPORT if r['kind']=='dlc'],rows=rows,**detail)
    (args.output/f'{args.worker}-{args.repeat}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'build/web-regional-performance')
    parser.add_argument('--baseline',default='1cff7f88')
    parser.add_argument('--reference',default='1168399a')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--worker',choices=['current','baseline','reference'])
    parser.add_argument('--repeat',type=int,default=0)
    args=parser.parse_args();args.output=args.output.resolve()
    if args.worker:return worker(args)
    sys.path.insert(0,str(ROOT))
    from scripts.release_evidence import inputs_digest
    from cultivation_life.version import BASE_GAME_VERSION
    before=inputs_digest(ROOT)
    args.output.mkdir(parents=True,exist_ok=True)
    roots={}
    for label,revision in [('baseline',args.baseline),('reference',args.reference),('current',None)]:
        target=args.output/label;target.mkdir(exist_ok=True)
        if revision:
            archive=args.output/(label+'.zip')
            subprocess.run(['git','archive','--format=zip','--output',str(archive),revision,
                            'cultivation_life','content','dlc','mods','web'],cwd=ROOT,check=True)
            with zipfile.ZipFile(archive) as z:z.extractall(target)
            roots[label]=subprocess.check_output(['git','rev-parse',revision],cwd=ROOT,text=True).strip()
        else:
            for name in ['cultivation_life','content','dlc','mods','web']:
                shutil.copytree(ROOT/name,target/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            roots[label]=before
        enabled={json.loads(p.read_text(encoding='utf8'))['id']:True for p in (target/'dlc').glob('*/manifest.json')}
        (target/'data').mkdir(exist_ok=True)
        (target/'data/extension_preferences.json').write_text(json.dumps({'schema_version':1,'enabled':enabled}),encoding='utf8')
    runs=[]
    for repeat in range(args.repeats):
        order=['baseline','current','reference'] if repeat%2==0 else ['reference','current','baseline']
        for label in order:
            subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--output',str(args.output),
                            '--worker',label,'--repeat',str(repeat)],cwd=ROOT,check=True)
            runs.append(json.loads((args.output/f'{label}-{repeat}.json').read_text(encoding='utf8')))
    medians={label:{str(action):statistics.median(row['seconds'] for run in runs if run['label']==label
                                                for row in run['rows'] if row['action']==action)
                    for action in (1,2)} for label in roots}
    assert inputs_digest(ROOT)==before,'Production inputs changed during measurement'
    assert all(medians['current'][a] < medians['baseline'][a] for a in ('1','2')),medians
    report=dict(version=BASE_GAME_VERSION,source_sha256=before,revisions=roots,repeats=args.repeats,
                method='Real all-DLC browser preset and cultivate clicks, two consecutive full centuries per fresh save; notifications disabled equally; no mocked simulation; serial matched runs.',
                status='passed',medians=medians,runs=runs)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(medians,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
