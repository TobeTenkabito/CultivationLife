"""Eleven-world dossiers: four themes, narrow screens, touch and persisted work."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.system.heavens.incident_definitions import ALL_INCIDENTS as INCIDENTS
from test_heavens_incidents import local, quiet, positioned
from test_heavens_m1 import issue


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT/'build/heavens-all-worlds-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        bundle = quiet(local.__wrapped__(Path(folder)))
        engine, initial, _ = bundle
        for desc in INCIDENTS:
            positioned(bundle, desc)
            issue(bundle, 'incident_survey', target=desc.id)
        work = positioned(bundle, INCIDENTS[0], True)
        work.settings['silent_events'] = True
        engine.store.save(work)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)), patch.object(engine, '_advance_guixu_calendar', return_value=False):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':393,'height':852}, has_touch=True)
                    errors, checks = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}', initial.id)
                    navigation_locator(page,'[data-panel-target=heavens]').tap()
                    before = engine.store._path(initial.id).read_bytes()
                    for theme in 'abdf':
                        page.set_viewport_size({'width':393,'height':852})
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width,height in ((1440,1050),(393,852),(320,852),(780,360),(1024,400)):
                            page.set_viewport_size({'width':width,'height':height})
                            for desc in INCIDENTS:
                                page.get_by_role('tab',name={'local':'诸界','anomaly':'异象','conflict':'战局'}[desc.category],exact=True).click()
                                page.get_by_label('选择界域',exact=True).select_option(desc.world)
                                assert page.locator('.heavens-destination').count() <= 3
                                page.get_by_role('button',name='查看'+desc.name,exact=True).click()
                                for tab in ('见闻档案','现场事务','后续影响'):
                                    page.get_by_role('tab',name=tab,exact=True).click()
                                    body = page.locator('#heavens-detail-body')
                                    assert body.locator('[data-heavens-action]').count() <= 1
                                    if height < 520:
                                        assert page.locator('#heavens-body').bounding_box()['height'] >= 140
                                        close = page.locator('#heavens-toggle').bounding_box()
                                        assert 0 <= close['y'] and close['y']+close['height'] <= height
                                    assert body.locator('p').count() > 0
                                    assert body.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                    for button in body.locator('[data-heavens-action],select').all():
                                        assert button.bounding_box()['height'] >= 44
                                    checks.append(dict(theme=theme,width=width,world=desc.world,tab=tab))
                                if desc.world in {'human','asura'} and width!=320:
                                    page.get_by_role('tab',name='见闻档案',exact=True).click()
                                    page.screenshot(path=str(output/f'{theme}-{width}-{desc.id}.png'))
                    assert engine.store._path(initial.id).read_bytes() == before
                    page.set_viewport_size({'width':393,'height':852})
                    page.get_by_role('tab',name='诸界',exact=True).tap()
                    page.get_by_label('选择界域',exact=True).select_option('human')
                    page.get_by_role('button',name='查看断烽归路',exact=True).tap()
                    page.get_by_role('tab',name='现场事务',exact=True).tap()
                    page.get_by_label('界域处理方案',exact=True).select_option('incident_seal')
                    page.get_by_role('button',name='封存误导路引',exact=True).tap()
                    page.locator('#game-confirm-cancel').tap()
                    assert engine.store._path(initial.id).read_bytes() == before
                    page.get_by_role('button',name='封存误导路引',exact=True).tap()
                    page.locator('#game-confirm-accept').tap()
                    page.wait_for_function("!busy && game.heavens.incidents.find(r=>r.id==='human_beacon').stage==='treated'",timeout=120000)
                    saved = engine.store.load(initial.id)
                    assert saved.player.age == work.player.age+2
                    page.reload();page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}', initial.id)
                    assert page.evaluate("game.heavens.incidents.find(r=>r.id==='human_beacon').choice==='incident_seal'")
                    assert not errors, errors
                    (output/'report.json').write_text(json.dumps(dict(checks=checks,pure_navigation=True,touch_execution=True,reload=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('Eleven worlds, four themes, 1980 dossier checks including short landscape, real touch and reload passed')


if __name__ == '__main__':
    main()
