"""Real four-world DLC UI submissions, upper gates and bounded layouts."""
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
from fixtures.upper_teachings_release import prepare_upper_teachings, WORLDS
from scripts.browser_navigation import navigation_locator, click_control


def main():
    output = ROOT / 'build/upper-teachings-browser'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='upper-teachings-ui-') as folder:
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
                            page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                            errors = []
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_function('!!configData')
                            ids = {path: engine.create_game('上界页面', 'supreme_wood', path, 2143, preset_id='core')['id'] for path in ('buddhist', 'confucian')}
                            for world in WORLDS:
                                identity = ids['buddhist']
                                prepare_upper_teachings(engine, identity, world, 'buddhist')
                                page.evaluate('async id=>loadGame(id)', identity)
                                page.evaluate('t=>document.documentElement.dataset.theme=t', theme)
                                navigation_locator(page, '[data-panel-target=buddhist-wish]').click()
                                panel = page.locator('#buddhist-wish-card')
                                assert panel.get_by_role('button', name='消耗 100 愿力 · 涅槃').is_disabled()
                                assert page.evaluate('game.buddhist_system.wish.value') == 100
                                assert panel.evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                page.screenshot(path=str(output / f'{world}-wish-{width}.png'))
                                navigation_locator(page, '[data-panel-target=buddhist]').click()
                                blessing = page.locator('.dharma-blessing').first
                                click_control(blessing)
                                page.wait_for_function('!busy && game.buddhist_system.blessings[0].selected')
                                identity = ids['confucian']
                                prepare_upper_teachings(engine, identity, world, 'confucian')
                                page.evaluate('async id=>loadGame(id)', identity)
                                navigation_locator(page, '[data-panel-target=sage]').click()
                                page.locator('#sage-teaching-sections').wait_for(state='visible')
                                click_control(page.locator('#sage-doctrine-list').get_by_role('button', name='加入', exact=True).first)
                                page.wait_for_function('!busy && !!game.sage_system.membership_id')
                                assert page.locator('.sage-action-card').count() == 3
                                if world == 'celestial':
                                    before_age = page.evaluate('game.player.age')
                                    click_control(page.locator('.sage-action-card').filter(has_text='解惑'))
                                    page.wait_for_function('age=>!busy && game.player.age>age', arg=before_age, timeout=90000)
                                    assert engine._load(identity).sage_state['active_action'] is None
                                    assert page.evaluate('game.sage_system.last_action.years') > 0
                                navigation_locator(page, '[data-panel-target=sage-inner-outer]').click()
                                manual = page.locator('#sage-manual-list').get_by_role('button', name='炼化', exact=True).first
                                assert manual.is_enabled()
                                before = page.evaluate('game.player.haoran_exp')
                                click_control(manual)
                                click_control(page.locator('#game-confirm-accept'))
                                page.wait_for_function('n=>!busy && game.player.haoran_exp>n', arg=before)
                                assert page.locator('.sage-outer-card').first.get_by_role('button').is_disabled()
                                opportunity = page.locator('.sage-outer-card').last.get_by_role('button')
                                assert opportunity.is_enabled()
                                before = page.evaluate('game.player.opportunity')
                                click_control(opportunity)
                                click_control(page.locator('#game-confirm-accept'))
                                page.wait_for_function('n=>!busy && game.player.opportunity>n', arg=before)
                                assert page.evaluate('game.player.layer') == 1
                                assert page.locator('#sage-inner-outer-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                page.screenshot(path=str(output / f'{world}-sage-{width}.png'))
                            # Authoritative ineligible snapshot must disable the actual button.
                            game = prepare_upper_teachings(engine, ids['buddhist'], 'celestial', 'buddhist')
                            game.player.immortal_veins = {}
                            engine.store.save(game)
                            page.evaluate('async id=>loadGame(id)', game.id)
                            navigation_locator(page, '[data-panel-target=buddhist-wish]').click()
                            assert page.locator('#buddhist-wish-card').get_by_role('button', name='消耗 100 愿力 · 涅槃').is_disabled()
                            assert '练气至大乘' in page.locator('#buddhist-wish-card').inner_text()
                            assert not errors, errors
                            page.close()
                    finally:
                        browser.close()
            finally:
                http.shutdown(); http.server_close()
    (output / 'result.json').write_text(json.dumps(dict(passed=True, checks=['four-worlds', 'nirvana-disabled-wish-retained', 'local-blessing', 'join-local-school', 'upper-classic', 'outer-opportunity', 'busy-unlocked', 'advance-disabled', 'desktop-mobile']), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Upper teachings browser passed: four worlds, both DLCs, real submissions and disabled gates, desktop/mobile')


if __name__ == '__main__': main()
