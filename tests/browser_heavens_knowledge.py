"""Real HTTP settings placement, theme choices and observer-relative news."""
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
from test_heavens_m1 import local, quiet, issue
from test_heavens_incidents import positioned
from cultivation_life.system.heavens.incident_definitions import INCIDENTS
from cultivation_life.system.heavens.intelligence import acquire_merchant_reports


def main():
    output=ROOT/'build/heavens-knowledge-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        bundle=quiet(local.__wrapped__(Path(folder)))
        engine, initial, _=bundle
        game=positioned(bundle,INCIDENTS[0])
        factions=[s for s in game.sects.values() if s.world=='celestial' and not s.extinct]
        war=engine._start_war(game,'sect',factions[0].id,factions[1].id)
        engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    page=browser.new_page(viewport=dict(width=393,height=852),has_touch=True)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>loadGame(id)',initial.id)
                    assert page.locator('[data-theme-picker=start] button').count()==4
                    assert page.locator('[data-theme-choice=c],[data-theme-choice=e]').count()==0
                    names=page.locator('[data-theme-picker=dialog] b').all_text_contents()
                    assert names==['松烟书院','月下观星','丹砂金阙','竹简纪年']
                    page.locator('[data-panel-target=heavens]').tap()
                    assert page.locator('#heavens-content input[type=checkbox]').count()==0
                    assert page.locator('#heavens-content').get_by_text('偏好',exact=True).count()==0
                    view=page.evaluate('game.heavens')
                    assert len(view['incidents'])==len(view['anomalies'])==len(view['conflicts'])==4
                    assert view['intelligence'][0]['level']==1
                    assert factions[0].name not in json.dumps(view,ensure_ascii=False)
                    page.get_by_role('button',name='查看诸天风闻',exact=True).tap()
                    assert '小周天' in page.locator('.heavens-incident-document').inner_text()
                    page.screenshot(path=str(output/'human-omen.png'))
                    page.locator('#heavens-toggle').tap()
                    page.locator('[data-panel-target=settings]').tap()
                    row=page.get_by_label('显示诸天机会通知',exact=True)
                    before=engine.store.load(initial.id).player.age
                    row.scroll_into_view_if_needed();row.uncheck()
                    page.wait_for_function('!busy && game.heavens.watch===false')
                    assert engine.store.load(initial.id).heavens_state['watch'] is False
                    assert engine.store.load(initial.id).player.age==before
                    page.screenshot(path=str(output/'settings.png'))
                    for desc,expected in [(INCIDENTS[1],2),(INCIDENTS[7],3)]:
                        positioned(bundle,desc)
                        page.evaluate('async id=>loadGame(id)',initial.id)
                        assert page.evaluate('game.heavens.intelligence[0].level')==expected
                    game=engine.store.load(initial.id)
                    game.player.location_id='law_sea'
                    engine.store.save(game)
                    issue(bundle,'observe',target='sea_echo')
                    game=positioned(bundle,INCIDENTS[0])
                    engine.store.save(game)
                    page.evaluate('async id=>loadGame(id)',initial.id)
                    page.evaluate("UtilityPanels.open('heavens')")
                    page.get_by_role('tab',name='诸界',exact=True).tap()
                    page.get_by_label('选择界域',exact=True).select_option('celestial')
                    assert page.locator('.heavens-destination').count()==1
                    assert '法则天海' in page.locator('.heavens-destination').inner_text()
                    acquire_merchant_reports(game,'celestial',3)
                    engine.store.save(game)
                    page.evaluate('async id=>loadGame(id)',initial.id)
                    rows=page.evaluate('game.heavens.intelligence')
                    assert rows[0]['level']==1 and rows[-1]['level']==3
                    assert rows[-1]['source']=='跨界商盟情报委托'
                    assert war['logs'][-1]['text'] in rows[-1]['text']
                    assert not errors,errors
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    print('Knowledge UI passed: four named themes, settings persistence, three observer levels and merchant snapshot')


if __name__=='__main__':main()
