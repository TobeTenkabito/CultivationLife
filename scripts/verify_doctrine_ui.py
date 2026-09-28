"""Isolated browser smoke: acquire, train, bind origin and inspect real battle UI."""
import random
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
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, max_hp, max_mp


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        engine = server.ENGINE = GameEngine(ROOT, Path(directory) / 'saves')
        shown = engine.create_game('问道', 'supreme_metal', 'dao', seed=7429, preset_id='true_immortal')
        game = engine.store.load(shown['id'])
        game.pending_event = None
        game.player.next_tribulation_age = None
        game.heavenly_court['open_election'] = None
        add_item(game.player, 'spirit_stone', 10**8)
        engine.store.save(game)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as p, patch.dict(WORLD_SYSTEMS['time_units'], {'9': 100}), \
                    patch.object(engine, '_advance_guixu_calendar', return_value=False):
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1080})
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData !== null')
                page.evaluate('(id) => loadGame(id)', game.id)
                page.evaluate("UtilityPanels.open('doctrine')")
                assert page.locator('.doctrine-book').count() == 5
                page.locator('.doctrine-book button').first.click()
                page.wait_for_function('game.doctrines.rows.some(r => r.learned)')
                assert page.locator('.doctrine-chapter').count() == 1
                page.get_by_role('button', name='参悟此道统', exact=True).click()
                page.wait_for_function('game.doctrines.rows.some(r => r.level === 1)')
                assert page.locator('.doctrine-chapter').count() == 2
                saved = engine.store.load(game.id)
                key = next(iter(saved.doctrine_state['player']['progress']))
                saved.doctrine_state['player']['progress'][key] = {'level': 4, 'experience': 650}
                saved.doctrine_state['player']['active'] = key
                saved.pending_event = None
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                page.evaluate("UtilityPanels.open('doctrine')")
                assert page.locator('.doctrine-chapter').count() == 5
                page.get_by_role('button', name='确立本源并突破 Lv5', exact=True).click()
                page.locator('#game-confirm-accept').click()
                page.wait_for_function('game.doctrines.rows.some(r => r.level === 5 && r.origin)')
                assert page.locator('.doctrine-chapter').count() == 6
                page.screenshot(path=str(ROOT / 'build/doctrine-desktop.png'))
                page.set_viewport_size({'width': 412, 'height': 915})
                page.locator('#doctrine-card').evaluate('(e) => { e.scrollTop = 0; }')
                page.screenshot(path=str(ROOT / 'build/doctrine-mobile.png'))
                assert page.locator('#doctrine-card').evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')
                saved = engine.store.load(game.id)
                saved.player.hp, saved.player.mp = max_hp(saved.player), max_mp(saved.player)
                engine._combat(saved, {'target_name': '试域石像', 'target_power': 100, 'target_realm_index': 8}, False, random.Random(1))
                assert any(r.get('domain', {}).get('fields') for r in saved.last_combat_report['rounds'])
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                page.evaluate("UtilityPanels.close('doctrine')")
                if page.locator('#battle-report-card').is_hidden():
                    page.locator('#battle-report-open').click()
                page.locator('.battle-round-details summary').click()
                assert page.locator('.domain-field').first.is_visible()
                page.locator('.domain-field').first.scroll_into_view_if_needed()
                page.screenshot(path=str(ROOT / 'build/doctrine-battle-mobile.png'))
                # Ordinary lower-world rounds have no domain panel. Explicit
                # fields still render independently of current world/tier.
                assert page.evaluate("DoctrinePanel.battleRound({events:[]}) === null")
                saved.player.world = 'human'
                saved.player.realm_index = 8
                saved.player.location_id = engine.maps.default_location('human')
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                assert page.locator('[data-panel-target="doctrine"]').is_hidden()
                assert page.locator('.domain-field').count() > 0
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Doctrines: purchase, actual elapsed training, origin confirmation, redaction, mobile and battle UI passed')


if __name__ == '__main__':
    main()
