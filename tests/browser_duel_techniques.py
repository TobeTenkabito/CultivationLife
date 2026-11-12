"""Real seven-book configuration, stale requests and existing pixel navigation."""
import random
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
from cultivation_life.engine import GameEngine
from cultivation_life.rules import learn_technique
from test_duel_techniques import books
from scripts.browser_navigation import reveal_subpage, set_theme


def reveal(page):
    if not page.locator('#player-details-dialog').evaluate('n=>n.open'):
        page.locator('.hud-identity').click()
    summary = page.locator('details.techniques > summary')
    reveal_subpage(page, summary)
    if not summary.evaluate('n=>n.parentElement.open'):
        summary.click()
    page.locator('#duel-technique-panel').wait_for(state='visible')


def main():
    output = ROOT / 'build/duel-ui'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        game = engine.store.load(engine.create_game('七部斗法验收', 'supreme_metal', 'dao', 713, preset_id='core')['id'])
        game.pending_event = None
        for book in books():
            learn_technique(game.player, book)
        engine.store.save(game)
        for book in books()[:8]:
            engine.equip_known_technique(game.id, book.id, 'combat')

        class Quiet(server.Handler):
            def log_message(self, *args):
                pass

        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960))
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    base = f'http://127.0.0.1:{http.server_port}'
                    endpoint = base + f'/api/games/{game.id}/equip-technique'
                    page.goto(base)
                    page.wait_for_function('!!configData && !busy')
                    page.evaluate('id=>loadGame(id)', game.id)
                    reveal(page)
                    assert page.locator('#duel-technique-select option[value="duel-test-8"]').count() == 0
                    for i in range(7):
                        page.locator('#duel-technique-select').select_option(f'duel-test-{i}')
                        page.locator('#duel-technique-add').click()
                        page.wait_for_function('count=>!busy && game.player.duel_techniques.selected.length===count', arg=i+1)
                    assert page.locator('#duel-technique-add').is_disabled()
                    assert page.locator('#duel-technique-select').is_disabled()
                    before = list(engine.store.load(game.id).player.duel_technique_ids)
                    refused = page.request.post(endpoint, data=dict(technique_id='duel-test-7', slot='duel'))
                    assert not refused.ok
                    assert engine.store.load(game.id).player.duel_technique_ids == before
                    page.locator('[data-duel-remove="duel-test-0"]').click()
                    page.wait_for_function('!busy && game.player.duel_techniques.selected.length===6')
                    assert page.locator('#duel-technique-add').is_disabled()
                    page.locator('#duel-technique-select').select_option('duel-test-7')
                    # A second tab fills the vacancy. The first tab must reject,
                    # refresh to the actual seven and release its busy lock.
                    accepted = page.request.post(endpoint, data=dict(technique_id='duel-test-0', slot='duel'))
                    assert accepted.ok
                    page.locator('#duel-technique-add').click()
                    page.wait_for_function('!busy && game.player.duel_techniques.selected.length===7')
                    assert 'duel-test-7' not in engine.store.load(game.id).player.duel_technique_ids
                    assert page.locator('#duel-technique-add').is_disabled()
                    assert page.locator('[data-duel-remove="duel-test-0"]').is_enabled()
                    page.reload();page.wait_for_function('!!configData && !busy')
                    page.evaluate('id=>loadGame(id)', game.id);reveal(page)
                    assert page.locator('[data-duel-remove]').count() == 7
                    for palette in ('light', 'dark'):
                        page.locator('[data-close-dialog=player-details-dialog]').click()
                        set_theme(page, palette)
                        reveal(page)
                        for width, height in ((1440, 960), (390, 844), (844, 390), (320, 740)):
                            page.set_viewport_size(dict(width=width, height=height))
                            page.wait_for_timeout(200)
                            panel = page.locator('#duel-technique-panel')
                            assert panel.evaluate('n=>n.scrollWidth<=n.clientWidth+2'), (palette, width)
                            panel.scroll_into_view_if_needed()
                            page.screenshot(path=str(output / f'{palette}-{width}.png'))
                    current = engine.store.load(game.id)
                    current.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], current, random.Random(1))
                    engine.store.save(current)
                    page.evaluate('id=>loadGame(id)', game.id)
                    # Pending events prevent loadout changes, even via forged HTTP.
                    assert page.locator('[data-duel-remove]').evaluate_all('nodes=>nodes.every(n=>n.disabled)')
                    refused = page.request.post(endpoint, data=dict(technique_id='duel-test-0', slot='duel_remove'))
                    assert not refused.ok
                    assert len(engine.store.load(game.id).player.duel_technique_ids) == 7
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    print('Duel UI passed: seven actual selections, prerequisite, overflow rejection, removal, stale recovery, reload, event lock, two themes/four widths')


if __name__ == '__main__':
    main()
