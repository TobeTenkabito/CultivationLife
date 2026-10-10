"""Actual HTTP military actions and four-theme independent page acceptance."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.rules import max_hp, max_mp
from test_heavens_campaign import local, site, ready, military, construction, load


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT/'build/heavens-m3-r2-browser'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        fixture = military.__wrapped__(ready.__wrapped__(site.__wrapped__(local.__wrapped__(Path(folder)))))
        engine, initial, _ = fixture
        work = construction(fixture)
        work.player.realm_index, work.player.layer = 4,9
        work.player.hp, work.player.mp = max_hp(work.player), max_mp(work.player)
        engine.store.save(work)
        key = initial.id
        with patch.object(server,'ENGINE',engine), patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1050})
                    errors = []
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    navigation_locator(page,'[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='战局',exact=True).click()
                    assert page.locator('#heavens-content .heavens-destination').count() == 2
                    assert page.get_by_role('button',name='击退当地守卫',exact=True).count() == 0
                    page.get_by_role('button',name='查看岚疆界门',exact=True).click()
                    page.get_by_role('tab',name='界门',exact=True).click()
                    assert page.get_by_role('button',name='查勘界门工地',exact=True).is_enabled(), page.locator('#heavens-body').inner_text()
                    before = engine.store._path(key).read_bytes()
                    page.get_by_role('button',name='查勘界门工地',exact=True).click()
                    page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                    page.locator('#game-confirm-cancel').click()
                    assert engine.store._path(key).read_bytes() == before
                    page.get_by_role('button',name='查勘界门工地',exact=True).click()
                    page.locator('#game-confirm-accept').click()
                    page.wait_for_function('!busy && game.heavens.campaign.gate')
                    snapshot = engine.store._path(key).read_bytes()
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393,320):
                            page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                            page.get_by_role('tab',name='战局',exact=True).click()
                            page.get_by_role('button',name='查看岚疆界门',exact=True).click()
                            for tab in ('军情','界门','交锋','援助'):
                                page.get_by_role('tab',name=tab,exact=True).click()
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                assert page.locator('#heavens-body').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                                if tab != '交锋':
                                    assert page.get_by_role('button',name='击退当地守卫',exact=True).count() == 0
                                if width != 320 and tab in {'界门','交锋'}:
                                    page.screenshot(path=str(output/f'{theme}-{width}-{tab}.png'))
                    assert engine.store._path(key).read_bytes() == snapshot
                    page.set_viewport_size({'width':393,'height':852})
                    page.get_by_role('tab',name='交锋',exact=True).click()
                    page.get_by_role('button',name='击退当地守卫',exact=True).click()
                    page.locator('#game-confirm-accept').click()
                    page.wait_for_function("!busy && game.heavens.campaign.reports.some(r=>r.kind==='personal_battle')")
                    work = engine.store.load(key)
                    assert work.last_combat_report
                    assert work.heavens_state['runtime']['campaign']['status'] == 'withdrawing'
                    page.locator('#battle-report-toggle').click()
                    page.get_by_role('tab',name='界门',exact=True).click()
                    page.get_by_role('button',name='拆除目标端界门',exact=True).click()
                    page.locator('#game-confirm-accept').click()
                    page.wait_for_function("!busy && game.heavens.campaign.gate.state==='destroyed'")
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    assert page.evaluate("game.heavens.campaign.reports.some(r=>r.kind==='demolition')")
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(themes=list('abdf'),widths=[1440,393,320],
                        errors=errors,preview_cancel=True,pure_navigation=True,real_combat=True,demolition=True,reload=True),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    print('M3 second round HTTP combat / gate / four-theme acceptance passed')


if __name__ == '__main__':
    main()
