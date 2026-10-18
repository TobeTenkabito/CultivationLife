"""Real page clicks: Guixu interruption, reload, disabled travel and continuation."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from fixtures.regional_calendar_release import prepare_regional_journey, inspect_regional_journey
from scripts.browser_navigation import navigation_locator, click_control


def main():
    output=ROOT/'build/regional-calendar-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='regional-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1'])
                    for theme in ('a','b','d','f'):
                        for width,height in [(1440,960),(393,852),(852,393)]:
                            identity=engine.create_game('远行验收','none','dao',20261018)['id']
                            prepare_regional_journey(engine,identity)
                            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                            page.on('dialog',lambda d:d.accept())
                            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_function('!!configData')
                            page.evaluate('async id=>loadGame(id)',identity)
                            page.evaluate('t=>document.documentElement.dataset.theme=t',theme)
                            navigation_locator(page,'[data-panel-target=map]').click()
                            click_control(page.locator('.map-travel[data-destination=lanjiang_steppe]'))
                            page.wait_for_function("!busy && game.pending_event?.id==='EVT_GUIXU_ANNOUNCE'")
                            inspect_regional_journey(engine,identity)
                            assert page.locator('.map-travel[data-destination=lanjiang_steppe]').is_disabled()
                            page.reload();page.wait_for_function('!!configData')
                            page.evaluate('async id=>loadGame(id)',identity)
                            for _ in range(20):
                                if engine.store.load(identity).player.location_id == 'lanjiang_steppe':break
                                if page.evaluate('!!game.pending_event'):
                                    if page.locator('#map-card').is_visible():click_control(page.locator('#map-toggle'))
                                    click_control(page.locator('#event-choices button:not([disabled])').first)
                                    page.wait_for_function('!busy')
                                else:
                                    if not page.locator('#map-card').is_visible():navigation_locator(page,'[data-panel-target=map]').click()
                                    button=page.locator('.map-travel[data-destination=lanjiang_steppe]')
                                    assert '继续' in button.inner_text()
                                    page.screenshot(path=str(output/f'continue-{theme}-{width}.png'))
                                    click_control(button);page.wait_for_function('!busy')
                            inspect_regional_journey(engine,identity,True)
                            assert not errors,errors
                            page.close()
                    # Read the real merchant panel, then reload its frozen
                    # order: no fabricated progress or state mutation on view.
                    from test_merchant_execution import posted
                    from cultivation_life.engine.world import regions
                    identity=engine.create_game('异界消息验收','heavenly','dao',20261018,preset_id='core')['id']
                    game=engine._load(identity)
                    _,game,order=posted((engine,game))
                    engine._merchant_start_order(game,order,__import__('random').Random(4))
                    regions.ensure(engine,game)
                    game.player.world='demon'  # Disposable remote observation.
                    game.player.location_id=game.merchant_state['worlds']['demon'][0]['hq']
                    game.player.age+=20
                    regions.synchronize(engine,game,['demon'])
                    engine.store.save(game)
                    page=browser.new_page(viewport=dict(width=393,height=852))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData')
                    for repeat in range(2):
                        page.evaluate('async id=>loadGame(id)',identity)
                        navigation_locator(page,'[data-panel-target=merchant]').click()
                        row=page.locator(f'.merchant-order[data-order-id="{order["id"]}"]')
                        assert '暂无法得到确切进度' in row.inner_text()
                        assert row.locator('progress').count()==0
                        assert engine.store.load(identity).merchant_state['posted'][-1]['status']=='working'
                        page.screenshot(path=str(output/f'remote-notice-{repeat}.png'))
                        page.reload();page.wait_for_function('!!configData')
                    page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'result.json').write_text(json.dumps(dict(passed=True,themes=4,layouts=3,
        checks=['real-travel','real-guixu-choice','reload','disabled-during-event','remaining-years','single-total-time'])),encoding='utf8')
    print('Regional travel browser acceptance passed')


if __name__=='__main__':main()
