"""Actual final EXE: native ownership, exact material costs and independent UI."""
import json
import urllib.error
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def verify_immortal(base, with_dlc, folder):
    def request(path, data=None):
        req = urllib.request.Request(base+path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    for asset in ('immortal-artifacts.js','immortal-artifacts.css'):
        with urllib.request.urlopen(base+'/'+asset) as response:
            assert response.read() == (ROOT/'web'/asset).read_bytes()
    from cultivation_life.engine import GameEngine
    namespace = {}
    exec((ROOT/'tests/fixtures/immortal_release.py').read_text(encoding='utf-8'),namespace)
    made = request('/api/games',dict(name='成品仙器验收',spirit_root='supreme_metal',path='dao',seed=340,
                                   custom_start=dict(world='celestial',realm_index=9)))
    engine = GameEngine(ROOT,folder/'data/saves')
    identity = made['id']; path = '/api/games/'+identity
    namespace['prepare_immortal_release'](engine,identity)
    request(path+'/natal-artifact',dict(action='refine'))
    namespace['mark_immortal_release'](engine,identity)
    request(path+'/natal-artifact',dict(action='promote'))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=dict(width=1440,height=1040));errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base);page.wait_for_function('!!configData&&!busy')
        page.evaluate('id=>loadGame(id)',identity)
        page.locator('[data-panel-target=immortal-artifacts]').click()
        page.locator('.ia-grade-track [aria-current=step]').wait_for()
        for rank in (5,4,3,2):
            shown = request(path); state = shown['immortal_artifacts']; item = state['equipment'][0]
            assert state['title']=='仙器' and item['grade']==rank
            payload=dict(artifact_id=item['id'],expected_grade=rank,expected_revision=state['revision'])
            if rank==5:
                request(path+'/immortal-artifact',payload)
                with page.expect_response(lambda r:r.url.endswith('/immortal-artifact')) as stale:
                    page.locator('[data-immortal-refine]').click()
                assert stale.value.status==400
            else:
                page.locator('[data-immortal-refine]').click()
            page.wait_for_function('rank=>!busy&&game.immortal_artifacts.equipment[0].grade===rank-1',arg=rank)
        assert page.locator('[data-immortal-refine]').count()==0
        assert page.locator('.ia-grade-track [aria-current=step]').inner_text()=='一品'
        assert not errors
        page.screenshot(path=str(ROOT/f'build/immortal-exe-{with_dlc}.png'))
        browser.close()
    namespace['inspect_immortal_release'](engine,identity)
    reloaded=request(path);assert reloaded['immortal_artifacts']['equipment'][0]['grade']==1
    print(f'EXE immortal verified: DLC={with_dlc}; real promotion, four grades, exact costs, stale click recovery and reload',flush=True)
