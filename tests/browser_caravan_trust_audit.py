"""Real fleet creation, trust switch, annual action, map and reload in both palettes."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy.ledger import transfer_value
from scripts.browser_navigation import navigation_locator, click_control, set_theme


def main():
    output = ROOT / 'build/caravan-trust-audit-browser'
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    with tempfile.TemporaryDirectory(prefix='caravan-trust-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme, width, height in [('light',1440,1000), ('dark',1440,1000), ('light',390,844), ('dark',390,844)]:
                        game = engine._load(engine.create_game('托管商队验收','supreme_metal','dao',419,preset_id='core')['id'])
                        game.pending_event = None
                        game.player.next_tribulation_age = None
                        game.settings.update(silent_events=True, combat_popup=False)
                        transfer_value(game, 'background:human', 'player', 100000, '隔离验收本金')
                        engine.store.save(game)
                        page = browser.new_page(viewport=dict(width=width,height=height), reduced_motion='reduce')
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData&&!busy')
                        set_theme(page, theme)
                        page.evaluate('id=>loadGame(id)', game.id)
                        navigation_locator(page, '[data-panel-target=merchant]').click()
                        create = page.get_by_role('button', name='自建独立商队', exact=True, include_hidden=True)
                        click_control(create)
                        page.wait_for_function('!busy && game.fleet_network.fleets.some(f=>f.player_controlled)')
                        key = page.evaluate('game.fleet_network.fleets.find(f=>f.player_controlled).id')
                        click_control(page.locator('#merchant-toggle'))
                        navigation_locator(page, '[data-panel-target=settings]').click()
                        click_control(page.locator('#setting-economy-trust'))
                        page.wait_for_function('!busy && game.settings.economy_trust')
                        click_control(page.locator('#settings-toggle'))
                        click_control(page.locator('[data-action=rest]'))
                        page.wait_for_function('!busy')
                        saved = engine._load(game.id)
                        f = saved.economy_v2['transport']['worlds']['human']['fleets'][key]
                        assert f['status'] == 'waiting' and f['guard_power'] == 0 and not f['cargo']
                        assert saved.economy_v2['accounts']['caravan:'+key]['balance'] == 4998
                        navigation_locator(page, '[data-panel-target=merchant]').click()
                        row = page.locator(f'#fleet-network-content [data-fleet-id="{key}"]')
                        click_control(page.locator('#fleet-network-content > details').first.locator(':scope > summary'))
                        assert '留驻等候' in row.inner_text()
                        assert page.locator('#merchant-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(output / f'{theme}-{width}-management.png'), animations='disabled')
                        click_control(page.locator('#merchant-toggle'))
                        if not page.locator('[data-home-map-mode=caravans]').is_visible():
                            click_control(page.locator('#pixel-scenery-toggle'))
                        click_control(page.locator('[data-home-map-mode=caravans]'))
                        assert '商队经营' in page.locator('.home-map-detail').inner_text()
                        frozen = engine.store._path(game.id).read_bytes()
                        page.reload()
                        page.wait_for_function('!!configData&&!busy')
                        page.evaluate('id=>loadGame(id)', game.id)
                        assert engine.store._path(game.id).read_bytes() == frozen
                        assert not errors, errors
                        reports.append(dict(theme=theme,width=width,status='passed'))
                        page.close()
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (output / 'report.json').write_text(json.dumps(reports, indent=2), encoding='utf8')
    print('Caravan trust: four layouts passed; actual create, setting, annual action, map and reload')


if __name__ == '__main__': main()
