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
        add_item(game.player, 'immortal_trace', 1000)
        game.player.opportunity = 10**8
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
                page.evaluate("UtilityPanels.open('daomen')")
                assert page.locator('.left-dock [data-panel-target="doctrine"]').count() == 1
                assert page.locator('.left-dock [data-panel-target="immortal-veins"]').count() == 1
                assert page.locator('.left-dock [data-panel-target="voisinage"]').count() == 1
                assert page.locator('#strategy-dock [data-panel-target="daomen"]').count() == 1
                assert '无尽' in page.locator('#opportunity-text').inner_text()
                assert page.locator('#hud-opportunity .hud-percent').inner_text() == '无尽'
                assert page.locator('.doctrine-book').count() == 5
                page.locator('.doctrine-book button').first.click()
                page.wait_for_function('game.doctrines.rows.some(r => r.learned)')
                assert page.locator('#doctrine-content .doctrine-chapter').count() == 1
                page.get_by_role('button', name='访求同道', exact=False).click()
                page.wait_for_function('game.doctrines.rows.some(r => r.peers.length === 1)')
                saved = engine.store.load(game.id)
                saved.pending_event = None
                saved.heavenly_court['open_election'] = None
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                page.get_by_role('button', name='求取 Lv1 注解', exact=False).click()
                page.wait_for_function('game.doctrines.rows.some(r => r.has_annotation)')
                page.screenshot(path=str(ROOT / 'build/daomen-desktop.png'))
                saved = engine.store.load(game.id)
                key = next(iter(saved.doctrine_state['player']['progress']))
                saved.doctrine_state['player']['progress'][key]['failures'] = {'1':3}
                saved.pending_event = None
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                page.evaluate("UtilityPanels.close('daomen'); UtilityPanels.open('doctrine')")
                page.get_by_role('button', name='参悟此道统', exact=True).click()
                page.wait_for_function('game.doctrines.rows.some(r => r.level === 1)')
                assert page.locator('#doctrine-content .doctrine-chapter').count() == 2
                saved = engine.store.load(game.id)
                key = next(iter(saved.doctrine_state['player']['progress']))
                saved.doctrine_state['player']['progress'][key] = {'level': 4, 'experience': 650, 'failures':{'5':20}}
                saved.doctrine_state['player']['annotations'][key] = [1,2,3,4,5]
                next(t for t in saved.player.known_techniques if t.doctrine_id == key).level = 5
                saved.doctrine_state['player']['active'] = key
                saved.pending_event = None
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                page.evaluate("UtilityPanels.open('doctrine')")
                assert page.locator('#doctrine-content .doctrine-chapter').count() == 5
                page.get_by_role('button', name='确立本源并尝试 Lv5', exact=True).click()
                page.locator('#game-confirm-accept').click()
                page.wait_for_function('game.doctrines.rows.some(r => r.level === 5 && r.origin)')
                assert page.locator('#doctrine-content .doctrine-chapter').count() == 6
                page.locator('#doctrine-card').evaluate('(e) => { e.scrollTop = 0; }')
                page.screenshot(path=str(ROOT / 'build/doctrine-desktop.png'))
                page.set_viewport_size({'width': 412, 'height': 915})
                page.locator('#doctrine-card').evaluate('(e) => { e.scrollTop = 0; }')
                page.screenshot(path=str(ROOT / 'build/doctrine-mobile.png'))
                assert page.locator('#doctrine-card').evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')
                page.evaluate("UtilityPanels.close('doctrine'); UtilityPanels.open('immortal-veins')")
                for n in range(1, 4):
                    page.get_by_role('button', name='开启下一条仙脉', exact=True).click()
                    page.wait_for_function('(n) => game.doctrines.veins.opened === n', arg=n)
                assert page.evaluate('game.player.layer') == 2
                page.screenshot(path=str(ROOT / 'build/immortal-veins-mobile.png'))
                page.evaluate("UtilityPanels.close('immortal-veins'); UtilityPanels.open('voisinage')")
                page.get_by_role('button', name='温养稳固', exact=False).click()
                page.wait_for_function('game.doctrines.voisinages[0].axes[0].rank === 1')
                page.screenshot(path=str(ROOT / 'build/voisinage-mobile.png'))
                assert page.locator('#voisinage-card').evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')
                saved = engine.store.load(game.id)
                saved.player.hp, saved.player.mp = max_hp(saved.player), max_mp(saved.player)
                engine._combat(saved, {'target_name': '试域石像', 'target_power': 100, 'target_realm_index': 8}, False, random.Random(1))
                assert any(r.get('voisinage', {}).get('fields') for r in saved.last_combat_report['rounds'])
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                page.evaluate("UtilityPanels.close('voisinage')")
                if page.locator('#battle-report-card').is_hidden():
                    page.locator('#battle-report-open').click()
                page.locator('.battle-round-details summary').click()
                assert page.locator('.voisinage-field').first.is_visible()
                page.locator('.voisinage-field').first.scroll_into_view_if_needed()
                page.screenshot(path=str(ROOT / 'build/doctrine-battle-mobile.png'))
                # Ordinary lower-world rounds have no voisinage panel. Explicit
                # fields still render independently of current world/tier.
                assert page.evaluate("DoctrinePanel.battleRound({events:[]}) === null")
                saved.player.world = 'human'
                saved.player.realm_index = 8
                saved.player.location_id = engine.maps.default_location('human')
                engine.store.save(saved)
                page.evaluate('(id) => loadGame(id)', game.id)
                assert page.locator('[data-panel-target="doctrine"]').is_hidden()
                assert page.locator('.voisinage-field').count() > 0
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Doctrines: purchase, actual elapsed training, origin confirmation, redaction, mobile and battle UI passed')


if __name__ == '__main__':
    main()
