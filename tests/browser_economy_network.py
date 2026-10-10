"""Actual HTTP and clicks in four themes: account, guards, founding and reload."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy.ledger import transfer_value, balance


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT / 'build/economy-v2-r4-browser'
    output.mkdir(exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme in 'abdf':
                        for width, height in [(1440, 1000), (393, 852)]:
                            game = engine._load(engine.create_game('个人商路', 'supreme_metal', 'dao', 419, preset_id='core')['id'])
                            game.pending_event = None
                            game.player.realm_index = 2
                            transfer_value(game, 'background:human', 'player', 10**7, '验收资本')
                            engine.store.save(game)
                            page = browser.new_page(viewport=dict(width=width, height=height))
                            errors = []
                            page.on('pageerror', lambda err: errors.append(str(err)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id => loadGame(id)', game.id)
                            page.wait_for_function('!busy && document.querySelector("#personal-economy-content h3")')
                            navigation_locator(page,'[data-panel-target=personal-economy]').click()
                            expect(page.locator('#personal-economy-card')).to_have_css('opacity', '1')
                            expect(page.locator('#personal-economy-content')).to_contain_text('现有灵石')
                            before = engine.store._path(game.id).read_bytes()
                            page.screenshot(path=str(output / f'{theme}-{width}-personal.png'))
                            page.locator('#personal-economy-toggle').click()
                            navigation_locator(page,'[data-panel-target=merchant]').click()
                            management = page.locator('#fleet-network-content > details').nth(0)
                            management.locator('summary').click()
                            management.get_by_role('button', name='自建独立商队', exact=True).click()
                            page.wait_for_function('!busy && game.fleet_network.fleets.some(f => f.player_controlled)')
                            management.locator('summary').click()
                            own = page.locator('#fleet-network-content [data-fleet-id]').filter(has=page.locator('[data-fleet-action=guard]')).first
                            own.locator('[data-fleet-action=guard]').click()
                            page.wait_for_function('!busy && game.fleet_network.fleets.some(f => f.player_controlled && f.guard_power > 0)')
                            management.locator('summary').click()
                            assert own.locator('[data-fleet-action=guard]').is_disabled()
                            assert management.get_by_role('button', name='自建独立商队', exact=True).is_disabled()
                            latest = engine._load(game.id)
                            ids = [f['id'] for f in latest.economy_v2['transport']['worlds']['human']['fleets'].values() if f['owner_kind'] == 'independent' and not f['player_controlled']][:2]
                            for identity in ids:
                                latest = engine._load(game.id)
                                latest.player.location_id = latest.economy_v2['transport']['worlds']['human']['fleets'][identity]['location']
                                engine.store.save(latest)
                                page.evaluate('async id => loadGame(id)', game.id)
                                if 'panel-open' not in page.locator('#merchant-card').get_attribute('class'):
                                    navigation_locator(page,'[data-panel-target=merchant]').click()
                                management.locator('summary').click()
                                page.locator(f'[data-fleet-id="{identity}"] [data-fleet-action=pledge]').click()
                                page.wait_for_function('!busy && game.fleet_network.fleets.some(f => f.id === "' + identity + '" && f.pledged)')
                            page.locator('#fleet-network-content > details').nth(1).locator('summary').click()
                            page.locator('[data-fleet-action=found]').click()
                            page.wait_for_function('!busy && !!game.fleet_network.owned')
                            management.locator('summary').click()
                            assert page.locator('[data-fleet-action=create]').filter(has_text='向商盟申请').is_disabled()
                            management.scroll_into_view_if_needed()
                            page.screenshot(path=str(output / f'{theme}-{width}-network.png'))
                            expected = balance(engine._load(game.id), 'player')
                            saved = engine.store._path(game.id).read_bytes()
                            page.evaluate('async id => loadGame(id)', game.id)
                            assert engine.store._path(game.id).read_bytes() == saved
                            assert page.evaluate('game.personal_economy.balance') == expected
                            assert not errors, errors
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                            assert saved != before
                            results.append(dict(theme=theme, width=width, passed=True))
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown()
    (output / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Economy network browser passed: 8 layouts, real founding, guards, account and reload')


if __name__ == '__main__':
    main()
