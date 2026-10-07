"""Real HTTP and clicks: join, freight disclosure, map arrivals and read-only reload."""
import json
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
from cultivation_life.system.economy import state, caravans


def prepare(engine):
    game=engine._load(engine.create_game('商路经营','supreme_metal','dao',213,preset_id='core')['id'])
    alliance=game.merchant_state['worlds']['human'][0]
    game.player.location_id=alliance['hq']
    for _ in range(50):
        game.player.age+=1
        state.advance_economy(game)
        caravans.advance_caravans(game,engine.maps)
    game.pending_event=None
    game.player.next_tribulation_age=None
    game.settings['silent_events']=True
    engine.store.save(game)
    engine._load(game.id)
    return game.id


def main():
    output=ROOT/'build/economy-v2-r4-caravan-browser';output.mkdir(exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(393,852)]:
                            gid=prepare(engine)
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[]
                            page.on('pageerror',lambda err:errors.append(str(err)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',gid)
                            page.locator('[data-panel-target=merchant]').click()
                            group=page.locator('.merchant-alliance').first
                            group.locator('.merchant-caravans summary').click()
                            assert group.locator('.caravan-row').count()>=3
                            assert not group.locator('.caravan-row').get_by_text('周转资金',exact=False).count()
                            group.get_by_role('button',name='加入商盟',exact=True).click()
                            page.wait_for_function('!busy && !!game.merchant_system.membership')
                            group.locator('.merchant-caravans summary').click()
                            assert '周转资金' in group.locator('.caravan-row').first.inner_text()
                            assert '已上缴' in group.locator('.caravan-row').first.inner_text()
                            before=engine.store._path(gid).read_bytes()
                            group.locator('.merchant-caravans summary').click()
                            group.locator('.merchant-caravans summary').click()
                            assert engine.store._path(gid).read_bytes()==before
                            assert page.locator('#merchant-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                            group.locator('.merchant-caravans').scroll_into_view_if_needed()
                            page.screenshot(path=str(output/f'{theme}-{width}-merchant.png'))
                            page.locator('[data-panel-target=map]').click()
                            page.get_by_role('button',name='本地市场',exact=True).click()
                            page.locator('.economy-freight summary').click()
                            assert page.locator('.economy-freight').is_visible()
                            page.wait_for_function('getComputedStyle(document.querySelector("#map-card")).opacity==="1" && document.querySelector("#map-card").scrollWidth<=document.querySelector("#map-card").clientWidth+1')
                            assert page.locator('#map-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1'), (theme, width, page.locator('#map-card').evaluate('(root)=>({width:root.clientWidth,scroll:root.scrollWidth,overflow:[...root.querySelectorAll("*")].filter(n=>n.scrollWidth>root.clientWidth).map(n=>[n.tagName,n.className,n.scrollWidth,n.textContent.slice(0,100)])})'))
                            page.locator('.economy-freight').scroll_into_view_if_needed()
                            page.screenshot(path=str(output/f'{theme}-{width}-map.png'))
                            page.reload();page.wait_for_function('configData')
                            page.evaluate('async id=>loadGame(id)',gid)
                            assert engine.store._path(gid).read_bytes()==before
                            assert not errors,errors
                            checks.append(dict(theme=theme,width=width,status='passed'))
                            page.close()
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Caravan browser passed: 8 layouts, real join, member disclosure, map freight, no tick on viewing/reload')


if __name__=='__main__':main()
