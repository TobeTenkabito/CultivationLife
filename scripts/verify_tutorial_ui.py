"""Six themes, opt-in creation, deterministic apprenticeship and safe reading."""
import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine

class Quiet(server.Handler):
    def log_message(self,*args):pass

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT=Path(folder);engine=server.ENGINE=GameEngine(ROOT,Path(folder)/'saves')
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport={'width':412,'height':915})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                page.locator('#start-screen [data-tutorial-open]').click()
                assert page.locator('#tutorial-dialog').is_visible()
                page.locator('#tutorial-enabled').check()
                page.locator('#tutorial-close').click()
                page.locator('[name=name]').fill('教程验收')
                page.locator('#new-game-form [type=submit]').click()
                page.wait_for_function('game?.tutorial.enabled && !busy')
                assert page.locator('#tutorial-dialog').is_visible()
                game_id=page.evaluate('game.id');age=page.evaluate('game.player.age')
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    page.evaluate('GameThemes.saved')
                    for width in (412,800,1440):
                        page.set_viewport_size({'width':width,'height':915})
                        page.locator('#tutorial-chapter').select_option('0');page.wait_for_function('!busy && game.tutorial.step===0')
                        assert page.locator('#tutorial-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                        assert page.locator('#tutorial-dialog').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth+1')
                        if width==412:page.screenshot(path=str(ROOT/f'build/tutorial-{theme}-1480.png'))
                    page.locator('.tutorial-preview').click()
                    assert page.locator('#inventory-card').evaluate("e=>e.classList.contains('panel-open')")
                    page.evaluate("UtilityPanels.close('inventory')")
                    page.locator('#action-card [data-tutorial-open]').click()
                    page.locator('#tutorial-chapter').select_option('3');page.wait_for_function('!busy && game.tutorial.step===3')
                    page.locator('.tutorial-preview').click()
                    assert page.locator('#player-details-dialog').is_visible()
                    assert page.locator('details.techniques').evaluate('e=>e.open')
                    page.locator('[data-close-dialog=player-details-dialog]').click()
                    page.locator('#action-card [data-tutorial-open]').click()
                    page.locator('#tutorial-chapter').select_option('6');page.wait_for_function('!busy && game.tutorial.step===6')
                    if theme=='a':
                        page.get_by_role('button',name='开启师缘事件',exact=True).click();page.wait_for_function('!busy && !!game.tutorial.mentor')
                        page.get_by_role('button',name='执弟子礼，拜入门下',exact=True).click();page.wait_for_function("!busy && game.tutorial.mentor_result==='accepted'")
                        assert engine.store.load(game_id).player.master['realm_index']==3
                    else:assert '已拜入沈照尘门下' in page.locator('.tutorial-mentor').inner_text()
                    page.locator('#tutorial-enabled').uncheck();page.wait_for_function('!busy && !game.tutorial.enabled')
                    assert page.evaluate('game.player.age')==age
                    page.locator('#tutorial-close').click()
                    page.evaluate("UtilityPanels.open('settings')")
                    assert page.locator('#tutorial-handbook details').count()==10
                    page.locator('#setting-tutorial-open').click()
                    page.locator('#tutorial-enabled').check();page.wait_for_function('!busy && game.tutorial.enabled')
                page.locator('#tutorial-chapter').select_option('9');page.wait_for_function('!busy && game.tutorial.step===9')
                page.locator('#tutorial-next').click();page.wait_for_function('!busy && game.tutorial.completed && !game.tutorial.enabled')
                assert not page.locator('#tutorial-dialog').is_visible()
                original=engine.store.load(game_id)
                assert len([h for h in original.history if h.event_id=='SYS_TUTORIAL_MENTOR'])==2
                page.evaluate('(id)=>loadGame(id)',game_id)
                assert not page.locator('#tutorial-dialog').is_visible()
                assert page.evaluate('game.player.age')==age
                assert not errors,errors
                browser.close()
        finally:httpd.shutdown()
    print('Tutorial UI passed: six themes / three widths, opt-in creation, safe panel viewing, fixed Core Formation master, saved progress, settings handbook, no elapsed time or duplicate rewards')

if __name__=='__main__':main()
