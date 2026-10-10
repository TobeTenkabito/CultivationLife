"""Real page clicks: relocate, build, dispatch, closed-route recall and reload."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy import fleet_network as net, cross_freight
from cultivation_life.system.economy.network_actions import home_alliance
from cultivation_life.system.economy.ledger import transfer_value, balance
from cultivation_life.system.economy.state import ensure_regional_market
from test_economy_network import found
from test_economy_network_expansion import visit, recruit


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT / 'build/economy-expansion-step1-browser'
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme in 'abdf':
                        for width, height in [(1440, 1000), (393, 852)]:
                            game = engine._load(engine.create_game('迁盟商路', 'supreme_metal', 'dao', 419, preset_id='core')['id'])
                            game.pending_event = None
                            game.player.realm_index = 2
                            game.player.next_tribulation_age = None
                            transfer_value(game, 'background:human', 'player', 10**9, '验收资金')
                            game = found(engine, game)
                            visit(engine, game, 'spirit')
                            game.player.realm_index = 8
                            game = recruit(engine, game)
                            engine.store.save(game)
                            page = browser.new_page(viewport=dict(width=width, height=height))
                            errors = []
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            def load():
                                page.evaluate('async id => loadGame(id)', game.id)
                                page.wait_for_function('!busy && !!game.fleet_network')
                                if 'panel-open' not in page.locator('#merchant-card').get_attribute('class'):
                                    navigation_locator(page,'[data-panel-target=merchant]').click()
                                expect(page.locator('#merchant-card')).to_have_css('opacity', '1')
                            def expand(index):
                                section = page.locator('#fleet-network-content > details').nth(index)
                                if section.get_attribute('open') is None:
                                    section.locator('summary').click()
                                return section
                            load()
                            expand(1)
                            page.locator('[data-fleet-action=relocate]').click()
                            page.wait_for_function('!busy && game.fleet_network.main_hq')
                            expand(2)
                            page.locator('[data-fleet-action=build_passage]').click()
                            page.wait_for_function('!busy && game.fleet_network.destinations.some(d => d.open)')
                            expand(2)
                            assert page.locator('[data-fleet-action=build_passage]').is_disabled()
                            saved = engine._load(game.id)
                            home = home_alliance(saved)
                            fleet = net.active_fleets(saved, 'spirit', 'alliance', home['id'])[0]
                            # Move fixture fleet to its actual departure map; dispatch itself is a page click.
                            fleet['location'] = home['hq']
                            transfer_value(saved, 'background:spirit', f'caravan:{fleet["id"]}', 10**7, '验收商队资本')
                            fleet['investment'] += 10**7
                            ensure_regional_market(saved, engine.maps, 'spirit', home['hq'])
                            for row in saved.economy_v2['markets'][f'spirit:{home["hq"]}']['commodities'].values():
                                row['stock'] = row['target'] * 3
                            engine.store.save(saved)
                            load()
                            expand(3)
                            page.get_by_label('跨界出发商队').select_option(fleet['id'])
                            page.get_by_label('总部索款比例').select_option('50')
                            page.locator('[data-fleet-action=cross_dispatch]').click()
                            page.wait_for_function('!busy && game.fleet_network.fleets.some(f => !!f.cross_trip)')
                            expand(3)
                            assert page.get_by_label('跨界出发商队').locator('option').evaluate_all('(options, id) => options.every(o => o.value !== id)', fleet['id'])
                            saved = engine._load(game.id)
                            fleet = saved.economy_v2['transport']['worlds']['spirit']['fleets'][fleet['id']]
                            assert fleet['cross_trip']['remittance_percent'] == 50
                            route = net.routes(saved)[net.route_key(home.get('network_id', home['id']), 'human', 'spirit')]
                            route['open'] = False
                            saved.player.age = fleet['cross_trip']['arrival']
                            cross_freight.advance_freight(saved, engine.maps, fleet, {})
                            engine.store.save(saved)
                            load()
                            expand(0)
                            page.locator('[data-fleet-action=cross_recall]').click()
                            page.wait_for_function('!busy && game.fleet_network.fleets.some(f => f.cross_trip?.phase === "return")')
                            expand(0)
                            assert page.locator('[data-fleet-action=cross_recall]').is_disabled()
                            expand(2)
                            page.locator('[data-fleet-action=build_passage]').click()
                            page.wait_for_function('!busy && game.fleet_network.destinations.some(d => d.open)')
                            expand(3)
                            page.screenshot(path=str(output / f'{theme}-{width}.png'))
                            expected = balance(engine._load(game.id), 'player')
                            data = engine.store._path(game.id).read_bytes()
                            load()
                            assert engine.store._path(game.id).read_bytes() == data
                            assert page.evaluate('game.personal_economy.balance') == expected
                            assert not errors, errors
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                            reports.append(dict(theme=theme, width=width, passed=True))
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown()
    (output / 'report.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print('Economy expansion step 1: 8 layouts, real relocation/build/dispatch/recall/repair and read-only reload passed')


if __name__ == '__main__':
    main()
