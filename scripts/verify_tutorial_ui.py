"""Click the real highlighted controls through the complete four-theme course."""
import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine

class Quiet(server.Handler):
    def log_message(self,*args):pass

def main():
    pixel='--pixel' in sys.argv;desktop='--desktop' in sys.argv;short='--short-landscape' in sys.argv
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT=Path(folder);engine=server.ENGINE=GameEngine(ROOT,Path(folder)/'saves')
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport={'width':754 if short else 1440 if desktop else 412,'height':365 if short else 960 if desktop else 915},has_touch=short)
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function("configData!==null && !!window.TutorialGuide && typeof document.querySelector('#start-screen [data-tutorial-open]').onclick==='function'")
                for theme_index,theme in enumerate(('light','dark') if pixel else 'abdf'):
                    page.evaluate('showStart()')
                    if pixel:
                        page.locator('#theme-open').click()
                        page.locator('#theme-dialog [data-pixel-setting]').check()
                        page.locator(f'[data-theme-picker=dialog] [data-pixel-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click()
                    else:page.evaluate('(t)=>document.querySelector(`[data-theme-picker=start] [data-theme-choice=${t}]`).click()',theme)
                    page.evaluate('GameThemes.saved')
                    if theme_index==0:
                        page.locator('#start-screen [data-tutorial-open]').click()
                        page.wait_for_selector('#tutorial-dialog[open]')
                        page.locator('#tutorial-enabled').check();page.locator('#tutorial-start').click()
                        page.locator('[name=name]').fill('亲手问道');page.locator('#new-game-form [type=submit]').click()
                    else:
                        page.evaluate("async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'操作验收',spirit_root:'supreme_wood',path:'dao',seed:1481,tutorial_enabled:true})});await loadGame(g.id);}")
                    page.wait_for_function('!busy && game?.tutorial.guide.active')
                    key=page.evaluate('game.id');before=engine.store.load(key);age=before.player.age
                    for _ in range(32):
                        step=page.evaluate('game.tutorial.guide.step');print(theme,step,flush=True)
                        assert page.locator('.tutorial-tour').is_visible()
                        if step=='practice' and not desktop and not short:
                            for w,h in [(1440,915),(915,412),(412,915)]:
                                page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(100)
                                assert page.locator('.tutorial-coach').evaluate('e=>e.getBoundingClientRect().right<=innerWidth+1 && e.getBoundingClientRect().bottom<=innerHeight+1')
                        if step in {'practice','mentor_choice','join'}:page.screenshot(path=str(ROOT/f'build/guide-{theme}-{step}-{"short" if short else "desktop" if desktop else "phone"}-1481.png'))
                        if step=='bag' and desktop:
                            page.set_viewport_size({'width':412,'height':915})
                            page.wait_for_function('GameNavigation.isCompact() && document.querySelector("#navigation-menu").open')
                            page.set_viewport_size({'width':1440,'height':960})
                            page.wait_for_function('!GameNavigation.isCompact()')
                        if step=='gain' and theme_index==0:
                            page.locator('#guide-pause').click();page.wait_for_function('!busy && !game.tutorial.enabled')
                            page.locator('#action-card [data-tutorial-open]').click();page.locator('#tutorial-start').click();page.wait_for_function('!busy && game.tutorial.enabled')
                            assert page.evaluate('game.tutorial.guide.step')=='gain'
                        if step=='join' and theme_index==0:
                            page.reload();page.wait_for_function('!!configData');page.evaluate('(id)=>loadGame(id)',key)
                            page.wait_for_function("!busy && game.tutorial.guide.step==='join'")
                        if step=='join':
                            selected=page.evaluate('game.tutorial.guide.admissions.slice(-1)[0].id')
                            page.locator('#guide-sect-select').select_option(selected)
                        if page.locator('#guide-next').is_visible():page.locator('#guide-next').click()
                        else:
                            selector=page.evaluate('TutorialSteps[game.tutorial.guide.step].target')
                            if step=='mentor_choice':selector='[data-guide-choice=guide_decline]' if theme=='b' else '[data-guide-choice=guide_accept]'
                            if step=='join':selector=f'.tutorial-faction-join[data-faction-id="{selected}"]'
                            target=page.locator(selector).filter(visible=True).first
                            assert target.is_enabled(),step
                            target.click(timeout=6000)
                        page.wait_for_function('(old)=>!busy && (game.tutorial.guide.step!==old || game.tutorial.guide.completed)',arg=step)
                        assert page.evaluate('game.player.age')==age
                    after=engine.store.load(key)
                    assert after.player.tutorial_state['guide_completed'] and after.player.faction_id
                    assert after.player.faction_id==selected
                    assert bool(after.player.master)==(theme!='b')
                    assert after.rng_state==before.rng_state
                    page.evaluate('(id)=>loadGame(id)',key)
                    assert not page.locator('.tutorial-tour').is_visible()
                assert not errors,errors
                browser.close()
        except Exception:
            print(errors,flush=True)
            raise
        finally:httpd.shutdown()
    print(f'Tutorial UI passed: {"pixel palettes" if pixel else "four text themes"}, {"754x365 touch landscape" if short else "desktop with responsive relocation" if desktop else "three widths"}, all 32 real steps, deterministic rewards, pause/reload, no elapsed time')
if __name__=='__main__':main()
