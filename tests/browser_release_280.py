"""Actual category navigation, lower-world field creation and fresh lazy panels."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator

def main():
    output=ROOT/'build/navigation-280';output.mkdir(exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(360,800),(412,915),(915,412)]:
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_selector('#custom-start')
                            page.evaluate('GameNavigation.ready')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            for rank in (1,4):
                                if rank==4:
                                    page.evaluate('showStart()')
                                page.locator('#custom-start>summary').click()
                                page.locator('#custom-root').select_option('otherworld')
                                page.locator('#custom-path').select_option('dao')
                                page.locator('#custom-world').select_option('spirit')
                                page.locator('#custom-realm').select_option('8')
                                page.locator('#custom-tendency').select_option('strike')
                                page.locator('#custom-domain-rank').fill(str(rank))
                                page.locator('#custom-start-submit').click()
                                page.wait_for_function('game && !busy')
                                identity=page.evaluate('game.id')
                                before=engine.store._path(identity).read_bytes()
                                assert page.locator('[data-navigation-category]').count()==6
                                assert page.evaluate('document.querySelector("#navigation-bar").scrollWidth<=document.querySelector("#navigation-bar").clientWidth+1')
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                navigation_locator(page,'[data-panel-target=spirit-voisinage]').click()
                                page.wait_for_selector('#spirit-voisinage-card.panel-open')
                                page.wait_for_function('()=>{const r=document.querySelector("#spirit-voisinage-card").getBoundingClientRect();return r.left>=0&&r.top>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1}',timeout=5000)
                                assert f'Lv{rank}' in page.locator('#spirit-voisinage-content').inner_text()
                                assert page.evaluate('game.aperture.available')==(rank>=4)
                                if rank==1:
                                    assert page.locator('[data-panel-target=immortal-aperture]').evaluate('b=>b.classList.contains("hidden")')
                                    assert '尚需合参' in page.locator('#spirit-voisinage-content').inner_text()
                                else:
                                    assert '展开 12' in page.locator('#spirit-voisinage-content').inner_text()
                                page.locator('[data-navigation-category=practice]').click()
                                pin=page.locator('[data-navigation-pin=spirit-voisinage]')
                                if pin.get_attribute('aria-pressed')!='true':pin.click()
                                page.locator('[data-navigation-tab=common]').click()
                                page.locator('[data-navigation-shortcut=spirit-voisinage]').wait_for()
                                page.locator('#navigation-search').fill('灵域')
                                assert page.locator('.navigation-entry:visible').count()>=1
                                page.locator('[data-panel-target=spirit-voisinage]').click()
                                # The original button toggles the current panel; open it again from common.
                                page.locator('[data-navigation-category=common]').click()
                                page.locator('[data-navigation-shortcut=spirit-voisinage]').click()
                                page.wait_for_selector('#spirit-voisinage-card.panel-open',state='visible')
                                page.locator('[data-navigation-category=worlds]').click()
                                page.keyboard.press('Escape')
                                assert not page.locator('#navigation-menu').evaluate('d=>d.open')
                                assert page.locator('#spirit-voisinage-card').is_visible()
                                # Map is rendered from this response only when actually opened.
                                navigation_locator(page,'[data-panel-target=map]').click()
                                page.wait_for_selector('#map-card.panel-open',state='visible')
                                actual=page.locator('#map-current').text_content()
                                expected='当前：'+page.evaluate('game.map.current_name')
                                assert actual==expected,(actual,expected,errors)
                                page.wait_for_function('()=>{const r=document.querySelector("#map-card").getBoundingClientRect();return r.left>=0&&r.top>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1}',timeout=5000)
                                for category in ['common','practice','craft','economy','people','worlds']:
                                    page.locator(f'[data-navigation-category={category}]').click() if not page.locator('#navigation-menu').evaluate('d=>d.open') else page.locator(f'[data-navigation-tab={category}]').click()
                                    assert page.locator('#navigation-menu').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
                                    assert page.locator('#navigation-bar button').evaluate_all('bs=>bs.every(b=>b.getBoundingClientRect().height>=44)')
                                page.wait_for_timeout(250)
                                page.screenshot(path=str(output/f'{theme}-{width}-{rank}.png'))
                                page.locator('#navigation-close').click()
                                page.evaluate('GameNavigation.saved')
                                assert engine.store._path(identity).read_bytes()==before
                                page.reload();page.wait_for_function('configData && !busy')
                                page.evaluate('GameNavigation.ready')
                                page.evaluate('async id=>loadGame(id)',identity)
                                page.locator('[data-navigation-category=common]').click()
                                assert page.locator('[data-navigation-shortcut=spirit-voisinage]').count()==1
                                page.locator('#navigation-close').click()
                                if theme=='a' and width==360 and rank==1:
                                    alternate=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
                                    threading.Thread(target=alternate.serve_forever,daemon=True).start()
                                    try:
                                        page.goto(f'http://127.0.0.1:{alternate.server_port}')
                                        page.wait_for_function('!!configData');page.evaluate('GameNavigation.ready')
                                        page.evaluate('async id=>loadGame(id)',identity)
                                        page.locator('[data-navigation-category=common]').click()
                                        assert page.locator('[data-navigation-shortcut=spirit-voisinage]').count()==1
                                        page.locator('#navigation-close').click()
                                        page.goto(f'http://127.0.0.1:{http.server_port}')
                                        page.wait_for_function('!!configData');page.evaluate('GameNavigation.ready')
                                        page.evaluate('async id=>loadGame(id)',identity)
                                    finally:alternate.shutdown();alternate.server_close()
                                rows.append(dict(theme=theme,width=width,rank=rank,status='passed'))
                            # Switching lives must discard unopened map work in favour of the new response.
                            other=engine.create_game('另世地图','heavenly','dao',281,preset_id='core')
                            page.evaluate('async id=>loadGame(id)',other['id'])
                            navigation_locator(page,'[data-panel-target=map]').click()
                            page.wait_for_selector('#map-card.panel-open',state='visible')
                            assert page.locator('#map-current').text_content()=='当前：'+other['map']['current_name']
                            assert page.locator('[data-panel-target=spirit-voisinage]').evaluate('b=>b.classList.contains("hidden")')
                            page.locator('[data-navigation-category=common]').click()
                            assert page.locator('[data-navigation-shortcut=spirit-voisinage]').count()==0
                            assert not errors,errors
                            page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Release 280 navigation passed: 32 real lower-world creations, four themes, desktop/360/412/landscape, category search, pins, Escape, reload, locked energy and latest map')

if __name__=='__main__':main()
