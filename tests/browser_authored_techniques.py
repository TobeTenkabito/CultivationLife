"""Real authoring, upgrade, stale recovery, lineage selection and Android-width contact layout."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator,reveal_subpage,set_theme


def main():
    output=ROOT/'build/authored-ui';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        g=e._load(e.create_game('著经界面验收','supreme_metal','dao',310,preset_id='core')['id']);g.pending_event=None
        for t in g.player.known_techniques:t.level=9
        e.store.save(g)
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960));errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    base=f'http://127.0.0.1:{http.server_port}'
                    page.goto(base);page.wait_for_function('!!configData&&!busy');page.evaluate('id=>loadGame(id)',g.id)
                    navigation_locator(page,'[data-panel-target=authored]').click()
                    page.locator('[data-authored-input=name]').fill('流云自著真经')
                    page.locator('[data-authored-input=category]').select_option('support')
                    page.locator('[data-author-add-buff]').click()
                    selects=page.locator('.at-buff select');selects.nth(1).select_option('from_round');selects.nth(2).select_option('restore')
                    page.locator('.at-buff input').nth(2).fill('3')
                    page.wait_for_function('!document.querySelector("[data-author-create]").disabled')
                    page.locator('[data-author-create]').click();page.wait_for_function('!busy&&game.authored_techniques.books.length===1')
                    key=page.evaluate('game.authored_techniques.books[0].id')
                    page.locator('[data-author-manual]').click();page.wait_for_function('!busy&&game.authored_techniques.revision===2')
                    page.locator('[data-author-upgrade]').click();page.wait_for_function('!busy&&game.authored_techniques.books[0].level===2')
                    assert '第3轮起' in page.locator('.at-book').inner_text()
                    # A different browser spent points; this open editor must reject its old revision and recover.
                    result=page.request.post(base+f'/api/games/{g.id}/authored-technique',data=dict(action='manual',id=key,level=2,revision=2));assert result.ok
                    spent=result.json()['authored_techniques']['points']['spent']
                    page.locator('[data-author-manual]').click();page.wait_for_function('!busy&&game.authored_techniques.revision===3')
                    assert page.evaluate('game.authored_techniques.points.spent')==spent
                    for theme in ['a','b','d','f']:
                        set_theme(page,theme)
                        for width,height in [(1440,960),(390,844),(844,390),(320,740)]:
                            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(250)
                            if not page.locator('#authored-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2'):
                                page.screenshot(path=str(output/'overflow.png'))
                                print(theme,width,page.locator('#authored-card').evaluate('n=>({w:n.clientWidth,s:n.scrollWidth,bad:[...n.querySelectorAll("*")].filter(x=>x.scrollWidth>x.clientWidth+2).map(x=>[x.className,x.clientWidth,x.scrollWidth])})'),flush=True)
                                print(page.locator('#authored-card').evaluate('n=>({style:n.getAttribute("style"),pseudo:["::before","::after"].map(p=>[getComputedStyle(n,p).cssText,getComputedStyle(n,p).width,getComputedStyle(n,p).transform]),bad:[...n.querySelectorAll("*")].filter(x=>x.getBoundingClientRect().right>n.getBoundingClientRect().right+1).map(x=>[x.tagName,x.className,x.getBoundingClientRect().x,x.getBoundingClientRect().width,x.getAttribute("style")])})'),flush=True)
                                raise AssertionError('Authoring overflow')
                            if theme=='a':page.screenshot(path=str(output/f'author-{width}.png'))
                    page.locator('#authored-toggle').click()
                    page.locator('#theme-open').click();page.locator('#theme-dialog [data-pixel-setting]').set_checked(True);page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
                    navigation_locator(page,'[data-panel-target=relationship]').click()
                    search=page.locator('#npc-contacts input[type=search]');reveal_subpage(page,search);search.fill('顾长庚');page.locator('.contact-person').click()
                    page.locator('.contact-detail .npc-art-figure').wait_for(state='visible')
                    for width,height in [(390,844),(844,390),(320,740)]:
                        page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(250);reveal_subpage(page,search)
                        assert page.locator('.contact-detail').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                        assert page.locator('.contact-hero').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                        page.screenshot(path=str(output/f'contacts-{width}.png'))
                    page.locator('#relationship-toggle').click();page.evaluate('showStart()')
                    page.wait_for_function('document.querySelector("#authored-lineage").options.length>1')
                    page.locator('#authored-lineage').select_option(g.id)
                    page.locator('#new-game-form input[name=name]').fill('继承界面验收')
                    page.locator('#new-game-form button[type=submit]').click();page.wait_for_function('!busy&&game&&game.player.name==="继承界面验收"')
                    assert page.evaluate('game.authored_techniques.books[0].own') is False
                    assert page.evaluate('game.authored_techniques.books[0].level')==0
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Authored UI passed: actual create/manual/upgrade/stale recovery, one-generation new game, four themes and contact art at 320/390/844 widths')

if __name__=='__main__':main()
