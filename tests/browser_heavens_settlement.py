"""M3 final HTTP/touch acceptance, content density and all six visual themes."""
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
from cultivation_life.rules import max_hp, max_mp
from test_heavens_settlement import local, site, ready, military, delegates


def main():
    output = ROOT/'build/heavens-m3-final-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        bundle = military.__wrapped__(ready.__wrapped__(site.__wrapped__(local.__wrapped__(Path(folder)))))
        engine, initial, _ = bundle
        work = delegates(bundle)
        work.player.realm_index, work.player.layer = 4, 9
        work.player.hp, work.player.mp = max_hp(work.player), max_mp(work.player)
        work.settings['silent_events'] = True
        engine.store.save(work)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)), patch.object(engine, '_advance_guixu_calendar', return_value=False):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':393, 'height':852}, has_touch=True)
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}', initial.id)
                    page.locator('[data-panel-target=heavens]').tap()
                    page.get_by_role('tab', name='战局', exact=True).tap()
                    page.get_by_role('button', name='查看岚疆界门', exact=True).tap()
                    page.get_by_role('tab', name='地方', exact=True).tap()
                    before = engine.store._path(initial.id).read_bytes()
                    measurements = []
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393,320):
                            page.set_viewport_size({'width':width, 'height':1050 if width == 1440 else 852})
                            page.get_by_role('tab', name='战局', exact=True).click()
                            page.get_by_role('button', name='查看岚疆界门', exact=True).click()
                            for tab in ('军情', '界门', '交锋', '援助', '地方'):
                                page.get_by_role('tab', name=tab, exact=True).click()
                                variants = ('order', 'treaty', 'recovery') if tab == '地方' else (None,)
                                for detail in variants:
                                    if detail: page.get_by_label('地方档案', exact=True).select_option(detail)
                                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                                    assert page.locator('#heavens-body').evaluate('e=>e.scrollWidth <= e.clientWidth+1')
                                    buttons = page.locator('#heavens-detail-body [data-heavens-action]')
                                    assert buttons.count() <= 2, (theme, width, tab, detail, buttons.count())
                                    assert page.locator('#heavens-detail-body p, #heavens-detail-body article, #heavens-detail-body ol').count()
                                    for button in buttons.all():
                                        assert button.bounding_box()['height'] >= 44
                                    measurements.append(dict(theme=theme, width=width, page=detail or tab, actions=buttons.count()))
                                    if detail and width != 320:
                                        page.screenshot(path=str(output/f'{theme}-{width}-{detail}.png'))
                    assert engine.store._path(initial.id).read_bytes() == before
                    page.set_viewport_size({'width':393, 'height':852})
                    page.get_by_label('地方档案', exact=True).select_option('treaty')
                    page.get_by_role('button', name='提出当地停战', exact=True).tap()
                    page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                    page.locator('#game-confirm-cancel').tap()
                    assert engine.store._path(initial.id).read_bytes() == before
                    page.get_by_role('button', name='提出当地停战', exact=True).tap()
                    page.locator('#game-confirm-accept').tap()
                    page.wait_for_function('!busy && game.heavens.campaign.settlement.treaty')
                    saved = engine.store.load(initial.id)
                    assert saved.heavens_state['runtime']['campaign']['settlement']['treaty']['kind'] == 'truce'
                    page.screenshot(path=str(output/'signed-truce-393.png'))
                    page.get_by_label('地方档案', exact=True).select_option('recovery')
                    page.get_by_label('选择当前事务', exact=True).select_option('campaign_evacuate')
                    page.get_by_role('button', name='沿原道路撤往无棣原', exact=True).tap()
                    page.locator('#game-confirm-accept').tap()
                    page.wait_for_function("!busy && game.player.location_id==='wudi_plain'", timeout=120000)
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}', initial.id)
                    assert page.evaluate("game.heavens.campaign.settlement.treaty.kind==='truce'")
                    assert not errors, errors
                    (output/'report.json').write_text(json.dumps(dict(measurements=measurements, max_actions=2,
                        min_touch_height=44, pure_navigation=True, preview_cancel=True, real_truce=True,
                        real_road_evacuation=True, reload=True, errors=errors), indent=2), encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    print('M3 final: four themes, independent content pages, touch truce and evacuation passed')


if __name__ == '__main__':
    main()
