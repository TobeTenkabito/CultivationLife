"""Actual creation, organization commands and steward clicks across all themes."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT / 'build/release-240-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *_args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme in 'abdf':
                        for width, height in [(1440, 1000), (393, 852)]:
                            page = browser.new_page(viewport=dict(width=width, height=height))
                            errors = []
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_selector('#custom-start')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            assert page.locator('.quick-start-group').count() == 4
                            page.locator('#custom-start > summary').click()
                            page.locator('#custom-realm').select_option('3')
                            page.locator('#custom-sense').fill('23')
                            page.locator('#custom-sect').select_option('new')
                            page.locator('#custom-sect-name').fill('青玉宗')
                            page.locator('#custom-family').select_option('new')
                            page.locator('#custom-family-name').fill('林氏仙族')
                            page.locator('#custom-item-search').fill('spirit_stone')
                            page.locator('#custom-item').select_option('spirit_stone')
                            page.locator('#custom-quantity').fill('1000000')
                            page.locator('#custom-add-item').click()
                            page.locator('#custom-item-search').fill('spirit_sword')
                            page.locator('#custom-item').select_option('spirit_sword')
                            page.locator('#custom-quantity').fill('1')
                            page.locator('#custom-add-item').click()
                            page.locator('#custom-natal').select_option('spirit_sword')
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                            page.locator('#custom-start').screenshot(path=str(output / f'{theme}-{width}-start.png'))
                            page.locator('#custom-start-submit').click()
                            page.wait_for_function('game && !busy && game.faction.name === "青玉宗"')
                            assert '筑基中期' in page.locator('#divine-sense').text_content()
                            assert page.evaluate('game.faction.join_age === game.player.age')
                            navigation_locator(page,'[data-panel-target=faction]').click()
                            box = page.locator('[data-organization=sect]')
                            box.locator(':scope > summary').click()
                            box.get_by_label('府库注资金额').fill('100000')
                            box.locator('[data-org-business=organization_fund]').click()
                            page.wait_for_function('!busy && game.faction.finance.balance===100000')
                            box.evaluate('e=>e.open=true')
                            box.locator('[data-org-business=create]').click()
                            page.wait_for_function('!busy && game.fleet_network.fleets.some(f=>f.player_controlled&&f.owner_kind==="sect")')
                            box.evaluate('e=>e.open=true')
                            estate = box.locator('#enterprise-panel-sect')
                            estate.locator(':scope > summary').click()
                            estate.get_by_label('购置产业').select_option('farm')
                            estate.locator('[data-estate-action=buy]').click()
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned.some(r=>r.owner_kind==="sect")')
                            box.evaluate('e=>e.open=true')
                            estate.evaluate('e=>e.open=true')
                            card = estate.locator('[data-estate-id]').first
                            card.locator(':scope > summary').click()
                            card.locator('[data-estate-action=entrust]').click()
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned[0].entrusted')
                            box.evaluate('e=>e.open=true'); estate.evaluate('e=>e.open=true'); card.evaluate('e=>e.open=true')
                            assert card.get_by_role('button', name='收回掌柜委托').is_visible()
                            assert page.locator('#faction-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                            box.locator(':scope > summary').scroll_into_view_if_needed()
                            page.screenshot(path=str(output / f'{theme}-{width}-business.png'))
                            gid = page.evaluate('game.id')
                            page.evaluate('async id=>loadGame(id)', gid)
                            assert page.evaluate('game.map.economy.enterprises.owned[0].entrusted')
                            assert not errors, errors
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown()
    print('Release 240 UI passed: four themes, two widths, real custom creation, treasury, caravan, property and entrust reload')


if __name__ == '__main__':
    main()
