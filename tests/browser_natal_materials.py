"""Real socket/return clicks, bounded picker, qualification and narrow layouts."""
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
from fixtures.natal_materials_release import prepare_natal_materials_release, inspect_natal_materials_release
from scripts.browser_navigation import navigation_locator, click_control


def main():
    output = ROOT / 'build/natal-materials-browser'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='natal-materials-ui-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(args=['--disable-gpu', '--renderer-process-limit=1', '--js-flags=--max-old-space-size=128'])
                    try:
                        for width, height, theme in [(1280, 1000, 'a'), (430, 920, 'f')]:
                            made = engine.create_game('镶材页面', 'supreme_metal', 'dao', 2142, preset_id='core')
                            ids = prepare_natal_materials_release(engine, made['id'])
                            page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                            errors=[]
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_function('!!configData')
                            page.evaluate('async id=>loadGame(id)', made['id'])
                            page.evaluate('theme=>document.documentElement.dataset.theme=theme', theme)
                            navigation_locator(page, '[data-panel-target=natal-artifact]').click()
                            click_control(page.locator('.natal-slot.slot-0'))
                            picker = page.locator('.natal-material-picker')
                            assert picker.locator('.natal-material-choice').count() == 3
                            click_control(picker.locator(f'[data-material-id="{ids[0]}"]'))
                            page.wait_for_function('id=>!busy && game.natal_artifact.slots[0].material_id===id', arg=ids[0])
                            click_control(page.locator('.natal-slot.slot-0'))
                            page.wait_for_function('!busy && !game.natal_artifact.slots[0].material_id')
                            click_control(page.locator('.natal-slot.slot-0'))
                            picker.get_by_label('镶材范围').select_option('all')
                            assert picker.locator('.natal-material-choice').count() == 24
                            assert picker.get_by_role('button', name='上一页', exact=True).is_disabled()
                            click_control(picker.get_by_role('button', name='下一页', exact=True))
                            assert picker.locator('.natal-material-pages span').inner_text().startswith('2 /')
                            picker.get_by_label('搜索镶材').fill('烛龙母金')
                            high = picker.locator('.natal-material-choice')
                            assert high.count() == 1 and high.is_disabled()
                            assert '幽冥界' in high.inner_text() and '大罗' in high.inner_text()
                            assert picker.locator('.natal-material-grid').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                            page.screenshot(path=str(output / f'catalog-{width}.png'))
                            picker.get_by_label('搜索镶材').fill('')
                            picker.get_by_label('镶材范围').select_option('local')
                            assert 0 < picker.locator('.natal-material-choice').count() <= 24
                            assert all('人界' in row.inner_text() for row in picker.locator('.natal-material-choice').all())
                            inspect_natal_materials_release(engine, made['id'])
                            assert not errors, errors
                            page.close()
                    finally:
                        browser.close()
            finally:
                http.shutdown(); http.server_close()
    (output / 'result.json').write_text(json.dumps(dict(passed=True, checks=['socket', 'unsocket', 'exact-return', 'owned-filter', 'world-filter', 'paging-limit', 'higher-tier-disabled', 'desktop-mobile']), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Natal materials browser: passed, desktop/mobile, exact returns and bounded catalog')


if __name__ == '__main__': main()
