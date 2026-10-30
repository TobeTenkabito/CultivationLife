"""Real tutorial clicks across pixel/text layouts, with byte-for-byte save guards."""
import json
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.release_evidence import inputs_digest


def step(page):
    return page.locator('.tutorial-tour').get_attribute('data-step')


def start(page):
    page.locator('#action-card [data-tutorial-open]').click()
    page.locator('#tutorial-interface-start').click()
    page.wait_for_selector('.tutorial-tour[data-mode=interface]:not([hidden])')


def walk(page,output,label,pause=False):
    for _ in range(30):
        key=step(page)
        assert key.startswith('ui_'),key
        assert page.locator('.tutorial-coach').evaluate('''n=>{const r=n.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1}'''),key
        if pause and key in {'ui_actions','ui_close_inventory','ui_save'}:
            page.keyboard.press('Escape')
            assert not page.locator('.tutorial-tour').is_visible()
            page.keyboard.press('Escape')
            start(page)
            assert step(page)==key
        if key in {'ui_scenery','ui_search','ui_save'}:
            page.screenshot(path=str(output/f'{label}-{key}.png'))
        info=page.evaluate('(key)=>{const s=TutorialInterface.resolve(key);return {target:s.target,read:!!s.read,input:!!s.input}}',key)
        if info['read']:
            page.locator('#guide-next').click()
        elif info['input']:
            page.locator(info['target']).fill('行囊')
        else:
            target=page.locator(info['target']).filter(visible=True).first
            assert target.is_enabled(),key
            # Actual hit testing catches a coach covering the highlighted control.
            target.click(timeout=6000)
        if key=='ui_finish':
            return
        page.wait_for_function('(old)=>document.querySelector(".tutorial-tour").dataset.step!==old',arg=key)
    raise AssertionError('Interface tour did not finish')


def main():
    output=ROOT/'build/tutorial-interface';output.mkdir(exist_ok=True)
    rows=[];source=inputs_digest(ROOT)
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        persistence=Path(folder)
        engine=GameEngine(ROOT,persistence/'saves')
        identity=engine.create_game('界面导览','supreme_wood','dao',330)['id']
        second=engine.create_game('切换人生','supreme_wood','dao',331)['id']
        guided=engine.create_game('实践衔接','supreme_wood','dao',332)['id']
        engine.tutorial_action(guided,'enable')
        advanced=engine.create_game('上界重看','supreme_wood','dao',333,preset_id='true_immortal')['id']
        old=engine.store.load(advanced)
        old.player.tutorial_state.update(enabled=False,guide_completed=True,completed=True)
        old.pending_event=None
        old.heavenly_court['open_election']=None
        engine.store.save(old)
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',persistence):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    scenarios=[(True,palette,w,h) for palette in ('light','dark') for w,h in [(1440,960),(412,915),(915,412),(754,365)]]
                    scenarios += [(False,theme,412,915) for theme in 'abdf']
                    if '--short-only' in sys.argv:scenarios=[row for row in scenarios if row[3]==365]
                    for pixel,palette,width,height in scenarios:
                        label=f'{"pixel" if pixel else "text"}-{palette}-{width}'
                        page=browser.new_page(viewport=dict(width=width,height=height),has_touch=height<520)
                        errors=[];requests=[]
                        page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData && !busy')
                        page.locator('#theme-open').click()
                        toggle=page.locator('#theme-dialog [data-pixel-setting]')
                        toggle.set_checked(pixel)
                        if pixel:page.locator(f'[data-theme-picker=dialog] [data-pixel-theme-choice={palette}]').click()
                        else:page.locator(f'[data-theme-picker=dialog] [data-theme-choice={palette}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        page.evaluate('GameThemes.saved')
                        page.evaluate('async id=>{await loadGame(id);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}',identity)
                        before=engine.store._path(identity).read_bytes()
                        page.on('request',lambda r:requests.append(r.url) if r.method=='POST' and '/api/games/' in r.url else None)
                        start(page)
                        walk(page,output,label,pause=width==412)
                        assert not page.locator('.tutorial-tour').is_visible()
                        assert not requests,requests
                        assert engine.store._path(identity).read_bytes()==before
                        assert not errors,errors
                        # A finished tour can be replayed without resetting the real course.
                        page.locator('#setting-tutorial-open').click()
                        page.locator('#tutorial-interface-start').click()
                        assert step(page)=='ui_welcome'
                        if label=='pixel-light-412':
                            # The previous tour left this chapter expanded. A
                            # replay must advance on its first real summary tap.
                            walk(page,output,label+'-repeat')
                            assert not page.locator('.tutorial-tour').is_visible()
                            assert engine.store._path(identity).read_bytes()==before
                        page.keyboard.press('Escape')
                        page.evaluate('(id)=>loadGame(id)',second)
                        assert not page.locator('.tutorial-tour').is_visible()
                        page.close();rows.append(dict(scenario=label,status='passed'))
                        print(label,'passed',flush=True)
                    if scenarios:
                        page=browser.new_page(viewport=dict(width=412,height=915))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData && !busy')
                        page.evaluate('(id)=>loadGame(id)',advanced)
                        before=engine.store._path(advanced).read_bytes()
                        page.locator('#action-card [data-tutorial-open]').click()
                        assert page.locator('#tutorial-start').is_disabled()
                        assert page.locator('#tutorial-interface-start').is_enabled()
                        page.locator('#tutorial-interface-start').click()
                        walk(page,output,'completed-upper')
                        assert not page.locator('.tutorial-tour').is_visible()
                        assert engine.store._path(advanced).read_bytes()==before
                        page.close();rows.append(dict(scenario='completed-upper',status='passed'))
                        print('completed-upper passed',flush=True)
                        page=browser.new_page(viewport=dict(width=412,height=915))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData && !busy')
                        page.evaluate('(id)=>loadGame(id)',identity)
                        start(page)
                        pending=engine.store.load(identity)
                        pending.player.realm_index=1
                        pending.pending_event=engine._instantiate_event(engine.events_by_id['EVT_TECHNIQUE_STELE_001'],pending,random.Random(2))
                        engine.store.save(pending)
                        page.evaluate('(id)=>loadGame(id)',identity)
                        before=engine.store._path(identity).read_bytes()
                        assert not page.locator('#guide-next').is_visible()
                        assert '暂停' in page.locator('#guide-copy').inner_text()
                        page.locator('#guide-pause').click()
                        assert not page.locator('.tutorial-tour').is_visible()
                        assert page.locator('#event-choices button:enabled').count()>0
                        assert engine.store._path(identity).read_bytes()==before
                        page.close();rows.append(dict(scenario='pending-event-pause',status='passed'))
                        print('pending-event-pause passed',flush=True)
                    # Keep an in-progress real course intact while learning the new UI.
                    page=browser.new_page(viewport=dict(width=1440,height=960))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData && !busy')
                    page.evaluate('(id)=>loadGame(id)',guided)
                    before=engine.store._path(guided).read_bytes()
                    page.locator('#guide-interface-start').click()
                    # Rotating/resizing mid-guide must reveal the same real moved button.
                    while step(page)!='ui_directory':
                        key=step(page);info=page.evaluate('(k)=>{const s=TutorialInterface.resolve(k);return {target:s.target,read:!!s.read}}',key)
                        print('handoff',key,flush=True)
                        page.locator('#guide-next' if info['read'] else info['target']).filter(visible=True).first.click()
                        page.wait_for_function('(old)=>document.querySelector(".tutorial-tour").dataset.step!==old',arg=key)
                    page.set_viewport_size(dict(width=412,height=915))
                    page.wait_for_function('GameNavigation.isCompact()')
                    page.locator('[data-navigation-category=craft]').click()
                    page.wait_for_function('document.querySelector(".tutorial-tour").dataset.step==="ui_search"')
                    page.set_viewport_size(dict(width=1440,height=960))
                    page.wait_for_function('!GameNavigation.isCompact()')
                    # Desktop search lesson now shows the real open inventory instead.
                    page.wait_for_function('document.querySelector("#inventory-card").classList.contains("panel-open")')
                    walk(page,output,'resized')
                    assert step(page)=='welcome' and page.locator('.tutorial-tour').is_visible()
                    assert engine.store._path(guided).read_bytes()==before
                    page.locator('#guide-pause').click()
                    page.wait_for_function('!busy && !game.tutorial.enabled')
                    page.close();browser.close()
            finally:http.shutdown();http.server_close()
    assert inputs_digest(ROOT)==source,'Production sources changed during browser acceptance'
    checks=['actual clicks','two pixel palettes','pause/resume/replay','responsive relocation','course handoff','no game POST','identical save bytes']
    checks+=['754x365 touch landscape'] if '--short-only' in sys.argv else ['four text themes','desktop/portrait/landscape','754x365 touch landscape']
    report_name='report-short.json' if '--short-only' in sys.argv else 'report.json'
    (output/report_name).write_text(json.dumps(dict(status='passed',inputs_sha256=source,scenarios=rows,checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Interface tutorial passed: {len(rows)} scenarios, real clicks, responsive handoff and unchanged saves')


if __name__=='__main__':main()
