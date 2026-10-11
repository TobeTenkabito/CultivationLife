"""Actual desktop controls, responsive relocation and Android wide-screen routing."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator


def main():
    output = ROOT / 'build/desktop-navigation'
    output.mkdir(exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
        engine = GameEngine(ROOT, Path(directory) / 'saves')
        made = engine.create_game('桌面导航验收', 'heavenly', 'dao', 272, preset_id='core')
        identity = made['id']

        class Quiet(server.Handler):
            def log_message(self, *args):
                pass

        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme in 'abdf':
                        page = browser.new_page(viewport=dict(width=1440, height=960))
                        errors = []
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData && !busy')
                        page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                        page.evaluate('async id=>loadGame(id)', identity)
                        before = engine.store._path(identity).read_bytes()
                        page.evaluate('window.originalMapButton=document.querySelector("[data-panel-target=map]")')
                        for width, height in [(1440, 960), (1024, 768), (1440, 480)]:
                            page.set_viewport_size(dict(width=width, height=height))
                            page.wait_for_function('!GameNavigation.isCompact()')
                            assert not page.locator('#navigation-bar').is_visible()
                            assert page.locator('.left-dock').is_visible()
                            assert page.locator('#strategy-dock').is_visible()
                            # Tutorial reveal must scroll the rail without opening a category.
                            page.evaluate('GameNavigation.reveal("map")')
                            assert not page.locator('#navigation-menu').evaluate('d=>d.open')
                            page.locator('#strategy-dock [data-panel-target=map]').click()
                            page.wait_for_selector('#map-card.panel-open')
                            assert page.locator('#map-current').text_content() == '当前：' + made['map']['current_name']
                            page.keyboard.press('Escape')
                            page.wait_for_selector('#map-card', state='hidden')
                            page.locator('.left-dock [data-panel-target=inventory]').click()
                            page.wait_for_selector('#inventory-card.panel-open')
                            page.keyboard.press('Escape')
                            page.locator('.settings-dock [data-panel-target=settings]').click()
                            page.wait_for_selector('#settings-card.panel-open')
                            page.keyboard.press('Escape')
                            page.wait_for_selector('#settings-card', state='hidden')
                            page.screenshot(path=str(output / f'{theme}-{width}-{height}.png'))
                            rows.append(dict(theme=theme, viewport=[width, height], mode='desktop', status='passed'))
                        # Several changes must preserve the authoritative node and its single click handler.
                        for _ in range(2):
                            page.set_viewport_size(dict(width=412, height=915))
                            page.wait_for_function('GameNavigation.isCompact()')
                            assert not page.locator('.left-dock').is_visible()
                            navigation_locator(page, '[data-panel-target=map]').click()
                            page.wait_for_selector('#map-card.panel-open')
                            page.locator('[data-navigation-category=worlds]').click()
                            page.set_viewport_size(dict(width=1440, height=960))
                            page.wait_for_function('!GameNavigation.isCompact()')
                            assert not page.locator('#navigation-menu').evaluate('d=>d.open')
                            assert page.locator('#map-card').is_visible()
                            page.locator('#strategy-dock [data-panel-target=map]').click()
                            page.wait_for_selector('#map-card', state='hidden')
                            assert page.evaluate('originalMapButton===document.querySelector("[data-panel-target=map]")')
                            assert page.locator('[data-panel-target=map]').count() == 1
                        page.evaluate('GameNavigation.saved')
                        assert engine.store._path(identity).read_bytes() == before
                        if theme == 'a':
                            # Hold an actual clicked action request while resizing the window.
                            held = []
                            page.route('**/advance', lambda route: held.append(route))
                            page.locator('[data-action=rest]').click()
                            page.wait_for_function('busy')
                            assert held
                            assert page.locator('#strategy-dock [data-panel-target=map]').is_disabled()
                            page.set_viewport_size(dict(width=412, height=915))
                            page.wait_for_function('GameNavigation.isCompact()')
                            page.locator('[data-navigation-category=worlds]').click()
                            assert page.locator('[data-panel-target=map]').is_disabled()
                            assert not page.locator('#map-card').is_visible()
                            page.set_viewport_size(dict(width=1440, height=960))
                            page.wait_for_function('!GameNavigation.isCompact()')
                            assert page.locator('#strategy-dock [data-panel-target=map]').is_disabled()
                            held.pop().continue_()
                            page.wait_for_function('!busy')
                            assert page.locator('#strategy-dock [data-panel-target=map]').is_enabled()
                            page.unroute('**/advance')
                            rows.append(dict(case='clicked-action-lock-during-resize', status='passed'))
                        assert not errors, errors
                        page.close()
                    # Mobile platform detection must survive a tablet-sized viewport.
                    for host in ('android-bridge', 'android-ua', 'touch-landscape'):
                        options = dict(viewport=dict(width=1440, height=960), has_touch=True)
                        if host == 'android-ua':
                            options['user_agent'] = 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36'
                        if host == 'touch-landscape':
                            options['viewport'] = dict(width=915, height=412)
                        page = browser.new_page(**options)
                        if host == 'android-bridge':
                            page.add_init_script('window.AndroidGame={};')
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData && !busy')
                        page.evaluate('async id=>loadGame(id)', identity)
                        assert page.evaluate('GameNavigation.isCompact()')
                        assert page.locator('#navigation-bar').is_visible()
                        assert not page.locator('#strategy-dock').is_visible()
                        navigation_locator(page, '[data-panel-target=inventory]').click()
                        page.wait_for_selector('#inventory-card.panel-open')
                        page.wait_for_function('()=>{const r=document.querySelector("#inventory-card").getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1}')
                        page.screenshot(path=str(output / f'{host}.png'))
                        page.close()
                        rows.append(dict(host=host, mode='compact', status='passed'))
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (output / 'report.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Desktop navigation passed: four themes, three desktop sizes, repeated responsive relocation, node identity, direct map/inventory/settings clicks, Escape, unchanged saves and three Android/touch layouts')


if __name__ == '__main__':
    main()
