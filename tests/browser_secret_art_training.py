"""Actual learning/casting, stale submits, theme/layouts and paging."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from fixtures.secret_arts_release import prepare_secret_arts, pending_secret_art_event, inspect_secret_arts
from scripts.browser_navigation import navigation_locator, click_control


def main():
    output = ROOT / 'build/secret-arts-browser'
    output.mkdir(exist_ok=True)
    layouts = [(1440, 960), (393, 852), (852, 393)]
    with tempfile.TemporaryDirectory(prefix='secret-arts-ui-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(args=['--disable-gpu', '--renderer-process-limit=1', '--js-flags=--max-old-space-size=192'])
                    try:
                        for theme in ('a', 'b', 'd', 'f'):
                            for width, height in layouts:
                                identity = engine.create_game('秘术验收', 'supreme_metal', 'dao', 2150)['id']
                                prepare_secret_arts(engine, identity)
                                page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                                errors = []
                                page.on('pageerror', lambda e: errors.append(str(e)))
                                page.goto(f'http://127.0.0.1:{http.server_port}')
                                page.wait_for_function('!!configData')
                                page.evaluate('async id=>loadGame(id)', identity)
                                page.evaluate('t=>document.documentElement.dataset.theme=t', theme)
                                navigation_locator(page, '[data-panel-target=secret-art]').click()
                                page.wait_for_function("document.querySelector('#secret-art-card').classList.contains('panel-open')")
                                # Reset the mobile catalog retained from the prior view, if any.
                                if page.locator('#secret-art-back').is_visible():
                                    click_control(page.locator('#secret-art-back'))
                                page.locator('#secret-art-search').fill('')
                                click_control(page.locator('#secret-tab-known'))
                                assert page.locator('#secret-art-library .secret-art-entry').count() == 4
                                page.screenshot(path=str(output / f'catalog-{theme}-{width}.png'))
                                click_control(page.locator('#secret-tab-potential'))
                                page.locator('#secret-art-filter').select_option('root')
                                assert page.locator('#secret-art-library .secret-art-entry').count() == 6
                                click_control(page.locator('#secret-art-library .secret-art-entry').first)
                                assert page.locator('#secret-root-detail .secret-art-command').count() == 0
                                if page.locator('#secret-art-back').is_visible():
                                    click_control(page.locator('#secret-art-back'))
                                click_control(page.locator('#secret-page-next'))
                                assert page.locator('#secret-art-library .secret-art-entry').count() == 1
                                click_control(page.locator('#secret-tab-known'))
                                page.locator('#secret-art-search').fill('玄水')
                                click_control(page.locator('[data-secret-art=root_water]'))
                                assert '不限' in page.locator('.secret-art-facts').inner_text()
                                with page.expect_response(lambda r: r.url.endswith('/secret-art')) as learned:
                                    click_control(page.get_by_role('button', name='开始修习', exact=True))
                                assert learned.value.status == 200
                                page.wait_for_function("!busy && game.secret_arts.library.find(a=>a.id==='root_water').learned")
                                page.locator('#secret-art-material').select_option('item:secret_core_water_4')
                                click_control(page.get_by_role('button', name='施术补灵', exact=True))
                                page.wait_for_function("!busy && game.player.additional_roots.includes('water')")
                                inspect_secret_arts(engine, identity)
                                page.screenshot(path=str(output / f'completed-{theme}-{width}.png'))
                                # An actually stale enabled command must reject once and refresh the page.
                                if page.locator('#secret-art-back').is_visible():
                                    click_control(page.locator('#secret-art-back'))
                                page.locator('#secret-art-search').fill('离火')
                                click_control(page.locator('[data-secret-art=root_fire]'))
                                pending_secret_art_event(engine, identity)
                                with page.expect_response(lambda r: r.url.endswith('/secret-art')) as rejected:
                                    click_control(page.get_by_role('button', name='开始修习', exact=True))
                                assert rejected.value.status == 400
                                page.wait_for_function('!busy && !!game.pending_event')
                                assert page.get_by_role('button', name='开始修习', exact=True).is_disabled()
                                assert engine.store.load(identity).player.secret_art_state['arts'].keys() == {'root_water'}
                                # Resolve the offered registered event through its actual page button.
                                if page.locator('#secret-art-toggle').is_visible():
                                    click_control(page.locator('#secret-art-toggle'))
                                choice = page.locator('#event-choices button').first
                                click_control(choice)
                                page.wait_for_function('!busy && !game.pending_event')
                                navigation_locator(page, '[data-panel-target=secret-art]').click()
                                assert page.get_by_role('button', name='开始修习', exact=True).is_enabled()
                                assert page.locator('#secret-art-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                page.evaluate("TutorialGuide.showChapter('secret-arts')")
                                chapter = page.locator('#tutorial-handbook [data-chapter=secret-arts][open]')
                                assert '秘术修习没有修为境界要求' in chapter.inner_text()
                                page.evaluate("TutorialGuide.showChapter('elemental-remains')")
                                assert '1至12级' in page.locator('#tutorial-handbook [data-chapter=elemental-remains][open]').inner_text()
                                assert not errors, errors
                                page.close()
                    finally:
                        browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (output / 'result.json').write_text(json.dumps(dict(passed=True, themes=4, layouts=3,
        checks=['real-study', 'real-cast', 'no-level-gate', 'one-time-material', 'stale-reject-refresh',
                'event-click', 'busy-cleared', 'disabled-while-event', 'six-entry-pagination', 'no-horizontal-overflow']), indent=2), encoding='utf-8')
    print('Secret arts browser passed: four themes, desktop/mobile, real study/cast and stale-event recovery')


if __name__ == '__main__':
    main()
